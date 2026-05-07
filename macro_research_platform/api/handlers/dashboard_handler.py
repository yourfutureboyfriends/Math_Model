"""Dashboard data handler."""
from api.schemas.models import DashboardData, RegimeData, KeyMetrics, RecessionData, SignalsData
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


async def get_dashboard_data(mode: str = "live") -> DashboardData:
    """
    Build complete dashboard data.

    Args:
        mode: Data mode

    Returns:
        Complete dashboard
    """
    # Placeholder implementation
    # Full implementation will be extracted from main.py in future step
    logger.info(f"Building dashboard data (mode: {mode})")

    return DashboardData(
        regime=RegimeData.default(),
        keyMetrics=KeyMetrics.default(),
        recession=RecessionData(
            probability=0.15,
            level="Low",
            logisticProb=0.12,
            emProbitProb=0.18,
            sahmValue=0.0,
            sahmSignal="No Signal",
            description="Low probability",
            components=[],
            history=[]
        ),
        signals=SignalsData(
            finalSignal="Neutral",
            growth={"score": 0.5, "threeMonth": 0.2, "state": "Neutral"},
            inflation={"score": 0.3, "threeMonth": 0.1, "state": "Neutral"},
            liquidity={"score": 0.4, "threeMonth": 0.2, "state": "Neutral"},
            risk={"score": 0.2, "threeMonth": 0.0, "state": "Neutral"}
        ),
        sectorAllocation={
            "sectors": [],
            "regime": "Unknown",
            "confidence": 0.0,
            "totalScore": 0.0
        },
        riskParity={
            "holdings": [],
            "totalHoldings": 0,
            "lastRebalanced": datetime.now().isoformat(),
            "methodology": "Placeholder",
            "portfolioVol": None,
            "diversificationRatio": None,
            "regimeAdjustmentActive": False,
            "lastUpdated": datetime.now().isoformat()
        },
        expectedReturns={
            "sectors": [],
            "weightedPortfolioReturn": 0.0,
            "methodology": "Placeholder",
            "lastUpdated": datetime.now().isoformat()
        },
        timestamp=datetime.now().isoformat(),
        mode=mode
    )
