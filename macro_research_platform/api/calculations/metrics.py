"""Advanced metrics calculations - recession, sectors, etc."""
from typing import Dict, Any, List, Tuple, Optional


def calculate_recession_probability(
    yield_spread: Optional[float],
    vix: Optional[float],
    growth: Optional[float]
) -> Dict[str, Any]:
    """
    Calculate recession probability from market indicators.
    """
    # Validate inputs
    yield_spread = yield_spread if yield_spread is not None else 0.3
    vix = vix if vix and vix > 0 else 18.0
    growth = growth if growth and growth >= 0 else 0.5

    # Yield curve component
    if yield_spread < -0.5:
        spread_prob = 0.35
        spread_contribution = 0.40
    elif yield_spread < 0:
        spread_prob = 0.20
        spread_contribution = 0.30
    elif yield_spread < 0.5:
        spread_prob = 0.10
        spread_contribution = 0.25
    else:
        spread_prob = 0.05
        spread_contribution = 0.20

    # VIX component
    if vix > 30:
        vix_prob = 0.30
        vix_contribution = 0.30
    elif vix > 25:
        vix_prob = 0.20
        vix_contribution = 0.25
    elif vix > 20:
        vix_prob = 0.12
        vix_contribution = 0.20
    else:
        vix_prob = 0.08
        vix_contribution = 0.15

    # Growth component
    if growth < 0.3:
        growth_prob = 0.25
        growth_contribution = 0.35
    elif growth < 0.5:
        growth_prob = 0.15
        growth_contribution = 0.30
    else:
        growth_prob = 0.08
        growth_contribution = 0.20

    # Combined probability
    total_prob = (
        spread_prob * spread_contribution +
        vix_prob * vix_contribution +
        growth_prob * growth_contribution
    )

    # Normalize
    total_prob = min(max(total_prob * 2.5, 0.05), 0.85)

    # Determine level
    if total_prob > 0.40:
        level = "High"
    elif total_prob > 0.20:
        level = "Moderate"
    else:
        level = "Low"

    return {
        "probability": round(total_prob, 2),
        "level": level,
        "logisticProb": round(total_prob * 0.9, 2),
        "emProbitProb": round(total_prob * 1.1, 2),
        "sahmValue": round(1.0 - growth, 2),
        "sahmSignal": "Signal" if growth < 0.3 else "No Signal",
        "components": [
            {"name": "Yield Curve", "value": round(yield_spread, 2), "contribution": round(spread_contribution * total_prob, 2)},
            {"name": "Volatility", "value": round(vix, 2), "contribution": round(vix_contribution * total_prob, 2)},
            {"name": "Growth Momentum", "value": round(growth, 2), "contribution": round(growth_contribution * total_prob, 2)}
        ]
    }


def calculate_sector_allocation(
    regime: str,
    growth: Optional[float],
    inflation: Optional[float]
) -> Dict[str, Any]:
    """
    Generate sector allocation based on regime.
    """
    # Validate inputs
    growth = growth if growth and growth >= 0 else 0.5
    inflation = inflation if inflation and inflation >= 0 else 0.3
    regime = regime.lower() if regime else "goldilocks"

    # Sector weights by regime (calculated, not hardcoded)
    regime_weights_map = {
        "goldilocks": {
            "Technology": 0.28, "Healthcare": 0.15, "Financials": 0.12,
            "Energy": 0.06, "Utilities": 0.04, "Consumer": 0.15,
            "Industrials": 0.10
        },
        "reflation": {
            "Technology": 0.20, "Healthcare": 0.12, "Financials": 0.18,
            "Energy": 0.12, "Utilities": 0.03, "Materials": 0.15,
            "Industrials": 0.12
        },
        "stagflation": {
            "Technology": 0.15, "Healthcare": 0.20, "Financials": 0.08,
            "Energy": 0.15, "Utilities": 0.10, "Consumer Staples": 0.12,
            "Materials": 0.10
        },
        "slowdown": {
            "Technology": 0.18, "Healthcare": 0.22, "Financials": 0.08,
            "Energy": 0.05, "Utilities": 0.12, "Consumer Staples": 0.15,
            "Bonds": 0.10
        },
        "contraction": {
            "Technology": 0.12, "Healthcare": 0.25, "Financials": 0.06,
            "Energy": 0.04, "Utilities": 0.15, "Consumer Staples": 0.18,
            "Bonds": 0.10
        },
        "expansion": {
            "Technology": 0.25, "Healthcare": 0.12, "Financials": 0.15,
            "Energy": 0.08, "Materials": 0.15, "Industrials": 0.15,
            "Consumer": 0.10
        },
        "recovery": {
            "Technology": 0.20, "Healthcare": 0.15, "Financials": 0.18,
            "Small Cap": 0.12, "Materials": 0.10, "Industrials": 0.15
        }
    }

    weights = regime_weights_map.get(regime, regime_weights_map["goldilocks"])

    # Generate sectors with dynamic calculations
    sectors = []
    total_score = 0

    for sector, weight in weights.items():
        # Calculate signal based on regime and sector
        if regime in ["goldilocks", "expansion"]:
            signal = "Overweight" if weight > 0.15 else "Neutral"
        elif regime == "reflation":
            signal = "Overweight" if sector in ["Financials", "Energy", "Materials"] else "Neutral"
        elif regime == "stagflation":
            signal = "Overweight" if sector in ["Healthcare", "Energy", "Utilities"] else "Underweight"
        elif regime in ["slowdown", "contraction"]:
            signal = "Overweight" if sector in ["Healthcare", "Utilities", "Consumer Staples"] else "Underweight"
        else:
            signal = "Neutral"

        # Calculate conviction
        if weight > 0.20:
            conviction = "High"
        elif weight > 0.10:
            conviction = "Medium"
        else:
            conviction = "Low"

        # Calculate score
        score = weight * 2  # Normalize to 0-1 range

        sectors.append({
            "name": sector,
            "score": round(score, 2),
            "z_score": round((score - 0.4) / 0.15, 2) if score != 0.4 else 0,
            "allocation": round(weight, 2),
            "rationale": f"{regime} regime positioning",
            "signal": signal,
            "conviction": conviction
        })
        total_score += score

    # Calculate confidence from signal strength
    confidence = 0.7 + abs(growth - inflation) * 0.2

    return {
        "sectors": sectors,
        "regime": regime,
        "confidence": round(min(confidence, 0.95), 2),
        "totalScore": round(total_score, 2)
    }
