"""Trading desk: analyst pitch review (PMC workflow) and the pre-trade feasibility assessment."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["trading-desk"])


def _user(request: Request, roles=("pm", "analyst", "risk", "quant")) -> Dict[str, Any]:
    from api.core.access import require_roles
    return require_roles(request, set(roles))


def _audit(user: str, action: str, text: str, target: str, after: Any = None) -> None:
    try:
        from api import audit_store
        audit_store.add_decision(action, text, user=user, target=target, after_state=after)
    except Exception:                                                          # noqa: BLE001 — never block the desk
        pass


class PitchIn(BaseModel):
    symbol: str = Field(..., max_length=20)
    title: Optional[str] = Field(None, max_length=200)
    body: Dict[str, Any]


class PitchVersionIn(BaseModel):
    body: Dict[str, Any]
    note: Optional[str] = Field(None, max_length=500)


class DecisionIn(BaseModel):
    decision: str = Field(..., pattern="^(approve|reject)$")
    notes: Optional[str] = Field(None, max_length=2000)


class PretradeIn(BaseModel):
    symbol: str = Field(..., max_length=20)
    side: str = Field(..., pattern="^(BUY|SELL|buy|sell)$")
    quantity: Optional[float] = Field(None, gt=0)
    amount_base: Optional[float] = Field(None, gt=0)
    participation: Optional[float] = Field(None, gt=0, le=0.5)
    pitch_id: Optional[int] = None


def _err(e: Exception):
    if isinstance(e, LookupError):
        raise HTTPException(404, str(e))
    if isinstance(e, PermissionError):
        raise HTTPException(403, str(e))
    raise HTTPException(400, str(e))


@router.get("/api/v1/pitches")
async def pitches_list(request: Request, status: Optional[str] = Query(None, pattern="^(draft|submitted|approved|rejected|closed)$"),
                       symbol: Optional[str] = Query(None, max_length=20)):
    from api import pitches
    _user(request)
    rows = await asyncio.to_thread(pitches.list_pitches, status, symbol)
    for r in rows:
        if r.get("current"):
            r["expected_value"] = round(pitches.expected_value(r["current"]), 4)
    return {"pitches": rows, "states": pitches.STATES, "kill_types": pitches.KILL_TYPES, "metrics": pitches.METRICS}


@router.get("/api/v1/pitches/{pid}")
async def pitch_get(pid: int, request: Request):
    """A pitch with every version, its valuation against the current price and its kill-criteria status."""
    from api import pitches
    from api.marketdata import core
    _user(request)
    try:
        p = await asyncio.to_thread(pitches.get, pid)
    except LookupError as e:
        _err(e)
    try:
        q = await asyncio.to_thread(core.quote, p["symbol"])
        price = q.get("price")
    except Exception:                                                          # noqa: BLE001
        q, price = {}, None
    try:
        ratios = (await asyncio.to_thread(core.statements, p["symbol"]) or {}).get("ratios") or {}
    except Exception:                                                          # noqa: BLE001
        ratios = {}
    from api import portfolio_store
    held = [x for x in await asyncio.to_thread(portfolio_store.list_positions, None) if str(x["symbol"]).upper() == p["symbol"]]
    entry = float(held[0]["avg_cost"]) if held else None
    p["quote"] = {"price": price, "currency": q.get("currency"), "market_state": q.get("market_state")}
    p["valuation"] = pitches.valuation_vs_price(p["current"], price) if p.get("current") else None
    p["kill_criteria_status"] = pitches.check_kill_criteria(p, price, entry, {k: ratios.get(k) for k in pitches.METRICS})
    return p


@router.post("/api/v1/pitches")
async def pitch_create(body: PitchIn, request: Request):
    from api import pitches
    u = _user(request, ("analyst", "pm"))
    try:
        p = await asyncio.to_thread(pitches.create, body.symbol, body.title or body.symbol, u["username"], body.body)
    except Exception as e:                                                     # noqa: BLE001
        _err(e)
    await asyncio.to_thread(_audit, u["username"], "pitch_created", f"Pitch #{p['id']} {p['symbol']} created", f"pitch:{p['id']}")
    return p


@router.post("/api/v1/pitches/{pid}/versions")
async def pitch_revise(pid: int, body: PitchVersionIn, request: Request):
    from api import pitches
    u = _user(request, ("analyst", "pm"))
    try:
        p = await asyncio.to_thread(pitches.add_version, pid, u["username"], body.body, body.note or "")
    except Exception as e:                                                     # noqa: BLE001
        _err(e)
    await asyncio.to_thread(_audit, u["username"], "pitch_revised", f"Pitch #{pid} revised to v{p['current_version']}: {body.note or ''}", f"pitch:{pid}")
    return p


@router.post("/api/v1/pitches/{pid}/submit")
async def pitch_submit(pid: int, request: Request):
    from api import pitches
    u = _user(request, ("analyst", "pm"))
    try:
        p = await asyncio.to_thread(pitches.transition, pid, u["username"], "submitted")
    except Exception as e:                                                     # noqa: BLE001
        _err(e)
    await asyncio.to_thread(_audit, u["username"], "pitch_submitted", f"Pitch #{pid} submitted to the PMC", f"pitch:{pid}")
    return p


@router.post("/api/v1/pitches/{pid}/decision")
async def pitch_decision(pid: int, body: DecisionIn, request: Request):
    """The PMC's decision, recorded by a PM who is not the pitch's author (four-eyes); the price and benchmark level
    at approval are kept for the kill criteria."""
    from api import fund_store, pitches
    from api.marketdata import core
    u = _user(request, ("pm",))
    price = None
    try:
        p0 = await asyncio.to_thread(pitches.get, pid)
        price = (await asyncio.to_thread(core.quote, p0["symbol"])).get("price")
    except Exception:                                                          # noqa: BLE001
        pass
    try:
        p = await asyncio.to_thread(pitches.transition, pid, u["username"], "approved" if body.decision == "approve" else "rejected",
                                    body.notes or "", price)
    except Exception as e:                                                     # noqa: BLE001
        _err(e)
    await asyncio.to_thread(_audit, u["username"], f"pitch_{body.decision}d",
                            f"PMC {body.decision}d pitch #{pid} {p['symbol']}" + (f" at {price}" if price else "") + f": {body.notes or ''}",
                            f"pitch:{pid}", {"status": p["status"], "price": price})
    return p


@router.post("/api/v1/pitches/{pid}/close")
async def pitch_close(pid: int, request: Request):
    from api import pitches
    u = _user(request, ("pm",))
    try:
        p = await asyncio.to_thread(pitches.transition, pid, u["username"], "closed")
    except Exception as e:                                                     # noqa: BLE001
        _err(e)
    await asyncio.to_thread(_audit, u["username"], "pitch_closed", f"Pitch #{pid} closed", f"pitch:{pid}")
    return p


@router.post("/api/v1/trading/pretrade-assessment")
async def pretrade_assessment(body: PretradeIn, request: Request):
    """Feasibility of implementing a proposed order: price and timestamp, liquidity, estimated costs (labelled),
    technicals, events in the execution window, mandate checks, portfolio impact and the pitch's valuation → flags
    and an execution suggestion. Decision support only: it approves nothing and places no order."""
    from api.handlers import pretrade_feasibility as pf
    u = _user(request)
    try:
        r = await asyncio.wait_for(asyncio.to_thread(pf.assess, body.symbol, body.side, body.quantity, body.amount_base,
                                                     body.participation, body.pitch_id), timeout=120)
    except asyncio.TimeoutError:
        raise HTTPException(504, "The assessment took too long (a data source is slow) — try again.")
    except ValueError as e:
        raise HTTPException(400, str(e))
    await asyncio.to_thread(_audit, u["username"], "pretrade_assessed",
                            f"Pre-trade assessment {body.side.upper()} {r['size']['quantity']:g} {r['symbol']}: {r['assessment']['verdict']}",
                            f"pretrade:{r['symbol']}", {"assessment": r["assessment"], "costs_bps": r["costs"].get("total_bps")})
    return r
