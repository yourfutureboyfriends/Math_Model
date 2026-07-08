"""Market data handler with real data from Yahoo Finance."""
from typing import Dict, Any
from datetime import datetime
import logging

import asyncio
import time as _time

from api.providers import YahooFinanceProvider
from api.providers.fred_provider import FREDProvider

logger = logging.getLogger(__name__)
_yahoo_provider = YahooFinanceProvider()
_fred_provider = FREDProvider()

# Small module-level TTL cache so a burst of /api/market calls does not trigger
# a fresh yfinance history pull for every instrument on every request.
_HISTORY_CACHE: dict[str, tuple[float, dict]] = {}
_HISTORY_TTL = 600  # 10 minutes


def _clean_closes(hist: dict) -> list[float]:
    """Extract non-NaN close prices from a fetch_history result."""
    if not hist or not hist.get("close"):
        return []
    return [c for c in hist["close"] if isinstance(c, (int, float)) and c == c]


def _pct_change(closes: list[float], lookback: int) -> "float | None":
    """Percent change over `lookback` trading days, or None if insufficient data."""
    if len(closes) <= lookback:
        return None
    prev = closes[-1 - lookback]
    cur = closes[-1]
    if not prev:
        return None
    return round((cur / prev - 1.0) * 100.0, 2)


def _percentile_52w(closes: list[float], cur: float) -> "int | None":
    """Where `cur` sits within the trailing range, 0-100. None if flat/empty."""
    if not closes:
        return None
    lo, hi = min(closes), max(closes)
    if hi == lo:
        return 50
    return round((cur - lo) / (hi - lo) * 100)


async def _fetch_closes(yf_ticker: str) -> list[float]:
    """Fetch 1y daily closes for a raw yfinance ticker, cached, off the event loop."""
    now = _time.time()
    cached = _HISTORY_CACHE.get(yf_ticker)
    if cached and now - cached[0] < _HISTORY_TTL:
        return cached[1].get("closes", [])
    try:
        hist = await asyncio.to_thread(_yahoo_provider.fetch_history, yf_ticker, "1y", "1d")
    except Exception as e:
        logger.warning(f"history fetch failed for {yf_ticker}: {e}")
        hist = None
    closes = _clean_closes(hist)
    if closes:
        _HISTORY_CACHE[yf_ticker] = (now, {"closes": closes})
    return closes


def _fred_recent_values(series_id: str, n: int = 8) -> list[float]:
    """Most-recent `n` numeric observations for a FRED series, newest first."""
    from api.config import FRED_API_KEY
    if not FRED_API_KEY:
        return []
    try:
        import requests
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}&api_key={FRED_API_KEY}"
            f"&file_type=json&sort_order=desc&limit={n}"
        )
        resp = requests.get(url, timeout=(3, 10))
        resp.raise_for_status()
        vals = []
        for obs in resp.json().get("observations", []):
            v = obs.get("value")
            if v not in (".", "", None):
                vals.append(float(v))
        return vals
    except Exception as e:
        logger.warning(f"FRED recent-values fetch failed for {series_id}: {e}")
        return []


async def _credit_spread(name: str, series_id: str, tight_bps: float, wide_bps: float,
                         fallback_bps: float) -> Dict[str, Any]:
    """Live ICE BofA OAS credit spread (percent -> bps) with a real 1-week change."""
    vals = await asyncio.to_thread(_fred_recent_values, series_id, 8)
    if not vals:
        return {"name": name, "spreadBps": fallback_bps, "change1wBps": None,
                "signal": "normal"}
    spread_bps = round(vals[0] * 100)  # OAS is in percent
    # ~5 trading days ago for the 1-week change; fall back to oldest available.
    prior = vals[5] if len(vals) > 5 else vals[-1]
    change_1w = round((vals[0] - prior) * 100)
    signal = "tight" if spread_bps < tight_bps else "wide" if spread_bps > wide_bps else "normal"
    return {"name": name, "spreadBps": spread_bps, "change1wBps": change_1w, "signal": signal}


