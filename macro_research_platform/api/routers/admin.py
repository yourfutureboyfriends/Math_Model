"""
User administration (admin role only). Every change is written to the audit trail.

Temporary passwords are returned exactly once (on create / reset) and must be changed by
the user at first sign-in.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from api.core import accounts
from api.core.access import require_roles

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def _thread(fn, *a, **kw):
    return await asyncio.to_thread(fn, *a, **kw)


def _audit(action: str, rationale: str, user: str, target: str, after=None) -> None:
    try:
        from api import audit_store
        audit_store.add_decision(action, rationale, user=user, target=target, after_state=after)
    except Exception:
        pass


class NewUserIn(BaseModel):
    """A new account: username, role and display name (a temporary password is generated)."""
    username: str
    role: str
    display_name: Optional[str] = None


class UserUpdateIn(BaseModel):
    """Changes to an account: role and / or disabled flag."""
    role: Optional[str] = None
    disabled: Optional[bool] = None


@router.get("/users")
async def list_users(request: Request):
    """All accounts with role and status (administrators)."""
    require_roles(request, {"admin"})
    return {"users": await _thread(accounts.list_users), "roles": list(accounts.ROLES)}


@router.post("/users")
async def create_user(body: NewUserIn, request: Request):
    """Create an account; returns the temporary password once (it must be changed at first sign-in)."""
    admin = require_roles(request, {"admin"})
    username = body.username.strip().lower()
    try:
        temp = await _thread(accounts.create_user, username, body.role, (body.display_name or "").strip())
    except ValueError as e:
        raise HTTPException(400, str(e))
    await _thread(_audit, "user_created", f"created {username} ({body.role})", admin["username"],
                  f"user:{username}", {"role": body.role})
    return {"success": True, "username": username, "temporary_password": temp,
            "note": "Shown once. The user must change it at first sign-in."}


@router.put("/users/{username}")
async def update_user(username: str, body: UserUpdateIn, request: Request):
    """Change an account's role or disable it (the last administrator cannot be removed or disabled; you cannot disable
    yourself).
    """
    admin = require_roles(request, {"admin"})
    try:
        user = await _thread(accounts.update_user, username, role=body.role, disabled=body.disabled,
                             acting_user=admin["username"])
    except KeyError:
        raise HTTPException(404, "user not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    await _thread(_audit, "user_updated", f"{username}: {changes}", admin["username"],
                  f"user:{username}", changes)
    return {"success": True, "user": user}


@router.post("/users/{username}/reset-password")
async def reset_password(username: str, request: Request):
    """Reset an account's password to a temporary one, returned once."""
    admin = require_roles(request, {"admin"})
    try:
        temp = await _thread(accounts.reset_password, username)
    except KeyError:
        raise HTTPException(404, "user not found")
    await _thread(_audit, "password_reset", f"reset password for {username}", admin["username"],
                  f"user:{username}")
    return {"success": True, "username": username, "temporary_password": temp,
            "note": "Shown once. Existing sessions are signed out; the user must change it at sign-in."}


@router.post("/users/{username}/unlock")
async def unlock_user(username: str, request: Request):
    """Clear a lockout after too many failed sign-ins."""
    admin = require_roles(request, {"admin"})
    if not await _thread(accounts.unlock, username):
        raise HTTPException(404, "user not found")
    await _thread(_audit, "user_unlocked", f"cleared lockout for {username}", admin["username"],
                  f"user:{username}")
    return {"success": True}
