"""
Momentum Signals

Signals related to time-series and cross-sectional momentum.

Research backing:
- Moskowitz, Ooi, Pedersen - Time Series Momentum
- Hurst, Ooi, Pedersen - A Century of Evidence on Trend Following
- Asness, Moskowitz, Pedersen - Value and Momentum Everywhere
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .signal_base import Signal, SignalDirection, SignalOutput, SignalConfidence

logger = logging.getLogger(__name__)


class TimeSeriesMomentumSignal(Signal):
    """
    Time-series momentum signal.

    Research: Moskowitz, Ooi, Pedersen - Time Series Momentum

    Past 12-month returns predict future returns.
    Positive past returns = go long, negative = go short.
    """

    def __init__(self, lookback_months: int = 12):
        super().__init__(
            name="ts_momentum",
            description="Time-series momentum signal",
            asset_universe=["equities", "bonds", "commodities", "fx"],
            frequency="monthly",
        )
        self.parameters = {
            "lookback_months": lookback_months,
            "strength_threshold": 0.05,  # 5%
        }

    def calculate(self, price_series: pd.Series) -> SignalOutput:
        """
        Calculate time-series momentum.

        Args:
            price_series: Asset price series

        Returns:
            SignalOutput with momentum signal
        """
        if len(price_series) < self.parameters["lookback_months"] + 1:
            return self._neutral_output()

        lookback = self.parameters["lookback_months"]

        # Calculate return over lookback period
        past_return = (price_series.iloc[-1] / price_series.iloc[-lookback-1] - 1)

        threshold = self.parameters["strength_threshold"]

        if past_return > threshold:
            direction = SignalDirection.LONG
            strength = min(1.0, past_return / 0.20)
            rationale = f"Positive momentum: +{past_return:.1%} over {lookback} months"
        elif past_return < -threshold:
            direction = SignalDirection.SHORT
            strength = min(1.0, abs(past_return) / 0.20)
            rationale = f"Negative momentum: {past_return:.1%} over {lookback} months"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            rationale = f"Weak momentum: {past_return:.1%} over {lookback} months"

        return SignalOutput(
            timestamp=price_series.index[-1] if len(price_series.index) > 0 else pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=SignalConfidence.HIGH,
            expected_return=self._estimate_return(direction, abs(past_return)),
            rationale=rationale,
            metadata={
                "lookback_return": past_return,
                "lookback_months": lookback,
            },
        )

    def _estimate_return(self, direction: SignalDirection, magnitude: float) -> float:
        """Estimate expected return based on momentum."""
        base_returns = {
            SignalDirection.LONG: 0.06,
            SignalDirection.SHORT: -0.06,
            SignalDirection.NEUTRAL: 0.0,
        }
        base = base_returns.get(direction, 0.0)
        # Scale by momentum magnitude
        return base * min(1.0, magnitude / 0.10)

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient data for time-series momentum",
        )


class CrossAssetMomentumSignal(Signal):
    """
    Cross-asset momentum confirmation signal.

    Research: Asness, Moskowitz, Pedersen - Value and Momentum Everywhere

    Momentum works across asset classes - confirm macro view with momentum.
    """

    def __init__(self):
        super().__init__(
            name="cross_asset_momentum",
            description="Cross-asset momentum confirmation",
            asset_universe=["equities", "rates", "credit", "commodities", "fx"],
            frequency="monthly",
        )
        self.parameters = {
            "lookback_months": 12,
            "min_assets_agreeing": 3,
        }

    def calculate(self, asset_returns: Dict[str, float]) -> SignalOutput:
        """
        Calculate cross-asset momentum.

        Args:
            asset_returns: Dict of asset class to 12-month return

        Returns:
            SignalOutput with cross-asset momentum assessment
        """
        if len(asset_returns) < self.parameters["min_assets_agreeing"]:
            return self._neutral_output()

        # Count positive and negative momentum
        positive = sum(1 for r in asset_returns.values() if r > 0.05)
        negative = sum(1 for r in asset_returns.values() if r < -0.05)
        total = len(asset_returns)

        if total == 0:
            return self._neutral_output()

        positive_pct = positive / total
        negative_pct = negative / total

        # Agreement threshold
        min_agree = self.parameters["min_assets_agreeing"]

        if positive >= min_agree and positive_pct > 0.6:
            direction = SignalDirection.LONG
            strength = min(1.0, positive_pct)
            confidence = SignalConfidence.HIGH if positive >= 4 else SignalConfidence.MEDIUM
            rationale = f"Broad momentum agreement: {positive}/{total} asset classes positive"
        elif negative >= min_agree and negative_pct > 0.6:
            direction = SignalDirection.SHORT
            strength = min(1.0, negative_pct)
            confidence = SignalConfidence.HIGH if negative >= 4 else SignalConfidence.MEDIUM
            rationale = f"Broad momentum weakness: {negative}/{total} asset classes negative"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.LOW
            rationale = f"Mixed momentum signals: {positive} positive, {negative} negative"

        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction),
            rationale=rationale,
            metadata={
                "positive_assets": positive,
                "negative_assets": negative,
                "total_assets": total,
                "asset_returns": asset_returns,
            },
        )

    def _estimate_return(self, direction: SignalDirection) -> float:
        returns = {
            SignalDirection.LONG: 0.05,
            SignalDirection.SHORT: -0.05,
            SignalDirection.NEUTRAL: 0.0,
        }
        return returns.get(direction, 0.0)

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient cross-asset data for momentum signal",
        )


class TrendFollowingSignal(Signal):
    """
    Trend following signal for crisis alpha.

    Research: Hurst, Ooi, Pedersen - A Century of Evidence on Trend Following Investing

    Trend following works as crisis alpha - captures momentum during stress.
    """

    def __init__(self, lookback_months: int = 12):
        super().__init__(
            name="trend_following",
            description="Trend following signal for crisis alpha",
            asset_universe=["equities", "bonds", "commodities", "fx"],
            frequency="monthly",
        )
        self.parameters = {
            "lookback_months": lookback_months,
            "volatility_lookback": 3,  # months
        }

    def calculate(self, price_series: pd.Series) -> SignalOutput:
        """
        Calculate trend following signal.

        Args:
            price_series: Asset price series

        Returns:
            SignalOutput with trend signal
        """
        if len(price_series) < self.parameters["lookback_months"] + 1:
            return self._neutral_output()

        lookback = self.parameters["lookback_months"]

        # Calculate trend
        trend_return = (price_series.iloc[-1] / price_series.iloc[-lookback-1] - 1)

        # Risk-adjust the trend
        recent_returns = price_series.pct_change().iloc[-self.parameters["volatility_lookback"]:]
        volatility = recent_returns.std() * np.sqrt(12) if len(recent_returns) > 0 else 0.15

        # Sharpe-adjusted trend
        if volatility > 0:
            sharpe = trend_return / volatility
        else:
            sharpe = 0

        if trend_return > 0.05 and sharpe > 0.3:
            direction = SignalDirection.LONG
            strength = min(1.0, sharpe / 1.0)
            confidence = SignalConfidence.HIGH
            rationale = f"Positive trend: {trend_return:.1%}, Sharpe: {sharpe:.2f}"
        elif trend_return < -0.05 and sharpe < -0.3:
            direction = SignalDirection.SHORT
            strength = min(1.0, abs(sharpe) / 1.0)
            confidence = SignalConfidence.HIGH
            rationale = f"Negative trend: {trend_return:.1%}, Sharpe: {sharpe:.2f}"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.3
            confidence = SignalConfidence.LOW
            rationale = f"Weak trend: {trend_return:.1%}, Sharpe: {sharpe:.2f}"

        return SignalOutput(
            timestamp=price_series.index[-1] if len(price_series.index) > 0 else pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction, abs(trend_return)),
            rationale=rationale,
            metadata={
                "trend_return": trend_return,
                "volatility": volatility,
                "sharpe": sharpe,
            },
        )

    def _estimate_return(self, direction: SignalDirection, magnitude: float) -> float:
        base_returns = {
            SignalDirection.LONG: 0.07,
            SignalDirection.SHORT: -0.07,
            SignalDirection.NEUTRAL: 0.0,
        }
        base = base_returns.get(direction, 0.0)
        return base * min(1.0, magnitude / 0.10)

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient data for trend following signal",
        )


class MomentumReversalSignal(Signal):
    """
    Signal for momentum reversals (short-term).

    Very short-term momentum tends to reverse (mean reversion).
    Use as contrarian signal for short-term trades.
    """

    def __init__(self, lookback_weeks: int = 4):
        super().__init__(
            name="momentum_reversal",
            description="Short-term momentum reversal signal",
            asset_universe=["equities", "fx"],
            frequency="weekly",
        )
        self.parameters = {
            "lookback_weeks": lookback_weeks,
            "reversal_threshold": 0.05,
        }

    def calculate(self, price_series: pd.Series) -> SignalOutput:
        """Calculate momentum reversal signal."""
        if len(price_series) < self.parameters["lookback_weeks"] + 1:
            return self._neutral_output()

        lookback = self.parameters["lookback_weeks"]
        short_return = (price_series.iloc[-1] / price_series.iloc[-lookback-1] - 1)

        threshold = self.parameters["reversal_threshold"]

        # Contrarian - recent big moves tend to reverse
        if short_return > threshold:
            direction = SignalDirection.SHORT  # Expect reversal down
            strength = min(1.0, short_return / 0.10)
            rationale = f"Strong recent gain ({short_return:.1%}) - expect partial reversal"
        elif short_return < -threshold:
            direction = SignalDirection.LONG  # Expect reversal up
            strength = min(1.0, abs(short_return) / 0.10)
            rationale = f"Strong recent decline ({short_return:.1%}) - expect partial bounce"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.0
            rationale = f"No significant short-term move ({short_return:.1%})"

        return SignalOutput(
            timestamp=price_series.index[-1] if len(price_series.index) > 0 else pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=SignalConfidence.LOW,  # Lower confidence for reversals
            expected_return=self._estimate_return(direction),
            rationale=rationale,
            metadata={
                "short_return": short_return,
                "lookback_weeks": lookback,
            },
        )

    def _estimate_return(self, direction: SignalDirection) -> float:
        # Smaller expected returns for reversal trades
        returns = {
            SignalDirection.LONG: 0.02,
            SignalDirection.SHORT: -0.02,
            SignalDirection.NEUTRAL: 0.0,
        }
        return returns.get(direction, 0.0)

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient data for momentum reversal signal",
        )
