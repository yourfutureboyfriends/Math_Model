"""
Macro Rate Signals

Signals for fixed income based on macroeconomic conditions.

Rate markets are driven by:
1. Inflation expectations
2. Real growth expectations
3. Policy expectations
4. Term premium
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .signal_base import MacroSignal, SignalConfidence, SignalDirection, SignalOutput

logger = logging.getLogger(__name__)


class InflationExpectationsSignal(MacroSignal):
    """
    Signal based on inflation expectations vs realized.

    When inflation expectations are rising, rates tend to rise.
    When expectations overshoot actual, there's mean reversion risk.
    """

    def __init__(self):
        super().__init__(
            name="inflation_expectations",
            description="Trade rates based on inflation expectations vs realized",
            asset_universe=["rates", "tips", "nominal_bonds"],
            required_macros=["inflation_expectations", "realized_inflation", "breakeven_inflation"],
        )

    def calculate(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: Optional[datetime] = None,
    ) -> SignalOutput:
        """Generate signal based on inflation expectations."""
        breakeven = data.get("breakeven_inflation", pd.Series())
        realized = data.get("realized_inflation", pd.Series())

        if len(breakeven) < 6 or len(realized) < 6:
            return SignalOutput(
                timestamp=as_of_date or datetime.now(),
                direction=SignalDirection.NEUTRAL,
                strength=0.0,
                confidence=SignalConfidence.LOW,
                rationale="Insufficient inflation data",
            )

        # Calculate inflation surprise
        current_be = breakeven.iloc[-1]
        expected_realized = realized.iloc[-12:].mean()
        inflation_gap = current_be - expected_realized

        # Signal logic
        if inflation_gap > 0.5:
            # Breakevens too high vs realized - rates could fall
            direction = SignalDirection.LONG  # Long bonds (rates fall)
            strength = min(1.0, inflation_gap / 1.5)
            rationale = f"Breakeven {current_be:.2f}% above realized trend {expected_realized:.2f}%"
        elif inflation_gap < -0.5:
            # Breakevens too low - inflation risk
            direction = SignalDirection.SHORT  # Short bonds (rates rise)
            strength = min(1.0, abs(inflation_gap) / 1.5)
            rationale = f"Breakeven {current_be:.2f}% below realized trend {expected_realized:.2f}%"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.2
            rationale = "Inflation expectations in line with realized"

        return SignalOutput(
            timestamp=as_of_date or datetime.now(),
            direction=direction,
            strength=strength,
            confidence=SignalConfidence.MEDIUM,
            rationale=rationale,
            metadata={
                "breakeven": current_be,
                "realized_trend": expected_realized,
                "inflation_gap": inflation_gap,
            },
        )


class YieldCurveSteepenerSignal(MacroSignal):
    """
    Signal to steepen or flatten the yield curve.

    Curve steepens when:
    - Recession fears increase (early easing)
    - Inflation expectations rise (long end sells off)

    Curve flattens when:
    - Policy tightening expected
    - Growth optimism + inflation contained
    """

    def __init__(self):
        super().__init__(
            name="yield_curve_shape",
            description="Trade yield curve steepeners/flatteners",
            asset_universe=["rates", "curve_trades"],
            required_macros=[
                "yields_2y",
                "yields_10y",
                "policy_expectations",
                "growth_expectations",
            ],
        )

    def calculate(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: Optional[datetime] = None,
    ) -> SignalOutput:
        """Generate curve shape signal."""
        y2 = data.get("yields_2y", pd.Series())
        y10 = data.get("yields_10y", pd.Series())

        if len(y2) < 3 or len(y10) < 3:
            return SignalOutput(
                timestamp=as_of_date or datetime.now(),
                direction=SignalDirection.NEUTRAL,
                strength=0.0,
                confidence=SignalConfidence.LOW,
                rationale="Insufficient yield data",
            )

        # Calculate curve spread
        current_spread = y10.iloc[-1] - y2.iloc[-1]
        spread_ma = (y10.iloc[-20:] - y2.iloc[-20:]).mean() if len(y10) >= 20 else current_spread

        # Historical context
        spread_z = (current_spread - spread_ma) / (y10 - y2).std() if len(y10) >= 60 else 0

        if spread_z < -1.0:
            # Curve very flat - steepening likely
            direction = SignalDirection.LONG  # Long steepener
            strength = min(1.0, abs(spread_z) / 2)
            rationale = f"Curve very flat ({current_spread:.0f}bps), steepening expected"
        elif spread_z > 1.5:
            # Curve very steep - flattening likely
            direction = SignalDirection.SHORT  # Short steepener (long flattener)
            strength = min(1.0, spread_z / 2)
            rationale = f"Curve very steep ({current_spread:.0f}bps), flattening expected"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.3
            rationale = f"Curve at normal steepness ({current_spread:.0f}bps)"

        return SignalOutput(
            timestamp=as_of_date or datetime.now(),
            direction=direction,
            strength=strength,
            confidence=SignalConfidence.MEDIUM,
            rationale=rationale,
            metadata={
                "curve_spread": current_spread,
                "spread_zscore": spread_z,
            },
        )


class CreditCycleSignal(MacroSignal):
    """
    Signal based on credit cycle position.

    Early cycle: credit spreads tight, corporate health good
    Late cycle: credit spreads widening, recession risk rising
    """

    def __init__(self):
        super().__init__(
            name="credit_cycle",
            description="Trade credit spreads based on cycle position",
            asset_universe=["credit", "high_yield", "investment_grade"],
            required_macros=[
                "credit_spreads",
                "leverage_ratios",
                "default_rates",
                "gdp_growth",
            ],
        )

    def calculate(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: Optional[datetime] = None,
    ) -> SignalOutput:
        """Generate credit cycle signal."""
        spreads = data.get("credit_spreads", pd.Series())
        leverage = data.get("leverage_ratios", pd.Series())
        defaults = data.get("default_rates", pd.Series())
        gdp = data.get("gdp_growth", pd.Series())

        if len(spreads) < 12:
            return SignalOutput(
                timestamp=as_of_date or datetime.now(),
                direction=SignalDirection.NEUTRAL,
                strength=0.0,
                confidence=SignalConfidence.LOW,
                rationale="Insufficient credit data",
            )

        # Calculate credit stress indicators
        spread_percentile = self._calculate_percentile(spreads)
        leverage_trend = leverage.iloc[-4:].mean() - leverage.iloc[-8:-4].mean() if len(leverage) >= 8 else 0

        # Signal logic
        if spread_percentile > 0.8 and leverage_trend > 0:
            # High spreads + rising leverage = recession risk
            direction = SignalDirection.SHORT  # Short credit
            strength = min(1.0, spread_percentile)
            rationale = f"Credit stress: spreads at {spread_percentile:.0%} percentile"
        elif spread_percentile < 0.2 and gdp.iloc[-1] > 2:
            # Low spreads + strong growth = good environment
            direction = SignalDirection.LONG  # Long credit
            strength = 0.7
            rationale = f"Credit benign: spreads at {spread_percentile:.0%} percentile"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.4
            rationale = f"Credit conditions neutral: {spread_percentile:.0%} percentile"

        return SignalOutput(
            timestamp=as_of_date or datetime.now(),
            direction=direction,
            strength=strength,
            confidence=SignalConfidence.MEDIUM,
            rationale=rationale,
            metadata={
                "spread_percentile": spread_percentile,
                "leverage_trend": leverage_trend,
            },
        )

    def _calculate_percentile(self, series: pd.Series) -> float:
        """Calculate percentile of current value."""
        if len(series) < 24:
            return 0.5

        current = series.iloc[-1]
        historical = series.iloc[:-1]

        return (historical < current).mean()


class TermPremiumSignal(MacroSignal):
    """
    Signal based on term premium estimates.

    When term premium is high (above fair value), long bonds attractive.
    When term premium is compressed, carry is poor.
    """

    def __init__(self):
        super().__init__(
            name="term_premium",
            description="Trade based on term premium vs fair value",
            asset_universe=["long_bonds", "duration"],
            required_macros=[
                "yields_10y",
                "yields_2y",
                "inflation_expectations",
                "real_rate_estimate",
            ],
        )

    def calculate(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: Optional[datetime] = None,
    ) -> SignalOutput:
        """Generate term premium signal."""
        y10 = data.get("yields_10y", pd.Series()).iloc[-1] if "yields_10y" in data else None
        y2 = data.get("yields_2y", pd.Series()).iloc[-1] if "yields_2y" in data else None

        if y10 is None or y2 is None:
            return SignalOutput(
                timestamp=as_of_date or datetime.now(),
                direction=SignalDirection.NEUTRAL,
                strength=0.0,
                confidence=SignalConfidence.LOW,
                rationale="Insufficient yield data",
            )

        # Estimate term premium (simplified)
        # Term premium ≈ 10Y yield - expected policy path - inflation expectations
        term_premium_estimate = y10 - y2 - 0.5  # Simplified: 10Y - 2Y - expected inflation

        # Historical comparison
        historical_premium = 0.5  # Long-term average

        if term_premium_estimate > historical_premium + 0.5:
            # Term premium high - long bonds attractive
            direction = SignalDirection.LONG
            strength = min(1.0, (term_premium_estimate - historical_premium) / 1.0)
            rationale = f"Term premium elevated: {term_premium_estimate:.2f}% vs {historical_premium:.2f}% average"
        elif term_premium_estimate < historical_premium - 0.3:
            # Term premium compressed
            direction = SignalDirection.SHORT
            strength = min(1.0, (historical_premium - term_premium_estimate) / 0.5)
            rationale = f"Term premium compressed: {term_premium_estimate:.2f}% vs {historical_premium:.2f}% average"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.3
            rationale = f"Term premium near fair value: {term_premium_estimate:.2f}%"

        return SignalOutput(
            timestamp=as_of_date or datetime.now(),
            direction=direction,
            strength=strength,
            confidence=SignalConfidence.MEDIUM,
            rationale=rationale,
            metadata={
                "estimated_term_premium": term_premium_estimate,
                "historical_average": historical_premium,
            },
        )
