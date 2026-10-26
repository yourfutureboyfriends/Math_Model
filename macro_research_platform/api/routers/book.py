"""
The fund's book: positions, trade ideas, and the risk of what is held.

Endpoints (all read the current fund's database — see api/funds.py)
    Positions      GET/POST /api/v1/portfolio/positions, POST .../positions/bulk, PUT/DELETE .../positions/{id},
                   GET /api/v1/portfolio/books
    Pre-trade      POST /api/v1/portfolio/what-if          VaR / exposure / concentration before vs after a trade
    Trade ideas    GET/POST /api/v1/portfolio/trade-ideas, POST .../{id}/transition, DELETE .../{id},
                   GET /api/v1/portfolio/generate-ideas
    Attribution    GET /api/v1/portfolio/attribution
    Risk           GET /api/v1/risk/factor-exposure, /risk/var, /risk/var/backtest, /risk/stress-test (GET + POST),
                   /risk/reverse-stress, /risk/concentration, /risk/liquidity

Shared helpers used by other routers (api/routers/fund.py, api/handlers/risk_handler.py):
    _enrich_positions(raw)          live prices, P&L and base-currency values for position rows
    _risk_snapshot(raw)             VaR, exposure and concentration of a (possibly hypothetical) set of positions
    _position_return_matrix(book)   aligned daily returns and market values of the book's positions
    _dollar_factor_exposures(book)  P&L per unit factor return, for stress tests

Conventions
    * Money is in the fund's base currency (positions are converted at today's FX; cost at the rate paid).
    * VaR is reported as a positive loss. The maths lives in api/calculations/ (var_model, factor_model,
      attribution); this module fetches data and shapes responses.
    * Edits to positions and trade ideas are audit-logged with the verified user (api/core/web.username).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["book"])




class PositionIn(BaseModel):
    """A position: symbol, quantity (negative for short), average cost, entry date, book and asset class."""
    symbol: str
    quantity: float
    avg_cost: float
    asset_class: Optional[str] = "Equity"
    book: Optional[str] = "Macro"
    strategy_bucket: Optional[str] = None
    entry_date: Optional[str] = None


class PositionUpdate(BaseModel):
    """Fields of a position to change."""
    quantity: Optional[float] = None
    avg_cost: Optional[float] = None
    asset_class: Optional[str] = None
    book: Optional[str] = None
    strategy_bucket: Optional[str] = None
    entry_date: Optional[str] = None


class BulkPositionsIn(BaseModel):
    """Several positions to add at once."""
    positions: List[PositionIn]


async def _enrich_positions(raw_positions: list) -> dict:
    """Attach live prices, market value, P&L and weights to raw position rows."""
    import asyncio as _aio
    from api.handlers.market_handler import _fetch_closes_literal
    from api.calculations.portfolio import enrich_position, add_weights, portfolio_summary, books_breakdown

    symbols = sorted({str(p["symbol"]).upper() for p in raw_positions if p.get("symbol")})
    prices: dict = {}
    if symbols:
        # Literal tickers (GLD = the ETF), not the dashboard's macro proxies.
        closes_list = await _aio.gather(*[_fetch_closes_literal(s) for s in symbols])
        for sym, closes in zip(symbols, closes_list):
            prices[sym] = closes[-1] if closes else None

    enriched = [enrich_position(p, prices.get(str(p["symbol"]).upper())) for p in raw_positions]
    # FX: every listing is valued in the fund's base currency — market value at today's rate, cost basis at the
    # rate when it was bought (stored per position, else its entry date), unrealised split into local and FX P&L
    from api.handlers.portfolio_analytics import _usd_per_unit
    from api.calculations import fx_accounting
    from api import fund_store
    base = (await asyncio.to_thread(fund_store.get_settings)).get("base_currency") or "USD"
    fx = dict(zip(symbols, await _aio.gather(*[asyncio.to_thread(_usd_per_unit, s) for s in symbols]))) if symbols else {}

    def _convert():
        for p in enriched:
            ccy, usd = fx.get(str(p["symbol"]).upper(), ("USD", 1.0))
            p["currency"], p["usd_per_unit"] = ccy, usd
            fx_accounting.convert_position(p, base, usd)
    await asyncio.to_thread(_convert)
    add_weights(enriched)
    return {
        "positions": enriched,
        "summary": portfolio_summary(enriched),
        "books": books_breakdown(enriched),
        "currency": base,
        "priced_at": datetime.now().isoformat(),
    }


@router.get("/api/v1/portfolio/positions")
async def portfolio_positions_v1(book: Optional[str] = None):
    """Held positions enriched with live market value, unrealized P&L and weights."""
    from api import portfolio_store
    try:
        raw = await asyncio.to_thread(portfolio_store.list_positions, book)
        return await _enrich_positions(raw)
    except Exception as e:
        logger.error("[portfolio] list failed: %s", e)
        raise HTTPException(status_code=503, detail=f"positions unavailable: {str(e)[:160]}")


async def _audit_position_edit(request: Request, action: str, rationale: str, before=None, after=None):
    try:
        from api import audit_store
        await asyncio.to_thread(lambda: audit_store.add_decision(
            action, rationale, user=_request_user(request), target="positions",
            before_state=before, after_state=after))
    except Exception as e:
        logger.debug(f"[audit] position edit not logged: {e}")


@router.post("/api/v1/portfolio/positions")
async def portfolio_add_position_v1(pos: PositionIn, request: Request):
    """Manual position entry (e.g. loading an existing book). Trading should go through
    /api/v1/orders so it is approved and booked in the blotter; manual edits are audited."""
    from api import portfolio_store
    from api.core.access import require_roles
    require_roles(request, {"pm"})
    try:
        out = await asyncio.to_thread(portfolio_store.add_position, pos.model_dump())
        await _audit_position_edit(request, "position_added", f"Manual position {out.get('symbol')} {out.get('quantity')}", after=out)
        return out
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("[portfolio] add failed: %s", e)
        raise HTTPException(status_code=503, detail=str(e)[:160])


@router.post("/api/v1/portfolio/positions/bulk")
async def portfolio_bulk_v1(body: BulkPositionsIn, request: Request):
    """Add several positions at once (audit-logged)."""
    from api import portfolio_store
    from api.core.access import require_roles
    require_roles(request, {"pm"})
    out = await asyncio.to_thread(portfolio_store.add_positions_bulk, [p.model_dump() for p in body.positions])
    await _audit_position_edit(request, "positions_bulk_loaded", f"Bulk load of {len(body.positions)} positions")
    return out


@router.put("/api/v1/portfolio/positions/{pos_id}")
async def portfolio_update_position_v1(pos_id: int, upd: PositionUpdate, request: Request):
    """Change a position (audit-logged with before and after)."""
    from api import portfolio_store
    from api.core.access import require_roles
    require_roles(request, {"pm"})
    before = await asyncio.to_thread(portfolio_store.get_position, pos_id)
    updated = await asyncio.to_thread(portfolio_store.update_position, pos_id, upd.model_dump(exclude_none=True))
    if updated is None:
        raise HTTPException(status_code=404, detail="position not found")
    await _audit_position_edit(request, "position_edited", f"Manual edit of position {pos_id}", before, updated)
    return updated


@router.delete("/api/v1/portfolio/positions/{pos_id}")
async def portfolio_delete_position_v1(pos_id: int, request: Request):
    """Delete a position (audit-logged)."""
    from api import portfolio_store
    from api.core.access import require_roles
    require_roles(request, {"pm"})
    before = await asyncio.to_thread(portfolio_store.get_position, pos_id)
    ok = await asyncio.to_thread(portfolio_store.delete_position, pos_id)
    if not ok:
        raise HTTPException(status_code=404, detail="position not found")
    await _audit_position_edit(request, "position_deleted", f"Manual delete of position {pos_id}", before)
    return {"deleted": True, "id": pos_id}


@router.get("/api/v1/portfolio/books")
async def portfolio_books_v1():
    """List books plus the firm-level aggregate across all positions."""
    from api import portfolio_store
    raw = await asyncio.to_thread(portfolio_store.list_positions, None)
    enriched = (await _enrich_positions(raw))
    return {
        "books": portfolio_store.list_books(),
        "firm": enriched["summary"],
        "book_breakdown": enriched["books"],
    }


async def _risk_snapshot(raw: list) -> dict:
    """VaR (95% 1d), exposure and concentration for a (possibly hypothetical) raw set."""
    from api.calculations.var_model import (
        portfolio_pnl_series, historical_var, parametric_var, concentration,
    )
    data, reason, enriched = await _position_return_matrix(None, raw_positions=raw)
    enr = enriched or (await _enrich_positions(raw) if raw else {"summary": {}, "positions": []})
    conc = concentration(enr["positions"]) if enr.get("positions") else {"available": False}
    if data is None:
        return {"var_available": False, "reason": reason,
                "summary": enr.get("summary", {}), "concentration": conc}
    pnl = portfolio_pnl_series(data["market_values"], data["R"])
    return {
        "var_available": True,
        "var_95_1d": parametric_var(pnl, 0.95),
        "var_95_1d_hist": historical_var(pnl, 0.95),
        "summary": data["enriched"]["summary"],
        "concentration": conc,
    }


class WhatIfIn(BaseModel):
    """A proposed trade for the what-if: symbol, quantity, optional cost and book, optional VaR budget."""
    symbol: str
    quantity: float
    avg_cost: Optional[float] = None      # defaults to current price (entry P&L = 0)
    book: Optional[str] = "Macro"
    var_limit: Optional[float] = None     # if set, suggest a size within this VaR budget


from api.core.web import username as _request_user


@router.post("/api/v1/portfolio/what-if")
async def portfolio_what_if_v1(trade: WhatIfIn):
    """Pre-trade analysis: projected VaR / exposure / concentration BEFORE vs AFTER
    adding a proposed trade, plus a VaR-budgeted suggested size."""
    import numpy as _np
    from api import portfolio_store
    from api.handlers.market_handler import _fetch_closes_literal
    from api.calculations.factor_model import returns_from_closes
    from api.calculations.var_model import suggest_size_for_var

    current = await asyncio.to_thread(portfolio_store.list_positions, None)
    before = await _risk_snapshot(current)

    sym = trade.symbol.strip().upper()
    closes = await _fetch_closes_literal(sym)
    if not closes:
        return {"available": False, "reason": f"No price history for {sym}."}
    price = closes[-1]
    proposed = {"symbol": sym, "quantity": trade.quantity,
                "avg_cost": trade.avg_cost if trade.avg_cost is not None else price,
                "book": trade.book or "Macro", "asset_class": "Equity"}
    after = await _risk_snapshot(current + [proposed])

    daily_vol = float(_np.std(returns_from_closes(closes))) if len(closes) > 2 else 0.0
    sizing = None
    if trade.var_limit:
        sizing = suggest_size_for_var(daily_vol, price, trade.var_limit, 0.95, 1)

    def _delta(a, b):
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return round(a - b, 2)
        return None

    return {
        "available": True,
        "proposed": {"symbol": sym, "quantity": trade.quantity, "price": round(price, 2),
                     "notional": round(trade.quantity * price, 2), "book": trade.book},
        "before": before, "after": after,
        "delta": {
            "var_95_1d": _delta(after.get("var_95_1d"), before.get("var_95_1d")),
            "gross_exposure": _delta(after.get("summary", {}).get("gross_exposure"),
                                     before.get("summary", {}).get("gross_exposure")),
            "net_exposure": _delta(after.get("summary", {}).get("net_exposure"),
                                   before.get("summary", {}).get("net_exposure")),
            "largest_weight": _delta(after.get("concentration", {}).get("largest_weight"),
                                     before.get("concentration", {}).get("largest_weight")),
        },
        "sizing": sizing,
        "computed_at": datetime.now().isoformat(),
    }


class TradeIdeaIn(BaseModel):
    """A trade idea: symbol, direction, thesis, conviction, sizing and book."""
    symbol: str
    direction: Optional[str] = "LONG"
    thesis: Optional[str] = None
    conviction: Optional[str] = "MEDIUM"
    rationale: Optional[str] = None
    suggested_size: Optional[float] = None
    book: Optional[str] = "Macro"


class TradeIdeaTransition(BaseModel):
    """A trade idea's next state and an optional note."""
    state: str
    note: Optional[str] = None


