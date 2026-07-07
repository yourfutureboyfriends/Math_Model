"""Market data handler with real data from Yahoo Finance."""
from typing import Dict, Any
from datetime import datetime
import logging

from api.providers import YahooFinanceProvider
from api.providers.fred_provider import FREDProvider

logger = logging.getLogger(__name__)
_yahoo_provider = YahooFinanceProvider()
_fred_provider = FREDProvider()


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

    # Calculate 12-month-ahead recession probability using the NY Fed
    # Estrella-Mishkin probit on the 3m10y spread expressed in PERCENTAGE POINTS.
    #   prob = Phi(-0.6045 + (-0.7374 * spread_pct))
    # At spread = -0.66 pp -> ~45%; at a normal +positive spread -> low single digits.
    from scipy.stats import norm
    spread_3m10y_pp = spread_3m10y / 100.0  # spread_3m10y is in bps; model needs pp
    assert -6.0 < spread_3m10y_pp < 6.0, (
        f"3m10y spread {spread_3m10y_pp} pp out of range — likely a unit error (bps vs pp)"
    )
    recession_prob = float(norm.cdf(-0.6045 + (-0.7374 * spread_3m10y_pp)))
    recession_prob = max(0.0, min(1.0, recession_prob))

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
        "creditSpreads": [
            {"name": "Investment Grade", "spreadBps": 85, "signal": "tight"},
            {"name": "High Yield", "spreadBps": 320, "signal": "normal"},
            {"name": "Emerging Markets", "spreadBps": 280, "signal": "normal"}
        ],
        "realYieldSignal": "positive" if real_yield_10y > 1.0 else "negative" if real_yield_10y < 0 else "neutral",
        # Legacy fields for backward compatibility
        "tenYear": round(ten_yr, 2),
        "twoYear": round(two_yr, 2),
        "fedFunds": fed_funds,
        "yieldCurve": shape,
        "lastUpdated": datetime.now().isoformat()
    }


async def get_fx_data() -> Dict[str, Any]:
    """Get FX data from Yahoo Finance."""
    logger.info("Fetching FX data")

    result = await _yahoo_provider.fetch_latest_async(['DXY', 'EURUSD', 'GBPUSD', 'USDJPY'])

    dxy = result.data.get('DXY', {}).price if result.success and result.data and 'DXY' in result.data else None
    eurusd = result.data.get('EURUSD', {}).price if result.success and result.data and 'EURUSD' in result.data else None

    return {
        "dxy": round(dxy, 2) if dxy else 104.0,
        "eurusd": round(eurusd, 4) if eurusd else 1.08,
        "gbpusd": 1.265,  # Would need real data
        "usdjpy": 148.2,  # Would need real data
        "lastUpdated": datetime.now().isoformat()
    }


async def get_commodities_data() -> Dict[str, Any]:
    """Get commodities data with calculated macro signals."""
    logger.info("Fetching commodities data")

    # Fetch real prices from Yahoo Finance
    result = await _yahoo_provider.fetch_latest_async(['GLD', 'WTI'])

    gold_price = None
    oil_price = None
    if result.success and result.data:
        gold_price = result.data.get('GLD', {}).price if 'GLD' in result.data else None
        oil_price = result.data.get('WTI', {}).price if 'WTI' in result.data else None

    # Use fallback values if fetch failed
    gold_price = gold_price or 2050.0
    oil_price = oil_price or 75.5

    # Calculate synthetic changes (would need historical data in production)
    gold_change_1d = 0.5
    oil_change_1d = -0.8

    # Calculate copper/gold ratio signal (synthetic)
    copper_price = 3.85
    copper_gold_ratio = copper_price / (gold_price / 1000)
    ratio_signal = "RISK-ON" if copper_gold_ratio > 1.8 else "RISK-OFF"

    # Calculate oil trend
    oil_trend = "RISING" if oil_change_1d > 0 else "FALLING"
    oil_interpretation = "Supply concerns" if oil_change_1d > 0 else "Demand moderation"

    # Calculate inflation index
    inflation_score = (gold_change_1d + oil_change_1d) / 2
    inflation_signal = "RISING" if inflation_score > 0 else "FALLING"

    return {
        "commodities": {
            "energy": [
                {
                    "symbol": "CL",
                    "name": "WTI Crude",
                    "spot": round(oil_price, 2),
                    "change1d": oil_change_1d,
                    "change1m": 2.5,  # Synthetic
                    "change3m": -5.2,  # Synthetic
                    "week52Percentile": 45  # Synthetic
                },
                {
                    "symbol": "NG",
                    "name": "Natural Gas",
                    "spot": 2.85,  # Would need real data
                    "change1d": 1.2,
                    "change1m": -3.5,
                    "change3m": 8.2,
                    "week52Percentile": 35
                }
            ],
            "metals": [
                {
                    "symbol": "GC",
                    "name": "Gold",
                    "spot": round(gold_price, 2),
                    "change1d": gold_change_1d,
                    "change1m": 3.2,
                    "change3m": 8.5,
                    "week52Percentile": 78
                },
                {
                    "symbol": "HG",
                    "name": "Copper",
                    "spot": copper_price,
                    "change1d": 0.3,
                    "change1m": 1.8,
                    "change3m": 4.2,
                    "week52Percentile": 62
                },
                {
                    "symbol": "SI",
                    "name": "Silver",
                    "spot": 24.5,
                    "change1d": 0.8,
                    "change1m": 4.2,
                    "change3m": 12.5,
                    "week52Percentile": 68
                }
            ],
            "agriculture": [
                {
                    "symbol": "ZC",
                    "name": "Corn",
                    "spot": 4.45,
                    "change1d": -0.5,
                    "change1m": -2.8,
                    "change3m": -8.5,
                    "week52Percentile": 35
                },
                {
                    "symbol": "ZS",
                    "name": "Soybeans",
                    "spot": 11.85,
                    "change1d": 0.3,
                    "change1m": -1.5,
                    "change3m": -6.2,
                    "week52Percentile": 42
                },
                {
                    "symbol": "ZW",
                    "name": "Wheat",
                    "spot": 5.95,
                    "change1d": 0.8,
                    "change1m": 2.2,
                    "change3m": -4.5,
                    "week52Percentile": 48
                }
            ]
        },
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

    prices = {}
    if result.success and result.data:
        for symbol in ['SPX', 'NDX', 'VIX', 'DXY']:
            if symbol in result.data:
                prices[symbol] = {
                    "price": round(result.data[symbol].price, 2),
                    "change_pct": 0.0  # Would need historical data
                }

    # Use fallbacks if needed
    if 'SPX' not in prices:
        prices['SPX'] = {"price": 5800.0, "change_pct": 0.5}
    if 'NDX' not in prices:
        prices['NDX'] = {"price": 18500.0, "change_pct": 0.8}
    if 'DXY' not in prices:
        prices['DXY'] = {"price": 104.0, "change_pct": -0.2}
    if 'VIX' not in prices:
        prices['VIX'] = {"price": 18.0, "change_pct": -5.0}

    return {
        **prices,
        "lastUpdated": datetime.now().isoformat()
    }
