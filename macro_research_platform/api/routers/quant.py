"""Quant Lab (build/backtest your own systematic strategies), the Quant Trader (paper-trades
deployed strategies) and the Macro Trader (paper-trades the macro model) — api/quant,
api/macro_trader."""
import asyncio
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(tags=["quant"])
_results: "OrderedDict[tuple, tuple]" = OrderedDict()
_RESULT_TTL = 1800
_sem = asyncio.Semaphore(2)               # at most two backtests at once


class SpecIn(BaseModel):
    spec: Dict[str, Any]
    strategy_id: Optional[int] = None


class SweepIn(BaseModel):
    spec: Dict[str, Any]
    params: Dict[str, List[float]]
    strategy_id: Optional[int] = None


class CombineIn(BaseModel):
    members: List[Dict[str, Any]]          # [{"strategy_id": 3} | {"template": "id"} | {"spec": {...}}]
    method: str = "erc"


class SaveIn(BaseModel):
    spec: Dict[str, Any]
    template: Optional[str] = None


class DeployIn(BaseModel):
    spec: Optional[Dict[str, Any]] = None
    strategy_id: Optional[int] = None
    template: Optional[str] = None
    capital: float = 1_000_000.0
    book: Optional[str] = None          # macro | fundamental | technical — checked against what the strategy trades


class ExprIn(BaseModel):
    formula: str


def _user(request: Request, roles=("pm", "quant", "analyst", "risk")) -> Dict[str, Any]:
    from api.core.access import require_roles
    return require_roles(request, set(roles))


def _spec_error(e: Exception):
    raise HTTPException(400, str(e))


async def _bt(fn, *a, **k):
    async with _sem:
        return await asyncio.wait_for(asyncio.to_thread(fn, *a, **k), timeout=240)


# ── Quant Lab ────────────────────────────────────────────────────────────────
@router.get("/api/v1/quant/meta")
async def quant_meta():
    from api.quant import data, engine, expr, templates, trader
    return {"functions": expr.catalogue(),
            "universes": [{"id": k, "label": v["label"], "symbols": v["symbols"], "note": v["note"],
                           "survivorship": bool(v.get("survivorship"))} for k, v in data.PRESETS.items()],
            "templates": [{**{k: t[k] for k in ("id", "name", "family", "description", "evidence", "citation", "spec")},
                           "book": trader.classify(t["spec"])} for t in templates.TEMPLATES],
            "research": templates.RESEARCH_NOTES,
            "options": {"selection": engine.SELECTION_MODES, "weighting": engine.WEIGHTINGS,
                        "rebalance": engine.REBALANCE, "execution": engine.EXECUTION},
            "limits": {"max_symbols": data.MAX_SYMBOLS, "max_sweep": 36}}


@router.post("/api/v1/quant/validate")
async def quant_validate(body: ExprIn):
    from api.quant import expr
    try:
        expr.parse(body.formula)
        return {"ok": True}
    except expr.ExprError as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/v1/quant/backtest")
async def quant_backtest(body: SpecIn, request: Request):
    from api.quant import backtest, engine, store
    user = _user(request)["username"]
    try:
        spec = engine.normalize(body.spec)
    except engine.SpecError as e:
        _spec_error(e)
    h = engine.spec_hash(spec)
    n, sharpes = await asyncio.to_thread(store.trials, user, body.strategy_id, h)
    key = (h, n, spec["name"])
    hit = _results.get(key)
    if hit and time.time() - hit[0] < _RESULT_TTL:
        return hit[1]
    try:
        res = await _bt(backtest.run, spec, n, sharpes)
    except engine.SpecError as e:
        _spec_error(e)
    except asyncio.TimeoutError:
        raise HTTPException(504, "The backtest took too long — try fewer symbols or a later start date.")
    res["trials_note"] = (f"This is variant #{n} you have tested{' for this strategy' if body.strategy_id else ''}; "
                          "the Deflated Sharpe corrects for all of them.")
    await asyncio.to_thread(store.record_run, user, body.strategy_id, h, res["metrics"].get("sharpe"))
    _results[key] = (time.time(), res)
    while len(_results) > 24:
        _results.popitem(last=False)
    return res


