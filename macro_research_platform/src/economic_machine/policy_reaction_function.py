"""
Policy Reaction Function

Models central bank reaction to economic conditions.

Inspired by Bridgewater's approach to understanding policy-maker behavior:
- Central banks react to deviations in growth and inflation from targets
- Policy operates with lags, so forward-looking behavior matters
- The reaction function shifts based on policy regime/framework
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class PolicyReactionParameters:
    """Parameters for central bank reaction function.

    Default values approximate a dual-mandate central bank (Fed, ECB).
    """
    # Inflation response (Taylor coefficient)
    inflation_weight: float = 1.5  # How strongly to react to inflation gaps

    # Output/growth response
    output_gap_weight: float = 0.5  # How strongly to react to growth gaps

    # Employment response (US dual mandate)
    employment_weight: float = 1.0  # React to unemployment gaps

    # Neutral rate estimate
    neutral_rate: float = 2.5  # Estimated r* (percent)

    # Inflation target
    inflation_target: float = 2.0  # Target inflation (percent)

    # Maximum employment estimate (NAIRU)
    nairu: float = 4.0  # Non-accelerating inflation rate of unemployment

    # Policy smoothing (interest rate smoothing)
    smoothing: float = 0.0  # 0 = no smoothing, high values = gradualism

    # Forward-looking vs backward-looking
    forecast_horizon: int = 12  # Months ahead for policy reaction

    # Asymmetric response (easier to ease than hike?)
    asymmetry: float = 1.0  # 1.0 = symmetric, >1 = hikes faster than cuts

    # Financial conditions channel
    financial_conditions_weight: float = 0.3  # React to tightening/easing


@dataclass
class PolicyRegime:
    """Policy regime determines reaction function parameters."""
    name: str
    description: str
    parameters: PolicyReactionParameters
    active_periods: List[Tuple[str, Optional[str]]]  # (start, end) dates


class PolicyReactionFunction:
    """
    Model central bank policy reaction to economic conditions.

    Based on Taylor Rule and its variants, capturing:
    - Dual mandate: inflation and employment
    - Financial stability concerns
    - Policy regime changes over time
    """

    # Predefined regimes for major central banks
    REGIMES = {
        "volcker": PolicyRegime(
            name="Volcker Era",
            description="High inflation fighting, aggressive hikes",
            parameters=PolicyReactionParameters(
                inflation_weight=2.5,
                output_gap_weight=0.0,
                employment_weight=0.0,
                neutral_rate=4.0,
                inflation_target=4.0,  # Implicit, gradually lowered
            ),
            active_periods=[("1979-08", "1987-08")],
        ),
        "greenspan": PolicyRegime(
            name="Greenspan Era",
            description="The Great Moderation, gradualist approach",
            parameters=PolicyReactionParameters(
                inflation_weight=1.5,
                output_gap_weight=0.5,
                employment_weight=1.0,
                neutral_rate=3.0,
                smoothing=0.5,
            ),
            active_periods=[("1987-08", "2006-01")],
        ),
        "bernanke": PolicyRegime(
            name="Bernanke Era",
            description="Financial crisis response, zero lower bound",
            parameters=PolicyReactionParameters(
                inflation_weight=1.0,
                output_gap_weight=1.0,
                employment_weight=1.5,
                neutral_rate=2.0,
                smoothing=0.3,
            ),
            active_periods=[("2006-02", "2014-01")],
        ),
        "yellen": PolicyRegime(
            name="Yellen Era",
            description="Gradual normalization, employment focus",
            parameters=PolicyReactionParameters(
                inflation_weight=1.5,
                output_gap_weight=0.5,
                employment_weight=1.5,
                neutral_rate=2.5,
                smoothing=0.7,
            ),
            active_periods=[("2014-02", "2018-01")],
        ),
        "powell": PolicyRegime(
            name="Powell Era",
            description="Flexible average inflation targeting",
            parameters=PolicyReactionParameters(
                inflation_weight=2.0,
                output_gap_weight=0.5,
                employment_weight=1.5,
                neutral_rate=2.5,
                inflation_target=2.0,
                smoothing=0.5,
            ),
            active_periods=[("2018-02", None)],
        ),
        "draghi": PolicyRegime(
            name="Draghi ECB",
            description="Whatever it takes era",
            parameters=PolicyReactionParameters(
                inflation_weight=1.5,
                output_gap_weight=1.0,
                employment_weight=0.5,
                neutral_rate=1.5,
                inflation_target=2.0,
                smoothing=0.4,
            ),
            active_periods=[("2011-11", "2019-10")],
        ),
        "emergency": PolicyRegime(
            name="Emergency Easing",
            description="Crisis response, ignore inflation temporarily",
            parameters=PolicyReactionParameters(
                inflation_weight=0.0,
                output_gap_weight=3.0,
                employment_weight=3.0,
                neutral_rate=0.0,
                smoothing=0.0,
            ),
            active_periods=[],
        ),
    }

    def __init__(self, parameters: Optional[PolicyReactionParameters] = None):
        self.params = parameters or PolicyReactionParameters()

    def calculate_implied_rate(
        self,
        current_inflation: float,
        current_unemployment: float,
        estimated_output_gap: float = 0.0,
        financial_conditions_index: float = 0.0,
    ) -> float:
        """
        Calculate implied policy rate based on reaction function.

        Args:
            current_inflation: Current inflation rate (percent)
            current_unemployment: Current unemployment rate (percent)
            estimated_output_gap: Output gap as % of potential
            financial_conditions_index: FCI (positive = tight)

        Returns:
            Implied policy rate (percent)
        """
        p = self.params

        # Inflation gap
        inflation_gap = current_inflation - p.inflation_target

        # Employment gap (unemployment relative to NAIRU)
        employment_gap = p.nairu - current_unemployment  # Positive = tight labor

        # Taylor-style rule
        # r = r* + 1.5*(inflation - target) + 0.5*output_gap
        implied = (
            p.neutral_rate
            + p.inflation_weight * inflation_gap
            + p.output_gap_weight * estimated_output_gap
            + p.employment_weight * employment_gap
            + p.financial_conditions_weight * financial_conditions_index
        )

        return implied

    def calculate_policy_stance(
        self,
        current_rate: float,
        current_inflation: float,
        current_unemployment: float,
        estimated_output_gap: float = 0.0,
    ) -> Dict:
        """
        Assess current policy stance relative to reaction function.

        Returns:
            Dict with stance assessment and expected path
        """
        implied = self.calculate_implied_rate(
            current_inflation, current_unemployment, estimated_output_gap
        )

        gap = current_rate - implied

        # Determine stance
        if gap > 1.0:
            stance = "restrictive"
            stance_desc = "Policy is tight relative to economic conditions"
        elif gap > 0.25:
            stance = "slightly_restrictive"
            stance_desc = "Policy is moderately tight"
        elif gap < -1.0:
            stance = "accommodative"
            stance_desc = "Policy is very loose relative to economic conditions"
        elif gap < -0.25:
            stance = "slightly_accommodative"
            stance_desc = "Policy is moderately loose"
        else:
            stance = "neutral"
            stance_desc = "Policy is broadly appropriate"

        # Expected direction
        if gap > 0.5:
            expected = "easing"
        elif gap < -0.5:
            expected = "tightening"
        else:
            expected = "stable"

        return {
            "current_rate": current_rate,
            "implied_rate": round(implied, 2),
            "policy_gap": round(gap, 2),
            "stance": stance,
            "stance_description": stance_desc,
            "expected_direction": expected,
            "expected_change_12m": round(-gap * 0.5, 2),  # Partial adjustment
        }

    def forecast_policy_path(
        self,
        current_rate: float,
        inflation_forecast: List[float],
        unemployment_forecast: List[float],
        output_gap_forecast: Optional[List[float]] = None,
        horizon_months: int = 12,
    ) -> List[Dict]:
        """
        Forecast policy rate path given macro forecasts.

        Args:
            current_rate: Current policy rate
            inflation_forecast: Monthly inflation forecasts (annualized)
            unemployment_forecast: Monthly unemployment forecasts
            output_gap_forecast: Optional output gap forecasts
            horizon_months: Forecast horizon

        Returns:
            List of monthly policy forecasts
        """
        path = []
        prev_rate = current_rate
        p = self.params

        for t in range(horizon_months):
            # Get forecasts for this month (or repeat last if insufficient)
            inf = inflation_forecast[min(t, len(inflation_forecast) - 1)]
            unemp = unemployment_forecast[min(t, len(unemployment_forecast) - 1)]
            ogap = (output_gap_forecast or [0.0] * horizon_months)[
                min(t, len(output_gap_forecast or []) - 1)
            ]

            # Calculate implied rate
            implied = self.calculate_implied_rate(inf, unemp, ogap)

            # Apply smoothing (partial adjustment)
            if p.smoothing > 0:
                rate = prev_rate + (1 - p.smoothing) * (implied - prev_rate)
            else:
                rate = implied

            # Check for ZLB
            rate = max(rate, 0.0)

            path.append({
                "month": t + 1,
                "implied_rate": round(implied, 2),
                "policy_rate": round(rate, 2),
                "expected_change": round(rate - prev_rate, 2),
                "inflation": round(inf, 2),
                "unemployment": round(unemp, 2),
            })

            prev_rate = rate

        return path

    @staticmethod
    def get_regime_for_date(date_str: str) -> Optional[PolicyRegime]:
        """Get appropriate regime for a historical date."""
        from datetime import datetime

        dt = datetime.strptime(date_str[:7], "%Y-%m")

        for regime in PolicyReactionFunction.REGIMES.values():
            for start, end in regime.active_periods:
                start_dt = datetime.strptime(start, "%Y-%m")
                end_dt = datetime.strptime(end, "%Y-%m") if end else datetime.now()

                if start_dt <= dt <= end_dt:
                    return regime

        return None

    def generate_policy_report(
        self,
        current_rate: float,
        current_inflation: float,
        current_unemployment: float,
        estimated_output_gap: float = 0.0,
        financial_conditions: float = 0.0,
    ) -> Dict:
        """Generate comprehensive policy analysis report."""
        stance = self.calculate_policy_stance(
            current_rate, current_inflation, current_unemployment, estimated_output_gap
        )

        # Calculate neutral rate estimate
        neutral_rate = self.params.neutral_rate

        # Real rate calculation
        real_rate = current_rate - current_inflation

        return {
            "parameters": {
                "neutral_rate": neutral_rate,
                "inflation_target": self.params.inflation_target,
                "nairu": self.params.nairu,
                "inflation_weight": self.params.inflation_weight,
                "output_gap_weight": self.params.output_gap_weight,
            },
            "current_conditions": {
                "policy_rate": current_rate,
                "inflation": current_inflation,
                "unemployment": current_unemployment,
                "output_gap": estimated_output_gap,
                "real_rate": round(real_rate, 2),
            },
            "policy_assessment": stance,
            "key_insights": [
                f"Real policy rate is {real_rate:.2f}%",
                f"Policy gap of {stance['policy_gap']:.2f}% suggests {stance['stance']}",
                f"Expected direction: {stance['expected_direction']}",
            ],
        }


def estimate_optimal_policy_rate(
    inflation_target: float,
    current_inflation: float,
    unemployment_target: float,
    current_unemployment: float,
    neutral_rate: float = 2.5,
) -> Tuple[float, str]:
    """
    Quick estimate of appropriate policy rate using simple Taylor rule.

    Returns:
        (optimal_rate, explanation)
    """
    # Simple Taylor rule: r = r* + 1.5*(inflation - target) + 0.5*(NAIRU - unemployment)
    inflation_gap = current_inflation - inflation_target
    unemployment_gap = unemployment_target - current_unemployment

    rate = neutral_rate + 1.5 * inflation_gap + 0.5 * unemployment_gap

    explanation = (
        f"Taylor rule: {neutral_rate}% + 1.5×({current_inflation}-{inflation_target}) "
        f"+ 0.5×({unemployment_target}-{current_unemployment}) = {rate:.2f}%"
    )

    return rate, explanation


def assess_policy_restrictiveness(
    policy_rate: float,
    inflation: float,
    unemployment: float,
    output_gap: float = 0.0,
    neutral_rate: float = 2.5,
) -> Dict:
    """
    Assess how restrictive/accommodative current policy is.

    Returns:
        Dict with restrictiveness metrics
    """
    real_rate = policy_rate - inflation

    # Taylor-implied rate
    taylor_rate = neutral_rate + 1.5 * inflation + 0.5 * output_gap

    # Deviation from Taylor rule
    deviation = policy_rate - taylor_rate

    if deviation > 2.0:
        stance = "highly_restrictive"
    elif deviation > 0.5:
        stance = "restrictive"
    elif deviation > -0.5:
        stance = "neutral"
    elif deviation > -2.0:
        stance = "accommodative"
    else:
        stance = "highly_accommodative"

    return {
        "nominal_rate": policy_rate,
        "real_rate": round(real_rate, 2),
        "taylor_implied": round(taylor_rate, 2),
        "deviation_from_taylor": round(deviation, 2),
        "stance": stance,
        "is_restrictive": deviation > 0.5,
        "is_accommodative": deviation < -0.5,
    }