@router.get("/api/v1/portfolio/trade-ideas")
async def trade_ideas_list_v1(state: Optional[str] = None):
    """Trade ideas, optionally filtered by state."""
    from api import portfolio_store
    ideas = await asyncio.to_thread(portfolio_store.list_trade_ideas, state)
    return {"ideas": ideas, "states": portfolio_store.IDEA_STATES}


@router.post("/api/v1/portfolio/trade-ideas")
async def trade_ideas_add_v1(idea: TradeIdeaIn, request: Request):
    """Add a trade idea."""
    from api import portfolio_store
    user = _request_user(request)
    try:
        return await asyncio.to_thread(lambda: portfolio_store.add_trade_idea(idea.model_dump(), user))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/api/v1/portfolio/trade-ideas/{idea_id}/transition")
async def trade_ideas_transition_v1(idea_id: int, body: TradeIdeaTransition, request: Request):
    """Move a trade idea through its workflow (proposed → under review → approved → executed / closed)."""
    from api import portfolio_store, blotter_store
    from api.core.access import require_roles
    user = _request_user(request)
    # Orders (ideas with side/quantity) may only be approved/executed through the order
    # workflow, which enforces four-eyes, re-runs compliance and books the fill.
    idea = await asyncio.to_thread(blotter_store.get_idea, idea_id)
    if idea and idea.get("side") and body.state in ("Approved", "Executed"):
        raise HTTPException(status_code=409, detail=(
            f"Order #{idea_id} must be {'approved' if body.state == 'Approved' else 'executed'} via "
            f"/api/v1/orders/{idea_id}/{'approve' if body.state == 'Approved' else 'execute'}"))
    if body.state == "Approved":
        require_roles(request, {"risk"})
        if idea and user == (idea.get("created_by") or ""):
            raise HTTPException(status_code=403, detail="four-eyes: approver must differ from the creator")
    try:
        updated = await asyncio.to_thread(lambda: portfolio_store.transition_trade_idea(idea_id, body.state, user, body.note))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if updated is None:
        raise HTTPException(status_code=404, detail="trade idea not found")
    # Record the lifecycle change in the audit decision log, attributed to the acting user.
    try:
        from api import audit_store
        await asyncio.to_thread(lambda: audit_store.add_decision(
            action=f"Trade idea → {body.state}", rationale=body.note or f"Transitioned to {body.state}",
            user=user, target=f"{updated.get('symbol')} (idea #{idea_id})",
            after_state={"state": body.state}))
    except Exception as e:
        logger.debug(f"[audit] could not log idea transition: {e}")
    return updated