@router.post("/api/v1/quant/sweep")
async def quant_sweep(body: SweepIn, request: Request):
    from api.quant import backtest, engine, store
    user = _user(request)["username"]
    try:
        n_prior, _ = await asyncio.to_thread(store.trials, user, body.strategy_id, "sweep")
        res = await _bt(backtest.sweep, body.spec, body.params, max(0, n_prior - 1))
    except engine.SpecError as e:
        _spec_error(e)
    except asyncio.TimeoutError:
        raise HTTPException(504, "The sweep took too long — use fewer combinations.")
    for i, row in enumerate(res["rows"]):
        await asyncio.to_thread(store.record_run, user, body.strategy_id, f"sweep:{body.params}:{i}", row["sharpe"])
    return res


def _member_spec(m: Dict[str, Any]) -> Dict[str, Any]:
    from api.quant import store, templates
    if m.get("strategy_id"):
        s = store.get_strategy(int(m["strategy_id"]))
        if not s:
            raise HTTPException(404, f"strategy {m['strategy_id']} not found")
        return s["spec"]
    if m.get("template"):
        try:
            return templates.get(m["template"])
        except KeyError:
            raise HTTPException(404, f"template {m['template']} not found")
    if m.get("spec"):
        return m["spec"]
    raise HTTPException(400, "each member needs strategy_id, template or spec")


@router.post("/api/v1/quant/combine")
async def quant_combine(body: CombineIn, request: Request):
    from api.quant import backtest, engine
    _user(request)
    if body.method not in ("erc", "equal", "inverse_vol"):
        raise HTTPException(400, "method must be erc, equal or inverse_vol")
    specs = [_member_spec(m) for m in body.members]
    try:
        return await _bt(backtest.combine, specs, body.method)
    except engine.SpecError as e:
        _spec_error(e)
    except asyncio.TimeoutError:
        raise HTTPException(504, "Combining took too long — use fewer strategies.")


@router.get("/api/v1/quant/strategies")
async def quant_strategies(request: Request):
    from api.quant import store
    _user(request)
    return {"strategies": await asyncio.to_thread(store.list_strategies)}


@router.post("/api/v1/quant/strategies")
async def quant_save(body: SaveIn, request: Request):
    from api.quant import engine, store
    user = _user(request, ("pm", "quant", "analyst"))["username"]
    try:
        spec = engine.normalize(body.spec)
    except engine.SpecError as e:
        _spec_error(e)
    return await asyncio.to_thread(store.save_strategy, user, spec, None, body.template)


@router.put("/api/v1/quant/strategies/{sid}")
async def quant_update(sid: int, body: SaveIn, request: Request):
    from api.quant import engine, store
    u = _user(request, ("pm", "quant", "analyst"))
    cur = await asyncio.to_thread(store.get_strategy, sid)
    if not cur:
        raise HTTPException(404, "strategy not found")
    if cur["owner"] != u["username"] and u["role"] != "admin":
        raise HTTPException(403, "only the owner can edit this strategy")
    try:
        spec = engine.normalize(body.spec)
    except engine.SpecError as e:
        _spec_error(e)
    return await asyncio.to_thread(store.save_strategy, cur["owner"], spec, sid)


@router.delete("/api/v1/quant/strategies/{sid}")
async def quant_delete(sid: int, request: Request):
    from api.quant import store
    u = _user(request, ("pm", "quant", "analyst"))
    cur = await asyncio.to_thread(store.get_strategy, sid)
    if not cur:
        raise HTTPException(404, "strategy not found")
    if cur["owner"] != u["username"] and u["role"] != "admin":
        raise HTTPException(403, "only the owner can delete this strategy")
    await asyncio.to_thread(store.delete_strategy, sid)
    return {"deleted": sid}


