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
    await asyncio.to_thread(_audit, user, "auto_run", f"Manual auto-book run: {res}")
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
    await asyncio.to_thread(_audit, user, "auto_settings", f"Auto-book settings changed: {changes}")
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
    await asyncio.to_thread(_audit, user, "auto_reset", f"Auto book reset (capital {body.capital})")
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
    await asyncio.to_thread(_audit, user, "auto_close", f"Closed auto position {pos_id}: {res}")
    return res
