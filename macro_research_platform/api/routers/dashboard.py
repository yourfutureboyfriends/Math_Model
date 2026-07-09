"""Dashboard endpoints."""
from fastapi import APIRouter
from api.schemas.models import DashboardData
import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["dashboard"])


@router.get("/api/dashboard", response_model=DashboardData)
async def get_dashboard(mode: str = "live") -> DashboardData:
    """
    Get complete dashboard with regime, metrics, signals, and analytics.

    Aggregates macro regime classification, key economic metrics,
    signal stack, sector allocation, and risk analytics into a
    unified dashboard response.

    Args:
        mode: Data mode
            - "live" (default): Real-time data from data sources
            - "sample": Demo/sample data for testing

    Returns:
        DashboardData with all dashboard sections:
            - regime: Current macro regime with confidence score
            - keyMetrics: Economic indicators (GDP, inflation, etc.)
            - recession: Recession probability and indicators
            - signals: Multi-layer signal stack with conviction
            - sectorAllocation: Recommended sector weights
            - riskParity: Portfolio construction
            - expectedReturns: Forward-looking return forecasts
            - timestamp: Generation timestamp

    Raises:
        HTTPException: 500 if critical data fetch fails

    Examples:
        >>> GET /api/dashboard
        >>> GET /api/dashboard?mode=sample

    Notes:
        Dashboard is validated at generation time if
        ENABLE_RUNTIME_VALIDATION environment variable is set.
    """
    # Import handler here to avoid circular imports
    from api.handlers.dashboard_handler import get_dashboard_data
    return await get_dashboard_data(mode=mode)
