"""Dashboard endpoints."""
from fastapi import APIRouter
from api.schemas.models import DashboardData
import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["dashboard"])


@router.get("/api/dashboard", response_model=DashboardData)
async def get_dashboard(mode: str = "live") -> DashboardData:
    """
    Get complete dashboard data.

    Args:
        mode: Data mode ('live' or 'sample')

    Returns:
        Complete dashboard with regime, metrics, signals, etc.
    """
    # Import handler here to avoid circular imports
    from api.handlers.dashboard_handler import get_dashboard_data
    return await get_dashboard_data(mode=mode)


@router.get("/api/v2/dashboard", deprecated=True)
async def get_v2_dashboard(mode: str = "live"):
    """DEPRECATED: Use /api/dashboard instead."""
    logger.warning("DEPRECATED: /api/v2/dashboard called")
    from api.handlers.dashboard_handler import get_dashboard_data
    return await get_dashboard_data(mode=mode)


@router.get("/api/v3/dashboard", deprecated=True)
async def get_v3_dashboard(mode: str = "live"):
    """DEPRECATED: Use /api/dashboard instead."""
    logger.warning("DEPRECATED: /api/v3/dashboard called")
    from api.handlers.dashboard_handler import get_dashboard_data
    return await get_dashboard_data(mode=mode)
