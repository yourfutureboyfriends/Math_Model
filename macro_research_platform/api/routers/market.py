"""Market data endpoints (rates, FX, commodities, prices)."""
from fastapi import APIRouter
from typing import Dict, Any
import logging

from api.schemas.models import (
    RatesData,
)
from api.utils.cache import ttl_cache

logger = logging.getLogger(__name__)
router = APIRouter(tags=["market"])


@router.get("/api/rates", response_model=RatesData)
@ttl_cache(30)
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
@ttl_cache(15)
async def get_market_overview() -> Dict[str, Any]:
    """Consolidated market overview: rates, FX, commodities, prices."""
    from api.handlers.market_handler import get_rates_data, get_fx_data, get_commodities_data, get_prices_data
    import asyncio
    rates, fx, commodities, prices = await asyncio.gather(
        get_rates_data(), get_fx_data(), get_commodities_data(), get_prices_data()
    )
    return {"rates": rates, "fx": fx, "commodities": commodities, "prices": prices}
