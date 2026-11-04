"""Systematic macro model API (see api/model/).

One method, three economies (api/model/economies.py): `economy=us` (default — the United States, the only model with a
tradeable sleeve), `ea` (euro area) and `row` (rest of the world). Orders and the sleeve are US only.

    GET  /api/v1/model?economy=        current state, portfolios and backtest (cached)
    GET  /api/v1/model/world           every economy's regime side by side
    GET  /api/v1/model/economies       what each economy's model uses (series, assets, sources, limitations)
    POST /api/v1/model/run             re-run with custom parameters (quant / pm)
    GET  /api/v1/model/runs?economy=   run history
    GET  /api/v1/model/sleeve          the US sleeve against its targets (read-only)
    POST /api/v1/model/orders/preview | /stage   US orders (stage: pre-trade compliance + four-eyes approval)
"""
from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(tags=["model"])


class RunIn(BaseModel):
    """Model parameter overrides for a run, and the economy (us / ea / row)."""
    params: Optional[Dict[str, Any]] = None
    economy: Literal["us", "ea", "row"] = "us"


class OrdersIn(BaseModel):
    """Parameters and book for turning model weights into orders."""
    portfolio: Literal["strategic", "tactical"] = "strategic"
    params: Optional[Dict[str, Any]] = None
    sleeve_capital: Optional[float] = None


@router.get("/api/v1/model")
async def model_latest(economy: Literal["us", "ea", "row"] = Query("us")):
    """Current model state, portfolios and backtest with default parameters (cached) for an economy."""
    from api.model.engine import run_model
    return await run_model(None, user="system", economy=economy)


@router.get("/api/v1/model/world")
async def model_world():
    """The US, euro-area and rest-of-world models side by side: regime, factor levels and changes, direction
    probabilities, contraction probability and the top tactical weights."""
    from api.model.engine import world_summary
    return await world_summary()


@router.get("/api/v1/model/economies")
async def model_economies():
    """Each economy's configuration: input series (block, transform, publication lag), assets with their estimation
    proxy and tradeable instrument, the 60/40 benchmark, data sources and limitations."""
    from api.model.economies import ECONOMIES
    return {"economies": [{
        "id": e.id, "name": e.name, "currency": e.currency, "cash": e.cash_label, "tradeable": e.tradeable,
        "series": [{"key": k, "label": e.labels.get(k, k), "block": b, "transform": t, "lag_months": lag}
                   for k, (b, t, lag) in e.series.items()],
        "assets": [{"name": a, "proxy": p, "instrument": i, "environment": env} for a, (p, i, env) in e.assets.items()],
        "benchmark_6040": {"equity": e.benchmark[0], "bonds": e.benchmark[1]},
        "sources": e.sources, "limitations": e.limitations} for e in ECONOMIES.values()]}


@router.get("/api/v1/model/params")
async def model_params():
    """The model's default parameters and their meaning."""
    from api.model.core import ModelParams
    return {"defaults": ModelParams().__dict__,
            "descriptions": {
                "vol_target": "Annualised portfolio volatility target",
                "max_weight": "Maximum weight per asset class (tactical portfolio)",
                "risk_aversion": "δ — Black–Litterman equilibrium and optimiser risk aversion",
                "tau": "τ — uncertainty of the prior (Black–Litterman)",
                "view_confidence": "Confidence in the model's views relative to the prior (>1 = trust views more)",
                "shrinkage_months": "Shrinkage of regime means toward the unconditional mean (months of pseudo-data)",
                "cov_months": "Covariance estimation window (months, Ledoit–Wolf shrinkage)",
                "min_history_months": "History required before an asset enters the model",
                "momentum_months": "Window defining a rising/falling factor",
                "cost_bps": "One-way transaction cost in the backtest (bp)",
                "max_gross": "Gross exposure limit (1.0 = no leverage)"}}