async def get_rates_data() -> Dict[str, Any]:
    """Get interest rates data from Yahoo Finance with yield curve structure."""
    logger.info("Fetching rates data")

    # Fetch treasury yields
    result = await _yahoo_provider.fetch_latest_async(['TENYR', 'TWYR'])

    ten_yr = None
    two_yr = None
    if result.success and result.data:
        ten_yr = result.data.get('TENYR', {}).price if 'TENYR' in result.data else None
        two_yr = result.data.get('TWYR', {}).price if 'TWYR' in result.data else None

    # Use fallback values if fetch failed
    ten_yr = ten_yr or 4.5
    two_yr = two_yr or 4.2

    # Live effective fed funds rate from FRED (was hardcoded 5.25, which is stale
    # and falsely inverts the 3m10y curve). Fall back to a plausible level on failure.
    fed_funds = None
    try:
        obs = _fred_provider.fetch_latest("FEDFUNDS")
        if obs is not None:
            fed_funds = obs.value
    except Exception as e:
        logger.warning(f"FEDFUNDS fetch failed: {e}")
    fed_funds = fed_funds if fed_funds is not None else 4.3

    # Calculate spreads
    spread_2s10s = (ten_yr - two_yr) * 100  # Convert to basis points for frontend
    spread_3m10y = (ten_yr - fed_funds) * 100

    # Determine curve shape
    shape = "inverted" if spread_2s10s < 0 else "flat" if spread_2s10s < 25 else "steep"

    # 12-month-ahead recession probability via the documented, unit-tested
    # Estrella-Mishkin probit (see api/calculations/models.py). Uses the 3m10y spread
    # in percentage points; falls back to a mid estimate only on an implausible input.
    from api.calculations.models import estrella_mishkin_recession_prob
    spread_3m10y_pp = spread_3m10y / 100.0  # spread_3m10y is in bps; model needs pp
    try:
        recession_prob = estrella_mishkin_recession_prob(spread_3m10y_pp)
    except ValueError as e:
        logger.warning(f"recession probit input rejected: {e}")
        recession_prob = 0.5

    # Build yield curve points (synthetic based on 2Y and 10Y)
    # Interpolate between known points
    curve_points = []
    tenors = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30]  # in years

    for tenor in tenors:
        if tenor <= 2:
            # Interpolate between Fed funds (0) and 2Y
            yield_val = fed_funds + (two_yr - fed_funds) * (tenor / 2)
        elif tenor <= 10:
            # Interpolate between 2Y and 10Y
            yield_val = two_yr + (ten_yr - two_yr) * ((tenor - 2) / 8)
        else:
            # Extrapolate beyond 10Y with a small linear term premium (~1.2bps/yr).
            # 20Y ~ +0.12pp, 30Y ~ +0.24pp above the 10Y — a realistic long-end slope.
            yield_val = ten_yr + 0.012 * (tenor - 10)
        curve_points.append({"tenor": tenor, "yield": round(yield_val, 2)})

    # Real yield (nominal - inflation, assuming 3% inflation)
    real_yield_10y = ten_yr - 3.0

    # Live ICE BofA OAS credit spreads with real 1-week changes.
    credit_spreads = await asyncio.gather(
        _credit_spread("Investment Grade", "BAMLC0A0CM", 120, 200, 85),
        _credit_spread("High Yield", "BAMLH0A0HYM2", 350, 600, 320),
        _credit_spread("Emerging Markets", "BAMLEMCBPIOAS", 300, 500, 280),
    )

    return {
        # New structure expected by frontend
        "yieldCurves": {
            "US": {
                "country": "US",
                "points": curve_points,
                "spread2s10s": round(spread_2s10s, 1),
                "spread3m10y": round(spread_3m10y, 1),
                "spread5s30s": round(40.0, 1),  # Synthetic
                "realYield10y": round(real_yield_10y, 2),
                "shape": shape,
                "recessionProb": round(recession_prob, 2)
            },
            "UK": {
                "country": "UK",
                "points": [{"tenor": t, "yield": round(4.0 + t * 0.05, 2)} for t in tenors],
                "spread2s10s": 35.0,
                "spread3m10y": 45.0,
                "shape": "normal",
                "recessionProb": 0.15
            },
            "DE": {
                "country": "DE",
                "points": [{"tenor": t, "yield": round(2.5 + t * 0.03, 2)} for t in tenors],
                "spread2s10s": 25.0,
                "spread3m10y": 30.0,
                "shape": "flat",
                "recessionProb": 0.20
            },
            "JP": {
                "country": "JP",
                "points": [{"tenor": t, "yield": round(0.5 + t * 0.02, 2)} for t in tenors],
                "spread2s10s": 15.0,
                "spread3m10y": 20.0,
                "shape": "normal",
                "recessionProb": 0.10
            },
            "CA": {
                "country": "CA",
                "points": [{"tenor": t, "yield": round(3.8 + t * 0.04, 2)} for t in tenors],
                "spread2s10s": 30.0,
                "spread3m10y": 40.0,
                "shape": "normal",
                "recessionProb": 0.18
            },
            "AU": {
                "country": "AU",
                "points": [{"tenor": t, "yield": round(4.2 + t * 0.05, 2)} for t in tenors],
                "spread2s10s": 40.0,
                "spread3m10y": 50.0,
                "shape": "steep",
                "recessionProb": 0.12
            }
        },
        "creditSpreads": list(credit_spreads),
        "realYieldSignal": "positive" if real_yield_10y > 1.0 else "negative" if real_yield_10y < 0 else "neutral",
        # Legacy fields for backward compatibility
        "tenYear": round(ten_yr, 2),
        "twoYear": round(two_yr, 2),
        "fedFunds": fed_funds,
        "yieldCurve": shape,
        "lastUpdated": datetime.now().isoformat()
    }


