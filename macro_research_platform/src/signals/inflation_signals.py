"""
Inflation Signals

Signals related to inflation pressure, inflation trends, and inflation expectations.

Research backing:
- McCracken & Ng - FRED-MD inflation components
- Various inflation targeting literature
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .signal_base import Signal, SignalDirection, SignalOutput, SignalConfidence

logger = logging.getLogger(__name__)


class InflationDiffusionSignal(Signal):
    """
    Diffusion index of inflation indicators.

    Measures the breadth of inflation pressure across multiple indicators.
    """

    def __init__(self, indicators: List[str] = None):
        super().__init__(
            name="inflation_diffusion",
            description="Breadth of inflation pressure across multiple indicators",
            asset_universe=["rates", "credit", "gold", "commodities"],
            frequency="monthly",
        )
        self.indicators = indicators or [
            "cpi_headline",
            "cpi_core",
            "ppi",
            "wage_growth",
            "import_prices",
            "inflation_expectations",
        ]
        self.parameters = {
            "inflation_target": 2.0,
            "zscore_threshold": 0.5,
            "lookback_months": 24,
        }

    def calculate(self, data: pd.DataFrame) -> SignalOutput:
        """Calculate inflation diffusion signal."""
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

        # Calculate diffusion (% of indicators above target)
        above_target = sum(1 for z in zscores.values() if z > 0)
        diffusion = above_target / len(zscores)

        # Average z-score
        avg_z = np.mean(list(zscores.values()))

        # Determine direction (rates sensitive to inflation)
        if avg_z > 0.5:
            direction = SignalDirection.SHORT  # Higher rates = bond prices down
            strength = min(1.0, avg_z / 2)
        elif avg_z < -0.5:
            direction = SignalDirection.LONG
            strength = min(1.0, abs(avg_z) / 2)
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5

        return SignalOutput(
            timestamp=data.index[-1] if len(data.index) > 0 else pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=self._calculate_confidence(zscores),
            expected_return=self._estimate_return(direction),
            rationale=f"Inflation diffusion at {diffusion:.0%} ({above_target}/{len(zscores)} indicators above target)",
            metadata={
                "diffusion": diffusion,
                "avg_zscore": avg_z,
                "zscores": zscores,
            },
        )

    def _calculate_zscore(self, series: pd.Series) -> float:
        """Calculate z-score relative to target."""
        if len(series) < 12:
            return 0.0

        lookback = self.parameters["lookback_months"]
        target = self.parameters["inflation_target"]

        recent = series.iloc[-lookback:]

        if recent.std() == 0:
            return 0.0

        return (series.iloc[-1] - target) / recent.std()

    def _calculate_confidence(self, zscores: Dict) -> SignalConfidence:
        """Calculate confidence based on agreement."""
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
        """Estimate expected return."""
        # Inflation signal primarily affects rates
        returns = {
            SignalDirection.LONG: 0.03,   # Rates fall = bond prices rise
            SignalDirection.SHORT: -0.03,  # Rates rise = bond prices fall
            SignalDirection.NEUTRAL: 0.0,
        }
        return returns.get(direction, 0.0)

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient data for inflation diffusion signal",
        )


class InflationExpectationsSignal(Signal):
    """
    Signal based on inflation expectations vs realized inflation.

    Divergence between expectations and reality creates signal.
    """

    def __init__(self):
        super().__init__(
            name="inflation_expectations",
            description="Inflation expectations signal",
            asset_universe=["rates", "inflation_linked_bonds"],
            frequency="monthly",
        )
        self.parameters = {
            "expectation_source": "breakeven",
            "realized_measure": "core_pce",
        }

    def calculate(self, data: Dict[str, pd.Series]) -> SignalOutput:
        """Calculate inflation expectations signal."""
        expected_key = self.parameters["expectation_source"]
        realized_key = self.parameters["realized_measure"]

        if expected_key not in data or realized_key not in data:
            return self._neutral_output()

        expected = data[expected_key].iloc[-1] if len(data[expected_key]) > 0 else 0
        realized = data[realized_key].iloc[-1] if len(data[realized_key]) > 0 else 0

        gap = expected - realized

        # Large gap suggests expectations will adjust
        if gap > 0.5:  # Expectations too high
            direction = SignalDirection.SHORT  # Rates will fall
            strength = min(1.0, gap / 1.5)
            rationale = f"Inflation expectations ({expected:.1f}%) above realized ({realized:.1f}%)"
        elif gap < -0.5:  # Expectations too low
            direction = SignalDirection.LONG  # Rates will rise
            strength = min(1.0, abs(gap) / 1.5)
            rationale = f"Inflation expectations ({expected:.1f}%) below realized ({realized:.1f}%)"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            rationale = f"Inflation expectations aligned with realized"

        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=SignalConfidence.MEDIUM,
            expected_return=self._estimate_return(direction),
            rationale=rationale,
            metadata={
                "expected": expected,
                "realized": realized,
                "gap": gap,
            },
        )

    def _estimate_return(self, direction: SignalDirection) -> float:
        returns = {
            SignalDirection.LONG: 0.025,
            SignalDirection.SHORT: -0.025,
            SignalDirection.NEUTRAL: 0.0,
        }
        return returns.get(direction, 0.0)

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient data for inflation expectations signal",
        )


class InflationMomentumSignal(Signal):
    """
    Signal based on inflation momentum (change in inflation rate).

    Rising inflation momentum suggests continued pressure.
    """

    def __init__(self, lookback_months: int = 6):
        super().__init__(
            name="inflation_momentum",
            description="Inflation momentum signal",
            asset_universe=["rates", "commodities"],
            frequency="monthly",
        )
        self.parameters = {
            "lookback_months": lookback_months,
        }

    def calculate(self, inflation_series: pd.Series) -> SignalOutput:
        """Calculate inflation momentum signal."""
        if len(inflation_series) < self.parameters["lookback_months"] + 1:
            return self._neutral_output()

        current = inflation_series.iloc[-1]
        previous = inflation_series.iloc[-self.parameters["lookback_months"]-1]

        change = current - previous

        # Determine signal based on momentum
        if change > 0.3:  # Rising inflation
            direction = SignalDirection.SHORT
            strength = min(1.0, change / 1.0)
            rationale = f"Inflation rising: {previous:.1f}% → {current:.1f}% (change: +{change:.1f}%)"
        elif change < -0.3:  # Falling inflation
            direction = SignalDirection.LONG
            strength = min(1.0, abs(change) / 1.0)
            rationale = f"Inflation falling: {previous:.1f}% → {current:.1f}% (change: {change:.1f}%)"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            rationale = f"Inflation stable: {current:.1f}%"

        return SignalOutput(
            timestamp=inflation_series.index[-1] if len(inflation_series.index) > 0 else pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=SignalConfidence.HIGH,
            expected_return=self._estimate_return(direction),
            rationale=rationale,
            metadata={
                "current": current,
                "previous": previous,
                "change": change,
            },
        )

    def _estimate_return(self, direction: SignalDirection) -> float:
        returns = {
            SignalDirection.LONG: 0.03,
            SignalDirection.SHORT: -0.03,
            SignalDirection.NEUTRAL: 0.0,
        }
        return returns.get(direction, 0.0)

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient data for inflation momentum signal",
        )
