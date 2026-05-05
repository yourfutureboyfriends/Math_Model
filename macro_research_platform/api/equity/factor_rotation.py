"""
Factor Rotation Engine — Macro-Aware Factor Timing

Extends multi-factor alpha with dynamic factor timing.
Different factors work in different macro environments.
This module provides regime-conditional factor weights.

Factor Performance by Environment:
┌────────────────────────────────────────────────────────────────┐
│ Environment         │ Best Factors              │ Worst Factors │
├────────────────────────────────────────────────────────────────┤
│ Growth + Inflation ↑│ Value, Momentum, Low Vol  │ Growth      │
│ Growth + Inflation ↓│ Growth, Quality, Momentum │ Value       │
│ Growth ↓ + Infl ↑  │ Quality, Low Vol          │ Momentum    │
│ Growth ↓ + Infl ↓  │ Low Vol, Quality, Value   │ Momentum    │
└────────────────────────────────────────────────────────────────┘

Also includes: factor momentum, crowding detection, dispersion analysis.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class FactorRecommendation:
    """Single factor timing recommendation."""
    factor: str
    signal: str  # "overweight", "underweight", "neutral"
    weight: float  # Portfolio weight (0-1 scale)
    confidence: float
    macro_alignment: str  # "high", "medium", "low"
    momentum: float
    crowding: str  # "crowded", "neutral", "underowned"


@dataclass
class FactorRotationModel:
    """Complete factor rotation model."""
    current_regime: str
    factor_weights: Dict[str, float]
    recommendations: List[FactorRecommendation]
    dispersion: float  # Cross-sectional factor return dispersion
    factor_momentum: Dict[str, float]
    timestamp: datetime


# Factor regime performance (Sharpe ratio by regime)
FACTOR_REGIME_SHARPE = {
    "Goldilocks": {
        "value": 0.3, "momentum": 0.8, "quality": 0.5,
        "growth": 0.9, "low_vol": 0.1,
    },
    "Reflation": {
        "value": 0.7, "momentum": 0.5, "quality": 0.4,
        "growth": 0.3, "low_vol": -0.2,
    },
    "Stagflation": {
        "value": 0.2, "momentum": -0.3, "quality": 0.6,
        "growth": -0.4, "low_vol": 0.7,
    },
    "Slowdown": {
        "value": 0.4, "momentum": -0.1, "quality": 0.5,
        "growth": 0.1, "low_vol": 0.6,
    },
}


class FactorRotationEngine:
    """
    Generate factor rotation recommendations based on macro regime.

    Combines:
    1. Regime-based factor scoring (historical Sharpe)
    2. Factor momentum (trend following)
    3. Crowding detection (contrarian)
    """

    def __init__(self):
        self.factor_history = {}

    def calculate_rotation(
        self,
        regime: str,
        factor_returns: Optional[Dict[str, float]] = None,
        factor_aum: Optional[Dict[str, float]] = None,
    ) -> FactorRotationModel:
        """
        Calculate factor rotation model.

        Args:
            regime: Current macro regime
            factor_returns: 12-month factor returns
            factor_aum: Factor AUM (for crowding detection)
        """
        # Base Sharpe from regime
        base_sharpes = FACTOR_REGIME_SHARPE.get(regime, {})

        recommendations = []
        weights = {}

        for factor in ["value", "momentum", "quality", "growth", "low_vol"]:
            base_sharpe = base_sharpes.get(factor, 0.0)

            # Adjust for factor momentum
            if factor_returns and factor in factor_returns:
                mom = factor_returns[factor]
                if (base_sharpe > 0 and mom > 0) or (base_sharpe < 0 and mom < 0):
                    adjusted_sharpe = base_sharpe + mom * 0.2
                else:
                    adjusted_sharpe = base_sharpe - abs(mom) * 0.1
            else:
                adjusted_sharpe = base_sharpe
                mom = 0.0

            # Detect crowding
            crowding = "neutral"
            if factor_aum and factor in factor_aum:
                # Simplified crowding: high AUM = crowded
                aum_pct = factor_aum[factor]
                if aum_pct > 0.3:
                    crowding = "crowded"
                    adjusted_sharpe -= 0.1  # Crowding penalty
                elif aum_pct < 0.15:
                    crowding = "underowned"
                    adjusted_sharpe += 0.05  # Contrarian bonus

            # Determine signal
            if adjusted_sharpe > 0.5:
                signal = "overweight"
                macro_align = "high"
            elif adjusted_sharpe > 0.2:
                signal = "overweight"
                macro_align = "medium"
            elif adjusted_sharpe < -0.2:
                signal = "underweight"
                macro_align = "low"
            else:
                signal = "neutral"
                macro_align = "medium"

            # Calculate weight (0-1 normalized)
            weight = max(0, min(1, (adjusted_sharpe + 0.5) / 1.5))
            weights[factor] = weight

            rec = FactorRecommendation(
                factor=factor,
                signal=signal,
                weight=round(weight, 3),
                confidence=min(abs(adjusted_sharpe) + 0.3, 0.95),
                macro_alignment=macro_align,
                momentum=round(mom, 3),
                crowding=crowding,
            )
            recommendations.append(rec)

        # Normalize weights to sum to 1
        total_weight = sum(weights.values())
        if total_weight > 0:
            weights = {k: round(v / total_weight, 3) for k, v in weights.items()}

        # Calculate dispersion
        if factor_returns:
            values = list(factor_returns.values())
            dispersion = float(np.std(values)) if values else 0.0
        else:
            dispersion = 0.0

        return FactorRotationModel(
            current_regime=regime,
            factor_weights=weights,
            recommendations=recommendations,
            dispersion=round(dispersion, 3),
            factor_momentum=factor_returns or {},
            timestamp=datetime.now(),
        )

    def get_factor_momentum(
        self,
        factor_returns_history: pd.DataFrame,
        lookback_months: int = 12,
    ) -> Dict[str, float]:
        """
        Calculate factor momentum from historical returns.

        Args:
            factor_returns_history: DataFrame with factor return columns
            lookback_months: Lookback period for momentum calculation
        """
        if factor_returns_history.empty:
            return {}

        momentum = {}
        for col in factor_returns_history.columns:
            if len(factor_returns_history) >= lookback_months:
                recent = factor_returns_history[col].iloc[-lookback_months:]
                momentum[col] = round(recent.mean(), 4)
            else:
                momentum[col] = 0.0

        return momentum


def get_optimal_factor_weights(model: FactorRotationModel) -> Dict[str, float]:
    """
    Get normalized optimal factor weights for portfolio construction.
    """
    return model.factor_weights


def detect_factor_crowding(
    model: FactorRotationModel,
    threshold: float = 0.7,
) -> List[Dict]:
    """
    Detect crowded factors that may underperform.
    """
    crowded = [
        {
            "factor": r.factor,
            "crowding_level": r.crowding,
            "recommendation": "reduce" if r.crowding == "crowded" else "maintain",
        }
        for r in model.recommendations
        if r.crowding == "crowded"
    ]

    return crowded


def explain_factor_rotation(
    model: FactorRotationModel,
) -> Dict:
    """
    Generate human-readable explanation of factor rotation.
    """
    top_factors = sorted(
        model.recommendations,
        key=lambda x: x.weight,
        reverse=True,
    )[:2]

    bottom_factors = sorted(
        model.recommendations,
        key=lambda x: x.weight,
    )[:2]

    return {
        "regime": model.current_regime,
        "thesis": f"In {model.current_regime} environments, " + (
            f"{top_factors[0].factor} and {top_factors[1].factor if len(top_factors) > 1 else 'quality'} factors historically outperform."
            if len(top_factors) >= 1 else "maintain balanced factor exposure."
        ),
        "overweights": [
            {"factor": r.factor, "weight": r.weight, "confidence": r.confidence}
            for r in top_factors if r.signal == "overweight"
        ],
        "underweights": [
            {"factor": r.factor, "weight": r.weight}
            for r in bottom_factors if r.signal == "underweight"
        ],
        "dispersion": model.dispersion,
        "timestamp": model.timestamp.isoformat(),
    }
