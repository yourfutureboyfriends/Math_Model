"""
Hedge-fund layer endpoints: fund NAV & track record, risk limits with pre-trade
compliance, and the regime rebalance engine (target portfolio -> staged orders).

Math lives in api/calculations/{fund,limits,rebalance}.py (pure, tested); persistence in
api/fund_store.py. Pricing / VaR / liquidity reuse the existing portfolio helpers.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["fund"])


def _m():
    """api.main, imported lazily (it includes this router)."""
    from api import main
    return main


async def _thread(fn, *a):
    return await asyncio.to_thread(fn, *a)


async def _risk_free(settings: Dict[str, Any]) -> Optional[float]:
    if settings.get("risk_free_rate") is not None:
        return float(settings["risk_free_rate"])
    from api.handlers.macro_inputs import load_macro_inputs
    rf = (await load_macro_inputs())["dgs3mo"].latest
    return rf / 100.0 if rf is not None else None


async def _book_state(raw: List[Dict[str, Any]], settings: Dict[str, Any],
                      include_liquidity: bool = True) -> Dict[str, Any]:
    """NAV, exposures and every limit metric for a (possibly hypothetical) set of positions."""
    from api import fund_store
    from api.calculations.fund import compute_nav, exposures_pct_nav, drawdown_from_peak

    main = _m()
    enriched = await main._enrich_positions(raw) if raw else {"positions": [], "summary": {}}
    summary = enriched.get("summary") or {}
    nav = compute_nav(settings["capital"], summary.get("total_unrealized_pnl", 0.0),
                      settings.get("realized_pnl") or 0.0)
    exp = exposures_pct_nav(summary, nav)

    mvs = sorted((abs(p["market_value"]) for p in enriched.get("positions", [])
                  if isinstance(p.get("market_value"), (int, float))), reverse=True)
    risk = await main._risk_snapshot(raw) if raw else {"var_available": False}
    var95 = risk.get("var_95_1d") if risk.get("var_available") else None

    history = await _thread(fund_store.nav_history)
    dd = drawdown_from_peak([h["nav"] for h in history] + [nav])

    liq_days = None
    if include_liquidity and raw:
        try:
            liq = await asyncio.wait_for(main.risk_liquidity_v1(None), timeout=20)
            vals = [r["days_to_liquidate"] for r in liq.get("positions", []) if r.get("days_to_liquidate") is not None]
            liq_days = max(vals) if vals else None
        except Exception as e:
            logger.warning(f"[fund] liquidity check unavailable: {e}")

    metrics = {
        "gross_exposure": exp["gross"],
        "net_exposure_abs": abs(exp["net"]) if exp["net"] is not None else None,
        "single_name": (mvs[0] / nav) if mvs and nav else (0.0 if nav else None),
        "top5": (sum(mvs[:5]) / nav) if nav else None,
        "var95_1d": (var95 / nav) if var95 is not None and nav else None,
        "drawdown": abs(dd) if dd is not None else None,
        "liquidity_days": liq_days,
    }
    return {"nav": nav, "summary": summary, "exposures": exp, "metrics": metrics,
            "var95_1d_usd": var95, "positions": enriched.get("positions", [])}


# ── Fund settings & NAV ──────────────────────────────────────────────────────
class FundSettingsIn(BaseModel):
    fund_name: Optional[str] = None
    capital: Optional[float] = None
    base_currency: Optional[str] = None
    inception_date: Optional[str] = None
    vol_target: Optional[float] = None
    risk_free_rate: Optional[float] = None
    realized_pnl: Optional[float] = None
    cost_bps: Optional[float] = None
    min_trade_pct: Optional[float] = None


@router.get("/api/v1/fund/settings")
async def fund_settings():
    from api import fund_store
    return await _thread(fund_store.get_settings)


@router.put("/api/v1/fund/settings")
async def update_fund_settings(body: FundSettingsIn, request: Request):
    from api import fund_store, audit_store
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    if "capital" in changes and changes["capital"] <= 0:
        raise HTTPException(400, "capital must be positive")
    if "vol_target" in changes and not (0 < changes["vol_target"] <= 1):
        raise HTTPException(400, "vol_target must be in (0, 1]")
    before = await _thread(fund_store.get_settings)
    after = await _thread(fund_store.update_settings, changes)
    await _thread(lambda: audit_store.add_decision(
        "fund_settings_update", f"Fund settings changed: {sorted(changes)}",
        user=_m()._request_user(request), target="fund", before_state=before, after_state=after))
    return after


@router.get("/api/v1/fund/overview")
async def fund_overview():
    """NAV, exposures as % NAV, risk-limit status, and the recorded track record
    (plus a clearly-labelled pro-forma path for context)."""
    from api import fund_store, portfolio_store
    from api.calculations.fund import track_record, proforma_nav
    from api.calculations.limits import merge_limits, evaluate_limits
    from api.handlers.market_handler import _fetch_dated_closes_literal

    settings = await _thread(fund_store.get_settings)
    raw = await _thread(portfolio_store.list_positions, None)
    state = await _book_state(raw, settings)
    limits = merge_limits(await _thread(fund_store.get_limit_overrides))
    rf = await _risk_free(settings)

    history = await _thread(fund_store.nav_history)
    # NAV does not accrue interest on uninvested cash, so its P&L is already a return in
    # excess of cash; subtracting the T-bill rate again would penalize idle capital twice.
    record = track_record([h["nav"] for h in history], risk_free_annual=0.0)

    mv_by_sym: Dict[str, float] = {}
    for p in state["positions"]:
        if isinstance(p.get("market_value"), (int, float)):
            s = str(p["symbol"]).upper()
            mv_by_sym[s] = mv_by_sym.get(s, 0.0) + p["market_value"]
    dated = {s: await _fetch_dated_closes_literal(s) for s in mv_by_sym}
    pf = proforma_nav(state["nav"], mv_by_sym, dated)
    pf_stats = track_record(pf.get("nav", []), risk_free_annual=0.0) if pf else {"available": False}

    return {
        "fund": {k: settings[k] for k in ("fund_name", "capital", "base_currency", "inception_date",
                                         "vol_target", "realized_pnl")},
        "nav": state["nav"],
        "unrealized_pnl": state["summary"].get("total_unrealized_pnl"),
        "exposures": state["exposures"],
        "var95_1d_usd": state["var95_1d_usd"],
        "risk_free_rate": rf,
        "limits": evaluate_limits(state["metrics"], limits),
        "track_record": {**record, "history": history[-260:],
                         "basis": "recorded daily NAV snapshots; NAV excludes interest on idle "
                                  "cash, so Sharpe/Sortino are already excess-of-cash"},
        "proforma": {**pf, "stats": pf_stats,
                     "basis": "HYPOTHETICAL — today's positions held constant over the past year; "
                              "not the fund's actual track record"},
        "as_of": datetime.now().isoformat(),
    }


async def take_nav_snapshot() -> Dict[str, Any]:
    """Record today's NAV (idempotent per day). Also called by the daily scheduler."""
    from api import fund_store, portfolio_store
    settings = await _thread(fund_store.get_settings)
    raw = await _thread(portfolio_store.list_positions, None)
    state = await _book_state(raw, settings, include_liquidity=False)
    regime = None
    try:
        from api.handlers.dashboard_handler import get_dashboard_data
        regime = (await get_dashboard_data(mode="live")).regime.current
    except Exception:
        pass
    if not settings.get("inception_date"):
        await _thread(fund_store.update_settings, {"inception_date": date.today().isoformat()})
    return await _thread(fund_store.record_nav, {
        "date": date.today().isoformat(), "nav": state["nav"],
        "gross": state["exposures"]["gross"], "net": state["exposures"]["net"],
        "unrealized_pnl": state["summary"].get("total_unrealized_pnl"),
        "realized_pnl": settings.get("realized_pnl"),
        "var95_1d": state["var95_1d_usd"], "regime": regime, "positions": len(raw),
    })


