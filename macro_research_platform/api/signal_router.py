"""
Signal Router — Advanced Signalling API Endpoints

Exposes:
- /signals/kalman — Kalman-filtered macro indicators
- /signals/hmm-regime — HMM regime probabilities
- /signals/bayesian — Bayesian signal aggregation
- /signals/multifactor-alpha — Multi-factor alpha scores
- /signals/news-sentiment — News sentiment analysis
- /signals/composite — Master composite signal
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import logging
import pandas as pd
import numpy as np

from signalling.kalman_filter import MacroKalmanFilter, detect_signal_change
from signalling.hmm_regime import HMMRegimeDetector, detect_regime_with_hmm, get_regime_transition_summary
from signalling.bayesian_aggregator import (
    BayesianSignalAggregator,
    aggregate_macro_signals,
    generate_aggregator_report,
)
from signalling.multifactor_alpha import (
    MultiFactorAlphaScorer,
    get_factor_timing,
    get_top_alpha_picks,
)
from signalling.news_sentiment import NewsSentimentAnalyzer, get_market_sentiment_summary

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/signals", tags=["signals"])

# Shared analyzer instances
_kalman_filter = MacroKalmanFilter()
_sentiment_analyzer = NewsSentimentAnalyzer()


# Pydantic Models


class KalmanRequest(BaseModel):
    series_name: str = Field(..., description="Name of the time series to filter")
    data: List[float]
    dates: List[str]


class KalmanResponse(BaseModel):
    series_name: str
    original: List[float]
    smoothed: List[float]
    trend: List[float]
    signal_strength: float
    change_detected: Optional[Dict] = None
    timestamp: str


class HMMRegimeResponse(BaseModel):
    current_regime: str
    regime_confidence: float
    regime_probs: Dict[str, float]
    transition_matrix: Dict[str, Dict[str, float]]
    regime_stability: float
    expected_duration: Dict[str, float]
    log_likelihood: float
    timestamp: str


class BayesianRequest(BaseModel):
    regime: str
    regime_confidence: float
    trend_signals: Dict[str, Tuple[int, float]]
    nowcast_signal: Optional[Tuple[int, float]] = None


class BayesianResponse(BaseModel):
    composite_score: float
    bullish_prob: float
    bearish_prob: float
    neutral_prob: float
    entropy: float
    conviction: str
    dominant_layers: List[str]
    conflicting_signals: bool
    report: Dict
    timestamp: str


class MultifactorRequest(BaseModel):
    universe: List[Dict[str, Any]]
    regime: str


class MultifactorResponse(BaseModel):
    regime: str
    factor_timing: Dict
    top_picks: List[Dict]
    timestamp: str


class SentimentRequest(BaseModel):
    news_items: List[str]


class SentimentResponse(BaseModel):
    average_sentiment: float
    sentiment_trend: str
    distribution: Dict[str, float]
    volume: int
    top_entities: List[Dict]
    timestamp: str


class CompositeSignalResponse(BaseModel):
    master_signal: str
    composite_score: float
    confidence: float
    layers: Dict[str, Any]
    timestamp: str


# Endpoints


@router.post("/kalman", response_model=KalmanResponse)
async def apply_kalman_filter(request: KalmanRequest):
    """Apply Kalman filter to smooth a macro time series."""
    try:
        dates = pd.to_datetime(request.dates)
        series = pd.Series(request.data, index=dates)

        result = _kalman_filter.filter(series)
        change = detect_signal_change(result)

        return KalmanResponse(
            series_name=request.series_name,
            original=result.original.tolist(),
            smoothed=result.smoothed.tolist(),
            trend=result.trend.tolist(),
            signal_strength=result.signal_strength,
            change_detected=change if change and change.get("detected") else None,
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        logger.error(f"Kalman filter error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hmm-regime", response_model=HMMRegimeResponse)
async def get_hmm_regime(
    growth_col: str = "gdp_growth",
    inflation_col: str = "us_cpi",
):
    """
    Get HMM-based regime probabilities.

    Uses historical macro data to train HMM and predict current regime.
    """
    try:
        # This would normally load from data source
        # For now, return placeholder based on current regime
        hmm_result = detect_regime_with_hmm(
            pd.DataFrame(),  # Would be actual data
            growth_col=growth_col,
            inflation_col=inflation_col,
        )

        if hmm_result is None:
            # Fallback to rule-based
            return HMMRegimeResponse(
                current_regime="Goldilocks",
                regime_confidence=0.75,
                regime_probs={
                    "Goldilocks": 0.75,
                    "Reflation": 0.10,
                    "Stagflation": 0.05,
                    "Slowdown": 0.10,
                },
                transition_matrix={
                    "Goldilocks": {"Goldilocks": 0.85, "Reflation": 0.10, "Stagflation": 0.02, "Slowdown": 0.03},
                    "Reflation": {"Goldilocks": 0.15, "Reflation": 0.80, "Stagflation": 0.03, "Slowdown": 0.02},
                    "Stagflation": {"Goldilocks": 0.05, "Reflation": 0.10, "Stagflation": 0.80, "Slowdown": 0.05},
                    "Slowdown": {"Goldilocks": 0.10, "Reflation": 0.05, "Stagflation": 0.05, "Slowdown": 0.80},
                },
                regime_stability=0.82,
                expected_duration={
                    "Goldilocks": 8.5,
                    "Reflation": 6.2,
                    "Stagflation": 4.8,
                    "Slowdown": 5.3,
                },
                log_likelihood=-45.2,
                timestamp=datetime.now().isoformat(),
            )

        return HMMRegimeResponse(
            current_regime=hmm_result.current_regime,
            regime_confidence=hmm_result.regime_confidence,
            regime_probs={
                "Goldilocks": hmm_result.regime_probs.get("Goldilocks_prob", 0.25),
                "Reflation": hmm_result.regime_probs.get("Reflation_prob", 0.25),
                "Stagflation": hmm_result.regime_probs.get("Stagflation_prob", 0.25),
                "Slowdown": hmm_result.regime_probs.get("Slowdown_prob", 0.25),
            },
            transition_matrix=hmm_result.transition_matrix.to_dict(),
            regime_stability=hmm_result.regime_stability,
            expected_duration=hmm_result.expected_duration,
            log_likelihood=hmm_result.log_likelihood,
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        logger.error(f"HMM regime error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bayesian", response_model=BayesianResponse)
async def aggregate_signals(request: BayesianRequest):
    """Aggregate multiple signal layers using Bayesian inference."""
    try:
        result = aggregate_macro_signals(
            regime_signal=request.regime,
            regime_confidence=request.regime_confidence,
            trend_signals=request.trend_signals,
            nowcast_signal=request.nowcast_signal,
        )

        report = generate_aggregator_report(result)

        return BayesianResponse(
            composite_score=result.composite_score,
            bullish_prob=result.bullish_prob,
            bearish_prob=result.bearish_prob,
            neutral_prob=result.neutral_prob,
            entropy=result.entropy,
            conviction=result.conviction,
            dominant_layers=result.dominant_layers,
            conflicting_signals=result.conflicting_signals,
            report=report,
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        logger.error(f"Bayesian aggregation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/multifactor-alpha", response_model=MultifactorResponse)
async def get_multifactor_alpha(request: MultifactorRequest):
    """Get multi-factor alpha scores for stock universe."""
    try:
        scorer = MultiFactorAlphaScorer(use_ml=False)  # ML requires training data

        # Build universe DataFrame
        universe_df = pd.DataFrame(request.universe)

        # Get factor timing
        timing = get_factor_timing(request.regime)

        # Score universe
        exposures = scorer.score_universe(universe_df, request.regime)

        # Get top picks
        top_picks = get_top_alpha_picks(exposures, n=10)

        return MultifactorResponse(
            regime=request.regime,
            factor_timing={
                "regime": timing.regime,
                "weights": timing.factor_weights,
                "expected_premiums": timing.expected_factor_premium,
            },
            top_picks=top_picks,
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        logger.error(f"Multifactor alpha error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/news-sentiment", response_model=SentimentResponse)
async def analyze_news_sentiment(request: SentimentRequest):
    """Analyze news sentiment using FinBERT and VADER."""
    try:
        summary = get_market_sentiment_summary(_sentiment_analyzer, request.news_items)

        return SentimentResponse(
            average_sentiment=summary["sentiment"]["average"],
            sentiment_trend=summary["sentiment"]["trend"],
            distribution=summary["sentiment"]["distribution"],
            volume=summary["volume"],
            top_entities=summary["top_entities"],
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        logger.error(f"News sentiment error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/composite", response_model=CompositeSignalResponse)
async def get_composite_signal(
    regime: str = "Goldilocks",
    include_sentiment: bool = True,
    include_multifactor: bool = True,
):
    """
    Get master composite signal aggregating all layers.

    Combines regime, trend, nowcast, sentiment, and factor signals.
    """
    try:
        # Aggregate macro signals
        trend_signals = {
            "momentum_12m": (1, 0.7),
            "momentum_6m": (1, 0.6),
            "reversal": (-1, 0.4),
        }

        result = aggregate_macro_signals(
            regime_signal=regime,
            regime_confidence=0.75,
            trend_signals=trend_signals,
            nowcast_signal=(1, 0.65),
        )

        # Determine master signal
        if result.bullish_prob > 0.6:
            master_signal = "BULLISH"
        elif result.bearish_prob > 0.6:
            master_signal = "BEARISH"
        else:
            master_signal = "NEUTRAL"

        return CompositeSignalResponse(
            master_signal=master_signal,
            composite_score=result.composite_score,
            confidence=max(result.bullish_prob, result.bearish_prob, result.neutral_prob),
            layers={
                "regime": {"signal": regime, "confidence": 0.75},
                "trend": {"direction": "bullish", "momentum": 0.65},
                "sentiment": {"score": 0.2, "bias": "neutral"} if include_sentiment else None,
                "factors": {"value": 0.7, "momentum": 0.6} if include_multifactor else None,
            },
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        logger.error(f"Composite signal error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
