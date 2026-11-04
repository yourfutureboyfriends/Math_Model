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


@router.get("/api/v1/models/recession/challenger")
async def recession_challenger():
    """The machine-learning challenger to the headline recession model: today's shadow forecast with what drove it,
    its walk-forward record against the headline, its live record and why it is (not) eligible for promotion."""
    from api.models_ml.recession_challenger import get_challenger
    return await asyncio.to_thread(get_challenger)


@router.get("/api/v1/ops/archive")
async def ops_archive():
    """Point-in-time archive: stored file vintages (e.g. the Fed's EBP) and the daily commodity-curve history."""
    from api import vintage_archive as va
    return await asyncio.to_thread(va.status)


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


# ── ML engine (api/ml): every forecasting task, its champion, its network challenger and the knowledge scanner ──
@router.get("/api/v1/ml/tasks")
async def ml_tasks(request: Request):
    """Each task's current signal (champion until a network is promoted), record and data checks — without weights.
    Tasks not yet computed this month report ready: false (they compute on first open or at the 07:00 UTC job)."""
    from api.core import web
    from api.ml import engine
    web.user(request, None)
    return {"tasks": engine.summary()}


@router.get("/api/v1/ml/tasks/{name}")
async def ml_task(name: str, request: Request):
    """One task in full: signal, champion and network (with weights for the visualizer), attributions, checks,
    walk-forward record, live record and promotion status. If not yet trained this month, returns
    {training: true} at once and trains in the background — poll until available."""
    from api.core import web
    from api.ml import engine
    web.user(request, None)
    d = engine.request(name)                     # never blocks: trains in the background and says so
    if d.get("reason") == "unknown task":
        raise HTTPException(404, f"Unknown ML task '{name}'")
    return d


@router.get("/api/v1/ml/tasks/{name}/history")
async def ml_task_history(name: str, request: Request):
    """Every model's recalibrated walk-forward forecast by month with the outcome (timeline, ROC, reliability)."""
    from api.core import web
    from api.ml import engine
    web.user(request, None)
    d = await asyncio.to_thread(engine.history, name)
    if d is None:
        raise HTTPException(409, "Not trained yet this month — open the task first")
    return d


@router.get("/api/v1/ml/registry")
async def ml_registry(request: Request):
    """Model registry and operations: stages, promotions, retrain log, latest forecasts."""
    from api.core import web
    from api.ml import engine
    web.user(request, None)
    return await asyncio.to_thread(engine.registry)


@router.post("/api/v1/ml/tasks/{name}/promote")
async def ml_promote(name: str, request: Request):
    """Promote a task's network to serve its signal — only when the validation gate says it is eligible."""
    from api.core import web
    from api.ml import engine
    u = web.user(request, ("pm", "risk"))
    return await web.run(engine.promote, name, u["username"])


@router.delete("/api/v1/ml/tasks/{name}/promote")
async def ml_demote(name: str, request: Request):
    """Return a task to its champion (the kill switch for a promoted network)."""
    from api.core import web
    from api.ml import engine
    web.user(request, ("pm", "risk"))
    return await web.run(engine.demote, name)


@router.get("/api/v1/ml/knowledge")
async def ml_knowledge(request: Request):
    """The knowledge scanner: the latest test of every candidate indicator and which a person approved."""
    from api.core import web
    from api.models_ml import knowledge_scanner as ks
    web.user(request, None)
    return {"scan": await asyncio.to_thread(ks.latest_scan), "approved": await asyncio.to_thread(ks.approved),
            "registry": {k: {"label": v[0], "transform": v[1], "why": v[2]} for k, v in ks.REGISTRY.items()}}


@router.post("/api/v1/ml/knowledge/{series}/approve")
async def ml_knowledge_approve(series: str, request: Request):
    """Add an indicator that passed the scanner's gate to the challenger's inputs (a person's decision)."""
    from api.core import web
    from api.models_ml import knowledge_scanner as ks
    u = web.user(request, ("pm", "risk"))
    return await web.run(ks.approve, series.upper(), u["username"])


@router.delete("/api/v1/ml/knowledge/{series}/approve")
async def ml_knowledge_revoke(series: str, request: Request):
    from api.core import web
    from api.models_ml import knowledge_scanner as ks
    web.user(request, ("pm", "risk"))
    return await web.run(ks.revoke, series.upper())


@router.get("/api/v1/ml/features")
async def ml_features(request: Request):
    """The ML feature store: every input the engine can use, its source and the months it covers."""
    from api.core import web
    from api.ml import features as F
    web.user(request, None)
    feats = await asyncio.to_thread(F.load)
    cov = F.coverage(feats)
    for k, v in cov.items():
        v["source"] = F.FEATURES.get(k, ("", "", ""))[2]
    return {"features": cov}
