"""Signals endpoints (nowcast, liquidity, sentiment, momentum, factors, etc.)."""
from fastapi import APIRouter
from typing import Dict, Any
import logging

from api.schemas.models import (
    NowcastData,
    LiquidityConditionsData,
    SentimentRiskData,
    ValuationFilterData,
    MomentumVetoData,
    CorrelationRegimeData,
    SignalStackData,
    SignalsData,
    FactorData,
    TrendsData,
    NewsSentimentData,
    LongtermForecastsData,
    ReflexivityData,
    FactorDecompositionData,
    GeopoliticalData,
    OptionsIntelligenceData,
)

logger = logging.getLogger(__name__)
from api.utils.cache import ttl_cache
router = APIRouter(tags=["signals"])


@router.get("/api/nowcast", response_model=NowcastData)
async def get_nowcast() -> NowcastData:
    """
    GDP Nowcast using DFM/PCA methodology.

    Estimates current quarter GDP growth using dynamic factor models
    and principal component analysis on high-frequency economic data.

    Returns:
        Dict containing:
            - nowcast: Current GDP growth estimate (annualized %)
            - confidence: Confidence interval (low, high)
            - components: Contributing factor weights
            - lastUpdated: Timestamp of calculation
            - model: "DFM/PCA" methodology identifier

    Examples:
        >>> GET /api/nowcast
        {"nowcast": 2.3, "confidence": {"low": 1.8, "high": 2.8}, ...}
    """
    from api.handlers.signal_handler import get_nowcast_data
    return await get_nowcast_data()


@router.get("/api/liquidity", response_model=LiquidityConditionsData)
async def get_liquidity() -> LiquidityConditionsData:
    """Liquidity Conditions Index."""
    from api.handlers.signal_handler import get_liquidity_data
    return await get_liquidity_data()


@router.get("/api/sentiment", response_model=SentimentRiskData)
async def get_sentiment() -> SentimentRiskData:
    """Sentiment & Risk Appetite."""
    from api.handlers.signal_handler import get_sentiment_data
    return await get_sentiment_data()


@router.get("/api/valuation", response_model=ValuationFilterData)
async def get_valuation() -> ValuationFilterData:
    """Valuation Filter."""
    from api.handlers.signal_handler import get_valuation_data
    return await get_valuation_data()


@router.get("/api/momentum-veto", response_model=MomentumVetoData)
async def get_momentum() -> MomentumVetoData:
    """Cross-Asset Momentum Veto."""
    from api.handlers.signal_handler import get_momentum_data
    return await get_momentum_data()


@router.get("/api/correlation-regime", response_model=CorrelationRegimeData)
async def get_correlation() -> CorrelationRegimeData:
    """Correlation Regime Adjustment."""
    from api.handlers.signal_handler import get_correlation_data
    return await get_correlation_data()


@router.get("/api/signal-stack", response_model=SignalStackData)
async def get_signal_stack() -> SignalStackData:
    """Signal Hierarchy & Override Logic."""
    from api.handlers.signal_handler import get_signal_stack_data
    return await get_signal_stack_data()


@router.get("/api/signals", response_model=SignalsData)
async def get_signals() -> SignalsData:
    """
    Multi-layer signal stack with conviction scoring.

    Combines growth, inflation, liquidity, and risk factors into a
    unified directional signal with confidence-weighted conviction.

    Returns:
        Dict containing:
            - finalSignal: "RISK_ON", "RISK_OFF", or "NEUTRAL"
            - conviction: Float 0.0-1.0 representing confidence
            - layers: Individual factor scores with weights
                - growth: Economic momentum score
                - inflation: Price pressure score
                - liquidity: Credit conditions score
                - risk: Market risk appetite score
            - risk_budget: Recommended position sizing (0.0-1.0)
            - regime: Current macro regime

    Examples:
        >>> GET /api/signals
        {"finalSignal": "RISK_ON", "conviction": 0.82, ...}
    """
    from api.handlers.signal_handler import get_signals_data
    return await get_signals_data()


@router.get("/api/factors", response_model=FactorData)
async def get_factors() -> FactorData:
    """AQR Factor Rotation Engine."""
    from api.handlers.signal_handler import get_factors_data
    return await get_factors_data()


@router.get("/api/trends", response_model=TrendsData)
async def get_trends() -> TrendsData:
    """CTA Trend Following."""
    from api.handlers.signal_handler import get_trends_data
    return await get_trends_data()


@router.get("/api/news-sentiment", response_model=NewsSentimentData)
async def get_news_sentiment() -> NewsSentimentData:
    """NLP News Sentiment Engine."""
    from api.handlers.signal_handler import get_news_sentiment_data
    return await get_news_sentiment_data()


@router.get("/api/forecasts/longterm", response_model=LongtermForecastsData)
async def get_longterm_forecasts() -> LongtermForecastsData:
    """GMO 7-Year Asset Class Return Model."""
    from api.handlers.signal_handler import get_longterm_forecasts_data
    return await get_longterm_forecasts_data()


@router.get("/api/reflexivity", response_model=ReflexivityData)
async def get_reflexivity() -> ReflexivityData:
    """Soros Reflexivity Detector."""
    from api.handlers.signal_handler import get_reflexivity_data
    return await get_reflexivity_data()


@router.get("/api/factors/decomposition", response_model=FactorDecompositionData)
async def get_factor_decomposition() -> FactorDecompositionData:
    """Two Sigma Factor Decomposition."""
    from api.handlers.signal_handler import get_factor_decomposition_data
    return await get_factor_decomposition_data()


@router.get("/api/geopolitical-risk", response_model=GeopoliticalData)
async def get_geopolitical() -> GeopoliticalData:
    """Geopolitical Risk Layer."""
    from api.handlers.signal_handler import get_geopolitical_data
    return await get_geopolitical_data()


@router.get("/api/options-intelligence", response_model=OptionsIntelligenceData)
async def get_options() -> OptionsIntelligenceData:
    """Options Market Intelligence."""
    from api.handlers.signal_handler import get_options_data
    return await get_options_data()


@router.post("/api/calibrate", response_model=Dict[str, Any])
async def calibrate_recession_model() -> Dict[str, Any]:
    """Re-calibrate the logistic recession model."""
    from api.handlers.signal_handler import calibrate_recession
    return await calibrate_recession()


@router.get("/api/signals/yield-curve")
@ttl_cache(60)
async def get_yield_curve_signal() -> Dict[str, Any]:
    """Yield curve structure and recession probability signal."""
    from api.handlers.market_handler import get_rates_data
    return await get_rates_data()
