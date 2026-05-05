"""
Commodity Signals

Signals related to commodity curves, inventory, and commodity cycles.

Research backing:
- Gorton, Hayashi, Rouwenhorst - The Fundamentals of Commodity Futures Returns
- Singleton - Investor Flows and Asset Prices
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .signal_base import Signal, SignalDirection, SignalOutput, SignalConfidence

logger = logging.getLogger(__name__)


class CommodityCurveSignal(Signal):
    """
    Commodity curve shape signal.

    Research: Gorton, Hayashi, Rouwenhorst

    Contango vs backwardation indicates inventory/storage conditions.
    """

    def __init__(self):
        super().__init__(
            name="commodity_curve",
            description="Commodity curve contango/backwardation signal",
            asset_universe=["commodities", "energy", "metals", "agriculture"],
            frequency="weekly",
        )
        self.parameters = {
            "near_contract": 1,  # month
            "far_contract": 12,  # months
            "threshold": 2.0,  # % annualized
        }

    def calculate(self, near_price: float, far_price: float, months_apart: int = 12) -> SignalOutput:
        """
        Calculate commodity curve signal.

        Args:
            near_price: Near contract price
            far_price: Far contract price
            months_apart: Months between contracts

        Returns:
            SignalOutput with curve signal
        """
        if near_price <= 0 or far_price <= 0:
            return self._neutral_output()

        # Calculate annualized roll yield
        roll_yield = ((far_price / near_price) - 1) * (12 / months_apart) * 100

        threshold = self.parameters["threshold"]

        # Backwardation (negative roll yield) = positive signal
        if roll_yield < -threshold:
            direction = SignalDirection.LONG
            strength = min(1.0, abs(roll_yield) / 10)
            confidence = SignalConfidence.HIGH
            rationale = f"Backwardation {roll_yield:.1f}% - positive roll yield"
        elif roll_yield > threshold:
            direction = SignalDirection.SHORT
            strength = min(1.0, roll_yield / 10)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Contango {roll_yield:.1f}% - negative roll yield"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.MEDIUM
            rationale = f"Flat curve {roll_yield:.1f}%"

        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction, roll_yield),
            rationale=rationale,
            metadata={
                "roll_yield": roll_yield,
                "near_price": near_price,
                "far_price": far_price,
            },
        )

    def _estimate_return(self, direction: SignalDirection, roll_yield: float) -> float:
        # Expected return includes the roll yield component
        if direction == SignalDirection.LONG:
            return abs(roll_yield) / 100 * 0.7  # Capture ~70% of roll
        elif direction == SignalDirection.SHORT:
            return -roll_yield / 100 * 0.5
        return 0.0

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Invalid commodity price data",
        )


class InventoryPressureSignal(Signal):
    """
    Inventory-based commodity signal.

    Low inventory = tight supply = potential price increase.
    """

    def __init__(self):
        super().__init__(
            name="inventory_pressure",
            description="Commodity inventory pressure signal",
            asset_universe=["commodities", "energy", "metals"],
            frequency="weekly",
        )
        self.parameters = {
            "lookback_months": 60,  # 5 years
        }

    def calculate(self, inventory_series: pd.Series) -> SignalOutput:
        """
        Calculate inventory pressure signal.

        Args:
            inventory_series: Inventory levels series

        Returns:
            SignalOutput with inventory assessment
        """
        if len(inventory_series) < 12:
            return self._neutral_output()

        current = inventory_series.iloc[-1]

        # Calculate percentile
        lookback = min(len(inventory_series), self.parameters["lookback_months"])
        percentile = (inventory_series.iloc[-lookback:] <= current).mean()

        # Low inventory = bullish
        if percentile < 0.2:
            direction = SignalDirection.LONG
            strength = min(1.0, (0.2 - percentile) / 0.2 + 0.5)
            confidence = SignalConfidence.HIGH
            rationale = f"Inventory at {percentile:.0%} percentile - tight supply"
        elif percentile > 0.8:
            direction = SignalDirection.SHORT
            strength = min(1.0, (percentile - 0.8) / 0.2 + 0.5)
            confidence = SignalConfidence.HIGH
            rationale = f"Inventory at {percentile:.0%} percentile - excess supply"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.MEDIUM
            rationale = f"Inventory at {percentile:.0%} percentile - balanced"

        return SignalOutput(
            timestamp=inventory_series.index[-1] if len(inventory_series.index) > 0 else pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction, percentile),
            rationale=rationale,
            metadata={
                "inventory": current,
                "percentile": percentile,
                "zscore": (current - inventory_series.mean()) / inventory_series.std() if inventory_series.std() > 0 else 0,
            },
        )

    def _estimate_return(self, direction: SignalDirection, percentile: float) -> float:
        # Mean reversion expected around inventory extremes
        if direction == SignalDirection.LONG:
            return 0.08 * (0.5 - percentile)
        elif direction == SignalDirection.SHORT:
            return -0.08 * (percentile - 0.5)
        return 0.0

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient inventory data",
        )


class CommodityMomentumSignal(Signal):
    """
    Commodity-specific momentum signal.

    Commodities exhibit strong momentum in certain regimes.
    """

    def __init__(self, lookback_months: int = 12):
        super().__init__(
            name="commodity_momentum",
            description="Commodity price momentum signal",
            asset_universe=["commodities", "energy", "metals", "agriculture"],
            frequency="monthly",
        )
        self.parameters = {
            "lookback_months": lookback_months,
            "volatility_lookback": 3,
        }

    def calculate(self, price_series: pd.Series) -> SignalOutput:
        """
        Calculate commodity momentum.

        Args:
            price_series: Commodity price series

        Returns:
            SignalOutput with momentum assessment
        """
        if len(price_series) < self.parameters["lookback_months"] + 1:
            return self._neutral_output()

        lookback = self.parameters["lookback_months"]
        ret = (price_series.iloc[-1] / price_series.iloc[-lookback-1] - 1)

        # Risk-adjust
        recent_vol = price_series.pct_change().iloc[-self.parameters["volatility_lookback"]:].std() * np.sqrt(12)
        sharpe = ret / recent_vol if recent_vol > 0 else 0

        if ret > 0.15 and sharpe > 0.5:
            direction = SignalDirection.LONG
            strength = min(1.0, ret / 0.50)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Commodity momentum +{ret:.1%} (Sharpe {sharpe:.2f})"
        elif ret < -0.15 and sharpe < -0.5:
            direction = SignalDirection.SHORT
            strength = min(1.0, abs(ret) / 0.50)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Negative commodity momentum {ret:.1%} (Sharpe {sharpe:.2f})"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.LOW
            rationale = f"Weak commodity momentum {ret:.1%}"

        return SignalOutput(
            timestamp=price_series.index[-1] if len(price_series.index) > 0 else pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction, abs(ret)),
            rationale=rationale,
            metadata={
                "return": ret,
                "sharpe": sharpe,
                "volatility": recent_vol,
            },
        )

    def _estimate_return(self, direction: SignalDirection, magnitude: float) -> float:
        if direction == SignalDirection.LONG:
            return 0.06 * min(1.0, magnitude / 0.20)
        elif direction == SignalDirection.SHORT:
            return -0.06 * min(1.0, magnitude / 0.20)
        return 0.0

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient commodity price data",
        )


class DollarCommoditySignal(Signal):
    """
    Dollar impact on commodities signal.

    Commodities are priced in USD, so dollar strength matters.
    """

    def __init__(self):
        super().__init__(
            name="dollar_commodity",
            description="Dollar impact on commodity prices",
            asset_universe=["commodities", "dollar"],
            frequency="weekly",
        )
        self.parameters = {
            "correlation": -0.5,  # Typical commodity-dollar correlation
            "dxy_lookback": 12,  # weeks
        }

    def calculate(self, dxy_series: pd.Series) -> SignalOutput:
        """
        Calculate dollar impact signal.

        Args:
            dxy_series: Dollar index series

        Returns:
            SignalOutput with dollar impact
        """
        if len(dxy_series) < self.parameters["dxy_lookback"] + 1:
            return self._neutral_output()

        lookback = self.parameters["dxy_lookback"]
        dxy_return = (dxy_series.iloc[-1] / dxy_series.iloc[-lookback-1] - 1)

        # Inverse relationship: strong dollar = commodity headwind
        if dxy_return > 0.05:
            direction = SignalDirection.SHORT  # Commodity headwind
            strength = min(1.0, dxy_return / 0.10)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Dollar strengthened {dxy_return:.1%} - commodity headwind"
        elif dxy_return < -0.05:
            direction = SignalDirection.LONG  # Commodity tailwind
            strength = min(1.0, abs(dxy_return) / 0.10)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Dollar weakened {dxy_return:.1%} - commodity tailwind"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.LOW
            rationale = f"Dollar stable {dxy_return:.1%}"

        return SignalOutput(
            timestamp=dxy_series.index[-1] if len(dxy_series.index) > 0 else pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction, dxy_return),
            rationale=rationale,
            metadata={
                "dxy_return": dxy_return,
                "implied_commodity_impact": dxy_return * self.parameters["correlation"],
            },
        )

    def _estimate_return(self, direction: SignalDirection, dxy_return: float) -> float:
        # Expected commodity return from dollar move
        correlation = self.parameters["correlation"]
        if direction == SignalDirection.LONG:
            return abs(dxy_return) * abs(correlation)
        elif direction == SignalDirection.SHORT:
            return -dxy_return * correlation
        return 0.0

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient dollar data",
        )
