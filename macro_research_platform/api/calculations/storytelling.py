"""
Signal storytelling — explain WHY each composite score is where it is (Phase 2).

Each function reuses the same math as the dashboard signal (so the score matches), then
decomposes it into named input contributions, identifies the largest driver, and emits a
one-line, plain-English `explanation_text`. Pure — inputs are already-normalized values
(percent for yields, index level for SPX/DXY, points for VIX); no I/O.
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


def explain_growth(spx_level: Optional[float], spx_history: Optional[List[float]]) -> Dict:
    score, trend, _ = calculate_growth_signal(spx_level, spx_history or [])
    lvl = spx_level if spx_level and spx_level > 0 else 5800.0
    hist = spx_history or [lvl]
    recent = (lvl - hist[-1]) / hist[-1] if hist and hist[-1] else 0.0
    trailing = (lvl - hist[0]) / hist[0] if hist and hist[0] else 0.0
    contributions = [
        _contrib("SPX recent return", recent * 100, recent, "%"),
        _contrib("SPX trailing return", trailing * 100, trailing, "%"),
    ]
    text = (f"Growth {trend}: S&P 500 {recent * 100:+.1f}% recent momentum "
            f"(vs {trailing * 100:+.1f}% trailing) → score {score:.2f}.")
    return _pack("Growth", score, trend, text, contributions)


def explain_inflation(ten_yr: Optional[float], two_yr: Optional[float]) -> Dict:
    score, trend, _ = calculate_inflation_signal(ten_yr, two_yr)
    ten = ten_yr if ten_yr and ten_yr > 0 else 4.5
    two = two_yr if two_yr and two_yr > 0 else 4.2
    spread = ten - two
    contributions = [
        _contrib("10Y yield", ten, spread),          # steepening (10Y up) lifts the signal
        _contrib("2Y yield", two, -spread if spread else 0.0),
    ]
    text = (f"Inflation signal {trend}: 10Y−2Y curve {spread * 100:+.0f}bps "
            f"({ten:.2f}% − {two:.2f}%) → score {score:.2f}.")
    return _pack("Inflation", score, trend, text, contributions)


def explain_liquidity(dxy: Optional[float], ten_yr: Optional[float], fed_rate: Optional[float]) -> Dict:
    score, trend, _ = calculate_liquidity_signal(dxy, ten_yr, fed_rate)
    d = dxy if dxy and dxy > 0 else 104.0
    ten = ten_yr if ten_yr and ten_yr > 0 else 4.5
    fed = fed_rate if fed_rate and fed_rate > 0 else 5.0
    dxy_component = (1.0 - _clamp((d - 90) / 20.0)) * 0.6      # weight 0.6
    spread = fed - ten
    spread_component = (1.0 - _clamp((spread + 1) / 3.0)) * 0.4  # weight 0.4
    contributions = [
        _contrib("US Dollar (DXY)", d, dxy_component),
        _contrib("Fed−10Y spread", spread, spread_component, "%"),
    ]
    driver = "US Dollar" if dxy_component >= spread_component else "Fed−10Y spread"
    text = (f"Liquidity {trend}: driven by {driver} — DXY {d:.1f}, Fed−10Y {spread:+.2f}% "
            f"→ score {score:.2f}.")
    return _pack("Liquidity", score, trend, text, contributions)


def explain_risk(vix: Optional[float]) -> Dict:
    score, trend, _ = calculate_risk_signal(vix)
    v = vix if vix and vix > 0 else 18.0
    contributions = [_contrib("VIX", v, score)]
    text = f"Risk appetite {trend}: VIX at {v:.1f} → score {score:.2f}."
    return _pack("Risk", score, trend, text, contributions)
