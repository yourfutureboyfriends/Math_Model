"""
Canonical Price Cache — Single Source of Truth for Market Prices

This is the ONLY place in the entire backend that fetches live market prices.
All endpoints must read from this cache via get_price() or get_all_prices().

Rules:
- Never fetch prices directly in endpoint handlers
- All FX pairs verified correct direction (USDJPY ~145-160, not 0.006)
- FED rate returned as decimal (3.64), NOT basis points (364)
- Cache refreshes every 60 seconds via scheduler
"""

import os
from typing import Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Symbol mapping: canonical name -> yfinance ticker
SYMBOLS = {
    'SPX': '^GSPC',
    'NDX': '^NDX',
    'VIX': '^VIX',
    'TENYR': '^TNX',
    'TWYR': '^FVX',
    'DXY': 'DX-Y.NYB',
    'EURUSD': 'EURUSD=X',
    'GBPUSD': 'GBPUSD=X',
    'USDJPY': 'JPY=X',      # Will be inverted (yfinance gives JPY/USD)
    'USDCAD': 'CAD=X',      # Will be inverted
    'USDCHF': 'CHF=X',      # Will be inverted
    'AUDUSD': 'AUDUSD=X',
    'NZDUSD': 'NZDUSD=X',
    'GLD': 'GC=F',
    'WTI': 'CL=F',
}

# FX pairs that need inversion (yfinance returns quote/base instead of base/quote)
INVERT_PAIRS = {'USDJPY', 'USDCAD', 'USDCHF'}

# Cache storage
_PRICE_CACHE: Dict[str, Optional[float]] = {}
_LAST_UPDATE: Optional[datetime] = None
_CACHE_TTL_SECONDS = 60


def _get_fred_rate(series_id: str) -> Optional[float]:
    """Fetch latest rate from FRED API."""
    from api.config import FRED_API_KEY as _cfg_key
    api_key = _cfg_key or os.getenv('FRED_API_KEY', '')
    if not api_key or api_key == 'your_fred_api_key_here':
        return None

    try:
        import requests
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}"
            f"&api_key={api_key}"
            f"&file_type=json"
            f"&sort_order=desc"
            f"&limit=1"
        )
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get('observations'):
            val = data['observations'][0].get('value')
            if val and val != '.':
                return float(val)
    except Exception as e:
        logger.debug(f"FRED fetch failed for {series_id}: {e}")
    return None


def refresh_prices() -> Dict[str, Optional[float]]:
    """
    Fetch all prices in one batch from yfinance.
    Called by scheduler every 60 seconds.
    Returns the updated cache.
    """
    global _PRICE_CACHE, _LAST_UPDATE

    try:
        import yfinance as yf

        # Download all symbols in one batch — timeout=5 prevents hang when proxy blocks
        yf_symbols = list(SYMBOLS.values())
        data = yf.download(
            yf_symbols,
            period='2d',  # Get 2 days for change calculation
            interval='1d',
            progress=False,
            threads=False,
            timeout=5,
        )

        if data.empty:
            logger.warning("Price refresh returned empty data")
            return _PRICE_CACHE

        # Process each symbol
        for canonical, yf_symbol in SYMBOLS.items():
            try:
                if 'Close' in data.columns:
                    close_series = data['Close'][yf_symbol]
                else:
                    close_series = data[yf_symbol]['Close'] if yf_symbol in data else None

                if close_series is None or close_series.empty:
                    continue

                latest = float(close_series.iloc[-1])

                # Apply inversion for USD-base pairs
                if canonical in INVERT_PAIRS and latest != 0:
                    latest = 1 / latest

                _PRICE_CACHE[canonical] = latest

            except Exception as e:
                logger.debug(f"Failed to process {canonical}: {e}")
                continue

        # Fetch FED rate from FRED (returns as annual %, e.g. 3.64)
        fed_rate = _get_fred_rate('DFEDTARU') or _get_fred_rate('FEDFUNDS')
        if fed_rate is not None:
            # Ensure it's stored as decimal (3.64), not basis points
            if fed_rate > 20:  # Basis points detected
                fed_rate = fed_rate / 100
            _PRICE_CACHE['FED'] = fed_rate
        else:
            # Fallback: try to get from cache or use default
            _PRICE_CACHE['FED'] = _PRICE_CACHE.get('FED', 3.64)

        _LAST_UPDATE = datetime.utcnow()
        logger.info(f"Price cache refreshed: {len([v for v in _PRICE_CACHE.values() if v is not None])}/{len(SYMBOLS)} instruments")

    except Exception as e:
        logger.error(f"Price refresh failed: {e}", exc_info=True)

    return _PRICE_CACHE.copy()