@router.post("/api/v1/model/run")
async def model_run(body: RunIn, request: Request):
    """Re-run the model with custom parameters (recorded with the user)."""
    from api.core.access import require_roles
    from api.model.engine import run_model
    user = require_roles(request, {"quant", "pm"})
    try:
        return await run_model(body.params, user=user["username"], force=True, economy=body.economy)
    except (TypeError, ValueError) as e:
        raise HTTPException(400, f"invalid parameters: {e}")


@router.get("/api/v1/model/runs")
async def model_runs(limit: int = 50, economy: Optional[Literal["us", "ea", "row"]] = None):
    """Recent model runs, newest first (one economy's, or all)."""
    import asyncio
    from api.model.engine import list_runs
    return {"runs": await asyncio.to_thread(list_runs, min(max(limit, 1), 500), economy)}


@router.get("/api/v1/model/sleeve")
async def model_sleeve(portfolio: Literal["strategic", "tactical"] = "strategic"):
    """Read-only: the model sleeve's holdings (book "Macro Model") against the model's
    targets, with the drift and the orders that would close it. Nothing is staged."""
    from api.model.engine import model_orders, run_model
    result = await run_model(None, user="system")
    if not result.get("available"):
        raise HTTPException(503, result.get("reason", "model unavailable"))
    plan = await model_orders(result, portfolio, None)
    plan["regime"] = result["regime"]["most_likely"]
    plan["regime_probability"] = result["regime"]["probabilities"][result["regime"]["most_likely"]]
    plan["expected_vol"] = result["portfolios"][portfolio]["expected_vol"]
    return plan


@router.post("/api/v1/model/orders/preview")
async def model_orders_preview(body: OrdersIn, request: Request):
    """Orders that would move the book to the model's portfolio — preview only, nothing is staged."""
    from api.core.access import require_roles
    from api.model.engine import model_orders, run_model
    require_roles(request, {"pm", "quant", "risk"})
    result = await run_model(body.params, persist=False)
    if not result.get("available"):
        raise HTTPException(503, result.get("reason", "model unavailable"))
    return await model_orders(result, body.portfolio, body.sleeve_capital)


@router.post("/api/v1/model/orders/stage")
async def model_orders_stage(body: OrdersIn, request: Request):
    """Stage the model's orders through the normal order ticket: each runs pre-trade
    compliance and needs risk approval (four-eyes) before it can be executed."""
    from api import audit_store
    from api.core.access import require_roles
    from api.model.engine import MODEL_BOOK, model_orders, run_model
    from api.routers.fund import OrderIn, create_order
    import asyncio
    user = require_roles(request, {"pm", "quant"})
    result = await run_model(body.params, user=user["username"])
    if not result.get("available"):
        raise HTTPException(503, result.get("reason", "model unavailable"))
    plan = await model_orders(result, body.portfolio, body.sleeve_capital)
    staged = []
    for o in plan["orders"]:
        thesis = (f"Macro model v{result['version']} run {result.get('run_id')} ({result['as_of']}), "
                  f"{body.portfolio} portfolio: {o['action']} to {o['target_weight']:.1%} of sleeve. "
                  f"Most likely regime {result['regime']['most_likely']} "
                  f"({result['regime']['probabilities'][result['regime']['most_likely']]:.0%}).")
        resp = await create_order(OrderIn(symbol=o["symbol"], side=o["side"], quantity=o["quantity"],
                                          book=MODEL_BOOK, thesis=thesis, conviction="MEDIUM"), request)
        staged.append(resp)
    await asyncio.to_thread(lambda: audit_store.add_decision(
        "model_orders_staged", f"{len(staged)} model orders staged ({body.portfolio}, run {result.get('run_id')})",
        user=user["username"], target=MODEL_BOOK,
        after_state={"orders": plan["orders"], "run_id": result.get("run_id"), "params_hash": result["params_hash"]}))
    return {"staged": len(staged), "orders": staged, "plan": {k: v for k, v in plan.items() if k != "orders"}}
