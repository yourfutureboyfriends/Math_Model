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


async def _fetch_dated_closes_literal(ticker: str, period: str = "1y") -> dict:
    """{ 'YYYY-MM-DD': close } for a literal ticker's daily history (cached).

    Dated so callers can align multiple series on common trading days before
    regressing — essential for a correct factor model. `period` is a yfinance period.
    """
    key = f"__dated__:{ticker}" if period == "1y" else f"__dated__:{ticker}:{period}"
    now = _time.time()
    cached = _HISTORY_CACHE.get(key)
    if cached and now - cached[0] < _HISTORY_TTL:
        return cached[1].get("dated", {})

    def _pull():
        import yfinance as yf
        from api.market_dates import align_frame
        # FX bars are re-dated to their NY session (see api/market_dates.py).
        hist = align_frame(ticker, yf.Ticker(ticker).history(period=period, interval="1d"))
        if hist is None or hist.empty:
            return {}
        out = {}
        for ts, close in zip(hist.index, hist["Close"].tolist()):
            if isinstance(close, (int, float)) and close == close:
                out[str(ts)[:10]] = float(close)
        return out

    try:
        dated = await asyncio.to_thread(_pull)
    except Exception as e:
        logger.warning(f"dated history fetch failed for {ticker}: {e}")
        dated = {}
    if dated:
        _HISTORY_CACHE[key] = (now, {"dated": dated})
    return dated


async def _fetch_closes_literal(ticker: str) -> list[float]:
    """1y daily closes for a LITERAL yfinance ticker, bypassing the macro SYMBOL_MAP.

    Position tickers must resolve to themselves (GLD = the GLD ETF, not gold futures),
    unlike the dashboard's macro proxies. Cached separately from the mapped fetches.
    """
    key = f"__literal__:{ticker}"
    now = _time.time()
    cached = _HISTORY_CACHE.get(key)
    if cached and now - cached[0] < _HISTORY_TTL:
        return cached[1].get("closes", [])

    def _pull():
        import yfinance as yf
        from api.market_dates import align_frame
        hist = align_frame(ticker, yf.Ticker(ticker).history(period="1y", interval="1d"))
        if hist is None or hist.empty:
            return []
        return [c for c in hist["Close"].tolist() if isinstance(c, (int, float)) and c == c]

    try:
        closes = await asyncio.to_thread(_pull)
    except Exception as e:
        logger.warning(f"literal history fetch failed for {ticker}: {e}")
        closes = []
    if closes:
        _HISTORY_CACHE[key] = (now, {"closes": closes})
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


async def _credit_spread(name: str, series_id: str, tight_bps: float,
                         wide_bps: float) -> Dict[str, Any]:
    """Live ICE BofA OAS credit spread (percent -> bps) with a real 1-week change.
    None (not a placeholder level) when FRED is unavailable."""
    vals = await asyncio.to_thread(_fred_recent_values, series_id, 8)
    if not vals:
        return {"name": name, "spreadBps": None, "change1wBps": None, "signal": None}
    spread_bps = round(vals[0] * 100)  # OAS is in percent
    # ~5 trading days ago for the 1-week change; fall back to oldest available.
    prior = vals[5] if len(vals) > 5 else vals[-1]
    change_1w = round((vals[0] - prior) * 100)
    signal = "tight" if spread_bps < tight_bps else "wide" if spread_bps > wide_bps else "normal"
    return {"name": name, "spreadBps": spread_bps, "change1wBps": change_1w, "signal": signal}


