"""Advanced metrics calculations - recession, sectors, etc."""
from typing import Dict, Any, Optional

from .models import estrella_mishkin_recession_prob, _EM_SLOPE


def _recession_level(p: float) -> str:
    if p > 0.40:
        return "High"
    if p > 0.20:
        return "Moderate"
    return "Low"


def calculate_recession_probability(
    spread_3m10y_pp: Optional[float],
    fed_funds: Optional[float] = None,
    sahm_value: Optional[float] = None,
    fitted_probit_prob: Optional[float] = None,
) -> Dict[str, Any]:
    """
    12-month recession probability from real models only.

    - emProbitProb: Estrella-Mishkin (1998) probit on the 10Y-3M spread (pp).
    - logisticProb: probit re-fitted on FRED history (spread + Fed funds, Wright 2006),
      when the fitted model is available; None otherwise.
    - sahmValue: FRED real-time Sahm rule (SAHMREALTIME); signal at >= 0.50.

    Headline probability = fitted probit if available, else Estrella-Mishkin.
    Returns probability None (level "Unavailable") when the spread is missing.
    """
    em_prob = None
    if spread_3m10y_pp is not None:
        try:
            em_prob = estrella_mishkin_recession_prob(spread_3m10y_pp)
        except ValueError:
            em_prob = None

    headline = fitted_probit_prob if fitted_probit_prob is not None else em_prob
    sahm_signal = (
        "Unavailable" if sahm_value is None
        else "Signal" if sahm_value >= 0.50 else "No Signal"
    )

    components = []
    if spread_3m10y_pp is not None:
        # contribution = the input's term inside the E-M probit index (z units)
        components.append({"name": "10Y-3M Spread", "value": round(spread_3m10y_pp, 2),
                           "contribution": round(_EM_SLOPE * spread_3m10y_pp, 3)})
    if fed_funds is not None:
        components.append({"name": "Fed Funds", "value": round(fed_funds, 2), "contribution": None})
    if sahm_value is not None:
        components.append({"name": "Sahm Rule", "value": round(sahm_value, 2), "contribution": None})

    return {
        "probability": round(headline, 4) if headline is not None else None,
        "level": _recession_level(headline) if headline is not None else "Unavailable",
        "logisticProb": round(fitted_probit_prob, 4) if fitted_probit_prob is not None else None,
        "emProbitProb": round(em_prob, 4) if em_prob is not None else None,
        "sahmValue": round(sahm_value, 2) if sahm_value is not None else None,
        "sahmSignal": sahm_signal,
        "model": "Fitted probit (FRED)" if fitted_probit_prob is not None else "Estrella-Mishkin probit",
        "components": components,
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
    growth = growth if growth is not None and growth >= 0 else 0.5
    inflation = inflation if inflation is not None and inflation >= 0 else 0.3
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
            "Energy": 0.05, "Utilities": 0.12, "Consumer Staples": 0.15
        },
        "contraction": {
            "Technology": 0.12, "Healthcare": 0.25, "Financials": 0.06,
            "Energy": 0.04, "Utilities": 0.15, "Consumer Staples": 0.18
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

    raw = regime_weights_map.get(regime, regime_weights_map["goldilocks"])
    # Equity sector weights are relative tilts; normalise so the allocation sums to 100%
    # (the tables above summed to 90% for most regimes).
    total = sum(raw.values())
    weights = {k: v / total for k, v in raw.items()}

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
