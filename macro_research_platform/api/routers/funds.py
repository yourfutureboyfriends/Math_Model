"""Funds: list the ones you can open, create one (each gets its own database), manage its name and members."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["funds"])


class FundIn(BaseModel):
    id: str = Field(..., max_length=24)
    name: str = Field(..., max_length=80)
    members: Optional[List[str]] = None
    base_currency: Optional[str] = Field(None, max_length=3)
    benchmark: Optional[str] = Field(None, max_length=12)
    capital: Optional[float] = Field(None, gt=0)
    fund_name: Optional[str] = Field(None, max_length=80)


class FundUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=80)
    members: Optional[List[str]] = None


@router.get("/api/v1/funds")
async def funds_list(request: Request):
    """The funds you can open and which one this request works on (X-Fund header)."""
    from api import fund_store, funds
    from api.core.access import require_roles
    u = require_roles(request, {"pm", "analyst", "risk", "quant"})
    rows = await asyncio.to_thread(funds.visible_to, u)
    out = []
    for f in rows:
        tok = funds.CURRENT.set(f["id"])
        try:
            st = await asyncio.to_thread(fund_store.get_settings)
        finally:
            funds.CURRENT.reset(tok)
        out.append({**f, "base_currency": st.get("base_currency"), "benchmark": st.get("benchmark"),
                    "fund_name": st.get("fund_name"), "capital": st.get("capital"),
                    "members": f["members"] if u.get("role") == "admin" else None})
    return {"funds": out, "current": funds.current()}


@router.post("/api/v1/funds")
async def funds_create(body: FundIn, request: Request):
    """A new fund with its own database; its settings (base currency, benchmark, capital) start from the body."""
    from api import funds, audit_store
    from api.core.access import require_roles
    u = require_roles(request, {"pm"})
    settings: Dict[str, Any] = {k: v for k, v in {"base_currency": (body.base_currency or "").upper() or None,
                                                  "benchmark": (body.benchmark or "").upper() or None,
                                                  "capital": body.capital, "fund_name": body.fund_name or body.name}.items()
                                if v is not None}
    if "benchmark" in settings:
        from api.calculations.benchmark import BENCHMARKS
        if settings["benchmark"] not in BENCHMARKS:
            raise HTTPException(400, f"benchmark must be one of {', '.join(BENCHMARKS)}")
    try:
        f = await asyncio.to_thread(funds.create, body.id, body.name, u["username"], body.members, settings)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await asyncio.to_thread(lambda: audit_store.add_decision("fund_created", f"Fund '{f['name']}' ({f['id']}) created",
                                                              user=u["username"], target=f"fund:{f['id']}", after_state=f))
    return f


@router.put("/api/v1/funds/{fund_id}")
async def funds_update(fund_id: str, body: FundUpdate, request: Request):
    """Rename a fund or set who may open it (admin)."""
    from api import funds
    from api.core.access import require_roles
    require_roles(request, set())                                # admin only
    try:
        return await asyncio.to_thread(funds.update, fund_id, body.name, body.members)
    except LookupError as e:
        raise HTTPException(404, str(e))