@router.post("/api/v1/fund/snapshot")
async def fund_snapshot():
    return {"recorded": await take_nav_snapshot()}


# ── Risk limits & pre-trade compliance ───────────────────────────────────────
class LimitIn(BaseModel):
    soft: float
    hard: float


@router.get("/api/v1/risk/limits")
async def risk_limits():
    from api import fund_store, portfolio_store
    from api.calculations.limits import merge_limits, evaluate_limits
    settings = await _thread(fund_store.get_settings)
    raw = await _thread(portfolio_store.list_positions, None)
    state = await _book_state(raw, settings)
    limits = merge_limits(await _thread(fund_store.get_limit_overrides))
    return {"nav": state["nav"], **evaluate_limits(state["metrics"], limits),
            "as_of": datetime.now().isoformat()}


@router.put("/api/v1/risk/limits")
async def update_risk_limits(body: Dict[str, LimitIn], request: Request):
    from api import fund_store, audit_store
    from api.calculations.limits import DEFAULT_LIMITS, merge_limits
    unknown = [k for k in body if k not in DEFAULT_LIMITS]
    if unknown:
        raise HTTPException(400, f"unknown limit(s): {unknown}")
    for k, v in body.items():
        if v.soft < 0 or v.hard < 0 or v.soft > v.hard:
            raise HTTPException(400, f"{k}: need 0 <= soft <= hard")
    before = merge_limits(await _thread(fund_store.get_limit_overrides))
    await _thread(fund_store.set_limit_overrides, {k: v.model_dump() for k, v in body.items()})
    after = merge_limits(await _thread(fund_store.get_limit_overrides))
    await _thread(lambda: audit_store.add_decision(
        "risk_limits_update", f"Risk limits changed: {sorted(body)}",
        user=_m()._request_user(request), target="risk_limits", before_state=before, after_state=after))
    return after