async def get_fx_data() -> Dict[str, Any]:
    """Get FX data from Yahoo Finance with real daily % changes."""
    logger.info("Fetching FX data")

    # (canonical symbol, response key, yfinance ticker for history, decimals, fallback)
    pairs = [
        ("DXY", "dxy", "DX-Y.NYB", 2, 104.0),
        ("EURUSD", "eurusd", "EURUSD=X", 4, 1.08),
        ("GBPUSD", "gbpusd", "GBPUSD=X", 4, 1.265),
        ("USDJPY", "usdjpy", "USDJPY=X", 2, 148.2),  # raw ticker already quotes USD/JPY
    ]

    out: Dict[str, Any] = {"lastUpdated": datetime.now().isoformat()}
    for canonical, key, yf_ticker, dp, fallback in pairs:
        closes = await _fetch_closes(yf_ticker)
        if closes:
            spot = closes[-1]
            out[key] = round(spot, dp)
            out[f"{key}Change"] = _pct_change(closes, 1)
        else:
            out[key] = fallback
            out[f"{key}Change"] = None  # explicit: daily change unavailable
    return out


async def get_commodities_data() -> Dict[str, Any]:
    """Get commodities data with real prices, changes and calculated macro signals."""
    logger.info("Fetching commodities data")

    # (symbol, name, yfinance ticker, decimals, spot fallback)
    specs = [
        ("energy", "CL", "WTI Crude", "CL=F", 2, 75.5),
        ("energy", "NG", "Natural Gas", "NG=F", 2, 2.85),
        ("metals", "GC", "Gold", "GC=F", 2, 2050.0),
        ("metals", "HG", "Copper", "HG=F", 4, 3.85),
        ("metals", "SI", "Silver", "SI=F", 2, 24.5),
        ("agriculture", "ZC", "Corn", "ZC=F", 2, 4.45),
        ("agriculture", "ZS", "Soybeans", "ZS=F", 2, 11.85),
        ("agriculture", "ZW", "Wheat", "ZW=F", 2, 5.95),
    ]

    # Fetch all histories concurrently (each is cached + off the event loop).
    closes_list = await asyncio.gather(*[_fetch_closes(s[3]) for s in specs])

    groups: Dict[str, list] = {"energy": [], "metals": [], "agriculture": []}
    spot_by_symbol: Dict[str, float] = {}
    for (group, sym, name, _tick, dp, fallback), closes in zip(specs, closes_list):
        if closes:
            spot = closes[-1]
            row = {
                "symbol": sym,
                "name": name,
                "spot": round(spot, dp),
                "change1d": _pct_change(closes, 1),
                "change1m": _pct_change(closes, 21),
                "change3m": _pct_change(closes, 63),
                "week52Percentile": _percentile_52w(closes, spot),
            }
        else:
            # No live data — surface the fallback spot but null the changes rather
            # than inventing them, so the UI can show "--" honestly.
            row = {
                "symbol": sym, "name": name, "spot": round(fallback, dp),
                "change1d": None, "change1m": None, "change3m": None,
                "week52Percentile": None,
            }
        groups[group].append(row)
        spot_by_symbol[sym] = row["spot"]

    gold_price = spot_by_symbol.get("GC", 2050.0)
    copper_price = spot_by_symbol.get("HG", 3.85)
    oil_row = groups["energy"][0]
    oil_change_1d = oil_row.get("change1d") or 0.0
    gold_change_1d = groups["metals"][0].get("change1d") or 0.0

    # Copper/gold ratio (copper $/lb vs gold $/oz-in-thousands)
    from api.calculations.models import copper_gold_ratio as _copper_gold_ratio
    try:
        copper_gold_ratio = _copper_gold_ratio(copper_price, gold_price)
    except ValueError:
        copper_gold_ratio = 0.0
    ratio_signal = "RISK-ON" if copper_gold_ratio > 1.8 else "RISK-OFF"

    oil_trend = "RISING" if oil_change_1d > 0 else "FALLING"
    oil_interpretation = "Supply concerns" if oil_change_1d > 0 else "Demand moderation"

    inflation_score = (gold_change_1d + oil_change_1d) / 2
    inflation_signal = "RISING" if inflation_score > 0 else "FALLING"

    return {
        "commodities": groups,
        "macroSignals": {
            "copperGoldRatio": {
                "value": round(copper_gold_ratio, 4),
                "signal": ratio_signal,
                "description": "Growth indicator based on copper/gold ratio"
            },
            "oilTrend": {
                "direction": oil_trend,
                "interpretation": oil_interpretation
            },
            "commodityInflationIndex": {
                "score": round(inflation_score, 2),
                "signal": inflation_signal
            }
        },
        "lastUpdated": datetime.now().isoformat()
    }


