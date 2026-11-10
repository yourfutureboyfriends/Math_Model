"""
Point-in-time archive: keep the data as it was known on the day, for sources that do not keep their own history.

  data_vintages        every distinct version of a downloaded file (e.g. the Fed's excess bond premium, which is
                       re-estimated each month and published without vintages), stored when its content changes
  commodity_curves     a daily snapshot of each commodity futures curve (front price, one-year slope, annualised
                       roll yield, the listed contracts) — Yahoo serves only contracts still trading, so past roll
                       yields cannot be rebuilt later; this builds the history to test commodity carry on

Both live in the main database, so the daily backup covers them. Read with `vintages(name)`, `vintage_as_of(name, day)`
and `carry_history(root)`.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
_ready = False

# commodity roots snapshotted daily (financial futures are carry by construction, not a commodity signal)
COMMODITY_ROOTS = ["CL", "BZ", "NG", "HO", "RB", "GC", "SI", "HG", "ZC", "ZW", "ZS", "KC", "LE", "HE", "CT", "SB", "PL", "PA"]


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
        c.execute("CREATE TABLE IF NOT EXISTS data_vintages (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, "
                  "captured_at TEXT NOT NULL, sha256 TEXT NOT NULL, content BLOB NOT NULL)")
        c.execute("CREATE INDEX IF NOT EXISTS ix_data_vintages_name ON data_vintages (name, captured_at)")
        c.execute("CREATE TABLE IF NOT EXISTS commodity_curves (day TEXT NOT NULL, root TEXT NOT NULL, front_month TEXT, "
                  "front_price REAL, slope_1y REAL, roll_yield REAL, points TEXT, PRIMARY KEY (day, root))")
    _ready = True


def archive(name: str, content: str | bytes) -> bool:
    """Store `content` as a new vintage of `name` if it differs from the latest stored one (a reverted file is a new
    vintage too). Returns True when stored."""
    init()
    raw = content.encode("utf-8") if isinstance(content, str) else content
    sha = hashlib.sha256(raw).hexdigest()
    with _conn() as c:
        last = c.execute("SELECT sha256 FROM data_vintages WHERE name = ? ORDER BY id DESC LIMIT 1", (name,)).fetchone()
        if last and last["sha256"] == sha:
            return False
        c.execute("INSERT INTO data_vintages (name, captured_at, sha256, content) VALUES (?,?,?,?)",
                  (name, datetime.now(timezone.utc).isoformat(timespec="seconds"), sha, raw))
        return True


def vintages(name: str) -> List[Dict[str, Any]]:
    init()
    with _conn() as c:
        return [{"captured_at": r["captured_at"], "sha256": r["sha256"], "bytes": r["n"]} for r in c.execute(
            "SELECT captured_at, sha256, length(content) AS n FROM data_vintages WHERE name = ? ORDER BY id", (name,))]


def vintage_as_of(name: str, day: str) -> Optional[str]:
    """The version of `name` that was current on `day` (ISO date): the latest captured on or before it."""
    init()
    with _conn() as c:
        r = c.execute("SELECT content FROM data_vintages WHERE name = ? AND substr(captured_at, 1, 10) <= ? "
                      "ORDER BY id DESC LIMIT 1", (name, day)).fetchone()
    return r["content"].decode("utf-8") if r else None


def snapshot_commodity_curves(roots: Optional[List[str]] = None) -> Dict[str, Any]:
    """Today's curve for each commodity root (idempotent per day). Failures are recorded, not raised."""
    from api.marketdata.monitors import futures_curve
    init()
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    done, failed = [], {}
    for root in roots or COMMODITY_ROOTS:
        try:
            cv = futures_curve(root)
        except Exception as e:                                               # noqa: BLE001 — record, carry on
            failed[root] = str(e)[:120]
            continue
        pts = [{"month": p["month"], "price": p["price"]} for p in cv.get("points", [])]
        with _conn() as c:
            c.execute("INSERT OR REPLACE INTO commodity_curves (day, root, front_month, front_price, slope_1y, roll_yield, points) "
                      "VALUES (?,?,?,?,?,?,?)", (day, root, cv["front"]["month"], cv["front"]["price"], cv.get("slope"),
                                                 cv.get("annualised_roll_yield"), json.dumps(pts)))
        done.append(root)
    return {"day": day, "saved": done, "failed": failed}


def carry_history(root: str) -> List[Dict[str, Any]]:
    init()
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT day, front_month, front_price, slope_1y, roll_yield FROM commodity_curves "
                                           "WHERE root = ? ORDER BY day", (root.upper(),))]


def status() -> Dict[str, Any]:
    init()
    with _conn() as c:
        v = [dict(r) for r in c.execute("SELECT name, COUNT(*) AS versions, MIN(captured_at) AS first, MAX(captured_at) AS last "
                                        "FROM data_vintages GROUP BY name")]
        cc = c.execute("SELECT COUNT(DISTINCT day) AS days, COUNT(DISTINCT root) AS roots, MIN(day) AS first, MAX(day) AS last "
                       "FROM commodity_curves").fetchone()
    return {"file_vintages": v, "commodity_curves": dict(cc),
            "note": "Kept so future tests can use data as it was known at the time; commodity carry needs about two "
                    "years of daily curves before it can be tested."}