@router.get("/api/v1/portfolio/generate-ideas")
async def portfolio_generate_ideas_v1(book: Optional[str] = None):
    """Auto-generate trade ideas by mapping the current macro regime's playbook
    (REGIME_CHARACTERISTICS) onto factor proxies and comparing to the book's live factor
    exposures. Transparent rules engine — every idea states the regime, factor and reason."""
    from api.calculations.idea_generation import generate_ideas

    # Current regime from the live dashboard cache.
    regime_key, regime_name = None, None
    try:
        from api.handlers.dashboard_handler import _DASHBOARD_CACHE
        cached = _DASHBOARD_CACHE.get("live")
        d = cached[1] if cached else None
        if d is not None:
            reg = getattr(d, "regime", None) or {}
            regime_name = getattr(reg, "current", None) if not isinstance(reg, dict) else reg.get("current")
            regime_key = (regime_name or "").strip().lower()
    except Exception as e:
        logger.debug(f"[generate-ideas] regime lookup failed: {e}")
    if not regime_key:
        return {"available": False, "reason": "Current regime unavailable — dashboard not warmed yet.",
                "ideas": []}

    dexp, reason = await _dollar_factor_exposures(book)
    if dexp is None:
        return {"available": False, "reason": reason or "No positions to analyse.",
                "regime": regime_name, "ideas": []}

    from api import portfolio_store
    raw = await asyncio.to_thread(portfolio_store.list_positions, book)
    gross = (await _enrich_positions(raw))["summary"]["gross_exposure"] or 0.0 if raw else 0.0

    ideas = generate_ideas(dexp, regime_key, gross_exposure=gross)
    return {"available": True, "regime": regime_name, "book": book or "Firm",
            "gross_exposure": round(gross, 2), "dollar_exposures": dexp,
            "ideas": ideas, "computed_at": datetime.now().isoformat()}


