"""Market data endpoints (rates, FX, commodities, prices)."""
from fastapi import APIRouter, Query
from typing import Dict, Any
import logging

from api.schemas.models import (
    RatesData,
)
from api.utils.cache import ttl_cache

logger = logging.getLogger(__name__)
router = APIRouter(tags=["market"])


@router.get("/api/rates", response_model=RatesData)
@ttl_cache(120, offload=True)
async def get_rates() -> RatesData:
    """Get interest rates data."""
    from api.handlers.market_handler import get_rates_data
    return await get_rates_data()


@router.get("/api/fx")
async def get_fx() -> Dict[str, Any]:
    """Get FX data."""
    from api.handlers.market_handler import get_fx_data
    return await get_fx_data()


@router.get("/api/commodities")
async def get_commodities() -> Dict[str, Any]:
    """Get commodities data with macro signals."""
    from api.handlers.market_handler import get_commodities_data
    return await get_commodities_data()


@router.get("/api/prices")
async def get_prices() -> Dict[str, Any]:
    """Get current prices for key assets."""
    from api.handlers.market_handler import get_prices_data
    return await get_prices_data()


@router.get("/api/market")
@ttl_cache(120, offload=True)
async def get_market_overview() -> Dict[str, Any]:
    """Consolidated market overview: rates, FX, commodities, prices."""
    from api.handlers.market_handler import get_rates_data, get_fx_data, get_commodities_data, get_prices_data
    import asyncio
    rates, fx, commodities, prices = await asyncio.gather(
        get_rates_data(), get_fx_data(), get_commodities_data(), get_prices_data()
    )
    return {"rates": rates, "fx": fx, "commodities": commodities, "prices": prices}


@router.get("/api/v1/market/bars")
async def market_bars(symbol: str, interval: str = "1d", period: str = "1y",
                      start: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"), end: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$")):
    """OHLCV bars for the interactive chart — interval 5m/15m/1h/1d/1wk/1mo, period 1d…max."""
    import asyncio as _asyncio
    from fastapi import HTTPException as _HTTPException
    from api import market_bars as mb
    try:
        return await _asyncio.to_thread(mb.bars, symbol, interval, period, start, end)
    except ValueError as e:
        raise _HTTPException(400, {"message": str(e), "allowed_periods": mb.allowed_periods(interval)})
    except LookupError as e:
        raise _HTTPException(404, str(e))
