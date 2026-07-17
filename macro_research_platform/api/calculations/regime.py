"""Regime classification and characteristics - comprehensive, no hardcoding."""
from typing import Dict, Tuple, List
from dataclasses import dataclass


@dataclass
class RegimeCharacteristics:
    """Complete characteristics for each regime type."""
    name: str
    description: str
    equity_bias: str  # overweight, neutral, underweight
    duration_bias: str  # long, neutral, short
    commodity_bias: str
    quality_bias: str
    value_bias: str
    risk_appetite: str  # high, medium, low
    typical_sectors: List[str]
    themes: List[str]
    position_modifier: float  # 0.5 = half size, 1.0 = full, 1.5 = increased
    rotation_signal: str = "neutral"  # momentum, value, quality, neutral


# Comprehensive regime definitions - ALL regimes covered
REGIME_CHARACTERISTICS = {
    "goldilocks": RegimeCharacteristics(
        name="Goldilocks",
        description="Moderate growth, low inflation - ideal for risk assets",
        equity_bias="overweight",
        duration_bias="neutral",
        commodity_bias="neutral",
        quality_bias="neutral",
        value_bias="growth",
        risk_appetite="high",
        typical_sectors=["Technology", "Consumer Discretionary", "Industrials"],
        themes=[
            "Growth supports risk assets",
            "Stable inflation benefits quality",
            "Overweight equities, neutral duration"
        ],
        position_modifier=1.0,
        rotation_signal="momentum"
    ),
    "reflation": RegimeCharacteristics(
        name="Reflation",
        description="Strong growth with rising inflation",
        equity_bias="overweight",
        duration_bias="short",
        commodity_bias="overweight",
        quality_bias="neutral",
        value_bias="value",
        risk_appetite="high",
        typical_sectors=["Materials", "Energy", "Financials", "Industrials"],
        themes=[
            "Cyclicals outperform",
            "Commodity exposure as inflation hedge",
            "Short duration, value over quality"
        ],
        position_modifier=1.1,
        rotation_signal="value"
    ),
    "stagflation": RegimeCharacteristics(
        name="Stagflation",
        description="Slowing growth with high inflation",
        equity_bias="underweight",
        duration_bias="short",
        commodity_bias="overweight",
        quality_bias="quality",
        value_bias="neutral",
        risk_appetite="low",
        typical_sectors=["Healthcare", "Utilities", "Consumer Staples", "Gold"],
        themes=[
            "Defensive positioning required",
            "Commodity/gold as inflation hedge",
            "Quality over cyclicals"
        ],
        position_modifier=0.7,
        rotation_signal="quality"
    ),
    "slowdown": RegimeCharacteristics(
        name="Slowdown",
        description="Decelerating growth with cooling inflation",
        equity_bias="neutral",
        duration_bias="long",
        commodity_bias="underweight",
        quality_bias="quality",
        value_bias="neutral",
        risk_appetite="medium",
        typical_sectors=["Healthcare", "Utilities", "Technology", "Bonds"],
        themes=[
            "Flight to quality",
            "Long duration benefits",
            "Defensive sectors outperform"
        ],
        position_modifier=0.8,
        rotation_signal="quality"
    ),
    "contraction": RegimeCharacteristics(
        name="Contraction",
        description="Tight liquidity with elevated recession risk",
        equity_bias="underweight",
        duration_bias="long",
        commodity_bias="underweight",
        quality_bias="quality",
        value_bias="neutral",
        risk_appetite="low",
        typical_sectors=["Utilities", "Consumer Staples", "Healthcare", "Long Bonds"],
        themes=[
            "Capital preservation mode",
            "Maximum defensive positioning",
            "Underweight risk assets"
        ],
        position_modifier=0.5,
        rotation_signal="quality"
    ),
    "expansion": RegimeCharacteristics(
        name="Expansion",
        description="Strong growth with stable inflation",
        equity_bias="overweight",
        duration_bias="short",
        commodity_bias="neutral",
        quality_bias="neutral",
        value_bias="value",
        risk_appetite="high",
        typical_sectors=["Cyclicals", "Small Cap", "Technology", "Materials"],
        themes=[
            "Full risk-on positioning",
            "Cyclicals lead",
            "Growth and value both work"
        ],
        position_modifier=1.2,
        rotation_signal="momentum"
    ),
    "recovery": RegimeCharacteristics(
        name="Recovery",
        description="Rebounding from recession, policy support",
        equity_bias="overweight",
        duration_bias="neutral",
        commodity_bias="overweight",
        quality_bias="neutral",
        value_bias="value",
        risk_appetite="medium",
        typical_sectors=["Small Cap", "Cyclicals", "Financials", "Materials"],
        themes=[
            "Early cycle positioning",
            "Small cap recovery",
            "Policy tailwinds"
        ],
        position_modifier=1.1,
        rotation_signal="value"
    ),
}