# ── Quant Trader ─────────────────────────────────────────────────────────────
@router.get("/api/v1/quant/trader")
async def quant_trader(request: Request, refresh: bool = False, book: str = Query("macro", pattern="^(macro|fundamental|technical)$")):
    """One trader's book — macro (asset classes), fundamental (stocks on company data) or technical (stocks on price/volume)."""
    from api.quant import trader
    _user(request)
    try:
        return await _bt(trader.book, refresh, book)
    except asyncio.TimeoutError:
        raise HTTPException(504, "Updating the Quant Trader took too long — try again shortly.")


@router.post("/api/v1/quant/trader/deploy")
async def quant_deploy(body: DeployIn, request: Request):
    from api.quant import engine, trader
    u = _user(request, ("pm", "quant"))
    spec = body.spec or _member_spec({"strategy_id": body.strategy_id, "template": body.template})
    try:
        d = await _bt(trader.deploy, u["username"], spec, body.capital, body.strategy_id, body.book)
    except engine.SpecError as e:
        _spec_error(e)
    await asyncio.to_thread(_audit, u["username"], "quant_deploy",
                            f"Deployed '{d['name']}' to the {trader.BOOK_LABEL.get(d.get('book'), 'Macro')} Quant Trader with ${body.capital:,.0f} (live from {d['deployed_at']})")
    return d


@router.delete("/api/v1/quant/trader/deployments/{did}")
async def quant_undeploy(did: int, request: Request):
    from api.quant import store, trader
    u = _user(request, ("pm", "quant"))
    d = await asyncio.to_thread(store.get_deployment, did)
    if not d:
        raise HTTPException(404, "deployment not found")
    await asyncio.to_thread(store.stop_deployment, did)
    trader.invalidate()
    await asyncio.to_thread(_audit, u["username"], "quant_stop", f"Stopped '{d['name']}' in the Quant Trader")
    return {"stopped": did}


# ── Macro Trader ─────────────────────────────────────────────────────────────
class MacroSettingsIn(BaseModel):
    enabled: Optional[bool] = None
    portfolio: Optional[str] = None
    drift_threshold: Optional[float] = None
    cost_bps: Optional[float] = None


class MacroResetIn(BaseModel):
    capital: Optional[float] = None


class DeepIn(BaseModel):
    spec: Optional[Dict[str, Any]] = None
    strategy_id: Optional[int] = None
    template: Optional[str] = None
    deployment_id: Optional[int] = None


@router.post("/api/v1/quant/deep")
async def quant_deep(body: DeepIn, request: Request):
    """In-depth analysis of a Quant Lab strategy or a live deployment (any of the three traders)."""
    from api.quant import backtest, deep, engine, store, trader
    _user(request)
    dep = None
    if body.deployment_id:
        dep = await asyncio.to_thread(store.get_deployment, body.deployment_id)
        if not dep:
            raise HTTPException(404, "deployment not found")
        spec = dep["spec"]
    else:
        spec = body.spec or _member_spec({"strategy_id": body.strategy_id, "template": body.template})

    def build():
        res = backtest.run(spec, light=True)
        rep = deep.report(res["daily_dates"], res["daily_returns"], 252, res.get("daily_benchmark"),
                          label=res["spec"].get("name") or "Strategy", benchmark_label=res["spec"].get("benchmark") or "Benchmark")
        rep["book"] = trader.classify(res["spec"])
        if dep:
            rep["deployed_at"] = dep["deployed_at"]
            live = [r for d, r in zip(res["daily_dates"], res["daily_returns"]) if d > dep["deployed_at"]]
            rep["live_days"] = len(live)
        return rep
    try:
        return await _bt(build)
    except engine.SpecError as e:
        _spec_error(e)


