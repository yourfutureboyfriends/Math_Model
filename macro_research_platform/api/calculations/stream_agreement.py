"""
Bridgewater 3-stream signal agreement — pure, tested (Phase 3).

Bridgewater sizes conviction by the NUMBER of independent, uncorrelated evidence streams that
agree, not the confidence of any single model. This classifies signals into three independent
streams — MACRO DRIVERS, INTERMARKET ACTION, CAPITAL FLOWS — reduces each to a risk-on /
risk-off / neutral direction, and returns an agreement score + a position-sizing multiplier
(more independent agreement → larger size; cross-stream disagreement → explicitly low
conviction, even if one model is individually confident).

Citation: Bridgewater Associates — research spans macro drivers, intermarket action, and
capital flows as three distinct evidence streams that must independently agree.
"""
from __future__ import annotations

from typing import Dict, Optional


def _dir(x: Optional[float], hi: float, lo: float) -> int:
    """Reduce a score to +1 (risk-on) / -1 (risk-off) / 0 (neutral)."""
    if x is None:
        return 0
    if x >= hi:
        return 1
    if x <= lo:
        return -1
    return 0


def macro_stream(growth: float, inflation: float, liquidity: float) -> int:
    """MACRO DRIVERS: growth up + liquidity loose = risk-on; inflation is a headwind."""
    votes = _dir(growth, 0.55, 0.45) + _dir(liquidity, 0.55, 0.45) - _dir(inflation, 0.6, 0.4)
    return 1 if votes >= 1 else -1 if votes <= -1 else 0


def intermarket_stream(curve_2s10s: Optional[float], hy_spread: Optional[float],
                       risk_appetite: Optional[float]) -> int:
    """INTERMARKET ACTION: steep curve + tight credit + risk appetite = risk-on."""
    votes = 0
    if curve_2s10s is not None:
        votes += 1 if curve_2s10s > 0.2 else -1 if curve_2s10s < 0 else 0     # inversion = risk-off
    if hy_spread is not None:
        votes += 1 if hy_spread < 350 else -1 if hy_spread > 500 else 0        # bps; wide = risk-off
    votes += _dir(risk_appetite, 0.55, 0.45)
    return 1 if votes >= 1 else -1 if votes <= -1 else 0


def flows_stream(cot_extremes_long: Optional[int], cot_extremes_short: Optional[int],
                 put_call: Optional[float]) -> int:
    """CAPITAL FLOWS: crowded longs = contrarian risk-off; crowded shorts / high put-call =
    contrarian risk-on. Positioning is a fade signal."""
    votes = 0
    if cot_extremes_long is not None and cot_extremes_short is not None:
        votes += (cot_extremes_short - cot_extremes_long)   # crowded shorts -> fade -> risk-on
    if put_call is not None:
        votes += 1 if put_call > 1.1 else -1 if put_call < 0.7 else 0          # high fear -> contrarian risk-on
    return 1 if votes >= 1 else -1 if votes <= -1 else 0


def stream_agreement(macro: int, intermarket: int, flows: int) -> Dict:
    """Agreement across the three independent streams + a sizing multiplier."""
    dirs = {"macro": macro, "intermarket": intermarket, "flows": flows}
    ups = sum(1 for d in dirs.values() if d > 0)
    downs = sum(1 for d in dirs.values() if d < 0)
    net = ups - downs
    consensus = "risk-on" if net > 0 else "risk-off" if net < 0 else "neutral / conflicted"
    agreeing = max(ups, downs)                       # streams pointing the dominant way
    opposing = min(ups, downs)
    agreement_score = round(agreeing / 3.0, 2)

    # Sizing: scales with independent agreement, penalised by any opposing stream.
    if agreeing == 3:
        mult, conviction = 1.5, "high"
    elif agreeing == 2 and opposing == 0:
        mult, conviction = 1.2, "moderate"
    elif agreeing == 2 and opposing == 1:
        mult, conviction = 0.7, "conflicted"
    else:
        mult, conviction = 0.5, "low"

    return {
        "streams": dirs,
        "consensus_direction": consensus,
        "agreeing_streams": agreeing,
        "opposing_streams": opposing,
        "agreement_score": agreement_score,
        "conviction": conviction,
        "sizing_multiplier": mult,
        "note": f"{agreeing}/3 independent streams agree ({consensus}); "
                f"size ×{mult} within the VaR budget.",
    }
