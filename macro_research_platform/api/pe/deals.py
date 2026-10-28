"""
The deal pipeline: saved LBO cases and their progress, kept in the current fund's own database (api/funds.py), so
each fund's deals stay apart. A deal stores its full input set, the headline results of its last run, its stage and
an activity log (stage changes and notes, who and when).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

STAGES = ["Sourcing", "Screening", "First-round bid", "Due diligence", "Final bid / IC", "Signed", "Closed", "Passed"]
_ready: set = set()


def _conn() -> sqlite3.Connection:
    from api import funds
    path = funds.db_path()
    c = sqlite3.connect(path, timeout=10)
    c.row_factory = sqlite3.Row
    if path not in _ready:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS pe_deals (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, symbol TEXT,
                sector TEXT, stage TEXT NOT NULL DEFAULT 'Sourcing', owner TEXT, inputs TEXT NOT NULL, summary TEXT,
                notes TEXT, created_at TEXT, updated_at TEXT);
            CREATE TABLE IF NOT EXISTS pe_deal_log (id INTEGER PRIMARY KEY AUTOINCREMENT, deal_id INTEGER NOT NULL,
                at TEXT NOT NULL, author TEXT, kind TEXT NOT NULL, text TEXT);
        """)
        _ready.add(path)
    return c


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row(r: sqlite3.Row, full: bool = False) -> Dict[str, Any]:
    d = dict(r)
    d["summary"] = json.loads(d["summary"]) if d.get("summary") else None
    if full:
        d["inputs"] = json.loads(d["inputs"])
    else:
        d.pop("inputs", None)
    return d


def summarise(result: Dict[str, Any]) -> Dict[str, Any]:
    """The headline numbers of an lbo.analyse() result, kept with the deal for the pipeline view."""
    b = result["cases"]["base"]
    return {"irr": b["returns"]["sponsor_irr"], "moic": b["returns"]["moic"], "weighted_irr": result["weighted"]["irr"],
            "entry_multiple": b["entry"]["multiple"], "ev": b["entry"]["ev"], "leverage": b["entry"]["leverage_close"],
            "equity": b["sponsor_equity"], "currency": b.get("currency"), "max_entry_multiple": result["max_entry"].get("multiple"),
            "hurdle": result["max_entry"].get("hurdle"), "warnings": b["warnings"], "at": _now()}


def list_deals() -> List[Dict[str, Any]]:
    with _conn() as c:
        return [_row(r) for r in c.execute("SELECT * FROM pe_deals ORDER BY updated_at DESC")]


def get(deal_id: int) -> Dict[str, Any]:
    with _conn() as c:
        r = c.execute("SELECT * FROM pe_deals WHERE id = ?", (deal_id,)).fetchone()
        if not r:
            raise LookupError("No such deal.")
        d = _row(r, full=True)
        d["log"] = [dict(x) for x in c.execute("SELECT at, author, kind, text FROM pe_deal_log WHERE deal_id = ? ORDER BY id DESC", (deal_id,))]
        return d


def save(owner: str, inputs: Dict[str, Any], summary: Optional[Dict[str, Any]], deal_id: Optional[int] = None,
         name: Optional[str] = None, stage: Optional[str] = None, sector: Optional[str] = None, notes: Optional[str] = None) -> Dict[str, Any]:
    """Create a deal, or update one (its inputs / results / stage / notes); stage changes are logged."""
    if stage is not None and stage not in STAGES:
        raise ValueError(f"Stage must be one of: {', '.join(STAGES)}.")
    now = _now()
    with _conn() as c:
        if deal_id is None:
            cur = c.execute("INSERT INTO pe_deals (name, symbol, sector, stage, owner, inputs, summary, notes, created_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            ((name or inputs.get("name") or "Untitled deal")[:120], inputs.get("symbol"), sector,
                             stage or STAGES[0], owner, json.dumps(inputs), json.dumps(summary) if summary else None, notes, now, now))
            deal_id = cur.lastrowid
            c.execute("INSERT INTO pe_deal_log (deal_id, at, author, kind, text) VALUES (?, ?, ?, 'created', ?)",
                      (deal_id, now, owner, f"Deal created at {stage or STAGES[0]}"))
        else:
            r = c.execute("SELECT stage FROM pe_deals WHERE id = ?", (deal_id,)).fetchone()
            if not r:
                raise LookupError("No such deal.")
            c.execute("UPDATE pe_deals SET name = COALESCE(?, name), sector = COALESCE(?, sector), stage = COALESCE(?, stage), "
                      "inputs = ?, summary = COALESCE(?, summary), notes = COALESCE(?, notes), updated_at = ? WHERE id = ?",
                      (name, sector, stage, json.dumps(inputs), json.dumps(summary) if summary else None, notes, now, deal_id))
            if stage and stage != r["stage"]:
                c.execute("INSERT INTO pe_deal_log (deal_id, at, author, kind, text) VALUES (?, ?, ?, 'stage', ?)",
                          (deal_id, now, owner, f"{r['stage']} → {stage}"))
    return get(deal_id)


def set_stage(owner: str, deal_id: int, stage: str) -> Dict[str, Any]:
    if stage not in STAGES:
        raise ValueError(f"Stage must be one of: {', '.join(STAGES)}.")
    with _conn() as c:
        r = c.execute("SELECT stage FROM pe_deals WHERE id = ?", (deal_id,)).fetchone()
        if not r:
            raise LookupError("No such deal.")
        if r["stage"] != stage:
            c.execute("UPDATE pe_deals SET stage = ?, updated_at = ? WHERE id = ?", (stage, _now(), deal_id))
            c.execute("INSERT INTO pe_deal_log (deal_id, at, author, kind, text) VALUES (?, ?, ?, 'stage', ?)",
                      (deal_id, _now(), owner, f"{r['stage']} → {stage}"))
    return get(deal_id)


def add_note(owner: str, deal_id: int, text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("The note is empty.")
    with _conn() as c:
        if not c.execute("SELECT 1 FROM pe_deals WHERE id = ?", (deal_id,)).fetchone():
            raise LookupError("No such deal.")
        c.execute("INSERT INTO pe_deal_log (deal_id, at, author, kind, text) VALUES (?, ?, ?, 'note', ?)", (deal_id, _now(), owner, text[:4000]))
        c.execute("UPDATE pe_deals SET updated_at = ? WHERE id = ?", (_now(), deal_id))
    return get(deal_id)


def delete(deal_id: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM pe_deal_log WHERE deal_id = ?", (deal_id,))
        if c.execute("DELETE FROM pe_deals WHERE id = ?", (deal_id,)).rowcount == 0:
            raise LookupError("No such deal.")
