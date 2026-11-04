"""
Capital-market-assumption (CMA) building blocks — pure, tested.

Single source of truth for the long-term asset-class return forecasts (dashboard
gmoForecasts, /api/forecasts/longterm, /api/business/expected-returns). Every building
block is an observed input supplied by the caller — no fixed premia or volatility tables:

  equity expected return = earnings yield (100 / trailing P/E of the asset's ETF)
                           + 10Y breakeven inflation            (real yield + inflation)
  bond expected return   = 10Y Treasury yield
  volatility             = realized annualized volatility of the asset's ETF
  Sharpe                 = (expected return − cash yield) / volatility

An asset whose inputs are missing is left out rather than filled with an assumption.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Mapping, Optional

# (asset class, proxy ETF, kind)
ASSETS = [
    ("US Large Cap", "SPY", "equity"),
    ("US Small Cap", "IWM", "equity"),
    ("International Developed", "EFA", "equity"),
    ("Emerging Markets", "EEM", "equity"),
    ("US Bonds", "AGG", "bond"),
]


def longterm_forecasts(ten_yr: Optional[float], as_of: Optional[datetime] = None,
                       risk_free: Optional[float] = None, breakeven: Optional[float] = None,
                       earnings_yields: Optional[Mapping[str, float]] = None,
                       vols: Optional[Mapping[str, float]] = None) -> Dict:
    """Build the long-term CMA payload from observed inputs (all in percent).

    ten_yr: 10Y Treasury yield. risk_free: cash (3M T-bill) yield. breakeven: 10Y breakeven
    inflation. earnings_yields: {ETF: 100 / trailing P/E}. vols: {ETF: realized annualized
    vol}. Returns {"available": False, ...} when nothing can be computed.
    """
    now = as_of or datetime.now()
    ey, vol = dict(earnings_yields or {}), dict(vols or {})
    forecasts = []
    for name, etf, kind in ASSETS:
        if kind == "bond":
            if ten_yr is None:
                continue
            er, comps = ten_yr, {"yield": round(ten_yr, 2)}
        else:
            if etf not in ey or breakeven is None:
                continue
            er = ey[etf] + breakeven
            comps = {"earnings_yield": round(ey[etf], 2), "inflation": round(breakeven, 2)}
        v = vol.get(etf)
        sharpe = round((er - risk_free) / v, 2) if (v and risk_free is not None) else None
        forecasts.append({
            "assetClass": name,
            "proxy": etf,
            "expectedReturn": round(er, 1),
            "volatility": round(v, 1) if v is not None else None,
            "sharpeRatio": sharpe,
            "confidence": None,       # no estimate of forecast uncertainty is modelled
            "components": comps,
        })

    if not forecasts:
        return {"available": False, "forecasts": [],
                "reason": "10Y yield, breakeven inflation and ETF valuations unavailable",
                "methodology": "Building-block CMA (unavailable: no inputs)",
                "asOfDate": now.isoformat(),
                "disclaimer": "Past performance does not guarantee future results.",
                "lastUpdated": now.isoformat()}

    rf_txt = f"; Sharpe vs {risk_free:.2f}% cash" if risk_free is not None else ""
    return {
        "available": True,
        "forecasts": forecasts,
        "riskFreeRate": risk_free,
        "breakeven": breakeven,
        "methodology": ("Building-block CMA: equity = earnings yield (1/trailing P/E of the ETF) + "
                        "10Y breakeven inflation; bonds = 10Y Treasury yield; volatility = realized "
                        f"2y daily vol of the ETF{rf_txt}. Not GMO's valuation model."),
        "asOfDate": now.isoformat(),
        "disclaimer": "Past performance does not guarantee future results.",
        "lastUpdated": now.isoformat(),
    }
