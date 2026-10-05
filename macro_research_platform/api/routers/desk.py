"""
GET /api/v1/desk — the signed-in user's role desk: their action queue plus the handful of
numbers their job turns on (see api/calculations/desk.py for the routing rules).

Each block degrades independently: a failing source becomes {"available": false, ...}
instead of failing the whole desk.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from api.calculations.desk import ROLE_FOCUS, build_queue

logger = logging.getLogger(__name__)
router = APIRouter(tags=["desk"])


async def _safe(coro, label: str, timeout: float = 20.0):
    try:
        return await asyncio.wait_for(coro, timeout)
    except Exception as e:
        logger.warning("[desk] %s unavailable: %s", label, e)
        return {"available": False, "reason": f"{label} unavailable"}


async def _fund_block() -> Dict[str, Any]:
    from api import fund_store, portfolio_store
    from api.calculations.fund import track_record
    from api.calculations.limits import merge_limits, evaluate_limits
    from api.routers.fund import _book_state
    settings = await asyncio.to_thread(fund_store.get_settings)
    raw = await asyncio.to_thread(portfolio_store.list_positions, None)
    state = await _book_state(raw, settings, include_liquidity=False)
    limits = evaluate_limits(state["metrics"], merge_limits(await asyncio.to_thread(fund_store.get_limit_overrides)))
    history = await asyncio.to_thread(fund_store.nav_history)
    rec = track_record([h["nav"] for h in history], risk_free_annual=0.0)
    day_pnl = (history[-1]["nav"] - history[-2]["nav"]) if len(history) >= 2 else None
    top = sorted((l for l in limits["limits"] if l.get("utilization") is not None),
                 key=lambda l: -l["utilization"])[:5]
    return {"available": True, "fund_name": settings.get("fund_name"),
            "base_currency": settings.get("base_currency"), "nav": state["nav"],
            "unrealized_pnl": state["summary"].get("total_unrealized_pnl"),
            "realized_pnl": state["realized_pnl"], "last_day_pnl": day_pnl,
            "exposures": state["exposures"], "var95_1d_usd": state["var95_1d_usd"],
            "positions": len(raw),
            "limits": {"overall": limits["overall"], "breaches": limits["breaches"],
                       "warnings": limits["warnings"], "top_utilization": top},
            "track_record": {k: rec.get(k) for k in ("available", "observations", "total_return",
                                                    "annualized_vol", "sharpe", "max_drawdown")}}


async def _macro_block() -> Dict[str, Any]:
    from api.handlers.dashboard_handler import get_dashboard_data
    d = (await get_dashboard_data(mode="live")).model_dump()
    reg, rec, ens = d.get("regime") or {}, d.get("recession") or {}, d.get("ensemble") or {}
    model_regime, model_prob = None, None
    try:                                     # the systematic model's regime (cached; never blocks)
        from api.model.engine import _CACHE
        runs = [v[1] for v in _CACHE.values() if v[1].get("available")]
        if runs:
            latest = max(runs, key=lambda r: r["run_at"])
            model_regime = latest["regime"]["most_likely"]
            model_prob = latest["regime"]["probabilities"][model_regime]
    except Exception:
        pass
    return {"available": True, "regime": reg.get("current"), "regime_confidence": reg.get("confidenceScore"),
            "model_regime": model_regime, "model_regime_probability": model_prob,
            "regime_months": reg.get("duration"), "recession_probability": rec.get("probability"),
            "sahm": rec.get("sahmValue"), "ensemble_score": ens.get("score"),
            "conviction": ens.get("conviction"), "risk_budget": ens.get("riskBudget")}


@router.get("/api/v1/desk")
async def desk(request: Request):
    from api.core.access import current_user
    from api import blotter_store, portfolio_store
    from api.data_freshness import get_live_freshness
    from api.routers.fund import _order_view

    user = current_user(request)
    if not user:
        raise HTTPException(401, "Authentication required")
    role, username = user["role"], user["username"]

    async def _orders():
        await asyncio.to_thread(blotter_store.init_db)
        ideas = await asyncio.to_thread(portfolio_store.list_trade_ideas, None)
        return [_order_view(i) for i in ideas if i.get("side") and i.get("quantity")]

    async def _users():
        if role != "admin":
            return None
        from api.core import accounts
        return await asyncio.to_thread(accounts.list_users)

    async def _cb_moves():
        from api.main import get_global_macro_v1
        return (await get_global_macro_v1()).get("recent_policy_moves", [])

    async def _cycle():
        from api.main import get_cycle_risk_v1
        return await get_cycle_risk_v1()

    fund, macro, freshness, orders, users, cb, cyc = await asyncio.gather(
        _safe(_fund_block(), "fund"), _safe(_macro_block(), "macro"),
        _safe(asyncio.to_thread(get_live_freshness), "data freshness"),
        _safe(_orders(), "orders"), _safe(_users(), "users"), _safe(_cb_moves(), "global macro"),
        _safe(_cycle(), "cycle risk", timeout=60.0))
    order_list = orders if isinstance(orders, list) else []
    queue = build_queue(role, username, orders=order_list,
                        limits=fund.get("limits") if fund.get("available") else None,
                        freshness=freshness if freshness.get("available") else None,
                        users=users if isinstance(users, list) else None,
                        cb_moves=cb if isinstance(cb, list) else None,
                        cycle=cyc if isinstance(cyc, dict) and "turbulence" in cyc else None)
    counts: Dict[str, int] = {}
    for o in order_list:
        counts[o.get("state") or "?"] = counts.get(o.get("state") or "?", 0) + 1

    data = {"available": False}
    if freshness.get("available"):
        data = {"available": True, "score_pct": freshness.get("score_pct"),
                "categories": freshness.get("categories"), "unknown": freshness.get("unknown"),
                "prints": [{k: s.get(k) for k in ("metric", "name", "series_id", "latest_value", "unit",
                                                   "last_observation_date", "frequency", "status",
                                                   "state", "next_expected_release", "category")}
                           for s in freshness.get("series", [])]}
    return {"user": {"username": username, "role": role},
            "focus": ROLE_FOCUS.get(role, ROLE_FOCUS["analyst"]),
            "queue": queue, "fund": fund, "macro": macro, "data": data,
            "orders": {"by_state": counts, "available": isinstance(orders, list)},
            "as_of": datetime.now().isoformat()}
