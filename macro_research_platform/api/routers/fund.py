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


async def _factor_dollar_exposures(positions: List[Dict[str, Any]]) -> Dict[str, float]:
    """$ exposure per factor = Σ market_value_i × beta_i,f (OLS betas on the long-short
    factor set, ~1y of daily returns). Positions without enough history are skipped."""
    from api.calculations.factor_model import (
        FACTOR_TICKERS, build_factor_returns, estimate_factor_loadings, returns_from_closes)
    from api.handlers.market_handler import _fetch_dated_closes_literal

    priced = [p for p in positions if isinstance(p.get("market_value"), (int, float))]
    if not priced:
        return {}
    tick = {t: await _fetch_dated_closes_literal(t) for t in FACTOR_TICKERS}
    common = None
    for d in tick.values():
        common = set(d) if common is None else common & set(d)
    common = sorted(common or [])
    out: Dict[str, float] = {}
    for p in priced:
        d = await _fetch_dated_closes_literal(str(p["symbol"]).upper())
        dates = [x for x in common if x in d]
        if len(dates) < 61:
            continue
        fac = build_factor_returns({t: returns_from_closes([tick[t][x] for x in dates]) for t in FACTOR_TICKERS})
        betas = estimate_factor_loadings(returns_from_closes([d[x] for x in dates]), fac)
        for f, b in betas.items():
            out[f] = out.get(f, 0.0) + p["market_value"] * b
    return out


async def _book_state(raw: List[Dict[str, Any]], settings: Dict[str, Any],
                      include_liquidity: bool = True, include_factors: bool = True) -> Dict[str, Any]:
    """NAV, cash, exposures and every limit metric for a (possibly hypothetical) set of positions."""
    from api import fund_store, blotter_store
    from api.calculations.fund import compute_nav, exposures_pct_nav, drawdown_from_peak
    from api.calculations.blotter import blotter_totals, cash_balance

    main = _m()
    enriched = await main._enrich_positions(raw) if raw else {"positions": [], "summary": {}}
    summary = enriched.get("summary") or {}
    totals = blotter_totals(await _thread(blotter_store.list_trades))
    realized = totals["realized_pnl"] + float(settings.get("realized_pnl") or 0.0)  # + manual adj.
    nav = compute_nav(settings["capital"], summary.get("total_unrealized_pnl", 0.0),
                      realized - totals["commissions"])
    cash = cash_balance(settings["capital"], raw, realized, totals["commissions"])
    exp = exposures_pct_nav(summary, nav)

    positions = enriched.get("positions", [])
    by_symbol: Dict[str, float] = {}
    by_class: Dict[str, float] = {}
    for p in positions:
        mv = p.get("market_value")
        if isinstance(mv, (int, float)):
            # Net per symbol across rows/books, so one name split over rows can't dodge the limit.
            s = str(p["symbol"]).upper()
            by_symbol[s] = by_symbol.get(s, 0.0) + mv
            c = p.get("asset_class") or "Unassigned"
            by_class[c] = by_class.get(c, 0.0) + abs(mv)
    mvs = sorted((abs(v) for v in by_symbol.values()), reverse=True)

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

    factor_usd: Dict[str, float] = {}
    if include_factors and positions:
        try:
            factor_usd = await asyncio.wait_for(_factor_dollar_exposures(positions), timeout=30)
        except Exception as e:
            logger.warning(f"[fund] factor exposure unavailable: {e}")

    def _pct(v):
        return (abs(v) / nav) if (v is not None and nav) else None

    metrics = {
        "gross_exposure": exp["gross"],
        "net_exposure_abs": abs(exp["net"]) if exp["net"] is not None else None,
        "single_name": (mvs[0] / nav) if mvs and nav else (0.0 if nav else None),
        "top5": (sum(mvs[:5]) / nav) if nav else None,
        "var95_1d": (var95 / nav) if var95 is not None and nav else None,
        "drawdown": abs(dd) if dd is not None else None,
        "liquidity_days": liq_days,
        "equity_beta_abs": _pct(factor_usd.get("equity")) if factor_usd else (0.0 if not positions else None),
        "rates_beta_abs": _pct(factor_usd.get("rates")) if factor_usd else (0.0 if not positions else None),
        "asset_class_max": (max(by_class.values()) / nav) if by_class and nav else (0.0 if nav else None),
    }
    return {"nav": nav, "cash": cash, "realized_pnl": round(realized, 2),
            "commissions": totals["commissions"], "summary": summary, "exposures": exp,
            "metrics": metrics, "var95_1d_usd": var95, "positions": positions,
            "factor_exposure_usd": {k: round(v, 2) for k, v in factor_usd.items()}}


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
    from api.core.access import require_roles
    require_roles(request, {"risk"})
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
        "cash": state["cash"],
        "realized_pnl": state["realized_pnl"],
        "commissions": state["commissions"],
        "factor_exposure_usd": state["factor_exposure_usd"],
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
        "realized_pnl": state["realized_pnl"],
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
    from api.core.access import require_roles
    require_roles(request, {"risk"})
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


