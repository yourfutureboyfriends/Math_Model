# ═══════════════════════════════════════════════════════════════════════════════
# Celery Pipeline Tasks — Data ingestion and updates
# ═══════════════════════════════════════════════════════════════════════════════

import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any

import asyncpg
import yfinance as yf
from fredapi import Fred
from celery_app import app

logger = logging.getLogger(__name__)

# Import from centralized config
from api.config import FRED_API_KEY, DATABASE_URL

# Fallback for backward compatibility
if not FRED_API_KEY:
    FRED_API_KEY = os.getenv("FRED_API_KEY", "")


async def get_db_pool():
    """Get async database connection pool"""
    return await asyncpg.create_pool(DATABASE_URL)


@app.task(bind=True, max_retries=3, default_retry_delay=60)
def refresh_market_data(self, symbols: Optional[list] = None) -> Dict[str, Any]:
    """
    Refresh market data for specified symbols (default: major indices and ETFs)
    Runs every 5 minutes during market hours
    """
    if symbols is None:
        symbols = ["SPY", "QQQ", "IWM", "VIXY", "TLT", "GLD", "USO", "DXY"]

    results = {"success": [], "failed": [], "timestamp": datetime.utcnow().isoformat()}

    try:
        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="5d", interval="5m")

                if hist.empty:
                    results["failed"].append(f"{symbol}: No data")
                    continue

                # Get latest data point
                latest = hist.iloc[-1]
                timestamp = hist.index[-1]

                # Store in database (async in sync context via run_in_executor or celery beat)
                # For now, log the data
                logger.info(f"Market data: {symbol} @ {timestamp} = {latest['Close']:.2f}")
                results["success"].append(symbol)

            except Exception as e:
                logger.error(f"Failed to fetch {symbol}: {e}")
                results["failed"].append(f"{symbol}: {str(e)}")

        return results

    except Exception as exc:
        logger.error(f"Market data refresh failed: {exc}")
        raise self.retry(exc=exc)


@app.task(bind=True, max_retries=3, default_retry_delay=300)
def update_economic_indicators(self) -> Dict[str, Any]:
    """
    Update economic indicators from FRED
    Runs hourly
    """
    if not FRED_API_KEY:
        logger.warning("FRED_API_KEY not set, skipping economic indicators")
        return {"status": "skipped", "reason": "No FRED_API_KEY"}

    results = {"success": [], "failed": [], "timestamp": datetime.utcnow().isoformat()}

    # Key FRED series
    series = {
        "GDP": "Gross Domestic Product",
        "CPIAUCSL": "Consumer Price Index",
        "UNRATE": "Unemployment Rate",
        "FEDFUNDS": "Federal Funds Rate",
        "T10Y2Y": "10Y-2Y Spread",
        "DCOILWTICO": "WTI Crude Oil",
        "DGS10": "10-Year Treasury",
        "VIXCLS": "VIX",
        "INDPRO": "Industrial Production",
        "PAYEMS": "Nonfarm Payrolls",
        "RSXFS": "Retail Sales",
        "HOUST": "Housing Starts",
        "PERMIT": "Building Permits",
        "M2SL": "M2 Money Stock",
        "TOTALSA": "Total Vehicle Sales",
        "UMCSENT": "Consumer Sentiment",
    }

    try:
        fred = Fred(api_key=FRED_API_KEY)

        for series_id, description in series.items():
            try:
                data = fred.get_series_latest_release(series_id)
                if data is not None and len(data) > 0:
                    latest_value = data.iloc[-1]
                    latest_date = data.index[-1]

                    logger.info(f"FRED: {series_id} ({description}) = {latest_value} @ {latest_date}")
                    results["success"].append(series_id)
                else:
                    results["failed"].append(f"{series_id}: No data")

            except Exception as e:
                logger.error(f"Failed to fetch {series_id}: {e}")
                results["failed"].append(f"{series_id}: {str(e)}")

        return results

    except Exception as exc:
        logger.error(f"Economic indicators update failed: {exc}")
        raise self.retry(exc=exc)


@app.task(bind=True, max_retries=3, default_retry_delay=3600)
def update_cot_data(self) -> Dict[str, Any]:
    """
    Update CFTC Commitment of Traders data
    Runs Tuesdays after CFTC release (weekly)
    """
    results = {"status": "pending", "timestamp": datetime.utcnow().isoformat()}

    try:
        # COT data requires CFTC API or scraping
        # For now, placeholder for actual implementation
        logger.info("COT data update triggered")

        # Implementation would:
        # 1. Fetch latest CFTC COT reports
        # 2. Parse non-commercial positioning
        # 3. Calculate percentiles and contrarian signals
        # 4. Store in database

        results["status"] = "completed"
        return results

    except Exception as exc:
        logger.error(f"COT data update failed: {exc}")
        raise self.retry(exc=exc)


@app.task(bind=True, max_retries=3, default_retry_delay=60)
def update_vol_surface(self) -> Dict[str, Any]:
    """
    Update volatility surface data
    Runs every 15 minutes
    """
    results = {"success": False, "timestamp": datetime.utcnow().isoformat()}

    try:
        # Fetch VIX data from Yahoo Finance
        vix = yf.Ticker("^VIX")
        vix_hist = vix.history(period="1mo")

        if not vix_hist.empty:
            vix_spot = vix_hist['Close'].iloc[-1]
            logger.info(f"VIX spot: {vix_spot:.2f}")

            # Calculate term structure metrics
            # Implementation would fetch VIX futures for term structure

            results["success"] = True
            results["vix_spot"] = float(vix_spot)

        return results

    except Exception as exc:
        logger.error(f"Vol surface update failed: {exc}")
        raise self.retry(exc=exc)


@app.task
def check_system_health() -> Dict[str, Any]:
    """
    Check system health and log metrics
    Runs every minute
    """
    import psutil

    metrics = {
        "timestamp": datetime.utcnow().isoformat(),
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory": {
            "percent": psutil.virtual_memory().percent,
            "used_gb": psutil.virtual_memory().used / (1024**3),
            "available_gb": psutil.virtual_memory().available / (1024**3),
        },
        "disk": {
            "percent": psutil.disk_usage('/').percent,
            "used_gb": psutil.disk_usage('/').used / (1024**3),
            "free_gb": psutil.disk_usage('/').free / (1024**3),
        },
    }

    # Check Redis connection
    try:
        import redis
        r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        r.ping()
        metrics["redis"] = "connected"
    except Exception as e:
        metrics["redis"] = f"error: {str(e)}"

    logger.info(f"System health: CPU {metrics['cpu_percent']}%, Memory {metrics['memory']['percent']}%")

    return metrics