async def get_prices_data() -> Dict[str, Any]:
    """Get current prices for key assets from Yahoo Finance."""
    logger.info("Fetching prices data")

    result = await _yahoo_provider.fetch_latest_async(['SPX', 'NDX', 'VIX', 'DXY'])
    yf_tickers = {'SPX': '^GSPC', 'NDX': '^NDX', 'VIX': '^VIX', 'DXY': 'DX-Y.NYB'}
    # Last-resort static fallbacks, used ONLY when neither the live quote nor the
    # cached daily history is available.
    static_fallback = {'SPX': 5800.0, 'NDX': 18500.0, 'VIX': 18.0, 'DXY': 104.0}

    prices = {}
    for symbol in ['SPX', 'NDX', 'VIX', 'DXY']:
        # Cached 1y history — stable across the frequent refresh polls even when the
        # live yf.download quote intermittently rate-limits (which previously flipped
        # the ticker to a fake 5800). Prefer live quote, fall back to last close.
        closes = await _fetch_closes(yf_tickers[symbol])
        live = result.data.get(symbol) if (result.success and result.data) else None
        if live is not None:
            price = live.price
        elif closes:
            price = closes[-1]
        else:
            price = static_fallback[symbol]
        change = _pct_change(closes, 1) if closes else None
        prices[symbol] = {
            "price": round(price, 2),
            "change_pct": change if change is not None else 0.0,
        }

    return {
        **prices,
        "lastUpdated": datetime.now().isoformat()
    }
