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


async def _bt(fn, *a, _timeout: float = 240, **k):
    async with _sem:
        return await asyncio.wait_for(asyncio.to_thread(fn, *a, **k), timeout=_timeout)


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


def _saved_spec(spec_in: Dict[str, Any]) -> Dict[str, Any]:
    """Code strategies are checked statically (never run); formula specs are normalised as before."""
    from api.quant import engine, sandbox
    if (spec_in or {}).get("kind") == "code":
        try:
            sandbox.check(spec_in.get("code") or "")
        except sandbox.SandboxError as e:
            _spec_error(e)
        return {"kind": "code", "name": str(spec_in.get("name") or "Untitled strategy")[:80],
                "description": str(spec_in.get("description") or "")[:1000], "code": spec_in["code"]}
    try:
        return engine.normalize(spec_in)
    except engine.SpecError as e:
        _spec_error(e)


@router.get("/api/v1/quant/strategies")
async def quant_strategies(request: Request):
    from api.quant import store
    _user(request)
    return {"strategies": await asyncio.to_thread(store.list_strategies)}


@router.post("/api/v1/quant/strategies")
async def quant_save(body: SaveIn, request: Request):
    from api.quant import engine, store
    user = _user(request, ("pm", "quant", "analyst"))["username"]
    spec = _saved_spec(body.spec)
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
    spec = _saved_spec(body.spec)
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


# ── Code Lab ─────────────────────────────────────────────────────────────────
class AnalyzeIn(BaseModel):
    dates: List[str]
    returns: List[float]
    benchmark: Optional[List[float]] = None
    label: str = "Strategy"
    benchmark_label: str = "SPY"
    mc_years: float = 10.0
    mc_paths: int = 2000
    max_leverage: float = 2.0
    dd_limit: float = 0.5
    provenance: Optional[Dict[str, Any]] = None     # from the engine; registers the run as a trial


class CodeCheckIn(BaseModel):
    code: str


@router.get("/api/v1/quant/code/engine")
async def code_engine(request: Request):
    """The backtest engine's source — loaded by the browser so tests run the exact server code."""
    from fastapi.responses import PlainTextResponse
    from api.quant import sandbox
    _user(request)
    return PlainTextResponse(sandbox.ENGINE.read_text(), headers={"Cache-Control": "private, max-age=300"})


@router.get("/api/v1/quant/code/data")
async def code_data(request: Request, universe: str = Query(..., max_length=1200), start: str = "2005-01-01",
                    benchmark: str = "SPY"):
    """Prices, T-bill rate and VIX for a strategy's UNIVERSE (float32, base64) for the browser."""
    from api.quant import codeserver
    _user(request)
    try:
        return await _bt(codeserver.data_payload, [u for u in universe.split(",") if u.strip()], start[:10], benchmark.upper())
    except ValueError as e:
        _spec_error(e)


class JobIn(BaseModel):
    code: str
    costs: Optional[Dict[str, float]] = None


@router.post("/api/v1/quant/code/jobs")
async def code_job_submit(body: JobIn, request: Request):
    """Run a strategy that needs the server (TRADABLE_UNIVERSE: hundreds of tickers) as a background job in the
    sandbox. Poll GET …/jobs/{id}; DELETE cancels."""
    from api.quant import jobs, sandbox
    u = _user(request)
    try:
        head = sandbox.check(body.code)
    except sandbox.SandboxError as e:
        _spec_error(e)
    if not head.get("tradable"):
        raise HTTPException(400, "Only TRADABLE_UNIVERSE strategies run as server jobs — others run in your browser.")
    try:
        j = jobs.submit(u["username"], "code_run", lambda job: sandbox.run(body.code, body.costs, job))
    except ValueError as e:
        raise HTTPException(429, str(e))
    return j.view(False)


@router.get("/api/v1/quant/code/jobs/{job_id}")
async def code_job_status(job_id: str, request: Request):
    from api.quant import jobs
    u = _user(request)
    j = jobs.get(job_id, u["username"], u["role"] == "admin")
    if not j:
        raise HTTPException(404, "Unknown job (finished jobs are kept for an hour; a server restart clears them).")
    return j.view()


@router.delete("/api/v1/quant/code/jobs/{job_id}")
async def code_job_cancel(job_id: str, request: Request):
    from api.quant import jobs
    u = _user(request)
    return {"cancelled": jobs.cancel(job_id, u["username"], u["role"] == "admin")}


@router.post("/api/v1/quant/code/check")
async def code_check(body: CodeCheckIn, request: Request):
    """Static check against the deploy sandbox's rules (does not run the code)."""
    from api.quant import sandbox
    _user(request)
    try:
        return {"ok": True, **sandbox.check(body.code)}
    except sandbox.SandboxError as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/v1/quant/code/analyze")
async def code_analyze(body: AnalyzeIn, request: Request):
    """Deep analysis + Monte Carlo (bootstrap, leverage/Kelly) of a daily return series — numbers only."""
    from api.quant import codeserver
    u = _user(request)
    if not 1 <= body.mc_years <= 30 or not 200 <= body.mc_paths <= 5000 or not 1 <= body.max_leverage <= 4 or not 0.1 <= body.dd_limit <= 0.9:
        raise HTTPException(400, "Monte Carlo: 1–30 years, 200–5000 paths, max leverage 1–4×, drawdown limit 10–90%.")
    try:
        return await _bt(codeserver.analyze, body.dates, body.returns, body.benchmark, body.label, body.benchmark_label,
                         body.mc_years, body.mc_paths, body.max_leverage, body.dd_limit, u["username"], body.provenance)
    except ValueError as e:
        _spec_error(e)


