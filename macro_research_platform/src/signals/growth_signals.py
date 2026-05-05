"""
Growth Signals

Signals related to economic growth, GDP, and business conditions.

Research backing:
- Stock & Watson - Diffusion Indexes
- Aruoba, Diebold, Scotti - Real-Time Business Conditions
- Giannone, Reichlin, Small - Nowcasting GDP
"""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

from .signal_base import Signal, SignalDirection, SignalOutput, SignalConfidence

logger = logging.getLogger(__name__)


class GrowthDiffusionSignal(Signal):
    """
    Diffusion index of growth indicators.

    Research: Stock & Watson - Macroeconomic Forecasting Using Diffusion Indexes

    Measures the breadth of growth across multiple indicators.
    Positive = majority of indicators showing growth
    Negative = majority showing contraction
    """

    def __init__(self, indicators: List[str] = None):
        super().__init__(
            name="growth_diffusion",
            description="Breadth of growth across multiple indicators",
            asset_universe=["equities", "credit", "commodities"],
            frequency="monthly",
        )
        self.indicators = indicators or [
            "industrial_production",
            "retail_sales",
            "employment",
            "hours_worked",
            "initial_claims",
        ]
        self.parameters = {
            "zscore_threshold": 0.5,
            "lookback_months": 24,
        }

    def calculate(self, data: pd.DataFrame) -> SignalOutput:
        """
        Calculate growth diffusion signal.

        Args:
            data: DataFrame with indicator columns

        Returns:
            SignalOutput with direction and strength
        """
        if data.empty:
            return self._neutral_output()

        # Calculate z-scores for each indicator
        zscores = {}
        for col in self.indicators:
            if col in data.columns:
                z = self._calculate_zscore(data[col])
                zscores[col] = z

        if not zscores:
            return self._neutral_output()

        # Calculate diffusion (% of indicators above median)
        positive = sum(1 for z in zscores.values() if z > 0)
        diffusion = positive / len(zscores)

        # Determine direction
        if diffusion > 0.6:
            direction = SignalDirection.LONG
            strength = min(1.0, (diffusion - 0.5) * 2)
        elif diffusion < 0.4:
            direction = SignalDirection.SHORT
            strength = min(1.0, (0.5 - diffusion) * 2)
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5

        # Confidence based on data quality
        confidence = self._calculate_confidence(zscores)

        return SignalOutput(
            timestamp=data.index[-1] if hasattr(data.index, '[-1]') else pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction),
            rationale=f"Growth diffusion at {diffusion:.0%} ({positive}/{len(zscores)} indicators positive)",
            metadata={
                "diffusion": diffusion,
                "zscores": zscores,
                "indicators_used": list(zscores.keys()),
            },
        )

    def _calculate_zscore(self, series: pd.Series) -> float:
        """Calculate z-score for latest value."""
        if len(series) < 12:
            return 0.0

        lookback = self.parameters["lookback_months"]
        recent = series.iloc[-lookback:]

        if recent.std() == 0:
            return 0.0

        return (series.iloc[-1] - recent.mean()) / recent.std()

    def _calculate_confidence(self, zscores: Dict) -> SignalConfidence:
        """Calculate confidence based on signal agreement."""
        if len(zscores) < 3:
            return SignalConfidence.LOW

        std_z = np.std(list(zscores.values()))

        if std_z < 0.3:
            return SignalConfidence.HIGH
        elif std_z < 0.6:
            return SignalConfidence.MEDIUM
        else:
            return SignalConfidence.LOW

    def _estimate_return(self, direction: SignalDirection) -> float:
        """Estimate expected return based on direction."""
        returns = {
            SignalDirection.LONG: 0.08,
            SignalDirection.SHORT: -0.08,
            SignalDirection.NEUTRAL: 0.02,
        }
        return returns.get(direction, 0.0)

    def _neutral_output(self) -> SignalOutput:
        """Return neutral signal when data insufficient."""
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient data for growth diffusion signal",
        )


