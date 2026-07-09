"""Business layer endpoints (trade-ideas, recommendations, expected-returns, etc.)."""
from fastapi import APIRouter
from typing import Dict, Any, List
import logging

from api.schemas.models import (
    TradeIdeasResponse,
    MorningBriefData,
    BusinessRecommendation,
    DecisionLogResponse,
    ExpectedReturnsResponse,
    PositionSizingResponse,
    ICPackResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["business"])


@router.get("/api/trade-ideas", response_model=TradeIdeasResponse)
async def get_trade_ideas() -> TradeIdeasResponse:
    """Trade ideas endpoint for standalone access."""
    from api.handlers.business_handler import get_trade_ideas_data
    return await get_trade_ideas_data()


@router.get("/api/morning-brief")
async def get_morning_brief() -> Dict[str, Any]:
    """Morning brief endpoint for standalone access."""
    from api.handlers.business_handler import get_morning_brief_data
    return await get_morning_brief_data()


@router.get("/api/business/recommendations")
async def get_business_recommendations() -> Dict[str, Any]:
    """Get latest investment recommendations from business layer.

    Returns comprehensive recommendations including:
    - summary: Overall regime and conviction
    - expected_returns: 1-year forecasts by asset class
    - position_sizing: Target allocations with conviction
    - signal_scorecard: Key signals and their status
    """
    from api.handlers.business_handler import get_recommendations_data
    return await get_recommendations_data()


@router.get("/api/business/decision-log", response_model=DecisionLogResponse)
async def get_decision_log(limit: int = 50) -> DecisionLogResponse:
    """Get decision log entries for audit trail."""
    from api.handlers.business_handler import get_decision_log_data
    return await get_decision_log_data(limit)


@router.get("/api/business/ic-pack", response_model=ICPackResponse)
async def get_ic_pack() -> ICPackResponse:
    """Get latest Investment Committee pack."""
    from api.handlers.business_handler import get_ic_pack_data
    return await get_ic_pack_data()


@router.get("/api/business/expected-returns", response_model=ExpectedReturnsResponse)
async def get_expected_returns() -> ExpectedReturnsResponse:
    """Get expected returns from business layer."""
    from api.handlers.business_handler import get_expected_returns_data
    return await get_expected_returns_data()


@router.get("/api/business/position-sizing", response_model=PositionSizingResponse)
async def get_position_sizing() -> PositionSizingResponse:
    """Get position sizing recommendations."""
    from api.handlers.business_handler import get_position_sizing_data
    return await get_position_sizing_data()


# Business-layer commodities endpoint (proxies to market data)
@router.get("/api/business/commodities")
async def get_business_commodities() -> Dict[str, Any]:
    """Get commodities data via business layer.

    Proxies to market data service for consistency with business layer API.
    """
    from api.handlers.market_handler import get_commodities_data
    return await get_commodities_data()


@router.get("/api/business/scenario")
async def get_scenario_analysis() -> Dict[str, Any]:
    """Get scenario analysis (bull/base/bear) with probability-weighted returns."""
    from api.handlers.business_handler import get_scenario_data
    return await get_scenario_data()


@router.get("/api/business/equity-research")
async def get_equity_research() -> Dict[str, Any]:
    """Get equity research data and recommendations."""
    from api.handlers.business_handler import get_equity_research_data
    return await get_equity_research_data()


@router.get("/api/equity-research")
async def get_equity_research_standalone() -> Dict[str, Any]:
    """Get equity research data - standalone route alias."""
    from api.handlers.business_handler import get_equity_research_data
    return await get_equity_research_data()


@router.get("/api/portfolio/attribution")
async def get_portfolio_attribution() -> Dict[str, Any]:
    """Get performance attribution data (factor, sector, regime)."""
    from api.handlers.business_handler import get_attribution_data
    return await get_attribution_data()


@router.get("/api/business/trade-ideas")
async def get_business_trade_ideas() -> Dict[str, Any]:
    """Trade ideas from business layer (alias for /api/trade-ideas)."""
    from api.handlers.business_handler import get_trade_ideas_data
    return await get_trade_ideas_data()
