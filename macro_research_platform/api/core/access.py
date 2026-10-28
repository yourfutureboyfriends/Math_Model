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
from api.core.json_safe import SafeJSONResponse as JSONResponse  # NaN-safe
from jose import JWTError, jwt

from api.config import JWT_ALGORITHM, JWT_SECRET

PUBLIC_WRITES = {"/api/auth/login"}
# Usable while a password change is pending (everything else needing auth is blocked).
PASSWORD_CHANGE_ALLOWED = {"/api/auth/me", "/api/auth/change-password", "/api/auth/logout"}
# Writes a read-only (viewer) position may still make — each further checked against its capabilities.
VIEWER_WRITES = ("/api/auth/", "/api/v1/governance/budget", "/api/v1/governance/controls/reconcile",
                 "/api/v1/governance/incidents", "/api/v1/governance/data-sources/review", "/api/v1/governance/milestones")
# Usable while two-factor enrolment is required and pending.
MFA_ENROLL_ALLOWED = PASSWORD_CHANGE_ALLOWED | {"/api/auth/mfa", "/api/auth/mfa/setup", "/api/auth/mfa/enable"}
SENSITIVE_READ_PREFIXES = (
    "/api/v1/portfolio", "/api/v1/fund", "/api/v1/orders", "/api/v1/blotter",
    "/api/v1/risk/", "/api/v1/audit", "/api/portfolio", "/api/admin", "/api/v1/desk",
    "/api/v1/auto", "/api/v1/corporate-actions", "/api/v1/governance", "/api/v1/positions", "/api/v1/broker",
    # the firm's own information: the brief lists the fund's holdings, the sleeve compares targets with the book,
    # the decision log and IC pack are internal records (found open in the Oct-2026 backend audit)
    "/api/morning-brief", "/api/v1/model/sleeve", "/api/business/decision-log", "/api/business/ic-pack",
    # analyst research and the trading desk's assessments
    "/api/v1/pitches", "/api/v1/trading",
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
    from api.core import mfa
    return {"username": user["username"], "role": user["role"],
            "must_change_password": bool(user.get("must_change_password")),
            "mfa_enrollment_required": bool(mfa.required() and not user.get("totp_enabled")),
            "jti": payload.get("jti"), "exp": payload.get("exp")}


def _bearer(request: Request) -> Optional[str]:
    h = request.headers.get("Authorization") or ""
    return h[7:].strip() if h.lower().startswith("bearer ") else None


def needs_auth(method: str, path: str) -> bool:
    """Whether a request must carry a valid token.

    All writes need one (except the public login); reads need one for the firm's own data (SENSITIVE_READ_PREFIXES)
    and for the identity endpoints. Market and research reads stay public.

    Args:
        method: HTTP method.
        path: URL path.

    Returns:
        True when the request must be authenticated.
    """
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
    """Authenticate, pick the fund, and apply the person's position — for every request.

    Order: (1) decode the bearer token into request.state.user; (2) refuse unauthenticated, password-change-pending
    or two-factor-enrolment-pending requests where needs_auth() applies; (3) select the fund from the X-Fund header
    — signed-in members only, 404 for an unknown fund, 403 for a non-member; (4) replace the role with the one from
    the person's position in that fund and refuse writes from read-only positions (outside VIEWER_WRITES). The fund
    is held in a context variable for the duration of the request.
    """
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
        if user.get("mfa_enrollment_required") and path not in MFA_ENROLL_ALLOWED:
            return JSONResponse({"detail": "Two-factor sign-in is required: set it up first",
                                 "code": "mfa_enrollment_required"}, status_code=403)
    # Which fund this request works on: the X-Fund header from the fund switcher, for a signed-in member of that fund;
    # 'main' otherwise (anonymous requests never pick a fund).
    from api import funds
    fid = (request.headers.get("X-Fund") or "").strip().lower() or funds.MAIN
    if fid != funds.MAIN and request.state.user and path.startswith("/api/"):
        f = funds.get(fid)
        if not f:
            return JSONResponse({"detail": f"Unknown fund '{fid}'", "code": "unknown_fund"}, status_code=404)
        if not funds.can_open(request.state.user, f):
            return JSONResponse({"detail": f"You are not a member of fund '{f['name']}'", "code": "fund_forbidden"},
                                status_code=403)
    else:
        fid = funds.MAIN
    token_ctx = funds.CURRENT.set(fid)
    if request.state.user:                           # role and capabilities from the person's position in this fund
        from api import positions
        request.state.user = positions.apply_to_user(request.state.user)
        if (request.state.user.get("role") == "viewer" and request.method not in ("GET", "HEAD", "OPTIONS")
                and path.startswith("/api/") and not path.startswith(VIEWER_WRITES)):
            funds.CURRENT.reset(token_ctx)
            return JSONResponse({"detail": "Your position is read-only in this fund", "code": "read_only"}, status_code=403)
    try:
        return await call_next(request)
    finally:
        funds.CURRENT.reset(token_ctx)


def current_user(request: Request) -> Optional[dict]:
    """The verified identity attached to the request by auth_middleware, or None when unauthenticated."""
    return getattr(request.state, "user", None)


def require_roles(request: Request, roles: Iterable[str]) -> dict:
    """The verified user, if their role is allowed (admin always is); else 401/403."""
    user = current_user(request)
    if not user:
        raise HTTPException(401, "Authentication required")
    allowed = set(roles) | {"admin"}
    if user["role"] == "viewer":                     # a read-only position: reads open to members, never writes
        if request.method == "GET" and "analyst" in allowed:
            return user
        raise HTTPException(403, "Your position is read-only here")
    if user["role"] not in allowed:
        raise HTTPException(403, f"Role '{user['role']}' cannot do this (needs one of: {sorted(allowed)})")
    return user
