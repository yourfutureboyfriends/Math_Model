"""
Signal governance — pure, tested.

Turns the out-of-sample evidence the platform already measures into consequences:

* ``evidence_status``: a walk-forward scorecard (api/calculations/backtest.backtest_signal) becomes
  PASS / WEAK / FAIL. FAIL = the signal lost money as a strategy (Sharpe < 0 or total return < 0);
  WEAK = its independent-window hit rate cannot be told from a coin flip (p > 0.10); else PASS.
* ``evidence_weights``: ensemble weights scaled by that status (PASS 1, WEAK 0.5, no evidence 0.5,
  FAIL 0 — retired from the score but still shown), renormalised to sum to 1.
* ``independence_agreement``: votes grouped by the data that drives them, each driver counting once,
  so four equity-price signals agreeing is not reported as four independent confirmations.
* ``factor_consequences``: factors flagged unstable out-of-sample are excluded from rotation calls.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

STATUS_MULT = {"PASS": 1.0, "WEAK": 0.5, "UNVALIDATED": 0.5, "FAIL": 0.0}
# composite input → the walk-forward test of that exact input (api/handlers/governance._input_scorecards)
INPUT_EVIDENCE = {"Growth signal": "input_growth", "1 − recession probability": "input_recession",
                  "Risk-appetite signal": "input_risk", "Liquidity signal": "input_liquidity"}


def evidence_for(cards: Dict[str, Dict]) -> Dict[str, Optional[Dict]]:
    return {name: cards.get(cid) for name, cid in INPUT_EVIDENCE.items()}


def evidence_status(card: Optional[Dict]) -> Tuple[str, str]:
    """(status, reason) for one backtest scorecard; UNVALIDATED when there is none."""
    if not card or not card.get("available"):
        return "UNVALIDATED", "no walk-forward test of this input"
    sh, tr = card.get("strategy_sharpe"), card.get("strategy_total_return")
    hr, p = card.get("hit_rate_independent"), card.get("hit_rate_p_value")
    desc = (f"Sharpe {sh:.2f}" if sh is not None else "Sharpe n/a") + (
        f", total {tr:+.0%}" if tr is not None else "") + (
        f", hit {hr:.0%} (p={p:.2f})" if hr is not None and p is not None else "")
    if (sh is not None and sh < 0) or (tr is not None and tr < 0):
        return "FAIL", f"lost money out-of-sample ({desc}) — retired from the score"
    if p is None or p > 0.10:
        return "WEAK", f"hit rate not distinguishable from 50% ({desc}) — half weight"
    bh = card.get("buy_hold_sharpe")
    if bh is not None and sh is not None and sh < bh:
        # a mostly-bullish signal in a rising market "wins" on drift alone; it must beat simply holding
        return "WEAK", f"no better than holding the index ({desc}; buy-and-hold Sharpe {bh:.2f}) — half weight"
    return "PASS", f"survives out-of-sample ({desc})"


def evidence_weights(components: Sequence[Tuple[str, float]],
                     evidence: Dict[str, Optional[Dict]]) -> List[Dict]:
    """Weight each (name, score) component by its evidence; equal base weights.

    ``evidence`` maps component name → scorecard (or None). If every component is retired the
    weights fall back to equal so the score stays defined (and says so)."""
    rows = []
    for name, score in components:
        status, reason = evidence_status(evidence.get(name))
        rows.append({"name": name, "score": score, "status": status, "reason": reason,
                     "raw": STATUS_MULT[status]})
    tot = sum(r["raw"] for r in rows)
    for r in rows:
        w = (r["raw"] / tot) if tot > 0 else 1.0 / len(rows)
        r["weight"] = round(w, 3)
        r["contribution"] = round(r["score"] * w, 3) if r["score"] is not None else None
        r.pop("raw")
    return rows


def independence_agreement(votes: Dict[str, bool], drivers: Dict[str, str]) -> Dict:
    """Agreement with each driver counted once (its members' votes averaged).

    Returns {agreement, bullish_share, effective_votes, raw_agreement, drivers: {driver: share}}."""
    if not votes:
        return {"agreement": None, "bullish_share": None, "effective_votes": 0,
                "raw_agreement": None, "drivers": {}}
    groups: Dict[str, List[bool]] = {}
    for k, v in votes.items():
        groups.setdefault(drivers.get(k, k), []).append(bool(v))
    shares = {g: sum(v) / len(v) for g, v in groups.items()}
    bull = sum(shares.values()) / len(shares)
    n_bull = sum(votes.values())
    return {"agreement": round(max(bull, 1 - bull), 2), "bullish_share": round(bull, 2),
            "effective_votes": len(groups),
            "raw_agreement": round(max(n_bull, len(votes) - n_bull) / len(votes), 2),
            "drivers": {g: round(s, 2) for g, s in shares.items()}}


def factor_consequences(validation: Optional[Dict]) -> Dict[str, Dict]:
    """Factor short name (e.g. 'momentum') → {unstable, verdict} from /factor-validation output."""
    out: Dict[str, Dict] = {}
    for r in (validation or {}).get("factors") or []:
        if not r.get("available"):
            continue
        short = r["factor"].split(" ")[0].lower()
        out[short] = {"unstable": bool(r.get("unstable")), "r2_is": r.get("in_sample_r2"),
                      "r2_oos": r.get("out_of_sample_r2"), "verdict": r.get("verdict")}
    return out


def cluster_votes(series: Dict[str, Sequence[int]], threshold: float = 0.5) -> Dict:
    """Group votes whose day-by-day positions (+1 / −1, 0 = no vote) correlate at |ρ| ≥ threshold (connected
    components). Correlation uses the days both voted. Returns {corr, groups: {vote: group label}}."""
    import numpy as np
    names = list(series)
    corr: Dict[str, Dict[str, Optional[float]]] = {a: {} for a in names}
    parent = {n: n for n in names}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            x, y = np.asarray(series[a], float), np.asarray(series[b], float)
            n = min(x.size, y.size)
            x, y = x[-n:], y[-n:]
            m = (x != 0) & (y != 0)
            r = float(np.corrcoef(x[m], y[m])[0, 1]) if m.sum() > 30 and x[m].std() > 0 and y[m].std() > 0 else None
            corr[a][b] = corr[b][a] = round(r, 2) if r is not None else None
            if r is not None and abs(r) >= threshold:
                parent[find(a)] = find(b)
    roots: Dict[str, List[str]] = {}
    for n in names:
        roots.setdefault(find(n), []).append(n)
    groups = {n: " + ".join(sorted(members)) if len(members) > 1 else n for members in roots.values() for n in members}
    return {"corr": corr, "groups": groups, "threshold": threshold, "independent_groups": len(roots)}
