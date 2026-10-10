"""
ECO (global economic calendar) and ECST (economic surprises), free sources:

  · Calendar + consensus forecasts, all major economies: the Forex Factory weekly feed
    (nfs.faireconomy.media). It only covers the current week, so every snapshot is kept on
    disk — consensus history accumulates from the day the terminal starts recording.
  · Actuals for US releases: ALFRED (St. Louis Fed), the vintage published on release day —
    the number as announced, before later revisions.
  · Surprise index (model-based): each US release vs what its own recent trend implied,
    standardised and decayed (half-life 30 days). The free counterpart of Citi's surprise
    index, which uses paid consensus history; reconstructible back to 2010 from ALFRED.
"""
from __future__ import annotations

import json
import logging
import math
import re
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from api.marketdata.core import NotFound, Upstream, _cached

logger = logging.getLogger(__name__)
STORE = Path(__file__).resolve().parents[2] / "data" / "processed" / "ecst" / "events.json"
FEED = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
_lock = threading.Lock()

# Forex Factory title → (FRED series, transform, display scale, label). transforms: pct_mm,
# pct_yy, diff, level. Scale converts FRED units to the feed's (e.g. thousands → "K").
US_ACTUALS: Dict[str, Tuple[str, str, float, str]] = {
    "CPI m/m": ("CPIAUCSL", "pct_mm", 1, "%"), "Core CPI m/m": ("CPILFESL", "pct_mm", 1, "%"),
    "CPI y/y": ("CPIAUCSL", "pct_yy", 1, "%"), "Core CPI y/y": ("CPILFESL", "pct_yy", 1, "%"),
    "PPI m/m": ("PPIFIS", "pct_mm", 1, "%"), "Core PPI m/m": ("PPIFES", "pct_mm", 1, "%"),
    "Retail Sales m/m": ("RSAFS", "pct_mm", 1, "%"), "Core Retail Sales m/m": ("RSFSXMV", "pct_mm", 1, "%"),
    "Non-Farm Employment Change": ("PAYEMS", "diff", 1, "K"), "Unemployment Rate": ("UNRATE", "level", 1, "%"),
    "Average Hourly Earnings m/m": ("CES0500000003", "pct_mm", 1, "%"), "Unemployment Claims": ("ICSA", "level", 1e-3, "K"),
    "Industrial Production m/m": ("INDPRO", "pct_mm", 1, "%"), "Building Permits": ("PERMIT", "level", 1e-3, "M"),
    "Housing Starts": ("HOUST", "level", 1e-3, "M"), "Core PCE Price Index m/m": ("PCEPILFE", "pct_mm", 1, "%"),
    "JOLTS Job Openings": ("JTSJOL", "level", 1e-3, "M"), "Advance GDP q/q": ("A191RL1Q225SBEA", "level", 1, "%"),
    "Prelim GDP q/q": ("A191RL1Q225SBEA", "level", 1, "%"), "Final GDP q/q": ("A191RL1Q225SBEA", "level", 1, "%"),
    "Trade Balance": ("BOPGSTB", "level", 1e-3, "B"), "Consumer Credit m/m": ("TOTALSL", "diff", 1e-3, "B"),
    "Durable Goods Orders m/m": ("DGORDER", "pct_mm", 1, "%"), "Core Durable Goods Orders m/m": ("ADXTNO", "pct_mm", 1, "%"),
}
# Series for the model-based surprise index (transform, weight)
INDEX_SERIES = {"PAYEMS": ("diff", 1.0), "UNRATE": ("level_inv", 1.0), "ICSA": ("level_inv", 0.5), "RSAFS": ("pct_mm", 1.0),
                "INDPRO": ("pct_mm", 1.0), "HOUST": ("pct_mm", 0.5), "PERMIT": ("pct_mm", 0.5), "DGORDER": ("pct_mm", 0.5),
                "CPIAUCSL": ("pct_mm", 0.0), "JTSJOL": ("pct_mm", 0.5)}


def _num(s: Any) -> Optional[float]:
    """'0.3%' → 0.3, '150K' → 150, '-1.2B' → -1.2, '<0.1%' → 0.1."""
    if s is None:
        return None
    m = re.search(r"-?\d+(\.\d+)?", str(s).replace(",", ""))
    return float(m.group(0)) if m else None


