"""
Trade blotter store — fills, and the order fields on the trade-idea workflow.

`book_fill` updates the positions table AND records the trade in ONE transaction, using
average-cost accounting (api/calculations/blotter.py), so positions and the blotter can't
disagree. Multiple position rows for the same (book, symbol) are consolidated into one.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from api.calculations.blotter import apply_fill
from api.portfolio_store import _conn, init_db as _init_positions, init_ideas_db

_ORDER_COLUMNS = {"side": "TEXT", "quantity": "REAL", "approved_by": "TEXT",
                  "approval_note": "TEXT", "executed_trade_id": "INTEGER"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_init_lock = __import__("threading").Lock()
_initialized: set = set()          # database paths already migrated in this process


def init_db() -> None:
    """Idempotent and safe under concurrency: the check-then-ALTER migration used to race
    when two requests initialised at once ("duplicate column name")."""
    from api.portfolio_store import _db_path
    key = str(_db_path())
    if key in _initialized:
        return
    with _init_lock:
        if key in _initialized:
            return
        _init_db_locked()
        _initialized.add(key)


def _init_db_locked() -> None:
    import sqlite3 as _sqlite3
    _init_positions()
    init_ideas_db()
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                book TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                commission REAL DEFAULT 0,
                realized_pnl REAL DEFAULT 0,
                position_after REAL,
                avg_cost_after REAL,
                idea_id INTEGER,
                source TEXT,
                user TEXT
            )
            """
        )
        existing = {r["name"] for r in conn.execute("PRAGMA table_info(pm_trade_ideas)")}
        for col, typ in _ORDER_COLUMNS.items():
            if col not in existing:
                try:
                    conn.execute(f"ALTER TABLE pm_trade_ideas ADD COLUMN {col} {typ}")
                except _sqlite3.OperationalError as e:   # another process added it first
                    if "duplicate column" not in str(e):
                        raise
        conn.commit()


def book_fill(book: str, symbol: str, signed_qty: float, price: float, commission: float,
              user: str, source: str = "simulated", idea_id: Optional[int] = None,
              asset_class: Optional[str] = None) -> Dict[str, Any]:
    """Apply a fill to the book and record it. Returns the trade row."""
    init_db()
    symbol = symbol.strip().upper()
    side = "BUY" if signed_qty > 0 else "SELL"
    with _conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute("SELECT * FROM positions WHERE book = ? AND UPPER(symbol) = ?",
                            (book, symbol)).fetchall()
        qty = sum(float(r["quantity"]) for r in rows)
        avg = (sum(float(r["quantity"]) * float(r["avg_cost"]) for r in rows) / qty) if qty else 0.0
        new_qty, new_avg, realized = apply_fill(qty, avg, signed_qty, price)

        keep = dict(rows[0]) if rows else {}
        conn.execute("DELETE FROM positions WHERE book = ? AND UPPER(symbol) = ?", (book, symbol))
        if abs(new_qty) > 1e-12:
            conn.execute(
                "INSERT INTO positions (symbol, asset_class, quantity, avg_cost, entry_date, book, "
                "strategy_bucket, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (symbol, keep.get("asset_class") or asset_class or "Equity", new_qty, round(new_avg, 6),
                 keep.get("entry_date") or datetime.now().date().isoformat(), book,
                 keep.get("strategy_bucket"), keep.get("created_at") or _now(), _now()))
        cur = conn.execute(
            "INSERT INTO trades (ts, book, symbol, side, quantity, price, commission, realized_pnl, "
            "position_after, avg_cost_after, idea_id, source, user) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (_now(), book, symbol, side, abs(signed_qty), price, commission, round(realized, 2),
             new_qty, round(new_avg, 6), idea_id, source, user))
        trade_id = cur.lastrowid
        if idea_id is not None:
            conn.execute("UPDATE pm_trade_ideas SET executed_trade_id = ? WHERE id = ?", (trade_id, idea_id))
        conn.commit()
        row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
    return dict(row)


def list_trades(limit: Optional[int] = None, book: Optional[str] = None) -> List[Dict[str, Any]]:
    init_db()
    q, args = "SELECT * FROM trades", []
    if book:
        q += " WHERE book = ?"
        args.append(book)
    q += " ORDER BY id DESC"
    if limit:
        q += f" LIMIT {int(limit)}"
    with _conn() as conn:
        return [dict(r) for r in conn.execute(q, args)]


def set_order_fields(idea_id: int, **fields) -> None:
    init_db()
    cols = {k: v for k, v in fields.items() if k in _ORDER_COLUMNS}
    if not cols:
        return
    with _conn() as conn:
        conn.execute(f"UPDATE pm_trade_ideas SET {', '.join(f'{k} = ?' for k in cols)} WHERE id = ?",
                     [*cols.values(), idea_id])
        conn.commit()


def get_idea(idea_id: int) -> Optional[Dict[str, Any]]:
    init_db()
    with _conn() as conn:
        r = conn.execute("SELECT * FROM pm_trade_ideas WHERE id = ?", (idea_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    try:
        d["state_history"] = json.loads(d.get("state_history") or "[]")
    except ValueError:
        d["state_history"] = []
    return d
