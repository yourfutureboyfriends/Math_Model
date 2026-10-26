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
    rel = None
    if p.get("status") in ("approved", "closed") and p.get("decided_at"):
        try:
            from api import fund_store
            from api.calculations import benchmark as bm
            st = await asyncio.to_thread(fund_store.get_settings)
            code = (st.get("benchmark") or "SPY").upper()
            if code in bm.BENCHMARKS:
                rel = await asyncio.to_thread(bm.relative_since, p["symbol"], code, st.get("base_currency") or "USD",
                                              p["decided_at"], p.get("approved_benchmark_level"))
                p["relative_since_approval"] = {"value": round(rel, 4) if rel is not None else None, "benchmark": code,
                                                "since": p["decided_at"][:10], "currency": st.get("base_currency") or "USD"}
        except Exception:                                                      # noqa: BLE001 — shown as not evaluable
            rel = None
    p["kill_criteria_status"] = pitches.check_kill_criteria(p, price, entry, {k: ratios.get(k) for k in pitches.METRICS},
                                                            relative_since_approval=rel)
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
    bench_level = None
    if body.decision == "approve":                   # the benchmark level at approval, for "underperform benchmark"
        try:
            from api.calculations import benchmark as bm
            st = await asyncio.to_thread(fund_store.get_settings)
            code = (st.get("benchmark") or "SPY").upper()
            if code in bm.BENCHMARKS:
                bench_level = await asyncio.to_thread(bm.index_level, code, st.get("base_currency") or "USD")
        except Exception:                                                      # noqa: BLE001 — recorded as unknown
            bench_level = None
    try:
        p = await asyncio.to_thread(pitches.transition, pid, u["username"], "approved" if body.decision == "approve" else "rejected",
                                    body.notes or "", price, bench_level)
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
    from api import trade_lifecycle
    r["assessment_id"] = await asyncio.to_thread(trade_lifecycle.save_assessment, r, u["username"], body.pitch_id)
    await asyncio.to_thread(_audit, u["username"], "pretrade_assessed",
                            f"Pre-trade assessment #{r['assessment_id']} {body.side.upper()} {r['size']['quantity']:g} {r['symbol']}: {r['assessment']['verdict']}",
                            f"pretrade:{r['symbol']}", {"assessment": r["assessment"], "costs_bps": r["costs"].get("total_bps")})
    return r


@router.get("/api/v1/trading/lifecycle")
async def trade_lifecycle_view(request: Request, symbol: Optional[str] = Query(None, max_length=20),
                               pitch_id: Optional[int] = None, limit: int = Query(100, ge=1, le=500)):
    """Pitch → pre-trade assessment → order and approvals → fill, with TCA of each fill against its estimate."""
    from api import trade_lifecycle
    _user(request)
    return await asyncio.to_thread(trade_lifecycle.lifecycle, symbol, pitch_id, limit)


@router.get("/api/v1/trading/assessments/{aid}")
async def assessment_get(aid: int, request: Request):
    from api import trade_lifecycle
    _user(request)
    a = await asyncio.to_thread(trade_lifecycle.get_assessment, aid)
    if not a:
        raise HTTPException(404, "assessment not found")
    return a


# ── corporate actions (splits) ───────────────────────────────────────────────
class SplitIn(BaseModel):
    book: str = Field(..., max_length=60)
    symbol: str = Field(..., max_length=20)
    ex_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    ratio: float = Field(..., gt=0, le=1000)


@router.get("/api/v1/corporate-actions")
async def corporate_actions_list(request: Request):
    """Splits on held positions: pending (with whether they need review) and already applied."""
    from api import corporate_actions as ca
    _user(request)
    return {"pending": await asyncio.to_thread(ca.pending), "applied": await asyncio.to_thread(ca.applied)}


@router.post("/api/v1/corporate-actions/apply")
async def corporate_action_apply(body: SplitIn, request: Request):
    """Apply one split to a position (shares × ratio, average cost ÷ ratio) — for splits the daily job left for
    review. It must match a split in the symbol's split history (date and ratio)."""
    from api import corporate_actions as ca
    u = _user(request, ("pm",))
    known = await asyncio.to_thread(ca.splits, body.symbol.upper())
    match = [s for s in known if s["ex_date"] == body.ex_date]
    if not match or abs(match[0]["ratio"] - body.ratio) > 1e-9:
        recent = ", ".join("%s %g" % (s["ex_date"], s["ratio"]) for s in known[-5:]) or "none"
        raise HTTPException(400, f"no {body.ratio:g}:1 split of {body.symbol.upper()} on {body.ex_date} in the split "
                                 f"history (latest: {recent})")
    try:
        return await asyncio.to_thread(ca.apply, body.book, body.symbol, body.ex_date, body.ratio, u["username"])
    except Exception as e:                                                     # noqa: BLE001
        _err(e)
