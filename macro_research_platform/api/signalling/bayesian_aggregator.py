"""
Bayesian Signal Aggregator — Probabilistic Multi-Layer Signal Combination

Implements Bayesian model averaging and weighted signal aggregation.
Each signal layer provides a probability distribution over outcomes (bullish/bearish).
The aggregator combines these using:

1. Bayesian Model Averaging: posterior ∝ prior × likelihood
2. Precision weighting: more reliable signals get higher weight
3. Kalman-style update: sequential belief updating

Academic Basis:
- Raftery (1995) "Bayesian Model Selection in Social Research"
- Applied to macro forecasting: Wright (2009) "Forecasting US Inflation"
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class SignalLayer:
    """Individual signal layer input to aggregator."""
    name: str
    direction: int  # +1 bullish, -1 bearish, 0 neutral
    confidence: float  # 0-1 confidence in the signal
    horizon: str  # "short", "medium", "long"
    timestamp: datetime
    metadata: Optional[Dict] = None


@dataclass
class AggregatedSignal:
    """Result from Bayesian aggregation."""
    composite_score: float  # -1 to +1
    bullish_prob: float
    bearish_prob: float
    neutral_prob: float
    entropy: float  # Uncertainty measure
    dominant_layers: List[str]
    conflicting_signals: bool
    conviction: str  # "high", "medium", "low"
    timestamp: datetime
    layer_breakdown: Dict[str, float]


class BayesianSignalAggregator:
    """
    Aggregate multiple signal layers using Bayesian inference.

    Each layer provides a signal with confidence. The aggregator:
    1. Converts signals to probability distributions
    2. Weights by layer reliability (learned from historical accuracy)
    3. Combines using product of experts (Bayesian) or linear pooling
    """

    def __init__(
        self,
        prior_bullish: float = 0.33,
        prior_bearish: float = 0.33,
        prior_neutral: float = 0.34,
        aggregation_method: str = "bayesian",  # "bayesian" or "linear"
    ):
        self.prior = np.array([prior_bullish, prior_bearish, prior_neutral])
        self.method = aggregation_method

        # Layer reliability scores (can be updated from backtests)
        self.layer_reliability: Dict[str, float] = {}

    def set_layer_reliability(self, layer_name: str, accuracy: float):
        """Update reliability score for a signal layer (from backtesting)."""
        self.layer_reliability[layer_name] = accuracy

    def _signal_to_likelihood(
        self, layer: SignalLayer
    ) -> np.ndarray:
        """
        Convert signal direction + confidence to likelihood vector.

        [P(signal|bullish), P(signal|bearish), P(signal|neutral)]
        """
        conf = layer.confidence
        noise = 1 - conf

        if layer.direction == 1:  # Bullish
            # High prob if bullish, some noise otherwise
            likelihood = np.array([conf, noise * 0.5, noise * 0.5])
        elif layer.direction == -1:  # Bearish
            likelihood = np.array([noise * 0.5, conf, noise * 0.5])
        else:  # Neutral
            likelihood = np.array([noise * 0.5, noise * 0.5, conf])

        return likelihood / likelihood.sum()  # Normalize

    def _weight_by_reliability(self, layer: SignalLayer) -> float:
        """Get weight for a layer based on its reliability."""
        return self.layer_reliability.get(layer.name, 0.5)

    def aggregate(self, layers: List[SignalLayer]) -> AggregatedSignal:
        """
        Aggregate multiple signal layers into composite signal.

        Uses Bayesian product of experts or linear opinion pool.
        """
        if not layers:
            return AggregatedSignal(
                composite_score=0.0,
                bullish_prob=self.prior[0],
                bearish_prob=self.prior[1],
                neutral_prob=self.prior[2],
                entropy=1.0,
                dominant_layers=[],
                conflicting_signals=False,
                conviction="low",
                timestamp=datetime.now(),
                layer_breakdown={},
            )

        # Convert all signals to likelihoods
        likelihoods = []
        weights = []

        for layer in layers:
            likelihood = self._signal_to_likelihood(layer)
            likelihoods.append(likelihood)
            weights.append(self._weight_by_reliability(layer))

        likelihoods = np.array(likelihoods)
        weights = np.array(weights)
        weights = weights / weights.sum()  # Normalize

        if self.method == "bayesian":
            # Product of experts (Bayesian update)
            # Posterior ∝ Prior × ∏ Likelihood_i^weight_i
            weighted_likelihoods = np.power(likelihoods, weights.reshape(-1, 1))
            combined_likelihood = weighted_likelihoods.prod(axis=0)
            posterior = self.prior * combined_likelihood
            posterior = posterior / posterior.sum()
        else:
            # Linear opinion pool
            weighted_sum = (likelihoods * weights.reshape(-1, 1)).sum(axis=0)
            posterior = self.prior * weighted_sum
            posterior = posterior / posterior.sum()

        # Calculate entropy (uncertainty)
        entropy = -np.sum(posterior * np.log(posterior + 1e-10))
        max_entropy = np.log(3)  # Uniform distribution
        normalized_entropy = entropy / max_entropy

        # Composite score: weighted average of directions
        directions = np.array([l.direction for l in layers])
        composite = np.average(directions, weights=weights)

        # Identify dominant and conflicting layers
        bullish_layers = [l.name for l in layers if l.direction == 1]
        bearish_layers = [l.name for l in layers if l.direction == -1]

        dominant = bullish_layers if posterior[0] > posterior[1] else bearish_layers
        conflicting = len(bullish_layers) > 0 and len(bearish_layers) > 0

        # Conviction level
        max_prob = posterior.max()
        if max_prob > 0.6:
            conviction = "high"
        elif max_prob > 0.45:
            conviction = "medium"
        else:
            conviction = "low"

        # Layer breakdown
        breakdown = {}
        for layer in layers:
            breakdown[layer.name] = layer.direction * layer.confidence

        return AggregatedSignal(
            composite_score=round(float(composite), 3),
            bullish_prob=round(float(posterior[0]), 3),
            bearish_prob=round(float(posterior[1]), 3),
            neutral_prob=round(float(posterior[2]), 3),
            entropy=round(float(normalized_entropy), 3),
            dominant_layers=dominant[:3],
            conflicting_signals=conflicting,
            conviction=conviction,
            timestamp=datetime.now(),
            layer_breakdown=breakdown,
        )

    def sequential_update(
        self,
        prior_signal: AggregatedSignal,
        new_layers: List[SignalLayer],
    ) -> AggregatedSignal:
        """
        Update existing signal with new evidence (Kalman-style).

        Uses prior signal probabilities as new prior.
        """
        self.prior = np.array([
            prior_signal.bullish_prob,
            prior_signal.bearish_prob,
            prior_signal.neutral_prob,
        ])

        return self.aggregate(new_layers)


def calculate_signal_divergence(
    signal1: AggregatedSignal, signal2: AggregatedSignal
) -> float:
    """
    Calculate KL divergence between two aggregated signals.
    Higher divergence = more disagreement.
    """
    p = np.array([signal1.bullish_prob, signal1.bearish_prob, signal1.neutral_prob])
    q = np.array([signal2.bullish_prob, signal2.bearish_prob, signal2.neutral_prob])

    # KL(P||Q)
    kl = np.sum(p * np.log((p + 1e-10) / (q + 1e-10)))
    return round(float(kl), 4)


def generate_aggregator_report(
    result: AggregatedSignal, horizon: str = "medium"
) -> Dict:
    """
    Generate human-readable report from aggregated signal.
    """
    signal_name = "bullish" if result.composite_score > 0.2 else (
        "bearish" if result.composite_score < -0.2 else "neutral"
    )

    return {
        "signal": signal_name.upper(),
        "composite_score": result.composite_score,
        "confidence": result.conviction,
        "probabilities": {
            "bullish": result.bullish_prob,
            "bearish": result.bearish_prob,
            "neutral": result.neutral_prob,
        },
        "uncertainty": {
            "entropy": result.entropy,
            "conflicting_signals": result.conflicting_signals,
        },
        "supporting_layers": result.dominant_layers,
        "horizon": horizon,
        "timestamp": result.timestamp.isoformat(),
    }


# Convenience function for macro terminal integration
def aggregate_macro_signals(
    regime_signal: str,
    regime_confidence: float,
    trend_signals: Dict[str, Tuple[int, float]],
    nowcast_signal: Optional[Tuple[int, float]] = None,
) -> AggregatedSignal:
    """
    Convenience function: aggregate macro signals into composite.

    Args:
        regime_signal: Current regime name
        regime_confidence: Confidence in regime classification
        trend_signals: Dict of {name: (direction, confidence)}
        nowcast_signal: Optional (direction, confidence) for nowcast
    """
    aggregator = BayesianSignalAggregator()

    layers = []

    # Regime layer
    regime_dir = 0
    if regime_signal in ["Goldilocks", "Reflation"]:
        regime_dir = 1
    elif regime_signal in ["Stagflation", "Slowdown"]:
        regime_dir = -1

    layers.append(SignalLayer(
        name="regime_classifier",
        direction=regime_dir,
        confidence=regime_confidence,
        horizon="medium",
        timestamp=datetime.now(),
    ))

    # Trend layers
    for name, (direction, conf) in trend_signals.items():
        layers.append(SignalLayer(
            name=name,
            direction=direction,
            confidence=conf,
            horizon="medium",
            timestamp=datetime.now(),
        ))

    # Nowcast layer
    if nowcast_signal:
        layers.append(SignalLayer(
            name="nowcast",
            direction=nowcast_signal[0],
            confidence=nowcast_signal[1],
            horizon="short",
            timestamp=datetime.now(),
        ))

    return aggregator.aggregate(layers)
