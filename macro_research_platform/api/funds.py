"""
Several funds on one platform, kept apart. Each fund has its own database file — positions, orders, blotter, NAV
history, fund settings and mandate, risk limits, analyst pitches and the audit log never mix — while sign-in, market
data, research tools and the Quant Lab are shared.

  main   the original fund: the existing application database (nothing moves)
  other  api/funds/<id>.db, created on first use

The request's fund comes from the X-Fund header (the app sends the one picked in the fund switcher); background jobs
run per fund explicitly (see for_each). A fund may list its members: only they (and admins) can open it.
"""
from __future__ import annotations

import contextvars
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

CURRENT: contextvars.ContextVar = contextvars.ContextVar("fund_id", default="main")
MAIN = "main"
ID_RE = re.compile(r"^[a-z][a-z0-9_-]{1,23}$")
FUNDS_DIR = Path(__file__).resolve().parent / "funds"                 # gitignored


def _registry() -> sqlite3.Connection:
    """The fund registry lives in the main (shared) database, beside the accounts."""
    from api.core.app_db import app_db_path
    c = sqlite3.connect(app_db_path(), timeout=5)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS funds (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, members TEXT, created_at TEXT, created_by TEXT, note TEXT)""")
    if not c.execute("SELECT 1 FROM funds WHERE id = ?", (MAIN,)).fetchone():
        c.execute("INSERT INTO funds (id, name, members, created_at, created_by, note) VALUES (?,?,?,?,?,?)",
                  (MAIN, "My Fund", "[]", datetime.now(timezone.utc).isoformat(timespec="seconds"), "system",
                   "the original application database"))
        c.commit()
    return c


def _row(r: sqlite3.Row) -> Dict[str, Any]:
    d = dict(r)
    d["members"] = json.loads(d.get("members") or "[]")
    return d


def list_funds() -> List[Dict[str, Any]]:
    """Every fund in the registry, the main fund first."""
    with _registry() as c:
        return [_row(r) for r in c.execute("SELECT * FROM funds ORDER BY (id != 'main'), name")]


def get(fund_id: str) -> Optional[Dict[str, Any]]:
    """One fund by id, or None."""
    with _registry() as c:
        r = c.execute("SELECT * FROM funds WHERE id = ?", (fund_id,)).fetchone()
    return _row(r) if r else None


def visible_to(user: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The funds a user may open."""
    return [f for f in list_funds() if can_open(user, f)]


def can_open(user: Optional[Dict[str, Any]], fund: Dict[str, Any]) -> bool:
    """Whether a user may open a fund: administrators always; others when the fund has no member list or they are on
    it.
    """
    if not user:
        return False
    return user.get("role") == "admin" or not fund["members"] or user.get("username") in fund["members"]


def create(fund_id: str, name: str, created_by: str, members: Optional[List[str]] = None,
           settings: Optional[Dict[str, Any]] = None, note: str = "") -> Dict[str, Any]:
    """Create a fund with its own database and initial settings.

    Raises:
        ValueError: the id is invalid or already used.
    """
    fund_id = (fund_id or "").strip().lower()
    if not ID_RE.match(fund_id):
        raise ValueError("fund id: 2–24 characters, lowercase letters, digits, - or _, starting with a letter")
    if get(fund_id):
        raise ValueError(f"fund '{fund_id}' already exists")
    with _registry() as c:
        c.execute("INSERT INTO funds (id, name, members, created_at, created_by, note) VALUES (?,?,?,?,?,?)",
                  (fund_id, (name or fund_id)[:80], json.dumps(sorted(set(members or []))),
                   datetime.now(timezone.utc).isoformat(timespec="seconds"), created_by, (note or "")[:300]))
        c.commit()
    if settings:
        tok = CURRENT.set(fund_id)
        try:
            from api import fund_store
            fund_store.update_settings(settings)
        finally:
            CURRENT.reset(tok)
    return get(fund_id)


def update(fund_id: str, name: Optional[str] = None, members: Optional[List[str]] = None) -> Dict[str, Any]:
    """Rename a fund or change its members.

    Raises:
        LookupError: no such fund.
    """
    f = get(fund_id)
    if not f:
        raise LookupError("fund not found")
    with _registry() as c:
        if name is not None:
            c.execute("UPDATE funds SET name = ? WHERE id = ?", (name[:80], fund_id))
        if members is not None:
            c.execute("UPDATE funds SET members = ? WHERE id = ?", (json.dumps(sorted(set(members))), fund_id))
        c.commit()
    return get(fund_id)


def db_path(fund_id: Optional[str] = None) -> str:
    """The database file of a fund (the current request's when None)."""
    from api.core.app_db import app_db_path
    fid = fund_id or CURRENT.get()
    if fid == MAIN:
        return app_db_path()
    if not ID_RE.match(fid):
        raise ValueError("invalid fund id")
    FUNDS_DIR.mkdir(parents=True, exist_ok=True)
    return str(FUNDS_DIR / f"{fid}.db")


def current() -> str:
    """The id of the fund the current request works in."""
    return CURRENT.get()


def for_each() -> Iterator[str]:
    """Run a block once per fund (background jobs): `for fid in funds.for_each(): …` with CURRENT set to it."""
    for f in list_funds():
        tok = CURRENT.set(f["id"])
        try:
            yield f["id"]
        finally:
            CURRENT.reset(tok)