@router.get("/api/v1/macro-trader/deep")
async def macro_trader_deep(request: Request, series: str = Query("tactical", pattern="^(tactical|strategic|all_weather)$")):
    """In-depth analysis of the Macro Quant Trader's model books (walk-forward backtests)."""
    from api.quant import deep
    _user(request)
    if series == "all_weather":
        from api.marketdata import bridgewater
        aw = await asyncio.to_thread(bridgewater.all_weather, 0.10, 2.0)
        rows = aw["curves"]
        dates = [r["date"] for r in rows]
        s_ = [rows[i]["aw"] / rows[i - 1]["aw"] - 1 if i else 0.0 for i in range(len(rows))]
        b_ = [rows[i]["6040"] / rows[i - 1]["6040"] - 1 if i else 0.0 for i in range(len(rows))]
        return await asyncio.to_thread(deep.report, dates[1:], s_[1:], 52, b_[1:], None, "All Weather (unlevered)", "60/40")
    from api.model.engine import run_model
    res = await run_model(None, user="system")
    bt = (res or {}).get("backtest") or {}
    curve = bt.get("equity_curve") or []
    if not curve:
        raise HTTPException(503, "The macro model backtest isn't available yet.")
    key = "model" if series == "tactical" else "strategic"
    # the book's full history; the 60/40 benchmark is blank (NaN) before both of its legs exist
    rows = [c for c in curve if c.get(key) is not None]
    dates = [pd_month_end(c["month"]) for c in rows]
    # the curve is growth of $1 *after* each month, so the first point is (1 + first month's return)
    s_ = [rows[0][key] - 1] + [rows[i][key] / rows[i - 1][key] - 1 for i in range(1, len(rows))]
    nan = float("nan")
    b_ = [nan] + [rows[i]["sixty_forty"] / rows[i - 1]["sixty_forty"] - 1 if rows[i].get("sixty_forty") is not None
                  and rows[i - 1].get("sixty_forty") is not None else nan for i in range(1, len(rows))]
    label = "Tactical model book (net of costs)" if series == "tactical" else "Strategic model book (net of costs)"
    rep = await asyncio.to_thread(deep.report, dates, s_, 12, b_, None, label, "60/40")
    if bt.get("returns_are"):
        rep["notes"].insert(0, f"The model book's returns are {bt['returns_are']} — add the T-bill rate for total returns. "
                               "The 60/40 benchmark is measured the same way.")
    return rep


def pd_month_end(m: str) -> str:
    import calendar
    y, mo = int(m[:4]), int(m[5:7])
    return f"{y}-{mo:02d}-{calendar.monthrange(y, mo)[1]:02d}"


@router.get("/api/v1/macro-trader")
async def macro_trader_status(request: Request):
    from api import macro_trader
    _user(request)
    return await macro_trader.status()


@router.post("/api/v1/macro-trader/run")
async def macro_trader_run(request: Request):
    from api import macro_trader
    u = _user(request, ("pm",))
    res = await macro_trader.run(force=True)
    await asyncio.to_thread(_audit, u["username"], "macro_run",
                            f"Macro trader run: {res.get('filled', 0)} filled, {res.get('orders', 0)} new orders"
                            + (" (rebalanced)" if res.get("rebalanced") else ""))
    return res


@router.put("/api/v1/macro-trader/settings")
async def macro_trader_settings(body: MacroSettingsIn, request: Request):
    from api import macro_trader
    u = _user(request, ("pm",))
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        s = await asyncio.to_thread(macro_trader.update_settings, changes)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await asyncio.to_thread(_audit, u["username"], "macro_settings",
                            "Macro trader settings: " + ", ".join(f"{k} → {v}" for k, v in changes.items()))
    return s


@router.post("/api/v1/macro-trader/reset")
async def macro_trader_reset(body: MacroResetIn, request: Request):
    from api import macro_trader
    u = _user(request, ())                                   # admin only
    try:
        await asyncio.to_thread(macro_trader.reset, body.capital)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await asyncio.to_thread(_audit, u["username"], "macro_reset", "Macro trader reset")
    return await macro_trader.status()


def _audit(user: str, action: str, text: str) -> None:
    try:
        from api import audit_store
        audit_store.add_decision(action, text, user=user, target="trader")
    except Exception:
        pass
