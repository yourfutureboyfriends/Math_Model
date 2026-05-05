"""
Sector Rotation Engine — Regime-Aware Sector Allocation

Maps macro regimes to sector performance and generates
regime-appropriate sector overweight/underweight recommendations.

Bridgewater Four-Environment Framework applied to sectors:
- Growth Up: Cyclicals outperform (Tech, Consumer Discretionary, Industrials)
- Growth Down: Defensives outperform (Utilities, Staples, Healthcare)
- Inflation Up: Real assets outperform (Energy, Materials, Financials)
- Inflation Down: Duration assets outperform (Growth, Tech, Long-duration)

Sector Regime Performance (based on historical analysis):
┌─────────────────────────────────────────────────────────────┐
│ Regime      │ Best Sectors              │ Worst Sectors     │
├─────────────────────────────────────────────────────────────┤
│ Goldilocks  │ Tech, Cons Disc, Industrials │ Utilities, Staples│
│ Reflation   │ Energy, Materials, Fin    │ Tech, Long-duration│
│ Stagflation │ Energy, Staples, Health   │ Tech, Cons Disc    │
│ Slowdown    │ Utilities, Staples, Health│ Energy, Materials  │
└─────────────────────────────────────────────────────────────┘
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class SectorRotationRecommendation:
    """Sector rotation signal for a single sector."""
    sector: str
    regime_alignment: str  # "strong", "moderate", "weak"
    signal: str  # "overweight", "underweight", "neutral"
    confidence: float
    expected_return: float
    relative_strength: float
    macro_drivers: List[str]


@dataclass
class SectorRotationModel:
    """Complete sector rotation analysis."""
    current_regime: str
    regime_score: float
    recommendations: List[SectorRotationRecommendation]
    momentum_leader: str
    momentum_laggard: str
    rotation_intensity: float
    timestamp: datetime
    # NEW: Calibration-enhanced fields
    conviction_multiplier: float = 1.0
    momentum_decay_adjustment: float = 0.0
    transition_alpha_boost: float = 0.0
    calibration_score: float = 0.0


@dataclass
class CalibrationResult:
    """Result of sector rotation calibration backtest."""
    period: str
    actual_return: float
    predicted_return: float
    prediction_error: float
    hit_rate: float
    regime_accuracy: float
    sharpe_ratio: float
    max_drawdown: float


# Sector definitions
SECTORS = [
    "Technology",
    "Healthcare",
    "Financials",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Materials",
    "Industrials",
    "Utilities",
    "Communication Services",
    "Real Estate",
]

# Regime-sector performance mapping (expected relative returns)
# Higher = better in that regime
SECTOR_REGIME_SCORES = {
    "Goldilocks": {
        "Technology": 1.0,
        "Consumer Discretionary": 0.8,
        "Industrials": 0.7,
        "Financials": 0.5,
        "Communication Services": 0.6,
        "Healthcare": 0.3,
        "Materials": 0.4,
        "Real Estate": 0.2,
        "Consumer Staples": -0.2,
        "Energy": 0.0,
        "Utilities": -0.5,
    },
    "Reflation": {
        "Energy": 1.0,
        "Materials": 0.9,
        "Financials": 0.7,
        "Industrials": 0.6,
        "Consumer Discretionary": 0.3,
        "Technology": 0.2,
        "Communication Services": 0.2,
        "Real Estate": 0.4,
        "Healthcare": 0.1,
        "Consumer Staples": -0.1,
        "Utilities": -0.3,
    },
    "Stagflation": {
        "Energy": 0.8,
        "Consumer Staples": 0.6,
        "Healthcare": 0.5,
        "Utilities": 0.3,
        "Real Estate": 0.1,
        "Materials": 0.2,
        "Financials": -0.3,
        "Industrials": -0.2,
        "Technology": -0.5,
        "Consumer Discretionary": -0.6,
        "Communication Services": -0.4,
    },
    "Slowdown": {
        "Utilities": 0.8,
        "Consumer Staples": 0.7,
        "Healthcare": 0.6,
        "Real Estate": 0.3,
        "Technology": 0.1,
        "Communication Services": 0.0,
        "Consumer Discretionary": -0.3,
        "Industrials": -0.4,
        "Materials": -0.5,
        "Financials": -0.4,
        "Energy": -0.6,
    },
}


class SectorRotationEngine:
    """
    Generate sector rotation recommendations based on macro regime.

    Combines:
    1. Regime-based sector scoring (historical performance)
    2. Relative strength momentum
    3. Macro driver alignment
    4. Regime transition alpha boost (NEW)
    5. Momentum decay guard (NEW)
    """

    def __init__(self):
        self.sector_scores = {}
        self._calibration_cache = {}
        self._last_regime = None
        self._regime_start_date = None
        self._momentum_history = {}

    def _calculate_conviction_multiplier(
        self,
        regime: str,
        regime_confidence: float,
        days_in_regime: int = 0
    ) -> float:
        """
        Calculate conviction multiplier for regime transition alpha boost.

        Higher conviction early in regime transitions when signal is strongest.
        Based on academic research showing regime transition alpha decays over time.

        Args:
            regime: Current regime
            regime_confidence: HMM confidence score (0-1)
            days_in_regime: Days since regime started

        Returns:
            Multiplier to apply to expected returns (0.5 - 2.0)
        """
        # Base conviction from HMM confidence
        base_conviction = max(0.5, min(1.5, regime_confidence))

        # Transition boost: strongest in first 20 days
        if days_in_regime <= 20:
            transition_boost = 1.5 - (days_in_regime / 40)  # 1.5x to 1.0x over 20 days
        else:
            transition_boost = 1.0

        # Conviction multiplier ranges from 0.5 (low confidence, late regime) to 2.0 (high confidence, early regime)
        conviction_multiplier = base_conviction * transition_boost

        return round(min(2.0, max(0.5, conviction_multiplier)), 3)

    def _calculate_momentum_decay_guard(
        self,
        sector: str,
        current_momentum: float,
        momentum_lookback: int = 5
    ) -> float:
        """
        Calculate momentum decay adjustment to prevent stale momentum signals.

        Reduces momentum weight when sector momentum is fading or reversing.

        Args:
            sector: Sector name
            current_momentum: Current 12m momentum score
            momentum_lookback: Days to look back for momentum trend

        Returns:
            Adjustment to apply to momentum score (-0.5 to 0.5)
        """
        # Track momentum history for decay detection
        if sector not in self._momentum_history:
            self._momentum_history[sector] = []

        self._momentum_history[sector].append(current_momentum)

        # Keep only recent history
        if len(self._momentum_history[sector]) > momentum_lookback:
            self._momentum_history[sector].pop(0)

        if len(self._momentum_history[sector]) < 3:
            return 0.0

        # Detect momentum decay (falling momentum)
        recent_momentum = self._momentum_history[sector]
        momentum_trend = recent_momentum[-1] - recent_momentum[0]

        # If momentum is fading, apply negative adjustment
        if momentum_trend < -0.05:
            # Strong decay: -0.3 adjustment
            decay_adjustment = max(-0.3, momentum_trend * 2)
        elif momentum_trend < 0:
            # Mild decay: -0.1 adjustment
            decay_adjustment = -0.1
        elif momentum_trend > 0.05:
            # Rising momentum: positive adjustment
            decay_adjustment = min(0.2, momentum_trend)
        else:
            decay_adjustment = 0.0

        return round(decay_adjustment, 3)

    def run_calibration_backtest(
        self,
        historical_regimes: List[Tuple[str, str, float]],  # [(date, regime, confidence), ...]
        historical_returns: Dict[str, List[Tuple[str, float]]],  # {sector: [(date, return), ...]}
        window: int = 63  # 3 months
    ) -> List[CalibrationResult]:
        """
        Run calibration backtest to validate sector rotation model.

        Args:
            historical_regimes: List of (date, regime, confidence) tuples
            historical_returns: Dict of sector returns {sector: [(date, return), ...]}
            window: Lookback window in days

        Returns:
            List of calibration results per period
        """
        results = []

        for i in range(window, len(historical_regimes)):
            current = historical_regimes[i]
            prev_regime = historical_regimes[i - window:i]

            date_str, regime, confidence = current

            # Calculate metrics
            actual_returns = []
            predicted_returns = []

            for sector, returns in historical_returns.items():
                # Find returns for this period
                period_return = next(
                    (r for d, r in returns if d == date_str), 0.0
                )
                actual_returns.append(period_return)

                # Get base score for this sector in current regime
                base_score = SECTOR_REGIME_SCORES.get(regime, {}).get(sector, 0.0)
                predicted_returns.append(base_score * 0.1)  # Scale to returns

            if not actual_returns:
                continue

            # Calculate metrics
            avg_actual = np.mean(actual_returns)
            avg_predicted = np.mean(predicted_returns)
            prediction_error = avg_predicted - avg_actual

            # Hit rate (% of times we predicted right direction)
            hits = sum(1 for a, p in zip(actual_returns, predicted_returns) if (a * p) > 0)
            hit_rate = hits / len(actual_returns) if actual_returns else 0.0

            # Regime accuracy (did we catch regime changes?)
            regime_changes = sum(
                1 for j in range(1, len(prev_regime))
                if prev_regime[j][1] != prev_regime[j-1][1]
            )
            regime_accuracy = regime_changes / window if window > 0 else 0.0

            # Sharpe ratio
            returns_std = np.std(actual_returns)
            sharpe = (avg_actual / (returns_std + 1e-6)) * np.sqrt(252) if returns_std > 0 else 0.0

            # Max drawdown
            cumulative = np.cumsum(actual_returns)
            max_dd = np.min(cumulative - np.maximum.accumulate(cumulative)) if len(cumulative) > 0 else 0.0

            results.append(CalibrationResult(
                period=date_str,
                actual_return=round(avg_actual, 4),
                predicted_return=round(avg_predicted, 4),
                prediction_error=round(prediction_error, 4),
                hit_rate=round(hit_rate, 3),
                regime_accuracy=round(regime_accuracy, 3),
                sharpe_ratio=round(sharpe, 3),
                max_drawdown=round(max_dd, 4)
            ))

        return results

    def calculate_rotation(
        self,
        regime: str,
        sector_momentum: Optional[Dict[str, float]] = None,
        macro_indicators: Optional[Dict[str, float]] = None,
        regime_confidence: float = 0.7,
        days_in_regime: int = 0,
    ) -> SectorRotationModel:
        """
        Calculate sector rotation model for current regime.

        Args:
            regime: Current macro regime
            sector_momentum: Optional dict of {sector: 12m return}
            macro_indicators: Optional dict of indicator values
            regime_confidence: HMM regime confidence (0-1)
            days_in_regime: Days since regime started for transition boost
        """
        # Get base regime scores
        base_scores = SECTOR_REGIME_SCORES.get(regime, {})

        # Calculate conviction multiplier for regime transition alpha boost
        conviction_multiplier = self._calculate_conviction_multiplier(
            regime, regime_confidence, days_in_regime
        )

        # Track regime transition for alpha boost
        transition_alpha_boost = 0.0
        if self._last_regime != regime:
            # Regime transition detected - apply initial alpha boost
            transition_alpha_boost = conviction_multiplier - 1.0
            self._last_regime = regime
            self._regime_start_date = datetime.now()
        elif self._regime_start_date:
            # Calculate days in regime
            days_in_regime = (datetime.now() - self._regime_start_date).days
            transition_alpha_boost = max(0, conviction_multiplier - 1.0)

        recommendations = []
        aligned_sectors = []
        total_momentum_decay_adjustment = 0.0

        for sector in SECTORS:
            base_score = base_scores.get(sector, 0.0)

            # Apply conviction multiplier (Regime Transition Alpha Boost)
            base_score *= conviction_multiplier

            # Momentum decay guard adjustment
            momentum_decay_adj = 0.0
            if sector_momentum and sector in sector_momentum:
                mom = sector_momentum[sector]

                # Calculate momentum decay guard
                momentum_decay_adj = self._calculate_momentum_decay_guard(sector, mom)
                total_momentum_decay_adjustment += momentum_decay_adj

                # Apply momentum with decay adjustment
                adjusted_mom = mom + momentum_decay_adj

                # Momentum amplification: strong momentum + regime alignment = higher score
                if (base_score > 0 and adjusted_mom > 0) or (base_score < 0 and adjusted_mom < 0):
                    base_score += adjusted_mom * 0.3  # Momentum boost
                else:
                    base_score -= abs(adjusted_mom) * 0.2  # Momentum vs regime = penalty

            # Determine signal
            if base_score > 0.4:
                signal = "overweight"
                alignment = "strong"
            elif base_score > 0.1:
                signal = "overweight"
                alignment = "moderate"
            elif base_score < -0.4:
                signal = "underweight"
                alignment = "strong"
            elif base_score < -0.1:
                signal = "underweight"
                alignment = "moderate"
            else:
                signal = "neutral"
                alignment = "weak"

            # Identify macro drivers
            drivers = self._get_sector_drivers(sector, regime, macro_indicators)

            rec = SectorRotationRecommendation(
                sector=sector,
                regime_alignment=alignment,
                signal=signal,
                confidence=min(abs(base_score) + 0.3, 0.95),
                expected_return=round(base_score * 0.1, 3),  # Scale to returns
                relative_strength=round(sector_momentum.get(sector, 0) if sector_momentum else 0, 3),
                macro_drivers=drivers,
            )
            recommendations.append(rec)

            if signal == "overweight":
                aligned_sectors.append((sector, base_score))

        # Sort by score
        recommendations.sort(key=lambda x: x.expected_return, reverse=True)

        # Identify momentum leader/laggard
        if sector_momentum:
            sorted_mom = sorted(sector_momentum.items(), key=lambda x: x[1], reverse=True)
            leader = sorted_mom[0][0] if sorted_mom else "N/A"
            laggard = sorted_mom[-1][0] if sorted_mom else "N/A"
        else:
            leader = recommendations[0].sector if recommendations else "N/A"
            laggard = recommendations[-1].sector if recommendations else "N/A"

        # Calculate rotation intensity (variance of scores)
        scores = [r.expected_return for r in recommendations]
        rotation_intensity = float(np.std(scores)) if scores else 0.0

        # Calculate calibration score (model confidence based on data quality)
        calibration_score = min(1.0, (
            (conviction_multiplier * 0.3) +
            (1 - abs(total_momentum_decay_adjustment) / len(SECTORS)) * 0.3 +
            (regime_confidence * 0.4)
        ))

        return SectorRotationModel(
            current_regime=regime,
            regime_score=round(np.mean([abs(s) for s in base_scores.values()]), 3),
            recommendations=recommendations,
            momentum_leader=leader,
            momentum_laggard=laggard,
            rotation_intensity=round(rotation_intensity, 3),
            timestamp=datetime.now(),
            conviction_multiplier=conviction_multiplier,
            momentum_decay_adjustment=round(total_momentum_decay_adjustment / len(SECTORS), 3),
            transition_alpha_boost=round(transition_alpha_boost, 3),
            calibration_score=round(calibration_score, 3),
        )

    def _get_sector_drivers(
        self,
        sector: str,
        regime: str,
        macro_indicators: Optional[Dict[str, float]],
    ) -> List[str]:
        """Identify macro drivers for a sector."""
        drivers = []

        sector_drivers = {
            "Technology": ["growth", "rates"],
            "Financials": ["rates", "growth"],
            "Energy": ["inflation", "growth"],
            "Materials": ["inflation", "commodities"],
            "Utilities": ["rates", "defensive"],
            "Consumer Staples": ["defensive", "inflation"],
            "Healthcare": ["defensive", "demographics"],
            "Real Estate": ["rates", "inflation"],
        }

        return sector_drivers.get(sector, ["market"])


def get_top_sector_picks(
    model: SectorRotationModel,
    n: int = 3,
    min_confidence: float = 0.5,
) -> List[Dict]:
    """
    Get top sector recommendations from rotation model.
    """
    overweight = [
        r for r in model.recommendations
        if r.signal == "overweight" and r.confidence >= min_confidence
    ]
    overweight.sort(key=lambda x: x.confidence, reverse=True)

    # FIXED BUG-7: Include weight field (proportional to confidence)
    total_conf = sum(r.confidence for r in overweight[:n]) if overweight[:n] else 1.0
    return [
        {
            "sector": r.sector,
            "signal": r.signal,
            "confidence": r.confidence,
            "expected_return": r.expected_return,
            "relative_strength": r.relative_strength,
            "macro_drivers": r.macro_drivers,
            "weight": round(r.confidence / total_conf, 2) if total_conf > 0 else round(1.0 / n, 2),
        }
        for r in overweight[:n]
    ]


def detect_rotation_opportunity(
    current_model: SectorRotationModel,
    previous_model: Optional[SectorRotationModel],
) -> Optional[Dict]:
    """
    Detect if regime change has created sector rotation opportunity.
    """
    if not previous_model:
        return None

    if current_model.current_regime != previous_model.current_regime:
        # Regime change detected
        prev_top = [r.sector for r in previous_model.recommendations[:3]]
        curr_top = [r.sector for r in current_model.recommendations[:3]]

        new_leaders = [s for s in curr_top if s not in prev_top]

        if new_leaders:
            return {
                "regime_change": True,
                "from_regime": previous_model.current_regime,
                "to_regime": current_model.current_regime,
                "new_leaders": new_leaders,
                "rotation_intensity": current_model.rotation_intensity,
                "action": f"Rotate toward {', '.join(new_leaders)}",
            }

    return None