class PretradeIn(BaseModel):
    symbol: str
    quantity: float               # signed: + buy, - sell/short
    book: Optional[str] = "Macro"


@router.post("/api/v1/risk/pretrade")
async def pretrade(body: PretradeIn):
    """Pre-trade compliance: limit metrics before vs after the trade → PASS / WARN / BLOCK."""
    from api import fund_store, portfolio_store
    from api.calculations.limits import merge_limits, pretrade_check
    from api.handlers.market_handler import _fetch_closes_literal
    sym = body.symbol.strip().upper()
    closes = await _fetch_closes_literal(sym)
    if not closes:
        raise HTTPException(404, f"No price history for {sym}")
    settings = await _thread(fund_store.get_settings)
    raw = await _thread(portfolio_store.list_positions, None)
    proposed = {"symbol": sym, "quantity": body.quantity, "avg_cost": closes[-1],
                "book": body.book or "Macro", "asset_class": "Equity"}
    before, after = await asyncio.gather(_book_state(raw, settings, include_liquidity=False),
                                         _book_state(raw + [proposed], settings, include_liquidity=False))
    limits = merge_limits(await _thread(fund_store.get_limit_overrides))
    result = pretrade_check(before["metrics"], after["metrics"], limits)
    return {"trade": {"symbol": sym, "quantity": body.quantity, "price": round(closes[-1], 2),
                      "notional": round(body.quantity * closes[-1], 2),
                      "pct_nav": round(body.quantity * closes[-1] / before["nav"], 4) if before["nav"] else None},
            **result, "nav": before["nav"], "as_of": datetime.now().isoformat()}


