"""
Credit Signals

Signals related to credit spreads, credit stress, and credit impulse.

Research backing:
- Gilchrist and Zakrajšek - Credit Spreads and Business Cycle Fluctuations
- López-Salido, Stein and Zakrajšek - Credit Market Sentiment and the Business Cycle
"""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .signal_base import Signal, SignalDirection, SignalOutput, SignalConfidence

logger = logging.getLogger(__name__)


class CreditStressSignal(Signal):
    """
    Credit stress signal based on excess bond premium.

    Research: Gilchrist and Zakrajšek - Credit Spreads and Business Cycle Fluctuations

    Excess bond premium predicts future economic weakness.
    High stress = defensive positioning
    """

    def __init__(self):
        super().__init__(
            name="credit_stress",
            description="Credit stress based on excess bond premium",
            asset_universe=["credit", "equities", "cyclicals"],
            frequency="monthly",
        )
        self.parameters = {
            "investment_grade_spread_threshold": 150,  # bps
            "high_yield_spread_threshold": 400,  # bps
            "stress_threshold": 0.5,  # z-score
        }

    def calculate(self, data: pd.DataFrame) -> SignalOutput:
        """
        Calculate credit stress signal.

        Args:
            data: DataFrame with credit spread columns

        Returns:
            SignalOutput with stress assessment
        """
        if data.empty:
            return self._neutral_output()

        # Calculate stress metrics
        stress_level = 0.0
        stress_indicators = {}

        # Check investment grade spreads
        if 'ig_spread' in data.columns:
            ig_current = data['ig_spread'].iloc[-1]
            ig_threshold = self.parameters["investment_grade_spread_threshold"]
            ig_z = self._calculate_zscore(data['ig_spread'])
            stress_indicators['ig_spread'] = ig_z
            if ig_current > ig_threshold or ig_z > 1.0:
                stress_level += 0.3

        # Check high yield spreads
        if 'hy_spread' in data.columns:
            hy_current = data['hy_spread'].iloc[-1]
            hy_threshold = self.parameters["high_yield_spread_threshold"]
            hy_z = self._calculate_zscore(data['hy_spread'])
            stress_indicators['hy_spread'] = hy_z
            if hy_current > hy_threshold or hy_z > 1.0:
                stress_level += 0.4

        # Check excess bond premium if available
        if 'ebp' in data.columns:
            ebp_z = self._calculate_zscore(data['ebp'])
            stress_indicators['ebp'] = ebp_z
            if ebp_z > self.parameters["stress_threshold"]:
                stress_level += 0.3

        # Determine signal
        if stress_level > 0.6:
            direction = SignalDirection.SHORT  # Risk-off
            strength = min(1.0, stress_level)
            confidence = SignalConfidence.HIGH if len(stress_indicators) >= 2 else SignalConfidence.MEDIUM
            rationale = f"High credit stress (level: {stress_level:.2f}) - defensive positioning warranted"
        elif stress_level > 0.3:
            direction = SignalDirection.NEUTRAL  # Cautious
            strength = stress_level
            confidence = SignalConfidence.MEDIUM
            rationale = f"Elevated credit stress (level: {stress_level:.2f}) - selective positioning"
        else:
            direction = SignalDirection.LONG  # Risk-on
            strength = max(0.3, 1.0 - stress_level)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Credit stress contained (level: {stress_level:.2f}) - normal positioning"

        return SignalOutput(
            timestamp=data.index[-1] if len(data.index) > 0 else pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction),
            rationale=rationale,
            metadata={
                "stress_level": stress_level,
                "stress_indicators": stress_indicators,
            },
        )

    def _calculate_zscore(self, series: pd.Series) -> float:
        """Calculate z-score."""
        if len(series) < 24:
            return 0.0
        recent = series.iloc[-24:]
        if recent.std() == 0:
            return 0.0
        return (series.iloc[-1] - recent.mean()) / recent.std()

    def _estimate_return(self, direction: SignalDirection) -> float:
        """Estimate expected return."""
        returns = {
            SignalDirection.LONG: 0.05,   # Normal risk-on
            SignalDirection.SHORT: -0.10,  # Defensive during stress
            SignalDirection.NEUTRAL: 0.0,
        }
        return returns.get(direction, 0.0)

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient data for credit stress signal",
        )