@router.delete("/api/v1/portfolio/trade-ideas/{idea_id}")
async def trade_ideas_delete_v1(idea_id: int):
    """Delete a trade idea."""
    from api import portfolio_store
    ok = await asyncio.to_thread(portfolio_store.delete_trade_idea, idea_id)
    if not ok:
        raise HTTPException(status_code=404, detail="trade idea not found")
    return {"deleted": True, "id": idea_id}




@router.get("/api/v1/portfolio/attribution")
async def portfolio_attribution_v1(book: Optional[str] = None):
    """Multi-level performance attribution on the real book:
    - contribution: each position's / book's dollar P&L (sums to total P&L),
    - factor: the trailing portfolio return split into systematic (per factor) +
      idiosyncratic (selection). Requires positions."""
    import numpy as _np
    from api import portfolio_store
    from api.calculations.attribution import (
        position_contributions, book_rollup, factor_attribution,
    )
    raw = await asyncio.to_thread(portfolio_store.list_positions, book)
    if not raw:
        return {"available": False, "reason": "No positions configured — add positions first."}
    enriched = await _enrich_positions(raw)
    positions = enriched["positions"]

    contribution = {
        "total_unrealized_pnl": enriched["summary"]["total_unrealized_pnl"],
        "by_position": position_contributions(positions),
        "by_book": book_rollup(positions),
    }

    # Factor attribution over the trailing window (best-effort; may be unavailable for
    # very new books). portfolio_return = Σ net_weight_i * cumulative_return_i.
    factor = {"available": False, "reason": "insufficient history"}
    data, _, _ = await _position_return_matrix(book)
    if data is not None:
        R, mvs, gross = data["R"], data["market_values"], enriched["summary"]["gross_exposure"] or 0.0
        cum = _np.prod(1.0 + R, axis=0) - 1.0
        net_w = _np.array([mv / gross if gross else 0.0 for mv in mvs])
        port_ret = float(net_w @ cum)

        fe = await risk_factor_exposure_v1(book)
        if fe.get("available"):
            from api.handlers.market_handler import _fetch_dated_closes_literal
            from api.calculations.factor_model import (
                FACTOR_DEFINITIONS, FACTOR_TICKERS, factor_period_return)
            loadings = {f["factor"]: f["exposure"] for f in fe["factors"]}
            # Period return per ticker over the same dates the positions span.
            dated_all = {t: await _fetch_dated_closes_literal(t) for t in FACTOR_TICKERS}
            dates = data.get("dates") or []
            tick_ret = {}
            for t, d in dated_all.items():
                pts = [d[k] for k in dates if k in d] if dates else [d[k] for k in sorted(d)]
                if len(pts) >= 2 and pts[0]:
                    tick_ret[t] = pts[-1] / pts[0] - 1.0
            fac_ret = {f: r for f in FACTOR_DEFINITIONS
                       if (r := factor_period_return(tick_ret, f)) is not None}
            factor = {"available": True, "window": "~1y",
                      **factor_attribution(loadings, fac_ret, port_ret)}

    return {
        "available": True, "book": book or "Firm",
        "contribution": contribution, "factor": factor,
        "computed_at": datetime.now().isoformat(),
    }


