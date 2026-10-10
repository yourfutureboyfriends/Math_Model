"""Portfolios: model review of your holdings, portfolio optimisation, and the auto (paper)
book. All under authenticated prefixes (/api/v1/portfolio, /api/v1/auto)."""
import asyncio
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["portfolios"])


def _equity_positions():
    from api import portfolio_store
    return [p for p in portfolio_store.list_positions() if float(p.get("quantity") or 0) != 0]


@router.get("/api/v1/portfolio/model-review")
async def model_review():
    """Your holdings run through the entry model → action, trailing stop, trend status."""
    from api.portfolio_review import review
    positions = await asyncio.to_thread(_equity_positions)
    if not positions:
        return {"holdings": [], "total_usd": 0, "counts": {},
                "reason": "No positions yet — add the stocks you hold to get the model's view."}
    return await review(positions)


@router.get("/api/v1/portfolio/optimize")
async def optimize(source: str = "my", symbols: Optional[str] = None, max_weight: float = 0.25):
    """Weights by six methods with a walk-forward comparison. source = my | auto | custom."""
    from api import auto_trader
    from api.portfolio_optimizer import optimise_async
    if not 0.02 <= max_weight <= 1.0:
        raise HTTPException(400, "max_weight must be between 0.02 and 1")
    qty: Dict[str, float] = {}
    usd: Dict[str, float] = {}
    if source == "my":
        for p in await asyncio.to_thread(_equity_positions):
            qty[p["symbol"].upper()] = qty.get(p["symbol"].upper(), 0.0) + float(p["quantity"])
        syms = [s for s, q in qty.items() if q > 0]
    elif source == "auto":
        st = await auto_trader.status()
        usd = {p["symbol"]: p["market_value_usd"] for p in st["positions"]}
        syms = list(usd)
    elif source == "custom":
        syms = [s for s in (symbols or "").replace(" ", ",").split(",") if s]
    else:
        raise HTTPException(400, "source must be my, auto or custom")
    if len(syms) < 2:
        return {"available": False, "source": source,
                "reason": "Need at least two long holdings to optimise." if source != "custom"
                else "Enter at least two tickers."}
    out = await optimise_async(syms, usd or None, max_weight, current_qty={s: qty[s] for s in syms} if qty else None)
    return {**out, "source": source}


# ── Auto (paper) book ────────────────────────────────────────────────────────
class AutoSettingsIn(BaseModel):
    enabled: Optional[bool] = None
    capital: Optional[float] = None
    max_positions: Optional[int] = None
    risk_per_trade: Optional[float] = None
    max_position: Optional[float] = None
    max_gross: Optional[float] = None
    max_drawdown: Optional[float] = None
    vol_target: Optional[float] = None
    max_per_sector: Optional[int] = None
    exclude_frontier: Optional[bool] = None


class ResetIn(BaseModel):
    capital: Optional[float] = None


def _audit(user: str, action: str, text: str) -> None:
    try:
        from api import audit_store
        audit_store.add_decision(action, text, user=user, target="auto_book")
    except Exception as e:
        logger.debug("[auto] audit failed: %s", e)


def _describe_run(res) -> str:
    """One readable line for the audit log instead of the raw result dict."""
    if not isinstance(res, dict):
        return str(res)
    if res.get("ran") is False:
        return f"Auto-book run skipped: {res.get('reason', 'no reason given')}"
    n = lambda k: len(res.get(k) or [])
    parts = [f"{n('filled')} filled", f"{n('ordered')} new orders", f"{n('exited')} exits",
             f"{n('cancelled')} cancelled"]
    tail = []
    if res.get("paused"):
        tail.append("trading paused")
    if isinstance(res.get("risk_scale"), (int, float)) and res["risk_scale"] != 1:
        tail.append(f"risk scaled to {res['risk_scale']:.0%}")
    if isinstance(res.get("equity"), (int, float)):
        tail.append(f"equity ${res['equity']:,.0f}")
    return "Auto-book run: " + ", ".join(parts) + (f" ({'; '.join(tail)})" if tail else "")


_SETTING_NAMES = {"enabled": "auto-trading", "exclude_frontier": "exclude frontier markets"}


