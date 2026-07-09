"""
Regime Service — Business logic for macro regime classification.

Computations:
- Bridgewater 2x2 regime classification
- Regime probabilities
- Regime transitions
- Regime-conditional recommendations

Reads from repository, not providers.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from api.repository.macro_repository import macro_repository
from api.services.forecast_tracker import forecast_tracker

logger = logging.getLogger(__name__)


class Regime(Enum):
    """Bridgewater 2x2 macro regimes."""
    GOLDILOCKS = "Goldilocks"      # High growth, low inflation
    REFLATION = "Reflation"        # High growth, high inflation
    STAGFLATION = "Stagflation"    # Low growth, high inflation
    SLOWDOWN = "Slowdown"          # Low growth, low inflation
    RECESSION = "Recession"        # Very low growth


class RegimeStance(Enum):
    """Risk stance based on regime."""
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    NEUTRAL = "NEUTRAL"


@dataclass
class RegimeClassification:
    """Result of regime classification."""
    regime: Regime
    confidence: float  # 0-1
    growth_score: float
    inflation_score: float
    stance: RegimeStance
    description: str


# Regime configuration
REGIME_CONFIG = {
    Regime.GOLDILOCKS: {
        "base_score": 0.60,
        "stance": RegimeStance.RISK_ON,
        "description": "Strong growth, low inflation: optimal for equities",
    },
    Regime.REFLATION: {
        "base_score": 0.40,
        "stance": RegimeStance.RISK_ON,
        "description": "Strong growth with inflation: cyclicals outperform",
    },
    Regime.STAGFLATION: {
        "base_score": -0.40,
        "stance": RegimeStance.RISK_OFF,
        "description": "Weak growth with inflation: real assets, commodities",
    },
    Regime.SLOWDOWN: {
        "base_score": -0.60,
        "stance": RegimeStance.RISK_OFF,
        "description": "Weak growth, low inflation: duration, defensive",
    },
    Regime.RECESSION: {
        "base_score": -0.80,
        "stance": RegimeStance.RISK_OFF,
        "description": "Contraction: maximum defensive positioning",
    },
}


class RegimeService:
    """
    Business service for regime classification and analysis.

    Single source of truth for all regime logic.
    No duplicated computation.
    """

    def __init__(self):
        self._repository = macro_repository
        self._current_regime: Optional[RegimeClassification] = None
        self._regime_history: List[Tuple[str, float]] = []  # (regime, timestamp)

    def classify_current(self) -> Optional[RegimeClassification]:
        """
        Classify current macro regime based on growth and inflation.

        Returns:
            RegimeClassification or None if data unavailable.
        """
        # Get macro data
        growth = self._repository.get_metric_value("growth")
        inflation = self._repository.get_metric_value("inflation")
        fed_funds = self._repository.get_metric_value("fed_funds")

        if growth is None or inflation is None:
            logger.warning("Cannot classify regime: missing growth or inflation data")
            return None

        # Normalize scores to -1 to 1 range
        # Growth: -5% to +8% maps to -1 to +1
        growth_score = max(-1.0, min(1.0, growth / 6.5))

        # Inflation: 0% to 10% maps to -1 to +1 (high inflation = negative score)
        inflation_score = max(-1.0, min(1.0, (4.0 - inflation) / 4.0))

        # Classify based on 2x2 matrix
        if growth_score > 0.2:  # High growth
            if inflation_score > 0.2:  # Low inflation
                regime = Regime.GOLDILOCKS
            else:  # High inflation
                regime = Regime.REFLATION
        else:  # Low growth
            if inflation_score > 0.2:  # Low inflation
                regime = Regime.SLOWDOWN
            else:  # High inflation
                regime = Regime.STAGFLATION

        # Check recession override
        sahm = self._repository.get_metric_value("sahm_rule")
        if sahm and sahm > 0.50:
            regime = Regime.RECESSION

        # Calculate confidence
        confidence = self._calculate_confidence(growth_score, inflation_score)

        config = REGIME_CONFIG[regime]

        classification = RegimeClassification(
            regime=regime,
            confidence=confidence,
            growth_score=growth_score,
            inflation_score=inflation_score,
            stance=config["stance"],
            description=config["description"],
        )

        self._current_regime = classification

        # Log to forecast tracker for validation
        try:
            forecast_tracker.log_regime_forecast(
                regime=regime.value,
                confidence=confidence,
                growth_score=growth_score,
                inflation_score=inflation_score,
                method="threshold",
                model_params={
                    "threshold": 0.2,
                    "sahm_threshold": 0.50,
                    "fed_funds": fed_funds,
                }
            )
        except Exception as e:
            logger.warning(f"[RegimeService] Failed to log forecast: {e}")

        return classification

    def _calculate_confidence(
        self,
        growth_score: float,
        inflation_score: float
    ) -> float:
        """
        Calculate confidence in regime classification.

        Confidence is higher when scores are farther from boundaries.
        """
        # Distance from 0 (boundary)
        growth_distance = abs(growth_score)
        inflation_distance = abs(inflation_score)

        # Average distance
        avg_distance = (growth_distance + inflation_distance) / 2

        # Map to 0-1 range
        return min(1.0, max(0.0, avg_distance + 0.3))

    def get_current(self) -> Optional[RegimeClassification]:
        """Get cached current regime or compute if needed."""
        if self._current_regime is None:
            return self.classify_current()
        return self._current_regime

    def get_regime_as_dict(self) -> Optional[Dict[str, Any]]:
        """Get current regime as dictionary for API response."""
        regime = self.get_current()
        if not regime:
            return None

        return {
            "current": regime.regime.value,
            "confidence": round(regime.confidence, 2),
            "growth_score": round(regime.growth_score, 2),
            "inflation_score": round(regime.inflation_score, 2),
            "stance": regime.stance.value,
            "description": regime.description,
        }

    def get_sector_recommendations(self, regime: Optional[Regime] = None) -> List[Dict[str, Any]]:
        """
        Get sector recommendations for a regime.

        Args:
            regime: Target regime (default: current)

        Returns:
            List of sector recommendations.
        """
        if regime is None:
            r = self.get_current()
            regime = r.regime if r else Regime.SLOWDOWN

        recommendations = {
            Regime.GOLDILOCKS: [
                {"sector": "Technology", "weight": "overweight", "rationale": "Growth supports tech"},
                {"sector": "Consumer Discretionary", "weight": "overweight", "rationale": "Strong consumer"},
                {"sector": "Financials", "weight": "overweight", "rationale": "Rising rates benefit banks"},
            ],
            Regime.REFLATION: [
                {"sector": "Materials", "weight": "overweight", "rationale": "Commodity exposure"},
                {"sector": "Energy", "weight": "overweight", "rationale": "Inflation beneficiary"},
                {"sector": "Financials", "weight": "overweight", "rationale": "Steep curve"},
            ],
            Regime.STAGFLATION: [
                {"sector": "Real Estate", "weight": "overweight", "rationale": "Real assets"},
                {"sector": "Energy", "weight": "overweight", "rationale": "Supply constraints"},
                {"sector": "Utilities", "weight": "overweight", "rationale": "Defensive income"},
            ],
            Regime.SLOWDOWN: [
                {"sector": "Utilities", "weight": "overweight", "rationale": "Defensive"},
                {"sector": "Consumer Staples", "weight": "overweight", "rationale": "Defensive"},
                {"sector": "Healthcare", "weight": "overweight", "rationale": "Defensive"},
            ],
            Regime.RECESSION: [
                {"sector": "Utilities", "weight": "overweight", "rationale": "Maximum defensive"},
                {"sector": "Consumer Staples", "weight": "overweight", "rationale": "Essential spending"},
                {"sector": "Healthcare", "weight": "overweight", "rationale": "Non-cyclical"},
                {"sector": "Treasuries", "weight": "overweight", "rationale": "Duration exposure"},
            ],
        }

        return recommendations.get(regime, [])

    def get_factor_bias(self) -> Dict[str, str]:
        """Get factor bias based on current regime."""
        regime = self.get_current()
        if not regime:
            return {"error": "No regime data"}

        biases = {
            Regime.GOLDILOCKS: {
                "value": "neutral",
                "growth": "overweight",
                "momentum": "overweight",
                "quality": "neutral",
                "low_vol": "underweight",
            },
            Regime.REFLATION: {
                "value": "overweight",
                "growth": "neutral",
                "momentum": "overweight",
                "quality": "neutral",
                "low_vol": "underweight",
            },
            Regime.STAGFLATION: {
                "value": "overweight",
                "growth": "underweight",
                "momentum": "underweight",
                "quality": "overweight",
                "low_vol": "overweight",
            },
            Regime.SLOWDOWN: {
                "value": "overweight",
                "growth": "underweight",
                "momentum": "underweight",
                "quality": "overweight",
                "low_vol": "overweight",
            },
            Regime.RECESSION: {
                "value": "overweight",
                "growth": "underweight",
                "momentum": "underweight",
                "quality": "overweight",
                "low_vol": "overweight",
            },
        }

        return biases.get(regime.regime, {})


# Global instance
regime_service = RegimeService()
