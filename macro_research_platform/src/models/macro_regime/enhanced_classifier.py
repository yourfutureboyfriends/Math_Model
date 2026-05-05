"""
Enhanced Regime Classification with Confidence Scoring

Addresses the limitations of the simple 2x2 matrix by:
1. Considering both level AND direction for growth and inflation
2. Adding intermediate regime classifications
3. Incorporating supporting indicator confirmation
4. Providing confidence scores

Regime Classification Framework:

Growth State (based on level + direction):
  - Strong/Improving: level > 0.5 AND direction improving/stable
  - Neutral/Stable: -0.5 <= level <= 0.5 AND direction stable
  - Weak/Deteriorating: level < -0.5 OR direction deteriorating

Inflation State (based on level + direction):
  - Low/Easing: level < -0.5 OR direction falling
  - Normal/Stable: -0.5 <= level <= 0.5 AND direction stable
  - Elevated/Rising: level > 0.5 OR direction rising

Primary Regimes:
  - Goldilocks: Growth strong/improving + Inflation low/stable
  - Reflation: Growth strong/improving + Inflation elevated/rising
  - Slowdown: Growth weak/deteriorating + Inflation low/falling
  - Stagflation: Growth weak/deteriorating + Inflation elevated/rising

Intermediate/Mixed Regimes:
  - Inflation Pressure/Late-Cycle: Growth neutral + Inflation elevated
  - Recovery/Mixed: Growth improving but low level + Inflation low
  - Mixed/Transition: Conflicting signals or unstable direction
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, List, Optional
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class RegimeClassification:
    """Complete regime classification result."""
    regime: str
    regime_category: str  # primary, intermediate, mixed
    confidence: str  # high, moderate, low, very_low
    confidence_score: float  # 0-1

    # Component states
    growth_level: float
    growth_direction: str
    growth_state: str  # strong, neutral, weak

    inflation_level: float
    inflation_direction: str
    inflation_state: str  # low, normal, elevated

    # Supporting indicators
    recession_probability: Optional[float]
    credit_stress_level: Optional[str]
    financial_conditions_category: Optional[str]

    # Validation
    validation_warnings: List[str]
    supporting_evidence: List[str]

    # Metadata
    timestamp: datetime = datetime.now()


# Regime definitions with descriptions
REGIME_DESCRIPTIONS = {
    "Goldilocks": {
        "category": "primary",
        "description": "Strong growth with contained inflation — optimal for risk assets",
        "color": "#2ecc71",  # green
    },
    "Reflation": {
        "category": "primary",
        "description": "Growth recovering with rising inflation — cyclicals favored",
        "color": "#f39c12",  # amber
    },
    "Slowdown": {
        "category": "primary",
        "description": "Weak growth with falling inflation — defensives and bonds favored",
        "color": "#3498db",  # blue
    },
    "Stagflation": {
        "category": "primary",
        "description": "Weak growth with elevated inflation — hardest regime for portfolios",
        "color": "#e74c3c",  # red
    },
    "Inflation Pressure / Late-Cycle": {
        "category": "intermediate",
        "description": "Elevated inflation with stable growth — late-cycle characteristics",
        "color": "#e67e22",  # dark orange
    },
    "Recovery / Mixed": {
        "category": "intermediate",
        "description": "Growth improving from low base with contained inflation",
        "color": "#9b59b6",  # purple
    },
    "Mixed / Transition": {
        "category": "mixed",
        "description": "Conflicting signals — high uncertainty, await clarity",
        "color": "#95a5a6",  # gray
    },
}


class EnhancedRegimeClassifier:
    """
    Enhanced regime classifier with level/direction analysis and confidence scoring.
    """

    # Thresholds for level classification
    LEVEL_THRESHOLDS = {
        "growth_strong": 0.5,
        "growth_weak": -0.5,
        "inflation_elevated": 0.5,
        "inflation_low": -0.5,
    }

    # Thresholds for direction classification (3-month change)
    DIRECTION_THRESHOLDS = {
        "improving": 0.25,
        "deteriorating": -0.25,
    }

    def __init__(self):
        pass

    def _classify_growth_state(
        self,
        level: float,
        direction_change: float,
    ) -> Tuple[str, str]:
        """
        Classify growth state based on level and direction.

        Returns:
            Tuple of (state, direction_label)
            state: strong, neutral, weak
            direction_label: improving, stable, deteriorating
        """
        th = self.DIRECTION_THRESHOLDS

        # Direction classification
        if direction_change > th["improving"]:
            direction_label = "improving"
        elif direction_change < th["deteriorating"]:
            direction_label = "deteriorating"
        else:
            direction_label = "stable"

        # State classification combining level and direction
        if level > self.LEVEL_THRESHOLDS["growth_strong"]:
            # Strong level - consider direction for nuance
            if direction_change < -0.3:
                state = "neutral"  # Peaking
            else:
                state = "strong"
        elif level < self.LEVEL_THRESHOLDS["growth_weak"]:
            # Weak level
            if direction_change > 0.3:
                state = "neutral"  # Recovering
            else:
                state = "weak"
        else:
            # Neutral level - direction matters more
            if direction_change > th["improving"]:
                state = "neutral-improving"
            elif direction_change < th["deteriorating"]:
                state = "neutral-deteriorating"
            else:
                state = "neutral"

        return state, direction_label

    def _classify_inflation_state(
        self,
        level: float,
        direction_change: float,
    ) -> Tuple[str, str]:
        """
        Classify inflation state based on level and direction.

        Returns:
            Tuple of (state, direction_label)
            state: low, normal, elevated
            direction_label: rising, stable, falling
        """
        th = self.DIRECTION_THRESHOLDS

        # Direction classification
        if direction_change > th["improving"]:
            direction_label = "rising"
        elif direction_change < th["deteriorating"]:
            direction_label = "falling"
        else:
            direction_label = "stable"

        # State classification
        if level > self.LEVEL_THRESHOLDS["inflation_elevated"]:
            state = "elevated"
        elif level < self.LEVEL_THRESHOLDS["inflation_low"]:
            state = "low"
        else:
            # Normal level
            if direction_change > th["improving"]:
                state = "normal-rising"
            elif direction_change < th["deteriorating"]:
                state = "normal-falling"
            else:
                state = "normal"

        return state, direction_label

    def _determine_base_regime(
        self,
        growth_state: str,
        inflation_state: str,
        growth_level: float,
        inflation_level: float,
    ) -> str:
        """
        Determine the base regime classification.
        """
        # Primary regime classification - use level primarily, direction for nuance
        # Level thresholds are more important than direction for primary classification
        growth_weak = growth_level < self.LEVEL_THRESHOLDS["growth_weak"] or ("weak" in growth_state and growth_level < 0)
        growth_strong = growth_level > self.LEVEL_THRESHOLDS["growth_strong"] or ("strong" in growth_state and growth_level > 0.3)
        growth_neutral = not growth_weak and not growth_strong

        inflation_elevated = inflation_level > self.LEVEL_THRESHOLDS["inflation_elevated"] or "elevated" in inflation_state
        inflation_low = inflation_level < self.LEVEL_THRESHOLDS["inflation_low"] or "low" in inflation_state
        inflation_normal = not inflation_elevated and not inflation_low

        # Stagflation requires weak growth AND elevated inflation
        if growth_weak and inflation_elevated:
            return "Stagflation"

        # Slowdown requires weak growth AND low/normal inflation
        if growth_weak and not inflation_elevated:
            return "Slowdown"

        # Reflation requires strong growth AND elevated inflation
        if growth_strong and inflation_elevated:
            return "Reflation"

        # Goldilocks requires strong growth AND low/normal inflation
        if growth_strong and not inflation_elevated:
            return "Goldilocks"

        # Intermediate cases
        if growth_neutral and inflation_elevated:
            return "Inflation Pressure / Late-Cycle"

        if growth_neutral and inflation_low:
            return "Recovery / Mixed"

        if growth_strong and inflation_normal:
            return "Reflation"  # Early reflation

        return "Mixed / Transition"

    def _calculate_confidence(
        self,
        base_regime: str,
        growth_state: str,
        inflation_state: str,
        recession_probability: Optional[float],
        credit_stress_level: Optional[str],
        financial_conditions_category: Optional[str],
    ) -> Tuple[str, float, List[str], List[str]]:
        """
        Calculate regime confidence based on supporting indicators.

        Returns:
            Tuple of (confidence_level, confidence_score, warnings, evidence)
        """
        confidence_score = 0.5  # Start with neutral confidence
        warnings = []
        evidence = []

        # Adjust for data quality (direction clarity)
        if "improving" in growth_state or "deteriorating" in growth_state:
            confidence_score += 0.15
            evidence.append("Clear growth direction")
        elif "neutral" in growth_state:
            confidence_score -= 0.05
            warnings.append("Growth direction unclear")

        if "rising" in inflation_state or "falling" in inflation_state:
            confidence_score += 0.15
            evidence.append("Clear inflation direction")
        elif "normal" in inflation_state and "stable" in inflation_state:
            confidence_score -= 0.0  # Neutral

        # Check data availability for supporting indicators
        supporting_indicators_available = sum([
            recession_probability is not None,
            credit_stress_level is not None,
            financial_conditions_category is not None,
        ])

        # Penalize for missing supporting indicators
        if supporting_indicators_available == 0:
            confidence_score -= 0.1
            warnings.append("Limited supporting indicator data")
        elif supporting_indicators_available >= 2:
            confidence_score += 0.1
            evidence.append("Good supporting indicator coverage")

        # Normalize recession probability to 0-1 scale if needed
        rec_prob = recession_probability
        if rec_prob is not None and rec_prob > 1.0:
            # Assume percentage (0-100) and convert to decimal
            rec_prob = rec_prob / 100.0

        # Adjust for supporting indicators
        if rec_prob is not None:
            if base_regime == "Stagflation":
                if rec_prob < 0.15:
                    confidence_score -= 0.3
                    warnings.append(f"Stagflation unlikely: recession risk only {rec_prob:.1%}")
                elif rec_prob > 0.30:
                    confidence_score += 0.15
                    evidence.append("Recession risk elevated — consistent with stagflation")

            elif base_regime == "Slowdown":
                if rec_prob > 0.25:
                    confidence_score += 0.1
                    evidence.append("Recession risk elevated — consistent with slowdown")
                elif rec_prob < 0.10:
                    confidence_score -= 0.15
                    warnings.append("Low recession risk contradicts slowdown view")

            elif base_regime in ["Goldilocks", "Reflation"]:
                if rec_prob > 0.25:
                    confidence_score -= 0.2
                    warnings.append(f"High recession risk ({rec_prob:.1%}) contradicts positive regime")

        # Credit stress check
        if credit_stress_level:
            if base_regime == "Stagflation" and credit_stress_level.lower() == "normal":
                confidence_score -= 0.2
                warnings.append("Normal credit stress contradicts stagflation classification")
            elif base_regime == "Slowdown" and credit_stress_level.lower() in ["elevated", "high"]:
                confidence_score += 0.1
                evidence.append("Elevated credit stress consistent with slowdown")

        # Financial conditions check
        if financial_conditions_category:
            fc = financial_conditions_category.lower()
            if base_regime == "Stagflation" and fc in ["easing", "neutral"]:
                confidence_score -= 0.15
                warnings.append("Easy financial conditions contradict stagflation")
            elif base_regime == "Goldilocks" and fc == "tightening":
                confidence_score -= 0.15
                warnings.append("Tight financial conditions contradict Goldilocks")

        # Cap confidence
        confidence_score = max(0.0, min(1.0, confidence_score))

        # Map to confidence level
        if confidence_score >= 0.75:
            confidence_level = "high"
        elif confidence_score >= 0.50:
            confidence_level = "moderate"
        elif confidence_score >= 0.30:
            confidence_level = "low"
        else:
            confidence_level = "very_low"

        return confidence_level, confidence_score, warnings, evidence

    def classify(
        self,
        growth_score: float,
        inflation_score: float,
        growth_3m_change: float,
        inflation_3m_change: float,
        recession_probability: Optional[float] = None,
        credit_stress_level: Optional[str] = None,
        financial_conditions_category: Optional[str] = None,
    ) -> RegimeClassification:
        """
        Perform full regime classification with confidence scoring.

        Args:
            growth_score: Current growth score (z-score)
            inflation_score: Current inflation score (z-score)
            growth_3m_change: 3-month change in growth score
            inflation_3m_change: 3-month change in inflation score
            recession_probability: Optional recession probability (0-100)
            credit_stress_level: Optional credit stress level string
            financial_conditions_category: Optional financial conditions category

        Returns:
            RegimeClassification with full analysis
        """
        # Classify component states
        growth_state, growth_dir = self._classify_growth_state(
            growth_score, growth_3m_change
        )
        inflation_state, inflation_dir = self._classify_inflation_state(
            inflation_score, inflation_3m_change
        )

        # Determine base regime
        base_regime = self._determine_base_regime(
            growth_state, inflation_state, growth_score, inflation_score
        )

        # Calculate confidence
        confidence_level, confidence_score, warnings, evidence = self._calculate_confidence(
            base_regime,
            growth_state,
            inflation_state,
            recession_probability,
            credit_stress_level,
            financial_conditions_category,
        )

        # Determine regime category
        regime_info = REGIME_DESCRIPTIONS.get(base_regime, {})
        regime_category = regime_info.get("category", "unknown")

        # Apply confidence-based adjustments
        final_regime = base_regime
        if confidence_level in ["low", "very_low"] and base_regime in ["Stagflation", "Goldilocks"]:
            # Downgrade high-confidence regimes to intermediate
            if base_regime == "Stagflation":
                final_regime = "Inflation Pressure / Late-Cycle"
            elif base_regime == "Goldilocks":
                final_regime = "Mixed / Transition"
            warnings.append(f"Low confidence ({confidence_level}) — downgraded from {base_regime}")

        return RegimeClassification(
            regime=final_regime,
            regime_category=regime_category,
            confidence=confidence_level,
            confidence_score=confidence_score,
            growth_level=growth_score,
            growth_direction=growth_dir,
            growth_state=growth_state,
            inflation_level=inflation_score,
            inflation_direction=inflation_dir,
            inflation_state=inflation_state,
            recession_probability=recession_probability,
            credit_stress_level=credit_stress_level,
            financial_conditions_category=financial_conditions_category,
            validation_warnings=warnings,
            supporting_evidence=evidence,
        )


def get_regime_description(regime: str) -> str:
    """Get description for a regime."""
    info = REGIME_DESCRIPTIONS.get(regime, {})
    return info.get("description", "Unknown regime")


def get_regime_color(regime: str) -> str:
    """Get color for a regime."""
    info = REGIME_DESCRIPTIONS.get(regime, {})
    return info.get("color", "#95a5a6")
