"""
Credit Stress Model

Measures credit market stress using:
- Credit spread levels
- Spread changes (momentum)
- High yield vs investment grade divergence
- Default rate indicators
- Credit stress momentum

Based on:
- Gilchrist & Zakrajšek (2012) - Credit Spreads and Business Cycle Fluctuations
- López-Salido, Stein & Zakrajšek (2017) - Credit Market Sentiment
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class CreditStressResult:
    """Credit stress measurement result."""
    stress_score: float  # 0-1, higher = more stress
    stress_level: str  # normal, elevated, high, severe
    confidence: float
    components: Dict[str, float]
    drivers: List[str]
    transmission: str


class CreditStressModel:
    """
    Credit Stress Model

    Monitors credit market conditions to detect rising stress
    that may precede economic weakness.
    """

    def __init__(self):
        # Component weights
        self.component_weights = {
            "spread_level": 0.30,
            "spread_change": 0.25,
            "spread_zscore": 0.20,
            "hy_ig_divergence": 0.15,
            "momentum": 0.10,
        }

        # Stress thresholds (spread levels in bps)
        self.stress_thresholds = {
            "normal": 400,
            "elevated": 600,
            "high": 800,
            "severe": 1200,
        }

    def _calculate_spread_level_score(self, spread: float) -> float:
        """Score based on absolute spread level."""
        # Normalize spread to 0-1 score
        # 300 bps = 0, 800 bps = 0.5, 1500 bps = 1.0
        score = (spread - 300) / 1200
        return np.clip(score, 0.0, 1.0)

    def _calculate_spread_change_score(
        self,
        current: float,
        past: float,
        months: int = 3,
    ) -> float:
        """Score based on spread change over time."""
        if past <= 0:
            return 0.0

        change_pct = (current - past) / past

        # Normalize: 50% increase over 3 months = 0.5 stress
        annualized_change = change_pct * (12 / months)
        score = annualized_change / 1.0

        return np.clip(score, 0.0, 1.0)

    def _calculate_spread_zscore(
        self,
        spread: float,
        historical_spreads: pd.Series,
    ) -> float:
        """Z-score of spread relative to historical distribution."""
        if len(historical_spreads) < 24:
            return 0.0

        mean = historical_spreads.mean()
        std = historical_spreads.std()

        if std == 0:
            return 0.0

        zscore = (spread - mean) / std

        # Convert to stress score: z-score > 2 = high stress
        score = (zscore - 0.5) / 2.0
        return np.clip(score, 0.0, 1.0)

    def _calculate_hy_ig_divergence(
        self,
        hy_spread: float,
        ig_spread: float,
    ) -> float:
        """
        Calculate HY vs IG divergence.

        Rising HY spreads relative to IG indicates risk-off.
        """
        if ig_spread <= 0:
            return 0.0

        # Typical HY/IG spread ratio ~2.5-3.0
        ratio = hy_spread / ig_spread
        neutral_ratio = 3.0

        # Divergence if ratio rises above neutral
        divergence = max(0, ratio - neutral_ratio)

        # Normalize: 1.0 point divergence = 0.5 stress
        score = divergence / 2.0

        return np.clip(score, 0.0, 1.0)

    def _calculate_momentum_score(
        self,
        spreads: pd.Series,
    ) -> float:
        """Calculate momentum score from recent spread trend."""
        if len(spreads) < 6:
            return 0.0

        # 3-month momentum
        recent = spreads.iloc[-1]
        past_3m = spreads.iloc[-4] if len(spreads) >= 4 else spreads.iloc[0]

        if past_3m <= 0:
            return 0.0

        momentum = (recent - past_3m) / past_3m

        # Score: rising spreads = stress
        score = momentum * 2  # 50% increase = 1.0 stress

        return np.clip(score, 0.0, 1.0)

    def compute_stress(
        self,
        current_spread: float,
        spread_history: Optional[pd.Series] = None,
        hy_spread: Optional[float] = None,
        ig_spread: Optional[float] = None,
    ) -> CreditStressResult:
        """
        Compute credit stress score.

        Args:
            current_spread: Current credit spread level (bps)
            spread_history: Historical spreads for z-score calculation
            hy_spread: High yield spread (optional)
            ig_spread: Investment grade spread (optional)

        Returns:
            CreditStressResult with stress assessment
        """
        components = {}
        drivers = []

        # 1. Spread level
        components["spread_level"] = self._calculate_spread_level_score(current_spread)
        drivers.append(f"Spread level: {current_spread:.0f} bps")

        # 2. Spread change (if history available)
        if spread_history is not None and len(spread_history) >= 4:
            past_3m = spread_history.iloc[-4]
            components["spread_change"] = self._calculate_spread_change_score(
                current_spread, past_3m, months=3
            )
            change = current_spread - past_3m
            drivers.append(f"3-month change: {change:+.0f} bps")
        else:
            components["spread_change"] = 0.0
            drivers.append("Spread change: insufficient history")

        # 3. Z-score (if history available)
        if spread_history is not None:
            components["spread_zscore"] = self._calculate_spread_zscore(
                current_spread, spread_history
            )
            z = (current_spread - spread_history.mean()) / spread_history.std() if spread_history.std() > 0 else 0
            drivers.append(f"Z-score: {z:+.2f}")
        else:
            components["spread_zscore"] = 0.0
            drivers.append("Z-score: insufficient history")

        # 4. HY/IG divergence
        if hy_spread is not None and ig_spread is not None:
            components["hy_ig_divergence"] = self._calculate_hy_ig_divergence(
                hy_spread, ig_spread
            )
            ratio = hy_spread / ig_spread if ig_spread > 0 else 0
            drivers.append(f"HY/IG ratio: {ratio:.2f}")
        else:
            components["hy_ig_divergence"] = 0.0
            drivers.append("HY/IG divergence: data unavailable")

        # 5. Momentum
        if spread_history is not None:
            components["momentum"] = self._calculate_momentum_score(spread_history)
            drivers.append(f"Momentum: {'rising' if components['momentum'] > 0.3 else 'stable'}")
        else:
            components["momentum"] = 0.0
            drivers.append("Momentum: insufficient history")

        # Calculate weighted stress score
        available_components = {k: v for k, v in components.items() if v > 0}

        if available_components:
            available_weight = sum(
                self.component_weights.get(k, 0) for k in available_components.keys()
            )
            if available_weight > 0:
                normalized_weights = {
                    k: self.component_weights[k] / available_weight
                    for k in available_components.keys()
                }
                stress_score = sum(
                    normalized_weights[k] * components[k]
                    for k in available_components.keys()
                )
            else:
                stress_score = 0.0

            confidence = min(0.9, len(available_components) / len(self.component_weights))
        else:
            stress_score = 0.0
            confidence = 0.0
            drivers.append("ERROR: No credit spread data available")

        # Classify stress level
        stress_level = self._classify_stress_level(stress_score)

        # Transmission description
        transmission = self._get_transmission_description(stress_level, components)

        return CreditStressResult(
            stress_score=stress_score,
            stress_level=stress_level,
            confidence=confidence,
            components=components,
            drivers=drivers,
            transmission=transmission,
        )

    def _classify_stress_level(self, score: float) -> str:
        """Classify stress score into level."""
        if score < 0.25:
            return "normal"
        elif score < 0.5:
            return "elevated"
        elif score < 0.75:
            return "high"
        else:
            return "severe"

    def _get_transmission_description(
        self,
        stress_level: str,
        components: Dict[str, float],
    ) -> str:
        """Get transmission mechanism description."""
        if stress_level == "normal":
            return (
                "Credit conditions are supportive. Financing is available "
                "for creditworthy borrowers at reasonable terms."
            )
        elif stress_level == "elevated":
            return (
                "Credit conditions are tightening. Spreads have widened, "
                "raising financing costs and reducing credit availability. "
                "Worth monitoring for further deterioration."
            )
        elif stress_level == "high":
            return (
                "Credit stress is elevated. Significant spread widening indicates "
                "risk aversion and reduced credit availability. This typically "
                "transmits to real economy through reduced capex and hiring. "
                "Research: Gilchrist & Zakrajšek (2012) show credit spreads "
                "predict business cycle fluctuations."
            )
        else:  # severe
            return (
                "Severe credit stress detected. Spreads at distressed levels. "
                "Credit availability is severely constrained. High probability "
                "of negative transmission to real activity through: "
                "(1) Reduced business investment, "
                "(2) Household deleveraging, "
                "(3) Financial sector stress."
            )


def compute_credit_stress_from_data(
    df: pd.DataFrame,
    model: Optional[CreditStressModel] = None,
) -> CreditStressResult:
    """
    Compute credit stress from DataFrame.

    Expected columns:
    - us_credit_spread (high yield)
    - us_ig_credit_spread (investment grade, optional)
    """
    if model is None:
        model = CreditStressModel()

    # Find credit spread columns
    hy_col = next(
        (c for c in df.columns if "credit" in c.lower() and "spread" in c.lower()),
        None,
    )
    ig_col = next(
        (c for c in df.columns if "ig" in c.lower() or "investment_grade" in c.lower()),
        None,
    )

    if hy_col is None:
        logger.warning("No credit spread column found in data")
        return CreditStressResult(
            stress_score=0.0,
            stress_level="unknown",
            confidence=0.0,
            components={},
            drivers=["No credit spread data available"],
            transmission="Unable to assess credit conditions without spread data.",
        )

    current_spread = df[hy_col].iloc[-1]
    spread_history = df[hy_col]

    hy_spread = current_spread
    ig_spread = df[ig_col].iloc[-1] if ig_col else None

    return model.compute_stress(
        current_spread=current_spread,
        spread_history=spread_history,
        hy_spread=hy_spread,
        ig_spread=ig_spread,
    )
