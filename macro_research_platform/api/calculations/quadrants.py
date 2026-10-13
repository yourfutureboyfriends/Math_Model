"""
Bridgewater Four Quadrants framework — pure, tested (Phase 1).

Bridgewater's All Weather / Pure Alpha process classifies every environment on TWO
independent axes — growth and inflation, each *relative to what the market expected* (a
surprise), not the raw level — producing exactly four quadrants. This module computes a
surprise for each axis (release vs its own trailing trend, a proxy when consensus data isn't
available), classifies the quadrant, provides the per-quadrant asset playbook, and
cross-validates against the app's existing 6-regime label.

Citation: Bridgewater Associates, "The All Weather Story" / Four Quadrants framework.
"""
from __future__ import annotations

from typing import Dict, Optional, Sequence
import numpy as np


def surprise_z(series: Sequence[float], window: int = 12) -> Optional[float]:
    """Surprise = how far the latest observation sits from its own recent trend, in std.
    A proxy for 'actual vs expected' when consensus estimates aren't accessible."""
    s = np.asarray([x for x in series if x is not None], dtype=float)
    s = s[~np.isnan(s)]
    if s.size < 4:
        return None
    ref = s[-window:] if s.size > window else s
    prior = ref[:-1]
    if prior.size < 3 or prior.std(ddof=1) == 0:
        return 0.0
    return round(float((ref[-1] - prior.mean()) / prior.std(ddof=1)), 3)


# quadrant -> favored / unfavored asset classes (All Weather sizing logic)
QUADRANT_PLAYBOOK = {
    "Reflation": {  # growth ↑, inflation ↑
        "label": "Reflation", "growth": "rising", "inflation": "rising",
        "favored": ["Commodities", "Inflation-linked bonds", "EM equity", "Value"],
        "unfavored": ["Nominal bonds", "Growth/long-duration equity"],
        "note": "Rising growth + rising inflation — cyclicals and real assets lead; short duration.",
    },
    "Goldilocks": {  # growth ↑, inflation ↓
        "label": "Goldilocks (Disinflationary Growth)", "growth": "rising", "inflation": "falling",
        "favored": ["Equity (growth & quality)", "Credit", "EM"],
        "unfavored": ["Commodities", "Cash"],
        "note": "Rising growth + falling inflation — the best quadrant for risk assets.",
    },
    "Stagflation": {  # growth ↓, inflation ↑
        "label": "Stagflation", "growth": "falling", "inflation": "rising",
        "favored": ["Commodities", "Gold", "Inflation-linked bonds", "Defensives"],
        "unfavored": ["Equity", "Nominal bonds", "Credit"],
        "note": "Falling growth + rising inflation — hardest quadrant; real assets over financial assets.",
    },
    "Deflation": {  # growth ↓, inflation ↓
        "label": "Deflationary Contraction", "growth": "falling", "inflation": "falling",
        "favored": ["Long-duration nominal bonds", "USD", "Quality/defensive equity"],
        "unfavored": ["Commodities", "Cyclicals", "Credit"],
        "note": "Falling growth + falling inflation — duration and safety; flight to quality.",
    },
}


def classify_quadrant(growth_surprise: float, inflation_surprise: float) -> str:
    g_up = growth_surprise >= 0
    i_up = inflation_surprise >= 0
    if g_up and i_up:
        return "Reflation"
    if g_up and not i_up:
        return "Goldilocks"
    if (not g_up) and i_up:
        return "Stagflation"
    return "Deflation"


# Map the existing 6-regime taxonomy onto the quadrant space for cross-validation.
REGIME_TO_QUADRANT = {
    "goldilocks": "Goldilocks", "expansion": "Goldilocks", "recovery": "Reflation",
    "reflation": "Reflation", "stagflation": "Stagflation", "slowdown": "Deflation",
    "contraction": "Deflation",
}


def quadrant_view(growth_surprise: Optional[float], inflation_surprise: Optional[float],
                  regime_6: Optional[str] = None) -> Dict:
    """Full quadrant classification + playbook + cross-validation vs the 6-regime label."""
    if growth_surprise is None or inflation_surprise is None:
        return {"available": False, "reason": "Insufficient macro history for surprise index."}
    q = classify_quadrant(growth_surprise, inflation_surprise)
    play = QUADRANT_PLAYBOOK[q]
    out = {
        "available": True,
        "quadrant": q,
        "label": play["label"],
        "growth_axis": "rising" if growth_surprise >= 0 else "falling",
        "inflation_axis": "rising" if inflation_surprise >= 0 else "falling",
        "growth_surprise": growth_surprise,
        "inflation_surprise": inflation_surprise,
        "playbook": {k: play[k] for k in ("favored", "unfavored", "note")},
    }
    if regime_6:
        mapped = REGIME_TO_QUADRANT.get(regime_6.strip().lower())
        out["regime_6"] = regime_6
        out["regime_mapped_quadrant"] = mapped
        out["agreement"] = (mapped == q) if mapped else None
        out["cross_validation"] = (
            "aligned" if mapped == q else
            f"DISAGREEMENT: 6-regime '{regime_6}' maps to {mapped}, quadrant model says {q} — "
            "recalibrate one model if this persists." if mapped else "unmapped regime")
    return out