@router.get("/api/v1/risk/factor-exposure")
async def risk_factor_exposure_v1(book: Optional[str] = None):
    """Portfolio factor exposure: OLS betas of each holding to systematic factors,
    aggregated by net weight, with each factor's contribution to portfolio volatility.
    Requires positions (Phase 1) — returns available=false with a reason if none."""
    import numpy as _np
    from api import portfolio_store
    from api.handlers.market_handler import _fetch_dated_closes_literal
    from api.calculations.factor_model import (
        FACTOR_PROXIES, FACTOR_LABELS, FACTOR_TICKERS, returns_from_closes,
        build_factor_returns, estimate_factor_loadings, regression_fit,
        aggregate_portfolio_loadings, contribution_to_vol,
    )

    raw = await asyncio.to_thread(portfolio_store.list_positions, book)
    if not raw:
        return {"available": False, "reason": "No positions configured — add positions first.",
                "factors": []}

    enriched = await _enrich_positions(raw)
    positions = enriched["positions"]
    gross = enriched["summary"]["gross_exposure"] or 0.0

    # Fetch dated closes for every factor ticker (long and short legs) and held symbol.
    ticker_dated = {t: await _fetch_dated_closes_literal(t) for t in FACTOR_TICKERS}
    common_dates = None
    for d in ticker_dated.values():
        keys = set(d.keys())
        common_dates = keys if common_dates is None else (common_dates & keys)
    common_dates = sorted(common_dates or [])
    if len(common_dates) < 61:
        return {"available": False, "reason": "Insufficient factor price history to estimate loadings.",
                "factors": []}

    def _aligned(dmap, dates):
        return returns_from_closes([dmap[dt] for dt in dates])

    def _factors_on(dates):
        return build_factor_returns({t: _aligned(ticker_dated[t], dates) for t in FACTOR_TICKERS})

    # Factor volatilities (annualized) over the common grid.
    factor_full_ret = _factors_on(common_dates)
    factor_vol = {f: float(_np.std(r) * (252 ** 0.5)) if len(r) else 0.0 for f, r in factor_full_ret.items()}

    per_position = []
    position_loadings, net_weights = [], []
    for p in positions:
        sym = str(p["symbol"]).upper()
        pdated = await _fetch_dated_closes_literal(sym)
        pdates = [dt for dt in common_dates if dt in pdated]
        loadings = {}
        r2 = 0.0
        if len(pdates) >= 61:
            pos_ret = _aligned(pdated, pdates)
            fac_ret = _factors_on(pdates)
            loadings = estimate_factor_loadings(pos_ret, fac_ret)
            r2 = regression_fit(pos_ret, fac_ret) if loadings else 0.0
        mv = p.get("market_value")
        net_w = (mv / gross) if (isinstance(mv, (int, float)) and gross) else 0.0
        position_loadings.append(loadings)
        net_weights.append(net_w)
        per_position.append({
            "symbol": sym, "book": p.get("book"), "net_weight": round(net_w, 4),
            "r_squared": r2, "loadings": {k: round(v, 4) for k, v in loadings.items()},
            "estimated": bool(loadings),
        })

    portfolio_loadings = aggregate_portfolio_loadings(position_loadings, net_weights)
    contrib = contribution_to_vol(portfolio_loadings, factor_full_ret)

    factors_out = []
    for f in FACTOR_PROXIES:
        factors_out.append({
            "factor": f,
            "label": FACTOR_LABELS.get(f, f),
            "proxy": FACTOR_PROXIES[f],
            "exposure": round(portfolio_loadings.get(f, 0.0), 4),
            "factor_vol_annual": round(factor_vol.get(f, 0.0), 4),
            "contribution_to_vol": round(contrib.get(f, 0.0), 4),
        })
    factors_out.sort(key=lambda x: abs(x["exposure"]), reverse=True)

    return {
        "available": True,
        "book": book or "Firm",
        "factors": factors_out,
        "positions": per_position,
        "observations": len(common_dates) - 1,
        "computed_at": datetime.now().isoformat(),
    }


