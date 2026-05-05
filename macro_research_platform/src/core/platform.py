"""
Macro Research Platform - Main Orchestration

Main entry point for the Bridgewater-inspired macro research platform.

Coordinates all modules:
- Data: Point-in-time data management
- Economic Machine: Causal graph and transmission channels
- Nowcasting: Real-time macro estimation
- Signals: Systematic trading signals
- Portfolio: Construction and risk management
- Scenarios: Stress testing
- Research: Validation and postmortem
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .config import PlatformConfig

# Import all modules
from ..data.pit import (
    PointInTimeStore,
    DataQualityEngine,
    VintageDataManager,
    FredMDLoader,
)
from ..economic_machine import (
    CausalGraph,
    TransmissionChannelAnalyzer,
    PolicyReactionFunction,
    DebtCycleTracker,
)
from ..nowcasting import (
    DiffusionIndexModel,
    BusinessConditionsNowcast,
    MacroSurpriseTracker,
)
from ..signals import (
    SignalRegistry,
    GrowthInflationRegimeSignal,
    BusinessCyclePhaseSignal,
    PolicyStanceSignal,
)
from ..portfolio import (
    ExpectedReturnEngine,
    RiskBudgetingEngine,
    PositionSizingEngine,
)
from ..scenarios import ScenarioStressEngine
from ..research import (
    HypothesisRegistry,
    SignalValidator,
    PostmortemEngine,
)
from ..models.global_macro import (
    GlobalMacroOrchestrator,
    GlobalMacroView,
    get_current_global_macro_view,
)
from ..business import (
    BusinessObjectivesManager,
    RecommendationEngine,
    DecisionLog,
    InvestmentCommitteePackGenerator,
    WeeklyMacroProcess,
)
from ..research_library import ResearchLibrary

logger = logging.getLogger(__name__)


class MacroResearchPlatform:
    """
    Main platform orchestrating all components.

    Provides unified interface for:
    - Data management with PIT discipline
    - Macro analysis and regime detection
    - Signal generation and validation
    - Portfolio construction
    - Research tracking
    """

    def __init__(self, config: Optional[PlatformConfig] = None):
        """
        Initialize the platform.

        Args:
            config: Platform configuration (default if None)
        """
        self.config = config or PlatformConfig()
        self._setup_logging()

        # Initialize components
        self._init_data_components()
        self._init_economic_machine()
        self._init_global_macro()
        self._init_nowcasting()
        self._init_signals()
        self._init_portfolio()
        self._init_scenarios()
        self._init_research()
        self._init_business_layer()

        logger.info(f"Initialized {self.config.name} v{self.config.version}")

    def _setup_logging(self) -> None:
        """Configure logging."""
        log_level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        if self.config.log_file:
            Path(self.config.log_file).parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(self.config.log_file)
            file_handler.setLevel(log_level)
            logging.getLogger().addHandler(file_handler)

    def _init_data_components(self) -> None:
        """Initialize data management components."""
        self.pit_store = PointInTimeStore()
        self.data_quality = DataQualityEngine()
        self.vintage_manager = VintageDataManager(self.pit_store)
        self.fred_loader = FredMDLoader()

        logger.debug("Initialized data components")

    def _init_economic_machine(self) -> None:
        """Initialize economic machine components."""
        self.causal_graph = CausalGraph()
        self.transmission_analyzer = TransmissionChannelAnalyzer(self.causal_graph)
        self.policy_reaction = PolicyReactionFunction()
        self.debt_tracker = DebtCycleTracker()

        logger.debug("Initialized economic machine components")

    def _init_global_macro(self) -> None:
        """Initialize global macro framework with country models."""
        self.global_macro_orchestrator = GlobalMacroOrchestrator(
            weight_scheme="default"
        )
        self._cached_global_view: Optional[GlobalMacroView] = None

        logger.debug("Initialized global macro framework")

    def _init_nowcasting(self) -> None:
        """Initialize nowcasting components."""
        self.diffusion_model = DiffusionIndexModel()
        self.nowcast_engine = BusinessConditionsNowcast()
        self.surprise_tracker = MacroSurpriseTracker()

        logger.debug("Initialized nowcasting components")

    def _init_signals(self) -> None:
        """Initialize signal components."""
        self.signal_registry = SignalRegistry()

        # Register default signals
        self._register_default_signals()

        logger.debug("Initialized signal components")

    def _register_default_signals(self) -> None:
        """Register built-in signals."""
        # Regime-based signals
        regime_signal = GrowthInflationRegimeSignal(
            asset_universe=["equities", "rates", "credit", "commodities", "gold"]
        )
        self.signal_registry.register_signal(
            regime_signal,
            author="system",
            hypothesis="Assets perform differently based on growth/inflation regime",
        )

        cycle_signal = BusinessCyclePhaseSignal(
            asset_universe=["equities", "rates", "credit"]
        )
        self.signal_registry.register_signal(
            cycle_signal,
            author="system",
            hypothesis="Business cycle phase determines optimal asset allocation",
        )

        policy_signal = PolicyStanceSignal(
            asset_universe=["rates", "credit", "equities"]
        )
        self.signal_registry.register_signal(
            policy_signal,
            author="system",
            hypothesis="Policy stance deviation from neutral drives asset returns",
        )

    def _init_portfolio(self) -> None:
        """Initialize portfolio components."""
        self.expected_return_engine = ExpectedReturnEngine()
        self.risk_budgeting = RiskBudgetingEngine()
        self.position_sizing = PositionSizingEngine(
            target_volatility=self.config.portfolio.target_volatility,
            max_position_size=self.config.portfolio.max_position_size,
        )

        logger.debug("Initialized portfolio components")

    def _init_scenarios(self) -> None:
        """Initialize scenario components."""
        self.stress_engine = ScenarioStressEngine()

        logger.debug("Initialized scenario components")

    def _init_research(self) -> None:
        """Initialize research components."""
        self.hypothesis_registry = HypothesisRegistry()
        self.signal_validator = SignalValidator(
            min_sharpe=self.config.signals.min_sharpe_ratio,
            min_ic=self.config.signals.min_information_coefficient,
        )
        self.postmortem_engine = PostmortemEngine()

        logger.debug("Initialized research components")

    def _init_business_layer(self) -> None:
        """Initialize business layer components."""
        self.business_manager = BusinessObjectivesManager()
        self.recommendation_engine = RecommendationEngine()
        self.decision_log = DecisionLog()
        self.ic_pack_generator = InvestmentCommitteePackGenerator()
        self.research_library = ResearchLibrary()

        logger.debug("Initialized business layer")

    # =======================================================================
    # Public API Methods
    # =======================================================================

    def get_economic_regime(
        self,
        data: Dict[str, float],
        as_of_date: Optional[datetime] = None,
    ) -> Dict:
        """
        Determine current economic regime.

        Args:
            data: Dict of macro indicators
            as_of_date: Point-in-time date

        Returns:
            Regime classification and implications
        """
        # Calculate regime based on growth and inflation
        growth = data.get("growth", 0)
        inflation = data.get("inflation", 0)

        # Simple regime classification
        if growth > 2 and inflation > 3:
            regime = "reflation"
        elif growth > 2 and inflation <= 3:
            regime = "goldilocks"
        elif growth <= 2 and inflation > 3:
            regime = "stagflation"
        else:
            regime = "deflation"

        # Get transmission channel analysis
        node_states = {
            "growth": {"direction": "improving" if growth > 2 else "deteriorating", "zscore": (growth - 2) / 2},
            "headline_inflation": {"direction": "rising" if inflation > 2 else "falling", "zscore": (inflation - 2) / 2},
        }

        transmission_report = self.transmission_analyzer.generate_transmission_report(node_states)

        return {
            "regime": regime,
            "growth": growth,
            "inflation": inflation,
            "implications": self._get_regime_implications(regime),
            "active_channels": transmission_report.get("active_channels", []),
        }

    def _get_regime_implications(self, regime: str) -> List[str]:
        """Get asset allocation implications for regime."""
        implications = {
            "reflation": [
                "Commodities and inflation-linked bonds preferred",
                "Equities benefit but monitor tightening risk",
                "Nominal bonds vulnerable",
            ],
            "goldilocks": [
                "Equities optimal asset class",
                "Credit spreads can tighten further",
                "Moderate duration works well",
            ],
            "stagflation": [
                "Gold and real assets preferred",
                "Cash has option value",
                "Equities face earnings pressure",
            ],
            "deflation": [
                "Long duration bonds outperform",
                "Defensive equities preferred",
                "Credit risk requires caution",
            ],
        }
        return implications.get(regime, ["Mixed signals - neutral positioning"])

    def get_global_macro_view(self, use_cache: bool = True) -> GlobalMacroView:
        """
        Get comprehensive global macro view with country analysis.

        Args:
            use_cache: Use cached view if available

        Returns:
            GlobalMacroView with country breakdowns and aggregates
        """
        if use_cache and self._cached_global_view is not None:
            return self._cached_global_view

        view = self.global_macro_orchestrator.run_full_analysis()
        self._cached_global_view = view
        return view

    def get_world_macro_map(self) -> pd.DataFrame:
        """
        Generate World Macro Map table for dashboard display.

        Returns:
            DataFrame with countries/regions and their regime status
        """
        return self.global_macro_orchestrator.aggregator.get_world_macro_map()

    def get_global_regime(self) -> Dict:
        """
        Get current global regime classification.

        Returns:
            Dict with regime name, confidence, and narrative
        """
        view = self.get_global_macro_view()
        return {
            "regime": view.global_regime,
            "confidence": view.global_regime_confidence,
            "description": view.regime_description,
            "growth_momentum": view.global_growth_momentum,
            "inflation_pressure": view.global_inflation_pressure,
            "regional_divergence": view.regional_divergence,
            "narrative": view.narrative,
        }

    def get_country_analysis(self, country_code: str) -> Optional[Dict]:
        """
        Get detailed analysis for a specific country.

        Args:
            country_code: Country code (e.g., 'US', 'China', 'EuroArea')

        Returns:
            Dict with country macro details or None if not found
        """
        view = self.get_global_macro_view()
        country_data = view.country_outputs.get(country_code)

        if country_data is None:
            return None

        return {
            "country": country_data.country,
            "regime": country_data.current_regime,
            "growth_momentum": country_data.growth_momentum,
            "growth_trend": country_data.growth_trend,
            "inflation_pressure": country_data.inflation_pressure,
            "inflation_trend": country_data.inflation_trend,
            "policy_stance": country_data.policy_stance,
            "policy_gap": country_data.policy_gap,
            "recession_risk": country_data.recession_risk,
            "recession_probability_12m": country_data.recession_probability_12m,
            "confidence": country_data.confidence_level,
        }

    def get_nowcast(self, data: Dict[str, pd.Series]) -> Dict:
        """
        Get current business conditions nowcast.

        Args:
            data: Dict of indicator series

        Returns:
            Nowcast results with recession probability
        """
        return self.nowcast_engine.generate_nowcast_report(data)

    def calculate_signals(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: Optional[datetime] = None,
    ) -> Dict[str, Dict]:
        """
        Calculate all active signals.

        Args:
            data: Data dictionary
            as_of_date: Point-in-time date

        Returns:
            Dict of signal_name to output
        """
        return self.signal_registry.calculate_all_signals(data, as_of_date)

    def build_portfolio(
        self,
        expected_returns: Dict[str, float],
        cov_matrix: pd.DataFrame,
        constraints: Optional[Dict] = None,
    ) -> Dict:
        """
        Build optimal portfolio.

        Args:
            expected_returns: Dict of asset to expected return
            cov_matrix: Covariance matrix
            constraints: Optional constraints dict

        Returns:
            Portfolio weights and risk metrics
        """
        # Calculate risk parity weights
        weights = self.risk_budgeting.calculate_risk_parity_weights(
            cov_matrix.values,
            list(cov_matrix.index),
        )

        # Calculate risk report
        risk_report = self.risk_budgeting.generate_risk_report(weights, cov_matrix)

        return {
            "weights": weights,
            "risk_metrics": risk_report,
            "expected_return": sum(weights.get(a, 0) * expected_returns.get(a, 0) for a in weights),
        }

    def run_stress_test(
        self,
        portfolio_weights: Dict[str, float],
        scenario_names: Optional[List[str]] = None,
    ) -> Dict:
        """
        Run stress tests on portfolio.

        Args:
            portfolio_weights: Portfolio weights
            scenario_names: Specific scenarios to test

        Returns:
            Stress test results
        """
        if scenario_names:
            results = {}
            for name in scenario_names:
                scenario = self.stress_engine.scenarios.get(name)
                if scenario:
                    results[name] = self.stress_engine.run_stress_test(
                        portfolio_weights, scenario
                    )
            return results

        return self.stress_engine.run_all_stress_tests(portfolio_weights)

    def validate_signal(
        self,
        signal_name: str,
        signal_series: pd.Series,
        returns: pd.Series,
    ) -> Dict:
        """
        Validate a signal before production.

        Args:
            signal_name: Name of signal
            signal_series: Signal values
            returns: Asset returns

        Returns:
            Validation results
        """
        result = self.signal_validator.validate_signal(
            signal_name, signal_series, returns
        )

        return {
            "validated": result.validated,
            "sharpe_ratio": result.sharpe_ratio,
            "information_coefficient": result.information_coefficient,
            "win_rate": result.win_rate,
            "max_drawdown": result.max_drawdown,
            "failure_reasons": result.failure_reasons,
        }

    def get_platform_status(self) -> Dict:
        """Get overall platform status."""
        # Get global macro status if available
        global_macro_status = {}
        try:
            view = self.get_global_macro_view(use_cache=True)
            global_macro_status = {
                "countries_tracked": len(view.country_outputs),
                "global_regime": view.global_regime,
                "regional_divergence": view.regional_divergence,
            }
        except Exception:
            global_macro_status = {"status": "not_initialized"}

        return {
            "name": self.config.name,
            "version": self.config.version,
            "environment": self.config.environment,
            "components": {
                "data": {
                    "pit_series_count": len(self.pit_store.series),
                },
                "economic_machine": {
                    "nodes": len(self.causal_graph.nodes),
                    "edges": len(self.causal_graph.edges),
                },
                "global_macro": global_macro_status,
                "signals": {
                    "registered": len(self.signal_registry.signals),
                    "active": sum(1 for s in self.signal_registry.signals.values() if s.is_active),
                },
                "research": {
                    "hypotheses": len(self.hypothesis_registry.hypotheses),
                },
            },
            "status": "operational",
        }

    def generate_research_report(self) -> Dict:
        """Generate comprehensive research report."""
        return {
            "platform_summary": self.get_platform_status(),
            "signal_performance": self.signal_registry.get_performance_summary(),
            "hypothesis_status": self.hypothesis_registry.generate_hypothesis_report(),
            "timestamp": datetime.now(),
        }

    # =======================================================================
    # Business Layer Methods
    # =======================================================================

    def generate_recommendations(self) -> Dict:
        """
        Generate three-level recommendations (research, portfolio, action).

        Returns:
            Dict with all recommendations and decision IDs
        """
        # Get global view
        global_view = self.get_global_macro_view()

        # Get cross-asset signals
        cross_asset = global_view.cross_asset_signals

        # Get country regimes
        country_regimes = {
            country: data.current_regime
            for country, data in global_view.country_outputs.items()
        }

        # Get expected returns (would calculate from data)
        expected_returns = {
            "Technology": 0.02,
            "Healthcare": 0.015,
            "Financials": 0.01,
            "Energy": 0.025,
            "Utilities": 0.005,
            "Consumer_Discretionary": -0.01,
            "Industrials": 0.01,
        }

        sector_scores = {s: r * 10 for s, r in expected_returns.items()}

        # Generate recommendations
        recommendations = self.recommendation_engine.generate_all_recommendations(
            global_regime=global_view.global_regime,
            country_regimes=country_regimes,
            growth_momentum=global_view.global_growth_momentum,
            inflation_pressure=global_view.global_inflation_pressure,
            liquidity_conditions=global_view.global_liquidity_impulse,
            recession_probability=global_view.global_recession_risk,
            cross_asset_signals=cross_asset,
            sector_scores=sector_scores,
            expected_returns=expected_returns,
            credit_stress=0.25,
            volatility=15,
            data_mode="sample",  # Would detect from data status
        )

        # Log decisions
        decision_ids = []
        for rec_type, rec in recommendations.items():
            decision_id = self.decision_log.log_decision(
                recommendation=rec,
                global_regime=global_view.global_regime,
                growth_momentum=global_view.global_growth_momentum,
                inflation_pressure=global_view.global_inflation_pressure,
                recession_probability=global_view.global_recession_risk,
            )
            decision_ids.append(decision_id)

        return {
            "recommendations": recommendations,
            "decision_ids": decision_ids,
            "global_regime": global_view.global_regime,
            "timestamp": datetime.now().isoformat(),
        }

    def generate_ic_pack(self, output_dir: str = "outputs") -> str:
        """
        Generate the Investment Committee pack.

        Args:
            output_dir: Directory for output files

        Returns:
            Path to generated markdown file
        """
        # Get recommendations
        recs = self.generate_recommendations()
        recommendations = recs["recommendations"]

        # Get global view
        global_view = self.get_global_macro_view()
        global_dict = global_view.to_dict()

        # Build sector allocation
        sector_allocation = {
            "Technology": {"score": 0.2, "signal": "overweight"},
            "Healthcare": {"score": 0.15, "signal": "overweight"},
            "Energy": {"score": 0.25, "signal": "overweight"},
            "Consumer_Discretionary": {"score": -0.1, "signal": "underweight"},
        }

        # Build signal scorecard
        signal_scorecard = {
            name: {
                "category": "macro",
                "current_reading": "active",
                "confidence": 0.7,
                "research_support": "TBD",
            }
            for name in self.signal_registry.signals.keys()
        }

        # Data status
        data_status = {
            "data_mode": "sample",
            "last_update": datetime.now().isoformat(),
            "series_count": 0,
            "model_version": self.config.version,
            "freshness": "current",
        }

        return self.ic_pack_generator.generate(
            global_view=global_dict,
            recommendations=recommendations,
            signal_scorecard=signal_scorecard,
            data_status=data_status,
            sector_allocation=sector_allocation,
            cross_asset_signals=global_dict.get("cross_asset_signals", {}),
        )

    def run_weekly_process(self) -> Dict:
        """
        Run the complete weekly macro process.

        Returns:
            Dict with all outputs and paths
        """
        process = WeeklyMacroProcess(
            output_dir="outputs",
            use_cache=True
        )
        return process.run_full_process()

    def get_research_papers(self, category: Optional[str] = None) -> List[Dict]:
        """
        Get research papers from the library.

        Args:
            category: Optional category filter

        Returns:
            List of paper dictionaries
        """
        if category:
            from ..research_library import ResearchCategory
            cat = ResearchCategory(category)
            papers = self.research_library.get_papers_by_category(cat)
        else:
            papers = list(self.research_library.papers.values())

        return [{
            "id": p.id,
            "title": p.title,
            "authors": p.authors,
            "year": p.year,
            "business_use": p.business_use,
            "signal_created": p.signal_created,
            "implementation_status": p.implementation_status,
        } for p in papers]

    def get_decision_log(self, days: int = 30) -> List[Dict]:
        """
        Get recent decision log entries.

        Args:
            days: Number of days to look back

        Returns:
            List of decision log entries
        """
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)
        entries = self.decision_log.get_entries(start_date=cutoff)
        return [e.to_dict() for e in entries]


# Convenience function for quick start
def create_platform(
    config_file: Optional[Path] = None,
    environment: str = "development",
) -> MacroResearchPlatform:
    """
    Create a platform instance.

    Args:
        config_file: Optional path to config file
        environment: Environment type

    Returns:
        Configured MacroResearchPlatform instance
    """
    if config_file and config_file.exists():
        config = PlatformConfig.from_file(config_file)
    elif environment == "production":
        from .config import get_production_config
        config = get_production_config()
    else:
        from .config import get_default_config
        config = get_default_config()

    return MacroResearchPlatform(config)
