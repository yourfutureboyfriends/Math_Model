"""
Global Macro View

Orchestrates the complete global macro analysis pipeline.
"""

import logging
from datetime import datetime
from typing import Dict, Optional

from ..country_macro.us_macro_model import USMacroModel
from ..country_macro.euro_area_macro_model import EuroAreaMacroModel
from ..country_macro.china_macro_model import ChinaMacroModel
from ..country_macro.japan_macro_model import JapanMacroModel
from ..country_macro.uk_macro_model import UKMacroModel
from ..country_macro.emerging_markets_model import EmergingMarketsModel
from .global_macro_aggregator import GlobalMacroAggregator, GlobalMacroView

logger = logging.getLogger(__name__)


class GlobalMacroOrchestrator:
    """
    Orchestrates global macro analysis.

    Runs all country models and aggregates them into a global view.
    """

    def __init__(self, weight_scheme: str = "default"):
        """
        Initialize orchestrator.

        Args:
            weight_scheme: Weighting scheme for aggregation
        """
        self.weight_scheme = weight_scheme

        # Initialize country models
        self.country_models = {
            "US": USMacroModel(),
            "EuroArea": EuroAreaMacroModel(),
            "China": ChinaMacroModel(),
            "Japan": JapanMacroModel(),
            "UK": UKMacroModel(),
            "EmergingMarkets": EmergingMarketsModel(),
        }

        # Aggregator
        self.aggregator = GlobalMacroAggregator(weight_scheme=weight_scheme)

    def run_full_analysis(self, use_sample_data: bool = True) -> GlobalMacroView:
        """
        Run complete global macro analysis.

        Args:
            use_sample_data: Use sample data if True

        Returns:
            GlobalMacroView with complete analysis
        """
        logger.info("Starting global macro analysis...")

        # Run each country model
        for name, model in self.country_models.items():
            logger.info(f"Running {name} model...")

            if use_sample_data:
                model.macro_data = model.get_sample_data()

            # Generate output
            output = model.generate_output()
            self.aggregator.add_country_output(output)

            logger.info(f"  {name}: {output.current_regime} "
                       f"(G:{output.growth_momentum:+.1f}, I:{output.inflation_pressure:+.1f})")

        # Aggregate
        global_view = self.aggregator.aggregate()

        logger.info(f"Global regime: {global_view.global_regime}")
        logger.info(f"Regional divergence: {global_view.regional_divergence:.2f}")

        return global_view

    def generate_world_macro_report(self) -> Dict:
        """
        Generate complete world macro report.

        Returns:
            Report dictionary with all sections
        """
        view = self.run_full_analysis()

        # World Macro Map table
        world_map = self.aggregator.get_world_macro_map()

        return {
            "timestamp": datetime.now().isoformat(),
            "executive_summary": {
                "global_regime": view.global_regime.replace("_", " ").title(),
                "global_growth": view.global_growth_momentum,
                "global_inflation": view.global_inflation_pressure,
                "recession_risk": view.global_recession_risk,
                "narrative": view.narrative,
            },
            "world_macro_map": world_map.to_dict("records"),
            "regional_divergence": {
                "level": view.regional_divergence,
                "growth_dispersion": view.growth_dispersion,
                "inflation_dispersion": view.inflation_dispersion,
            },
            "country_details": {
                country: {
                    "regime": data.current_regime,
                    "growth": data.growth_momentum,
                    "growth_trend": data.growth_trend,
                    "inflation": data.inflation_pressure,
                    "inflation_trend": data.inflation_trend,
                    "policy": data.policy_stance,
                    "recession_risk": data.recession_risk,
                    "confidence": data.confidence_level,
                }
                for country, data in view.country_outputs.items()
            },
            "cross_asset_implications": view.cross_asset_signals,
            "main_risks": self._identify_main_risks(view),
        }

    def _identify_main_risks(self, view: GlobalMacroView) -> list:
        """Identify main risks to the global view."""
        risks = []

        if view.global_recession_risk > 0.3:
            risks.append(f"Elevated recession risk ({view.global_recession_risk:.0%})")

        if view.global_inflation_pressure > 1.0:
            risks.append("Persistent inflation pressure forcing tighter policy")

        if view.regional_divergence > 0.4:
            risks.append("Regional divergence limiting coordinated policy response")

        us = view.country_outputs.get("US")
        if us and us.policy_stance == "tight":
            risks.append("US policy tightening creating dollar strength headwinds")

        if not risks:
            risks.append("Unexpected geopolitical events or policy shifts")

        return risks


def get_current_global_macro_view() -> GlobalMacroView:
    """Convenience function to get current global macro view."""
    orchestrator = GlobalMacroOrchestrator()
    return orchestrator.run_full_analysis()
