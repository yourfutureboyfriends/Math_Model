"""
Screen usage: which screens people actually read, so the platform can be consolidated on evidence — the bottom third of
screens that nobody opens are candidates to retire or fold into a workflow.

  view     a dashboard panel that stayed at least 40% on screen for 3 seconds, or a Markets function opened; counted at
           most once per screen per page load, with the seconds it stayed in view
  known    every screen the app could show (panels in the layout, Markets functions), registered by the browser, so
           screens with no views at all are listed too
  stored   per day × user × screen: views and seconds — nothing about what was on the screen

Kept in the main database (usage_daily, usage_known). Internal measurement only; the summary is visible to signed-in
members.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List

SCREEN_RE = re.compile(r"^(dash|mkt|pe):[A-Za-z0-9_.\-]{1,60}$")
_ready = False


def _conn() -> sqlite3.Connection:
    from api.core.app_db import app_db_path
    c = sqlite3.connect(app_db_path(), timeout=10)
    c.row_factory = sqlite3.Row
    return c


def init() -> None:
    global _ready
    if _ready:
        return
    with _conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS usage_daily (day TEXT NOT NULL, username TEXT NOT NULL, screen TEXT NOT NULL, "
                  "views INTEGER NOT NULL DEFAULT 0, seconds INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, username, screen))")
        c.execute("CREATE TABLE IF NOT EXISTS usage_known (screen TEXT PRIMARY KEY, label TEXT, area TEXT, last_registered TEXT)")
    _ready = True


def record(username: str, events: Iterable[Dict[str, Any]], known: Iterable[Dict[str, Any]] = ()) -> Dict[str, int]:
    init()
    day = date.today().isoformat()
    n = k = 0
    with _conn() as c:
        for e in list(events)[:500]:
            s = str(e.get("screen") or "")
            if not SCREEN_RE.match(s):
                continue
            secs = max(0, min(int(e.get("seconds") or 0), 4 * 3600))
            views = max(0, min(int(e.get("views") or 1), 100))
            c.execute("INSERT INTO usage_daily (day, username, screen, views, seconds) VALUES (?,?,?,?,?) "
                      "ON CONFLICT(day, username, screen) DO UPDATE SET views = views + excluded.views, seconds = seconds + excluded.seconds",
                      (day, username, s, views, secs))
            n += 1
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for s in list(known)[:2000]:
            sid = str(s.get("screen") or "")
            if SCREEN_RE.match(sid):
                c.execute("INSERT INTO usage_known (screen, label, area, last_registered) VALUES (?,?,?,?) ON CONFLICT(screen) DO UPDATE "
                          "SET label = excluded.label, area = excluded.area, last_registered = excluded.last_registered",
                          (sid, str(s.get("label") or "")[:80], str(s.get("area") or "")[:20], now))
                k += 1
    return {"events": n, "known": k}


def summary(days: int = 90) -> Dict[str, Any]:
    init()
    since = (date.today() - timedelta(days=days)).isoformat()
    with _conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT screen, SUM(views) AS views, SUM(seconds) AS seconds, COUNT(DISTINCT username) AS users, MAX(day) AS last_day "
            "FROM usage_daily WHERE day >= ? GROUP BY screen ORDER BY views DESC", (since,))]
        known = {r["screen"]: dict(r) for r in c.execute("SELECT * FROM usage_known")}
        first = c.execute("SELECT MIN(day) FROM usage_daily").fetchone()[0]
    used = {r["screen"] for r in rows}
    for r in rows:
        k = known.get(r["screen"]) or {}
        r["label"], r["area"] = k.get("label") or r["screen"].split(":", 1)[1], k.get("area") or r["screen"].split(":", 1)[0]
    never = sorted(({"screen": s, "label": v["label"], "area": v["area"]} for s, v in known.items() if s not in used),
                   key=lambda x: (x["area"] or "", x["label"] or ""))
    total = sum(r["views"] for r in rows) or 1
    cum, top80 = 0, 0
    for r in rows:
        cum += r["views"]
        top80 += 1
        if cum / total >= 0.8:
            break
    return {"days": days, "since": since, "tracking_since": first, "screens": rows, "never_viewed": never,
            "known_screens": len(known), "viewed_screens": len(rows),
            "concentration": {"screens_for_80pct_of_views": top80 if rows else 0, "of": len(rows)},
            "note": "A view = a panel at least 40% on screen for 3 s, or a Markets function opened; once per screen per page "
                    "load. Judge after a few weeks of normal use: a screen nobody opens in 90 days is a candidate to retire "
                    "or fold into a workflow."}
