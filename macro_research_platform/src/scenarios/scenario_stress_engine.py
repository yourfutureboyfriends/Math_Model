"""
Scenario Stress Engine

Implements scenario analysis for portfolio stress testing.

Scenarios:
- Historical scenarios (2008, 2020, etc.)
- Hypothetical macro shocks
- Probability-weighted scenarios
- Reverse stress testing
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class Scenario:
    """A stress test scenario."""
    name: str
    description: str
    shock_magnitude: Dict[str, float]  # Asset to shock %
    probability: float
    duration_months: int
    recovery_pattern: str  # V, L, U, etc.


@dataclass
class StressTestResult:
    """Result of a stress test."""
    scenario_name: str
    portfolio_loss: float
    max_drawdown: float
    var_95: float
    expected_shortfall: float
    worst_performers: List[Tuple[str, float]]
    hedging_effectiveness: Dict[str, float]


class ScenarioStressEngine:
    """
    Stress test portfolios against macro scenarios.

    Inspired by Bridgewater's approach to understanding
    how portfolios perform in different environments.
    """

    # Predefined historical scenarios
    HISTORICAL_SCENARIOS = {
        "2008_financial_crisis": Scenario(
            name="2008 Financial Crisis",
            description="Lehman Brothers collapse, global credit freeze",
            shock_magnitude={
                "equities": -0.50,
                "credit": -0.30,
                "high_yield": -0.40,
                "rates": 0.05,
                "commodities": -0.40,
                "emerging_markets": -0.55,
                "real_estate": -0.35,
            },
            probability=0.05,
            duration_months=18,
            recovery_pattern="L",
        ),
        "2020_covid_crash": Scenario(
            name="2020 COVID Crash",
            description="Pandemic-driven global shutdown",
            shock_magnitude={
                "equities": -0.35,
                "credit": -0.20,
                "high_yield": -0.25,
                "rates": -0.10,
                "commodities": -0.50,
                "emerging_markets": -0.40,
                "gold": 0.10,
            },
            probability=0.03,
            duration_months=3,
            recovery_pattern="V",
        ),
        "1999_tech_bubble": Scenario(
            name="1999 Tech Bubble",
            description="Dot-com bubble burst",
            shock_magnitude={
                "tech_equities": -0.70,
                "equities": -0.45,
                "rates": -0.15,
                "credit": 0.05,
            },
            probability=0.05,
            duration_months=30,
            recovery_pattern="L",
        ),
        "1970s_stagflation": Scenario(
            name="1970s Stagflation",
            description="High inflation, weak growth",
            shock_magnitude={
                "equities": -0.15,
                "nominal_bonds": -0.30,
                "tips": 0.05,
                "commodities": 0.50,
                "gold": 0.80,
            },
            probability=0.10,
            duration_months=60,
            recovery_pattern="L",
        ),
        "1997_asian_crisis": Scenario(
            name="1997 Asian Crisis",
            description="Currency crisis in emerging Asia",
            shock_magnitude={
                "emerging_markets": -0.60,
                "asia_equities": -0.70,
                "commodities": -0.30,
                "rates": -0.10,
            },
            probability=0.05,
            duration_months=12,
            recovery_pattern="U",
        ),
    }

    # Hypothetical macro scenarios
    MACRO_SCENARIOS = {
        "inflation_shock": Scenario(
            name="Inflation Shock",
            description="Inflation rises to 6% unexpectedly",
            shock_magnitude={
                "nominal_bonds": -0.15,
                "tips": 0.05,
                "equities": -0.10,
                "commodities": 0.20,
                "gold": 0.15,
            },
            probability=0.15,
            duration_months=12,
            recovery_pattern="U",
        ),
        "recession": Scenario(
            name="Recession",
            description="Global recession, earnings collapse",
            shock_magnitude={
                "equities": -0.30,
                "credit": -0.15,
                "high_yield": -0.20,
                "rates": -0.15,
                "commodities": -0.25,
            },
            probability=0.20,
            duration_months=12,
            recovery_pattern="U",
        ),
        "dollar_crisis": Scenario(
            name="USD Crisis",
            description="Dollar loses reserve status",
            shock_magnitude={
                "dollar": -0.20,
                "gold": 0.30,
                "commodities": 0.25,
                "emerging_markets": 0.15,
                "nominal_bonds": -0.10,
            },
            probability=0.05,
            duration_months=24,
            recovery_pattern="L",
        ),
        "geopolitical_shock": Scenario(
            name="Major Geopolitical Shock",
            description="War or major political disruption",
            shock_magnitude={
                "equities": -0.20,
                "commodities": 0.30,
                "energy": 0.50,
                "gold": 0.25,
                "rates": -0.10,
            },
            probability=0.08,
            duration_months=6,
            recovery_pattern="V",
        ),
    }

    def __init__(self):
        self.scenarios: Dict[str, Scenario] = {}
        self.results: Dict[str, StressTestResult] = {}

        # Load predefined scenarios
        self._load_predefined_scenarios()

    def _load_predefined_scenarios(self) -> None:
        """Load historical and macro scenarios."""
        for name, scenario in self.HISTORICAL_SCENARIOS.items():
            self.scenarios[name] = scenario

        for name, scenario in self.MACRO_SCENARIOS.items():
            self.scenarios[name] = scenario

    def add_custom_scenario(self, scenario: Scenario) -> None:
        """Add a custom scenario."""
        self.scenarios[scenario.name] = scenario
        logger.info(f"Added custom scenario: {scenario.name}")

    def run_stress_test(
        self,
        portfolio_weights: Dict[str, float],
        scenario: Scenario,
        asset_correlations: Optional[pd.DataFrame] = None,
    ) -> StressTestResult:
        """
        Run stress test for a single scenario.

        Args:
            portfolio_weights: Dict of asset to weight
            scenario: Scenario to test
            asset_correlations: Optional correlation matrix

        Returns:
            StressTestResult
        """
        # Calculate portfolio shock
        portfolio_shock = 0
        asset_shocks = {}

        for asset, weight in portfolio_weights.items():
            # Find applicable shock
            shock = scenario.shock_magnitude.get(asset, 0)

            # Apply shock
            asset_shocks[asset] = shock
            portfolio_shock += weight * shock

        # Add correlation effects if provided
        if asset_correlations is not None:
            portfolio_shock = self._apply_correlation_effects(
                portfolio_weights, asset_shocks, asset_correlations
            )

        # Calculate metrics
        max_dd = abs(portfolio_shock) * 1.5  # Estimate
        var_95 = abs(portfolio_shock) * 1.5  # Simplified
        es = abs(portfolio_shock) * 1.8  # Simplified

        # Worst performers
        worst = sorted(asset_shocks.items(), key=lambda x: x[1])[:3]

        # Calculate hedging effectiveness (simplified)
        hedging = self._estimate_hedging_effectiveness(
            portfolio_weights, scenario.shock_magnitude
        )

        result = StressTestResult(
            scenario_name=scenario.name,
            portfolio_loss=round(portfolio_shock, 4),
            max_drawdown=round(max_dd, 4),
            var_95=round(var_95, 4),
            expected_shortfall=round(es, 4),
            worst_performers=worst,
            hedging_effectiveness=hedging,
        )

        self.results[scenario.name] = result
        return result

    def _apply_correlation_effects(
        self,
        weights: Dict[str, float],
        shocks: Dict[str, float],
        correlations: pd.DataFrame,
    ) -> float:
        """Apply correlation effects to shocks."""
        # Simplified: increase shock magnitude for high correlations
        portfolio_shock = 0

        for asset, weight in weights.items():
            base_shock = shocks.get(asset, 0)

            # Find correlated assets
            if asset in correlations.index:
                correlations_with_others = correlations.loc[asset].abs().mean()
                # Increase shock if high correlations
                adjusted_shock = base_shock * (1 + correlations_with_others * 0.5)
            else:
                adjusted_shock = base_shock

            portfolio_shock += weight * adjusted_shock

        return portfolio_shock

    def _estimate_hedging_effectiveness(
        self,
        weights: Dict[str, float],
        shocks: Dict[str, float],
    ) -> Dict[str, float]:
        """Estimate effectiveness of different hedges."""
        # Test different hedge instruments
        hedges = {}

        # Long bonds hedge
        bond_shock = shocks.get("nominal_bonds", 0)
        bond_hedge = -bond_shock * 0.5  # Assume 50% bond allocation

        # Gold hedge
        gold_shock = shocks.get("gold", 0)
        gold_hedge = gold_shock * 0.1  # Assume 10% gold allocation

        # VIX/hedge funds
        vix_hedge = 0.15  # Rough estimate

        return {
            "nominal_bonds": round(bond_hedge, 4),
            "gold": round(gold_hedge, 4),
            "volatility_hedge": round(vix_hedge, 4),
        }

    def run_all_stress_tests(
        self,
        portfolio_weights: Dict[str, float],
        asset_correlations: Optional[pd.DataFrame] = None,
    ) -> Dict[str, StressTestResult]:
        """
        Run stress tests for all scenarios.

        Args:
            portfolio_weights: Portfolio weights
            asset_correlations: Asset correlations

        Returns:
            Dict of scenario name to result
        """
        results = {}

        for name, scenario in self.scenarios.items():
            result = self.run_stress_test(portfolio_weights, scenario, asset_correlations)
            results[name] = result

        return results

    def calculate_expected_shortfall(
        self,
        portfolio_weights: Dict[str, float],
        percentile: float = 0.95,
    ) -> float:
        """
        Calculate Expected Shortfall (CVaR) across scenarios.

        Args:
            portfolio_weights: Portfolio weights
            percentile: Percentile for ES calculation

        Returns:
            Expected shortfall
        """
        # Run all scenarios
        results = self.run_all_stress_tests(portfolio_weights)

        # Get losses
        losses = [r.portfolio_loss for r in results.values()]

        # Weight by scenario probability
        probabilities = [self.scenarios[name].probability for name in results.keys()]

        # Normalize probabilities
        total_prob = sum(probabilities)
        if total_prob == 0:
            return 0

        normalized_probs = [p / total_prob for p in probabilities]

        # Calculate weighted losses
        weighted_losses = list(zip(losses, normalized_probs))
        weighted_losses.sort(key=lambda x: x[0])  # Sort by loss

        # Calculate cumulative probability
        cumulative = 0
        tail_losses = []
        for loss, prob in weighted_losses:
            cumulative += prob
            if cumulative >= 1 - percentile:
                tail_losses.append(loss)

        if tail_losses:
            return np.mean(tail_losses)
        return min(losses)

    def reverse_stress_test(
        self,
        portfolio_weights: Dict[str, float],
        target_loss: float = 0.20,
    ) -> List[Scenario]:
        """
        Find scenarios that would cause target loss.

        Reverse stress testing: "What would it take to lose X%?"

        Args:
            portfolio_weights: Portfolio weights
            target_loss: Target portfolio loss

        Returns:
            List of scenarios causing that loss
        """
        results = self.run_all_stress_tests(portfolio_weights)

        # Find scenarios with loss >= target
        severe_scenarios = [
            self.scenarios[name]
            for name, result in results.items()
            if abs(result.portfolio_loss) >= target_loss
        ]

        return severe_scenarios

    def generate_stress_report(
        self,
        portfolio_weights: Dict[str, float],
    ) -> Dict:
        """Generate comprehensive stress test report."""
        results = self.run_all_stress_tests(portfolio_weights)

        # Worst case
        worst_result = min(results.values(), key=lambda r: r.portfolio_loss)

        # Probability-weighted expected loss
        expected_loss = sum(
            r.portfolio_loss * self.scenarios[name].probability
            for name, r in results.items()
        ) / sum(s.probability for s in self.scenarios.values())

        # Tail scenarios (95th percentile worst)
        losses = sorted([r.portfolio_loss for r in results.values()])
        tail_threshold_idx = int(len(losses) * 0.05)
        tail_scenarios = [
            name for name, r in results.items()
            if r.portfolio_loss <= losses[tail_threshold_idx]
        ]

        return {
            "summary": {
                "worst_scenario": worst_result.scenario_name,
                "worst_loss": worst_result.portfolio_loss,
                "probability_weighted_expected_loss": round(expected_loss, 4),
                "scenarios_tested": len(results),
            },
            "scenario_results": {
                name: {
                    "loss": r.portfolio_loss,
                    "max_drawdown": r.max_drawdown,
                    "var_95": r.var_95,
                    "worst_performers": [a for a, _ in r.worst_performers],
                }
                for name, r in results.items()
            },
            "tail_risk_scenarios": tail_scenarios,
            "hedging_recommendations": worst_result.hedging_effectiveness,
        }


def monte_carlo_stress_test(
    portfolio_weights: Dict[str, float],
    asset_returns: pd.DataFrame,
    n_simulations: int = 1000,
    shock_multiplier: float = 2.0,
) -> Dict:
    """
    Monte Carlo stress test using historical returns.

    Args:
        portfolio_weights: Portfolio weights
        asset_returns: Historical returns DataFrame
        n_simulations: Number of simulations
        shock_multiplier: Multiplier for stress scenarios

    Returns:
        Stress test statistics
    """
    # Calculate historical portfolio returns
    portfolio_returns = pd.Series(0, index=asset_returns.index)
    for asset, weight in portfolio_weights.items():
        if asset in asset_returns.columns:
            portfolio_returns += asset_returns[asset] * weight

    # Find worst periods
    rolling_dd = portfolio_returns.rolling(63).apply(  # 3 months
        lambda x: (1 + x).prod() - 1
    )
    worst_periods = rolling_dd.nsmallest(int(n_simulations * 0.05))

    # Simulate stressed returns
    stressed_returns = []
    for _ in range(n_simulations):
        # Sample from worst periods
        if len(worst_periods) > 0:
            sample_loss = np.random.choice(worst_periods.values)
            stressed_returns.append(sample_loss * shock_multiplier)
        else:
            stressed_returns.append(0)

    return {
        "mean_stressed_loss": np.mean(stressed_returns),
        "worst_5_percent": np.percentile(stressed_returns, 5),
        "worst_1_percent": np.percentile(stressed_returns, 1),
        "probability_of_major_loss": sum(1 for r in stressed_returns if r < -0.20) / n_simulations,
    }
