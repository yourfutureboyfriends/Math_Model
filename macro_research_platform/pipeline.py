#!/usr/bin/env python3
"""
Pipeline Module - Orchestrates the complete macro model workflow.

STRICT MODE ENFORCEMENT:
- live mode: ONLY uses live data, NEVER falls back to sample
- sample mode: ONLY uses sample data, clearly labeled
- Commands:
  --mode refresh-live-data    Pull from FRED API, save to live/
  --mode check-freshness      Check data status
  --mode run-current          Run with live data (FAILS if missing)
  --mode run-sample           Run with sample data
  --mode dashboard            Start dashboard

Usage:
    python pipeline.py --mode refresh-live-data
    python pipeline.py --mode run-current
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import os
import pandas as pd

# Load .env file early
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
    print(f"Loaded .env file from {Path(__file__).parent / '.env'}")
except ImportError:
    print("Warning: python-dotenv not installed, .env file not loaded")
except Exception as e:
    print(f"Warning: Could not load .env: {e}")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Paths
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))


def check_fred_api_key() -> bool:
    """Check if FRED API key is configured."""
    key = os.getenv("FRED_API_KEY")
    if key:
        return True
    # Check .env file
    env_file = ROOT_DIR / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.startswith("FRED_API_KEY="):
                    return True
    return False


def get_data_mode() -> str:
    """Determine data mode from environment or default."""
    mode = os.getenv("MACRO_DATA_MODE", "sample")
    return mode.lower()


def print_data_status():
    """Print current data status."""
    from src.data import get_data_status

    status = get_data_status()

    print("=" * 60)
    print("DATA STATUS")
    print("=" * 60)

    if status["live_processed_exists"]:
        print(f"Live processed data: YES")
        if "live_latest_date" in status:
            latest = status["live_latest_date"]
            days_since = (datetime.now() - latest).days
            print(f"  Latest date: {latest.strftime('%Y-%m-%d')}")
            print(f"  Days since update: {days_since}")
            if days_since <= 45:
                print(f"  Status: CURRENT")
            elif days_since <= 90:
                print(f"  Status: ACCEPTABLE")
            else:
                print(f"  Status: STALE")
    else:
        print(f"Live processed data: NO")
        if status["live_raw_files"] > 0:
            print(f"  Raw files: {status['live_raw_files']} files")

    print(f"\nSample data exists: {'YES' if status['sample_exists'] else 'NO'}")

    print(f"\nFRED API Key: {'PRESENT' if check_fred_api_key() else 'MISSING'}")
    if not check_fred_api_key():
        print("  Set FRED_API_KEY in environment or .env file")


class Pipeline:
    """Main pipeline orchestrator."""

    def __init__(self, mode: str = "sample"):
        self.mode = mode
        self.run_timestamp = datetime.now()
        logger.info(f"=" * 60)
        logger.info(f"PIPELINE INITIALIZED - MODE: {mode.upper()}")
        logger.info(f"=" * 60)

    def step_refresh_live_data(self) -> bool:
        """Step 1: Refresh data from FRED API."""
        logger.info("STEP: Refresh Live Data from FRED")

        # Check FRED API key
        if not check_fred_api_key():
            logger.error("=" * 60)
            logger.error("FRED_API_KEY IS MISSING")
            logger.error("=" * 60)
            logger.error("Cannot fetch live data without FRED_API_KEY.")
            logger.error("Set it in .env or environment variables:")
            logger.error("  export FRED_API_KEY='your_key_here'")
            logger.error("")
            logger.error("Get a free API key from:")
            logger.error("  https://fred.stlouisfed.org/docs/api/api_key.html")
            return False

        # Import and run fetcher
        try:
            from src.data import refresh_fred_live_data

            logger.info("Fetching data from FRED API...")
            success, message = refresh_fred_live_data()

            if success:
                logger.info("=" * 60)
                logger.info("SUCCESS: Live data refreshed")
                logger.info("=" * 60)
                logger.info(message)

                # Now process the raw data
                self._process_raw_to_live()
                return True
            else:
                logger.error("=" * 60)
                logger.error("FAILED: Could not refresh live data")
                logger.error("=" * 60)
                logger.error(message)
                return False

        except Exception as e:
            logger.error(f"Error refreshing live data: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _process_raw_to_live(self) -> bool:
        """Process raw live files into processed live data."""
        from src.data.data_loader_live import RAW_LIVE_DIR, PROCESSED_LIVE_DIR, LiveDataLoader

        logger.info("Processing raw live data...")

        # Find most recent raw file
        raw_files = sorted(RAW_LIVE_DIR.glob("fred_live_*.parquet"), reverse=True)

        if not raw_files:
            logger.error("No raw live files found to process")
            return False

        latest_raw = raw_files[0]
        logger.info(f"Processing: {latest_raw.name}")

        try:
            # Use the loader's processing logic (includes completeness capping)
            loader = LiveDataLoader(mode="live")
            df = loader._process_raw_live_files([latest_raw])

            if df.empty:
                logger.error("Processing resulted in empty DataFrame")
                return False

            # Save processed
            processed_file = PROCESSED_LIVE_DIR / "macro_data.parquet"
            df.to_parquet(processed_file, compression="zstd")

            logger.info(f"Saved processed data: {processed_file}")
            logger.info(f"  Rows: {len(df)}")
            logger.info(f"  Columns: {len(df.columns)}")
            logger.info(f"  Date range: {df.index.min()} to {df.index.max()}")

            return True

        except Exception as e:
            logger.error(f"Failed to process raw data: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def step_run_model(self) -> bool:
        """Run the model with current mode."""
        logger.info(f"STEP: Running Model (mode={self.mode})")

        # Load data according to mode
        try:
            from src.data import load_model_data, DataModeError

            logger.info(f"Loading data in {self.mode} mode...")
            df, metadata = load_model_data(mode=self.mode)

            logger.info(f"Loaded {len(df)} rows from {metadata.get('source', 'unknown')}")
            logger.info(f"Latest date: {metadata.get('latest_date')}")
            logger.info(f"Data status: {metadata.get('data_status', 'unknown')}")

        except DataModeError as e:
            logger.error("=" * 60)
            logger.error("DATA LOADING FAILED")
            logger.error("=" * 60)
            logger.error(str(e))
            return False
        except Exception as e:
            logger.error(f"Unexpected error loading data: {e}")
            return False

        # Run transformations and model
        try:
            from src.features.macro_features import compute_all_transforms
            from src.models.macro_regime.regime_model import compute_group_scores, compute_score_directions, get_current_scores
            from src.models.macro_regime.classifier import classify_regime, get_regime_history
            from src.models.macro_regime.financial_conditions_model import compute_financial_conditions_from_data
            from src.models.macro_regime.inflation_shock_model import InflationShockModel
            from src.models.portfolio_construction.sector_allocation_model import ConfigDrivenSectorModel
            from src.models.business_conditions.business_conditions_model import BusinessConditionsModel
            from src.models.recession_risk.recession_model import RecessionModel
            from src.models.recession_risk.credit_stress_model import CreditStressModel
            from src.models.market_confirmation.trend_confirmation_model import MarketConfirmationModel
            from src.models.valuation_risk_premium.valuation_model import ValuationRiskPremiumModel
            from src.models.stress_testing.scenario_analyzer import StressTestingModel
            from src.models.ensemble.model_ensemble import ModelEnsemble

            logger.info("Running transformations...")
            df_trans = compute_all_transforms(df)

            logger.info("=" * 60)
            logger.info("RUNNING MODEL MODULES")
            logger.info("=" * 60)

            # 1. Base regime classification
            logger.info("[1/9] Computing macro regime scores...")
            scores_df = compute_group_scores(df_trans)
            directions = compute_score_directions(scores_df)
            scores = get_current_scores(scores_df)

            # Calculate 3-month changes for enhanced classification
            if len(scores_df) >= 4:
                growth_3m_change = scores["growth"] - scores_df["growth_score"].iloc[-4]
                inflation_3m_change = scores["inflation"] - scores_df["inflation_score"].iloc[-4]
            else:
                growth_3m_change = 0.0
                inflation_3m_change = 0.0

            logger.info(f"    Scores: Growth={scores['growth']:+.2f} (3m: {growth_3m_change:+.2f}), Inflation={scores['inflation']:+.2f} (3m: {inflation_3m_change:+.2f}), Liquidity={scores['liquidity']:+.2f}, Risk={scores['risk']:+.2f}")

            # 2. Business conditions nowcast
            logger.info("[2/9] Computing business conditions nowcast...")
            bc_model = BusinessConditionsModel()
            bc_result = bc_model.nowcast(df)
            confidence_val = 0.9 if bc_result.confidence == "high" else 0.7 if bc_result.confidence == "moderate" else 0.5
            logger.info(f"    Business conditions score: {bc_result.score:+.2f} ({bc_result.direction}, conf: {bc_result.confidence})")

            # 3. Recession risk
            logger.info("[3/9] Computing recession risk...")
            from src.models.recession_risk.recession_model import (
                compute_recession_probability, get_recession_risk_level
            )
            rec_prob_series = compute_recession_probability(df)
            current_rec_prob = rec_prob_series.iloc[-1] if not rec_prob_series.empty else 0.0
            rec_risk_level = get_recession_risk_level(current_rec_prob)
            logger.info(f"    Recession probability: {current_rec_prob:.1f}% ({rec_risk_level})")

            # 4. Credit stress
            logger.info("[4/9] Computing credit stress...")
            from src.models.recession_risk.credit_stress_model import compute_credit_stress_from_data
            cs_result = compute_credit_stress_from_data(df)
            if cs_result:
                logger.info(f"    Credit stress level: {cs_result.stress_level} (score: {cs_result.stress_score:.2f})")
            else:
                logger.info("    Credit stress: No data available")

            # 5. Financial conditions impulse
            logger.info("[5/9] Computing financial conditions...")
            fc_result = compute_financial_conditions_from_data(df)
            logger.info(f"    Financial conditions: {fc_result.category} (impulse: {fc_result.impulse_score:+.2f})")

            # 6. Inflation shock assessment
            logger.info("[6/9] Computing inflation shock risk...")
            from src.models.macro_regime.inflation_shock_model import compute_inflation_shock_from_data
            inf_result = compute_inflation_shock_from_data(df)
            if inf_result:
                is_shock = 1.0 if inf_result.regime == "shock" else 0.3 if inf_result.regime == "supply_led" else 0.0
                logger.info(f"    Inflation regime: {inf_result.regime} (core pressure: {inf_result.core_pressure:.2f})")
            else:
                logger.info("    Inflation shock: No data available")

            # 7. Enhanced regime classification with supporting indicators
            logger.info("[7/9] Enhanced regime classification...")
            from src.models.macro_regime.enhanced_classifier import EnhancedRegimeClassifier

            classifier = EnhancedRegimeClassifier()
            regime_result = classifier.classify(
                growth_score=scores["growth"],
                inflation_score=scores["inflation"],
                growth_3m_change=growth_3m_change,
                inflation_3m_change=inflation_3m_change,
                recession_probability=current_rec_prob,
                credit_stress_level=cs_result.stress_level if cs_result else None,
                financial_conditions_category=fc_result.category if fc_result else None,
            )

            regime = regime_result.regime
            logger.info(f"    Regime: {regime}")
            logger.info(f"    Growth: {regime_result.growth_state} ({regime_result.growth_direction})")
            logger.info(f"    Inflation: {regime_result.inflation_state} ({regime_result.inflation_direction})")
            logger.info(f"    Confidence: {regime_result.confidence} ({regime_result.confidence_score:.0%})")
            if regime_result.validation_warnings:
                logger.info(f"    Warnings: {regime_result.validation_warnings[0]}")

            # 8. Market confirmation
            logger.info("[8/9] Computing market confirmation...")
            mc_model = MarketConfirmationModel()
            mc_result = mc_model.confirm_regime(df, regime, scores)
            logger.info(f"    Market confirmation: {mc_result.overall_signal.value} (alignment: {mc_result.macro_market_alignment:.0%})")

            # 9. Valuation assessment
            logger.info("[9/9] Computing valuation assessment...")
            val_model = ValuationRiskPremiumModel()
            val_result = val_model.calculate_full_assessment(df)
            if val_result.equity_valuation:
                logger.info(f"    Equity valuation: {val_result.equity_valuation.level.value.replace('_', ' ')}")
            if val_result.credit_valuation:
                logger.info(f"    Credit valuation: {val_result.credit_valuation.level.value.replace('_', ' ')}")

            # Model Ensemble - combine all views
            logger.info("=" * 60)
            logger.info("COMPUTING MODEL ENSEMBLE")
            logger.info("=" * 60)

            from src.models.ensemble.model_ensemble import ModelOutput

            ensemble = ModelEnsemble()

            # Create ModelOutput for each model
            model_outputs = {}

            # Macro regime
            model_outputs["macro_regime"] = ModelOutput(
                model_name="Macro Regime",
                signal=regime,
                strength=0.85,
                confidence="high",
                drivers=[f"Growth: {directions.get('growth', 'unknown')}", f"Inflation: {directions.get('inflation', 'unknown')}"],
            )

            # Business conditions
            if bc_result:
                bc_conf = "high" if bc_result.confidence == "high" else "moderate" if bc_result.confidence == "moderate" else "low"
                model_outputs["business_conditions"] = ModelOutput(
                    model_name="Business Conditions Nowcast",
                    signal=bc_result.direction,
                    strength=0.7,
                    confidence=bc_conf,
                    drivers=bc_result.top_positive[:2] if bc_result.top_positive else [],
                )

            # Recession risk
            model_outputs["recession_risk"] = ModelOutput(
                model_name="Recession Risk",
                signal=rec_risk_level.lower().replace(" ", "_"),
                strength=current_rec_prob / 100,
                confidence="moderate" if current_rec_prob > 25 else "high",
                drivers=["Yield curve slope", "Credit spreads"],
            )

            # Credit stress
            if cs_result:
                model_outputs["credit_stress"] = ModelOutput(
                    model_name="Credit Stress",
                    signal=cs_result.stress_level,
                    strength=cs_result.stress_score,
                    confidence="moderate",
                )

            # Financial conditions
            if fc_result:
                model_outputs["financial_conditions"] = ModelOutput(
                    model_name="Financial Conditions",
                    signal=fc_result.category,
                    strength=abs(fc_result.impulse_score),
                    confidence="high" if fc_result.confidence > 0.7 else "moderate",
                )

            # Inflation
            if inf_result:
                inf_shock = 1.0 if inf_result.regime == "shock" else 0.3 if inf_result.regime == "supply_led" else 0.0
                model_outputs["inflation_pressure"] = ModelOutput(
                    model_name="Inflation Pressure",
                    signal="shock" if inf_shock > 0.3 else inf_result.regime,
                    strength=inf_shock,
                    confidence="moderate",
                )

            # Market confirmation
            if mc_result:
                model_outputs["market_confirmation"] = ModelOutput(
                    model_name="Market Confirmation",
                    signal=mc_result.overall_signal.value,
                    strength=mc_result.macro_market_alignment,
                    confidence="high" if mc_result.macro_market_alignment > 0.7 else "moderate",
                    concerns=mc_result.divergence_warnings[:2] if mc_result.divergence_warnings else [],
                )

            # Combine all outputs
            ensemble_result = ensemble.combine(
                outputs=model_outputs,
                data_freshness="current" if metadata.get("is_sample") is False else "sample",
                data_coverage=0.8,
            )

            logger.info(f"Ensemble final view: {ensemble_result.final_view}")
            logger.info(f"Ensemble confidence: {ensemble_result.confidence_level}")
            logger.info(f"Disagreement score: {ensemble_result.disagreement_score:.2f}")
            if ensemble_result.disagreeing_models:
                logger.info(f"Disagreeing models: {', '.join(ensemble_result.disagreeing_models)}")

            # Sector allocation with all context
            logger.info("=" * 60)
            logger.info("COMPUTING SECTOR ALLOCATION")
            logger.info("=" * 60)

            sector_model = ConfigDrivenSectorModel()
            cs_score = cs_result.stress_score if cs_result else 0.0
            sector_df = sector_model.score_all_sectors(
                regime=regime,
                growth_score=scores["growth"],
                liquidity_score=scores["liquidity"],
                credit_stress_score=cs_score,
            )

            # Convert to dict format
            sector_scores = dict(zip(sector_df["Sector"], sector_df["Score"]))
            sector_signals = dict(zip(sector_df["Sector"], sector_df["Signal"]))

            logger.info(f"Sector signals computed for {len(sector_df)} sectors")
            logger.info(f"Overweight: {len([s for s in sector_signals.values() if s == 'Overweight'])}")
            logger.info(f"Underweight: {len([s for s in sector_signals.values() if s == 'Underweight'])}")

            # Stress testing
            logger.info("=" * 60)
            logger.info("RUNNING STRESS TESTS")
            logger.info("=" * 60)

            stress_model = StressTestingModel()
            stress_result = stress_model.run_stress_test(
                current_regime=regime,
                current_scores=scores,
                current_sectors=sector_signals,
            )

            logger.info(f"Worst-case drawdown: {stress_result.worst_case_drawdown:.1%}")
            logger.info(f"Average drawdown: {stress_result.average_drawdown:.1%}")
            logger.info(f"Most likely regime shift: {stress_result.most_likely_shift}")
            if stress_result.key_vulnerabilities:
                logger.info(f"Key vulnerability: {stress_result.key_vulnerabilities[0]}")

            # Generate outputs with all model results
            logger.info("=" * 60)
            logger.info("GENERATING OUTPUTS")
            logger.info("=" * 60)

            self._generate_outputs(
                df=df,
                metadata=metadata,
                regime=regime,
                scores=scores,
                directions=directions,
                sector_scores=sector_scores,
                sector_signals=sector_signals,
                # Additional model outputs
                bc_result=bc_result,
                rec_prob=current_rec_prob,
                rec_risk_level=rec_risk_level,
                cs_result=cs_result,
                fc_result=fc_result,
                inf_result=inf_result,
                mc_result=mc_result,
                val_result=val_result,
                ensemble_result=ensemble_result,
                stress_result=stress_result,
                regime_result=regime_result,
            )

            # Run business layer on top of legacy outputs
            business_success = self.step_run_business_layer(
                df=df,
                metadata=metadata,
                regime=regime,
                scores=scores,
                directions=directions,
                sector_scores=sector_scores,
                sector_signals=sector_signals,
                bc_result=bc_result,
                rec_prob=current_rec_prob,
                rec_risk_level=rec_risk_level,
                cs_result=cs_result,
                fc_result=fc_result,
                inf_result=inf_result,
                mc_result=mc_result,
                val_result=val_result,
                ensemble_result=ensemble_result,
                stress_result=stress_result,
                regime_result=regime_result,
            )

            if business_success:
                logger.info("✅ Business layer completed successfully")
            else:
                logger.warning("⚠️ Business layer had issues but pipeline continuing")

            return True

        except Exception as e:
            logger.error(f"Model execution failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def step_run_business_layer(
        self,
        df: pd.DataFrame,
        metadata: Dict[str, Any],
        regime: str,
        scores: Dict[str, float],
        directions: Dict[str, str],
        sector_scores: Dict[str, float],
        sector_signals: Dict[str, str],
        bc_result=None,
        rec_prob=None,
        rec_risk_level=None,
        cs_result=None,
        fc_result=None,
        inf_result=None,
        mc_result=None,
        val_result=None,
        ensemble_result=None,
        stress_result=None,
        regime_result=None,
    ) -> bool:
        """
        Run the business layer on top of legacy model outputs.

        This connects the business layer (recommendation engine, IC pack, etc.)
        to the existing pipeline.
        """
        logger.info("=" * 60)
        logger.info("RUNNING BUSINESS LAYER")
        logger.info("=" * 60)

        try:
            # Import business layer components
            from src.business.business_integration_adapter import BusinessIntegrationAdapter
            from src.business.recommendation_engine import RecommendationEngine, ConvictionEngine, PositionSizingEngine
            from src.business.investment_committee_pack import InvestmentCommitteePackGenerator
            from src.business.decision_log import DecisionLog
            from src.portfolio.expected_return_engine import ExpectedReturnEngine

            # Step 1: Adapt legacy output to business context
            logger.info("[Business Layer] Adapting legacy model outputs...")
            adapter = BusinessIntegrationAdapter()

            business_context = adapter.adapt_pipeline_output(
                regime=regime,
                scores=scores,
                directions=directions,
                sector_scores=sector_scores,
                sector_signals=sector_signals,
                data_mode=self.mode,
                latest_data_date=metadata.get("latest_date"),
                metadata=metadata,
                ensemble_result=ensemble_result,
                bc_result=bc_result,
                cs_result=cs_result,
                fc_result=fc_result,
                inf_result=inf_result,
                mc_result=mc_result,
                val_result=val_result,
                stress_result=stress_result,
            )

            # Step 2: Run signal library
            logger.info("[Business Layer] Running signal library...")
            signal_registry = adapter.get_signal_registry()
            signal_count = len(signal_registry.signals)
            logger.info(f"  Signals registered: {signal_count}")

            # Step 3: Calculate expected returns
            logger.info("[Business Layer] Calculating expected returns...")
            er_engine = ExpectedReturnEngine()

            # Build signal scores for expected return calculation
            signal_scores = {}
            for name, signal in signal_registry.signals.items():
                # Map signals to asset classes with placeholder values
                # In production, this would calculate from actual signal values
                signal_scores[name] = self._map_signal_to_assets(signal, scores)

            expected_returns = er_engine.calculate_expected_returns(
                signals=signal_scores,
                asset_classes=list(sector_scores.keys()) + ["equities", "rates", "credit", "commodities", "fx"],
            )

            logger.info(f"  Expected returns calculated for {len(expected_returns)} assets")

            # Step 4: Run conviction engine
            logger.info("[Business Layer] Calculating conviction...")
            conviction_engine = ConvictionEngine()

            signal_score_dict = {name: 0.5 for name in signal_registry.signals.keys()}
            conviction, conviction_score = conviction_engine.calculate_conviction(
                signal_scores=signal_score_dict,
                data_quality_score=business_context["data_quality"]["score"],
                research_support_score=0.6,
                backtest_ic=0.15,
                market_confirmation=mc_result.macro_market_alignment > 0.5 if mc_result else False,
                model_disagreement_penalty=business_context["model_disagreement"],
            )

            logger.info(f"  Conviction: {conviction.value} (score: {conviction_score:.2f})")

            # Step 5: Run position sizing
            logger.info("[Business Layer] Calculating position sizing...")
            position_sizing_engine = PositionSizingEngine()

            position_sizes = {}
            for asset, exp_ret in expected_returns.items():
                size, multiplier = position_sizing_engine.calculate_position_size(
                    expected_return_score=exp_ret.expected_return,
                    conviction_score=conviction_score,
                    data_quality_score=business_context["data_quality"]["score"],
                    volatility=exp_ret.volatility_estimate,
                    data_mode=self.mode,
                    model_disagreement=business_context["model_disagreement"],
                    backtest_reliability=0.5,
                )
                position_sizes[asset] = {
                    "size": size.value,
                    "multiplier": multiplier,
                    "expected_return": exp_ret.expected_return,
                }

            logger.info(f"  Position sizes calculated for {len(position_sizes)} assets")

            # Step 6: Run recommendation engine
            logger.info("[Business Layer] Generating recommendations...")
            rec_engine = RecommendationEngine()

            # Prepare inputs for recommendation engine
            country_regimes = {}
            for country, data in business_context.get("country_outputs", {}).items():
                country_regimes[country] = data.get("regime", "unknown")

            recommendations = rec_engine.generate_all_recommendations(
                global_regime=regime,
                country_regimes=country_regimes,
                growth_momentum=scores.get("growth", 0),
                inflation_pressure=scores.get("inflation", 0),
                liquidity_conditions=scores.get("liquidity", 0),
                recession_probability=rec_prob if rec_prob is not None else 0.2,
                cross_asset_signals=business_context["cross_asset_view"],
                sector_scores=sector_scores,
                expected_returns={asset: er.expected_return for asset, er in expected_returns.items()},
                credit_stress=cs_result.stress_score if cs_result else 0.25,
                volatility=0.15,  # Would calculate from actual data
                data_mode=self.mode,
            )

            logger.info(f"  Recommendations generated: {len(recommendations)}")
            for rec_type, rec in recommendations.items():
                logger.info(f"    {rec_type}: {rec.headline[:50]}... (conviction: {rec.conviction.value})")
                # Update recommendation with business context BEFORE IC pack generation
                rec.data_mode = self.mode
                rec.data_freshness_score = business_context["data_quality"]["score"]

            # Step 7: Generate IC pack
            logger.info("[Business Layer] Generating Investment Committee pack...")
            ic_generator = InvestmentCommitteePackGenerator(output_dir="outputs")

            # Build sector allocation for IC pack
            sector_allocation_for_ic = {}
            for asset, size_data in position_sizes.items():
                if asset in sector_scores:
                    sector_allocation_for_ic[asset] = {
                        "score": sector_scores[asset],
                        "signal": sector_signals.get(asset, "neutral"),
                        "expected_return": size_data["expected_return"],
                        "position_size": size_data["size"],
                    }

            # Build signal scorecard
            signal_scorecard = {}
            for name, signal in signal_registry.signals.items():
                signal_scorecard[name] = {
                    "category": getattr(signal, 'category', 'macro'),
                    "current_reading": "active",
                    "confidence": 0.7,
                    "research_support": "Systematic signal",
                }

            ic_pack_path = ic_generator.generate(
                global_view={
                    "global_regime": regime,
                    "global_growth_momentum": scores.get("growth", 0),
                    "global_inflation_pressure": scores.get("inflation", 0),
                    "regional_divergence": 0.3,  # Would calculate
                    "narrative": f"{regime} regime with growth at {scores.get('growth', 0):+.2f}",
                },
                recommendations=recommendations,
                signal_scorecard=signal_scorecard,
                data_status=business_context["data_quality"],
                sector_allocation=sector_allocation_for_ic,
                cross_asset_signals=business_context["cross_asset_view"],
            )

            logger.info(f"  IC pack generated: {ic_pack_path}")

            # Step 8: Log decisions
            logger.info("[Business Layer] Logging decisions...")
            decision_log = DecisionLog(output_dir="outputs")

            decision_ids = []
            for rec_type, rec in recommendations.items():
                decision_id = decision_log.log_decision(
                    recommendation=rec,
                    global_regime=regime,
                    growth_momentum=scores.get("growth", 0),
                    inflation_pressure=scores.get("inflation", 0),
                    recession_probability=rec_prob if rec_prob is not None else 0.2,
                )
                decision_ids.append(decision_id)

            logger.info(f"  Decisions logged: {len(decision_ids)}")

            # Step 9: Export business layer outputs
            logger.info("[Business Layer] Exporting outputs...")
            self._export_business_outputs(
                recommendations=recommendations,
                expected_returns=expected_returns,
                position_sizes=position_sizes,
                signal_scorecard=signal_scorecard,
                conviction=conviction,
                conviction_score=conviction_score,
                data_mode=self.mode,
                latest_data_date=metadata.get("latest_date"),
            )

            logger.info("=" * 60)
            logger.info("BUSINESS LAYER COMPLETE")
            logger.info("=" * 60)
            logger.info(f"Signals generated: {signal_count}")
            logger.info(f"Recommendations generated: {len(recommendations)}")
            logger.info(f"Expected return scores: {len(expected_returns)}")
            logger.info(f"Position sizes calculated: {len(position_sizes)}")
            logger.info(f"IC pack generated: yes")
            logger.info(f"Decision log updated: yes")

            return True

        except Exception as e:
            logger.error(f"Business layer failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _map_signal_to_assets(self, signal, scores: Dict[str, float]) -> Dict[str, float]:
        """Map a signal to asset class scores based on signal type."""
        asset_universe = getattr(signal, 'asset_universe', ['equities'])
        signal_name = getattr(signal, 'name', 'unknown')

        # Map signal type to asset scores
        if 'growth' in signal_name.lower():
            base_score = scores.get('growth', 0)
        elif 'inflation' in signal_name.lower():
            base_score = scores.get('inflation', 0)
        elif 'momentum' in signal_name.lower():
            base_score = 0.3  # Placeholder
        elif 'credit' in signal_name.lower():
            base_score = -scores.get('risk', 0)  # Inverse of risk
        elif 'dollar' in signal_name.lower():
            base_score = 0.1  # Placeholder
        else:
            base_score = 0.0

        return {asset: base_score for asset in asset_universe}

    def _export_business_outputs(
        self,
        recommendations: Dict,
        expected_returns: Dict,
        position_sizes: Dict,
        signal_scorecard: Dict,
        conviction,
        conviction_score: float,
        data_mode: str,
        latest_data_date,
    ):
        """Export all business layer outputs to files."""
        outputs_dir = ROOT_DIR / "outputs"
        outputs_dir.mkdir(exist_ok=True)

        # 1. Export recommendation summary
        logger.info("  Exporting recommendation summary...")
        rec_path = outputs_dir / "latest_recommendation_summary.md"
        with open(rec_path, "w") as f:
            f.write("# Latest Recommendation Summary\n\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n")
            f.write(f"Data Mode: {data_mode.upper()}\n")
            if latest_data_date:
                f.write(f"Latest Data Date: {latest_data_date.strftime('%Y-%m-%d')}\n")
            f.write(f"Overall Conviction: {conviction.value.upper()} (score: {conviction_score:.2f})\n\n")

            # Add sample warning if applicable
            if data_mode == "sample":
                f.write("⚠️ **SAMPLE MODE:** These recommendations are for testing only.\n\n")

            for rec_type, rec in recommendations.items():
                f.write(f"## {rec_type.replace('_', ' ').title()}\n\n")
                f.write(f"**Headline:** {rec.headline}\n\n")
                f.write(f"**Detail:** {rec.detail}\n\n")
                f.write(f"**Conviction:** {rec.conviction.value.upper()}\n\n")
                f.write(f"**Position Size:** {rec.suggested_position_size.value.replace('_', ' ').title()}\n\n")
                f.write(f"**Supporting Signals:** {', '.join(rec.supporting_signals) if rec.supporting_signals else 'None'}\n\n")
                f.write(f"**Opposing Signals:** {', '.join(rec.opposing_signals) if rec.opposing_signals else 'None'}\n\n")
                f.write(f"**Risk to View:** {rec.risk_to_view}\n\n")
                f.write(f"**Data to Watch:** {', '.join(rec.data_to_watch) if rec.data_to_watch else 'None'}\n\n")
                f.write(f"**Business Relevance:** {rec.business_relevance}\n\n")
                f.write(f"**Suggested Action:** {rec.suggested_action}\n\n")
                f.write("---\n\n")

        logger.info(f"    Saved: {rec_path}")

        # 2. Export expected return scores
        logger.info("  Exporting expected return scores...")
        import csv
        er_path = outputs_dir / "latest_expected_return_scores.csv"
        with open(er_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "asset_or_sector",
                "expected_return_score",
                "volatility_estimate",
                "sharpe_estimate",
                "confidence",
                "signal_contributions",
                "interpretation",
            ])
            for asset, er in expected_returns.items():
                interpretation = "attractive" if er.sharpe_estimate > 0.5 else "unattractive" if er.sharpe_estimate < 0 else "neutral"
                writer.writerow([
                    asset,
                    f"{er.expected_return:.4f}",
                    f"{er.volatility_estimate:.4f}",
                    f"{er.sharpe_estimate:.2f}",
                    f"{er.confidence:.2f}",
                    str(er.signal_contributions),
                    interpretation,
                ])

        logger.info(f"    Saved: {er_path}")

        # 3. Export position sizing
        logger.info("  Exporting position sizing...")
        ps_path = outputs_dir / "latest_position_sizing.csv"
        with open(ps_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "asset_or_sector",
                "signal",
                "expected_return_score",
                "conviction",
                "data_quality",
                "volatility_assumption",
                "suggested_position_size",
                "position_bucket",
                "reason",
            ])
            for asset, size_data in position_sizes.items():
                if data_mode == "sample":
                    reason = "SAMPLE MODE - no real position recommended"
                else:
                    reason = f"Based on {size_data['multiplier']:.2f}x multiplier"

                writer.writerow([
                    asset,
                    size_data.get("signal", "neutral"),
                    f"{size_data['expected_return']:.4f}",
                    f"{conviction_score:.2f}",
                    "high" if data_mode == "live" else "sample",
                    "0.15",  # Would be actual if calculated
                    size_data["size"],
                    size_data["size"].replace("_", " ").title(),
                    reason,
                ])

        logger.info(f"    Saved: {ps_path}")

        # 4. Export signal scorecard
        logger.info("  Exporting signal scorecard...")
        ss_path = outputs_dir / "latest_signal_scorecard.csv"
        with open(ss_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["signal", "category", "status", "confidence", "research_support"])
            for name, data in signal_scorecard.items():
                writer.writerow([
                    name,
                    data.get("category", "macro"),
                    data.get("current_reading", "active"),
                    f"{data.get('confidence', 0.7):.0%}",
                    data.get("research_support", "TBD"),
                ])

        logger.info(f"    Saved: {ss_path}")

        # 5. Copy decision log to latest_decision_log.csv (already created by DecisionLog)
        import shutil
        decision_log_path = outputs_dir / "decision_log.csv"
        latest_decision_log_path = outputs_dir / "latest_decision_log.csv"
        if decision_log_path.exists():
            shutil.copy(decision_log_path, latest_decision_log_path)
            logger.info(f"    Saved: {latest_decision_log_path}")

    def _generate_outputs(
        self,
        df: pd.DataFrame,
        metadata: Dict[str, Any],
        regime: str,
        scores: Dict[str, float],
        directions: Dict[str, str],
        sector_scores: Dict[str, float],
        sector_signals: Dict[str, str],
        # Additional model results
        bc_result=None,
        rec_prob=None,
        rec_risk_level=None,
        cs_result=None,
        fc_result=None,
        inf_result=None,
        mc_result=None,
        val_result=None,
        ensemble_result=None,
        stress_result=None,
        regime_result=None,
    ):
        """Generate all outputs (legacy + business layer)."""
        from src.reporting.memo_generator import generate_detailed_memo
        from src.reporting.report_generator import export_all_reports
        from src.reporting.hedge_fund_style import generate_executive_summary
        from src.models.portfolio_construction.sector_allocation_model import get_sector_allocation_table as get_sector_table

        outputs_dir = ROOT_DIR / "outputs"
        outputs_dir.mkdir(exist_ok=True)

        # Generate base memo
        memo_text = generate_detailed_memo(regime, scores, directions, sector_signals)

        # Add data mode header
        is_sample = metadata.get("is_sample", True)
        latest_date = metadata.get("latest_date")

        if is_sample:
            memo_text = f"""**DATA MODE: SAMPLE DATA ONLY**