def classify_regime(growth: float, inflation: float, liquidity: float) -> Tuple[str, float, int]:
    """
    Classify macro regime from signal scores.

    Args:
        growth: Growth signal 0-1 (higher = stronger growth)
        inflation: Inflation signal 0-1 (higher = higher inflation)
        liquidity: Liquidity signal 0-1 (higher = looser conditions)

    Returns:
        Tuple of (regime_name, confidence, duration_months)
    """
    # Define regime boundaries
    g_strong = growth > 0.6
    g_weak = growth < 0.4
    i_high = inflation > 0.6
    i_low = inflation < 0.4
    l_tight = liquidity < 0.3
    l_loose = liquidity > 0.6

    # Classify based on signal combinations
    if g_strong and i_low and l_loose:
        regime = "goldilocks"
        confidence = 0.75 + (growth - 0.6) * 0.5 + (liquidity - 0.6) * 0.3
    elif g_strong and i_high:
        regime = "reflation"
        confidence = 0.70 + (growth - 0.6) * 0.4 + (inflation - 0.6) * 0.3
    elif g_weak and i_high:
        regime = "stagflation"
        confidence = 0.70 + max((0.4 - growth), 0) * 0.5 + (inflation - 0.6) * 0.3
    elif g_weak and i_low:
        regime = "slowdown"
        confidence = 0.65 + max((0.4 - growth), 0) * 0.4
    elif l_tight:
        regime = "contraction"
        confidence = 0.70 + max((0.3 - liquidity), 0) * 0.5
    elif g_strong and i_low:
        regime = "expansion"
        confidence = 0.75 + (growth - 0.6) * 0.4
    elif g_weak and l_loose:
        regime = "recovery"
        confidence = 0.70 + (liquidity - 0.6) * 0.4
    else:
        # Mixed signals - use closest match
        if growth > 0.5 and inflation < 0.5:
            regime = "goldilocks"
        elif growth < 0.5 and inflation > 0.5:
            regime = "stagflation"
        elif growth < 0.5:
            regime = "slowdown"
        else:
            regime = "reflation"
        confidence = 0.60

    # Calculate duration based on signal persistence
    duration = int(6 + confidence * 18)  # 6-24 months

    return regime, min(confidence, 0.95), duration


def get_regime_characteristics(regime: str) -> RegimeCharacteristics:
    """Get characteristics for a regime."""
    normalized = regime.lower().strip() if regime else "goldilocks"
    return REGIME_CHARACTERISTICS.get(normalized, REGIME_CHARACTERISTICS["goldilocks"])


def get_all_regimes() -> Dict[str, RegimeCharacteristics]:
    """Get all regime definitions."""
    return REGIME_CHARACTERISTICS.copy()


# ── Regime transition (Phase 6B) ──────────────────────────────────────────────
def empirical_transition_matrix(regimes: List[str]) -> Dict:
    """Count-based P(next | current) from an ordered sequence of regime labels.

    Returns {states, matrix: {from: {to: prob}}, counts, observations, transitions}.
    Pure — the caller supplies the (real, historically-classified) regime series.
    """
    seq = [r for r in regimes if r]
    states = sorted(set(seq))
    counts = {a: {b: 0 for b in states} for a in states}
    for a, b in zip(seq[:-1], seq[1:]):
        counts[a][b] += 1
    matrix: Dict[str, Dict[str, float]] = {}
    for a in states:
        tot = sum(counts[a].values())
        matrix[a] = {b: (round(counts[a][b] / tot, 3) if tot else 0.0) for b in states}
    return {"states": states, "matrix": matrix, "counts": counts,
            "observations": len(seq), "transitions": max(0, len(seq) - 1)}


def forward_outlook(matrix: Dict, current: str) -> Dict:
    """From the transition matrix, the forward (next-period) probabilities for `current`,
    ranked, plus the stay probability and implied expected persistence (1/(1-p_stay))."""
    row = (matrix.get("matrix") or {}).get(current, {})
    ranked = sorted(row.items(), key=lambda kv: kv[1], reverse=True)
    stay = float(row.get(current, 0.0))
    expected = round(1.0 / (1.0 - stay), 1) if 0.0 <= stay < 1.0 else None
    # Most likely change (highest-probability non-stay target)
    change = next(({"to": t, "prob": p} for t, p in ranked if t != current), None)
    return {
        "current": current,
        "ranked": [{"regime": t, "prob": p} for t, p in ranked],
        "stay_prob": round(stay, 3),
        "expected_persistence_periods": expected,
        "most_likely_change": change,
    }
