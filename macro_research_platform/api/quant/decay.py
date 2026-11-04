"""
Signal decay monitor: is each signal's predictive power holding up, fading, or gone — and should it be retired?

Published signals keep roughly 40% of their in-sample strength after publication and their half-lives have shortened
(McLean–Pontiff; 2026 studies put factor half-lives near 18 months), and decay is not stationary — so a signal is judged
on its own information-coefficient (IC) history, not on its full-sample average:

  early vs recent   mean IC in the first half of the history against the last three years
  trend             slope of IC over time (per year) with its t-statistic
  half-life         if IC is falling but still positive, the years for it to halve at the observed rate
  status            healthy · fading · gone · never worked, with a retirement flag

The retirement rule is deliberately simple and stated: recent IC ≤ 0 after a positive early history (the edge has gone),
never positive in either half, or recent IC below a quarter of its early level with a significantly falling trend
(t < −2). A signal positive only lately is "emerging": watched, not yet trusted.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _ols(x: Sequence[float], y: Sequence[float]) -> Tuple[Optional[float], Optional[float]]:
    """Slope and its t-statistic."""
    n = len(x)
    if n < 4:
        return None, None
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    if sxx == 0:
        return None, None
    b = sum((a - mx) * (c - my) for a, c in zip(x, y)) / sxx
    resid = [c - (my + b * (a - mx)) for a, c in zip(x, y)]
    s2 = sum(r * r for r in resid) / (n - 2)
    se = math.sqrt(s2 / sxx) if s2 > 0 else 0.0
    return b, (b / se if se > 0 else None)


def assess(points: List[Tuple[float, float]], per_year: int) -> Dict[str, Any]:
    """`points` = [(time in years, IC)], oldest first; `per_year` = observations a year (12 monthly, 1 annual)."""
    pts = [(t, v) for t, v in points if v is not None and math.isfinite(v)]
    if len(pts) < max(4, 2 * per_year):
        return {"status": "insufficient history", "retire": False, "observations": len(pts)}
    ics = [v for _, v in pts]
    full = sum(ics) / len(ics)
    half = len(pts) // 2
    early = sum(ics[:half]) / half
    k = min(len(ics) - 1, 3 * per_year)
    recent = sum(ics[-k:]) / k
    slope, t = _ols([p[0] for p in pts], ics)
    half_life = None
    if early > 0 and 0 < recent < early:
        span = pts[-1][0] - (pts[0][0] + pts[half - 1][0]) / 2 - (pts[-1][0] - pts[-k][0]) / 2   # early midpoint → recent midpoint
        if span > 0:
            half_life = span * math.log(2) / math.log(early / recent)
    if early > 0 and recent <= 0:
        status, retire = "gone", True                       # it worked, and no longer does
    elif early <= 0 and recent <= 0:
        status, retire = "never worked", True
    elif early <= 0 < recent:
        status, retire = "emerging", False                  # positive only lately: watch, too early to trust
    elif recent < 0.25 * early and (t is not None and t < -2):
        status, retire = "fading fast", True
    elif recent < 0.6 * early:
        status, retire = "fading", False
    else:
        status, retire = "holding up", False
    return {"status": status, "retire": retire, "ic_full": round(full, 4), "ic_early": round(early, 4),
            "ic_recent": round(recent, 4), "recent_window_years": round(k / per_year, 1),
            "trend_per_year": round(slope, 5) if slope is not None else None, "trend_t": round(t, 2) if t is not None else None,
            "half_life_years": round(half_life, 1) if half_life is not None else None, "observations": len(pts)}


def signal_health() -> Dict[str, Any]:
    """Decay assessment for every Stock Signal Lab signal, for each universe that has a built result."""
    from api.quant import alphalab
    out: List[Dict[str, Any]] = []
    for uni in alphalab.UNIVERSES:
        res = alphalab.saved_result(uni) if hasattr(alphalab, "saved_result") else None
        if not res:
            continue
        for s in res.get("signals") or []:
            monthly = s.get("ic_monthly")
            if monthly:                                     # [[YYYY-MM, ic], …] — newer builds
                pts = [(int(m[:4]) + (int(m[5:7]) - 0.5) / 12, v) for m, v in monthly]
                a, basis = assess(pts, 12), "monthly IC"
            else:                                           # older builds keep yearly means only
                yrs = sorted((int(y), v) for y, v in (s.get("ic_by_year") or {}).items())
                a, basis = assess([(y + 0.5, v) for y, v in yrs], 1), "yearly mean IC"
            out.append({"universe": uni, "id": s["id"], "name": s.get("name", s["id"]), "basis": basis, **a})
    order = {"gone": 0, "fading fast": 1, "never worked": 2, "fading": 3, "emerging": 4, "holding up": 5, "insufficient history": 6}
    out.sort(key=lambda r: (order.get(r["status"], 9), r["universe"], r["id"]))
    return {"signals": out,
            "counts": {k: sum(1 for r in out if r["status"] == k) for k in order},
            "rule": "Retire when the recent IC is ≤ 0 after a positive early history, was never positive, or fell below a quarter "
                    "of its early level with a significantly falling trend (t < −2). 'Fading' and 'emerging' signals are watched.",
            "method": "IC = monthly rank correlation of the signal with next-month returns across the universe. Early = first half "
                      "of the history; recent = last three years. Half-life assumes exponential decay between the two."}