This output is based on sample data and should only be used to test the model pipeline.
Do not use for actual investment decisions.

---

{memo_text}"""
        elif latest_date and (datetime.now() - latest_date).days > 60:
            memo_text = f"""**DATA MODE: HISTORICAL VIEW (STALE)**

Based on data through {latest_date.strftime('%Y-%m-%d')}, the model historically pointed to the following view.
This is NOT a current investment recommendation. Data is {((datetime.now() - latest_date).days)} days old.

---

{memo_text}"""
        else:
            memo_text = f"""**DATA MODE: LIVE DATA**

The latest available data (as of {latest_date.strftime('%Y-%m-%d')}) points to the following view:

---

{memo_text}"""

        # Build enhanced report with model ensemble context
        report_sections = [memo_text]

        if ensemble_result:
            report_sections.append(f"""
---

## Model Ensemble View

**Consensus:** {ensemble_result.final_view}
**Confidence:** {ensemble_result.confidence_level}
**Disagreement Score:** {ensemble_result.disagreement_score:.2f}

*Agreeing Models:* {', '.join(ensemble_result.agreeing_models[:5])}
*Disagreeing Models:* {', '.join(ensemble_result.disagreeing_models[:3]) if ensemble_result.disagreeing_models else 'None'}
""")

        if rec_prob is not None:
            report_sections.append(f"""
