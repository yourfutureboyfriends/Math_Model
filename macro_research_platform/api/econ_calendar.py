"""
US economic calendar from official release timetables.

Dates come from FRED's release calendar (release/dates with include_release_dates_with_no_data,
i.e. the agencies' published schedules); FOMC decisions from api.release_calendar.FOMC_DECISIONS.
"Previous" is the latest published value of each release's headline series. No consensus
forecasts are shown — there is no licensed source for them here.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")
_FRED = "https://api.stlouisfed.org/fred"

# release_id: (name, importance, time ET, headline series, transform, unit, affected assets)
RELEASES: Dict[int, tuple] = {
    50:  ("Employment Situation (payrolls)", "HIGH", "08:30", "PAYEMS", "diff", "k", ["SPY", "TLT", "DXY"]),
    10:  ("Consumer Price Index", "HIGH", "08:30", "CPIAUCSL", "yoy", "%", ["TLT", "TIP", "DXY"]),
    53:  ("Gross Domestic Product", "HIGH", "08:30", "A191RL1Q225SBEA", "level", "%", ["SPY", "TLT"]),
    54:  ("Personal Income & Outlays (core PCE)", "HIGH", "08:30", "PCEPILFE", "yoy", "%", ["TLT", "TIP"]),
    9:   ("Retail Sales", "MEDIUM", "08:30", "RSAFS", "mom", "%", ["SPY", "XRT"]),
    46:  ("Producer Price Index", "MEDIUM", "08:30", "PPIFIS", "yoy", "%", ["TLT"]),
    180: ("Initial Jobless Claims", "MEDIUM", "08:30", "ICSA", "level_k", "k", ["TLT", "SPY"]),
    192: ("JOLTS Job Openings", "MEDIUM", "10:00", "JTSJOL", "level_m", "m", ["SPY"]),
    13:  ("Industrial Production", "MEDIUM", "09:15", "INDPRO", "mom", "%", ["SPY", "XLI"]),
    27:  ("Housing Starts", "LOW", "08:30", "HOUST", "level_k", "k", ["XHB"]),
    97:  ("New Home Sales", "LOW", "10:00", "HSN1F", "level_k", "k", ["XHB"]),
    95:  ("Durable Goods Orders", "MEDIUM", "08:30", "DGORDER", "mom", "%", ["SPY"]),
    51:  ("International Trade", "LOW", "08:30", "BOPGSTB", "level_bn", "bn", ["DXY"]),
    91:  ("UMich Consumer Sentiment", "LOW", "10:00", "UMCSENT", "level", "", ["SPY"]),
    11:  ("Employment Cost Index", "MEDIUM", "08:30", "ECIALLCIV", "yoy", "%", ["TLT"]),
}


_LEGACY = {"Consumer Price Index": "CPI Release", "Employment Situation (payrolls)": "Nonfarm Payrolls",
           "FOMC rate decision": "FOMC Decision"}


def _get(path: str, **params) -> dict:
    import requests
    from api.config import FRED_API_KEY
    if not FRED_API_KEY:
        raise RuntimeError("FRED_API_KEY not set")
    r = requests.get(f"{_FRED}/{path}", params={**params, "api_key": FRED_API_KEY, "file_type": "json"}, timeout=8)
    r.raise_for_status()
    return r.json()


def _dates(rid: int, start: date, end: date) -> List[str]:
    """Scheduled dates for one release. Schedules change rarely, so they are cached on disk
    for 12h (and the last good copy is used if FRED is unavailable)."""
    from api.handlers.macro_inputs import _disk_load, _disk_save
    name = f"release_dates_{rid}"
    cached = _disk_load(name, max_age=12 * 3600)
    if cached is None:
        try:
            j = _get("release/dates", release_id=rid, include_release_dates_with_no_data="true",
                     realtime_start=(start - timedelta(days=7)).isoformat(), realtime_end="9999-12-31",
                     sort_order="asc", limit=200)
            cached = {"dates": [d["date"] for d in j.get("release_dates", [])]}
            _disk_save(name, cached)
        except Exception:
            cached = _disk_load(name)
            if cached is None:
                raise
    return [d for d in cached["dates"] if start.isoformat() <= d <= end.isoformat()]


def _previous(series: str, how: str, unit: str) -> Optional[Dict]:
    """Latest print of the headline series. Changes are matched by DATE, not position: a
    missing month (e.g. Oct-2025 CPI, never published) must not shift the comparison."""
    from api.handlers.macro_inputs import _fetch_fred_history_sync
    hist = _fetch_fred_history_sync(series, 800)      # cached in memory/on disk, shared with the app
    vals = {d: float(v) for d, v in zip(hist.dates, hist.values) if v is not None}
    if not vals:
        return None
    d0 = max(vals)
    v0 = vals[d0]
    t0 = date.fromisoformat(d0)

    def back(months: int) -> Optional[float]:
        y, m = divmod(t0.year * 12 + t0.month - 1 - months, 12)
        return vals.get(date(y, m + 1, t0.day).isoformat())

    if how == "yoy":
        base = back(12)
        x = None if base is None else v0 / base * 100 - 100
    elif how == "mom":
        base = back(1)
        x = None if base is None else v0 / base * 100 - 100
    elif how == "diff":
        base = back(1)
        x = None if base is None else v0 - base
    elif how in ("level_m", "level_bn") or (how == "level_k" and series == "ICSA"):
        x = v0 / 1000
    else:
        x = v0
    if x is None:
        return None
    label = {"yoy": " y/y", "mom": " m/m", "diff": ""}.get(how, "")
    sign = "+" if how in ("mom", "diff") and x > 0 else ""
    txt = f"{sign}{x:,.0f}{unit}" if abs(x) >= 100 else f"{sign}{x:,.1f}{unit}{label}"
    return {"value": round(x, 3), "text": txt, "period": d0, "series": series}


_CACHE: Dict[str, tuple] = {}


def get_calendar() -> Dict:
    """build_calendar() cached 30 min, or 2 min when some releases could not be loaded."""
    import time
    hit = _CACHE.get("cal")
    if hit and time.time() < hit[0]:
        return hit[1]
    cal = build_calendar()
    _CACHE["cal"] = (time.time() + (120 if cal["sources_failed"] else 1800), cal)
    return cal


def build_calendar(today: Optional[date] = None, horizon_days: int = 45) -> Dict:
    from api.release_calendar import FOMC_DECISIONS
    today = today or datetime.now(_ET).date()
    end = today + timedelta(days=horizon_days)

    def one(rid):
        name, imp, t, series, how, unit, assets = RELEASES[rid]
        try:
            ds = _dates(rid, today, end)
        except Exception as e:
            logger.warning("[calendar] release %s dates failed: %s", rid, e)
            return rid, [], None, str(e)[:80]
        prev = None
        if ds:
            try:
                prev = _previous(series, how, unit)
            except Exception as e:
                logger.debug("[calendar] previous %s failed: %s", series, e)
        return rid, ds, prev, None

    with ThreadPoolExecutor(max_workers=2) as ex:   # FRED rate limit is shared
        results = list(ex.map(one, RELEASES))

    events, failed = [], []
    for rid, ds, prev, err in results:
        name, imp, t, series, how, unit, assets = RELEASES[rid]
        if err:
            failed.append(name)
        # weekly claims: next two prints only
        months = set()
        for d in (ds[:2] if rid == 180 else ds):
            label = name
            if rid == 95 and int(d[8:]) <= 10:
                label = "Factory Orders (full M3 report)"   # the advance report is durable goods
            elif rid != 180:
                if (label, d[:7]) in months:      # one print per release per month
                    continue
                months.add((label, d[:7]))
            events.append({"name": label, "importance": imp, "date": d, "time_et": t, "release_id": rid,
                           "previous": prev["text"] if prev else None,
                           "previous_period": prev["period"] if prev else None,
                           "series_id": series, "affected_assets": assets, "source": "FRED release calendar"})
    fomc = [d for d in FOMC_DECISIONS if today.isoformat() <= d <= end.isoformat()]
    target = None
    if fomc:
        try:
            from api.handlers.macro_inputs import _fetch_fred_history_sync
            lo, hi = (_fetch_fred_history_sync(s, 400) for s in ("DFEDTARL", "DFEDTARU"))
            if lo.values and hi.values:
                target = (f"{lo.values[-1]:.2f}–{hi.values[-1]:.2f}%", lo.dates[-1])
        except Exception as e:
            logger.debug("[calendar] fed target failed: %s", e)
    for d in fomc:
        events.append({"name": "FOMC rate decision", "importance": "HIGH", "date": d, "time_et": "14:00",
                       "release_id": None, "previous": target[0] if target else None,
                       "previous_period": target[1] if target else None, "series_id": "DFEDTARU",
                       "affected_assets": ["TLT", "DXY", "SPY"], "source": "Federal Reserve calendar"})

    now_et = datetime.now(_ET)
    rows = []
    for i, e in enumerate(sorted(events, key=lambda e: (e["date"], e["time_et"]))):
        hh, mm = map(int, e["time_et"].split(":"))
        dt = datetime.fromisoformat(e["date"]).replace(hour=hh, minute=mm, tzinfo=_ET)
        if dt < now_et - timedelta(hours=1):
            continue
        rows.append({"id": i, "event_name": e["name"], "importance": e["importance"],
                     "release_datetime": dt.astimezone(timezone.utc).isoformat(), "time_et": e["time_et"],
                     "actual": None, "forecast": None, "previous": e["previous"],
                     "previous_period": e["previous_period"], "series_id": e["series_id"], "release_id": e["release_id"],
                     "affected_assets": e["affected_assets"], "source": e["source"]})
    nxt = next((r for r in rows if datetime.fromisoformat(r["release_datetime"]) > now_et), None)
    minutes = int((datetime.fromisoformat(nxt["release_datetime"]) - now_et).total_seconds() // 60) if nxt else None
    week_end = (today + timedelta(days=7)).isoformat()
    return {
        "upcoming": rows,
        "this_week": [r for r in rows if r["release_datetime"][:10] <= week_end],
        "minutes_to_next": minutes,
        "blackout_active": bool(nxt and nxt["importance"] == "HIGH" and minutes is not None and minutes <= 30),
        "as_of": now_et.isoformat(timespec="minutes"),
        "horizon_days": horizon_days,
        "sources_failed": failed,
        # Back-compat for older consumers
        "events": [{"date": r["release_datetime"][:10], "event": _LEGACY.get(r["event_name"], r["event_name"]),
                    "impact": r["importance"], "release_id": r["release_id"], "source": r["source"]} for r in rows],
    }
