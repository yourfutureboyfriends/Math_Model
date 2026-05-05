"""
Uncertainty Signals

Signals related to economic policy uncertainty and global uncertainty.

Research backing:
- Baker, Bloom, Davis - Measuring Economic Policy Uncertainty
- Ahir, Bloom, Furceri - World Uncertainty Index
"""

import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd

from .signal_base import Signal, SignalDirection, SignalOutput, SignalConfidence

logger = logging.getLogger(__name__)


class PolicyUncertaintySignal(Signal):
    """
    Economic policy uncertainty signal.

    Research: Baker, Bloom, Davis - Measuring Economic Policy Uncertainty

    High policy uncertainty predicts lower investment and employment.
    Used as risk overlay - high uncertainty = defensive positioning.
    """

    def __init__(self):
        super().__init__(
            name="policy_uncertainty",
            description="Economic policy uncertainty signal",
            asset_universe=["equities", "credit", "cyclicals"],
            frequency="monthly",
        )
        self.parameters = {
            "epu_threshold_high": 150,
            "epu_threshold_low": 100,
            "lookback_months": 24,
        }

    def calculate(self, epu_series: pd.Series) -> SignalOutput:
        """
        Calculate policy uncertainty signal.

        Args:
            epu_series: Economic Policy Uncertainty index

        Returns:
            SignalOutput with uncertainty assessment
        """
        if len(epu_series) < self.parameters["lookback_months"]:
            return self._neutral_output()

        current = epu_series.iloc[-1]

        # Calculate z-score
        recent = epu_series.iloc[-self.parameters["lookback_months"]:]
        zscore = (current - recent.mean()) / recent.std() if recent.std() > 0 else 0

        high_threshold = self.parameters["epu_threshold_high"]
        low_threshold = self.parameters["epu_threshold_low"]

        # High uncertainty = defensive
        if current > high_threshold or zscore > 1.5:
            direction = SignalDirection.SHORT  # Risk-off
            strength = min(1.0, current / 300)
            confidence = SignalConfidence.HIGH
            rationale = f"High policy uncertainty: {current:.0f} (z-score: {zscore:+.2f})"
        elif current < low_threshold and zscore < -0.5:
            direction = SignalDirection.LONG  # Risk-on
            strength = min(1.0, 1 - current / high_threshold)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Low policy uncertainty: {current:.0f} (z-score: {zscore:+.2f})"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.MEDIUM
            rationale = f"Normal policy uncertainty: {current:.0f}"

        return SignalOutput(
            timestamp=epu_series.index[-1] if len(epu_series.index) > 0 else pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction),
            rationale=rationale,
            metadata={
                "epu": current,
                "zscore": zscore,
                "historical_avg": recent.mean(),
            },
        )

    def _estimate_return(self, direction: SignalDirection) -> float:
        returns = {
            SignalDirection.LONG: 0.04,   # Normal risk-on
            SignalDirection.SHORT: -0.08,  # Defensive during high uncertainty
            SignalDirection.NEUTRAL: 0.0,
        }
        return returns.get(direction, 0.0)

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient data for policy uncertainty signal",
        )


class GlobalUncertaintySignal(Signal):
    """
    Global uncertainty signal from World Uncertainty Index.

    Research: Ahir, Bloom, Furceri - World Uncertainty Index

    Global uncertainty affects trade, investment, and risk appetite.
    """

    def __init__(self):
        super().__init__(
            name="global_uncertainty",
            description="Global uncertainty signal",
            asset_universe=["equities", "fx", "commodities"],
            frequency="quarterly",
        )
        self.parameters = {
            "wui_threshold": 100,
            "lookback_quarters": 12,
        }

    def calculate(self, wui_series: pd.Series) -> SignalOutput:
        """
        Calculate global uncertainty signal.

        Args:
            wui_series: World Uncertainty Index

        Returns:
            SignalOutput with global uncertainty assessment
        """
        if len(wui_series) < self.parameters["lookback_quarters"]:
            return self._neutral_output()

        current = wui_series.iloc[-1]
        threshold = self.parameters["wui_threshold"]

        recent = wui_series.iloc[-self.parameters["lookback_quarters"]:]
        zscore = (current - recent.mean()) / recent.std() if recent.std() > 0 else 0

        if current > threshold * 1.5 or zscore > 2.0:
            direction = SignalDirection.SHORT
            strength = min(1.0, current / 200)
            confidence = SignalConfidence.HIGH
            rationale = f"Elevated global uncertainty: {current:.0f}"
        elif current < threshold * 0.8 and zscore < -0.5:
            direction = SignalDirection.LONG
            strength = min(1.0, 0.8 - current / 200)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Contained global uncertainty: {current:.0f}"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.MEDIUM
            rationale = f"Normal global uncertainty: {current:.0f}"

        return SignalOutput(
            timestamp=wui_series.index[-1] if len(wui_series.index) > 0 else pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction),
            rationale=rationale,
            metadata={
                "wui": current,
                "zscore": zscore,
            },
        )

    def _estimate_return(self, direction: SignalDirection) -> float:
        returns = {
            SignalDirection.LONG: 0.03,
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
            rationale="Insufficient data for global uncertainty signal",
        )


class VolatilityUncertaintySignal(Signal):
    """
    Uncertainty signal derived from market volatility.

    Uses realized volatility as real-time uncertainty proxy.
    """

    def __init__(self, lookback_days: int = 20):
        super().__init__(
            name="volatility_uncertainty",
            description="Uncertainty from market volatility",
            asset_universe=["equities", "equity_volatility"],
            frequency="daily",
        )
        self.parameters = {
            "lookback_days": lookback_days,
            "vix_threshold_high": 25,
            "vix_threshold_low": 15,
        }

    def calculate(self, returns_series: pd.Series) -> SignalOutput:
        """
        Calculate volatility-based uncertainty.

        Args:
            returns_series: Asset returns series

        Returns:
            SignalOutput with volatility uncertainty
        """
        if len(returns_series) < self.parameters["lookback_days"]:
            return self._neutral_output()

        # Calculate realized volatility
        lookback = self.parameters["lookback_days"]
        recent_returns = returns_series.iloc[-lookback:]
        realized_vol = recent_returns.std() * np.sqrt(252) * 100  # Annualized, in percent

        # Compare to historical
        hist_vol = returns_series.std() * np.sqrt(252) * 100

        high_threshold = self.parameters["vix_threshold_high"]
        low_threshold = self.parameters["vix_threshold_low"]

        if realized_vol > high_threshold:
            direction = SignalDirection.SHORT
            strength = min(1.0, (realized_vol - high_threshold) / 20)
            confidence = SignalConfidence.HIGH
            rationale = f"High volatility uncertainty: {realized_vol:.1f}%"
        elif realized_vol < low_threshold:
            direction = SignalDirection.LONG
            strength = min(1.0, (low_threshold - realized_vol) / 10)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Low volatility: {realized_vol:.1f}%"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.MEDIUM
            rationale = f"Normal volatility: {realized_vol:.1f}%"

        return SignalOutput(
            timestamp=returns_series.index[-1] if len(returns_series.index) > 0 else pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction),
            rationale=rationale,
            metadata={
                "realized_vol": realized_vol,
                "historical_vol": hist_vol,
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
            rationale="Insufficient data for volatility uncertainty signal",
        )