async def _position_return_matrix(book: Optional[str], raw_positions: Optional[list] = None):
    """(symbols, market_values, TxN return matrix, enriched) for held positions,
    date-aligned across names. Pass raw_positions to compute on a hypothetical set
    (e.g. what-if) instead of the persisted book."""
    import numpy as _np
    from api import portfolio_store
    from api.handlers.market_handler import _fetch_dated_closes_literal
    from api.calculations.factor_model import returns_from_closes

    raw = raw_positions if raw_positions is not None else await asyncio.to_thread(portfolio_store.list_positions, book)
    if not raw:
        return None, "No positions configured — add positions first.", None
    enriched = await _enrich_positions(raw)
    positions = [p for p in enriched["positions"] if p.get("price_available")]
    if not positions:
        return None, "No priced positions to compute risk on.", enriched

    dated = {}
    for p in positions:
        dated[p["symbol"]] = await _fetch_dated_closes_literal(str(p["symbol"]).upper())
    common = None
    for d in dated.values():
        keys = set(d.keys())
        common = keys if common is None else (common & keys)
    common = sorted(common or [])
    if len(common) < 61:
        return None, "Insufficient overlapping price history to estimate VaR.", enriched

    cols = []
    symbols, mvs = [], []
    for p in positions:
        r = returns_from_closes([dated[p["symbol"]][dt] for dt in common])
        cols.append(r)
        symbols.append(p["symbol"])
        mvs.append(float(p["market_value"]))
    R = _np.column_stack(cols)  # (T, n)
    return {"symbols": symbols, "market_values": mvs, "R": R, "dates": common,
            "enriched": enriched}, None, enriched


@router.get("/api/v1/risk/var")
async def risk_var_v1(book: Optional[str] = None):
    """Value-at-Risk (historical, parametric, Monte Carlo) at 95%/99%, 1d & 10d, on
    actual positions, with VaR contribution by position."""
    from api.calculations.var_model import (
        portfolio_pnl_series, historical_var, parametric_var, monte_carlo_var,
        scale_horizon, component_var_by_position,
    )
    data, reason, _ = await _position_return_matrix(book)
    if data is None:
        return {"available": False, "reason": reason, "methods": {}}
    mvs, R, symbols = data["market_values"], data["R"], data["symbols"]
    pnl = portfolio_pnl_series(mvs, R)

    def block(conf):
        h = historical_var(pnl, conf)
        pv = parametric_var(pnl, conf)
        mc = monte_carlo_var(mvs, R, conf)
        return {
            "historical": {"1d": h, "10d": scale_horizon(h, 10)},
            "parametric": {"1d": pv, "10d": scale_horizon(pv, 10)},
            "monte_carlo": {"1d": mc, "10d": scale_horizon(mc, 10)},
        }

    # Allocate the PARAMETRIC 95% 1d VaR: the Euler/variance decomposition is only
    # self-consistent against a variance-based total (not the empirical historical one).
    total_1d_param = parametric_var(pnl, 0.95)
    from api.calculations import var_model as vm
    fhs95 = vm.filtered_hs(pnl, 0.95)
    tail = {
        "expected_shortfall_975": {"historical": vm.expected_shortfall_hist(pnl, 0.975),
                                   "normal": vm.expected_shortfall_normal(pnl, 0.975),
                                   "filtered_hs": fhs95["es"]},
        "var_95_1d_models": {"cornish_fisher": vm.cornish_fisher_var(pnl, 0.95), "ewma_094": vm.ewma_var(pnl, 0.95),
                             "filtered_hs": fhs95["var"]},
        "pnl_moments": {k: round(v, 3) for k, v in vm.moments(pnl).items()},
        "notes": ("ES 97.5% is the Basel FRTB measure (average loss beyond VaR). Cornish–Fisher adjusts the normal "
                  "quantile for skew and fat tails; EWMA (RiskMetrics λ=0.94) and filtered historical simulation scale "
                  "to today's volatility — when they exceed the equal-weighted VaR, volatility is rising."),
    }
    return {
        "available": True,
        "book": book or "Firm",
        "observations": int(R.shape[0]),
        "gross_exposure": data["enriched"]["summary"]["gross_exposure"],
        "var": {"95": block(0.95), "99": block(0.99)},
        "tail_risk": tail,
        "component_var_95_1d": component_var_by_position(symbols, mvs, R, total_1d_param),
        "component_var_basis": "parametric_95_1d",
        "computed_at": datetime.now().isoformat(),
    }


