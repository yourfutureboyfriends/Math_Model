"""
Signal storytelling — explain WHY each composite score is where it is (Phase 2).

Each function reuses the same math as the dashboard signal (so the score matches), then
decomposes it into named input contributions, identifies the largest driver, and emits a
one-line, plain-English `explanation_text`. Pure — inputs are already-normalized values
(percent for yields/inflation, index level for SPX/DXY, points for VIX); no I/O.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from api.calculations.signals import (
    calculate_growth_signal, calculate_inflation_signal,
    calculate_liquidity_signal, calculate_risk_signal,
)


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(x, hi))


def _contrib(name: str, value: float, contribution: float, unit: str = "") -> Dict:
    return {"input": name, "value": round(value, 3), "contribution": round(contribution, 3),
            "unit": unit, "direction": "positive" if contribution >= 0 else "negative"}


def _pack(signal: str, score: float, trend: str, text: str, contributions: List[Dict]) -> Dict:
    ranked = sorted(contributions, key=lambda c: abs(c["contribution"]), reverse=True)
    return {"signal": signal, "score": round(score, 2), "trend": trend,
            "explanation_text": text, "contributions": ranked,
            "driver": ranked[0]["input"] if ranked else None}


def _unavailable(signal: str, reason: str) -> Dict:
    return {"signal": signal, "score": None, "trend": "unavailable",
            "explanation_text": f"{signal} unavailable: {reason}.",
            "contributions": [], "driver": None}


def explain_growth(spx_level: Optional[float], spx_history: Optional[List[float]]) -> Dict:
    """spx_history: real daily closes, oldest first (excluding spx_level)."""
    score, trend, _ = calculate_growth_signal(spx_level, spx_history or [])
    if score is None:
        return _unavailable("Growth", "needs ~6 months of daily S&P 500 closes")
    closes = list(spx_history or []) + ([spx_level] if spx_level else [])
    last = closes[-1]
    recent = last / closes[-22] - 1.0          # ~1 month
    trailing = last / closes[-127] - 1.0       # ~6 months
    contributions = [
        _contrib("SPX 1M return", recent * 100, recent, "%"),
        _contrib("SPX 6M return", trailing * 100, trailing, "%"),
    ]
    text = (f"Growth {trend}: S&P 500 {recent * 100:+.1f}% over 1M "
            f"(vs {trailing * 100:+.1f}% over 6M) → score {score:.2f}.")
    return _pack("Growth", score, trend, text, contributions)


def explain_inflation(cpi_yoy: Optional[float], breakeven_10y: Optional[float]) -> Dict:
    score, trend, _ = calculate_inflation_signal(cpi_yoy, breakeven_10y)
    if score is None:
        return _unavailable("Inflation", "CPI and 10Y breakeven both missing")
    contributions = []
    if cpi_yoy is not None:
        contributions.append(_contrib("CPI YoY", cpi_yoy, _clamp((cpi_yoy - 1.0) / 4.0) - 0.5, "%"))
    if breakeven_10y is not None:
        contributions.append(_contrib("10Y breakeven", breakeven_10y,
                                      _clamp((breakeven_10y - 1.5) / 1.5) - 0.5, "%"))
    parts = [p for p in (f"CPI {cpi_yoy:.1f}% YoY" if cpi_yoy is not None else None,
                         f"10Y breakeven {breakeven_10y:.2f}%" if breakeven_10y is not None else None) if p]
    text = f"Inflation {trend}: {' and '.join(parts)} → score {score:.2f}."
    return _pack("Inflation", score, trend, text, contributions)


def explain_liquidity(dxy: Optional[float], ten_yr: Optional[float], fed_rate: Optional[float]) -> Dict:
    score, trend, _ = calculate_liquidity_signal(dxy, ten_yr, fed_rate)
    if score is None:
        return _unavailable("Liquidity", "DXY, 10Y yield or Fed funds missing")
    dxy_component = (1.0 - _clamp((dxy - 90) / 20.0)) * 0.6      # weight 0.6
    spread = fed_rate - ten_yr
    spread_component = (1.0 - _clamp((spread + 1) / 3.0)) * 0.4  # weight 0.4
    contributions = [
        _contrib("US Dollar (DXY)", dxy, dxy_component),
        _contrib("Fed−10Y spread", spread, spread_component, "%"),
    ]
    driver = "US Dollar" if dxy_component >= spread_component else "Fed−10Y spread"
    text = (f"Liquidity {trend}: driven by {driver} — DXY {dxy:.1f}, Fed−10Y {spread:+.2f}% "
            f"→ score {score:.2f}.")
    return _pack("Liquidity", score, trend, text, contributions)


def explain_risk(vix: Optional[float]) -> Dict:
    score, trend, _ = calculate_risk_signal(vix)
    if score is None:
        return _unavailable("Risk", "VIX missing")
    contributions = [_contrib("VIX", vix, score)]
    text = f"Risk appetite {trend}: VIX at {vix:.1f} → score {score:.2f}."
    return _pack("Risk", score, trend, text, contributions)