def _load() -> Dict[str, Dict[str, Any]]:
    try:
        return json.loads(STORE.read_text()) if STORE.exists() else {}
    except Exception:
        return {}


def _save(d: Dict[str, Dict[str, Any]]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d))
    tmp.replace(STORE)


def _snapshot() -> List[Dict[str, Any]]:
    """Fetch this week's calendar and merge it into the on-disk store (consensus history)."""
    def fetch():
        import requests
        r = requests.get(FEED, timeout=20, headers={"User-Agent": "Mozilla/5.0 (research terminal)"})
        r.raise_for_status()
        return r.json()
    try:
        events = _cached("ff:week", 1800, fetch)
    except Exception as e:
        logger.warning("[eco] calendar feed unavailable: %s", e)
        events = []
    with _lock:
        store = _load()
        for e in events:
            key = f"{e.get('country')}|{e.get('title')}|{e.get('date')}"
            rec = store.get(key, {"first_seen": datetime.utcnow().isoformat(timespec="seconds")})
            rec.update({"country": e.get("country"), "title": e.get("title"), "date": e.get("date"), "impact": e.get("impact"),
                        "previous": e.get("previous") or rec.get("previous")})
            if e.get("forecast"):
                rec["forecast"] = e["forecast"]
            if e.get("actual"):
                rec["actual_feed"] = e["actual"]
            store[key] = rec
        if events:
            _save(store)
    return events


def _vintage_value(series: str, transform: str, released: str) -> Optional[Tuple[float, str]]:
    """The headline number as published on `released` (ALFRED vintage of that day)."""
    from api.providers import alfred

    def fetch():
        obs = [o for o in alfred.as_of(series, released, start=str(date.fromisoformat(released) - timedelta(days=500))) if o["value"] is not None]
        return obs
    obs = _cached(f"vint:{series}:{released}", 86400 * 30, fetch)
    if len(obs) < 13:
        return None
    last, prev, yago = obs[-1]["value"], obs[-2]["value"], obs[-13]["value"]
    v = {"pct_mm": (last / prev - 1) * 100 if prev else None, "pct_yy": (last / yago - 1) * 100 if yago else None,
         "diff": last - prev, "level": last}[transform]
    return (v, obs[-1]["date"]) if v is not None else None


def _release_dates(series: str) -> Dict[str, str]:
    """observation date → first-release date (ALFRED initial releases)."""
    from api.providers import alfred
    return _cached(f"rel:{series}", 6 * 3600, lambda: {o["date"]: o["released"] for o in alfred.first_release(series, start="2008-01-01")})


