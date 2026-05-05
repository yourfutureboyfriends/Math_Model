"""
Carry Signals

Signals related to carry, term premia, and yield curve strategies.

Research backing:
- Koijen, Moskowitz, Pedersen, Vrugt - Carry
- Cochrane, Piazzesi - Bond Risk Premia
- Lustig, Verdelhan - The Cross-Section of Foreign Currency Risk Premia
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .signal_base import Signal, SignalDirection, SignalOutput, SignalConfidence

logger = logging.getLogger(__name__)


class TermPremiumCarrySignal(Signal):
    """
    Term premium / steepness carry signal.

    Research: Cochrane, Piazzesi - Bond Risk Premia

    Upward sloping yield curve predicts positive excess returns.
    """

    def __init__(self):
        super().__init__(
            name="term_premium_carry",
            description="Term premium carry signal from yield curve",
            asset_universe=["bonds", "rates"],
            frequency="monthly",
        )
        self.parameters = {
            "long_duration": 10,  # years
            "short_duration": 2,  # years
            "carry_threshold": 0.5,  # %
        }

    def calculate(self, long_yield: float, short_yield: float) -> SignalOutput:
        """
        Calculate term premium carry signal.

        Args:
            long_yield: Long-term bond yield (%)
            short_yield: Short-term bond yield (%)

        Returns:
            SignalOutput with carry assessment
        """
        carry = long_yield - short_yield  # Slope of yield curve

        if carry > self.parameters["carry_threshold"]:
            direction = SignalDirection.LONG
            strength = min(1.0, carry / 2.0)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Yield curve steep ({carry:.1f}%) - positive term premium carry"
        elif carry < 0:
            direction = SignalDirection.SHORT
            strength = min(1.0, abs(carry) / 1.0)
            confidence = SignalConfidence.HIGH
            rationale = f"Inverted yield curve ({carry:.1f}%) - negative carry"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.MEDIUM
            rationale = f"Modest yield curve slope ({carry:.1f}%)"

        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction, carry),
            rationale=rationale,
            metadata={
                "long_yield": long_yield,
                "short_yield": short_yield,
                "carry": carry,
                "duration": self.parameters["long_duration"] - self.parameters["short_duration"],
            },
        )

    def _estimate_return(self, direction: SignalDirection, carry: float) -> float:
        if direction == SignalDirection.LONG:
            return 0.02 * carry  # ~2% per unit of carry
        elif direction == SignalDirection.SHORT:
            return -0.02 * abs(carry)
        return 0.0


class CreditCarrySignal(Signal):
    """
    Credit spread carry signal.

    Credit spreads provide compensation for default risk.
    """

    def __init__(self):
        super().__init__(
            name="credit_carry",
            description="Credit spread carry signal",
            asset_universe=["credit", "hy_credit"],
            frequency="monthly",
        )
        self.parameters = {
            "min_spread": 200,  # bps - minimum for compensation
            "target_spread": 400,  # bps
        }

    def calculate(self, spread_series: pd.Series, default_rate: float = 0.0) -> SignalOutput:
        """
        Calculate credit carry signal.

        Args:
            spread_series: Credit spread series (bps)
            default_rate: Expected default rate (%)

        Returns:
            SignalOutput with credit carry assessment
        """
        if len(spread_series) < 12:
            return self._neutral_output()

        current_spread = spread_series.iloc[-1]
        min_spread = self.parameters["min_spread"]

        # Net carry after expected defaults
        net_carry = current_spread - (default_rate * 100)  # Convert default rate to bps

        if net_carry > min_spread:
            direction = SignalDirection.LONG
            strength = min(1.0, net_carry / self.parameters["target_spread"])
            confidence = SignalConfidence.MEDIUM
            rationale = f"Credit spread {current_spread:.0f}bps provides adequate carry"
        elif current_spread < min_spread * 0.5:
            direction = SignalDirection.SHORT
            strength = min(1.0, 1 - current_spread / min_spread)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Credit spread {current_spread:.0f}bps insufficient for risk"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.LOW
            rationale = f"Credit spread {current_spread:.0f}bps - marginal compensation"

        return SignalOutput(
            timestamp=spread_series.index[-1] if len(spread_series.index) > 0 else pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction, net_carry),
            rationale=rationale,
            metadata={
                "spread": current_spread,
                "net_carry": net_carry,
                "default_rate": default_rate,
            },
        )

    def _estimate_return(self, direction: SignalDirection, net_carry: float) -> float:
        if direction == SignalDirection.LONG:
            return net_carry / 100  # Return in %
        elif direction == SignalDirection.SHORT:
            return -net_carry / 200
        return 0.0

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient credit spread data",
        )


class FXCarrySignal(Signal):
    """
    FX carry signal based on interest rate differentials.

    Research: Lustig, Verdelhan - The Cross-Section of Foreign Currency Risk Premia

    High-yielding currencies tend to outperform.
    """

    def __init__(self):
        super().__init__(
            name="fx_carry",
            description="FX carry signal from rate differentials",
            asset_universe=["fx", "em_fx"],
            frequency="monthly",
        )
        self.parameters = {
            "min_carry": 1.0,  # % annualized
            "max_vol_adj_carry": 1.5,
        }

    def calculate(self, local_rate: float, funding_rate: float, fx_vol: float = 10.0) -> SignalOutput:
        """
        Calculate FX carry signal.

        Args:
            local_rate: Local currency interest rate (%)
            funding_rate: Funding currency rate (%) - e.g., USD
            fx_vol: FX volatility (%)

        Returns:
            SignalOutput with FX carry assessment
        """
        carry = local_rate - funding_rate
        vol_adjusted_carry = carry / fx_vol if fx_vol > 0 else 0

        min_carry = self.parameters["min_carry"]

        if carry > min_carry and vol_adjusted_carry > 0.3:
            direction = SignalDirection.LONG  # Long high-yielder
            strength = min(1.0, carry / 5.0)
            confidence = SignalConfidence.MEDIUM if vol_adjusted_carry > 0.5 else SignalConfidence.LOW
            rationale = f"FX carry {carry:.1f}% with vol-adjusted {vol_adjusted_carry:.2f}"
        elif carry < -min_carry:
            direction = SignalDirection.SHORT
            strength = min(1.0, abs(carry) / 5.0)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Negative FX carry {carry:.1f}% - short funding pressure"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.0
            confidence = SignalConfidence.LOW
            rationale = f"Limited FX carry: {carry:.1f}%"

        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction, carry),
            rationale=rationale,
            metadata={
                "carry": carry,
                "local_rate": local_rate,
                "funding_rate": funding_rate,
                "vol_adjusted_carry": vol_adjusted_carry,
            },
        )

    def _estimate_return(self, direction: SignalDirection, carry: float) -> float:
        # FX carry trades earn the spread, but with crash risk
        if direction == SignalDirection.LONG:
            return carry * 0.7 / 100  # Assume capture 70% of carry
        elif direction == SignalDirection.SHORT:
            return -carry * 0.5 / 100
        return 0.0


class CarryTradeRiskSignal(Signal):
    """
    Risk-adjusted carry trade signal.

    Considers carry vs volatility and tail risk.
    """

    def __init__(self):
        super().__init__(
            name="carry_risk",
            description="Risk-adjusted carry trade signal",
            asset_universe=["fx", "credit", "em"],
            frequency="weekly",
        )
        self.parameters = {
            "sharpe_threshold": 0.5,
            "max_position_size": 1.0,
        }

    def calculate(self, carry: float, volatility: float, skewness: float = 0.0) -> SignalOutput:
        """
        Calculate risk-adjusted carry.

        Args:
            carry: Annualized carry (%)
            volatility: Realized volatility (%)
            skewness: Return skewness (negative = left tail)

        Returns:
            SignalOutput with risk-adjusted carry
        """
        sharpe = carry / volatility if volatility > 0 else 0

        # Adjust for skewness (penalize negative skew)
        skew_adjustment = 1.0 + max(-0.5, skewness / 3)  # Range 0.5 to 1.5
        adjusted_sharpe = sharpe * skew_adjustment

        threshold = self.parameters["sharpe_threshold"]

        if adjusted_sharpe > threshold and carry > 0:
            direction = SignalDirection.LONG
            strength = min(1.0, adjusted_sharpe / 1.5)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Attractive risk-adjusted carry: Sharpe {sharpe:.2f}, skew {skewness:.2f}"
        elif adjusted_sharpe < -threshold and carry < 0:
            direction = SignalDirection.SHORT
            strength = min(1.0, abs(adjusted_sharpe) / 1.5)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Negative carry with poor risk profile: Sharpe {sharpe:.2f}"
        elif sharpe < threshold / 2 and carry > 0:
            direction = SignalDirection.NEUTRAL
            strength = 0.3
            confidence = SignalConfidence.LOW
            rationale = f"Poor risk-adjusted carry: Sharpe {sharpe:.2f} below threshold"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.LOW
            rationale = f"Marginal carry: Sharpe {sharpe:.2f}, skew {skewness:.2f}"

        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction, adjusted_sharpe),
            rationale=rationale,
            metadata={
                "carry": carry,
                "volatility": volatility,
                "sharpe": sharpe,
                "skewness": skewness,
                "adjusted_sharpe": adjusted_sharpe,
            },
        )

    def _estimate_return(self, direction: SignalDirection, adjusted_sharpe: float) -> float:
        if direction == SignalDirection.LONG:
            return adjusted_sharpe * 0.05  # ~5% vol assumption
        elif direction == SignalDirection.SHORT:
            return -adjusted_sharpe * 0.05
        return 0.0


class RollDownCarrySignal(Signal):
    """
    Roll-down carry signal for bond futures.

    Captures price appreciation as bond approaches maturity.
    """

    def __init__(self):
        super().__init__(
            name="roll_down_carry",
            description="Bond roll-down carry signal",
            asset_universe=["bonds", "rates"],
            frequency="monthly",
        )
        self.parameters = {
            "years_to_maturity": 10,
            "convexity_factor": 0.5,
        }

    def calculate(self, yield_curve: Dict[float, float], duration: float) -> SignalOutput:
        """
        Calculate roll-down carry.

        Args:
            yield_curve: Dict of maturity (years) to yield (%)
            duration: Bond duration

        Returns:
            SignalOutput with roll-down carry
        """
        if len(yield_curve) < 3:
            return self._neutral_output()

        # Find current maturity yield
        current_yield = None
        for mat, yld in sorted(yield_curve.items()):
            if mat >= self.parameters["years_to_maturity"]:
                current_yield = yld
                break

        if current_yield is None:
            current_yield = list(yield_curve.values())[-1]

        # Find shorter maturity yield (for roll-down)
        shorter_yield = current_yield  # Default
        sorted_mats = sorted(yield_curve.keys())
        for i, mat in enumerate(sorted_mats):
            if mat >= self.parameters["years_to_maturity"] - 1 and i > 0:
                shorter_yield = yield_curve[sorted_mats[i-1]]
                break

        # Roll-down = price gain from moving down the curve
        yield_change = current_yield - shorter_yield
        roll_down = yield_change * duration * self.parameters["convexity_factor"]

        # Add coupon carry
        coupon_carry = current_yield / 12  # Monthly

        total_carry = coupon_carry + roll_down

        if total_carry > 0.3:
            direction = SignalDirection.LONG
            strength = min(1.0, total_carry / 1.0)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Roll-down carry {total_carry:.2f}% (coupon {coupon_carry:.2f}% + roll {roll_down:.2f}%)"
        elif total_carry < 0:
            direction = SignalDirection.SHORT
            strength = min(1.0, abs(total_carry) / 0.5)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Negative roll-down carry {total_carry:.2f}%"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.LOW
            rationale = f"Modest roll-down carry {total_carry:.2f}%"

        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction, total_carry),
            rationale=rationale,
            metadata={
                "total_carry": total_carry,
                "coupon_carry": coupon_carry,
                "roll_down": roll_down,
                "duration": duration,
            },
        )

    def _estimate_return(self, direction: SignalDirection, carry: float) -> float:
        if direction == SignalDirection.LONG:
            return carry * 12 / 100  # Annualized
        return 0.0

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient yield curve data",
        )
