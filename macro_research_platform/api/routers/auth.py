"""
Authentication endpoints: sign in, sign out, change password, policy status and "who am I".

Endpoints
    POST /api/auth/login            username + password (+ one-time code when two-factor is on) → signed JWT
    POST /api/auth/logout           revoke the presented token (persisted; survives restarts)
    POST /api/auth/change-password  own password change; other sessions are signed out, a fresh token returned
    GET  /api/auth/status           public: whether seeded demo accounts still work, password policy, lockout rules
    GET  /api/auth/me               the verified identity behind the request's token

Security model
    * Passwords are bcrypt-hashed (api/core/auth.py); the policy and lockout live in api/core/accounts.py.
    * A wrong password or a wrong two-factor code counts as a failed attempt; MAX_FAILED_ATTEMPTS locks the account
      for LOCKOUT_SECONDS. Counters reset only after every factor passes (api/core/accounts.check_login).
    * Tokens carry a unique id (jti) and issue time; a token is rejected after logout (revocation list), after a
      password change, or when the account is disabled (api/core/access.decode_token).
    * Login accepts JSON or form-encoded bodies (the OAuth2 password form used by the UI).

Errors
    400 missing fields · 401 bad credentials (`mfa_required: true` when only the code is missing or wrong)
    403 account disabled · 429 locked after too many failures
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from api.core.json_safe import SafeJSONResponse as JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])


@router.post("/api/auth/login")
async def login(request: Request):
    """Verify username/password against the users table (bcrypt) and issue a signed JWT
    carrying the user and role. Invalid credentials return HTTP 401.

    (This used to accept only demo/demo and answer every other attempt with HTTP 200
    {"success": false}, which the UI treated as a successful login — any credentials got in.)
    """
    from urllib.parse import parse_qs
    from api.config import ROLE_PERMISSIONS, ACCESS_TOKEN_EXPIRE_MINUTES

    content_type = request.headers.get("content-type", "").lower()
    body = await request.body()
    username = password = otp = None
    try:
        if "application/json" in content_type:
            data = json.loads(body or b"{}")
            username, password, otp = data.get("username"), data.get("password"), data.get("otp")
        else:
            form = parse_qs(body.decode("utf-8"))
            username, password = form.get("username", [None])[0], form.get("password", [None])[0]
            otp = form.get("otp", [None])[0]
    except (ValueError, UnicodeDecodeError):
        pass
    if not username or not password:
        return JSONResponse({"success": False, "error": "Username and password required"}, status_code=400)

    from api.core import accounts, mfa
    try:
        user = await asyncio.to_thread(accounts.check_login, username.strip(), password, otp)
    except accounts.LoginError as e:
        logger.warning(f"[AUTH] failed login for '{username[:64]}': {e.message}")
        return JSONResponse({"success": False, "error": e.message, "mfa_required": e.mfa_required},
                            status_code=e.status)

    role = user["role"]
    token = accounts.issue_token(user)
    perms = ROLE_PERMISSIONS.get(role, [])
    try:
        from api import audit_store
        await asyncio.to_thread(lambda: audit_store.add_decision(
            "login", f"{user['username']} signed in", user=user["username"], target="auth"))
    except Exception:
        pass
    return {
        "success": True, "access_token": token, "token": token, "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "role": role, "display_name": user["display_name"], "permissions": perms,
        "must_change_password": bool(user.get("must_change_password")),
        "mfa_enrollment_required": bool(mfa.required() and not user.get("totp_enabled")),
        "user": {"username": user["username"], "role": role,
                 "display_name": user["display_name"], "permissions": perms},
    }


@router.post("/api/auth/logout")
async def logout(request: Request):
    """Revoke the presented token for the rest of its lifetime (persisted, survives restarts)."""
    from api.core.access import current_user
    from api.core import accounts
    u = current_user(request)
    if u:
        await asyncio.to_thread(accounts.revoke, u.get("jti"), u.get("exp"))
    return {"success": True, "message": "Logged out successfully"}


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


@router.post("/api/auth/change-password")
async def change_password(body: ChangePasswordIn, request: Request):
    """Change your own password (policy-checked). All your other sessions are signed out;
    a fresh token is returned for this one."""
    from api.core.access import current_user
    from api.core import accounts
    from api.core.auth import verify_password
    u = current_user(request)
    if not u:
        raise HTTPException(401, "Not authenticated")
    row = await asyncio.to_thread(accounts.get_user, u["username"])
    if not row or not verify_password(body.current_password, row["hashed_password"]):
        raise HTTPException(400, "Current password is incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(400, "New password must differ from the current one")
    problems = accounts.password_problems(body.new_password, u["username"])
    if problems:
        raise HTTPException(400, {"message": "Password does not meet the policy", "problems": problems})
    await asyncio.to_thread(accounts.set_password, u["username"], body.new_password)
    await asyncio.to_thread(accounts.revoke, u.get("jti"), u.get("exp"))
    try:
        from api import audit_store
        await asyncio.to_thread(lambda: audit_store.add_decision(
            "password_changed", f"{u['username']} changed their password", user=u["username"], target="auth"))
    except Exception:
        pass
    fresh = await asyncio.to_thread(accounts.get_user, u["username"])
    return {"success": True, "access_token": accounts.issue_token(fresh), "must_change_password": False}


@router.get("/api/auth/status")
async def auth_status():
    """Public: whether the seeded demo credentials still work (the login screen only shows
    them in that case) and the password policy."""
    from api.core import accounts
    from api.config import ENVIRONMENT
    still_default = await asyncio.to_thread(accounts.default_credential_accounts)
    return {"default_credentials_active": bool(still_default),
            # Which accounts: development only (the login screen lists just those), never
            # disclosed by a production server.
            "default_credential_accounts": still_default if ENVIRONMENT == "development" else None,
            "password_policy": {"min_length": accounts.MIN_PASSWORD_LENGTH,
                                "rules": ["at least 3 of: lowercase, uppercase, digit, symbol",
                                          "must not contain the username", "not a common/default password"]},
            "lockout": {"max_failed_attempts": accounts.MAX_FAILED_ATTEMPTS,
                        "lockout_minutes": accounts.LOCKOUT_SECONDS // 60}}


@router.get("/api/auth/me")
async def auth_me(request: Request):
    """The verified identity behind the request's token (401 if none)."""
    from api.core.access import current_user
    from api.config import ROLE_PERMISSIONS
    u = current_user(request)
    if not u:
        raise HTTPException(401, "Not authenticated")
    return {**u, "permissions": ROLE_PERMISSIONS.get(u["role"], [])}
