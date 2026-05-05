"""
Macro-Aware Equity Valuation — Regime-Conditional Fair Value

Implements equity valuation models that adjust for macro regime.
Different valuations are appropriate in different regimes:
- Goldilocks: P/E expansion, growth premium
- Stagflation: Real assets, inflation pass-through
- Slowdown: Quality premium, defensive focus

Models:
1. Fair Value ERP: Equity Risk Premium adjusted for regime
2. Cyclically-Adjusted P/E (CAPE) vs regime-appropriate target
3. Gordon Growth Model with regime-dependent growth rates
4. Factor-implied valuation (which factors are expensive/cheap)
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class MacroValuationMetrics:
    """Valuation metrics for a market/sector/stock."""
    current_pe: float
    forward_pe: float
    peg_ratio: float
    ev_ebitda: float
    pb_ratio: float
    dividend_yield: float
    fcf_yield: float
    regime: str
    regime_target_pe: float
    valuation_discount: float  # Current vs target
    erp: float  # Equity Risk Premium
    erp_zscore: float  # ERP vs historical average
    fair_value_estimate: float
    upside_potential: float


@dataclass
class MacroValuationModel:
    """Complete macro-aware valuation model."""
    timestamp: datetime
    market: str
    current_regime: str
    metrics: MacroValuationMetrics
    valuation_percentile: float  # 0-100 scale
    regime_appropriate_multiples: Dict[str, float]
    factor_valuations: Dict[str, Dict]  # Value/Growth/etc valuations


# Regime-appropriate valuation multiples (historical averages)
REGIME_MULTIPLES = {
    "Goldilocks": {
        "target_pe": 20.0,
        "target_erp": 0.035,
        "growth_premium": 0.15,  # Growth gets 15% premium
        "quality_premium": 0.10,
    },
    "Reflation": {
        "target_pe": 16.0,
        "target_erp": 0.045,
        "growth_premium": 0.05,
        "quality_premium": 0.05,
    },
    "Stagflation": {
        "target_pe": 14.0,
        "target_erp": 0.055,
        "growth_premium": -0.10,  # Discount in stagflation
        "quality_premium": 0.20,  # Quality commands premium
    },
    "Slowdown": {
        "target_pe": 15.0,
        "target_erp": 0.050,
        "growth_premium": 0.05,
        "quality_premium": 0.15,
    },
}


class MacroValuationEngine:
    """
    Compute macro-aware equity valuations.

    Adjusts standard valuation metrics for macro regime context.
    Provides fair value estimates and upside/downside potential.
    """

    def __init__(self):
        self.historical_erp = {}

    def calculate_valuation(
        self,
        market_data: Dict,
        regime: str,
        historical_pe: Optional[List[float]] = None,
        historical_erp: Optional[float] = None,
    ) -> MacroValuationModel:
        """
        Calculate macro-aware valuation.

        Args:
            market_data: Dict with valuation metrics
            regime: Current macro regime
            historical_pe: Long-term average P/E
            historical_erp: Long-term average ERP
        """
        current_pe = market_data.get("current_pe", 0)
        forward_pe = market_data.get("forward_pe", current_pe)
        earnings_growth = market_data.get("earnings_growth", 0.05)
        risk_free_rate = market_data.get("risk_free_rate", 0.04)

        # Get regime multiples
        regime_mult = REGIME_MULTIPLES.get(regime, REGIME_MULTIPLES["Goldilocks"])
        target_pe = regime_mult["target_pe"]
        target_erp = regime_mult["target_erp"]

        # Calculate ERP
        # ERP = Earnings Yield - Risk Free Rate
        earnings_yield = 1 / current_pe if current_pe > 0 else 0
        erp = earnings_yield - risk_free_rate

        # ERP z-score
        if historical_erp:
            erp_zscore = (erp - historical_erp) / 0.01  # Assuming 1% std dev
        else:
            erp_zscore = (erp - 0.045) / 0.01

        # Valuation discount vs regime target
        if target_pe > 0:
            valuation_discount = (current_pe / target_pe) - 1
        else:
            valuation_discount = 0

        # Fair value estimate (Gordon growth model + regime adjustments)
        # P = D / (r + ERP - g)
        discount_rate = risk_free_rate + target_erp
        if discount_rate > earnings_growth:
            fair_value_pe = 1 / (discount_rate - earnings_growth)
            fair_value = fair_value_pe * market_data.get("eps", 0)
        else:
            fair_value_pe = current_pe
            fair_value = current_pe * market_data.get("eps", 0)

        # Upside potential
        if current_pe > 0:
            upside = (fair_value_pe / current_pe) - 1
        else:
            upside = 0

        # Valuation percentile (0 = cheapest, 100 = most expensive)
        if historical_pe:
            current = current_pe
            hist_mean = np.mean(historical_pe)
            hist_std = np.std(historical_pe)
            if hist_std > 0:
                z = (current - hist_mean) / hist_std
                percentile = min(max((z + 2) * 25, 0), 100)
            else:
                percentile = 50
        else:
            # Rough estimate based on regime target
            if target_pe > 0:
                ratio = current_pe / target_pe
                percentile = min(max(ratio * 50, 0), 100)
            else:
                percentile = 50

        metrics = MacroValuationMetrics(
            current_pe=round(current_pe, 1),
            forward_pe=round(forward_pe, 1),
            peg_ratio=round(current_pe / (earnings_growth * 100), 2) if earnings_growth > 0 else 0,
            ev_ebitda=round(market_data.get("ev_ebitda", 0), 1),
            pb_ratio=round(market_data.get("pb_ratio", 0), 1),
            dividend_yield=round(market_data.get("dividend_yield", 0), 3),
            fcf_yield=round(market_data.get("fcf_yield", 0), 3),
            regime=regime,
            regime_target_pe=round(target_pe, 1),
            valuation_discount=round(valuation_discount, 3),
            erp=round(erp, 4),
            erp_zscore=round(erp_zscore, 2),
            fair_value_estimate=round(fair_value, 2),
            upside_potential=round(upside * 100, 1),
        )

        # Factor valuations (simplified)
        factor_vals = {}
        for factor in ["value", "momentum", "quality", "growth", "low_vol"]:
            # Placeholder - would need factor-specific data
            factor_vals[factor] = {
                "current_val": current_pe * (1 + regime_mult.get(f"{factor}_premium", 0)),
                "regime_premium": regime_mult.get(f"{factor}_premium", 0),
            }

        return MacroValuationModel(
            timestamp=datetime.now(),
            market=market_data.get("market", "US"),
            current_regime=regime,
            metrics=metrics,
            valuation_percentile=round(percentile, 1),
            regime_appropriate_multiples={
                "pe": target_pe,
                "erp": target_erp,
                "growth_premium": regime_mult.get("growth_premium", 0),
            },
            factor_valuations=factor_vals,
        )

    def compare_across_regimes(
        self,
        market_data: Dict,
    ) -> Dict[str, float]:
        """
        Compare valuation attractiveness across all regimes.
        Returns expected returns by regime.
        """
        expected_returns = {}
        for regime in ["Goldilocks", "Reflation", "Stagflation", "Slowdown"]:
            model = self.calculate_valuation(market_data, regime)
            expected_returns[regime] = model.metrics.upside_potential

        return expected_returns


def get_valuation_signal(model: MacroValuationModel) -> Dict:
    """
    Generate buy/sell signal from valuation model.
    """
    upside = model.metrics.upside_potential
    erp_z = model.metrics.erp_zscore

    if upside > 15 and erp_z > 0.5:
        signal = "STRONG_BUY"
    elif upside > 10:
        signal = "BUY"
    elif upside < -15:
        signal = "SELL"
    elif upside < -10:
        signal = "REDUCE"
    else:
        signal = "HOLD"

    return {
        "signal": signal,
        "upside_potential": upside,
        "valuation_percentile": model.valuation_percentile,
        "regime_adjusted_pe": model.metrics.regime_target_pe,
        "current_pe": model.metrics.current_pe,
        "erp_zscore": erp_z,
    }


def detect_valuation_extreme(
    model: MacroValuationModel,
    threshold: float = 90.0,
) -> Optional[Dict]:
    """
    Detect if market is at valuation extreme (bubble or panic).
    """
    if model.valuation_percentile > threshold:
        return {
            "extreme": "overvalued",
            "percentile": model.valuation_percentile,
            "signal": "reduce_equity_exposure",
            "confidence": min(model.valuation_percentile / 100, 0.95),
        }
    elif model.valuation_percentile < (100 - threshold):
        return {
            "extreme": "undervalued",
            "percentile": model.valuation_percentile,
            "signal": "increase_equity_exposure",
            "confidence": min((100 - model.valuation_percentile) / 100, 0.95),
        }
    return None