async def _run_pretrade(symbol: str, quantity: float, book: str) -> Dict[str, Any]:
    """Limit metrics before vs after adding `quantity` of `symbol` to `book`."""
    from api import fund_store, portfolio_store
    from api.calculations.limits import merge_limits
    from api.handlers.market_handler import _fetch_closes_literal
    sym = symbol.strip().upper()
    closes = await _fetch_closes_literal(sym)
    if not closes:
        raise HTTPException(404, f"No price history for {sym}")
    settings = await _thread(fund_store.get_settings)
    raw = await _thread(portfolio_store.list_positions, None)
    proposed = {"symbol": sym, "quantity": quantity, "avg_cost": closes[-1],
                "book": book or "Macro", "asset_class": "Equity"}
    before, after = await asyncio.gather(_book_state(raw, settings, include_liquidity=False),
                                         _book_state(raw + [proposed], settings, include_liquidity=False))
    return _pretrade_result(sym, quantity, closes[-1], before, after,
                            merge_limits(await _thread(fund_store.get_limit_overrides)))


@router.post("/api/v1/risk/pretrade")
async def pretrade(body: PretradeIn):
    """Pre-trade compliance: limit metrics before vs after the trade → PASS / WARN / BLOCK."""
    return await _run_pretrade(body.symbol, body.quantity, body.book or "Macro")