@router.get("/api/v1/quant/library")
async def strategy_library(request: Request):
    from api.quant import library
    _user(request)
    return {"strategies": await asyncio.to_thread(library.summaries), "notes": library.__doc__}


@router.get("/api/v1/quant/smartmoney/latest")
async def smartmoney_latest(request: Request):
    """Latest 13F top holdings of the tracked institutions (built from cached SEC filings)."""
    from api.quant import smartmoney
    _user(request)
    try:
        return await _bt(smartmoney.latest_view)
    except asyncio.TimeoutError:
        raise HTTPException(504, "Reading the 13F filings took too long — try again shortly.")


@router.get("/api/v1/quant/library/{sid}")
async def strategy_library_result(sid: str, request: Request, refresh: bool = False):
    from api.quant import library
    _user(request)
    try:
        library.get(sid)
    except KeyError:
        raise HTTPException(404, "Unknown strategy")
    try:
        return await _bt(library.result, sid, refresh)
    except asyncio.TimeoutError:
        raise HTTPException(504, "Evaluating this strategy took too long — try again shortly.")


# ── Quant Trader ─────────────────────────────────────────────────────────────
@router.get("/api/v1/quant/trader")
async def quant_trader(request: Request, refresh: bool = False, book: str = Query("macro", pattern="^(macro|fundamental|technical)$")):
    """One trader's book — macro (asset classes), fundamental (stocks on company data) or technical (stocks on price/volume)."""
    from api.quant import trader
    _user(request)
    try:
        return await _bt(trader.book, refresh, book, _timeout=900)     # large-universe code strategies run in the sandbox
    except asyncio.TimeoutError:
        raise HTTPException(504, "Updating the Quant Trader took too long — try again shortly.")


@router.post("/api/v1/quant/trader/deploy")
async def quant_deploy(body: DeployIn, request: Request):
    from api.quant import engine, trader
    u = _user(request, ("pm", "quant"))
    spec = body.spec or _member_spec({"strategy_id": body.strategy_id, "template": body.template})
    try:
        d = await _bt(trader.deploy, u["username"], spec, body.capital, body.strategy_id, body.book, _timeout=900)
    except engine.SpecError as e:
        _spec_error(e)
    except asyncio.TimeoutError:
        raise HTTPException(504, "Deploying took longer than 15 minutes (a first download of hundreds of tickers?) — "
                                 "try again; the data is cached now.")
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
        if (spec or {}).get("kind") in ("code", "library"):
            cres = trader.eval_code_spec(spec)
            res = {"daily_dates": cres["dates"], "daily_returns": cres["returns"], "daily_benchmark": cres.get("benchmark"),
                   "spec": {"name": spec.get("name"), "benchmark": "SPY", **spec}}
        else:
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


# ── Relative value & market making ─────────────────────────────────────────
@router.get("/api/v1/quant/pairs/scan")
async def pairs_scan(request: Request, preset: Optional[str] = None, symbols: Optional[str] = None,
                     years: float = Query(2.0, ge=0.5, le=10), min_corr: float = Query(0.4, ge=0, le=0.99)):
    """Engle–Granger cointegration scan of every pair in a universe."""
    from api.quant import data, pairs
    _user(request)
    try:
        syms = data.resolve_universe({"preset": preset} if preset else {"symbols": (symbols or "").split(",")})[0]
        return await _bt(pairs.scan, syms, years, 25, min_corr)
    except (ValueError, pairs.PairsError) as e:
        _spec_error(e)
    except asyncio.TimeoutError:
        raise HTTPException(504, "The pairs scan took too long — try fewer tickers.")


@router.get("/api/v1/quant/pairs/backtest")
async def pairs_backtest(request: Request, a: str, b: str, lookback: int = 252, entry: float = 2.0, exit: float = 0.5,
                         stop: float = 4.0, max_hold: int = 60, bps: float = 3.0, start: Optional[str] = None):
    """Rolling-window (no look-ahead) z-score backtest of one pair."""
    from api.quant import pairs
    _user(request)
    try:
        return await _bt(pairs.backtest, a, b, lookback, entry, exit, stop, max_hold, bps, start)
    except pairs.PairsError as e:
        _spec_error(e)


@router.get("/api/v1/quant/mm")
async def market_making(request: Request, symbol: str = "SPY", interval: str = Query("1m", pattern="^(1m|2m|5m)$"),
                        half_spread_bps: float = 1.0, aversion: float = 1.0, max_inventory: int = 10,
                        lot: int = 100, rebate_per_share: float = 0.0):
    """Avellaneda–Stoikov market-making simulation on intraday bars vs symmetric quoting."""
    from api.marketdata import core
    from api.quant import mm
    _user(request)
    try:
        return await _bt(mm.simulate, symbol, interval, half_spread_bps, aversion, max_inventory, lot, rebate_per_share)
    except ValueError as e:
        _spec_error(e)
    except core.NotFound as e:
        raise HTTPException(404, str(e))
    except core.Upstream as e:
        raise HTTPException(503, str(e))


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
