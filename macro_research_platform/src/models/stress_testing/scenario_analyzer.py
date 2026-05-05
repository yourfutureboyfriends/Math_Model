"""
Stress Testing & Scenario Analysis Module

Implements scenario-based stress tests for macro regime model outputs.
Key principle: "Don't assume the current regime persists forever"

Scenarios:
- Historical replay (2008 GFC, 2020 COVID, etc.)
- Shock scenarios (inflation spike, growth collapse)
- Correlation breakdown
- Liquidity freeze

Based on:
- Federal Reserve CCAR methodology
- ECB stress testing framework
- Historical crisis dynamics
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ScenarioType(Enum):
    HISTORICAL = "historical"
    SHOCK = "shock"
    CORRELATION_BREAKDOWN = "correlation_breakdown"
    LIQUIDITY_FREEZE = "liquidity_freeze"


@dataclass
class ScenarioResult:
    """Result of a single scenario stress test."""
    scenario_name: str
    scenario_type: ScenarioType
    probability: float  # User-defined probability
    regime_shift: str  # Which regime this pushes toward

    # Impact on current positions
    equity_impact: float  # -1 to 1, negative = loss
    credit_impact: float
    rates_impact: float

    # Model response
    signal_changes: Dict[str, float]
    portfolio_drawdown: float

    # Mitigation
    suggested_adjustments: List[str]
    hedging_effectiveness: float


@dataclass
class StressTestReport:
    """Complete stress test results."""
    current_regime: str
    current_scores: Dict[str, float]

    # All scenarios run
    scenarios: List[ScenarioResult]

    # Summary metrics
    worst_case_drawdown: float
    average_drawdown: float
    most_likely_shift: str

    # Recommendations
    key_vulnerabilities: List[str]
    recommended_hedges: List[str]
    position_sizing_adjustment: float  # 0-1, reduce size by this much


class StressTestingModel:
    """
    Stress Testing Model

    Evaluates portfolio vulnerabilities under various scenarios
    and provides risk mitigation recommendations.
    """

    # Historical scenarios
    HISTORICAL_SCENARIOS = {
        "2008_GFC": {
            "description": "2008 Global Financial Crisis",
            "regime": "Stagflation",
            "equity_drop": -0.50,
            "credit_widening": 800,  # bps
            "rates_change": -3.0,  # percentage points
            "duration_months": 18,
        },
        "2020_COVID": {
            "description": "2020 COVID-19 Shock",
            "regime": "Slowdown",
            "equity_drop": -0.35,
            "credit_widening": 400,
            "rates_change": -1.5,
            "duration_months": 3,
        },
        "2022_INFLATION": {
            "description": "2022 Inflation Shock",
            "regime": "Stagflation",
            "equity_drop": -0.25,
            "credit_widening": 200,
            "rates_change": +2.5,
            "duration_months": 12,
        },
        "2013_TAPER": {
            "description": "2013 Taper Tantrum",
            "regime": "Slowdown",
            "equity_drop": -0.05,
            "credit_widening": 100,
            "rates_change": +1.0,
            "duration_months": 6,
        },
    }

    # Shock scenarios
    SHOCK_SCENARIOS = {
        "inflation_spike": {
            "description": "Sudden 2% inflation spike",
            "regime": "Stagflation",
            "equity_impact": -0.15,
            "credit_impact": -0.10,
            "rates_impact": +1.5,
            "probability": 0.15,
        },
        "recession_catalyst": {
            "description": "Growth contraction (PMI < 45)",
            "regime": "Slowdown",
            "equity_impact": -0.25,
            "credit_impact": -0.20,
            "rates_impact": -0.75,
            "probability": 0.20,
        },
        "credit_freeze": {
            "description": "Credit market freeze",
            "regime": "Stagflation",
            "equity_impact": -0.30,
            "credit_impact": -0.35,
            "rates_impact": -1.0,
            "probability": 0.10,
        },
        "policy_mistake": {
            "description": "Overtightening by central banks",
            "regime": "Slowdown",
            "equity_impact": -0.20,
            "credit_impact": -0.15,
            "rates_impact": +0.5,
            "probability": 0.15,
        },
    }

    def __init__(self):
        pass

    def run_historical_scenario(
        self,
        scenario_name: str,
        current_regime: str,
        current_sectors: Dict[str, str],
    ) -> ScenarioResult:
        """Run a historical scenario stress test."""

        if scenario_name not in self.HISTORICAL_SCENARIOS:
            raise ValueError(f"Unknown scenario: {scenario_name}")

        scenario = self.HISTORICAL_SCENARIOS[scenario_name]

        # Calculate impacts based on current positions
        equity_impact = scenario["equity_drop"]

        # Credit impact depends on sector exposures
        credit_exposure = sum(
            1 for s in current_sectors.values() if s == "Overweight"
        ) / max(len(current_sectors), 1)
        credit_impact = -scenario["credit_widening"] / 1000 * credit_exposure

        # Rates impact (inverse of rates move)
        rates_impact = scenario["rates_change"] * 0.1  # Simplified duration

        # Signal changes
        signal_changes = {
            "growth": -0.5 if "Slowdown" in scenario["regime"] or "Stagflation" in scenario["regime"] else 0.0,
            "inflation": 0.5 if "Stagflation" in scenario["regime"] else 0.0,
            "liquidity": -0.3,
            "risk": -0.5,
        }

        # Portfolio drawdown estimate
        portfolio_drawdown = abs(equity_impact) * 0.6 + abs(credit_impact) * 0.3 + abs(rates_impact) * 0.1

        # Suggested adjustments
        adjustments = []
        if scenario["regime"] == "Stagflation":
            adjustments.extend([
                "Increase commodity exposure",
                "Reduce duration risk",
                "Add inflation hedges (TIPS, gold)",
            ])
        elif scenario["regime"] == "Slowdown":
            adjustments.extend([
                "Increase duration",
                "Rotate to defensive sectors",
                "Add quality factor exposure",
            ])

        return ScenarioResult(
            scenario_name=scenario_name,
            scenario_type=ScenarioType.HISTORICAL,
            probability=0.05,  # Low for historical replay
            regime_shift=scenario["regime"],
            equity_impact=equity_impact,
            credit_impact=credit_impact,
            rates_impact=rates_impact,
            signal_changes=signal_changes,
            portfolio_drawdown=portfolio_drawdown,
            suggested_adjustments=adjustments,
            hedging_effectiveness=0.3 if scenario_name == "2008_GFC" else 0.5,
        )

    def run_shock_scenario(
        self,
        scenario_name: str,
        current_regime: str,
        current_sectors: Dict[str, str],
    ) -> ScenarioResult:
        """Run a shock scenario stress test."""

        if scenario_name not in self.SHOCK_SCENARIOS:
            raise ValueError(f"Unknown shock: {scenario_name}")

        shock = self.SHOCK_SCENARIOS[scenario_name]

        # Calculate portfolio drawdown
        portfolio_drawdown = abs(shock["equity_impact"]) * 0.6 + abs(shock["credit_impact"]) * 0.3

        # Signal changes
        signal_changes = {
            "growth": -0.3 if shock["regime"] in ["Slowdown", "Stagflation"] else 0.0,
            "inflation": 0.3 if shock["regime"] == "Stagflation" else -0.1 if shock["regime"] == "Slowdown" else 0.0,
            "liquidity": -0.4,
            "risk": -0.4,
        }

        # Adjustments specific to shock
        adjustments = []
        if scenario_name == "inflation_spike":
            adjustments = [
                "Add TIPS exposure",
                "Reduce real rate sensitive assets",
                "Consider commodity hedges",
            ]
        elif scenario_name == "recession_catalyst":
            adjustments = [
                "Increase cash allocation",
                "Add duration",
                "Defensive sector rotation",
            ]
        elif scenario_name == "credit_freeze":
            adjustments = [
                "Reduce credit exposure",
                "Increase liquidity buffer",
                "Add tail risk hedges",
            ]
        elif scenario_name == "policy_mistake":
            adjustments = [
                "Reduce rate-sensitive assets",
                "Add volatility exposure",
                "Quality over growth",
            ]

        return ScenarioResult(
            scenario_name=scenario_name,
            scenario_type=ScenarioType.SHOCK,
            probability=shock["probability"],
            regime_shift=shock["regime"],
            equity_impact=shock["equity_impact"],
            credit_impact=shock["credit_impact"],
            rates_impact=shock["rates_impact"],
            signal_changes=signal_changes,
            portfolio_drawdown=portfolio_drawdown,
            suggested_adjustments=adjustments,
            hedging_effectiveness=0.4,
        )

    def run_stress_test(
        self,
        current_regime: str,
        current_scores: Dict[str, float],
        current_sectors: Dict[str, str],
        historical_scenarios: Optional[List[str]] = None,
        shock_scenarios: Optional[List[str]] = None,
    ) -> StressTestReport:
        """
        Run complete stress test suite.

        Args:
            current_regime: Current macro regime
            current_scores: Current macro factor scores
            current_sectors: Current sector signals
            historical_scenarios: List of historical scenarios to run
            shock_scenarios: List of shock scenarios to run

        Returns:
            StressTestReport with all results
        """

        scenarios = []

        # Run historical scenarios
        if historical_scenarios is None:
            historical_scenarios = ["2008_GFC", "2020_COVID", "2022_INFLATION"]

        for hist in historical_scenarios:
            if hist in self.HISTORICAL_SCENARIOS:
                scenarios.append(
                    self.run_historical_scenario(hist, current_regime, current_sectors)
                )

        # Run shock scenarios
        if shock_scenarios is None:
            shock_scenarios = ["inflation_spike", "recession_catalyst", "credit_freeze"]

        for shock in shock_scenarios:
            if shock in self.SHOCK_SCENARIOS:
                scenarios.append(
                    self.run_shock_scenario(shock, current_regime, current_sectors)
                )

        # Calculate summary metrics
        drawdowns = [s.portfolio_drawdown for s in scenarios]
        worst_case = max(drawdowns) if drawdowns else 0.0
        average_dd = sum(drawdowns) / len(drawdowns) if drawdowns else 0.0

        # Most likely regime shift
        regime_counts = {}
        for s in scenarios:
            regime_counts[s.regime_shift] = regime_counts.get(s.regime_shift, 0) + 1
        most_likely_shift = max(regime_counts.keys(), key=lambda x: regime_counts[x]) if regime_counts else "Unknown"

        # Key vulnerabilities
        vulnerabilities = []
        if current_regime == "Goldilocks":
            vulnerabilities.append("Current optimism vulnerable to inflation shock or growth rollover")
        elif current_regime == "Reflation":
            vulnerabilities.append("Rising rates may accelerate, hurting duration-sensitive assets")
        elif current_regime == "Slowdown":
            vulnerabilities.append("Recession risk elevated; credit spreads may widen significantly")
        elif current_regime == "Stagflation":
            vulnerabilities.append("Both growth and inflation risks; limited safe havens")

        # Recommended hedges
        hedges = []
        if average_dd > 0.15:
            hedges.append("Consider equity index puts (5-10% OTM)")
        if any(s.regime_shift == "Stagflation" for s in scenarios):
            hedges.append("Add commodity or gold exposure")
            hedges.append("Inflation-linked bonds (TIPS)")
        if any(s.credit_impact < -0.15 for s in scenarios):
            hedges.append("CDX protection or reduce HY exposure")

        # Position sizing adjustment
        sizing_adjustment = min(0.3, worst_case * 0.5)  # Reduce up to 30%

        return StressTestReport(
            current_regime=current_regime,
            current_scores=current_scores,
            scenarios=scenarios,
            worst_case_drawdown=worst_case,
            average_drawdown=average_dd,
            most_likely_shift=most_likely_shift,
            key_vulnerabilities=vulnerabilities,
            recommended_hedges=hedges,
            position_sizing_adjustment=sizing_adjustment,
        )

    def get_stress_summary(self, report: StressTestReport) -> str:
        """Get plain-English stress test summary."""

        lines = [
            "## Stress Testing Results",
            "",
            f"**Current Regime:** {report.current_regime}",
            f"**Worst-Case Drawdown:** {report.worst_case_drawdown:.1%}",
            f"**Average Scenario Drawdown:** {report.average_drawdown:.1%}",
            f"**Most Likely Shift:** {report.most_likely_shift}",
            "",
            "### Key Vulnerabilities",
        ]

        for v in report.key_vulnerabilities:
            lines.append(f"- {v}")

        lines.extend(["", "### Scenario Impacts"])

        for s in report.scenarios:
            lines.append(
                f"- **{s.scenario_name}** → {s.regime_shift} "
                f"(DD: {s.portfolio_drawdown:.1%}, Prob: {s.probability:.0%})"
            )

        if report.recommended_hedges:
            lines.extend(["", "### Recommended Hedges"])
            for h in report.recommended_hedges:
                lines.append(f"- {h}")

        lines.extend([
            "",
            f"### Position Sizing",
            f"Consider reducing exposure by {report.position_sizing_adjustment:.0%} based on stress results."
        ])

        return "\n".join(lines)


def run_stress_test(
    current_regime: str,
    current_scores: Dict[str, float],
    current_sectors: Dict[str, str],
) -> StressTestReport:
    """Convenience function to run stress tests."""
    model = StressTestingModel()
    return model.run_stress_test(current_regime, current_scores, current_sectors)