def get_price(symbol: str) -> Optional[float]:
    """
    Get cached price for a symbol.
    Returns None if unavailable.
    """
    return _PRICE_CACHE.get(symbol.upper())


def get_all_prices() -> Dict[str, Optional[float]]:
    """
    Return entire price cache.
    Returns a copy to prevent external mutation.
    """
    return _PRICE_CACHE.copy()


def get_last_update() -> Optional[datetime]:
    """Get timestamp of last cache update."""
    return _LAST_UPDATE


def compute_daily_changes() -> Dict[str, Optional[float]]:
    """
    Compute daily percent changes for all cached prices.
    Uses a single batch yf.download (timeout=5s) instead of per-symbol Ticker calls
    to avoid blocking for minutes when the network proxy is unavailable.
    Returns dict of symbol -> change_pct (e.g., 0.0114 = +1.14%).
    """
    changes: Dict[str, Optional[float]] = {sym: None for sym in SYMBOLS}

    try:
        import yfinance as yf

        yf_symbols = list(SYMBOLS.values())
        data = yf.download(
            yf_symbols,
            period='2d',
            interval='1d',
            progress=False,
            threads=False,
            timeout=5,
        )

        if data.empty:
            logger.warning("compute_daily_changes: empty data from yfinance")
            return changes

        for canonical, yf_symbol in SYMBOLS.items():
            try:
                if 'Close' in data.columns.get_level_values(0) if hasattr(data.columns, 'get_level_values') else []:
                    close_series = data['Close'][yf_symbol]
                elif yf_symbol in data.columns:
                    close_series = data[yf_symbol]['Close']
                else:
                    continue

                valid = close_series.dropna()
                if len(valid) >= 2:
                    latest = float(valid.iloc[-1])
                    prev = float(valid.iloc[-2])

                    if canonical in INVERT_PAIRS:
                        latest = 1 / latest if latest != 0 else 0
                        prev = 1 / prev if prev != 0 else 0

                    changes[canonical] = (latest - prev) / prev if prev != 0 else 0.0
                else:
                    changes[canonical] = 0.0

            except Exception as e:
                logger.debug(f"Change calc failed for {canonical}: {e}")

    except Exception as e:
        logger.error(f"compute_daily_changes failed: {e}")

    return changes


def get_price_with_change(symbol: str) -> Dict[str, Optional[float]]:
    """
    Get price and daily change for a symbol.
    Returns {price, change_pct, price_prev}.
    """
    price = get_price(symbol)
    changes = compute_daily_changes()
    change_pct = changes.get(symbol.upper())

    return {
        'price': price,
        'change_pct': change_pct,
        'price_prev': price / (1 + change_pct) if price and change_pct is not None else None
    }


def is_cache_fresh(max_age_seconds: int = 120) -> bool:
    """Check if cache is fresh (default: 2 minutes)."""
    if _LAST_UPDATE is None:
        return False
    return (datetime.utcnow() - _LAST_UPDATE).total_seconds() < max_age_seconds


# NOTE: Do NOT call refresh_prices() at import time.
# It calls yf.download() which blocks the async event loop during startup.
# The APScheduler fires the first refresh 60s after startup via lifespan.
# All endpoints use fallback values until the first scheduled refresh completes.
