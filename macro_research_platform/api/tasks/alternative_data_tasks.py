# ═══════════════════════════════════════════════════════════════════════════════
# Celery Alternative Data Tasks — Phase 13C
# Google Trends, JOLTS, Credit Card Spending
# ═══════════════════════════════════════════════════════════════════════════════

import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

import requests
from celery_app import app

logger = logging.getLogger(__name__)

# Alternative data API keys
BLS_API_KEY = os.getenv("BLS_API_KEY", "")
CENSUS_API_KEY = os.getenv("CENSUS_API_KEY", "")


@app.task(bind=True, max_retries=3, default_retry_delay=300)
def fetch_google_trends(self, keywords: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Fetch Google Trends data for macro-related search terms
    Runs daily at 10 AM ET
    """
    if keywords is None:
        keywords = [
            "recession",
            "inflation",
            "unemployment",
            "stock market",
            "housing market",
            "interest rates",
            "bitcoin",
            "gold price",
            "oil price",
            "federal reserve",
        ]

    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "keywords_fetched": [],
        "errors": [],
    }

    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl='en-US', tz=360)

        for keyword in keywords:
            try:
                # Build payload
                pytrends.build_payload([keyword], cat=0, timeframe='today 3-m')

                # Get interest over time
                data = pytrends.interest_over_time()

                if data is not None and not data.empty:
                    latest_value = data[keyword].iloc[-1]
                    avg_value = data[keyword].mean()
                    z_score = (latest_value - avg_value) / data[keyword].std() if data[keyword].std() > 0 else 0

                    signal_data = {
                        "keyword": keyword,
                        "value": float(latest_value),
                        "z_score": float(z_score),
                        "trend": "increasing" if z_score > 1 else "decreasing" if z_score < -1 else "stable",
                        "timestamp": datetime.utcnow().isoformat(),
                    }

                    store_alternative_signal("google_trends", signal_data)
                    results["keywords_fetched"].append(keyword)

                    logger.info(f"Google Trends: {keyword} = {latest_value} (z={z_score:.2f})")
                else:
                    results["errors"].append(f"{keyword}: No data")

            except Exception as e:
                logger.error(f"Failed to fetch Google Trends for {keyword}: {e}")
                results["errors"].append(f"{keyword}: {str(e)}")

        return results

    except ImportError:
        logger.warning("pytrends not installed, skipping Google Trends")
        return {"status": "skipped", "reason": "pytrends not installed"}

    except Exception as exc:
        logger.error(f"Google Trends fetch failed: {exc}")
        raise self.retry(exc=exc)


@app.task(bind=True, max_retries=3, default_retry_delay=600)
def fetch_jolts_data(self) -> Dict[str, Any]:
    """
    Fetch JOLTS (Job Openings and Labor Turnover Survey) data from BLS
    Monthly data, check for updates
    """
    if not BLS_API_KEY:
        logger.warning("BLS_API_KEY not set, skipping JOLTS data")
        return {"status": "skipped", "reason": "No BLS_API_KEY"}

    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "series_fetched": [],
        "errors": [],
    }

    # JOLTS series IDs
    jolts_series = {
        "JTSJOL": "Job Openings",
        "JTS3000OSL": "Hires",
        "JTS3000QUL": "Quits",
        "JTS3000LSL": "Layoffs",
    }

    try:
        headers = {'Content-Type': 'application/json'}
        data = {
            "seriesid": list(jolts_series.keys()),
            "startyear": str(datetime.now().year - 2),
            "endyear": str(datetime.now().year),
            "registrationkey": BLS_API_KEY,
        }

        response = requests.post(
            'https://api.bls.gov/publicAPI/v2/timeseries/data/',
            json=data,
            headers=headers,
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()

            if result.get('status') == 'REQUEST_SUCCEEDED':
                for series in result.get('Results', {}).get('series', []):
                    series_id = series['seriesID']
                    series_name = jolts_series.get(series_id, series_id)

                    # Get latest data point
                    latest = series['data'][0] if series['data'] else None

                    if latest:
                        value_data = {
                            "series_id": series_id,
                            "series_name": series_name,
                            "value": float(latest['value']),
                            "year": latest['year'],
                            "period": latest['period'],
                            "timestamp": datetime.utcnow().isoformat(),
                        }

                        store_alternative_signal("jolts", value_data)
                        results["series_fetched"].append(series_name)

                        logger.info(f"JOLTS: {series_name} = {latest['value']}")
            else:
                results["errors"].append(f"BLS API error: {result.get('message', 'Unknown')}")

        return results

    except Exception as exc:
        logger.error(f"JOLTS data fetch failed: {exc}")
        raise self.retry(exc=exc)


@app.task(bind=True, max_retries=3, default_retry_delay=600)
def fetch_credit_card_spending(self) -> Dict[str, Any]:
    """
    Fetch aggregated credit card spending data
    Requires access to services like Affinity Solutions, Second Measure, or similar
    """
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "status": "not_implemented",
    }

    # This would integrate with actual credit card data providers
    # Examples: Affinity Solutions, Second Measure, Earnest Research

    logger.info("Credit card spending fetch - requires data provider integration")

    return results


def store_alternative_signal(signal_type: str, data: Dict[str, Any]):
    """Store alternative data signal in database"""
    logger.info(f"Storing alternative signal: {signal_type}")
    # Implementation would use SQLAlchemy async session to store in
    # alternative_data_signals table


def calculate_economic_phase_indication(signal_type: str, value: float, z_score: float) -> Optional[str]:
    """
    Calculate which economic phase this signal indicates
    """
    indications = {
        "google_trends": {
            "recession": "contraction_risk" if z_score > 1.5 else None,
            "inflation": "inflation_expectations" if z_score > 1.5 else None,
            "unemployment": "labor_market_stress" if z_score > 1.5 else None,
        },
        "jolts": {
            "high_openings": "expansion",
            "low_openings": "contraction",
            "high_quits": "confidence",
            "low_quits": "fear",
        },
    }

    return indications.get(signal_type, {}).get("default")
