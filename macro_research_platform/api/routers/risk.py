"""Risk endpoints (recession, alerts, risk/full)."""
from fastapi import APIRouter
from typing import Dict, Any
import logging

from api.schemas.models import (
    RecessionData,
    AdvancedIndicatorsData,
    AlertsData,
    FullRiskData,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["risk"])


@router.get("/api/recession", response_model=RecessionData)
async def get_recession() -> RecessionData:
    """
    Detailed recession risk endpoint with all three model outputs.

    Combines three complementary recession probability models:
    - Logistic regression: Traditional economic indicators
    - Sahm Rule: Unemployment-based recession signal
    - Estrella-Mishkin: Yield curve-based probability

    Returns:
        Dict containing:
            - probability: Weighted average recession probability (0.0-1.0)
            - regime: Risk level classification (Low/Medium/High)
            - models: Individual model outputs
                - logistic: {probability, signal}
                - sahm: {probability, signal}
                - estrella_mishkin: {probability, signal}
            - indicators: Key predictive indicators
                - yield_curve: 10Y-2Y spread
                - credit_spreads: Investment grade spreads
                - unemployment: Current unemployment rate
            - lastUpdated: ISO timestamp

    Examples:
        >>> GET /api/recession
        {"probability": 0.25, "regime": "Low Risk", "models": {...}}

    Notes:
        Probability thresholds: Low (<0.3), Medium (0.3-0.6), High (>0.6)
    """
    from api.handlers.risk_handler import get_recession_data
    return await get_recession_data()


@router.get("/api/advanced", response_model=AdvancedIndicatorsData)
async def get_advanced() -> AdvancedIndicatorsData:
    """Advanced indicators: Sahm, Credit Impulse, LEI, Risk Parity."""
    from api.handlers.risk_handler import get_advanced_indicators
    return await get_advanced_indicators()


@router.get("/api/alerts", response_model=AlertsData)
async def get_alerts() -> AlertsData:
    """Get active alerts."""
    from api.handlers.risk_handler import get_alerts_data
    return await get_alerts_data()


@router.get("/api/risk/full", response_model=FullRiskData)
async def get_full_risk() -> FullRiskData:
    """
    Comprehensive risk analytics for portfolio or benchmark.

    Returns full suite of risk metrics including Sharpe ratio,
    Sortino ratio, VaR, CVaR, max drawdown, and stress test results.

    When no user portfolio is loaded, returns S&P 500 benchmark
    statistics as a proxy.

    Returns:
        Dict containing:
            - sharpe: Sharpe ratio (risk-adjusted return)
            - sortino: Sortino ratio (downside risk only)
            - calmar: Calmar ratio (return/max drawdown)
            - informationRatio: Active return vs benchmark
            - var95: Value at Risk (95% confidence)
            - cvar95: Conditional VaR (expected shortfall)
            - maxDrawdown: Maximum historical drawdown
            - correlation: Asset correlation matrix
            - stressTests: Scenario analysis results
            - riskAdjustedReturns: Detailed breakdown
            - status: Data source indicator
            - lastUpdated: ISO timestamp

    Examples:
        >>> GET /api/risk/full
        {"sharpe": 0.85, "maxDrawdown": -8.5, "var95": 0.0125, ...}

    Notes:
        Stress tests include: 2008 Crisis, 2020 COVID, 2022 Inflation
    """
    from api.handlers.risk_handler import get_full_risk_data
    return await get_full_risk_data()
