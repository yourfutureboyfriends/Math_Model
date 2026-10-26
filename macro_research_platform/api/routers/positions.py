"""Positions and tiers per fund (api/positions.py): the fund's organisation, who holds what, and what each can do."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from api.core import web

router = APIRouter(tags=["positions"])


def _me(request: Request) -> Dict[str, Any]:
    return web.user(request, None)

async def _t(fn, *a):
    return await web.run(fn, *a)

class PositionIn(BaseModel):
    key: str = Field(..., max_length=40)
    title: str = Field(..., max_length=80)
    tier: int = Field(..., ge=1, le=4)
    base_role: str = Field(..., pattern="^(pm|risk|analyst|quant|viewer)$")
    capabilities: List[str] = []
    panels: List[str] = []
    description: str = Field("", max_length=500)
    seats: int = Field(1, ge=1, le=200)


class AssignIn(BaseModel):
    username: str = Field(..., max_length=32)
    position_key: Optional[str] = Field(None, max_length=40)


@router.get("/api/v1/positions/me")
async def positions_me(request: Request):
    """Your position, tier and capabilities in the current fund."""
    from api import positions
    return positions.me(_me(request))


@router.get("/api/v1/positions")
async def positions_list(request: Request):
    from api import positions
    u = _me(request)
    return {"positions": await _t(positions.list_positions), "tiers": positions.TIERS, "capabilities": positions.CAPABILITIES,
            "base_roles": positions.BASE_ROLES, "templates": list(positions.TEMPLATES),
            "can_manage": "manage_positions" in positions.capabilities_for(u)}


@router.get("/api/v1/positions/people")
async def positions_people(request: Request):
    """Accounts that can be given a position (for the fund's managers)."""
    from api import positions
    from api.core import accounts
    positions.require(request, "manage_positions")
    users = await asyncio.to_thread(accounts.list_users)
    return {"people": [{"username": x["username"], "display_name": x.get("display_name"), "role": x.get("role"),
                        "disabled": bool(x.get("disabled"))} for x in users]}


@router.post("/api/v1/positions")
async def positions_save(body: PositionIn, request: Request):
    from api import positions
    u = positions.require(request, "manage_positions")
    return await _t(positions.upsert_position, body.model_dump(), u["username"])


@router.delete("/api/v1/positions/{key}")
async def positions_delete(key: str, request: Request):
    from api import positions
    u = positions.require(request, "manage_positions")
    await _t(positions.delete_position, key, u["username"])
    return {"deleted": key}


@router.post("/api/v1/positions/assign")
async def positions_assign(body: AssignIn, request: Request):
    from api import positions
    from api.core import accounts
    u = positions.require(request, "manage_positions")
    if not await asyncio.to_thread(accounts.get_user, body.username):
        raise HTTPException(404, "no such account")
    if body.username == u["username"] and u.get("platform_role", u.get("role")) != "admin":
        raise HTTPException(403, "you cannot change your own position — ask another manager")
    return {"position": await _t(positions.assign, body.username, body.position_key, u["username"])}


@router.post("/api/v1/positions/templates/{template}")
async def positions_seed(template: str, request: Request):
    from api import positions
    positions.require(request, "manage_positions")
    if template not in positions.TEMPLATES:
        raise HTTPException(404, "unknown template")
    return {"added": await _t(positions.seed, template)}
