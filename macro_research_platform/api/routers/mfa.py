"""Two-factor sign-in (api/core/mfa.py): enrol with an authenticator app, recovery codes, admin reset and policy."""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["auth"])


def _me(request: Request) -> Dict[str, Any]:
    from api.core.access import current_user
    u = current_user(request)
    if not u:
        raise HTTPException(401, "Authentication required")
    return u


def _audit(user: str, action: str, text: str, target: str) -> None:
    try:
        from api import audit_store
        audit_store.add_decision(action, text, user=user, target=target)
    except Exception:                                                          # noqa: BLE001
        pass


class CodeIn(BaseModel):
    code: str = Field(..., min_length=6, max_length=20)


class RequiredIn(BaseModel):
    required: bool


@router.get("/api/auth/mfa")
async def mfa_status(request: Request):
    from api.core import mfa
    return await asyncio.to_thread(mfa.status, _me(request)["username"])


@router.post("/api/auth/mfa/setup")
async def mfa_setup(request: Request):
    """A new authenticator secret (shown once) — confirmed by entering a code from the app."""
    from api.core import mfa
    u = _me(request)
    if await asyncio.to_thread(mfa.enabled, u["username"]):
        raise HTTPException(409, "two-factor is already on — turn it off first to move it to a new device")
    return await asyncio.to_thread(mfa.begin_setup, u["username"])


@router.post("/api/auth/mfa/enable")
async def mfa_enable(body: CodeIn, request: Request):
    from api.core import mfa
    u = _me(request)
    try:
        r = await asyncio.to_thread(mfa.confirm_setup, u["username"], body.code)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await asyncio.to_thread(_audit, u["username"], "mfa_enabled", f"{u['username']} turned on two-factor sign-in", "auth")
    return r


@router.post("/api/auth/mfa/disable")
async def mfa_disable(body: CodeIn, request: Request):
    from api.core import mfa
    u = _me(request)
    if await asyncio.to_thread(mfa.required):
        raise HTTPException(403, "two-factor is required for every account here — an administrator can reset it "
                                 "if you need to move it to a new device")
    if not await asyncio.to_thread(mfa.verify, u["username"], body.code):
        raise HTTPException(400, "invalid or already used code")
    await asyncio.to_thread(mfa.disable, u["username"])
    await asyncio.to_thread(_audit, u["username"], "mfa_disabled", f"{u['username']} turned off two-factor sign-in", "auth")
    return {"enabled": False}


@router.post("/api/admin/users/{username}/mfa/reset")
async def mfa_reset(username: str, request: Request):
    """Lost device: remove a user's two-factor (they enrol again at next sign-in if it is required)."""
    from api.core import mfa
    from api.core.access import require_roles
    admin = require_roles(request, set())
    await asyncio.to_thread(mfa.disable, username)
    await asyncio.to_thread(_audit, admin["username"], "mfa_reset", f"Two-factor reset for {username}", f"user:{username}")
    return {"username": username, "enabled": False}


@router.get("/api/admin/security/mfa")
async def mfa_policy(request: Request):
    from api.core import accounts, mfa
    from api.core.access import require_roles
    require_roles(request, set())
    users = await asyncio.to_thread(accounts.list_users)
    on = {u["username"]: await asyncio.to_thread(mfa.enabled, u["username"]) for u in users}
    return {"required": await asyncio.to_thread(mfa.required), "users": on}


@router.put("/api/admin/security/mfa")
async def mfa_policy_set(body: RequiredIn, request: Request):
    from api.core import mfa
    from api.core.access import require_roles
    admin = require_roles(request, set())
    await asyncio.to_thread(mfa.set_required, body.required)
    await asyncio.to_thread(_audit, admin["username"], "mfa_policy",
                            f"Two-factor sign-in {'required for every account' if body.required else 'optional'}", "auth")
    return {"required": body.required}
