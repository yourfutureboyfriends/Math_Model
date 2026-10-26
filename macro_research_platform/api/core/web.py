"""
Shared helpers for API routers — one way to do the common things:

  user(request, roles)      the signed-in user, if their role is allowed (admin always is); 401 / 403 otherwise
  require(request, cap)     the signed-in user, if their position (or role) in the current fund grants the capability
  run(fn, *args)            run blocking work off the event loop, mapping errors to HTTP status codes:
                              LookupError → 404, PermissionError → 403, ValueError → 400, timeout → 504
  audit(user, action, ...)  append to the fund's audit log; never fails the request

Routers keep their own request/response models; these cover identity, errors and the audit trail.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Iterable, Optional

from fastapi import HTTPException, Request

MEMBER_ROLES = ("pm", "analyst", "risk", "quant")


def user(request: Request, roles: Optional[Iterable[str]] = MEMBER_ROLES) -> Dict[str, Any]:
    """The signed-in user, if their role is in `roles` (None: any signed-in user). Admin always passes."""
    from api.core.access import current_user, require_roles
    if roles is None:
        u = current_user(request)
        if not u:
            raise HTTPException(401, "Authentication required")
        return u
    return require_roles(request, set(roles))


def require(request: Request, capability: str) -> Dict[str, Any]:
    """The signed-in user, if their position (or role) in this fund grants `capability` (api/positions.py)."""
    from api import positions
    return positions.require(request, capability)


async def run(fn: Callable, *args: Any, timeout: Optional[float] = None) -> Any:
    """`fn(*args)` in a worker thread, with domain errors mapped to HTTP status codes."""
    try:
        coro = asyncio.to_thread(fn, *args)
        return await (asyncio.wait_for(coro, timeout) if timeout else coro)
    except asyncio.TimeoutError:
        raise HTTPException(504, "This took too long — a data source is slow; try again.")
    except LookupError as e:
        raise HTTPException(404, str(e))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


def audit(username: str, action: str, text: str, target: Optional[str] = None,
          before: Any = None, after: Any = None) -> None:
    """Append to the current fund's audit log. Never raises: the audit must not fail the action it records."""
    try:
        from api import audit_store
        audit_store.add_decision(action, text, user=username, target=target, before_state=before, after_state=after)
    except Exception:                                                          # noqa: BLE001
        pass
