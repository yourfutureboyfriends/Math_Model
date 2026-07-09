"""
Trade-idea generation — pure, tested (Phase 6, gap-closure).

This is NOT a black-box signal. It is a transparent rules engine that maps the platform's
OWN documented regime playbook (`REGIME_CHARACTERISTICS`: equity / duration / commodity /
value / risk-appetite biases per macro regime) onto the tradable factor proxies, then
compares the *desired* factor tilt against the portfolio's *actual* dollar factor exposure.

An idea is only emitted when the book is misaligned with the regime playbook:
  - opposite sign   → the book leans the wrong way            (highest priority)
  - flat but wanted → the regime calls for a tilt we don't have (initiate)

Every idea carries the regime, the factor, the proxy ETF, a direction and a plain-English
rationale, so a PM can see exactly *why* it was proposed. No fabricated conviction scores.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from api.calculations.regime import REGIME_CHARACTERISTICS
from api.calculations.factor_model import FACTOR_PROXIES, FACTOR_LABELS


def desired_tilts(regime_key: str) -> Dict[str, int]:
    """Translate a regime's biases into a desired sign (+1 long / -1 short / 0 neutral)
    for each tradable factor. Returns {} for an unknown regime."""
    rc = REGIME_CHARACTERISTICS.get((regime_key or "").strip().lower())
    if rc is None:
        return {}
    bias3 = {"overweight": 1, "neutral": 0, "underweight": -1,
             "long": 1, "short": -1, "high": 1, "medium": 0, "low": -1}
    tilts: Dict[str, int] = {
        "equity": bias3.get(rc.equity_bias, 0),
        "rates": bias3.get(rc.duration_bias, 0),
        "commodity": bias3.get(rc.commodity_bias, 0),
        # Risk appetite drives credit (long HY when risk-on) and volatility (own vol as a
        # hedge when risk-off, i.e. desired +1 on the VIX factor in low-appetite regimes).
        "credit": bias3.get(rc.risk_appetite, 0),
        "volatility": -bias3.get(rc.risk_appetite, 0),
    }
    # Value vs growth rotation.
    if rc.value_bias == "value":
        tilts["value"], tilts["growth"] = 1, -1
    elif rc.value_bias == "growth":
        tilts["value"], tilts["growth"] = -1, 1
    # Momentum rotation signal.
    if rc.rotation_signal == "momentum":
        tilts["momentum"] = 1
    return {f: s for f, s in tilts.items() if s != 0}


def generate_ideas(dollar_exposures: Dict[str, float], regime_key: str,
                   gross_exposure: float = 0.0, flat_threshold_frac: float = 0.02) -> List[Dict]:
    """Propose trades that move the book toward the regime playbook.

    dollar_exposures : {factor: $ P&L per 1.0 factor move} — the live book's exposure.
    gross_exposure   : book gross, used to decide when an exposure is effectively "flat".
    Returns a list of ideas ranked by misalignment severity (most misaligned first).
    """
    tilts = desired_tilts(regime_key)
    if not tilts:
        return []
    flat = max(abs(gross_exposure) * flat_threshold_frac, 1.0)
    rc = REGIME_CHARACTERISTICS.get(regime_key.strip().lower())
    regime_name = rc.name if rc else regime_key

    ideas: List[Dict] = []
    for factor, want in tilts.items():
        cur = float(dollar_exposures.get(factor, 0.0))
        proxy = FACTOR_PROXIES.get(factor, factor)
        label = FACTOR_LABELS.get(factor, factor)
        direction = "LONG" if want > 0 else "SHORT"
        want_word = "increase" if want > 0 else "reduce"

        if want > 0 and cur < -flat or want < 0 and cur > flat:
            kind, severity = "REALIGN", abs(cur)          # leaning the wrong way
            action = f"Book is {'short' if cur < 0 else 'long'} {label} (${cur:,.0f}); regime favours the opposite."
        elif abs(cur) <= flat:
            kind, severity = "INITIATE", flat              # flat but the regime wants a tilt
            action = f"No {label} exposure; {regime_name} regime calls for a {direction.lower()} tilt."
        else:
            continue                                       # already aligned — nothing to do

        ideas.append({
            "factor": factor, "label": label, "proxy": proxy,
            "direction": direction, "kind": kind,
            "current_exposure": round(cur, 2),
            "rationale": f"{regime_name}: {want_word} {label} exposure. {action}",
            "severity": round(severity, 2),
        })

    ideas.sort(key=lambda x: x["severity"], reverse=True)
    for i, idea in enumerate(ideas, 1):
        idea["rank"] = i
    return ideas