class GDPNowcastSignal(Signal):
    """
    GDP nowcasting signal using bridge equations.

    Research: Giannone, Reichlin, and Small - Nowcasting GDP and Inflation

    Uses monthly indicators to estimate current quarter GDP
    before official release.
    """

    def __init__(self):
        super().__init__(
            name="gdp_nowcast",
            description="Nowcast of current quarter GDP growth",
            asset_universe=["equities", "rates", "fx"],
            frequency="monthly",
        )
        self.parameters = {
            "industrial_weight": 0.3,
            "employment_weight": 0.25,
            "consumption_weight": 0.25,
            "housing_weight": 0.2,
        }

    def calculate(self, data: Dict[str, pd.Series]) -> SignalOutput:
        """
        Calculate GDP nowcast.

        Args:
            data: Dict of indicator series

        Returns:
            SignalOutput with nowcast and signal
        """
        # Simplified bridge equation
        nowcast = self._bridge_equation(data)

        if nowcast is None:
            return self._neutral_output()

        # Determine signal based on nowcast vs consensus
        consensus = 2.0  # Would get from actual data

        if nowcast > consensus + 0.5:
            direction = SignalDirection.LONG
            strength = min(1.0, (nowcast - consensus) / 2)
        elif nowcast < consensus - 0.5:
            direction = SignalDirection.SHORT
            strength = min(1.0, (consensus - nowcast) / 2)
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5

        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=SignalConfidence.MEDIUM,
            expected_return=self._estimate_return(direction),
            rationale=f"GDP nowcast at {nowcast:.1f}% (consensus: {consensus:.1f}%)",
            metadata={
                "nowcast": nowcast,
                "consensus": consensus,
                "surprise": nowcast - consensus,
            },
        )

    def _bridge_equation(self, data: Dict[str, pd.Series]) -> Optional[float]:
        """Calculate nowcast using bridge equation."""
        if not data:
            return None

        weights = self.parameters
        weighted_sum = 0.0
        total_weight = 0.0

        for indicator, weight in [
            ("industrial_production", weights["industrial_weight"]),
            ("employment", weights["employment_weight"]),
            ("retail_sales", weights["consumption_weight"]),
            ("housing_starts", weights["housing_weight"]),
        ]:
            if indicator in data and len(data[indicator]) > 0:
                # Use year-over-year change
                series = data[indicator]
                if len(series) >= 13:
                    yoy = (series.iloc[-1] / series.iloc[-13] - 1) * 100
                    weighted_sum += yoy * weight
                    total_weight += weight

        if total_weight == 0:
            return None

        return weighted_sum / total_weight

    def _estimate_return(self, direction: SignalDirection) -> float:
        """Estimate expected return based on direction."""
        returns = {
            SignalDirection.LONG: 0.05,
            SignalDirection.SHORT: -0.05,
            SignalDirection.NEUTRAL: 0.0,
        }
        return returns.get(direction, 0.0)

    def _neutral_output(self) -> SignalOutput:
        """Return neutral signal when data insufficient."""
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient data for GDP nowcast",
        )


class BusinessConditionsSignal(Signal):
    """
    Business conditions index signal.

    Research: Aruoba, Diebold, Scotti - Real-Time Measurement of Business Conditions

    Composite index of business conditions using mixed-frequency data.
    """

    def __init__(self):
        super().__init__(
            name="business_conditions",
            description="Real-time business conditions index",
            asset_universe=["equities", "credit"],
            frequency="weekly",
        )
        self.parameters = {
            "factor_weights": {
                "output": 0.4,
                "employment": 0.35,
                "consumption": 0.25,
            },
        }

    def calculate(self, data: pd.DataFrame) -> SignalOutput:
        """
        Calculate business conditions signal.

        Args:
            data: DataFrame with output, employment, consumption columns

        Returns:
            SignalOutput with business conditions assessment
        """
        if data.empty:
            return self._neutral_output()

        # Calculate factor scores
        factors = self.parameters["factor_weights"]
        factor_scores = {}

        for factor, weight in factors.items():
            if factor in data.columns:
                series = data[factor]
                if len(series) >= 12:
                    # Standardized score
                    zscore = (series.iloc[-1] - series.iloc[-12:].mean()) / series.iloc[-12:].std()
                    factor_scores[factor] = zscore

        if not factor_scores:
            return self._neutral_output()

        # Weighted average
        total_score = sum(factor_scores.get(f, 0) * w for f, w in factors.items())
        total_weight = sum(w for f, w in factors.items() if f in factor_scores)

        if total_weight == 0:
            return self._neutral_output()

        composite = total_score / total_weight

        # Determine signal
        if composite > 0.5:
            direction = SignalDirection.LONG
            strength = min(1.0, composite / 2)
        elif composite < -0.5:
            direction = SignalDirection.SHORT
            strength = min(1.0, abs(composite) / 2)
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5 + abs(composite) / 2

        return SignalOutput(
            timestamp=data.index[-1] if hasattr(data.index, '[-1]') else pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=SignalConfidence.HIGH if len(factor_scores) >= 3 else SignalConfidence.MEDIUM,
            expected_return=self._estimate_return(direction),
            rationale=f"Business conditions index at {composite:+.2f}",
            metadata={
                "composite_score": composite,
                "factor_scores": factor_scores,
            },
        )

    def _estimate_return(self, direction: SignalDirection) -> float:
        """Estimate expected return based on direction."""
        returns = {
            SignalDirection.LONG: 0.06,
            SignalDirection.SHORT: -0.06,
            SignalDirection.NEUTRAL: 0.0,
        }
        return returns.get(direction, 0.0)

    def _neutral_output(self) -> SignalOutput:
        """Return neutral signal when data insufficient."""
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient data for business conditions index",
        )
