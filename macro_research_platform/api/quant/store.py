"""
Quant Lab persistence (application DB, own tables):
  * quant_strategies  — saved user strategies (spec JSON)
  * quant_runs        — every distinct spec a user has backtested within a strategy's lineage;
                        the count is the number of trials the Deflated Sharpe corrects for
  * quant_deployments — strategies paper-traded by the Quant Trader (frozen spec + start date)
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

_ready = False


def _conn() -> sqlite3.Connection:
    from api.core.app_db import app_db_path
    c = sqlite3.connect(app_db_path(), timeout=10)
    c.row_factory = sqlite3.Row
    return c


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init() -> None:
    global _ready
    if _ready:
        return
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS quant_strategies (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, owner TEXT NOT NULL,
                spec TEXT NOT NULL, template TEXT, created_at TEXT, updated_at TEXT);
            CREATE TABLE IF NOT EXISTS quant_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, strategy_id INTEGER,
                spec_hash TEXT NOT NULL, sharpe REAL, ts TEXT);
            CREATE INDEX IF NOT EXISTS ix_quant_runs ON quant_runs(owner, strategy_id, spec_hash);
            CREATE TABLE IF NOT EXISTS quant_deployments (
                id INTEGER PRIMARY KEY AUTOINCREMENT, strategy_id INTEGER, name TEXT NOT NULL,
                owner TEXT NOT NULL, spec TEXT NOT NULL, deployed_at TEXT NOT NULL, capital REAL NOT NULL,
                active INTEGER NOT NULL DEFAULT 1, backtest TEXT, created_at TEXT, stopped_at TEXT);
        """)
    _ready = True


def _row(r: sqlite3.Row) -> Dict[str, Any]:
    d = dict(r)
    for k in ("spec", "backtest"):
        if d.get(k):
            d[k] = json.loads(d[k])
    return d


# ── Strategies ───────────────────────────────────────────────────────────────
def list_strategies(owner: Optional[str] = None) -> List[Dict[str, Any]]:
    init()
    with _conn() as c:
        rows = (c.execute("SELECT * FROM quant_strategies WHERE owner = ? ORDER BY updated_at DESC", (owner,))
                if owner else c.execute("SELECT * FROM quant_strategies ORDER BY updated_at DESC")).fetchall()
    return [_row(r) for r in rows]


def get_strategy(sid: int) -> Optional[Dict[str, Any]]:
    init()
    with _conn() as c:
        r = c.execute("SELECT * FROM quant_strategies WHERE id = ?", (sid,)).fetchone()
    return _row(r) if r else None


def save_strategy(owner: str, spec: Dict[str, Any], sid: Optional[int] = None, template: Optional[str] = None) -> Dict[str, Any]:
    init()
    now = _now()
    with _conn() as c:
        if sid is None:
            cur = c.execute("INSERT INTO quant_strategies (name, owner, spec, template, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                            (spec["name"], owner, json.dumps(spec), template, now, now))
            sid = cur.lastrowid
        else:
            c.execute("UPDATE quant_strategies SET name = ?, spec = ?, updated_at = ? WHERE id = ?",
                      (spec["name"], json.dumps(spec), now, sid))
    return get_strategy(sid)


def delete_strategy(sid: int) -> None:
    init()
    with _conn() as c:
        c.execute("DELETE FROM quant_strategies WHERE id = ?", (sid,))


# ── Trials ───────────────────────────────────────────────────────────────────
def record_run(owner: str, strategy_id: Optional[int], spec_hash: str, sharpe: Optional[float]) -> None:
    init()
    with _conn() as c:
        q = "SELECT 1 FROM quant_runs WHERE owner = ? AND spec_hash = ? AND " + \
            ("strategy_id = ?" if strategy_id is not None else "strategy_id IS NULL")
        args = (owner, spec_hash, strategy_id) if strategy_id is not None else (owner, spec_hash)
        if not c.execute(q, args).fetchone():
            c.execute("INSERT INTO quant_runs (owner, strategy_id, spec_hash, sharpe, ts) VALUES (?,?,?,?,?)",
                      (owner, strategy_id, spec_hash, sharpe, _now()))


def trials(owner: str, strategy_id: Optional[int], spec_hash: str) -> Tuple[int, List[float]]:
    """Distinct variants tried in this lineage, counting the current one."""
    init()
    with _conn() as c:
        if strategy_id is not None:
            rows = c.execute("SELECT spec_hash, sharpe FROM quant_runs WHERE owner = ? AND strategy_id = ?", (owner, strategy_id)).fetchall()
        else:
            rows = c.execute("SELECT spec_hash, sharpe FROM quant_runs WHERE owner = ? AND strategy_id IS NULL", (owner,)).fetchall()
    seen = {r["spec_hash"]: r["sharpe"] for r in rows}
    n = len(seen) + (0 if spec_hash in seen else 1)
    return n, [s for s in seen.values() if s is not None]


# ── Deployments (Quant Trader) ───────────────────────────────────────────────
def deploy(owner: str, name: str, spec: Dict[str, Any], deployed_at: str, capital: float,
           strategy_id: Optional[int], backtest_summary: Dict[str, Any]) -> Dict[str, Any]:
    init()
    with _conn() as c:
        cur = c.execute("INSERT INTO quant_deployments (strategy_id, name, owner, spec, deployed_at, capital, active, backtest, created_at)"
                        " VALUES (?,?,?,?,?,?,1,?,?)",
                        (strategy_id, name, owner, json.dumps(spec), deployed_at, capital, json.dumps(backtest_summary), _now()))
        did = cur.lastrowid
    return get_deployment(did)


def get_deployment(did: int) -> Optional[Dict[str, Any]]:
    init()
    with _conn() as c:
        r = c.execute("SELECT * FROM quant_deployments WHERE id = ?", (did,)).fetchone()
    return _row(r) if r else None


def list_deployments(active_only: bool = True) -> List[Dict[str, Any]]:
    init()
    with _conn() as c:
        rows = c.execute("SELECT * FROM quant_deployments" + (" WHERE active = 1" if active_only else "") +
                         " ORDER BY id").fetchall()
    return [_row(r) for r in rows]


def stop_deployment(did: int) -> None:
    init()
    with _conn() as c:
        c.execute("UPDATE quant_deployments SET active = 0, stopped_at = ? WHERE id = ?", (_now(), did))
