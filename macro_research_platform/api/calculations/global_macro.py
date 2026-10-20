"""
Cross-country analytics for the developed-markets monitor. Pure functions (no I/O).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence, Tuple


def policy_stats(points: Sequence[Tuple[str, float]], today: Optional[date] = None,
                 active_days: int = 180) -> Dict:
    """From a dated policy-rate series: latest level, 12-month change, the last move and
    the stance (hiking / cutting within `active_days`, else on hold)."""
    pts = sorted((d, float(v)) for d, v in points if v is not None and float(v) == float(v))
    if not pts:
        return {"available": False}
    today = today or date.today()
    last_d, last_v = pts[-1]
    year_ago = (today - timedelta(days=365)).isoformat()
    base = [v for d, v in pts if d <= year_ago]
    change_12m = round((last_v - base[-1]) * 100) if base else None
    move = None
    for (d0, v0), (d1, v1) in zip(reversed(pts[:-1]), reversed(pts[1:])):
        if abs(v1 - v0) > 1e-9:
            move = {"date": d1, "from": v0, "to": v1, "bp": round((v1 - v0) * 100)}
            break
    stance = "on hold"
    if move and (today - date.fromisoformat(move["date"])).days <= active_days:
        stance = "hiking" if move["bp"] > 0 else "cutting"
    return {"available": True, "rate": last_v, "as_of": last_d, "change_12m_bp": change_12m,
            "last_move": move, "stance": stance}


def recent_moves(series: Dict[str, Sequence[Tuple[str, float]]], since: str) -> List[Dict]:
    """Every policy-rate change on/after `since`, newest first: [{economy, date, from, to, bp}]."""
    out = []
    for econ, points in series.items():
        pts = sorted((d, float(v)) for d, v in points if v is not None and float(v) == float(v))
        for (d0, v0), (d1, v1) in zip(pts, pts[1:]):
            if d1 >= since and abs(v1 - v0) > 1e-9:
                out.append({"economy": econ, "date": d1, "from": v0, "to": v1, "bp": round((v1 - v0) * 100)})
    return sorted(out, key=lambda m: m["date"], reverse=True)


def period_return(dated: Dict[str, float], start_after: str) -> Optional[float]:
    """Return from the last close on/before `start_after` to the latest close (fraction)."""
    days = sorted(dated)
    if not days:
        return None
    base = [d for d in days if d <= start_after]
    if not base or not dated[base[-1]]:
        return None
    return dated[days[-1]] / dated[base[-1]] - 1


def currency_return(fx: Dict[str, float], start_after: str, usd_base: bool) -> Optional[float]:
    """Local currency's return against USD. For USD-base quotes (USD/JPY) a rise means the
    local currency weakened, so the return is inverted."""
    r = period_return(fx, start_after)
    if r is None:
        return None
    return (1 / (1 + r) - 1) if usd_base else r


def in_usd(local_return: Optional[float], ccy_return: Optional[float]) -> Optional[float]:
    if local_return is None:
        return None
    if ccy_return is None:
        return None
    return (1 + local_return) * (1 + ccy_return) - 1


def latest_by_area(rows: Sequence[Dict], area_key: str = "REF_AREA",
                   prefer: Optional[Dict[str, Sequence[Tuple[str, str]]]] = None) -> Dict[str, Tuple[str, float]]:
    """{area: (period, value)} — the latest observation per area. `prefer` maps an area to
    an ordered list of (column, value) preferences, e.g. national CPI before HICP."""
    best: Dict[str, Tuple[Tuple[int, int], str, float]] = {}
    for r in rows:
        try:
            v = float(r["OBS_VALUE"])
        except (TypeError, ValueError, KeyError):
            continue
        area = r[area_key]
        rank = 0
        if prefer and area in prefer:
            for i, (col, val) in enumerate(prefer[area]):
                if r.get(col) == val:
                    rank = i
                    break
            else:
                rank = len(prefer[area])
        p = r["TIME_PERIOD"]
        key = (rank, -date.fromisoformat(period_date(p)).toordinal())   # preferred, then newest
        cur = best.get(area)
        if cur is None or key < cur[0]:
            best[area] = (key, p, v)
    return {a: (p, v) for a, (_, p, v) in best.items()}


def period_date(period: str) -> str:
    """ISO date FRED-style for a reporting period (its first day): '2026-08' → 2026-08-01,
    '2026-Q2' → 2026-04-01 — the convention api/release_calendar.py grades against."""
    if "-Q" in period:
        y, q = period.split("-Q")
        return f"{y}-{(int(q) - 1) * 3 + 1:02d}-01"
    if len(period) == 7:
        return period + "-01"
    return period[:10]


def macro_quadrant(gdp_yoy: Optional[float], cpi_yoy: Optional[float], trend_growth: Optional[float],
                   target: Optional[float], band: float = 0.5) -> Optional[str]:
    """Growth vs the economy's trend and inflation vs its central bank's target:
    goldilocks (above-trend growth, inflation near/below target), reflation (above trend,
    inflation above target + band), stagflation (below trend, inflation high), slowdown."""
    if None in (gdp_yoy, cpi_yoy, trend_growth, target):
        return None
    strong = gdp_yoy >= trend_growth
    hot = cpi_yoy > target + band
    return ("reflation" if hot else "goldilocks") if strong else ("stagflation" if hot else "slowdown")
