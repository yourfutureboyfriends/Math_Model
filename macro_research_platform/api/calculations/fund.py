"""
Fund-level accounting and track-record statistics — pure, tested.

NAV convention (no trade blotter yet, so no cash ledger):
    NAV = fund capital + realized P&L + Σ unrealized P&L of open positions
Interest on uninvested cash is NOT accrued, so NAV P&L is already a return in excess of
cash — pass risk_free_annual=0 to track_record for that NAV. Exposures are expressed as %
of NAV. Track-record statistics are computed only from
RECORDED daily NAV snapshots; `proforma_nav` builds a clearly hypothetical path that holds
today's positions constant over past prices (useful context, never mixed into the record).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np


def compute_nav(capital: float, total_unrealized_pnl: float, realized_pnl: float = 0.0) -> float:
    return round(float(capital) + float(realized_pnl) + float(total_unrealized_pnl), 2)


def exposures_pct_nav(summary: Dict, nav: float) -> Dict[str, Optional[float]]:
    """Long / short / gross / net exposure as a fraction of NAV."""
    if not nav or nav <= 0:
        return {"long": None, "short": None, "gross": None, "net": None}
    return {
        "long": round(summary.get("long_market_value", 0.0) / nav, 4),
        "short": round(summary.get("short_market_value", 0.0) / nav, 4),
        "gross": round(summary.get("gross_exposure", 0.0) / nav, 4),
        "net": round(summary.get("net_exposure", 0.0) / nav, 4),
    }


def track_record(navs: Sequence[float], periods_per_year: int = 252,
                 risk_free_annual: float = 0.0) -> Dict:
    """Performance statistics from a chronological NAV series (one value per day).

    Returns total/annualized return, annualized vol, Sharpe and Sortino (excess of
    risk_free_annual, a decimal), max and current drawdown, Calmar, hit rate and best/
    worst day. Needs at least 2 observations; ratios need at least 3 returns.
    """
    v = np.asarray([x for x in navs if x is not None], dtype=float)
    if v.size < 2 or np.any(v <= 0):
        return {"available": False, "reason": f"{v.size} NAV observations — need at least 2",
                "observations": int(v.size)}
    r = v[1:] / v[:-1] - 1.0
    n = r.size
    total = float(v[-1] / v[0] - 1.0)
    ann_ret = float((1.0 + total) ** (periods_per_year / n) - 1.0) if n else 0.0
    rf_p = (1.0 + risk_free_annual) ** (1.0 / periods_per_year) - 1.0
    ex = r - rf_p
    vol = float(r.std(ddof=1) * np.sqrt(periods_per_year)) if n > 1 else None
    sharpe = (float(ex.mean() / r.std(ddof=1) * np.sqrt(periods_per_year))
              if n > 2 and r.std(ddof=1) > 0 else None)
    downside = float(np.sqrt(np.mean(np.minimum(ex, 0.0) ** 2)))
    sortino = (float(ex.mean() / downside * np.sqrt(periods_per_year))
               if n > 2 and downside > 0 else None)
    peak = np.maximum.accumulate(v)
    dd = v / peak - 1.0
    max_dd = float(dd.min())
    calmar = (ann_ret / abs(max_dd)) if max_dd < 0 else None

    def _r(x, k=4):
        return None if x is None else round(x, k)

    return {
        "available": True,
        "observations": int(v.size),
        "total_return": _r(total),
        "annualized_return": _r(ann_ret),
        "annualized_vol": _r(vol),
        "sharpe": _r(sharpe, 2),
        "sortino": _r(sortino, 2),
        "max_drawdown": _r(max_dd),
        "current_drawdown": _r(float(dd[-1])),
        "calmar": _r(calmar, 2),
        "hit_rate": _r(float((r > 0).mean())),
        "best_day": _r(float(r.max())),
        "worst_day": _r(float(r.min())),
    }


def proforma_nav(nav_now: float, position_mv: Dict[str, float],
                 dated_closes: Dict[str, Dict[str, float]], days: int = 252) -> Dict:
    """HYPOTHETICAL NAV path: today's positions (by market value) held constant over the
    last `days` common trading days, scaled so the path ends at today's NAV.

    position_mv: {symbol: signed market value today}; dated_closes: {symbol: {date: close}}.
    Returns {dates, nav} oldest first, or {} when there is no common history.
    """
    syms = [s for s in position_mv if dated_closes.get(s)]
    if not syms or not nav_now:
        return {}
    common = None
    for s in syms:
        common = set(dated_closes[s]) if common is None else common & set(dated_closes[s])
    dates = sorted(common or [])[-(days + 1):]
    if len(dates) < 2:
        return {}
    # Daily $ P&L of the current book on each day, then accumulate backwards from NAV_now.
    pnl = np.zeros(len(dates) - 1)
    for s in syms:
        px = np.array([dated_closes[s][d] for d in dates], dtype=float)
        rets = px[1:] / px[:-1] - 1.0
        pnl += position_mv[s] * rets
    navs = np.empty(len(dates))
    navs[-1] = nav_now
    for i in range(len(dates) - 2, -1, -1):
        navs[i] = navs[i + 1] - pnl[i]
    return {"dates": dates, "nav": [round(float(x), 2) for x in navs]}


def drawdown_from_peak(navs: List[float]) -> Optional[float]:
    """Current drawdown of the latest NAV from its running peak (fraction, <= 0)."""
    v = [x for x in navs if x]
    if not v:
        return None
    return round(v[-1] / max(v) - 1.0, 4)