def _pretrade_result(sym, quantity, price, before, after, limits):
    from api.calculations.limits import pretrade_check
    result = pretrade_check(before["metrics"], after["metrics"], limits)
    return {"trade": {"symbol": sym, "quantity": quantity, "price": round(price, 2),
                      "notional": round(quantity * price, 2),
                      "pct_nav": round(quantity * price / before["nav"], 4) if before["nav"] else None},
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
    from api.core.access import require_roles
    require_roles(request, {"pm", "quant"})
    user = _m()._request_user(request)
    from api import blotter_store
    await _thread(blotter_store.init_db)
    created = []
    for o in body.orders:
        idea = await _thread(lambda o=o: portfolio_store.add_trade_idea({
            "symbol": o["symbol"], "direction": "LONG" if o.get("side") == "BUY" else "SHORT",
            "thesis": f"Rebalance ({body.regime or 'current regime'}): {o.get('action', 'ADJUST')} "
                      f"{o.get('side')} {o.get('quantity')} @ ~{o.get('price')}",
            "conviction": "MEDIUM", "rationale": "Regime rebalance engine",
            "suggested_size": o.get("quantity"), "book": body.book}, user))
        await _thread(lambda i=idea, o=o: blotter_store.set_order_fields(
            i["id"], side=str(o.get("side", "BUY")).upper(), quantity=float(o.get("quantity") or 0)))
        created.append(idea)
    await _thread(lambda: audit_store.add_decision(
        "rebalance_staged", f"{len(created)} rebalance orders staged for approval ({body.book})",
        user=user, target=body.book, after_state={"orders": body.orders}))
    return {"staged": len(created), "ideas": created}


# ── Orders: four-eyes approval & execution ───────────────────────────────────
class OrderIn(BaseModel):
    symbol: str
    side: str                      # BUY / SELL
    quantity: float
    book: str = "Macro"
    thesis: Optional[str] = None
    conviction: str = "MEDIUM"


class DecisionNoteIn(BaseModel):
    note: Optional[str] = None


def _order_view(idea: Dict[str, Any]) -> Dict[str, Any]:
    return {k: idea.get(k) for k in ("id", "symbol", "side", "quantity", "book", "thesis",
                                     "conviction", "state", "created_by", "approved_by",
                                     "approval_note", "executed_trade_id", "created_at",
                                     "updated_at", "state_history")}


@router.get("/api/v1/orders")
async def list_orders(state: Optional[str] = None):
    from api import blotter_store, portfolio_store
    await _thread(blotter_store.init_db)
    ideas = await _thread(portfolio_store.list_trade_ideas, state)
    return {"orders": [_order_view(i) for i in ideas if i.get("side") and i.get("quantity")],
            "execution_mode": __import__("api.execution", fromlist=["x"]).execution_mode()}


@router.post("/api/v1/orders")
async def create_order(body: OrderIn, request: Request):
    """Order ticket: runs pre-trade compliance immediately and queues the order as
    'Proposed' (a BLOCK is reported but the ticket is still recorded for the audit trail)."""
    from api import blotter_store, portfolio_store, audit_store
    from api.calculations.blotter import side_to_signed
    from api.core.access import require_roles
    user = require_roles(request, {"pm", "quant", "analyst"})["username"]
    signed = side_to_signed(body.side, body.quantity)
    check = await _run_pretrade(body.symbol, signed, body.book)
    await _thread(blotter_store.init_db)
    idea = await _thread(lambda: portfolio_store.add_trade_idea({
        "symbol": body.symbol, "direction": "LONG" if signed > 0 else "SHORT",
        "thesis": body.thesis or f"{body.side.upper()} {abs(body.quantity):g} {body.symbol.upper()}",
        "conviction": body.conviction, "rationale": "Order ticket",
        "suggested_size": abs(body.quantity), "book": body.book}, user))
    await _thread(lambda: blotter_store.set_order_fields(idea["id"], side=body.side.upper(),
                                                         quantity=abs(body.quantity)))
    await _thread(lambda: audit_store.add_decision(
        "order_created", f"{body.side.upper()} {abs(body.quantity):g} {body.symbol.upper()} "
                         f"({body.book}) — pre-trade {check['decision']}",
        user=user, target=f"order:{idea['id']}", after_state={"pretrade": check["decision"]}))
    return {"order": _order_view(await _thread(blotter_store.get_idea, idea["id"])), "pretrade": check}


@router.post("/api/v1/orders/{order_id}/approve")
async def approve_order(order_id: int, body: DecisionNoteIn, request: Request):
    """Four-eyes approval: the approver must differ from the order's creator. Compliance is
    re-run against the CURRENT book: BLOCK refuses; WARN requires a written note."""
    from api import blotter_store, portfolio_store, audit_store
    from api.calculations.blotter import side_to_signed
    from api.core.access import require_roles
    user = require_roles(request, {"risk"})["username"]       # approval is a risk function
    o = await _thread(blotter_store.get_idea, order_id)
    if not o or not o.get("side"):
        raise HTTPException(404, "order not found")
    if o["state"] not in ("Proposed", "Under Review"):
        raise HTTPException(409, f"order is {o['state']}")
    if user == (o.get("created_by") or ""):
        raise HTTPException(403, "four-eyes: the approver must be a different, identified user "
                                 f"than the creator ({o.get('created_by')})")
    check = await _run_pretrade(o["symbol"], side_to_signed(o["side"], o["quantity"]), o["book"])
    if check["decision"] == "BLOCK":
        raise HTTPException(409, {"message": "pre-trade compliance BLOCK", "reasons": check["reasons"]})
    if check["decision"] == "WARN" and not (body.note or "").strip():
        raise HTTPException(409, {"message": "soft-limit WARN — approval needs a written note",
                                  "reasons": check["reasons"]})
    await _thread(lambda: portfolio_store.transition_trade_idea(order_id, "Approved", user, body.note))
    await _thread(lambda: blotter_store.set_order_fields(order_id, approved_by=user, approval_note=body.note))
    await _thread(lambda: audit_store.add_decision(
        "order_approved", f"Approved order {order_id} ({o['side']} {o['quantity']:g} {o['symbol']}); "
                          f"pre-trade {check['decision']}" + (f"; note: {body.note}" if body.note else ""),
        user=user, target=f"order:{order_id}", after_state={"pretrade": check}))
    return {"order": _order_view(await _thread(blotter_store.get_idea, order_id)), "pretrade": check}


@router.post("/api/v1/orders/{order_id}/reject")
async def reject_order(order_id: int, body: DecisionNoteIn, request: Request):
    from api import blotter_store, portfolio_store, audit_store
    from api.core.access import require_roles
    user = require_roles(request, {"risk", "pm"})["username"]
    o = await _thread(blotter_store.get_idea, order_id)
    if not o:
        raise HTTPException(404, "order not found")
    if o["state"] in ("Executed", "Closed"):
        raise HTTPException(409, f"order is {o['state']}")
    if not (body.note or "").strip():
        raise HTTPException(400, "a rejection reason is required")
    await _thread(lambda: portfolio_store.transition_trade_idea(order_id, "Closed", user, f"Rejected: {body.note}"))
    await _thread(lambda: audit_store.add_decision(
        "order_rejected", f"Rejected order {order_id}: {body.note}", user=user, target=f"order:{order_id}"))
    return {"order": _order_view(await _thread(blotter_store.get_idea, order_id))}


@router.post("/api/v1/orders/{order_id}/execute")
async def execute_order(order_id: int, request: Request):
    """Execute an APPROVED order: simulated fill at the latest close (default) or Alpaca PAPER
    routing when configured; the fill is booked into positions + blotter atomically."""
    from api import blotter_store, fund_store, portfolio_store, audit_store
    from api import execution
    from api.calculations.blotter import side_to_signed, commission
    from api.handlers.market_handler import _fetch_closes_literal
    from api.core.access import require_roles
    user = require_roles(request, {"pm"})["username"]        # execution desk
    o = await _thread(blotter_store.get_idea, order_id)
    if not o or not o.get("side"):
        raise HTTPException(404, "order not found")
    if o["state"] != "Approved":
        raise HTTPException(409, f"only Approved orders can be executed (order is {o['state']})")
    signed = side_to_signed(o["side"], o["quantity"])
    mode = execution.execution_mode()
    if mode == "alpaca_paper":
        fill = await _thread(lambda: execution.alpaca_paper_fill(o["symbol"], signed))
    else:
        closes = await _fetch_closes_literal(o["symbol"])
        fill = execution.simulated_fill(signed, closes[-1] if closes else None)
    if not fill.filled:
        await _thread(lambda: audit_store.add_decision(
            "order_not_filled", f"Order {order_id} not filled ({fill.source}): {fill.detail}",
            user=user, target=f"order:{order_id}"))
        raise HTTPException(409, {"message": "not filled", "status": fill.status, "detail": fill.detail,
                                  "broker_order_id": fill.broker_order_id})
    settings = await _thread(fund_store.get_settings)
    comm = commission(signed * fill.price, settings["cost_bps"])
    trade = await _thread(lambda: blotter_store.book_fill(
        o["book"], o["symbol"], signed, fill.price, comm, user, fill.source, order_id))
    await _thread(lambda: portfolio_store.transition_trade_idea(
        order_id, "Executed", user, f"{fill.source} fill {abs(signed):g} @ {fill.price:.2f}"))
    await _thread(lambda: audit_store.add_decision(
        "order_executed", f"Executed order {order_id}: {o['side']} {abs(signed):g} {o['symbol']} @ "
                          f"{fill.price:.2f} ({fill.source}); realized {trade['realized_pnl']:+.2f}",
        user=user, target=f"order:{order_id}", after_state=trade))
    return {"trade": trade, "order": _order_view(await _thread(blotter_store.get_idea, order_id)),
            "execution_mode": mode}


@router.get("/api/v1/blotter")
async def blotter(book: Optional[str] = None, limit: int = 200):
    from api import blotter_store, fund_store, portfolio_store
    from api.calculations.blotter import blotter_totals
    trades = await _thread(lambda: blotter_store.list_trades(limit, book))
    settings = await _thread(fund_store.get_settings)
    raw = await _thread(portfolio_store.list_positions, None)
    state = await _book_state(raw, settings, include_liquidity=False, include_factors=False)
    return {"trades": trades, "totals": blotter_totals(await _thread(blotter_store.list_trades)),
            "cash": state["cash"], "nav": state["nav"], "realized_pnl": state["realized_pnl"],
            "commissions": state["commissions"]}


# ── Model scorecard ──────────────────────────────────────────────────────────
@router.get("/api/v1/models/scorecard")
async def model_scorecard():
    """How the models actually performed: walk-forward regime-transition test on FRED history,
    recession forecasts scored once their 12-month horizon resolves (FRED USREC), and the
    signal backtests' independent-window hit rates."""
    from api.calculations.scorecard import transition_backtest, resolve_recession_forecasts
    out: Dict[str, Any] = {"as_of": datetime.now().isoformat()}

    try:
        regimes = list((await _thread(_m()._monthly_regime_frame))["regime"])
        out["regime_transition"] = transition_backtest(regimes, min_train=60) or {"available": False}
        out["regime_transition"]["method"] = ("walk-forward: each month's next-regime forecast uses "
                                              "only the history up to that month")
    except Exception as e:
        out["regime_transition"] = {"available": False, "reason": str(e)[:120]}

    try:
        import sqlite3
        from database.db import DB_PATH
        # Score only GENUINE forecasts: logged on the day they were made, by the current
        # model (its log carries a "model" field). Older rows include back-filled "history"
        # from a retired heuristic — dated 2018-2027 but all written on one day — which would
        # be scoring hindsight, not forecasts.
        with sqlite3.connect(str(DB_PATH)) as conn:
            rows = conn.execute(
                "SELECT date, blended_prob FROM recession_forecast_history "
                "WHERE horizon = '12M' AND substr(recorded_at, 1, 10) = substr(date, 1, 10) "
                "AND metadata LIKE '%\"model\"%' ORDER BY date").fetchall()
            excluded = conn.execute(
                "SELECT COUNT(*) FROM recession_forecast_history WHERE horizon = '12M'").fetchone()[0] - len(rows)
        from api.handlers.macro_inputs import _fred
        res = await _thread(lambda: _fred().fetch_series("USREC", start_date="2018-01-01"))
        usrec = {o.date: o.value for o in (res.data or [])}
        out["recession"] = {**resolve_recession_forecasts(rows, usrec, 12), "logged_forecasts": len(rows),
                            "excluded_non_genuine": excluded,
                            "note": "scored only after the 12-month horizon passes and NBER data is published"}
    except Exception as e:
        out["recession"] = {"available": False, "reason": str(e)[:120]}

    try:
        bt = await _m().signals_backtest_v1()
        out["signals"] = [{"label": s.get("label"), "hit_rate_independent": s.get("hit_rate_independent"),
                           "p_value": s.get("hit_rate_p_value"), "independent": s.get("independent_directional"),
                           "sharpe": s.get("strategy_sharpe")} for s in bt.get("signals", [])]
    except Exception as e:
        out["signals"] = {"available": False, "reason": str(e)[:120]}
    return out
