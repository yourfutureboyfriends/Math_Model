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
    inflation: Optional[float],
    sector_stats: Optional[Dict[str, Dict[str, float]]] = None,
    confidence: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Sector allocation: regime playbook weights (a policy table) + observed relative strength.

    `sector_stats` maps playbook sector -> {relativeReturn, percentile, z} of the sector
    proxy's 3m return vs SPY (see dashboard_sections.build_sector_stats). Each sector's
    `score` is that rank mapped to -1..+1 (2·percentile − 1) and `z_score` the actual
    z-score; both are None without price data. `confidence` is the regime classifier's
    confidence, passed through (None if not supplied) — not derived here.
    `growth` / `inflation` are accepted for signature compatibility.
    """
    regime = regime.lower() if regime else "goldilocks"
    stats = sector_stats or {}

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

    sectors = []
    for sector, weight in weights.items():
        # Playbook stance for the regime (policy, not data)
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

        conviction = "High" if weight > 0.20 else "Medium" if weight > 0.10 else "Low"

        st = stats.get(sector)
        score = round(2 * st["percentile"] - 1, 2) if st else None
        z = round(st["z"], 2) if st and st.get("z") is not None else None
        # The playbook tilt is policy; relative strength is data. A tilt the data contradicts
        # (e.g. "Overweight Financials" while XLF trails the S&P by 7% at a z of -0.9) is
        # reported as Neutral, with the playbook stance kept alongside for transparency.
        playbook = signal
        if z is not None:
            if playbook == "Overweight" and z < -0.5:
                signal = "Neutral"
            elif playbook == "Underweight" and z > 0.5:
                signal = "Neutral"
        rationale = f"{regime} playbook: {playbook.lower()}, weight {weight:.0%}"
        if st:
            rationale += (f"; {st.get('etf', sector)} 3m vs SPY {st['relativeReturn']:+.1%} "
                          f"({st['percentile']:.0%} of past year)")
        if signal != playbook:
            rationale += " — relative strength does not confirm the playbook tilt"
        sectors.append({
            "name": sector,
            "score": score,
            "z_score": z,
            "allocation": round(weight, 2),
            "rationale": rationale,
            "signal": signal,
            "playbookStance": playbook,
            "conviction": conviction,
        })

    scored = [x["score"] for x in sectors if x["score"] is not None]
    return {
        "sectors": sectors,
        "regime": regime,
        "confidence": round(confidence, 2) if confidence is not None else None,
        "totalScore": round(sum(scored), 2) if scored else None,
    }
