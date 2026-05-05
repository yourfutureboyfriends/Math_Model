"""
Weekly Macro Process

Orchestrates the weekly macro research workflow:
1. Data validation and freshness check
2. Macro feature engineering
3. Country macro models
4. Global macro aggregation
5. Signal generation
6. Transmission channel analysis
7. Expected return calculation
8. Conviction assessment
9. Risk and position sizing
10. Recommendation generation
11. Investment memo generation
12. IC pack generation
13. Decision logging
14. Output generation

This module provides the business-level orchestration on top of
the core platform functionality.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from ..models.global_macro import GlobalMacroOrchestrator
from ..portfolio.expected_return_engine import ExpectedReturnEngine
from ..signals.signal_registry import SignalRegistry
from .business_objectives import Recommendation, PlatformEffectiveness
from .recommendation_engine import RecommendationEngine
from .decision_log import DecisionLog
from .investment_committee_pack import InvestmentCommitteePackGenerator

if TYPE_CHECKING:
    from ..core.platform import MacroResearchPlatform

logger = logging.getLogger(__name__)


class WeeklyMacroProcess:
    """
    Orchestrates the weekly macro research and allocation workflow.

    This is the business-level entry point that coordinates:
    - Data pipeline
    - Model execution
    - Signal generation
    - Recommendation creation
    - Output generation
    """

    def __init__(self, platform=None, output_dir: str = "outputs", use_cache: bool = True):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.use_cache = use_cache

        # Initialize platform (passed in or created locally)
        if platform is None:
            # Local import to avoid circular dependency
            from ..core.platform import MacroResearchPlatform
            self.platform = MacroResearchPlatform()
        else:
            self.platform = platform

        # Initialize business components
        self.recommendation_engine = RecommendationEngine()
        self.decision_log = DecisionLog(output_dir)
        self.ic_pack_generator = InvestmentCommitteePackGenerator(output_dir)

        logger.info("Weekly Macro Process initialized")

    def run_full_process(self) -> Dict:
        """
        Run the complete weekly macro process.

        Returns:
            Dict with all outputs and paths
        """
        start_time = datetime.now()
        logger.info("Starting weekly macro process...")

        try:
            # Step 1: Data validation
            logger.info("Step 1: Validating data...")
            data_status = self._check_data_status()

            # Step 2: Get global macro view
            logger.info("Step 2: Generating global macro view...")
            global_view = self._generate_global_view()

            # Step 3: Generate signals
            logger.info("Step 3: Generating signals...")
            signals = self._generate_signals()

            # Step 4: Calculate expected returns
            logger.info("Step 4: Calculating expected returns...")
            expected_returns = self._calculate_expected_returns()

            # Step 5: Generate recommendations
            logger.info("Step 5: Generating recommendations...")
            recommendations = self._generate_recommendations(
                global_view, signals, expected_returns, data_status
            )

            # Step 6: Log decisions
            logger.info("Step 6: Logging decisions...")
            decision_ids = self._log_decisions(recommendations, global_view)

            # Step 7: Generate IC pack
            logger.info("Step 7: Generating IC pack...")
            ic_pack_path = self._generate_ic_pack(
                global_view, recommendations, signals, data_status, expected_returns
            )

            # Step 8: Generate outputs
            logger.info("Step 8: Generating outputs...")
            output_paths = self._generate_outputs(
                global_view, recommendations, signals, expected_returns
            )

            # Calculate platform effectiveness
            effectiveness = self._calculate_effectiveness(signals, recommendations)

            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"Weekly macro process completed in {duration:.1f}s")

            return {
                "status": "success",
                "duration_seconds": duration,
                "outputs": {
                    "ic_pack": ic_pack_path,
                    **output_paths,
                },
                "data_status": data_status,
                "global_view": global_view,
                "recommendations": recommendations,
                "effectiveness": effectiveness.to_dict(),
                "decision_ids": decision_ids,
            }

        except Exception as e:
            logger.error(f"Weekly macro process failed: {e}", exc_info=True)
            return {
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def _check_data_status(self) -> Dict:
        """Check data status and freshness."""
        status = self.platform.get_platform_status()

        # Determine data mode
        if status.get("components", {}).get("data", {}).get("pit_series_count", 0) > 0:
            data_mode = "live"
        else:
            data_mode = "sample"

        return {
            "data_mode": data_mode,
            "series_count": status.get("components", {}).get("data", {}).get("pit_series_count", 0),
            "active_signals": status.get("components", {}).get("signals", {}).get("active", 0),
            "last_update": datetime.now().isoformat(),
            "model_version": status.get("version", "1.0.0"),
            "freshness": "current",  # Would check actual data timestamps
        }

    def _generate_global_view(self) -> Dict:
        """Generate global macro view."""
        try:
            view = self.platform.get_global_macro_view(use_cache=self.use_cache)

            return {
                "global_regime": view.global_regime,
                "global_regime_confidence": view.global_regime_confidence,
                "global_growth_momentum": view.global_growth_momentum,
                "global_inflation_pressure": view.global_inflation_pressure,
                "regional_divergence": view.regional_divergence,
                "growth_dispersion": view.growth_dispersion,
                "inflation_dispersion": view.inflation_dispersion,
                "narrative": view.narrative,
                "cross_asset_signals": view.cross_asset_signals,
                "country_outputs": {
                    country: {
                        "regime": data.current_regime,
                        "growth": data.growth_momentum,
                        "inflation": data.inflation_pressure,
                        "recession_risk": data.recession_risk,
                    }
                    for country, data in view.country_outputs.items()
                },
                "timestamp": view.timestamp.isoformat() if hasattr(view, 'timestamp') else datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error generating global view: {e}")
            return {
                "global_regime": "unknown",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def _generate_signals(self) -> Dict:
        """Generate all signals."""
        try:
            # Get signals from registry
            registry = self.platform.signal_registry

            signals = {}
            for name, signal in registry.signals.items():
                signals[name] = {
                    "name": name,
                    "signal_type": signal.__class__.__name__,
                    "is_active": signal.is_active if hasattr(signal, 'is_active') else True,
                    "description": signal.description if hasattr(signal, 'description') else "",
                }

            return signals
        except Exception as e:
            logger.error(f"Error generating signals: {e}")
            return {}

    def _calculate_expected_returns(self) -> Dict[str, float]:
        """Calculate expected returns for sectors/assets."""
        # This would use the expected return engine
        # For now, return placeholder values
        return {
            "Technology": 0.02,
            "Healthcare": 0.015,
            "Financials": 0.01,
            "Energy": 0.025,
            "Utilities": 0.005,
            "Consumer_Discretionary": -0.01,
            "Industrials": 0.01,
        }

    def _generate_recommendations(
        self,
        global_view: Dict,
        signals: Dict,
        expected_returns: Dict[str, float],
        data_status: Dict
    ) -> Dict[str, Recommendation]:
        """Generate all three levels of recommendations."""
        # Prepare sector scores (placeholder)
        sector_scores = {sector: ret * 10 for sector, ret in expected_returns.items()}

        # Get cross-asset signals from global view
        cross_asset = global_view.get("cross_asset_signals", {})

        # Get country regimes
        country_regimes = {}
        for country, data in global_view.get("country_outputs", {}).items():
            country_regimes[country] = data.get("regime", "unknown")

        # Generate recommendations
        recommendations = self.recommendation_engine.generate_all_recommendations(
            global_regime=global_view.get("global_regime", "unknown"),
            country_regimes=country_regimes,
            growth_momentum=global_view.get("global_growth_momentum", 0),
            inflation_pressure=global_view.get("global_inflation_pressure", 0),
            liquidity_conditions=0,  # Would calculate from data
            recession_probability=0.2,  # Would calculate from data
            cross_asset_signals=cross_asset,
            sector_scores=sector_scores,
            expected_returns=expected_returns,
            credit_stress=0.25,  # Would calculate from data
            volatility=15,  # Would calculate from data
            data_mode=data_status.get("data_mode", "sample"),
        )

        return recommendations

    def _log_decisions(self, recommendations: Dict[str, Recommendation], global_view: Dict) -> List[str]:
        """Log all decisions."""
        decision_ids = []

        for rec_type, rec in recommendations.items():
            decision_id = self.decision_log.log_decision(
                recommendation=rec,
                global_regime=global_view.get("global_regime", ""),
                growth_momentum=global_view.get("global_growth_momentum"),
                inflation_pressure=global_view.get("global_inflation_pressure"),
                recession_probability=0.2,  # Would calculate
            )
            decision_ids.append(decision_id)

        return decision_ids

    def _generate_ic_pack(
        self,
        global_view: Dict,
        recommendations: Dict[str, Recommendation],
        signals: Dict,
        data_status: Dict,
        expected_returns: Dict
    ) -> str:
        """Generate the Investment Committee pack."""
        # Prepare sector allocation
        sector_allocation = {
            sector: {"score": score, "signal": "overweight" if score > 0.2 else "underweight" if score < -0.2 else "neutral"}
            for sector, score in expected_returns.items()
        }

        # Prepare signal scorecard
        signal_scorecard = {
            name: {
                "category": "macro",
                "current_reading": "active",
                "confidence": 0.7,
                "research_support": "TBD",
            }
            for name, signal in signals.items()
        }

        return self.ic_pack_generator.generate(
            global_view=global_view,
            recommendations=recommendations,
            signal_scorecard=signal_scorecard,
            data_status=data_status,
            sector_allocation=sector_allocation,
            cross_asset_signals=global_view.get("cross_asset_signals", {}),
        )

    def _generate_outputs(
        self,
        global_view: Dict,
        recommendations: Dict[str, Recommendation],
        signals: Dict,
        expected_returns: Dict[str, float]
    ) -> Dict[str, str]:
        """Generate all output files."""
        outputs = {}
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Generate recommendation summary
        rec_path = self.output_dir / f"latest_recommendation_summary.md"
        with open(rec_path, "w") as f:
            f.write("# Latest Recommendation Summary\n\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n\n")
            for rec_type, rec in recommendations.items():
                f.write(f"## {rec_type.replace('_', ' ').title()}\n\n")
                f.write(f"**Headline:** {rec.headline}\n\n")
                f.write(f"**Detail:** {rec.detail}\n\n")
                f.write(f"**Conviction:** {rec.conviction.value}\n\n")
                f.write(f"**Suggested Action:** {rec.suggested_action}\n\n---\n\n")
        outputs["recommendation_summary"] = str(rec_path)

        # Generate signal scorecard CSV
        scorecard_path = self.output_dir / f"latest_signal_scorecard.csv"
        with open(scorecard_path, "w", newline="") as f:
            import csv
            writer = csv.writer(f)
            writer.writerow(["Signal", "Category", "Status", "Confidence"])
            for name, signal in signals.items():
                writer.writerow([name, "macro", "active", 0.7])
        outputs["signal_scorecard"] = str(scorecard_path)

        # Generate expected returns CSV
        er_path = self.output_dir / f"latest_expected_return_scores.csv"
        with open(er_path, "w", newline="") as f:
            import csv
            writer = csv.writer(f)
            writer.writerow(["Sector", "Expected_Return", "Score"])
            for sector, ret in expected_returns.items():
                writer.writerow([sector, ret, ret * 10])
        outputs["expected_returns"] = str(er_path)

        return outputs

    def _calculate_effectiveness(
        self,
        signals: Dict,
        recommendations: Dict[str, Recommendation]
    ) -> PlatformEffectiveness:
        """Calculate platform effectiveness metrics."""
        high_conviction = sum(
            1 for r in recommendations.values()
            if r.conviction.value == "high"
        )

        return PlatformEffectiveness(
            timestamp=datetime.now(),
            active_signals=len(signals),
            high_conviction_signals=high_conviction,
            conflicting_signals=0,  # Would calculate from signal disagreements
            data_freshness_pct=0.8,  # Would calculate from actual data
            live_data_pct=0.5,
            recommendation_hit_rate=None,  # Would calculate from decision log
            avg_signal_decay_days=None,
            postmortems_completed=0,
            current_portfolio_risk_stance="neutral",
        )


# Convenience function
def run_weekly_process(output_dir: str = "outputs") -> Dict:
    """Run the weekly macro process."""
    process = WeeklyMacroProcess(output_dir)
    return process.run_full_process()