def _describe_settings(changes: dict) -> str:
    out = []
    for k, v in changes.items():
        name = _SETTING_NAMES.get(k, k.replace("_", " "))
        out.append(f"{name} {'on' if v else 'off'}" if isinstance(v, bool) else f"{name} → {v}")
    return "Auto-book settings: " + (", ".join(out) or "no changes")


@router.get("/api/v1/auto/status")
async def auto_status():
    from api import auto_trader
    return await auto_trader.status()


@router.post("/api/v1/auto/run")
async def auto_run(request: Request):
    from api import auto_trader
    from api.core.access import require_roles
    user = require_roles(request, {"pm"})["username"]
    res = await auto_trader.run(force=True)
    await asyncio.to_thread(_audit, user, "auto_run", "Manual " + _describe_run(res)[0].lower() + _describe_run(res)[1:])
    return res


@router.put("/api/v1/auto/settings")
async def auto_settings(body: AutoSettingsIn, request: Request):
    from api import auto_trader
    from api.core.access import require_roles
    user = require_roles(request, {"pm"})["username"]
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    changes.pop("capital", None)        # capital changes only through a reset (it resets the book)
    try:
        s = await asyncio.to_thread(auto_trader.update_settings, changes)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await asyncio.to_thread(_audit, user, "auto_settings", _describe_settings(changes))
    return s


@router.post("/api/v1/auto/reset")
async def auto_reset(body: ResetIn, request: Request):
    from api import auto_trader
    from api.core.access import require_roles
    user = require_roles(request, set())["username"]           # admin only
    try:
        await asyncio.to_thread(auto_trader.reset, body.capital)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await asyncio.to_thread(_audit, user, "auto_reset", "Auto book reset" + (f" with ${body.capital:,.0f} capital" if body.capital else ""))
    return await auto_trader.status()


@router.post("/api/v1/auto/positions/{pos_id}/close")
async def auto_close(pos_id: int, request: Request):
    from api import auto_trader
    from api.core.access import require_roles
    user = require_roles(request, {"pm"})["username"]
    try:
        res = await auto_trader.close_position(pos_id, user)
    except KeyError:
        raise HTTPException(404, "open position not found")
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    await asyncio.to_thread(_audit, user, "auto_close", (f"Closed {res['closed']} at {res['price']:,.2f}, P&L ${res['pnl_usd']:+,.2f}"
                             if isinstance(res, dict) and {'closed', 'price', 'pnl_usd'} <= res.keys()
                             else f"Closed auto position {pos_id}: {res}"))
    return res


@router.get("/api/v1/auto/backtest")
async def auto_backtest():
    """The auto book's rules backtested (with ablations, a random-stock control, the Deflated
    Sharpe Ratio and a live-performance expectation) and the live book compared with it."""
    from api import auto_backtest as ab, auto_trader
    cur = await asyncio.to_thread(ab.latest)
    if not cur:
        if not ab.status()["running"]:
            _BG.add(t := asyncio.get_running_loop().create_task(ab.run_in_background()))
            t.add_done_callback(_BG.discard)
        return {"available": False, "status": ab.status(),
                "reason": "Running the first backtest of the auto book (about a minute with cached prices)."}
    live = await auto_trader.status()
    cur = {k: v for k, v in cur.items() if k not in ("live_daily_returns", "live_trade_r")} | \
          {"live_vs_backtest": await asyncio.to_thread(ab.live_vs_backtest, cur, live)}
    s = live["settings"]
    stale = any(cur["rules"].get(k) != s.get(k) for k in ("risk_per_trade", "max_positions", "max_drawdown", "vol_target"))
    return {**cur, "status": ab.status(), "rules_changed": stale}


@router.post("/api/v1/auto/backtest/run")
async def auto_backtest_run(request: Request):
    from api import auto_backtest as ab
    from api.core.access import require_roles
    require_roles(request, {"pm"})
    if not ab.status()["running"]:
        _BG.add(t := asyncio.get_running_loop().create_task(ab.run_in_background()))
        t.add_done_callback(_BG.discard)
    return {"started": True, "status": ab.status()}


_BG: set = set()
