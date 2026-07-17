"""
Event-driven volatility forecasting — pure, tested (Phase 6A).

For a recurring high-impact macro event (CPI, FOMC, NFP), estimate how SPX realized
volatility behaves in the ±window trading-day window around it, versus the baseline. Uses
REAL SPX daily closes; the historical event dates are derived from each event's cadence
(monthly / FOMC ~45d), so windows are approximate — the caller should surface that caveat.
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Optional
import numpy as np


def realized_vol(closes: Sequence[float], annualize: bool = True) -> Optional[float]:
    """Annualized realized volatility (std of daily log-ish returns) of a close series."""
    c = np.asarray([x for x in closes if x is not None], dtype=float)
    if c.size < 3:
        return None
    rets = np.diff(c) / c[:-1]
    vol = float(np.std(rets, ddof=1))
    return round(vol * (252 ** 0.5), 4) if annualize else round(vol, 6)


def event_window_vol(dated_closes: Dict[str, float], event_dates: List[str],
                     window: int = 3) -> Dict:
    """Average SPX realized vol in the ±`window` trading-day window around each event date,
    vs the full-sample baseline.

    dated_closes : {YYYY-MM-DD: close} (real trading days).
    event_dates  : approximate event dates (nearest prior trading day is used).
    Returns {baseline_vol, event_vol, expansion_pct, n_events, per_event}.
    """
    dates = sorted(dated_closes.keys())
    if len(dates) < 2 * window + 5 or not event_dates:
        return {"available": False, "reason": "insufficient price history"}
    closes_all = [dated_closes[d] for d in dates]
    baseline = realized_vol(closes_all)
    idx_of = {d: i for i, d in enumerate(dates)}

    def nearest_idx(target: str) -> Optional[int]:
        # nearest trading day at or before target, else the first after
        prior = [d for d in dates if d <= target]
        if prior:
            return idx_of[prior[-1]]
        after = [d for d in dates if d > target]
        return idx_of[after[0]] if after else None

    per_event = []
    for ev in event_dates:
        i = nearest_idx(ev)
        if i is None or i - window < 0 or i + window >= len(dates):
            continue
        win = closes_all[i - window: i + window + 1]
        v = realized_vol(win)
        if v is not None:
            per_event.append({"event_date": ev, "window_vol": v})

    if not per_event:
        return {"available": False, "reason": "no event windows within price history"}
    event_vol = round(float(np.mean([p["window_vol"] for p in per_event])), 4)
    expansion = round((event_vol / baseline - 1.0) * 100, 1) if baseline else None
    return {
        "available": True,
        "baseline_vol": baseline,
        "event_vol": event_vol,
        "expansion_pct": expansion,
        "n_events": len(per_event),
        "per_event": per_event,
        "window": window,
    }