---

## Recession Risk Assessment

**Probability:** {rec_prob:.1f}%
**Risk Level:** {rec_risk_level}
""")

        if bc_result:
            report_sections.append(f"""
---

## Business Conditions Nowcast

**Score:** {bc_result.score:+.2f}
**Direction:** {bc_result.direction}
**Confidence:** {bc_result.confidence}
**Top Positive Drivers:** {', '.join(bc_result.top_positive[:2]) if bc_result.top_positive else 'N/A'}
**Top Negative Drivers:** {', '.join(bc_result.top_negative[:2]) if bc_result.top_negative else 'N/A'}
""")

        if stress_result:
            report_sections.append(f"""
---

## Stress Testing Summary

**Worst-Case Drawdown:** {stress_result.worst_case_drawdown:.1%}
**Average Drawdown:** {stress_result.average_drawdown:.1%}
**Most Likely Shift:** {stress_result.most_likely_shift}
**Key Vulnerability:** {stress_result.key_vulnerabilities[0] if stress_result.key_vulnerabilities else 'None identified'}

*Suggested Position Sizing Adjustment:* Reduce exposure by {stress_result.position_sizing_adjustment:.0%}
""")

        full_report = '\n'.join(report_sections)

        # Export reports
        # Create sector table DataFrame from the sector_scores and sector_signals
        sector_table = pd.DataFrame([
            {"Sector": sector, "Score": score, "Signal": sector_signals.get(sector, "Neutral")}
            for sector, score in sector_scores.items()
        ])

        # Prepare additional metadata
        enhanced_metadata = {
            **metadata,
            "recession_probability": rec_prob,
            "recession_risk_level": rec_risk_level,
            "business_conditions_score": bc_result.score if bc_result else None,
            "ensemble_confidence": ensemble_result.confidence_level if ensemble_result else None,
            "ensemble_disagreement": ensemble_result.disagreement_score if ensemble_result else None,
            "stress_worst_drawdown": stress_result.worst_case_drawdown if stress_result else None,
        }

        exports = export_all_reports(
            regime=regime,
            scores=scores,
            directions=directions,
            sector_signals=sector_signals,
            sector_scores=sector_scores,
            sector_table=sector_table,
            scores_df=pd.DataFrame(),  # Simplified
            regime_series=pd.Series(),
            memo_text=full_report,
            metadata=enhanced_metadata,
        )

        logger.info(f"Generated outputs: {list(exports.keys())}")

        # Save comprehensive model results to JSON for dashboard
        import json
        model_results = {
            "timestamp": datetime.now().isoformat(),
            "data_mode": self.mode,
            "regime": regime,
            "scores": scores,
            "directions": directions,
            "ensemble": {
                "final_view": ensemble_result.final_view if ensemble_result else None,
                "confidence": ensemble_result.confidence_level if ensemble_result else None,
                "disagreement": ensemble_result.disagreement_score if ensemble_result else None,
                "agreeing_models": ensemble_result.agreeing_models if ensemble_result else [],
                "disagreeing_models": ensemble_result.disagreeing_models if ensemble_result else [],
            },
            "recession_risk": {
                "probability": rec_prob if rec_prob is not None else None,
                "risk_level": rec_risk_level if rec_risk_level is not None else None,
            },
            "business_conditions": {
                "score": bc_result.score if bc_result else None,
                "direction": bc_result.direction if bc_result else None,
                "confidence": bc_result.confidence if bc_result else None,
            },
            "credit_stress": {
                "level": cs_result.stress_level if cs_result else None,
                "stress_score": cs_result.stress_score if cs_result else None,
            },
            "financial_conditions": {
                "category": fc_result.category if fc_result else None,
                "impulse": fc_result.impulse_score if fc_result else None,
            },
            "regime_classification": {
                "regime": regime_result.regime if regime_result else None,
                "category": regime_result.regime_category if regime_result else None,
                "confidence": regime_result.confidence if regime_result else None,
                "confidence_score": regime_result.confidence_score if regime_result else None,
                "growth_state": regime_result.growth_state if regime_result else None,
                "growth_direction": regime_result.growth_direction if regime_result else None,
                "inflation_state": regime_result.inflation_state if regime_result else None,
                "inflation_direction": regime_result.inflation_direction if regime_result else None,
                "warnings": regime_result.validation_warnings if regime_result else [],
                "evidence": regime_result.supporting_evidence if regime_result else [],
            },
            "valuation": {
                "equity_level": val_result.equity_valuation.level.value if val_result and val_result.equity_valuation else None,
                "credit_level": val_result.credit_valuation.level.value if val_result and val_result.credit_valuation else None,
                "risk_premium": val_result.overall_risk_premium if val_result else None,
            },
            "stress_test": {
                "worst_drawdown": stress_result.worst_case_drawdown if stress_result else None,
                "average_drawdown": stress_result.average_drawdown if stress_result else None,
                "most_likely_shift": stress_result.most_likely_shift if stress_result else None,
            },
            "sector_signals": sector_signals,
            "sector_scores": sector_scores,
        }

        results_path = outputs_dir / "latest_model_results.json"
        with open(results_path, 'w') as f:
            json.dump(model_results, f, indent=2, default=str)

        logger.info(f"Saved comprehensive model results to {results_path}")

    def run(self, mode: str) -> bool:
        """Run the complete pipeline."""
        self.mode = mode

        if mode == "refresh-live-data":
            return self.step_refresh_live_data()

        elif mode == "check-freshness":
            print_data_status()
            return True

        elif mode == "run-current":
            # Check if live data exists first
            from src.data import get_data_status
            status = get_data_status()

            if not status["live_processed_exists"]:
                logger.error("=" * 60)
                logger.error("CANNOT RUN CURRENT MODE")
                logger.error("=" * 60)
                logger.error("No live data found. Run first:")
                logger.error("  python pipeline.py --mode refresh-live-data")
                return False

            # Set internal mode to "live" for data loading
            self.mode = "live"
            return self.step_run_model()

        elif mode == "run-sample":
            # Set internal mode to "sample" for data loading
            self.mode = "sample"
            return self.step_run_model()

        elif mode == "dashboard":
            import subprocess
            logger.info("Starting dashboard...")
            subprocess.run(["streamlit", "run", "dashboard.py"])
            return True

        else:
            logger.error(f"Unknown mode: {mode}")
            return False


def main():
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        description="Macro Regime Model Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Refresh live data from FRED
  python pipeline.py --mode refresh-live-data

  # Check data freshness
  python pipeline.py --mode check-freshness

  # Run with live data (fails if no live data)
  python pipeline.py --mode run-current

  # Run with sample data
  python pipeline.py --mode run-sample

  # Start dashboard
  python pipeline.py --mode dashboard
        """
    )

    parser.add_argument(
        "--mode",
        choices=["refresh-live-data", "check-freshness", "run-current", "run-sample", "dashboard"],
        required=True,
        help="Pipeline execution mode",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Run pipeline
    pipeline = Pipeline(mode=args.mode)
    success = pipeline.run(args.mode)

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
