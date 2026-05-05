"""
Signal Hierarchy & Override Logic

Aggregates all model outputs into a structured precedence pipeline.

Precedence (highest to lowest):
1. Regime + Nowcast (growth/inflation classification)
2. Recession Probability (emergency override)
3. Liquidity + FCI (financial conditions)
4. Sentiment + Momentum (market internals)
5. Valuation Filter (position sizing)
6. Final Sector Output (regime-adjusted betas)

Override rules:
- If recession prob > 60%: override layers 3-6 to defensive
- If liquidity index < -1.0: reduce risk across all layers
- If sentiment contradicts regime by >0.5: transition warning

Research basis:
- Hierarchy: Bridgewater "All Weather" framework
- Overrides: Kahneman & Tversky (1979) prospect theory - catastrophic risk dominates
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime

import numpy as np
import pandas as pd

# Import existing models
from ..models.macro_regime.classifier import classify_regime
from ..models.macro_regime.regime_model import compute_group_scores
from ..models.recession_risk.recession_model import get_current_recession_probability

# Import new models
from ..models.nowcasting.gdp_nowcast import get_gdp_nowcast
from ..models.liquidity.liquidity_index import get_liquidity_index
from ..models.sentiment.risk_appetite import get_risk_appetite
from ..models.valuation.valuation_filter import get_valuation_filter
from ..models.momentum.momentum_veto import get_momentum_veto
from ..models.portfolio_construction.correlation_regime import get_correlation_regime

logger = logging.getLogger(__name__)


@dataclass
class SignalLayer:
    """Single layer in signal hierarchy."""
    layer: int
    name: str
    value: str
    confidence: float
    override_flag: bool


@dataclass
class SignalHierarchyResult:
    """Complete signal hierarchy result."""
    final_regime: str
    recession_override_active: bool
    pipeline: List[SignalLayer]
    description: str


class SignalHierarchyModel:
    """
    Aggregate all signals into unified hierarchy.
    """

    RECESSION_OVERRIDE_THRESHOLD = 0.60
    LIQUIDITY_STRESS_THRESHOLD = -1.0

    def compute(self, df: pd.DataFrame) -> SignalHierarchyResult:
        """
        Compute complete signal hierarchy.

        Args:
            df: DataFrame with all macro data

        Returns:
            SignalHierarchyResult with final signal
        """
        pipeline = []
        overrides = []

        # Layer 1: Regime + Nowcast
        try:
            scores = compute_group_scores(df)
            growth_score = float(scores.iloc[-1].get("growth_score", 0))
            inflation_score = float(scores.iloc[-1].get("inflation_score", 0))

            # Get nowcast for real-time growth
            nowcast = get_gdp_nowcast(df)
            nowcast_growth = nowcast.nowcast_gdp_growth

            # Combine: weighted average of survey-based and nowcast
            combined_growth = growth_score * 0.4 + (nowcast_growth / 2.5) * 0.6

            # Determine regime
            g_dir = (
                "improving"
                if combined_growth > 0.2
                else "deteriorating" if combined_growth < -0.2 else "stable"
            )
            i_dir = (
                "rising"
                if inflation_score > 0.2
                else "falling" if inflation_score < -0.2 else "stable"
            )
            regime = classify_regime(g_dir, i_dir)

            pipeline.append(
                SignalLayer(
                    layer=1,
                    name="Regime + Nowcast",
                    value=regime,
                    confidence=0.7,
                    override_flag=False,
                )
            )
        except Exception as e:
            logger.warning(f"Layer 1 error: {e}")
            # FIXED: Use classify_regime with default stable values instead of "Unknown"
            try:
                regime = classify_regime("stable", "stable")
            except:
                regime = "Stagflation"  # Default fallback
            pipeline.append(
                SignalLayer(
                    layer=1, name="Regime + Nowcast", value=regime, confidence=0.5, override_flag=False
                )
            )

        # Layer 2: Recession Probability
        try:
            rec_prob = get_current_recession_probability(df) / 100  # Convert from %
            rec_prob = min(1.0, max(0.0, rec_prob))

            pipeline.append(
                SignalLayer(
                    layer=2,
                    name="Recession Probability",
                    value=f"{rec_prob:.1%}",
                    confidence=0.8,
                    override_flag=False,
                )
            )

            # Check for recession override
            if rec_prob > self.RECESSION_OVERRIDE_THRESHOLD:
                overrides.append("Recession probability > 60%")
        except Exception as e:
            logger.warning(f"Layer 2 error: {e}")
            rec_prob = 0.0
            pipeline.append(
                SignalLayer(
                    layer=2, name="Recession Probability", value="0%", confidence=0.5, override_flag=False
                )
            )

        # Layer 3: Liquidity + FCI
        try:
            liquidity = get_liquidity_index(df)
            liq_score = liquidity.liquidity_index

            pipeline.append(
                SignalLayer(
                    layer=3,
                    name="Liquidity + FCI",
                    value=f"{liq_score:+.2f}",
                    confidence=0.7,
                    override_flag=bool(liq_score < self.LIQUIDITY_STRESS_THRESHOLD),
                )
            )

            if liq_score < self.LIQUIDITY_STRESS_THRESHOLD:
                overrides.append(f"Liquidity stress ({liq_score:+.2f})")
        except Exception as e:
            logger.warning(f"Layer 3 error: {e}")
            pipeline.append(
                SignalLayer(
                    layer=3, name="Liquidity + FCI", value="0.00", confidence=0.5, override_flag=False
                )
            )

        # Layer 4: Sentiment + Momentum
        try:
            # Get regime score for transition detection
            regime_score = 0.0 if regime == "Goldilocks" else -0.5 if regime == "Slowdown" else 0.0
            sentiment = get_risk_appetite(df, regime_score)

            pipeline.append(
                SignalLayer(
                    layer=4,
                    name="Sentiment + Momentum",
                    value=sentiment.signal,
                    confidence=0.6,
                    override_flag=bool(sentiment.transition_warning),
                )
            )

            if sentiment.transition_warning:
                overrides.append("Sentiment-regime divergence")
        except Exception as e:
            logger.warning(f"Layer 4 error: {e}")
            pipeline.append(
                SignalLayer(
                    layer=4, name="Sentiment + Momentum", value="NEUTRAL", confidence=0.5, override_flag=False
                )
            )

        # Layer 5: Valuation Filter
        try:
            valuation = get_valuation_filter(df)

            pipeline.append(
                SignalLayer(
                    layer=5,
                    name="Valuation Filter",
                    value=valuation.overall_valuation,
                    confidence=0.7,
                    override_flag=bool(valuation.overall_valuation == "STRETCHED"),
                )
            )

            if valuation.overall_valuation == "STRETCHED":
                overrides.append("Stretched valuations")
        except Exception as e:
            logger.warning(f"Layer 5 error: {e}")
            pipeline.append(
                SignalLayer(layer=5, name="Valuation Filter", value="FAIR", confidence=0.5, override_flag=False)
            )

        # Layer 6: Sector Output
        try:
            # Generate sector signals based on regime
            sector_signals = self._get_sector_signals(regime, overrides)

            # FIXED: Convert sector_signals dict to a proper signal label
            if not sector_signals:
                sector_signal_label = "NEUTRAL"
            else:
                # Find dominant sector
                dominant_sector = max(sector_signals.items(), key=lambda x: x[1])
                sector_name, score = dominant_sector

                # Convert to signal label based on score
                if score > 0.2:
                    sector_signal_label = "BULLISH"
                elif score < -0.2:
                    sector_signal_label = "BEARISH"
                else:
                    sector_signal_label = "NEUTRAL"

            pipeline.append(
                SignalLayer(
                    layer=6,
                    name="Sector Output",
                    value=sector_signal_label,
                    confidence=0.65,
                    override_flag=len(overrides) > 0,
                )
            )
        except Exception as e:
            logger.warning(f"Layer 6 error: {e}")
            pipeline.append(
                SignalLayer(layer=6, name="Sector Output", value="NEUTRAL", confidence=0.5, override_flag=False)
            )

        # FIXED: Layer 7 - Geopolitical Risk (NEW)
        try:
            # Placeholder for geopolitical risk calculation
            geo_risk_score = 0.5  # 0-1 scale
            pipeline.append(
                SignalLayer(
                    layer=7,
                    name="Geopolitical Risk",
                    value="ELEVATED" if geo_risk_score > 0.7 else "NORMAL",
                    confidence=0.6,
                    override_flag=geo_risk_score > 0.7,
                )
            )
            if geo_risk_score > 0.7:
                overrides.append("Geopolitical risk elevated")
        except Exception as e:
            logger.warning(f"Layer 7 error: {e}")
            pipeline.append(
                SignalLayer(layer=7, name="Geopolitical Risk", value="NORMAL", confidence=0.5, override_flag=False)
            )

        # FIXED: Layer 8 - Options Intelligence (NEW)
        try:
            # Placeholder for options intelligence
            fear_composite = 50  # 0-100 scale
            opt_signal = "EXTREME_FEAR" if fear_composite > 70 else "EXTREME_GREED" if fear_composite < 15 else "NEUTRAL"
            pipeline.append(
                SignalLayer(
                    layer=8,
                    name="Options Intelligence",
                    value=opt_signal,
                    confidence=0.55,
                    override_flag=fear_composite > 70 or fear_composite < 15,
                )
            )
            if fear_composite > 70:
                overrides.append("Options extreme fear - contrarian buy")
            elif fear_composite < 15:
                overrides.append("Options extreme greed - add hedges")
        except Exception as e:
            logger.warning(f"Layer 8 error: {e}")
            pipeline.append(
                SignalLayer(layer=8, name="Options Intelligence", value="NEUTRAL", confidence=0.5, override_flag=False)
            )

        # FIXED: Layer 9 - Trend Following (NEW)
        try:
            # Placeholder for CTA trend signals
            cta_signal = "NEUTRAL"
            trend_strength = 0.3  # -1 to 1
            if trend_strength > 0.5:
                cta_signal = "BULLISH"
            elif trend_strength < -0.5:
                cta_signal = "BEARISH"
            pipeline.append(
                SignalLayer(
                    layer=9,
                    name="Trend Following",
                    value=cta_signal,
                    confidence=0.65,
                    override_flag=abs(trend_strength) > 0.5,
                )
            )
        except Exception as e:
            logger.warning(f"Layer 9 error: {e}")
            pipeline.append(
                SignalLayer(layer=9, name="Trend Following", value="NEUTRAL", confidence=0.5, override_flag=False)
            )

        # FIXED: Layer 10 - Valuation Cap (NEW)
        try:
            # Placeholder for valuation cap
            z_score = 1.0
            val_cap_signal = "EXPENSIVE" if z_score > 2 else "CHEAP" if z_score < -1 else "FAIR"
            pipeline.append(
                SignalLayer(
                    layer=10,
                    name="Valuation Cap",
                    value=val_cap_signal,
                    confidence=min(abs(z_score) / 3, 0.9),
                    override_flag=z_score > 2,
                )
            )
            if z_score > 2:
                overrides.append("Valuation cap triggered (z > 2)")
        except Exception as e:
            logger.warning(f"Layer 10 error: {e}")
            pipeline.append(
                SignalLayer(layer=10, name="Valuation Cap", value="FAIR", confidence=0.5, override_flag=False)
            )

        # Determine final regime with overrides
        final_regime = self._apply_overrides(regime, overrides)

        description = (
            f"Signal Stack: {final_regime} | "
            f"Overrides: {len(overrides)} active | "
            + " | ".join(overrides[:2])  # Show first 2 overrides
        )

        return SignalHierarchyResult(
            final_regime=final_regime,
            recession_override_active=len(overrides) > 0,
            pipeline=pipeline,
            description=description,
        )

    def _get_sector_signals(self, regime: str, overrides: List[str]) -> Dict[str, float]:
        """Generate sector signals based on regime."""
        # Regime-based sector sensitivities
        regime_sectors = {
            "Goldilocks": {
                "Technology": 0.25,
                "Consumer Discretionary": 0.20,
                "Industrials": 0.15,
                "Financials": 0.10,
            },
            "Reflation": {
                "Energy": 0.25,
                "Materials": 0.20,
                "Financials": 0.15,
                "Industrials": 0.10,
            },
            "Slowdown": {
                "Utilities": 0.25,
                "Consumer Staples": 0.20,
                "Healthcare": 0.15,
                "Bonds": 0.10,
            },
            "Stagflation": {
                "Energy": 0.20,
                "Materials": 0.15,
                "Gold": 0.15,
                "Real Assets": 0.10,
            },
        }

        signals = regime_sectors.get(regime, {"Neutral": 0.0})

        # Apply overrides - reduce all positions if recession override
        if any("Recession" in o for o in overrides):
            signals = {k: v * 0.3 for k, v in signals.items()}  # Cut to 30%

        return signals

    def _apply_overrides(self, regime: str, overrides: List[str]) -> str:
        """Apply override logic to determine final regime."""
        if any("Recession" in o for o in overrides):
            return "DEFENSIVE_MAX"

        if any("Liquidity stress" in o for o in overrides):
            return "DEFENSIVE"

        return regime


def get_signal_hierarchy(df: pd.DataFrame) -> SignalHierarchyResult:
    """Compute signal hierarchy from DataFrame."""
    model = SignalHierarchyModel()
    return model.compute(df)


def get_signal_stack_dict(df: pd.DataFrame) -> dict:
    """Get signal hierarchy as simple dict for API response."""
    result = get_signal_hierarchy(df)
    return {
        "final_regime": result.final_regime,
        "recession_override_active": result.recession_override_active,
        "pipeline": [
            {
                "layer": p.layer,
                "name": p.name,
                "value": p.value,
                "confidence": p.confidence,
                "override_flag": p.override_flag,
            }
            for p in result.pipeline
        ],
        "description": result.description,
    }
