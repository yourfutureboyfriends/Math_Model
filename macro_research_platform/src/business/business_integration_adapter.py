"""
Business Integration Adapter

Converts legacy pipeline outputs into the format required by the business layer.
This allows the existing pipeline to feed into the business layer without
duplicating logic or changing the legacy model code.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

import pandas as pd
import numpy as np

from ..signals.signal_registry import SignalRegistry
from ..signals import (
    TimeSeriesMomentumSignal,
    CrossAssetMomentumSignal,
    TrendFollowingSignal,
    GrowthDiffusionSignal,
    InflationDiffusionSignal,
    CreditStressSignal,
    GlobalLiquidityPressureSignal,
    PolicyUncertaintySignal,
    CAPESignal,
    YieldGapSignal,
    TermPremiumCarrySignal,
    FXCarrySignal,
    DollarCycleSignal,
    BusinessConditionsSignal,
    InflationMomentumSignal,
    CreditImpulseSignal,
    GlobalUncertaintySignal,
    VolatilityUncertaintySignal,
)

logger = logging.getLogger(__name__)


class BusinessIntegrationAdapter:
    """
    Adapter that converts legacy pipeline outputs to business layer format.

    Takes:
    - regime classification
    - macro scores
    - sector allocation
    - data mode
    - latest data date
    - confidence scores

    Returns:
    - business_context dictionary ready for business layer consumption
    """

    def __init__(self):
        self.signal_registry = SignalRegistry()
        self._register_default_signals()

    def _register_default_signals(self) -> None:
        """Register the core signals for the business layer."""
        signals_to_register = [
            # Momentum signals
            TimeSeriesMomentumSignal(),
            CrossAssetMomentumSignal(),
            TrendFollowingSignal(),

            # Macro signals
            GrowthDiffusionSignal(),
            InflationDiffusionSignal(),
            CreditStressSignal(),
            GlobalLiquidityPressureSignal(),
            PolicyUncertaintySignal(),

            # Valuation signals
            CAPESignal(),
            YieldGapSignal(),

            # Carry signals
            TermPremiumCarrySignal(),
            FXCarrySignal(),

            # Dollar signals
            DollarCycleSignal(),
        ]

        for signal in signals_to_register:
            self.signal_registry.register_signal(
                signal,
                author="system",
                hypothesis=f"Systematic {signal.name} signal",
            )

        logger.info(f"Registered {len(signals_to_register)} signals in adapter")

    def adapt_pipeline_output(
        self,
        regime: str,
        scores: Dict[str, float],
        directions: Dict[str, str],
        sector_scores: Dict[str, float],
        sector_signals: Dict[str, str],
        data_mode: str,
        latest_data_date: Optional[datetime],
        metadata: Dict[str, Any],
        ensemble_result=None,
        bc_result=None,
        cs_result=None,
        fc_result=None,
        inf_result=None,
        mc_result=None,
        val_result=None,
        stress_result=None,
    ) -> Dict[str, Any]:
        """
        Convert legacy pipeline output to business context.

        Args:
            regime: Current macro regime
            scores: Dict of macro scores (growth, inflation, liquidity, risk)
            directions: Dict of score directions
            sector_scores: Dict of sector to score
            sector_signals: Dict of sector to signal (overweight/underweight)
            data_mode: 'live', 'sample', etc.
            latest_data_date: Latest date in the data
            metadata: Additional metadata from pipeline
            Various model results from the pipeline

        Returns:
            business_context dict ready for business layer
        """
        # Build signal snapshot from available data
        signal_snapshot = self._build_signal_snapshot(
            regime, scores, directions, sector_scores, metadata
        )

        # Build cross-asset view
        cross_asset_view = self._build_cross_asset_view(
            regime, scores, directions, mc_result
        )

        # Calculate data quality score
        data_quality = self._calculate_data_quality(data_mode, latest_data_date)

        # Calculate model confidence
        model_confidence = self._calculate_model_confidence(
            ensemble_result, metadata
        )

        # Calculate model disagreement
        model_disagreement = self._calculate_model_disagreement(ensemble_result)

        # Build expected returns from sector scores
        expected_returns = self._derive_expected_returns(sector_scores, regime)

        # Build macro scores dict
        macro_scores = {
            "growth": scores.get("growth", 0),
            "inflation": scores.get("inflation", 0),
            "liquidity": scores.get("liquidity", 0),
            "risk": scores.get("risk", 0),
            "growth_direction": directions.get("growth", "neutral"),
            "inflation_direction": directions.get("inflation", "neutral"),
            "liquidity_direction": directions.get("liquidity", "neutral"),
            "risk_direction": directions.get("risk", "neutral"),
        }

        # Build regime output
        regime_output = {
            "regime": regime,
            "category": self._categorize_regime(regime),
            "confidence": ensemble_result.confidence_level if ensemble_result else "medium",
            "confidence_score": getattr(ensemble_result, 'confidence_score', 0.5) if ensemble_result else 0.5,
        }

        # Build sector allocation
        sector_allocation = {
            sector: {
                "score": score,
                "signal": sector_signals.get(sector, "neutral"),
                "expected_return": expected_returns.get(sector, 0),
            }
            for sector, score in sector_scores.items()
        }

        # Additional model context
        additional_context = {
            "recession_probability": getattr(metadata, 'recession_probability', 0.2),
            "recession_risk_level": getattr(metadata, 'recession_risk_level', 'low'),
            "business_conditions_score": getattr(bc_result, 'score', None) if bc_result else None,
            "business_conditions_direction": getattr(bc_result, 'direction', None) if bc_result else None,
            "credit_stress_level": getattr(cs_result, 'stress_level', None) if cs_result else None,
            "credit_stress_score": getattr(cs_result, 'stress_score', 0) if cs_result else 0,
            "financial_conditions_category": getattr(fc_result, 'category', None) if fc_result else None,
            "inflation_regime": getattr(inf_result, 'regime', None) if inf_result else None,
            "market_confirmation": getattr(mc_result, 'overall_signal', None) if mc_result else None,
            "macro_market_alignment": getattr(mc_result, 'macro_market_alignment', 0.5) if mc_result else 0.5,
            "equity_valuation_level": getattr(val_result.equity_valuation, 'level', None) if val_result and val_result.equity_valuation else None,
            "worst_case_drawdown": getattr(stress_result, 'worst_case_drawdown', None) if stress_result else None,
        }

        business_context = {
            "data_mode": data_mode,
            "latest_data_date": latest_data_date,
            "regime": regime_output,
            "macro_scores": macro_scores,
            "sector_allocation": sector_allocation,
            "cross_asset_view": cross_asset_view,
            "signal_snapshot": signal_snapshot,
            "data_quality": data_quality,
            "model_confidence": model_confidence,
            "model_disagreement": model_disagreement,
            "expected_returns": expected_returns,
            "additional_context": additional_context,
            "ensemble_result": ensemble_result,
            "timestamp": datetime.now(),
        }

        logger.info("Adapted pipeline output to business context")
        return business_context

    def _build_signal_snapshot(
        self,
        regime: str,
        scores: Dict[str, float],
        directions: Dict[str, str],
        sector_scores: Dict[str, float],
        metadata: Dict[str, Any],
    ) -> Dict[str, Dict]:
        """Build a snapshot of current signal readings."""
        snapshot = {}

        # Macro regime signals
        snapshot["growth_regime"] = {
            "category": "macro",
            "current_reading": directions.get("growth", "neutral"),
            "value": scores.get("growth", 0),
            "confidence": 0.7 if abs(scores.get("growth", 0)) > 0.5 else 0.5,
            "research_support": "McCracken & Ng - FRED-MD",
        }

        snapshot["inflation_regime"] = {
            "category": "macro",
            "current_reading": directions.get("inflation", "neutral"),
            "value": scores.get("inflation", 0),
            "confidence": 0.7 if abs(scores.get("inflation", 0)) > 0.5 else 0.5,
            "research_support": "Various inflation targeting literature",
        }

        snapshot["liquidity_conditions"] = {
            "category": "macro",
            "current_reading": directions.get("liquidity", "neutral"),
            "value": scores.get("liquidity", 0),
            "confidence": 0.6,
            "research_support": "Rey - Dilemma not Trilemma",
        }

        snapshot["risk_appetite"] = {
            "category": "sentiment",
            "current_reading": directions.get("risk", "neutral"),
            "value": scores.get("risk", 0),
            "confidence": 0.6,
            "research_support": "Market-based risk indicators",
        }

        # Add sector signals
        for sector, score in sector_scores.items():
            snapshot[f"sector_{sector.lower()}"] = {
                "category": "sector",
                "current_reading": "overweight" if score > 0.2 else "underweight" if score < -0.2 else "neutral",
                "value": score,
                "confidence": 0.5 + abs(score) * 0.5,
                "research_support": "Regime-based sector allocation",
            }

        return snapshot

    def _build_cross_asset_view(
        self,
        regime: str,
        scores: Dict[str, float],
        directions: Dict[str, str],
        mc_result=None,
    ) -> Dict[str, Dict]:
        """Build cross-asset view from regime and scores."""
        view = {}

        # Map regime to asset class signals
        regime_asset_map = {
            "goldilocks": {
                "equities": {"signal": "overweight", "confidence": 0.7, "rationale": "Growth positive, inflation contained"},
                "rates": {"signal": "underweight", "confidence": 0.6, "rationale": "Rising rates as economy improves"},
                "credit": {"signal": "overweight", "confidence": 0.6, "rationale": "Spreads can tighten"},
                "commodities": {"signal": "neutral", "confidence": 0.5, "rationale": "Mixed demand signals"},
                "fx": {"signal": "neutral", "confidence": 0.5, "rationale": "Rate differentials matter"},
            },
            "reflation": {
                "equities": {"signal": "overweight", "confidence": 0.6, "rationale": "Earnings growth strong"},
                "rates": {"signal": "underweight", "confidence": 0.7, "rationale": "Inflation pressure on bonds"},
                "credit": {"signal": "neutral", "confidence": 0.5, "rationale": "Mixed - growth good but rates rising"},
                "commodities": {"signal": "overweight", "confidence": 0.6, "rationale": "Inflation hedge"},
                "fx": {"signal": "neutral", "confidence": 0.5, "rationale": "Dollar depends on Fed path"},
            },
            "stagflation": {
                "equities": {"signal": "underweight", "confidence": 0.7, "rationale": "Earnings pressure from costs"},
                "rates": {"signal": "underweight", "confidence": 0.6, "rationale": "Inflation erodes returns"},
                "credit": {"signal": "underweight", "confidence": 0.6, "rationale": "Default risk rises"},
                "commodities": {"signal": "overweight", "confidence": 0.7, "rationale": "Real asset hedge"},
                "fx": {"signal": "neutral", "confidence": 0.5, "rationale": "Flight to safety unclear"},
            },
            "slowdown": {
                "equities": {"signal": "underweight", "confidence": 0.6, "rationale": "Growth decelerating"},
                "rates": {"signal": "overweight", "confidence": 0.7, "rationale": "Flight to quality"},
                "credit": {"signal": "underweight", "confidence": 0.7, "rationale": "Spreads widen as growth slows"},
                "commodities": {"signal": "underweight", "confidence": 0.5, "rationale": "Demand weakness"},
                "fx": {"signal": "neutral", "confidence": 0.5, "rationale": "Rate cut expectations"},
            },
        }

        default_view = {
            "equities": {"signal": "neutral", "confidence": 0.5, "rationale": "Mixed signals"},
            "rates": {"signal": "neutral", "confidence": 0.5, "rationale": "Mixed signals"},
            "credit": {"signal": "neutral", "confidence": 0.5, "rationale": "Mixed signals"},
            "commodities": {"signal": "neutral", "confidence": 0.5, "rationale": "Mixed signals"},
            "fx": {"signal": "neutral", "confidence": 0.5, "rationale": "Mixed signals"},
        }

        view = regime_asset_map.get(regime, default_view)

        # Adjust based on market confirmation if available
        if mc_result:
            alignment = getattr(mc_result, 'macro_market_alignment', 0.5)
            if alignment < 0.5:
                for asset in view:
                    view[asset]["confidence"] *= 0.7
                    view[asset]["rationale"] += " (market disagrees)"

        return view

    def _calculate_data_quality(
        self,
        data_mode: str,
        latest_data_date: Optional[datetime],
    ) -> Dict[str, Any]:
        """Calculate data quality metrics."""
        if data_mode == "sample":
            return {
                "score": 0.3,
                "mode": "sample",
                "is_live": False,
                "warning": "Sample data only - not for trading decisions",
            }

        if latest_data_date is None:
            return {
                "score": 0.0,
                "mode": data_mode,
                "is_live": True,
                "warning": "No data date available",
            }

        days_since = (datetime.now() - latest_data_date).days

        if days_since <= 30:
            freshness = "current"
            score = 0.9
        elif days_since <= 60:
            freshness = "acceptable"
            score = 0.7
        elif days_since <= 90:
            freshness = "stale"
            score = 0.5
        else:
            freshness = "very_stale"
            score = 0.3

        return {
            "score": score,
            "mode": data_mode,
            "is_live": True,
            "latest_date": latest_data_date.isoformat() if latest_data_date else None,
            "days_since_update": days_since,
            "freshness": freshness,
            "warning": f"Data is {days_since} days old" if days_since > 45 else None,
        }

    def _calculate_model_confidence(
        self,
        ensemble_result=None,
        metadata: Dict[str, Any] = None,
    ) -> float:
        """Calculate overall model confidence."""
        if ensemble_result is None:
            return 0.5

        confidence = getattr(ensemble_result, 'confidence_level', 'medium')
        confidence_map = {
            "high": 0.8,
            "medium": 0.6,
            "low": 0.4,
        }

        return confidence_map.get(confidence, 0.5)

    def _calculate_model_disagreement(
        self,
        ensemble_result=None,
    ) -> float:
        """Calculate model disagreement score."""
        if ensemble_result is None:
            return 0.0

        return getattr(ensemble_result, 'disagreement_score', 0.0)

    def _derive_expected_returns(
        self,
        sector_scores: Dict[str, float],
        regime: str,
    ) -> Dict[str, float]:
        """Derive expected returns from sector scores."""
        # Map regime to base return expectation
        regime_base_return = {
            "goldilocks": 0.08,
            "reflation": 0.06,
            "stagflation": -0.02,
            "slowdown": -0.01,
        }

        base = regime_base_return.get(regime, 0.03)

        expected_returns = {}
        for sector, score in sector_scores.items():
            # Scale score to expected return
            # Score range roughly -0.5 to +0.5
            expected_returns[sector] = base + score * 0.1

        return expected_returns

    def _categorize_regime(self, regime: str) -> str:
        """Categorize regime into high-level category."""
        categories = {
            "goldilocks": "expansion",
            "reflation": "expansion",
            "stagflation": "contraction",
            "slowdown": "contraction",
            "recovery": "expansion",
            "deflation": "contraction",
        }
        return categories.get(regime, "mixed")

    def get_signal_registry(self) -> SignalRegistry:
        """Get the signal registry with all registered signals."""
        return self.signal_registry