class CreditImpulseSignal(Signal):
    """
    Credit impulse signal - change in credit growth.

    Research: López-Salido, Stein, Zakrajšek - Credit Market Sentiment

    Credit growth acceleration/deceleration predicts economic activity.
    """

    def __init__(self):
        super().__init__(
            name="credit_impulse",
            description="Credit impulse signal (change in credit growth)",
            asset_universe=["equities", "credit", "cyclicals"],
            frequency="monthly",
        )
        self.parameters = {
            "lookback_quarters": 4,
            "impulse_threshold": 0.5,
        }

    def calculate(self, credit_series: pd.Series) -> SignalOutput:
        """
        Calculate credit impulse signal.

        Args:
            credit_series: Series of credit growth rates

        Returns:
            SignalOutput with impulse assessment
        """
        if len(credit_series) < self.parameters["lookback_quarters"] + 1:
            return self._neutral_output()

        current = credit_series.iloc[-1]
        previous = credit_series.iloc[-self.parameters["lookback_quarters"]-1]

        impulse = current - previous

        # Determine signal
        if impulse > self.parameters["impulse_threshold"]:
            direction = SignalDirection.LONG
            strength = min(1.0, impulse / 2.0)
            rationale = f"Positive credit impulse: {previous:.1f}% → {current:.1f}% (+{impulse:.1f}%)"
        elif impulse < -self.parameters["impulse_threshold"]:
            direction = SignalDirection.SHORT
            strength = min(1.0, abs(impulse) / 2.0)
            rationale = f"Negative credit impulse: {previous:.1f}% → {current:.1f}% ({impulse:.1f}%)"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            rationale = f"Neutral credit impulse: {current:.1f}% (change: {impulse:.1f}%)"

        return SignalOutput(
            timestamp=credit_series.index[-1] if len(credit_series.index) > 0 else pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=SignalConfidence.HIGH,
            expected_return=self._estimate_return(direction),
            rationale=rationale,
            metadata={
                "current": current,
                "previous": previous,
                "impulse": impulse,
            },
        )

    def _estimate_return(self, direction: SignalDirection) -> float:
        returns = {
            SignalDirection.LONG: 0.06,
            SignalDirection.SHORT: -0.08,
            SignalDirection.NEUTRAL: 0.0,
        }
        return returns.get(direction, 0.0)

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient data for credit impulse signal",
        )


class CreditSpreadMomentumSignal(Signal):
    """
    Signal based on momentum in credit spreads.

    Widening spreads momentum = risk-off
    Narrowing spreads momentum = risk-on
    """

    def __init__(self, lookback_months: int = 3):
        super().__init__(
            name="credit_spread_momentum",
            description="Credit spread momentum signal",
            asset_universe=["credit", "equities"],
            frequency="monthly",
        )
        self.parameters = {
            "lookback_months": lookback_months,
        }

    def calculate(self, spread_series: pd.Series) -> SignalOutput:
        """Calculate credit spread momentum signal."""
        if len(spread_series) < self.parameters["lookback_months"] + 1:
            return self._neutral_output()

        current = spread_series.iloc[-1]
        previous = spread_series.iloc[-self.parameters["lookback_months"]-1]

        change = current - previous

        # Normalize change by level
        if previous > 0:
            pct_change = change / previous
        else:
            pct_change = 0

        # Determine signal
        if pct_change > 0.15:  # Spreads widening 15%+
            direction = SignalDirection.SHORT
            strength = min(1.0, pct_change / 0.3)
            rationale = f"Credit spreads widening: {previous:.0f}bps → {current:.0f}bps (+{pct_change:.1%})"
        elif pct_change < -0.15:  # Spreads narrowing 15%+
            direction = SignalDirection.LONG
            strength = min(1.0, abs(pct_change) / 0.3)
            rationale = f"Credit spreads narrowing: {previous:.0f}bps → {current:.0f}bps ({pct_change:.1%})"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            rationale = f"Credit spreads stable: {current:.0f}bps"

        return SignalOutput(
            timestamp=spread_series.index[-1] if len(spread_series.index) > 0 else pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=SignalConfidence.MEDIUM,
            expected_return=self._estimate_return(direction),
            rationale=rationale,
            metadata={
                "current": current,
                "previous": previous,
                "change": change,
                "pct_change": pct_change,
            },
        )

    def _estimate_return(self, direction: SignalDirection) -> float:
        returns = {
            SignalDirection.LONG: 0.04,
            SignalDirection.SHORT: -0.06,
            SignalDirection.NEUTRAL: 0.0,
        }
        return returns.get(direction, 0.0)

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient data for credit spread momentum signal",
        )