# ── Rebalance engine ─────────────────────────────────────────────────────────
@router.get("/api/v1/portfolio/rebalance")
async def rebalance(book: str = "Macro", regime: Optional[str] = None,
                    vol_target: Optional[float] = None, sleeve_pct: float = 1.0):
    """Regime-tilted, risk-budgeted, vol-targeted target portfolio for `book` and the
    orders to get there. sleeve_pct = fraction of fund NAV allocated to this book."""
    from api import fund_store, portfolio_store
    from api.calculations.rebalance import UNIVERSE, target_portfolio, rebalance_orders
    from api.calculations.factor_model import returns_from_closes
    from api.calculations.limits import merge_limits
    from api.handlers.market_handler import _fetch_dated_closes_literal

    settings = await _thread(fund_store.get_settings)
    if regime is None:
        from api.handlers.dashboard_handler import get_dashboard_data
        regime = (await get_dashboard_data(mode="live")).regime.current
    limits = merge_limits(await _thread(fund_store.get_limit_overrides))

    dated = {a: await _fetch_dated_closes_literal(a) for a in UNIVERSE}
    common = None
    for d in dated.values():
        if d:
            common = set(d) if common is None else common & set(d)
    dates = sorted(common or [])
    rets = {a: returns_from_closes([dated[a][x] for x in dates]) for a in UNIVERSE if dated[a]}
    tp = target_portfolio(regime, rets, vol_target=vol_target or settings["vol_target"],
                          max_gross=limits["gross_exposure"]["soft"])
    if not tp.get("available"):
        return tp

    raw_all = await _thread(portfolio_store.list_positions, None)
    state = await _book_state(raw_all, settings, include_liquidity=False)
    sleeve_nav = state["nav"] * max(0.0, min(sleeve_pct, 1.0))
    raw_book = [p for p in raw_all if (p.get("book") or "Macro") == book]
    current: Dict[str, float] = {}
    for p in raw_book:
        s = str(p["symbol"]).upper()
        current[s] = current.get(s, 0.0) + float(p["quantity"])
    prices = {a: dated[a][dates[-1]] for a in rets}
    from api.handlers.market_handler import _fetch_closes_literal
    for s in current:
        if s not in prices:
            c = await _fetch_closes_literal(s)
            if c:
                prices[s] = c[-1]
    orders = rebalance_orders({w["symbol"]: w["weight"] for w in tp["weights"]}, sleeve_nav,
                              prices, current, settings["min_trade_pct"], settings["cost_bps"])
    return {**tp, "book": book, "sleeve_nav": round(sleeve_nav, 2), **orders,
            "as_of": datetime.now().isoformat(),
            "method": "Regime-tilted risk budgeting (ERC with playbook budgets), scaled to the "
                      "vol target and capped at the soft gross-exposure limit."}


class StageIn(BaseModel):
    book: str = "Macro"
    orders: List[Dict[str, Any]]
    regime: Optional[str] = None


@router.post("/api/v1/portfolio/rebalance/stage")
async def stage_rebalance(body: StageIn, request: Request):
    """Send rebalance orders into the trade-idea workflow (state 'Proposed') for PM/risk
    approval, and record the decision in the audit trail."""
    from api import portfolio_store, audit_store
    user = _m()._request_user(request)
    created = []
    for o in body.orders:
        idea = await _thread(lambda o=o: portfolio_store.add_trade_idea({
            "symbol": o["symbol"], "direction": "LONG" if o.get("side") == "BUY" else "SHORT",
            "thesis": f"Rebalance ({body.regime or 'current regime'}): {o.get('action', 'ADJUST')} "
                      f"{o.get('side')} {o.get('quantity')} @ ~{o.get('price')}",
            "conviction": "MEDIUM", "rationale": "Regime rebalance engine",
            "suggested_size": o.get("quantity"), "book": body.book}, user))
        created.append(idea)
    await _thread(lambda: audit_store.add_decision(
        "rebalance_staged", f"{len(created)} rebalance orders staged for approval ({body.book})",
        user=user, target=body.book, after_state={"orders": body.orders}))
    return {"staged": len(created), "ideas": created}
