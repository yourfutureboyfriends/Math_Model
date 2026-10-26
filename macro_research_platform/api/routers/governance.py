"""Fund governance API (api/governance.py): stage and policy, approved instruments, model gates G0–G5, halts and
incidents, reconciliation, the monthly reporting pack, scorecard, budget, milestones and break-even AUM."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["governance"])
ALL = ("pm", "analyst", "risk", "quant")


def _user(request: Request, roles=ALL) -> Dict[str, Any]:
    from api.core.access import require_roles
    return require_roles(request, set(roles))


async def _t(fn, *a):
    try:
        return await asyncio.to_thread(fn, *a)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/api/v1/governance")
async def gov_overview(request: Request):
    from api import governance as gov
    _user(request)
    st = await _t(gov.settings)
    return {"settings": st, "halt": await _t(gov.active_halt), "open_incidents": len(await _t(gov.incidents, True)),
            "stages": gov.STAGES, "gates": gov.GATE_INFO, "gate_signoffs": {k: [sorted(r) for r in v] for k, v in gov.GATE_SIGNOFFS.items()},
            "sleeves": gov.SLEEVES, "label": gov.results_label(st["stage"])}


@router.post("/api/v1/governance/setup/moriah")
async def gov_setup_moriah(request: Request, paper_notional: float = Query(25_000.0, gt=0)):
    """Configure the current fund as Moriah Capital Partners from its Future Growth Strategy (admin)."""
    from api import funds, moriah
    u = _user(request, ())
    return await _t(moriah.setup, funds.current(), u["username"], paper_notional)


# ── instruments ──────────────────────────────────────────────────────────────
class InstrumentIn(BaseModel):
    symbol: str = Field(..., max_length=20)
    name: str = Field("", max_length=120)
    asset_class: str = Field("", max_length=40)
    theme: str = Field("", max_length=60)
    currency: str = Field("", max_length=4)
    tradable: bool = True
    note: str = Field("", max_length=500)


class DecideIn(BaseModel):
    approve: bool
    note: str = Field("", max_length=500)


@router.get("/api/v1/governance/instruments")
async def gov_instruments(request: Request):
    from api import governance as gov
    _user(request)
    return {"instruments": await _t(gov.instruments)}


@router.post("/api/v1/governance/instruments")
async def gov_instrument_propose(body: InstrumentIn, request: Request):
    from api import governance as gov
    u = _user(request)
    return await _t(lambda: gov.propose_instrument(body.symbol, u["username"], body.name, body.asset_class, body.theme,
                                                   body.currency, body.tradable, body.note))


@router.post("/api/v1/governance/instruments/{symbol}/decision")
async def gov_instrument_decide(symbol: str, body: DecideIn, request: Request):
    from api import governance as gov
    u = _user(request, ("pm", "risk"))
    return await _t(gov.decide_instrument, symbol, u["username"], body.approve, body.note)


# ── models ───────────────────────────────────────────────────────────────────
class ModelIn(BaseModel):
    name: str = Field(..., max_length=120)
    sleeve: str = "other"
    book: Optional[str] = Field(None, max_length=60)
    mechanism: str = Field("", max_length=2000)
    target_variable: str = Field("", max_length=500)
    horizon: str = Field("", max_length=200)
    dataset: str = Field("", max_length=2000)
    null_hypothesis: str = Field("", max_length=1000)


class SignoffIn(BaseModel):
    evidence: Dict[str, Any] = {}
    note: str = Field("", max_length=2000)


class CloseIn(BaseModel):
    action: str = Field(..., pattern="^(reject|retire|suspend|reactivate)$")
    note: str = Field(..., max_length=2000)


class ModelUpdateIn(BaseModel):
    allocation: Optional[float] = Field(None, ge=0)
    max_loss_budget: Optional[float] = Field(None, gt=0, le=1)
    retirement_criterion: Optional[str] = Field(None, max_length=1000)
    book: Optional[str] = Field(None, max_length=60)
    mechanism: Optional[str] = Field(None, max_length=2000)
    dataset: Optional[str] = Field(None, max_length=2000)
    horizon: Optional[str] = Field(None, max_length=200)


@router.get("/api/v1/governance/models")
async def gov_models(request: Request):
    from api import governance as gov
    _user(request)
    return {"models": await _t(gov.list_models)}


@router.post("/api/v1/governance/models")
async def gov_model_create(body: ModelIn, request: Request):
    from api import governance as gov
    u = _user(request, ("pm", "analyst", "quant"))
    return await _t(gov.create_model, u["username"], body.model_dump())


@router.get("/api/v1/governance/models/{mid}")
async def gov_model_get(mid: int, request: Request):
    from api import governance as gov
    _user(request)
    return await _t(gov.get_model, mid)


@router.post("/api/v1/governance/models/{mid}/signoff")
async def gov_model_signoff(mid: int, body: SignoffIn, request: Request):
    from api import governance as gov
    u = _user(request, ALL)
    return await _t(gov.signoff, mid, u["username"], u.get("role") or "", body.evidence, body.note)


@router.post("/api/v1/governance/models/{mid}/close")
async def gov_model_close(mid: int, body: CloseIn, request: Request):
    from api import governance as gov
    u = _user(request, ("pm", "risk"))
    return await _t(gov.close_model, mid, u["username"], u.get("role") or "", body.action, body.note)


@router.put("/api/v1/governance/models/{mid}")
async def gov_model_update(mid: int, body: ModelUpdateIn, request: Request):
    from api import governance as gov
    u = _user(request, ("pm", "risk", "quant", "analyst"))
    return await _t(gov.update_model, mid, u["username"], body.model_dump(exclude_none=True))


# ── controls ─────────────────────────────────────────────────────────────────
class HaltIn(BaseModel):
    reason: str = Field(..., min_length=3, max_length=1000)
    test: bool = False


class TextIn(BaseModel):
    text: str = Field(..., min_length=3, max_length=2000)


@router.get("/api/v1/governance/controls")
async def gov_controls(request: Request):
    from api import governance as gov
    _user(request)
    return {"halt": await _t(gov.active_halt), "incidents": await _t(gov.incidents),
            "reconciliations": await _t(gov.reconciliations, 30)}


@router.post("/api/v1/governance/controls/halt")
async def gov_halt(body: HaltIn, request: Request):
    from api import governance as gov
    u = _user(request, ("pm", "risk"))
    return await _t(lambda: gov.start_halt("manual" if not body.test else "test", body.reason, u["username"], body.test))


@router.post("/api/v1/governance/controls/resume")
async def gov_resume(body: TextIn, request: Request):
    from api import governance as gov
    u = _user(request, ("risk",))
    return await _t(gov.lift_halt, u["username"], body.text)


@router.post("/api/v1/governance/controls/reconcile")
async def gov_reconcile(request: Request):
    from api import governance as gov
    u = _user(request)
    return await _t(gov.reconcile, u["username"])


@router.post("/api/v1/governance/incidents")
async def gov_incident_open(body: TextIn, request: Request):
    from api import governance as gov
    u = _user(request)
    iid = await _t(lambda: gov.open_incident("operational", body.text, u["username"], "medium"))
    return {"id": iid}


@router.post("/api/v1/governance/incidents/{iid}/fix")
async def gov_incident_fix(iid: int, body: TextIn, request: Request):
    from api import governance as gov
    u = _user(request)
    return await _t(gov.fix_incident, iid, u["username"], body.text)


@router.post("/api/v1/governance/incidents/{iid}/signoff")
async def gov_incident_signoff(iid: int, request: Request):
    from api import governance as gov
    u = _user(request, ("risk", "pm"))
    return await _t(gov.signoff_incident, iid, u["username"])


# ── reporting ────────────────────────────────────────────────────────────────
@router.get("/api/v1/governance/report/monthly")
async def gov_monthly(request: Request, month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$")):
    from api import governance_reports as gr
    _user(request)
    return await _t(gr.monthly_report, month)


@router.get("/api/v1/governance/scorecard")
async def gov_scorecard(request: Request):
    from api import governance_reports as gr
    _user(request)
    return await _t(gr.scorecard)


# ── budget and milestones ────────────────────────────────────────────────────
class ExpenseIn(BaseModel):
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    category: str = Field(..., max_length=80)
    amount: float = Field(..., gt=0)
    currency: str = Field("GBP", max_length=3)
    description: str = Field(..., min_length=2, max_length=500)


class MilestoneIn(BaseModel):
    status: str = Field(..., pattern="^(open|in_progress|done|blocked)$")
    evidence: str = Field("", max_length=2000)


@router.get("/api/v1/governance/budget")
async def gov_budget(request: Request):
    from api import governance as gov
    _user(request)
    return await _t(gov.budget)


@router.post("/api/v1/governance/budget/expenses")
async def gov_expense(body: ExpenseIn, request: Request):
    from api import governance as gov
    u = _user(request)
    return await _t(gov.add_expense, u["username"], body.date, body.category, body.amount, body.currency, body.description)


@router.post("/api/v1/governance/budget/expenses/{eid}/approve")
async def gov_expense_approve(eid: int, request: Request):
    from api import governance as gov
    u = _user(request, ("pm",))
    return await _t(gov.approve_expense, eid, u["username"])


@router.get("/api/v1/governance/milestones")
async def gov_milestones(request: Request):
    from api import governance as gov
    _user(request)
    return {"milestones": await _t(gov.milestones)}


@router.put("/api/v1/governance/milestones/{mid}")
async def gov_milestone_update(mid: int, body: MilestoneIn, request: Request):
    from api import governance as gov
    u = _user(request)
    return await _t(gov.update_milestone, mid, u["username"], body.status, body.evidence)


@router.post("/api/v1/governance/milestones/{mid}/signoff")
async def gov_milestone_signoff(mid: int, request: Request):
    from api import governance as gov
    u = _user(request, ("pm", "risk"))
    return await _t(gov.signoff_milestone, mid, u["username"])


@router.get("/api/v1/governance/break-even")
async def gov_break_even(request: Request, costs: str = Query("175000,250000,350000,500000"),
                         fees: str = Query("0.01,0.015,0.02"), aums: str = Query("5e6,1e7,1.5e7,2e7,3e7")):
    """Break-even AUM on management fees alone (the plan's formula); defaults are the plan's illustrative US$ figures."""
    from api import governance as gov
    _user(request)
    try:
        c = [float(x) for x in costs.split(",") if x][:8]
        f = [float(x) for x in fees.split(",") if x][:6]
        a = [float(x) for x in aums.split(",") if x][:12]
    except ValueError:
        raise HTTPException(400, "costs, fees and aums are comma-separated numbers")
    if not c or not f or any(x <= 0 for x in f):
        raise HTTPException(400, "give at least one cost and positive fee rates")
    return {**gov.break_even(c, f, a), "currency": "USD",
            "note": "Excludes performance fees, taxes and fee discounts or waivers; illustrative, not a regulatory minimum."}
