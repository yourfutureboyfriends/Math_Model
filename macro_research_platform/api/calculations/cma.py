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

# (assetClass, expected-return offset vs US Large Cap equity or None for the bond leg, volatility, confidence)
_ASSETS = [
    ("US Large Cap", 0.0, 15.0, 0.6),
    ("US Small Cap", 0.5, 18.0, 0.5),
    ("International Developed", 1.0, 16.0, 0.5),
    ("Emerging Markets", 2.5, 22.0, 0.4),
    ("US Bonds", None, 5.0, 0.8),          # None offset => this is the bond leg (= 10Y yield)
]


def longterm_forecasts(ten_yr: Optional[float], as_of: Optional[datetime] = None,
                       risk_free: Optional[float] = None) -> Dict:
    """Build the long-term CMA forecast payload from the 10Y yield.

    `ten_yr` is the 10Y Treasury yield in percent (e.g. 4.6). `risk_free` is the cash
    yield in percent (e.g. 3M T-bill); Sharpe = (expected return − risk_free) / vol, and is
    None when no risk-free rate is supplied (total return / vol is not a Sharpe ratio).
    Returns {"available": False, ...} when the 10Y yield is missing — no default yield.
    """
    now = as_of or datetime.now()
    if ten_yr is None:
        return {"available": False, "forecasts": [],
                "reason": "10Y Treasury yield unavailable",
                "methodology": "Building-block CMA (unavailable: no 10Y yield)",
                "asOfDate": now.isoformat(),
                "disclaimer": "Past performance does not guarantee future results.",
                "lastUpdated": now.isoformat()}
    bond_return = ten_yr
    equity_return = bond_return + EQUITY_ERP

    forecasts = []
    for name, offset, vol, conf in _ASSETS:
        er = bond_return if offset is None else round(equity_return + offset, 1)
        sharpe = round((er - risk_free) / vol, 2) if (vol and risk_free is not None) else None
        forecasts.append({
            "assetClass": name,
            "expectedReturn": round(er, 1),
            "volatility": vol,
            "sharpeRatio": sharpe,
            "confidence": conf,
        })

    rf_txt = f"; Sharpe vs {risk_free:.2f}% cash" if risk_free is not None else ""
    return {
        "available": True,
        "forecasts": forecasts,
        "riskFreeRate": risk_free,
        "methodology": f"Building-block CMA: bond = 10Y yield ({bond_return:.1f}%), "
                       f"equity = 10Y + {EQUITY_ERP:.0f}% ERP (GMO-style, not GMO's valuation model){rf_txt}",
        "asOfDate": now.isoformat(),
        "disclaimer": "Past performance does not guarantee future results.",
        "lastUpdated": now.isoformat(),
    }