@router.get("/api/v1/risk/var/backtest")
async def risk_var_backtest_v1():
    """Backtest of the recorded VaR: each day's 95% 1-day VaR (recorded with the NAV snapshot) against the next
    day's flow-adjusted NAV change — Kupiec, Christoffersen and the Basel traffic light."""
    from api import fund_store
    from api.calculations import var_model as vm
    from api.governance_reports import _flows
    rows = [r for r in await asyncio.to_thread(fund_store.nav_history) if r.get("nav")]
    flows = await asyncio.to_thread(_flows)
    losses, fc = [], []
    for a, b in zip(rows[:-1], rows[1:]):
        if a.get("var95_1d") is None:
            continue
        f = sum(v for d, v in flows.items() if a["date"] < d <= b["date"])
        losses.append(-(float(b["nav"]) - f - float(a["nav"])))
        fc.append(float(a["var95_1d"]))
    return {**vm.var_backtest(losses, fc, 0.95), "basis": "recorded 95% 1-day VaR vs next snapshot's NAV change (flows removed)"}


async def _dollar_factor_exposures(book: Optional[str]):
    """DExp_f = gross_exposure * portfolio_loading_f ($ P&L per 1.0 factor return)."""
    fe = await risk_factor_exposure_v1(book)
    if not fe.get("available"):
        return None, fe.get("reason")
    gross = 0.0
    from api import portfolio_store
    raw = await asyncio.to_thread(portfolio_store.list_positions, book)
    if raw:
        gross = (await _enrich_positions(raw))["summary"]["gross_exposure"] or 0.0
    dexp = {f["factor"]: round(gross * f["exposure"], 2) for f in fe["factors"]}
    return dexp, None


@router.get("/api/v1/risk/stress-test")
async def risk_stress_get_v1(book: Optional[str] = None):
    """Apply predefined historical scenarios (2008, 2020, 2013, 2022, 1994) to the
    current portfolio's dollar factor exposures."""
    from api.calculations.var_model import STRESS_SCENARIOS, scenario_pnl, to_factor_shocks
    dexp, reason = await _dollar_factor_exposures(book)
    if dexp is None:
        return {"available": False, "reason": reason, "scenarios": []}
    scenarios = []
    from api.calculations.factor_model import orthogonal_shocks
    for key, sc in STRESS_SCENARIOS.items():
        # Exposures are to orthogonalized factors (factor_model.orthogonalize_factors), so the
        # scenario's raw moves are mapped into that space before applying them.
        shocks = orthogonal_shocks(to_factor_shocks(sc["shocks"]))
        res = scenario_pnl(dexp, shocks)
        scenarios.append({"id": key, "label": sc["label"], "shocks": shocks,
                          "proxy_shocks": sc["shocks"],
                          "total_pnl": res["total_pnl"], "by_factor": res["by_factor"]})
    scenarios.sort(key=lambda s: s["total_pnl"])
    return {"available": True, "book": book or "Firm", "dollar_exposures": dexp,
            "scenarios": scenarios, "computed_at": datetime.now().isoformat()}


class StressCustomIn(BaseModel):
    """A custom stress scenario: factor shocks as returns (e.g. equity −0.20)."""
    shocks: Dict[str, float]
    book: Optional[str] = None


@router.post("/api/v1/risk/stress-test")
async def risk_stress_custom_v1(body: StressCustomIn):
    """Custom scenario: shock any combination of factors and see estimated P&L."""
    from api.calculations.var_model import scenario_pnl
    dexp, reason = await _dollar_factor_exposures(body.book)
    if dexp is None:
        return {"available": False, "reason": reason}
    from api.calculations.factor_model import orthogonal_shocks
    res = scenario_pnl(dexp, orthogonal_shocks(body.shocks))
    return {"available": True, "shocks": body.shocks, "total_pnl": res["total_pnl"],
            "by_factor": res["by_factor"]}


