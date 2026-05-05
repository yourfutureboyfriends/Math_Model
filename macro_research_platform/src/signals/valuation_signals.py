"""
Valuation Signals

Signals related to asset valuation, CAPE ratios, and value investing.

Research backing:
- Shiller - Irrational Exuberance, CAPE ratio
- Campbell, Thompson - Predicting Excess Stock Returns
- Lettau, Ludvigson - Consumption-Wealth Ratio
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .signal_base import Signal, SignalDirection, SignalOutput, SignalConfidence

logger = logging.getLogger(__name__)


class CAPESignal(Signal):
    """
    Cyclically Adjusted PE (CAPE) signal.

    Research: Shiller - Irrational Exuberance

    CAPE predicts long-term returns. High CAPE = lower future returns.
    """

    def __init__(self):
        super().__init__(
            name="cape_valuation",
            description="CAPE-based valuation signal",
            asset_universe=["equities"],
            frequency="monthly",
        )
        self.parameters = {
            "mean_cape": 17.0,
            "cheap_threshold": 15.0,
            "expensive_threshold": 25.0,
            "extreme_threshold": 30.0,
        }

    def calculate(self, cape_series: pd.Series) -> SignalOutput:
        """
        Calculate CAPE-based signal.

        Args:
            cape_series: CAPE ratio series

        Returns:
            SignalOutput with valuation assessment
        """
        if len(cape_series) < 12:
            return self._neutral_output()

        current_cape = cape_series.iloc[-1]
        params = self.parameters

        # Calculate percentile
        percentile = (cape_series <= current_cape).mean()

        # Signal logic
        if current_cape > params["extreme_threshold"]:
            direction = SignalDirection.SHORT
            strength = min(1.0, (current_cape - params["extreme_threshold"]) / 10)
            confidence = SignalConfidence.HIGH
            rationale = f"CAPE at {current_cape:.1f} - extreme overvaluation"
        elif current_cape > params["expensive_threshold"]:
            direction = SignalDirection.SHORT
            strength = min(1.0, (current_cape - params["expensive_threshold"]) / 15)
            confidence = SignalConfidence.MEDIUM
            rationale = f"CAPE at {current_cape:.1f} - expensive valuation"
        elif current_cape < params["cheap_threshold"]:
            direction = SignalDirection.LONG
            strength = min(1.0, (params["cheap_threshold"] - current_cape) / 5)
            confidence = SignalConfidence.HIGH
            rationale = f"CAPE at {current_cape:.1f} - cheap valuation"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.MEDIUM
            rationale = f"CAPE at {current_cape:.1f} - fair valuation"

        return SignalOutput(
            timestamp=cape_series.index[-1] if len(cape_series.index) > 0 else pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction, percentile),
            rationale=rationale,
            metadata={
                "cape": current_cape,
                "percentile": percentile,
                "historical_mean": cape_series.mean(),
            },
        )

    def _estimate_return(self, direction: SignalDirection, percentile: float) -> float:
        # Expected returns based on CAPE percentile
        if direction == SignalDirection.SHORT:
            return -0.04 * (percentile - 0.5) * 2  # Higher CAPE = lower returns
        elif direction == SignalDirection.LONG:
            return 0.06 * (1 - percentile)
        return 0.0

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient CAPE data",
        )


class YieldGapSignal(Signal):
    """
    Equity-bond yield gap signal.

    Compares earnings yield (E/P) to bond yields.
    """

    def __init__(self):
        super().__init__(
            name="yield_gap",
            description="Equity-bond yield gap signal",
            asset_universe=["equities", "bonds"],
            frequency="monthly",
        )
        self.parameters = {
            "long_term_avg_gap": 3.0,  # E/P - bond yield, in %
        }

    def calculate(self, earnings_yield: float, bond_yield: float) -> SignalOutput:
        """
        Calculate yield gap signal.

        Args:
            earnings_yield: Earnings/Price ratio (%)
            bond_yield: Bond yield (%)

        Returns:
            SignalOutput with yield gap assessment
        """
        gap = earnings_yield - bond_yield
        avg_gap = self.parameters["long_term_avg_gap"]

        gap_diff = gap - avg_gap

        if gap_diff > 2:
            direction = SignalDirection.LONG
            strength = min(1.0, gap_diff / 4)
            confidence = SignalConfidence.HIGH
            rationale = f"Yield gap {gap:.1f}% vs avg {avg_gap:.1f}% - equities attractive"
        elif gap_diff < -2:
            direction = SignalDirection.SHORT
            strength = min(1.0, abs(gap_diff) / 4)
            confidence = SignalConfidence.HIGH
            rationale = f"Yield gap {gap:.1f}% vs avg {avg_gap:.1f}% - bonds attractive"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.MEDIUM
            rationale = f"Yield gap near neutral: {gap:.1f}%"

        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction),
            rationale=rationale,
            metadata={
                "earnings_yield": earnings_yield,
                "bond_yield": bond_yield,
                "gap": gap,
                "gap_diff": gap_diff,
            },
        )

    def _estimate_return(self, direction: SignalDirection) -> float:
        returns = {
            SignalDirection.LONG: 0.05,
            SignalDirection.SHORT: -0.04,
            SignalDirection.NEUTRAL: 0.0,
        }
        return returns.get(direction, 0.0)


class ValueSpreadSignal(Signal):
    """
    Value spread signal - cheap vs expensive stocks.

    Research: Asness et al - The Value Premium

    Value spreads predict value factor returns.
    """

    def __init__(self):
        super().__init__(
            name="value_spread",
            description="Value spread between cheap and expensive stocks",
            asset_universe=["equities", "value_factor"],
            frequency="monthly",
        )
        self.parameters = {
            "lookback_years": 20,
        }

    def calculate(self, value_spread_series: pd.Series) -> SignalOutput:
        """
        Calculate value spread signal.

        Args:
            value_spread_series: Series of value spreads

        Returns:
            SignalOutput with value assessment
        """
        if len(value_spread_series) < 60:  # 5 years minimum
            return self._neutral_output()

        current_spread = value_spread_series.iloc[-1]

        # Calculate z-score
        lookback = min(len(value_spread_series), self.parameters["lookback_years"] * 12)
        recent = value_spread_series.iloc[-lookback:]
        zscore = (current_spread - recent.mean()) / recent.std() if recent.std() > 0 else 0

        # High spread = value is cheap (LONG value)
        if zscore > 1.5:
            direction = SignalDirection.LONG
            strength = min(1.0, zscore / 3)
            confidence = SignalConfidence.HIGH
            rationale = f"Value spread {zscore:.2f} SD above normal - extreme value opportunity"
        elif zscore > 0.5:
            direction = SignalDirection.LONG
            strength = min(1.0, zscore / 2)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Value spread {zscore:.2f} SD above normal - value looks attractive"
        elif zscore < -1.0:
            direction = SignalDirection.SHORT
            strength = min(1.0, abs(zscore) / 2)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Value spread {zscore:.2f} SD below normal - growth extreme"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.MEDIUM
            rationale = f"Value spread near normal: {zscore:.2f} SD"

        return SignalOutput(
            timestamp=value_spread_series.index[-1] if len(value_spread_series.index) > 0 else pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction, abs(zscore)),
            rationale=rationale,
            metadata={
                "value_spread": current_spread,
                "zscore": zscore,
                "percentile": (recent <= current_spread).mean(),
            },
        )

    def _estimate_return(self, direction: SignalDirection, zscore: float) -> float:
        # Value spreads mean revert - wide spreads = higher future returns
        if direction == SignalDirection.LONG:
            return 0.08 * min(1.0, zscore / 2)
        elif direction == SignalDirection.SHORT:
            return -0.04
        return 0.0

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient value spread data",
        )


class CreditYieldSignal(Signal):
    """
    Credit yield vs equity yield signal.

    Compares relative attractiveness of credit vs equities.
    """

    def __init__(self):
        super().__init__(
            name="credit_yield",
            description="Credit yield relative to equity yield",
            asset_universe=["credit", "equities"],
            frequency="monthly",
        )
        self.parameters = {
            "hy_spread_threshold": 400,  # bps
        }

    def calculate(self, hy_yield: float, equity_yield: float) -> SignalOutput:
        """
        Calculate credit yield signal.

        Args:
            hy_yield: High yield bond yield (%)
            equity_yield: Equity earnings yield (%)

        Returns:
            SignalOutput with relative value assessment
        """
        yield_diff = hy_yield - equity_yield

        if yield_diff > 3:
            direction = SignalDirection.LONG
            strength = min(1.0, yield_diff / 6)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Credit yields {hy_yield:.1f}% vs equities {equity_yield:.1f}% - prefer credit"
        elif yield_diff < -3:
            direction = SignalDirection.SHORT
            strength = min(1.0, abs(yield_diff) / 6)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Equity yields {equity_yield:.1f}% vs credit {hy_yield:.1f}% - prefer equities"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.LOW
            rationale = f"Balanced yields - credit {hy_yield:.1f}%, equity {equity_yield:.1f}%"

        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction),
            rationale=rationale,
            metadata={
                "hy_yield": hy_yield,
                "equity_yield": equity_yield,
                "yield_diff": yield_diff,
            },
        )

    def _estimate_return(self, direction: SignalDirection) -> float:
        returns = {
            SignalDirection.LONG: 0.04,   # Credit outperformance
            SignalDirection.SHORT: -0.04,  # Equity outperformance
            SignalDirection.NEUTRAL: 0.0,
        }
        return returns.get(direction, 0.0)


class AssetClassValuationSignal(Signal):
    """
    Multi-asset class valuation signal.

    Combines valuation signals across asset classes.
    """

    def __init__(self):
        super().__init__(
            name="asset_class_valuation",
            description="Cross-asset valuation signal",
            asset_universe=["equities", "bonds", "credit", "reits"],
            frequency="monthly",
        )
        self.parameters = {
            "lookback_years": 10,
        }

    def calculate(self, valuations: Dict[str, pd.Series]) -> SignalOutput:
        """
        Calculate cross-asset valuation.

        Args:
            valuations: Dict of asset class to valuation series

        Returns:
            SignalOutput with overall valuation assessment
        """
        if len(valuations) < 2:
            return self._neutral_output()

        zscores = {}
        for asset, series in valuations.items():
            if len(series) >= 12:
                lookback = min(len(series), self.parameters["lookback_years"] * 12)
                recent = series.iloc[-lookback:]
                z = (series.iloc[-1] - recent.mean()) / recent.std() if recent.std() > 0 else 0
                zscores[asset] = z

        if not zscores:
            return self._neutral_output()

        avg_zscore = np.mean(list(zscores.values()))

        # Average z-score determines signal
        if avg_zscore > 1.0:
            direction = SignalDirection.SHORT
            strength = min(1.0, avg_zscore / 2)
            confidence = SignalConfidence.HIGH
            rationale = f"Cross-asset overvaluation ({avg_zscore:.2f} SD)"
        elif avg_zscore < -1.0:
            direction = SignalDirection.LONG
            strength = min(1.0, abs(avg_zscore) / 2)
            confidence = SignalConfidence.HIGH
            rationale = f"Cross-asset undervaluation ({avg_zscore:.2f} SD)"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.MEDIUM
            rationale = f"Fair cross-asset valuation ({avg_zscore:.2f} SD)"

        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction),
            rationale=rationale,
            metadata={
                "avg_zscore": avg_zscore,
                "asset_zscores": zscores,
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
            rationale="Insufficient cross-asset valuation data",
        )
