"""
Alternative-data signal math — pure, tested (Phase 7).

Computes edge signals from data available via yfinance/FRED:
- VIX term structure (contango/backwardation) — options-implied positioning stress.
- Cross-market correlation breakdown — rolling correlations vs their own history, flagged
  when they move beyond normal bounds (an early regime-change tell).
- Credit-spread stress — z-score / momentum of high-yield and IG OAS.
No I/O — series are passed in.
"""
from __future__ import annotations

from typing import Dict, Sequence, Optional
import numpy as np


def zscore(value: float, series: Sequence[float]) -> Optional[float]:
    """Standard score of `value` vs the distribution of `series`. None if degenerate."""
    s = np.asarray(series, dtype=float)
    s = s[~np.isnan(s)]
    if s.size < 5 or s.std(ddof=1) == 0:
        return None
    return round((value - s.mean()) / s.std(ddof=1), 2)


def percentile_rank(value: float, series: Sequence[float]) -> Optional[float]:
    """Percentile (0-100) of `value` within `series`."""
    s = np.asarray(series, dtype=float)
    s = s[~np.isnan(s)]
    if s.size < 5:
        return None
    return round(float((s < value).mean() * 100.0), 1)


def term_structure(vix9d: Optional[float], vix: Optional[float],
                   vix3m: Optional[float], vix6m: Optional[float]) -> Dict:
    """VIX term structure and its slope.

    slope = vix3m / vix - 1. In **contango** (slope > 0, longer-dated higher) markets are
    calm; **backwardation** (slope < 0, spot elevated) signals acute near-term stress.
    """
    pts = {"9d": vix9d, "spot": vix, "3m": vix3m, "6m": vix6m}
    slope = None
    state = "unknown"
    if vix and vix3m and vix > 0:
        slope = round(vix3m / vix - 1.0, 4)
        state = "backwardation" if slope < -0.02 else "contango" if slope > 0.02 else "flat"
    return {"points": pts, "slope_3m_spot": slope, "state": state,
            "interpretation": (
                "Near-term stress: spot vol above 3-month (backwardation)." if state == "backwardation"
                else "Calm: 3-month vol above spot (contango)." if state == "contango"
                else "Flat term structure." if state == "flat" else "Insufficient data.")}


def rolling_correlation(a_ret: Sequence[float], b_ret: Sequence[float], window: int = 63) -> np.ndarray:
    """Trailing `window`-day correlation of two return series (aligned)."""
    a = np.asarray(a_ret, dtype=float)
    b = np.asarray(b_ret, dtype=float)
    n = min(a.size, b.size)
    a, b = a[-n:], b[-n:]
    out = np.full(n, np.nan)
    for t in range(window - 1, n):
        wa, wb = a[t - window + 1: t + 1], b[t - window + 1: t + 1]
        if wa.std() > 0 and wb.std() > 0:
            out[t] = np.corrcoef(wa, wb)[0, 1]
    return out


def correlation_breakdown(a_ret: Sequence[float], b_ret: Sequence[float],
                          window: int = 63, breach_z: float = 2.0) -> Dict:
    """Current rolling correlation vs its own trailing distribution.

    Flags a breakdown when the latest correlation is more than `breach_z` std from its
    history — often an early regime-change signal (e.g. SPY-TLT flipping positive).
    """
    corr = rolling_correlation(a_ret, b_ret, window)
    valid = corr[~np.isnan(corr)]
    if valid.size < 20:
        return {"available": False, "reason": "insufficient overlapping history"}
    current = float(valid[-1])
    hist = valid[:-1]
    z = zscore(current, hist)
    return {
        "available": True,
        "current_correlation": round(current, 3),
        "mean_correlation": round(float(hist.mean()), 3),
        "zscore": z,
        "breakdown": bool(z is not None and abs(z) >= breach_z),
        "window_days": window,
    }
