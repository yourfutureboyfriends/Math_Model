"""Private equity: the LBO workbench (company defaults from filings and live credit markets, the full analysis, the
Excel model), the deal pipeline (per fund), and fund mathematics (performance with PMEs, the carry waterfall)."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

router = APIRouter(tags=["private equity"])
READ = {"pm", "quant", "analyst", "risk", "viewer", "trader"}
WRITE = {"pm", "quant", "analyst", "trader"}


def _user(request: Request, roles=READ) -> str:
    from api.core.access import require_roles
    return require_roles(request, roles)["username"]


async def _run(fn, *a, **kw):
    from api.pe.lbo import LboError
    try:
        return await asyncio.to_thread(fn, *a, **kw)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except (LboError, ValueError, KeyError, TypeError) as e:
        raise HTTPException(400, str(e))


class LboIn(BaseModel):
    inputs: Dict[str, Any]
    sources: Optional[Dict[str, str]] = None


class DealIn(BaseModel):
    inputs: Dict[str, Any]
    name: Optional[str] = Field(None, max_length=120)
    stage: Optional[str] = None
    sector: Optional[str] = Field(None, max_length=60)
    notes: Optional[str] = Field(None, max_length=4000)


class StageIn(BaseModel):
    stage: str


class NoteIn(BaseModel):
    text: str = Field(..., max_length=4000)


class Flow(BaseModel):
    date: str
    amount: float


class PerformanceIn(BaseModel):
    flows: List[Flow]
    nav: float = 0.0
    nav_date: Optional[str] = None
    index: Optional[str] = Field("^SP500TR", max_length=20)


class WaterfallIn(BaseModel):
    contributions: List[Flow]
    distributions: List[Flow]
    pref: float = Field(0.08, ge=0, le=0.5)
    carry: float = Field(0.20, ge=0, le=0.5)
    catch_up: float = Field(1.0, ge=0, le=1)
    compounding: bool = True


def _merge(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Fill any field the client left out from the documented defaults."""
    from api.pe import lbo
    return {**lbo.default_inputs(), **(inputs or {})}


@router.get("/api/v1/pe/defaults")
async def pe_defaults(request: Request):
    """An illustrative, complete input set (each field documented in api/pe/lbo.py)."""
    _user(request)
    from api.pe import deals, lbo
    return {"inputs": lbo.default_inputs(), "stages": deals.STAGES}


@router.get("/api/v1/pe/credit")
async def pe_credit(request: Request, currency: str = Query("USD", max_length=3)):
    """Leveraged-finance pricing today: base rate, BB / B / CCC spreads, 5-year Treasury, high-yield yield."""
    _user(request)
    from api.pe import market
    return await _run(market.credit, currency)


@router.get("/api/v1/pe/company/{symbol}")
async def pe_company(symbol: str, request: Request, premium: float = Query(0.30, ge=0, le=1.5)):
    """A complete LBO input set for a listed company, with the source of every assumption."""
    _user(request)
    from api.pe import market
    return await _run(market.from_company, symbol, premium)


@router.post("/api/v1/pe/lbo")
async def pe_lbo(body: LboIn, request: Request):
    """Run the model: base / upside / downside, the weighted IRR, sensitivities, the max price at the hurdle, the
    EBITDA cushion."""
    _user(request)
    from api.pe import lbo
    return await _run(lbo.analyse, _merge(body.inputs))


@router.post("/api/v1/pe/lbo/excel")
async def pe_lbo_excel(body: LboIn, request: Request):
    """The deal as an investment-committee workbook (.xlsx)."""
    _user(request)
    from api.pe import excel, lbo
    result = await _run(lbo.analyse, _merge(body.inputs))
    data = await asyncio.to_thread(excel.build, result, body.sources)
    name = "".join(ch for ch in (body.inputs.get("name") or "deal") if ch.isalnum() or ch in " -_")[:60].strip() or "deal"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="LBO - {name}.xlsx"'})


# ── Deal pipeline (the current fund's database) ───────────────────────────────────────────────────────────────────
@router.get("/api/v1/pe/deals")
async def pe_deals(request: Request):
    _user(request)
    from api.pe import deals
    return {"deals": await _run(deals.list_deals), "stages": deals.STAGES}


@router.get("/api/v1/pe/deals/{deal_id}")
async def pe_deal(deal_id: int, request: Request):
    _user(request)
    from api.pe import deals
    return await _run(deals.get, deal_id)


async def _save(request: Request, body: DealIn, deal_id: Optional[int]):
    who = _user(request, WRITE)
    from api.pe import deals, lbo
    inputs = _merge(body.inputs)
    try:
        summary = deals.summarise(await asyncio.to_thread(lbo.analyse, inputs))
    except lbo.LboError:
        summary = None                                   # an unfinished case can still be saved
    return await _run(deals.save, who, inputs, summary, deal_id, body.name, body.stage, body.sector, body.notes)


@router.post("/api/v1/pe/deals")
async def pe_deal_create(body: DealIn, request: Request):
    return await _save(request, body, None)


@router.put("/api/v1/pe/deals/{deal_id}")
async def pe_deal_update(deal_id: int, body: DealIn, request: Request):
    return await _save(request, body, deal_id)


@router.post("/api/v1/pe/deals/{deal_id}/stage")
async def pe_deal_stage(deal_id: int, body: StageIn, request: Request):
    who = _user(request, WRITE)
    from api.pe import deals
    return await _run(deals.set_stage, who, deal_id, body.stage)


@router.post("/api/v1/pe/deals/{deal_id}/notes")
async def pe_deal_note(deal_id: int, body: NoteIn, request: Request):
    who = _user(request, WRITE)
    from api.pe import deals
    return await _run(deals.add_note, who, deal_id, body.text)


@router.delete("/api/v1/pe/deals/{deal_id}")
async def pe_deal_delete(deal_id: int, request: Request):
    _user(request, {"pm"})
    from api.pe import deals
    await _run(deals.delete, deal_id)
    return {"deleted": deal_id}


# ── Fund mathematics ──────────────────────────────────────────────────────────────────────────────────────────────
@router.post("/api/v1/pe/fund/performance")
async def pe_fund_performance(body: PerformanceIn, request: Request):
    """IRR, TVPI / DPI / RVPI and — against a public index — KS-PME, Direct Alpha and the Long-Nickels PME."""
    _user(request)
    from api.pe import fundmath
    flows = [f.model_dump() for f in body.flows]
    index = None
    if body.index:
        start = min(f["date"] for f in flows) if flows else None
        try:
            index = await asyncio.to_thread(fundmath.index_levels, body.index, start) if start else None
        except ValueError as e:
            raise HTTPException(400, str(e))
    out = await _run(fundmath.performance, flows, body.nav, body.nav_date, index)
    out["index_symbol"] = body.index
    return out


@router.post("/api/v1/pe/fund/waterfall")
async def pe_fund_waterfall(body: WaterfallIn, request: Request):
    """European distribution waterfall: return of capital, preferred return, GP catch-up, carried-interest split."""
    _user(request)
    from api.pe import fundmath
    return await _run(fundmath.waterfall, [c.model_dump() for c in body.contributions],
                      [d.model_dump() for d in body.distributions], body.pref, body.carry, body.catch_up, body.compounding)
