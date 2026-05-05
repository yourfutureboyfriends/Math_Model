"""
Debt Cycle Tracker

Monitors the debt cycle - the most important driver of economic activity
according to Bridgewater's "Economic Machine" framework.

Key concepts:
1. Long-term debt cycle (50-75 years): Debt growth vs income growth
2. Short-term debt cycle (5-8 years): Credit expansion and contraction
3. Debt burdens: Debt service vs income
4. Deleveraging mechanics: Austerity, debt defaults, money printing, etc.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class DebtCycleState:
    """Current state of the debt cycle."""
    cycle_phase: str  # early, bubble, top, depression, reflation, late
    debt_to_income: float
    debt_service_ratio: float
    credit_growth_rate: float
    nominal_gdp_growth: float
    interest_rate_level: float
    deleveraging_type: Optional[str]  # None if not deleveraging


@dataclass
class LeveragingMetrics:
    """Metrics for assessing leverage levels."""
    debt_to_gdp: float
    debt_to_income: float
    debt_service_to_income: float
    credit_impulse: float  # Change in credit growth
    private_credit_growth: float
    public_credit_growth: float
    household_leverage: float
    corporate_leverage: float


class DebtCycleTracker:
    """
    Track the debt cycle and identify which phase of the cycle we're in.

    Based on Bridgewater's framework:
    - Debt growth faster than income growth = leveraging
    - Debt growth slower than income growth = deleveraging
    - Debt service costs vs income determines pain level
    """

    # Debt cycle phases
    PHASES = {
        "early": {
            "description": "Early cycle: Debt low, strong growth potential",
            "characteristics": ["debt_to_gdp_low", "credit_growing_normally", "strong_growth"],
            "typical_duration_years": 5,
            "risk_level": "low",
        },
        "bubble": {
            "description": "Bubble: Debt growing faster than income, asset bubbles forming",
            "characteristics": ["debt_accelerating", "asset_prices_rising_fast", "euphoria"],
            "typical_duration_years": 3,
            "risk_level": "medium_high",
        },
        "top": {
            "description": "Peak: Tightening kills the expansion",
            "characteristics": ["rates_peaking", "credit_tightening", "asset_prices_falling"],
            "typical_duration_years": 1,
            "risk_level": "high",
        },
        "depression": {
            "description": "Depression: Debt burdens too high, defaults rising",
            "characteristics": ["deleveraging", "defaults_high", "deflationary_pressure"],
            "typical_duration_years": 2,
            "risk_level": "very_high",
        },
        "reflation": {
            "description": "Reflation: Policy response brings nominal growth back",
            "characteristics": ["policy_easing", "nominal_growth_accelerating", "confidence_returning"],
            "typical_duration_years": 3,
            "risk_level": "medium",
        },
        "late": {
            "description": "Late cycle: Growth slowing but not yet in recession",
            "characteristics": ["growth_slow", "inflation_pressures", "tightening_begins"],
            "typical_duration_years": 2,
            "risk_level": "medium_high",
        },
    }

    # Thresholds for assessments
    DEBT_TO_GDP_HIGH = 300  # % of GDP
    DEBT_TO_GDP_MED = 200
    DEBT_SERVICE_HIGH = 20  # % of income
    CREDIT_GROWTH_FAST = 15  # % YoY

    def __init__(self):
        self.metrics_history: List[LeveragingMetrics] = []
        self.phase_history: List[str] = []

    def calculate_leverage_metrics(
        self,
        total_debt: float,  # In currency units
        gdp: float,
        disposable_income: float,
        debt_service_payments: float,
        credit_growth_rate: float,
        private_credit: float,
        public_credit: float,
        household_debt: float,
        corporate_debt: float,
        household_income: float,
        corporate_ebitda: float,
    ) -> LeveragingMetrics:
        """Calculate comprehensive leverage metrics."""
        return LeveragingMetrics(
            debt_to_gdp=(total_debt / gdp) * 100 if gdp > 0 else 0,
            debt_to_income=(total_debt / disposable_income) * 100 if disposable_income > 0 else 0,
            debt_service_to_income=(debt_service_payments / disposable_income) * 100
            if disposable_income > 0 else 0,
            credit_impulse=credit_growth_rate - self._get_trend_credit_growth(),
            private_credit_growth=private_credit,
            public_credit_growth=public_credit,
            household_leverage=(household_debt / household_income) * 100 if household_income > 0 else 0,
            corporate_leverage=(corporate_debt / corporate_ebitda) if corporate_ebitda > 0 else 0,
        )

    def _get_trend_credit_growth(self) -> float:
        """Get trend credit growth (simplified - would use history in practice)."""
        return 8.0  # Historical average roughly

    def identify_cycle_phase(self, metrics: LeveragingMetrics,
                            prev_metrics: Optional[LeveragingMetrics] = None) -> str:
        """
        Identify which phase of the debt cycle we're in.

        Uses heuristics based on debt levels and credit impulse.
        """
        dti = metrics.debt_to_income
        dsi = metrics.debt_service_to_income
        impulse = metrics.credit_impulse

        # High debt service = depression risk
        if dsi > self.DEBT_SERVICE_HIGH and impulse < -2:
            return "depression"

        # Very high debt + tightening credit = bubble/late
        if dti > self.DEBT_TO_GDP_HIGH:
            if impulse > 3:
                return "bubble"
            elif impulse < -2:
                return "top"
            else:
                return "late"

        # Medium-high debt with accelerating credit = bubble forming
        if dti > self.DEBT_TO_GDP_MED and impulse > 3:
            return "bubble"

        # Early cycle: Low debt, normal credit growth
        if dti < self.DEBT_TO_GDP_MED and abs(impulse) < 2:
            return "early"

        # Tightening phase
        if impulse < -3 and dti > self.DEBT_TO_GDP_MED:
            return "top"

        # Recovery from depression
        if dsi > 15 and impulse > 0:
            return "reflation"

        # Default to late cycle
        return "late"

    def assess_deleveraging_type(
        self,
        metrics: LeveragingMetrics,
        policy_response: str,  # tight, neutral, loose
        inflation_level: float,
        currency_stability: str,  # stable, weakening, crisis
    ) -> Optional[str]:
        """
        Classify type of deleveraging per Bridgewater framework.

        Types:
        - Beautiful: Inflationary growth > interest rates
        - Ugly: Austerity without inflation
        - Bad: Debt defaults
        - Good: Money printing + currency devaluation
        """
        if metrics.credit_impulse > 0:
            return None  # Not deleveraging

        if policy_response == "loose" and inflation_level < 3:
            # Money printing without high inflation = good deleveraging
            return "good"

        if policy_response == "tight" and metrics.debt_service_to_income > 20:
            # Austerity with high debt burdens = ugly
            return "ugly"

        if currency_stability == "crisis":
            # Currency crisis = bad deleveraging
            return "bad"

        if policy_response == "loose" and inflation_level > 4:
            # Inflation > rates = beautiful deleveraging
            return "beautiful"

        return "mild"  # Mild deleveraging

    def calculate_debt_burden(self, metrics: LeveragingMetrics) -> Dict:
        """
        Calculate debt burden relative to capacity to service.

        Returns burden score and interpretation.
        """
        # Debt service burden
        dsi = metrics.debt_service_to_income

        if dsi < 10:
            burden_level = "low"
            burden_desc = "Debt easily serviced"
        elif dsi < 15:
            burden_level = "moderate"
            burden_desc = "Debt service manageable"
        elif dsi < 20:
            burden_level = "high"
            burden_desc = "Debt constraining spending"
        else:
            burden_level = "crisis"
            burden_desc = "Debt unsustainable, defaults likely"

        # Debt to income ratio
        dti = metrics.debt_to_income

        return {
            "debt_service_ratio": round(dsi, 1),
            "debt_to_income": round(dti, 1),
            "burden_level": burden_level,
            "description": burden_desc,
            "is_sustainable": dsi < 18 and dti < self.DEBT_TO_GDP_HIGH,
            "years_to_pay_off": dti / 10 if metrics.credit_impulse <= 0 else None,
        }

    def get_cycle_position_score(self, metrics: LeveragingMetrics) -> float:
        """
        Score 0-100 indicating position in debt cycle.

        0 = cycle bottom (max deleveraging)
        50 = mid cycle (healthy growth)
        100 = cycle peak (max leverage)
        """
        # Debt to income normalized (higher = closer to peak)
        dti_score = min(metrics.debt_to_income / 4, 100)

        # Credit impulse (accelerating = closer to peak)
        impulse_score = 50 + metrics.credit_impulse * 5
        impulse_score = max(0, min(100, impulse_score))

        # Debt service burden (high = closer to peak)
        ds_score = metrics.debt_service_to_income * 4

        # Weighted average
        score = dti_score * 0.4 + impulse_score * 0.3 + ds_score * 0.3

        return round(score, 1)

    def generate_cycle_report(self, metrics: LeveragingMetrics) -> Dict:
        """Generate comprehensive debt cycle analysis."""
        phase = self.identify_cycle_phase(metrics)
        burden = self.calculate_debt_burden(metrics)
        position = self.get_cycle_position_score(metrics)

        phase_info = self.PHASES.get(phase, {})

        return {
            "cycle_phase": phase,
            "phase_description": phase_info.get("description", ""),
            "risk_level": phase_info.get("risk_level", "unknown"),
            "position_in_cycle": position,
            "leverage_metrics": {
                "debt_to_gdp": round(metrics.debt_to_gdp, 1),
                "debt_to_income": round(metrics.debt_to_income, 1),
                "debt_service_ratio": round(metrics.debt_service_to_income, 1),
                "credit_impulse": round(metrics.credit_impulse, 1),
            },
            "debt_burden": burden,
            "implications": self._get_cycle_implications(phase, burden),
        }

    def _get_cycle_implications(self, phase: str, burden: Dict) -> List[str]:
        """Get implications based on cycle phase and burden."""
        implications = []

        if phase == "early":
            implications.append("Good time for risk assets, credit expansion beginning")
            implications.append("Monetary policy likely accommodative")

        elif phase == "bubble":
            implications.append("Asset bubbles likely forming")
            implications.append("Monitor for tightening signals")
            implications.append("Consider reducing leverage")

        elif phase == "top":
            implications.append("Cycle turning - defensive positioning warranted")
            implications.append("Credit tightening will impact risk assets")

        elif phase == "depression":
            implications.append("Deleveraging in progress - high volatility")
            implications.append("Policy response critical for recovery timing")

        elif phase == "reflation":
            implications.append("Policy supporting recovery")
            implications.append("Risk assets recovering but select carefully")

        elif phase == "late":
            implications.append("Cycle mature - watch for topping signals")
            implications.append("Policy likely tightening")

        # Add burden-specific implications
        if burden["burden_level"] in ["high", "crisis"]:
            implications.append("High debt burden constraining growth")

        return implications

    def forecast_cycle_transition(
        self,
        current_metrics: LeveragingMetrics,
        macro_assumptions: Dict,
        horizon_years: int = 2,
    ) -> Dict:
        """
        Forecast likely debt cycle path.

        Args:
            current_metrics: Current leverage metrics
            macro_assumptions: Dict with keys like 'gdp_growth', 'rates', 'inflation'
            horizon_years: Forecast horizon

        Returns:
            Forecast of cycle phase and metrics
        """
        gdp_growth = macro_assumptions.get("gdp_growth", 2.5)
        rate_change = macro_assumptions.get("rate_change", 0)
        inflation = macro_assumptions.get("inflation", 2.0)

        current_phase = self.identify_cycle_phase(current_metrics)

        # Simple projection
        projected_debt_to_income = current_metrics.debt_to_income
        projected_credit_growth = current_metrics.credit_impulse

        forecast = []
        for year in range(1, horizon_years + 1):
            # Update debt to income based on growth and credit assumptions
            debt_growth = projected_credit_growth + gdp_growth
            projected_debt_to_income = projected_debt_to_income * (1 + debt_growth / 100)

            # Update credit impulse (tends to mean revert)
            projected_credit_growth = projected_credit_growth * 0.8

            # Estimate new phase
            temp_metrics = LeveragingMetrics(
                debt_to_gdp=projected_debt_to_income / 2,
                debt_to_income=projected_debt_to_income,
                debt_service_to_income=current_metrics.debt_service_to_income + rate_change * year,
                credit_impulse=projected_credit_growth,
                private_credit_growth=projected_credit_growth,
                public_credit_growth=0,
                household_leverage=current_metrics.household_leverage,
                corporate_leverage=current_metrics.corporate_leverage,
            )

            phase = self.identify_cycle_phase(temp_metrics)

            forecast.append({
                "year": year,
                "projected_debt_to_income": round(projected_debt_to_income, 1),
                "projected_phase": phase,
                "risk_level": self.PHASES.get(phase, {}).get("risk_level", "unknown"),
            })

        return {
            "current_phase": current_phase,
            "forecast": forecast,
            "key_risks": self._identify_cycle_risks(current_phase, forecast),
        }

    def _identify_cycle_risks(self, current_phase: str, forecast: List[Dict]) -> List[str]:
        """Identify key risks based on cycle forecast."""
        risks = []

        # Check for phase transitions
        phases = [current_phase] + [f["projected_phase"] for f in forecast]

        if "top" in phases or "depression" in phases:
            risks.append("Cycle downturn likely within forecast horizon")

        if "bubble" in phases:
            risks.append("Asset bubble risk - watch for tightening")

        if current_phase == "late" and "depression" in phases:
            risks.append("Hard landing risk - rapid transition to deleveraging")

        return risks


def calculate_private_sector_balance(
    private_savings: float,
    private_investment: float,
) -> float:
    """
    Calculate private sector financial balance.

    Per sectoral balances: (S - I) + (T - G) + (M - X) = 0
    Positive = surplus (saving > investment)
    Negative = deficit (investment > saving)
    """
    return private_savings - private_investment


def assess_credit_availability(
    credit_spreads: float,
    lending_standards: str,  # tight, neutral, loose
    bank_capital_ratios: float,
) -> Dict:
    """
    Assess credit availability conditions.

    Returns assessment of credit supply/demand balance.
    """
    # Credit spread interpretation
    if credit_spreads < 150:
        spread_condition = "easy"
    elif credit_spreads < 250:
        spread_condition = "normal"
    else:
        spread_condition = "tight"

    # Combined assessment
    conditions = [spread_condition, lending_standards]

    if "tight" in conditions or conditions.count("tight") >= 1:
        availability = "restricted"
    elif "easy" in conditions and lending_standards == "loose":
        availability = "very_easy"
    else:
        availability = "normal"

    return {
        "spread_condition": spread_condition,
        "lending_standards": lending_standards,
        "credit_availability": availability,
        "is_accommodative": availability in ["normal", "very_easy"],
        "is_restrictive": availability == "restricted",
    }
