"""
Regime-Based Signals

Signals that depend on growth/inflation regime classification.

Core Bridgewater concept: Different asset classes perform
differently depending on whether growth/inflation is
rising or falling relative to expectations.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .signal_base import MacroSignal, SignalConfidence, SignalDirection, SignalOutput

logger = logging.getLogger(__name__)


class GrowthInflationRegimeSignal(MacroSignal):
    """
    Signal based on growth and inflation regime.

    The four quadrants:
    - Rising Growth, Rising Inflation: Commodities, Inflation-Linked Bonds
    - Rising Growth, Falling Inflation: Equities, Credit
    - Falling Growth, Rising Inflation: Gold, Cash, TIPS
    - Falling Growth, Falling Inflation: Nominal Bonds
    """

    REGIME_ALLOCATIONS = {
        "reflation": {  # Growth up, Inflation up
            "equities": 0.3,
            "commodities": 0.3,
            "tips": 0.2,
            "nominal_bonds": 0.1,
            "cash": 0.1,
        },
        "goldilocks": {  # Growth up, Inflation down
            "equities": 0.5,
            "credit": 0.2,
            "nominal_bonds": 0.2,
            "cash": 0.1,
        },
        "stagflation": {  # Growth down, Inflation up
            "gold": 0.3,
            "tips": 0.3,
            "cash": 0.3,
            "commodities": 0.1,
        },
        "deflation": {  # Growth down, Inflation down
            "nominal_bonds": 0.5,
            "equities": 0.2,
            "cash": 0.3,
        },
    }

    def __init__(self, asset_universe: List[str]):
        super().__init__(
            name="growth_inflation_regime",
            description="Asset allocation based on growth/inflation regime",
            asset_universe=asset_universe,
            required_macros=["growth", "inflation", "growth_expectations", "inflation_expectations"],
        )
        self.regime_threshold = 0.5  # Standard deviations

    def calculate(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: Optional[datetime] = None,
    ) -> SignalOutput:
        """
        Determine regime and generate signal.

        Returns signal based on which regime we're in.
        """
        # Get latest data
        growth = data.get("growth", pd.Series()).iloc[-1] if "growth" in data else 0
        inflation = data.get("inflation", pd.Series()).iloc[-1] if "inflation" in data else 0

        # Calculate z-scores vs expectations
        growth_z = self._calculate_zscore(data.get("growth"))
        inflation_z = self._calculate_zscore(data.get("inflation"))

        # Determine regime
        if growth_z > 0 and inflation_z > 0:
            regime = "reflation"
            direction = SignalDirection.LONG
            strength = min(1.0, (growth_z + inflation_z) / 2)
        elif growth_z > 0 and inflation_z <= 0:
            regime = "goldilocks"
            direction = SignalDirection.LONG
            strength = min(1.0, growth_z)
        elif growth_z <= 0 and inflation_z > 0:
            regime = "stagflation"
            direction = SignalDirection.SHORT
            strength = min(1.0, inflation_z)
        else:
            regime = "deflation"
            direction = SignalDirection.NEUTRAL
            strength = min(1.0, abs(growth_z) + abs(inflation_z)) / 2

        # Get allocation for regime
        allocation = self.REGIME_ALLOCATIONS.get(regime, {})

        return SignalOutput(
            timestamp=as_of_date or datetime.now(),
            direction=direction,
            strength=strength,
            confidence=SignalConfidence.HIGH,
            rationale=f"In {regime} regime: Growth z={growth_z:.2f}, Inflation z={inflation_z:.2f}",
            metadata={
                "regime": regime,
                "growth_zscore": growth_z,
                "inflation_zscore": inflation_z,
                "allocation": allocation,
            },
        )

    def _calculate_zscore(self, series: Optional[pd.Series]) -> float:
        """Calculate z-score of latest value."""
        if series is None or len(series) < 24:
            return 0.0

        recent = series.iloc[-12:]  # Last year
        historical = series.iloc[:-12]  # Prior history

        if len(historical) == 0:
            return 0.0

        mean = historical.mean()
        std = historical.std()

        if std == 0:
            return 0.0

        return (recent.mean() - mean) / std


class BusinessCyclePhaseSignal(MacroSignal):
    """
    Signal based on business cycle phase.

    Phases: Early, Mid, Late, Recession
    Each phase has different optimal asset allocations.
    """

    PHASE_ALLOCATIONS = {
        "early": {
            "equities": 0.6,
            "credit": 0.2,
            "commodities": 0.1,
            "bonds": 0.1,
        },
        "mid": {
            "equities": 0.5,
            "credit": 0.2,
            "commodities": 0.15,
            "bonds": 0.15,
        },
        "late": {
            "equities": 0.35,
            "credit": 0.15,
            "commodities": 0.1,
            "bonds": 0.4,
        },
        "recession": {
            "equities": 0.2,
            "credit": 0.1,
            "commodities": 0.05,
            "bonds": 0.5,
            "cash": 0.15,
        },
    }

    def __init__(self, asset_universe: List[str]):
        super().__init__(
            name="business_cycle_phase",
            description="Asset allocation based on business cycle phase",
            asset_universe=asset_universe,
            required_macros=[
                "gdp_growth",
                "unemployment",
                "leading_indicators",
                "credit_spreads",
            ],
        )

    def calculate(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: Optional[datetime] = None,
    ) -> SignalOutput:
        """Determine business cycle phase and generate signal."""
        # Calculate cycle indicators
        gdp = data.get("gdp_growth", pd.Series())
        unemp = data.get("unemployment", pd.Series())
        leading = data.get("leading_indicators", pd.Series())
        credit = data.get("credit_spreads", pd.Series())

        # Phase detection logic
        phase = self._detect_phase(gdp, unemp, leading, credit)

        # Get allocation
        allocation = self.PHASE_ALLOCATIONS.get(phase, {})

        # Signal based on phase
        if phase in ["early", "mid"]:
            direction = SignalDirection.LONG
            strength = 0.7 if phase == "early" else 0.5
        elif phase == "late":
            direction = SignalDirection.NEUTRAL
            strength = 0.5
        else:  # recession
            direction = SignalDirection.SHORT
            strength = 0.8

        return SignalOutput(
            timestamp=as_of_date or datetime.now(),
            direction=direction,
            strength=strength,
            confidence=SignalConfidence.MEDIUM,
            rationale=f"Business cycle phase: {phase}",
            metadata={
                "phase": phase,
                "allocation": allocation,
            },
        )

    def _detect_phase(
        self,
        gdp: pd.Series,
        unemp: pd.Series,
        leading: pd.Series,
        credit: pd.Series,
    ) -> str:
        """Detect current business cycle phase."""
        # Simplified phase detection
        # In practice, would use more sophisticated rules

        if len(gdp) < 4:
            return "unknown"

        gdp_trend = gdp.iloc[-4:].mean() - gdp.iloc[-8:-4].mean()
        unemp_trend = unemp.iloc[-4:].mean() - unemp.iloc[-8:-4].mean() if len(unemp) >= 8 else 0

        if gdp_trend > 1.0 and unemp_trend < -0.2:
            return "early"
        elif gdp_trend > 0.5:
            return "mid"
        elif gdp_trend < 0 and unemp_trend > 0.1:
            return "late"
        elif gdp_trend < -0.5:
            return "recession"
        else:
            return "mid"  # Default


class PolicyStanceSignal(MacroSignal):
    """
    Signal based on central bank policy stance.

    Uses policy gap (current rate vs Taylor-implied) to
    assess policy restrictiveness.
    """

    def __init__(self, asset_universe: List[str]):
        super().__init__(
            name="policy_stance",
            description="Trade based on central bank policy stance vs neutral",
            asset_universe=asset_universe,
            required_macros=[
                "policy_rate",
                "inflation",
                "unemployment",
                "neutral_rate_estimate",
            ],
        )

    def calculate(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: Optional[datetime] = None,
    ) -> SignalOutput:
        """Generate signal based on policy stance."""
        policy_rate = data.get("policy_rate", pd.Series()).iloc[-1] if "policy_rate" in data else None
        inflation = data.get("inflation", pd.Series()).iloc[-1] if "inflation" in data else None
        unemployment = data.get("unemployment", pd.Series()).iloc[-1] if "unemployment" in data else None
        neutral = data.get("neutral_rate_estimate", pd.Series()).iloc[-1] if "neutral_rate_estimate" in data else 2.5

        if policy_rate is None or inflation is None:
            return SignalOutput(
                timestamp=as_of_date or datetime.now(),
                direction=SignalDirection.NEUTRAL,
                strength=0.0,
                confidence=SignalConfidence.LOW,
                rationale="Insufficient data for policy stance",
            )

        # Calculate real rate
        real_rate = policy_rate - inflation

        # Calculate Taylor-implied rate
        # r* + 1.5*(inflation - 2%) + 0.5*(unemployment gap)
        unemployment_gap = 4.5 - unemployment if unemployment else 0
        taylor_rate = neutral + 1.5 * (inflation - 2.0) - 0.5 * unemployment_gap

        # Policy gap
        policy_gap = policy_rate - taylor_rate

        # Generate signal
        if policy_gap > 1.0:
            # Tight policy - bearish for equities, bullish for bonds
            direction = SignalDirection.SHORT
            strength = min(1.0, policy_gap / 2.0)
            rationale = f"Policy tight: {policy_rate:.2f}% vs Taylor-implied {taylor_rate:.2f}%"
        elif policy_gap < -1.0:
            # Loose policy - bullish for equities, bearish for bonds
            direction = SignalDirection.LONG
            strength = min(1.0, abs(policy_gap) / 2.0)
            rationale = f"Policy loose: {policy_rate:.2f}% vs Taylor-implied {taylor_rate:.2f}%"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.3
            rationale = f"Policy neutral: {policy_rate:.2f}% vs Taylor-implied {taylor_rate:.2f}%"

        return SignalOutput(
            timestamp=as_of_date or datetime.now(),
            direction=direction,
            strength=strength,
            confidence=SignalConfidence.MEDIUM,
            rationale=rationale,
            metadata={
                "policy_rate": policy_rate,
                "real_rate": real_rate,
                "taylor_rate": taylor_rate,
                "policy_gap": policy_gap,
            },
        )
