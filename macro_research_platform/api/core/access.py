"""
Request authentication & authorization.

Every request's `Authorization: Bearer <JWT>` is verified once by `auth_middleware` and
the identity stored on `request.state.user` ({"username", "role"}) — or None.

Policy (enforced by the middleware):
  * any state-changing request (POST/PUT/PATCH/DELETE) needs a valid token, except login;
  * reads of fund-sensitive data (positions, orders, blotter, fund, book risk, audit) need a
    valid token;
  * market / macro research reads stay open.
Endpoint-level role checks use `require_roles(request, {...})`.

The `X-User` header is no longer trusted for attribution: identity comes only from the
verified token.
"""
from __future__ import annotations

from typing import Iterable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from jose import JWTError, jwt

from api.config import JWT_ALGORITHM, JWT_SECRET

PUBLIC_WRITES = {"/api/auth/login"}
# Usable while a password change is pending (everything else needing auth is blocked).
PASSWORD_CHANGE_ALLOWED = {"/api/auth/me", "/api/auth/change-password", "/api/auth/logout"}
SENSITIVE_READ_PREFIXES = (
    "/api/v1/portfolio", "/api/v1/fund", "/api/v1/orders", "/api/v1/blotter",
    "/api/v1/risk/", "/api/v1/audit", "/api/portfolio", "/api/admin",
)
# Market-level risk views that don't expose the book.
OPEN_RISK_READS = {"/api/v1/risk-parity-compare"}


def decode_token(token: str) -> Optional[dict]:
    """Verified identity for a token, or None. Checks the signature/expiry AND the account:
    it must exist, be enabled, the token must post-date the last password change / role
    change, and its id must not be revoked. The role comes from the DB, so role changes
    apply immediately."""
    from api.core import accounts
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None
    username = payload.get("sub")
    if not username or accounts.is_revoked(payload.get("jti")):
        return None
    user = accounts.get_user(str(username))
    if not user or user.get("disabled"):
        return None
    changed = user.get("password_changed_at")
    if changed and float(payload.get("iat") or 0) < float(changed):
        return None
    return {"username": user["username"], "role": user["role"],
            "must_change_password": bool(user.get("must_change_password")),
            "jti": payload.get("jti"), "exp": payload.get("exp")}


def _bearer(request: Request) -> Optional[str]:
    h = request.headers.get("Authorization") or ""
    return h[7:].strip() if h.lower().startswith("bearer ") else None


def needs_auth(method: str, path: str) -> bool:
    if not path.startswith("/api/"):
        return False
    if path in ("/api/auth/me", "/api/auth/change-password"):
        return True
    if method in ("POST", "PUT", "PATCH", "DELETE"):
        return path not in PUBLIC_WRITES
    if path in OPEN_RISK_READS:
        return False
    return path.startswith(SENSITIVE_READ_PREFIXES)


async def auth_middleware(request: Request, call_next):
    token = _bearer(request)
    request.state.user = decode_token(token) if token else None
    path = request.url.path
    if request.method != "OPTIONS" and needs_auth(request.method, path):
        user = request.state.user
        if not user:
            return JSONResponse({"detail": "Authentication required"}, status_code=401,
                                headers={"WWW-Authenticate": "Bearer"})
        if user.get("must_change_password") and path not in PASSWORD_CHANGE_ALLOWED:
            return JSONResponse({"detail": "Password change required", "code": "password_change_required"},
                                status_code=403)
    return await call_next(request)


def current_user(request: Request) -> Optional[dict]:
    return getattr(request.state, "user", None)


def require_roles(request: Request, roles: Iterable[str]) -> dict:
    """The verified user, if their role is allowed (admin always is); else 401/403."""
    user = current_user(request)
    if not user:
        raise HTTPException(401, "Authentication required")
    allowed = set(roles) | {"admin"}
    if user["role"] not in allowed:
        raise HTTPException(403, f"Role '{user['role']}' cannot do this (needs one of: {sorted(allowed)})")
    return user