@router.get("/api/v1/risk/reverse-stress")
async def risk_reverse_stress_v1(target_loss: float, book: Optional[str] = None):
    """Reverse stress: the single-factor move that alone would cause target_loss ($)."""
    from api.calculations.var_model import reverse_stress
    dexp, reason = await _dollar_factor_exposures(book)
    if dexp is None:
        return {"available": False, "reason": reason, "factors": []}
    return {"available": True, "target_loss": target_loss,
            "factors": reverse_stress(dexp, target_loss),
            "computed_at": datetime.now().isoformat()}


@router.get("/api/v1/risk/concentration")
async def risk_concentration_v1(book: Optional[str] = None, limit_pct: float = 0.20):
    """Single-name and top-5 concentration with limit breaches."""
    from api import portfolio_store
    from api.calculations.var_model import concentration
    raw = await asyncio.to_thread(portfolio_store.list_positions, book)
    if not raw:
        return {"available": False, "reason": "No positions configured."}
    enriched = await _enrich_positions(raw)
    out = concentration(enriched["positions"], limit_pct)
    # Breaches are judged against the fund's risk limits (single name as % of NAV, the same
    # rule as pre-trade compliance and the Fund Overview). A fixed 20%-of-GROSS cap flagged a
    # name at 0.5% of NAV as a breach while every other panel showed the limits clean.
    try:
        from api import fund_store
        from api.calculations.fund import compute_nav
        from api.calculations.limits import merge_limits
        settings = await asyncio.to_thread(fund_store.get_settings)
        lim = merge_limits(await asyncio.to_thread(fund_store.get_limit_overrides))["single_name"]
        nav = compute_nav(settings["capital"], enriched["summary"].get("total_unrealized_pnl", 0.0), 0.0)
        mv = {str(p["symbol"]).upper(): abs(p.get("market_value") or 0.0) for p in enriched["positions"]}
        for row in out.get("positions", []):
            row["pct_nav"] = round(mv.get(str(row["symbol"]).upper(), 0.0) / nav, 6) if nav else None
        out["breaches"] = [{"symbol": r["symbol"], "pct_nav": r["pct_nav"], "limit": lim["hard"]}
                           for r in out.get("positions", []) if (r.get("pct_nav") or 0) > lim["hard"]]
        out["warnings"] = [{"symbol": r["symbol"], "pct_nav": r["pct_nav"], "limit": lim["soft"]}
                           for r in out.get("positions", []) if lim["soft"] < (r.get("pct_nav") or 0) <= lim["hard"]]
        out["single_name_limit"] = lim["hard"]
        out["limit_basis"] = "% of NAV (fund risk limits)"
        out["largest_pct_nav"] = max((r.get("pct_nav") or 0 for r in out.get("positions", [])), default=0.0)
    except Exception as e:
        logger.warning(f"[concentration] fund limits unavailable, using {limit_pct:.0%} of gross: {e}")
        out["limit_basis"] = f"{limit_pct:.0%} of gross (fund limits unavailable)"
    return out


@router.get("/api/v1/risk/liquidity")
async def risk_liquidity_v1(book: Optional[str] = None, participation: float = 0.20,
                            illiquid_days: float = 5.0):
    """Days-to-liquidate per position from average daily volume; flags illiquid names."""
    from api import portfolio_store
    from api.calculations.var_model import days_to_liquidate
    raw = await asyncio.to_thread(portfolio_store.list_positions, book)
    if not raw:
        return {"available": False, "reason": "No positions configured.", "positions": []}

    def _adv(ticker):
        try:
            import yfinance as yf
            h = yf.Ticker(ticker).history(period="1mo", interval="1d")
            if h is None or h.empty or "Volume" not in h:
                return None
            v = [x for x in h["Volume"].tolist() if isinstance(x, (int, float)) and x == x and x > 0]
            return float(sum(v) / len(v)) if v else None
        except Exception:
            return None

    rows = []
    for p in raw:
        sym = str(p["symbol"]).upper()
        adv = await asyncio.to_thread(_adv, sym)
        dtl = days_to_liquidate(float(p["quantity"]), adv, participation)
        rows.append({"symbol": sym, "book": p.get("book"), "quantity": p["quantity"],
                     "avg_daily_volume": round(adv) if adv else None,
                     "days_to_liquidate": dtl,
                     "illiquid": bool(dtl is not None and dtl > illiquid_days)})
    rows.sort(key=lambda r: (r["days_to_liquidate"] is None, -(r["days_to_liquidate"] or 0)))
    return {"available": True, "book": book or "Firm", "participation": participation,
            "illiquid_threshold_days": illiquid_days, "positions": rows,
            "illiquid_count": sum(1 for r in rows if r["illiquid"])}