def _actual_for(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    m = US_ACTUALS.get(rec.get("title") or "")
    if not m or rec.get("country") != "USD":
        return None
    series, transform, scale, unit = m
    ev_day = str(rec["date"])[:10]
    rel = _release_dates(series)
    if ev_day not in set(rel.values()):                  # not released yet (or a different release)
        return None
    got = _vintage_value(series, transform, ev_day)
    if not got:
        return None
    return {"actual": round(got[0] * scale, 3), "unit": unit, "period": got[1], "series": series}


def calendar(days_back: int = 7, countries: Optional[List[str]] = None, min_impact: str = "Low") -> Dict[str, Any]:
    """This week's global calendar plus recorded history: forecast, previous, actual (US from
    ALFRED) and the surprise (actual − forecast)."""
    _snapshot()
    rank = {"Holiday": -1, "Non-Economic": -1, "Low": 0, "Medium": 1, "High": 2}
    cutoff = (datetime.utcnow() - timedelta(days=days_back)).date().isoformat()
    rows = []
    with _lock:
        store = _load()
    for rec in store.values():
        d = str(rec.get("date"))[:10]
        if d < cutoff or rank.get(rec.get("impact"), 0) < rank.get(min_impact, 0):
            continue
        if countries and rec.get("country") not in countries:
            continue
        r = {k: rec.get(k) for k in ("country", "title", "date", "impact", "forecast", "previous")}
        past = d <= date.today().isoformat()
        if past:
            try:
                a = _actual_for(rec)
            except Exception as e:
                logger.debug("[eco] actual %s: %s", rec.get("title"), e)
                a = None
            if a:
                r.update(a)
                f = _num(rec.get("forecast"))
                r["surprise"] = round(a["actual"] - f, 3) if f is not None else None
            elif rec.get("actual_feed"):
                r["actual"] = _num(rec["actual_feed"])
        rows.append(r)
    rows.sort(key=lambda x: str(x["date"]))
    return {"events": rows, "countries": sorted({r["country"] for r in rows if r.get("country")}),
            "recorded_since": min((v.get("first_seen", "") for v in store.values()), default=None),
            "note": "Consensus forecasts come from a weekly feed and are recorded from the day this terminal first saw "
                    "them; US actuals are the figures as first published (ALFRED). Other countries: forecast and previous.",
            "source": "Forex Factory calendar feed; ALFRED (St. Louis Fed)"}


def surprise_index(start: str = "2010-01-01", half_life_days: int = 30) -> Dict[str, Any]:
    """Model-based US data surprise index: for each release, (actual change − mean of the prior
    6 changes) ÷ std of the prior 24, weighted, summed with exponential decay."""
    def fetch():
        from api.providers import alfred
        events: List[Tuple[date, float, str]] = []
        contrib: Dict[str, List[Dict[str, Any]]] = {}
        for sid, (tf, w) in INDEX_SERIES.items():
            if w == 0:
                continue
            try:
                fr = [o for o in alfred.first_release(sid, start="2005-01-01") if o["value"] is not None and o.get("released")]
            except Exception as e:
                logger.warning("[ecst] %s: %s", sid, e)
                continue
            vals = np.array([o["value"] for o in fr], float)
            if len(vals) < 40:
                continue
            if tf == "diff":
                ch = np.diff(vals)
            elif tf == "pct_mm":
                ch = np.diff(vals) / vals[:-1] * 100
            else:                                  # level_inv: higher is worse (unemployment, claims)
                ch = -np.diff(vals)
            rel = [o["released"] for o in fr[1:]]
            for i in range(24, len(ch)):
                prior = ch[i - 24:i]
                sd = prior.std()
                if sd <= 0:
                    continue
                z = float(np.clip((ch[i] - ch[i - 6:i].mean()) / sd, -4, 4)) * w
                d = date.fromisoformat(rel[i])
                if str(d) >= start:
                    events.append((d, z, sid))
                    contrib.setdefault(sid, []).append({"date": str(d), "z": z})
        if not events:
            raise Upstream("ALFRED unavailable for the surprise index.")
        events.sort()
        lam = math.log(2) / half_life_days
        out, k, level, last = [], 0, 0.0, None
        day = date.fromisoformat(start)
        end = date.today()
        while day <= end:
            if last is not None:
                level *= math.exp(-lam * (day - last).days)
            while k < len(events) and events[k][0] <= day:
                level += events[k][1]
                k += 1
            last = day
            if day.weekday() == 4 or day == end:      # weekly points (Fridays) + today
                out.append({"date": str(day), "index": round(level, 3)})
            day += timedelta(days=1)
        recent = sorted((e for e in events if (end - e[0]).days <= 45), key=lambda e: -abs(e[1]))[:10]
        return {"series": out, "latest": out[-1]["index"] if out else None,
                "recent": [{"date": str(d), "series": s, "z": round(z, 2)} for d, z, s in recent],
                "components": {s: {"transform": INDEX_SERIES[s][0], "weight": INDEX_SERIES[s][1]} for s in contrib},
                "method": "Each US release (as first published, ALFRED) vs the average of its previous 6 changes, in standard "
                          "deviations of the previous 24; inflation excluded; summed with a 30-day half-life. Above 0: data "
                          "beating its recent trend. A model-based proxy — consensus-based surprises are recorded separately "
                          "as the weekly calendar is captured.",
                "source": "ALFRED (St. Louis Fed)"}
    return _cached(f"ecst:{start}:{half_life_days}", 6 * 3600, fetch)
