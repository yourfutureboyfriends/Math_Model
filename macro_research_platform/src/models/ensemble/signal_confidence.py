"""
Signal Confidence Engine

Computes confidence scores for model signals based on:
- Signal strength
- Data quality
- Cross-indicator agreement
- Momentum confirmation
- Data recency
- Revision risk
- Backtest reliability

Output: Low, Medium, High confidence
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceResult:
    """Confidence calculation result."""
    overall_confidence: str  # low, medium, high
    confidence_score: float  # 0-1
    components: Dict[str, float]
    drivers: List[str]
    recommendation: str


class SignalConfidenceEngine:
    """
    Signal Confidence Engine

    Combines multiple factors to assess confidence in model signals.
    """

    def __init__(self):
        # Component weights
        self.weights = {
            "signal_strength": 0.25,
            "data_quality": 0.20,
            "cross_indicator_agreement": 0.20,
            "momentum_confirmation": 0.15,
            "recency": 0.10,
            "revision_risk": 0.10,
        }

    def _calculate_signal_strength_score(
        self,
        signal_scores: Dict[str, float],
    ) -> float:
        """
        Score based on signal magnitude.

        Stronger signals (further from zero) = higher confidence
        """
        if not signal_scores:
            return 0.0

        # Average absolute score
        avg_magnitude = np.mean([abs(v) for v in signal_scores.values()])

        # Score: |signal| > 1.0 = 1.0 confidence, |signal| > 0.5 = 0.7, etc.
        if avg_magnitude > 1.0:
            return 1.0
        elif avg_magnitude > 0.5:
            return 0.7 + (avg_magnitude - 0.5) * 0.6
        else:
            return 0.3 + avg_magnitude * 0.8

    def _calculate_data_quality_score(
        self,
        data_quality_scores: Dict[str, float],
    ) -> float:
        """Score based on underlying data quality."""
        if not data_quality_scores:
            return 0.5

        # Weight by importance (simplified - would use indicator weights)
        return np.mean(list(data_quality_scores.values()))

    def _calculate_cross_indicator_agreement(
        self,
        signal_scores: Dict[str, float],
        groups: Optional[Dict[str, List[str]]] = None,
    ) -> float:
        """
        Score based on agreement across indicators.

        If multiple indicators point same direction = higher confidence
        """
        if not signal_scores or len(signal_scores) < 2:
            return 0.5

        # Check sign agreement
        signs = [np.sign(v) for v in signal_scores.values() if v != 0]

        if not signs:
            return 0.5

        # Fraction agreeing with majority sign
        from collections import Counter
        sign_counts = Counter(signs)
        majority_count = sign_counts.most_common(1)[0][1]
        agreement = majority_count / len(signs)

        return agreement

    def _calculate_momentum_confirmation(
        self,
        signal_history: pd.DataFrame,
        lookback: int = 3,
    ) -> float:
        """
        Score based on signal direction persistence.

        Signals that have been building = higher confidence
        """
        if signal_history is None or len(signal_history) < lookback + 1:
            return 0.5

        # Check if recent signals are trending
        recent = signal_history.iloc[-lookback:].mean()
        previous = signal_history.iloc[-(lookback*2):-lookback].mean()

        # If same direction and building, higher confidence
        if np.sign(recent) == np.sign(previous):
            if abs(recent) > abs(previous):
                return 0.8  # Building momentum
            else:
                return 0.6  # Consistent but fading
        else:
            return 0.3  # Direction changed

    def _calculate_recency_score(
        self,
        freshness_scores: Dict[str, float],
    ) -> float:
        """Score based on data recency."""
        if not freshness_scores:
            return 0.5

        return np.mean(list(freshness_scores.values()))

    def _calculate_revision_risk_score(
        self,
        indicator_types: Dict[str, str],
    ) -> float:
        """
        Score based on revision risk.

        Some indicators (like GDP, payrolls) get heavily revised.
        """
        revision_risk_weights = {
            "gdp": 0.3,  # High revision risk
            "payrolls": 0.4,  # Moderate revision risk
            "cpi": 0.8,  # Low revision risk
            "market": 0.9,  # Very low revision risk
            "survey": 0.6,  # Some revision risk
        }

        if not indicator_types:
            return 0.5

        risks = []
        for ind, typ in indicator_types.items():
            risks.append(revision_risk_weights.get(typ, 0.5))

        return np.mean(risks) if risks else 0.5

    def compute_confidence(
        self,
        signal_scores: Dict[str, float],
        data_quality_scores: Optional[Dict[str, float]] = None,
        freshness_scores: Optional[Dict[str, float]] = None,
        signal_history: Optional[pd.DataFrame] = None,
        indicator_types: Optional[Dict[str, str]] = None,
    ) -> ConfidenceResult:
        """
        Compute overall confidence score.

        Returns:
            ConfidenceResult with level and components
        """
        components = {}
        drivers = []

        # 1. Signal strength
        components["signal_strength"] = self._calculate_signal_strength_score(
            signal_scores
        )
        if components["signal_strength"] < 0.5:
            drivers.append("Weak signal strength")
        elif components["signal_strength"] > 0.8:
            drivers.append("Strong signal strength")

        # 2. Data quality
        components["data_quality"] = self._calculate_data_quality_score(
            data_quality_scores or {}
        )
        if components["data_quality"] < 0.5:
            drivers.append("Low data quality")

        # 3. Cross-indicator agreement
        components["cross_indicator_agreement"] = self._calculate_cross_indicator_agreement(
            signal_scores
        )
        if components["cross_indicator_agreement"] < 0.6:
            drivers.append("Mixed signals across indicators")
        elif components["cross_indicator_agreement"] > 0.8:
            drivers.append("Strong cross-indicator agreement")

        # 4. Momentum confirmation
        components["momentum_confirmation"] = self._calculate_momentum_confirmation(
            signal_history
        )
        if components["momentum_confirmation"] < 0.4:
            drivers.append("Momentum not confirmed")

        # 5. Recency
        components["recency"] = self._calculate_recency_score(
            freshness_scores or {}
        )
        if components["recency"] < 0.5:
            drivers.append("Stale data")

        # 6. Revision risk (inverted - lower risk = higher score)
        revision_risk = self._calculate_revision_risk_score(indicator_types or {})
        components["revision_risk"] = revision_risk  # Already inverted

        # Calculate weighted score
        total_score = sum(
            self.weights.get(k, 0) * components[k]
            for k in components.keys()
        )

        # Classify confidence level
        if total_score >= 0.7:
            confidence_level = "high"
        elif total_score >= 0.4:
            confidence_level = "medium"
        else:
            confidence_level = "low"

        # Generate recommendation
        recommendation = self._get_recommendation(confidence_level, drivers)

        return ConfidenceResult(
            overall_confidence=confidence_level,
            confidence_score=round(total_score, 2),
            components=components,
            drivers=drivers,
            recommendation=recommendation,
        )

    def _get_recommendation(self, confidence: str, drivers: List[str]) -> str:
        """Generate recommendation based on confidence."""
        if confidence == "high":
            return (
                "High confidence - can increase position sizes. "
                "Multiple factors confirm the signal."
            )
        elif confidence == "medium":
            return (
                "Medium confidence - standard position sizing. "
                "Consider: " + ", ".join(drivers[:2])
            )
        else:
            return (
                "Low confidence - consider reducing position sizes or waiting. "
                "Issues: " + ", ".join(drivers)
            )


def get_regime_confidence(
    regime: str,
    scores: Dict[str, float],
    data_freshness: Optional[Dict[str, str]] = None,
) -> ConfidenceResult:
    """
    Convenience function to get confidence for regime classification.

    Args:
        regime: Current regime classification
        scores: Current macro scores
        data_freshness: Data freshness status per indicator

    Returns:
        ConfidenceResult
    """
    engine = SignalConfidenceEngine()

    # Map freshness to scores
    freshness_map = {
        "fresh": 1.0,
        "acceptable": 0.7,
        "stale": 0.4,
        "severely_stale": 0.0,
        "missing": 0.0,
        "sample": 0.3,
    }

    freshness_scores = {}
    if data_freshness:
        freshness_scores = {
            k: freshness_map.get(v, 0.5)
            for k, v in data_freshness.items()
        }

    return engine.compute_confidence(
        signal_scores=scores,
        freshness_scores=freshness_scores,
    )
