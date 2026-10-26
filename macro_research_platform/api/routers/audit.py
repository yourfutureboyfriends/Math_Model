"""
Audit-trail endpoints: the decision log and point-in-time snapshots of the platform's state.

Endpoints
    GET  /api/v1/audit/decisions             recent decisions (newest first)
    POST /api/v1/audit/decisions             record a decision (rationale required) — identity from the token
    GET  /api/v1/audit/snapshots             saved point-in-time snapshots
    GET  /api/v1/audit/snapshots/{id}        one snapshot
    GET  /api/v1/audit/time-machine?at=ISO   the snapshot in force at a past moment

Guarantees
    * The decision log is append-only, enforced by database triggers (api/audit_store.py): an UPDATE or DELETE
      aborts, so corrections are new rows.
    * The log is kept per fund (each fund's own database).
    * Snapshots are taken by the scheduler in api/main.py (_build_pit_snapshot) and on demand.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from api.core.web import username as _request_user

router = APIRouter(tags=["audit"])


class DecisionIn(BaseModel):
    action: str
    rationale: str
    target: Optional[str] = None
    before_state: Optional[Any] = None
    after_state: Optional[Any] = None


@router.get("/api/v1/audit/decisions")
async def audit_decisions_list_v1(limit: int = 100):
    from api import audit_store
    return {"decisions": await asyncio.to_thread(audit_store.list_decisions, limit)}


@router.post("/api/v1/audit/decisions")
async def audit_decisions_add_v1(d: DecisionIn, request: Request):
    from api import audit_store
    user = _request_user(request)
    try:
        return await asyncio.to_thread(lambda: audit_store.add_decision(
            d.action, d.rationale, user, d.target, d.before_state, d.after_state))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/api/v1/audit/snapshots")
async def audit_snapshots_list_v1(limit: int = 200):
    from api import audit_store
    return {"snapshots": await asyncio.to_thread(audit_store.list_snapshots, limit)}


@router.get("/api/v1/audit/snapshots/{snap_id}")
async def audit_snapshot_get_v1(snap_id: int):
    from api import audit_store
    snap = await asyncio.to_thread(audit_store.get_snapshot, snap_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="snapshot not found")
    return snap


@router.get("/api/v1/audit/time-machine")
async def audit_time_machine_v1(at: str):
    """The system state as it was at (or just before) the given ISO timestamp."""
    from api import audit_store
    snap = await asyncio.to_thread(audit_store.get_snapshot_at, at)
    if snap is None:
        return {"available": False, "reason": "No snapshot at or before that time."}
    return {"available": True, **snap}
