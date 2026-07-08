"""
Portfolio positions store — SQLite persistence for held positions.

Pure persistence: create/read/update/delete position records across one or more
"books" (e.g. Macro, Equity L/S). Market values / P&L are computed at read time from
live prices in the API layer, not stored, so they never go stale in the DB.
"""
from __future__ import annotations

import os
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

_COLUMNS = ["symbol", "asset_class", "quantity", "avg_cost", "entry_date", "book", "strategy_bucket"]


def _db_path() -> str:
    from api.config import DATABASE_URL
    path = (DATABASE_URL or "sqlite:///macro_terminal.db").split("sqlite:///", 1)[-1]
    if not os.path.isabs(path):
        here = os.path.dirname(os.path.abspath(__file__))  # api/
        # Prefer an existing db next to the package or its parent.
        for base in (here, os.path.dirname(here)):
            candidate = os.path.join(base, path)
            if os.path.exists(candidate):
                return candidate
        return os.path.join(here, path)
    return path


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                asset_class TEXT DEFAULT 'Equity',
                quantity REAL NOT NULL,
                avg_cost REAL NOT NULL,
                entry_date TEXT,
                book TEXT DEFAULT 'Macro',
                strategy_bucket TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(data: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for c in _COLUMNS:
        if c in data and data[c] is not None:
            out[c] = data[c]
    if "symbol" in out:
        out["symbol"] = str(out["symbol"]).strip().upper()
    for num in ("quantity", "avg_cost"):
        if num in out:
            out[num] = float(out[num])
    return out


def list_positions(book: Optional[str] = None) -> List[Dict[str, Any]]:
    init_db()
    with _conn() as conn:
        if book and book.lower() not in ("firm", "all"):
            rows = conn.execute("SELECT * FROM positions WHERE book = ? ORDER BY id", (book,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM positions ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def add_position(data: Dict[str, Any]) -> Dict[str, Any]:
    init_db()
    d = _clean(data)
    if not d.get("symbol") or "quantity" not in d or "avg_cost" not in d:
        raise ValueError("symbol, quantity and avg_cost are required")
    d.setdefault("asset_class", "Equity")
    d.setdefault("book", "Macro")
    d.setdefault("entry_date", datetime.now(timezone.utc).date().isoformat())
    now = _now()
    cols = list(d.keys()) + ["created_at", "updated_at"]
    vals = list(d.values()) + [now, now]
    placeholders = ",".join("?" for _ in cols)
    with _conn() as conn:
        cur = conn.execute(f"INSERT INTO positions ({','.join(cols)}) VALUES ({placeholders})", vals)
        conn.commit()
        row = conn.execute("SELECT * FROM positions WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


def add_positions_bulk(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    added, errors = 0, []
    for i, item in enumerate(items):
        try:
            add_position(item)
            added += 1
        except Exception as e:
            errors.append({"row": i, "error": str(e)[:120]})
    return {"added": added, "errors": errors}


def update_position(pos_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    init_db()
    d = _clean(data)
    if not d:
        return get_position(pos_id)
    d["updated_at"] = _now()
    sets = ",".join(f"{k} = ?" for k in d)
    with _conn() as conn:
        conn.execute(f"UPDATE positions SET {sets} WHERE id = ?", list(d.values()) + [pos_id])
        conn.commit()
    return get_position(pos_id)


def get_position(pos_id: int) -> Optional[Dict[str, Any]]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM positions WHERE id = ?", (pos_id,)).fetchone()
    return dict(row) if row else None


def delete_position(pos_id: int) -> bool:
    init_db()
    with _conn() as conn:
        cur = conn.execute("DELETE FROM positions WHERE id = ?", (pos_id,))
        conn.commit()
        return cur.rowcount > 0


def list_books() -> List[str]:
    init_db()
    with _conn() as conn:
        rows = conn.execute("SELECT DISTINCT book FROM positions ORDER BY book").fetchall()
    return [r["book"] for r in rows if r["book"]]
