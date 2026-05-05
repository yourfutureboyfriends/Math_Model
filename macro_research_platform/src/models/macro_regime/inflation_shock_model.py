"""
Inflation Shock Model

Decomposes inflation into components:
- Core inflation pressure
- Energy shock
- Food shock
- Wage inflation pressure

Determines inflation regime:
- Demand-led inflation
- Supply-led inflation
- Wage-led inflation
- Disinflation
- Inflation shock

Based on:
- Kilian (2008) - Economic Effects of Energy Price Shocks
- Fang, Liu & Roussanov (2022) - Getting to the Core
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class InflationShockResult:
    """Inflation decomposition result."""
    headline_pressure: float
    core_pressure: float
    energy_contribution: float
    wage_pressure: float
    regime: str  # demand_led, supply_led, wage_led, disinflation, shock, balanced
    confidence: float
    drivers: Dict[str, str]


class InflationShockModel:
    """
    Inflation Shock Model

    Decomposes inflation into supply vs demand components
    and identifies inflation regime.
    """

    def __init__(self):
        # Thresholds
        self.inflation_threshold = 2.5  # %, target threshold
        self.shock_threshold = 1.5  # std dev threshold for shock

    def _calculate_core_pressure(
        self,
        core_inflation: float,
        trend: float = 2.0,
    ) -> float:
        """Calculate core inflation pressure score."""
        deviation = core_inflation - trend
        # Score: 1% above target = 0.4 pressure
        return np.clip(deviation / 2.5, -1.0, 1.0)

    def _calculate_energy_contribution(
        self,
        energy_price_change: float,
        oil_volatility: Optional[float] = None,
    ) -> float:
        """
        Calculate energy contribution to inflation.

        Based on Kilian (2008) - oil price shocks have different
        effects depending on whether they are supply or demand driven.
        """
        # Simplified: large oil price moves contribute to headline
        # Typical oil contribution to CPI: ~4%
        if abs(energy_price_change) < 10:  # Less than 10% move
            contribution = energy_price_change * 0.04 / 20  # Scale
        else:  # Shock
            contribution = np.sign(energy_price_change) * 0.3

        return np.clip(contribution, -0.5, 0.5)

    def _calculate_wage_pressure(
        self,
        wage_growth: float,
        productivity_growth: float = 1.5,
    ) -> float:
        """
        Calculate wage-price spiral pressure.

        Wage growth above productivity + inflation target = pressure
        """
        # Sustainable: wage growth = productivity + target inflation
        sustainable = productivity_growth + 2.0
        deviation = wage_growth - sustainable

        # Score: 1% above sustainable = 0.3 pressure
        return np.clip(deviation / 3.0, -0.5, 0.5)

    def _identify_regime(
        self,
        core_pressure: float,
        energy_contribution: float,
        wage_pressure: float,
    ) -> str:
        """Identify inflation regime."""
        # Calculate component magnitudes
        components = {
            "core": abs(core_pressure),
            "energy": abs(energy_contribution),
            "wage": abs(wage_pressure),
        }

        dominant = max(components, key=components.get)

        # Check for disinflation
        if core_pressure < -0.3 and energy_contribution < 0:
            return "disinflation"

        # Check for shock (rapid change)
        if components["energy"] > 0.3:
            return "supply_led"  # Energy shock = supply shock

        # Classify by dominant component
        if dominant == "wage" and wage_pressure > 0.2:
            return "wage_led"
        elif dominant == "core" and core_pressure > 0:
            return "demand_led"
        elif dominant == "energy" and energy_contribution > 0:
            return "supply_led"
        else:
            return "balanced"

    def analyze_inflation(
        self,
        headline_inflation: float,
        core_inflation: float,
        energy_price_change: float,
        wage_growth: float,
    ) -> InflationShockResult:
        """
        Analyze inflation composition and regime.

        Args:
            headline_inflation: Headline CPI y/y%
            core_inflation: Core CPI y/y%
            energy_price_change: Energy/Oil price y/y% change
            wage_growth: Wage growth y/y%

        Returns:
            InflationShockResult with decomposition
        """
        # Calculate components
        core_pressure = self._calculate_core_pressure(core_inflation)
        energy_contribution = self._calculate_energy_contribution(energy_price_change)
        wage_pressure = self._calculate_wage_pressure(wage_growth)

        # Calculate headline pressure
        headline_pressure = core_pressure + energy_contribution

        # Identify regime
        regime = self._identify_regime(
            core_pressure, energy_contribution, wage_pressure
        )

        # Build drivers
        drivers = {}
        if headline_inflation > self.inflation_threshold:
            drivers["headline"] = f"Above target: {headline_inflation:.1f}%"
        else:
            drivers["headline"] = f"Near/below target: {headline_inflation:.1f}%"

        if abs(energy_contribution) > 0.1:
            drivers["energy"] = f"Significant energy contribution: {energy_contribution:+.1%}"

        if wage_pressure > 0.1:
            drivers["wage"] = f"Elevated wage pressure: {wage_growth:.1f}%"

        # Confidence based on data availability
        confidence = 0.8 if all([
            headline_inflation is not None,
            core_inflation is not None,
        ]) else 0.5

        return InflationShockResult(
            headline_pressure=headline_pressure,
            core_pressure=core_pressure,
            energy_contribution=energy_contribution,
            wage_pressure=wage_pressure,
            regime=regime,
            confidence=confidence,
            drivers=drivers,
        )

    def get_regime_description(self, regime: str) -> str:
        """Get description of inflation regime."""
        descriptions = {
            "demand_led": (
                "Inflation is primarily demand-led. Core inflation is elevated "
                "suggesting overheating in the domestic economy. Policy tightening "
                "is appropriate to cool demand."
            ),
            "supply_led": (
                "Inflation is supply-led, driven by energy costs and/or supply "
                "constraints. Policy response is complicated - tightening may not "
                "address supply issues but could slow growth excessively."
            ),
            "wage_led": (
                "Wage-price spiral risk is elevated. Wage growth is running above "
                "sustainable levels. Risk of second-round effects and entrenched "
                "inflation. Policy action needed."
            ),
            "disinflation": (
                "Disinflationary pressures are dominant. Inflation is below target "
                "and falling. Policy easing may be appropriate."
            ),
            "shock": (
                "Inflation shock detected. Rapid price changes in specific sectors. "
                "May be transitory or may spill over. Monitor for persistence."
            ),
            "balanced": (
                "Inflation pressures are balanced. No dominant driver. Watch for "
                "shifts in composition."
            ),
        }
        return descriptions.get(regime, "Inflation regime unclear")


def compute_inflation_shock_from_data(
    df: pd.DataFrame,
    model: Optional[InflationShockModel] = None,
) -> InflationShockResult:
    """
    Compute inflation shock analysis from DataFrame.

    Expected columns:
    - us_cpi_yoy (headline)
    - us_core_cpi (core)
    - oil_price (for energy)
    - us_average_hourly_earnings (wages)
    """
    if model is None:
        model = InflationShockModel()

    latest = df.iloc[-1] if not df.empty else pd.Series()

    # Map columns
    headline_col = next(
        (c for c in df.columns if "cpi" in c.lower()),
        None,
    )
    core_col = next(
        (c for c in df.columns if "core" in c.lower()),
        None,
    )
    oil_col = next(
        (c for c in df.columns if "oil" in c.lower()),
        None,
    )
    wage_col = next(
        (c for c in df.columns if "wage" in c.lower() or "earn" in c.lower()),
        None,
    )

    # Get values
    headline = latest.get(headline_col) if headline_col else None
    core = latest.get(core_col) if core_col else None

    # Calculate oil price change (YoY)
    oil_change = None
    if oil_col and len(df) > 12:
        current = df[oil_col].iloc[-1]
        past = df[oil_col].iloc[-13]
        if past != 0:
            oil_change = (current - past) / past * 100

    # Wage growth
    wage_growth = latest.get(wage_col) if wage_col else None

    # Use defaults if missing
    headline = headline or 2.0
    core = core or 2.0
    oil_change = oil_change or 0.0
    wage_growth = wage_growth or 3.0

    return model.analyze_inflation(
        headline_inflation=headline,
        core_inflation=core,
        energy_price_change=oil_change,
        wage_growth=wage_growth,
    )
