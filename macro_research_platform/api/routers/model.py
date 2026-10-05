"""Systematic macro model API (see api/model/)."""
from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["model"])


class RunIn(BaseModel):
    params: Optional[Dict[str, Any]] = None


class OrdersIn(BaseModel):
    portfolio: Literal["strategic", "tactical"] = "strategic"
    params: Optional[Dict[str, Any]] = None
    sleeve_capital: Optional[float] = None


@router.get("/api/v1/model")
async def model_latest():
    """Current model state, portfolios and backtest with default parameters (cached)."""
    from api.model.engine import run_model
    return await run_model(None, user="system")


@router.get("/api/v1/model/params")
async def model_params():
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
        return await run_model(body.params, user=user["username"], force=True)
    except (TypeError, ValueError) as e:
        raise HTTPException(400, f"invalid parameters: {e}")


@router.get("/api/v1/model/runs")
async def model_runs(limit: int = 50):
    import asyncio
    from api.model.engine import list_runs
    return {"runs": await asyncio.to_thread(list_runs, min(max(limit, 1), 500))}


@router.post("/api/v1/model/orders/preview")
async def model_orders_preview(body: OrdersIn, request: Request):
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
