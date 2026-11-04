"""
Model scorecard — how the platform's forecasts actually performed. Pure, tested.

* Regime transitions: walk-forward test of the empirical transition model on the monthly
  quadrant history (no look-ahead) vs the naive "no change" forecast.
* Recession probabilities: logged forecasts are scored only once their horizon has passed
  and the NBER recession indicator (FRED USREC) for the target month is published —
  Brier score and calibration buckets. Unresolved forecasts are reported as pending.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple


def transition_backtest(regimes: Sequence[str], min_train: int = 60) -> Optional[Dict]:
    """At each month t >= min_train, estimate P(next | current) from months <= t only, predict
    t+1 as the most likely next regime; compare with what happened and with "no change"."""
    regimes = list(regimes)
    states = sorted(set(regimes))
    if len(regimes) < min_train + 2:
        return None
    hits = naive_hits = n = 0
    brier = 0.0
    for t in range(min_train, len(regimes) - 1):
        hist = regimes[:t + 1]
        cur, nxt = hist[-1], regimes[t + 1]
        counts = {s: 0 for s in states}
        for a, b in zip(hist[:-1], hist[1:]):
            if a == cur:
                counts[b] += 1
        tot = sum(counts.values())
        probs = {s: (counts[s] / tot if tot else (1.0 if s == cur else 0.0)) for s in states}
        pred = max(probs, key=probs.get)
        hits += pred == nxt
        naive_hits += cur == nxt
        brier += sum((probs[s] - (1.0 if s == nxt else 0.0)) ** 2 for s in states)
        n += 1
    skill = hits / n - naive_hits / n
    return {"forecasts": n, "hit_rate": round(hits / n, 4),
            "naive_persistence_hit_rate": round(naive_hits / n, 4),
            "brier": round(brier / n, 4), "states": states,
            "skill_vs_naive": round(skill, 4),
            "verdict": ("adds skill over 'no change'" if skill > 0.005 else
                        "no skill beyond regime persistence — use the stay-probability, not the "
                        "'most likely change', for decisions")}


def _add_months(d: date, m: int) -> date:
    y, mo = divmod(d.month - 1 + m, 12)
    return date(d.year + y, mo + 1, 1)


def resolve_recession_forecasts(forecasts: Sequence[Tuple[str, float]],
                                usrec: Dict[str, float], horizon_months: int = 12) -> Dict:
    """forecasts: [(YYYY-MM-DD, probability)]; usrec: {YYYY-MM-01: 0/1} (FRED USREC).

    A forecast made in month m resolves when USREC for month m+horizon is published.
    Returns Brier score + calibration buckets on resolved forecasts, and pending counts.
    """
    resolved: List[Tuple[float, int]] = []
    pending: List[str] = []
    for d, p in forecasts:
        if p is None:
            continue
        made = date.fromisoformat(d[:10]).replace(day=1)
        target = _add_months(made, horizon_months).isoformat()
        if target in usrec:
            resolved.append((float(p), int(round(usrec[target]))))
        else:
            pending.append(target)
    out: Dict = {"resolved": len(resolved), "pending": len(pending),
                 "next_resolution": min(pending) if pending else None}
    if resolved:
        out["brier"] = round(sum((p - y) ** 2 for p, y in resolved) / len(resolved), 4)
        out["base_rate"] = round(sum(y for _, y in resolved) / len(resolved), 4)
        buckets = []
        for lo, hi in ((0, .1), (.1, .25), (.25, .5), (.5, 1.01)):
            grp = [(p, y) for p, y in resolved if lo <= p < hi]
            if grp:
                buckets.append({"range": f"{int(lo*100)}–{min(int(hi*100), 100)}%", "n": len(grp),
                                "avg_forecast": round(sum(p for p, _ in grp) / len(grp), 4),
                                "observed_rate": round(sum(y for _, y in grp) / len(grp), 4)})
        out["calibration"] = buckets
    return out
