"""
Audit store — decision log + point-in-time system snapshots (Phase 8).

Two tables in the same SQLite DB; decision_log is append-only (UPDATE/DELETE triggers abort):
- decision_log: every material action (override, approval, param change) with user,
  timestamp, before/after state and a required rationale.
- pit_snapshots: periodic snapshots of key system state (regime, signals, portfolio risk)
  so a PM can answer "what did the system say at time T" for post-trade review / audit.
"""
from __future__ import annotations

import json as _json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from api.portfolio_store import _conn  # reuse the same DB connection/path

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_audit_db() -> None:
    """Create the decision log and point-in-time snapshot tables in the current fund's database if missing."""
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS decision_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                user TEXT,
                action TEXT NOT NULL,
                target TEXT,
                before_state TEXT,
                after_state TEXT,
                rationale TEXT NOT NULL
            )
            """
        )
        # Append-only, enforced by the database: any UPDATE or DELETE on the decision log aborts,
        # whatever code path (or sqlite shell) attempts it. Corrections are new rows.
        conn.execute(
            "CREATE TRIGGER IF NOT EXISTS decision_log_no_update BEFORE UPDATE ON decision_log "
            "BEGIN SELECT RAISE(ABORT, 'decision_log is append-only'); END")
        conn.execute(
            "CREATE TRIGGER IF NOT EXISTS decision_log_no_delete BEFORE DELETE ON decision_log "
            "BEGIN SELECT RAISE(ABORT, 'decision_log is append-only'); END")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pit_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                label TEXT,
                state TEXT NOT NULL
            )
            """
        )
        conn.commit()


# ── Decision log ─────────────────────────────────────────────────────────────
def add_decision(action: str, rationale: str, user: str = "admin",
                 target: Optional[str] = None,
                 before_state: Any = None, after_state: Any = None) -> Dict[str, Any]:
    """Append a decision to the audit log (append-only).

    Args:
        action: What was done (e.g. ``portfolio_update``).
        rationale: Why — required for every entry.
        user: Who did it.
        target: What it was done to (e.g. ``position:12``).
        before_state: State before the change (JSON-serialisable).
        after_state: State after the change.

    Returns:
        The stored entry.

    Raises:
        ValueError: action or rationale is empty.
    """
    if not action:
        raise ValueError("action is required")
    if not rationale:
        raise ValueError("rationale is required for every logged decision")
    init_audit_db()
    row = {
        "ts": _now(), "user": user, "action": action, "target": target,
        "before_state": _json.dumps(before_state) if before_state is not None else None,
        "after_state": _json.dumps(after_state) if after_state is not None else None,
        "rationale": rationale,
    }
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO decision_log (ts,user,action,target,before_state,after_state,rationale) "
            "VALUES (?,?,?,?,?,?,?)",
            (row["ts"], row["user"], row["action"], row["target"],
             row["before_state"], row["after_state"], row["rationale"]),
        )
        conn.commit()
        r = conn.execute("SELECT * FROM decision_log WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _decode_decision(dict(r))


def list_decisions(limit: int = 100) -> List[Dict[str, Any]]:
    """The latest `limit` audit-log entries, newest first."""
    init_audit_db()
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM decision_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [_decode_decision(dict(r)) for r in rows]


def _decode_decision(d: Dict[str, Any]) -> Dict[str, Any]:
    for k in ("before_state", "after_state"):
        if d.get(k):
            try:
                d[k] = _json.loads(d[k])
            except Exception:
                pass
    return d


# ── Point-in-time snapshots ──────────────────────────────────────────────────
def add_snapshot(state: Dict[str, Any], label: Optional[str] = None) -> int:
    """Store a point-in-time snapshot of platform state (the table keeps about the last 2,000).

    Returns:
        The snapshot id.
    """
    init_audit_db()
    with _conn() as conn:
        cur = conn.execute("INSERT INTO pit_snapshots (ts,label,state) VALUES (?,?,?)",
                           (_now(), label, _json.dumps(state, default=str)))
        conn.commit()
        # Keep the table bounded (retain most recent ~2000 snapshots).
        conn.execute("DELETE FROM pit_snapshots WHERE id < (SELECT MAX(id)-2000 FROM pit_snapshots)")
        conn.commit()
        return cur.lastrowid


def list_snapshots(limit: int = 200) -> List[Dict[str, Any]]:
    """Snapshot ids, times and labels, newest first (without the state)."""
    init_audit_db()
    with _conn() as conn:
        rows = conn.execute("SELECT id, ts, label FROM pit_snapshots ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_snapshot(snap_id: int) -> Optional[Dict[str, Any]]:
    """One snapshot with its decoded state, or None."""
    init_audit_db()
    with _conn() as conn:
        r = conn.execute("SELECT * FROM pit_snapshots WHERE id = ?", (snap_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    try:
        d["state"] = _json.loads(d["state"])
    except Exception:
        pass
    return d


def get_snapshot_at(iso_ts: str) -> Optional[Dict[str, Any]]:
    """The most recent snapshot at or before the given ISO timestamp (time machine)."""
    init_audit_db()
    with _conn() as conn:
        r = conn.execute("SELECT * FROM pit_snapshots WHERE ts <= ? ORDER BY ts DESC LIMIT 1", (iso_ts,)).fetchone()
    if not r:
        return None
    d = dict(r)
    try:
        d["state"] = _json.loads(d["state"])
    except Exception:
        pass
    return d
