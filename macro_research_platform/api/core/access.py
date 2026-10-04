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
SENSITIVE_READ_PREFIXES = (
    "/api/v1/portfolio", "/api/v1/fund", "/api/v1/orders", "/api/v1/blotter",
    "/api/v1/risk/", "/api/v1/audit", "/api/portfolio",
)
# Market-level risk views that don't expose the book.
OPEN_RISK_READS = {"/api/v1/risk-parity-compare"}


def decode_token(token: str) -> Optional[dict]:
    try:
        from api.core.auth import token_blacklist
        if token in token_blacklist:
            return None
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None
    if not payload.get("sub"):
        return None
    return {"username": str(payload["sub"]), "role": str(payload.get("role") or "analyst")}


def _bearer(request: Request) -> Optional[str]:
    h = request.headers.get("Authorization") or ""
    return h[7:].strip() if h.lower().startswith("bearer ") else None


def needs_auth(method: str, path: str) -> bool:
    if not path.startswith("/api/"):
        return False
    if method in ("POST", "PUT", "PATCH", "DELETE"):
        return path not in PUBLIC_WRITES
    if path in OPEN_RISK_READS:
        return False
    return path.startswith(SENSITIVE_READ_PREFIXES)


async def auth_middleware(request: Request, call_next):
    token = _bearer(request)
    request.state.user = decode_token(token) if token else None
    if request.method != "OPTIONS" and needs_auth(request.method, request.url.path) and not request.state.user:
        return JSONResponse({"detail": "Authentication required"}, status_code=401,
                            headers={"WWW-Authenticate": "Bearer"})
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