async def get_rates_data() -> Dict[str, Any]:
    """Get interest rates data from Yahoo Finance with yield curve structure."""
    logger.info("Fetching rates data")

    # 10Y live from Yahoo (^TNX); 2Y and 3M from FRED — Yahoo has no 2-year index
    # (^FVX is the 5-year) and Estrella-Mishkin is estimated on the 3M bill, not Fed funds.
    from api.handlers.macro_inputs import load_macro_inputs
    inputs = await load_macro_inputs()
    result = await _yahoo_provider.fetch_latest_async(['TENYR'])
    ten_yr = None
    if result.success and result.data:
        ten_yr = getattr(result.data.get('TENYR'), 'price', None)
    ten_yr = ten_yr if ten_yr is not None else inputs["dgs10"].latest
    two_yr = inputs["dgs2"].latest
    three_mo = inputs["dgs3mo"].latest
    fed_funds = inputs["dff"].latest

    missing = [n for n, v in (("10Y", ten_yr), ("2Y (FRED DGS2)", two_yr),
                              ("3M (FRED DGS3MO)", three_mo), ("Fed funds (FRED DFF)", fed_funds))
               if v is None]
    if missing:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Rates inputs unavailable: " + ", ".join(missing))

    # Spreads from SAME-DAY FRED yields. Subtracting FRED's 2Y (yesterday) from Yahoo's
    # live 10Y (today) put a day's 10Y move into the spread (49.7bp vs the official 45).
    dgs10_s = inputs["dgs10"]
    c2 = dgs10_s.last_common(inputs["dgs2"])
    c3 = dgs10_s.last_common(inputs["dgs3mo"])
    spread_2s10s = (c2[1] - c2[2]) * 100 if c2 else (ten_yr - two_yr) * 100
    spread_3m10y = (c3[1] - c3[2]) * 100 if c3 else (ten_yr - three_mo) * 100
    spreads_as_of = c2[0] if c2 else None

    # Determine curve shape
    from api.handlers.dashboard_sections import curve_shape
    shape = curve_shape(spread_2s10s)

    # 12-month-ahead recession probability via the documented, unit-tested
    # Estrella-Mishkin probit (see api/calculations/models.py). Uses the 3m10y spread
    # in percentage points; None (not a made-up 0.5) on an implausible input.
    from api.calculations.models import estrella_mishkin_recession_prob
    spread_3m10y_pp = spread_3m10y / 100.0  # spread_3m10y is in bps; model needs pp
    try:
        recession_prob = estrella_mishkin_recession_prob(spread_3m10y_pp)
    except ValueError as e:
        logger.warning(f"recession probit input rejected: {e}")
        recession_prob = None

    # Real curve points: FRED constant-maturity Treasury yields at every tenor (1M-30Y),
    # TIPS 10Y real yield, and OECD 3M / 10Y yields for the other countries.
    from api.handlers.dashboard_sections import (
        rates_fred_ids, us_curve_points, foreign_curve, FOREIGN_CURVES)
    from api.handlers.macro_inputs import load_fred_series
    curve_fred = await load_fred_series(rates_fred_ids())
    curve_points = us_curve_points(curve_fred)
    dgs5, dgs30 = curve_fred.get("DGS5"), curve_fred.get("DGS30")
    c530 = dgs30.last_common(dgs5) if (dgs5 and dgs30) else None
    spread_5s30s = (c530[1] - c530[2]) * 100 if c530 else None
    dfii10 = curve_fred.get("DFII10")
    real_yield_10y = dfii10.latest if dfii10 else None

    # Live ICE BofA OAS credit spreads with real 1-week changes.
    credit_spreads = await asyncio.gather(
        _credit_spread("Investment Grade", "BAMLC0A0CM", 120, 200),
        _credit_spread("High Yield", "BAMLH0A0HYM2", 350, 600),
        _credit_spread("Emerging Markets", "BAMLEMCBPIOAS", 300, 500),
    )

    return {
        # New structure expected by frontend
        "yieldCurves": {
            "US": {
                "country": "US",
                "points": curve_points,
                "spread2s10s": round(spread_2s10s, 1),
                "spread3m10y": round(spread_3m10y, 1),
                "spread5s30s": round(spread_5s30s, 1) if spread_5s30s is not None else None,
                "realYield10y": round(real_yield_10y, 2) if real_yield_10y is not None else None,
                "shape": shape,
                "recessionProb": round(recession_prob, 2) if recession_prob is not None else None,
                "asOf": {"spreads": spreads_as_of} if spreads_as_of else None,
                "source": "FRED constant-maturity yields (spreads on a common date)",
            },
            **{cc: foreign_curve(cc, curve_fred) for cc in FOREIGN_CURVES},
        },
        "creditSpreads": list(credit_spreads),
        "realYieldSignal": (None if real_yield_10y is None else
                            "positive" if real_yield_10y > 1.0 else "negative" if real_yield_10y < 0 else "neutral"),
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
            # Unavailable is reported as null — never a hard-coded "typical" level shown as live.
            out[key] = None
            out[f"{key}Change"] = None
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
            # No data: null, never a hard-coded spot (2050 gold was shown with gold at 4,100+).
            row = {
                "symbol": sym, "name": name, "spot": None, "available": False,
                "change1d": None, "change1m": None, "change3m": None,
                "week52Percentile": None,
            }
        groups[group].append(row)
        if row["spot"] is not None:
            spot_by_symbol[sym] = row["spot"]

    from api.calculations.commodity_signals import (
        copper_gold_signal, oil_trend_signal, broad_commodity_momentum)
    hg, gc = await asyncio.gather(_fetch_dated_closes_literal("HG=F"), _fetch_dated_closes_literal("GC=F"))
    oil_row = groups["energy"][0]

    return {
        "commodities": groups,
        "macroSignals": {
            # Judged against the ratio's own history: a fixed 1.8 threshold (set when gold was
            # ~$2,000) read RISK-OFF permanently once gold doubled.
            "copperGoldRatio": copper_gold_signal(hg, gc),
            "oilTrend": oil_trend_signal(oil_row.get("change1m")),
            # Equal-weight 3M move of the whole basket (was gold+oil's ONE-DAY change).
            "commodityInflationIndex": broad_commodity_momentum(
                [r for g in groups.values() for r in g]),
        },
        "lastUpdated": datetime.now().isoformat()
    }


async def get_prices_data() -> Dict[str, Any]:
    """Get current prices for key assets from Yahoo Finance."""
    logger.info("Fetching prices data")

    result = await _yahoo_provider.fetch_latest_async(['SPX', 'NDX', 'VIX', 'DXY'])
    yf_tickers = {'SPX': '^GSPC', 'NDX': '^NDX', 'VIX': '^VIX', 'DXY': 'DX-Y.NYB'}

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
            price = None            # unavailable — not a made-up 5800
        change = _pct_change(closes, 1) if closes else None
        prices[symbol] = {
            "price": round(price, 2) if price is not None else None,
            "change_pct": change,   # None when unknown (0.0 claimed "unchanged")
        }

    return {
        **prices,
        "lastUpdated": datetime.now().isoformat()
    }
