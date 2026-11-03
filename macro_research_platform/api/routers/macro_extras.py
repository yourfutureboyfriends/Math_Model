"""Macro extras: Fed watch (FOMC statement redline, dissents, tone), FINRA margin debt, the ops monitor and screen usage."""
import asyncio
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter()


@router.get("/api/v1/mkt/fedwatch")
async def fed_watch():
    """What changed in the latest FOMC statement versus the previous one, dissents, and a lexicon tone score for recent
    statements and speeches (federalreserve.gov)."""
    from api.marketdata import fedwatch
    from api.marketdata.core import Upstream
    try:
        return await asyncio.to_thread(fedwatch.fedwatch)
    except Upstream as e:
        raise HTTPException(503, str(e))


@router.get("/api/v1/mkt/margin-debt")
async def margin_debt():
    """FINRA customer margin debt and free credit balances, monthly since 1997, with year-on-year growth."""
    from api.marketdata import freedata
    from api.marketdata.core import Upstream
    try:
        return await asyncio.to_thread(freedata.margin_debt)
    except Upstream as e:
        raise HTTPException(503, str(e))


@router.get("/api/v1/ops/monitor")
async def ops_monitor():
    """Feed state, open data incidents, the last accuracy audit and recent events (for alerts and due diligence)."""
    from api import ops_monitor as ops
    return await asyncio.to_thread(ops.summary)


class UsageIn(BaseModel):
    events: List[Dict[str, Any]] = Field(default_factory=list, max_length=500)
    known: List[Dict[str, Any]] = Field(default_factory=list, max_length=2000)


@router.post("/api/v1/usage")
async def usage_record(body: UsageIn, request: Request):
    """Screen views from the browser (batched): which panels and functions are actually read."""
    from api import usage
    from api.core import web
    u = web.user(request, None)
    return await asyncio.to_thread(usage.record, u["username"], body.events, body.known)


@router.get("/api/v1/usage/summary")
async def usage_summary(request: Request, days: int = Query(90, ge=7, le=730)):
    """Views per screen over `days`, screens never viewed, and how concentrated use is."""
    from api import usage
    from api.core import web
    web.user(request, None)
    return await asyncio.to_thread(usage.summary, days)
