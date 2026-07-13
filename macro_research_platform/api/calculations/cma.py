"""
Capital-market-assumption (CMA) building blocks — pure, tested.

Single source of truth for the long-term asset-class return forecasts that were previously
duplicated verbatim in signal_handler.get_longterm_forecasts_data() and
dashboard_handler (gmoForecasts). A simple building-block model anchored to the real 10Y
yield: bond return = 10Y yield, equity return = 10Y + a fixed equity risk premium, with
per-asset offsets and fixed volatility assumptions.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

EQUITY_ERP = 4.0          # equity risk premium over the 10Y (percentage points)
DEFAULT_10Y = 4.5         # fallback when the live 10Y yield is unavailable

# (assetClass, expected-return offset vs US Large Cap equity or None for the bond leg, volatility, confidence)
_ASSETS = [
    ("US Large Cap", 0.0, 15.0, 0.6),
    ("US Small Cap", 0.5, 18.0, 0.5),
    ("International Developed", 1.0, 16.0, 0.5),
    ("Emerging Markets", 2.5, 22.0, 0.4),
    ("US Bonds", None, 5.0, 0.8),          # None offset => this is the bond leg (= 10Y yield)
]


def longterm_forecasts(ten_yr: Optional[float], as_of: Optional[datetime] = None) -> Dict:
    """Build the long-term CMA forecast payload from the 10Y yield.

    `ten_yr` is the 10Y Treasury yield in percent (e.g. 4.6); falls back to DEFAULT_10Y.
    Returns the same shape both callers previously produced (incl. `lastUpdated`).
    """
    now = as_of or datetime.now()
    bond_return = ten_yr if ten_yr else DEFAULT_10Y
    equity_return = bond_return + EQUITY_ERP

    forecasts = []
    for name, offset, vol, conf in _ASSETS:
        er = bond_return if offset is None else round(equity_return + offset, 1)
        forecasts.append({
            "assetClass": name,
            "expectedReturn": round(er, 1),
            "volatility": vol,
            "sharpeRatio": round(er / vol, 2) if vol else 0.0,
            "confidence": conf,
        })

    return {
        "forecasts": forecasts,
        "methodology": f"Building-block CMA: bond = 10Y yield ({bond_return:.1f}%), "
                       f"equity = 10Y + {EQUITY_ERP:.0f}% ERP (GMO-style, not GMO's valuation model)",
        "asOfDate": now.isoformat(),
        "disclaimer": "Past performance does not guarantee future results.",
        "lastUpdated": now.isoformat(),
    }
