"""
Multi-Factor Alpha Scoring — Stock Selection via Factor Exposures

Implements a multi-factor alpha model for equity scoring.
Combines traditional factors (value, momentum, quality) with macro-aware
factor timing (which factors work in current regime).

Academic Basis:
- Fama-French 5-Factor Model (2015)
- Factor timing: Arnott et al. (2016) "Factor Timing with Macro Variables"
- Machine learning: Gu et al. (2020) "Empirical Asset Pricing via Machine Learning"

Factor Definitions:
- Value: Book-to-market, earnings yield, dividend yield
- Momentum: 12-1 month return, earnings momentum
- Quality: ROE, earnings stability, low leverage
- Growth: Sales growth, earnings growth
- Low Vol: Low beta, low idiosyncratic volatility
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    logger.warning("xgboost not installed. Gradient boosting features disabled.")

try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False


@dataclass
class FactorExposure:
    """Factor exposure scores for a single stock."""
    ticker: str
    value_score: float
    momentum_score: float
    quality_score: float
    growth_score: float
    low_vol_score: float
    macro_sync_score: float  # How well aligned with current regime
    composite_alpha: float


@dataclass
class FactorTimingModel:
    """Current factor recommendations based on macro regime."""
    regime: str
    factor_weights: Dict[str, float]
    factor_performance: Dict[str, float]
    expected_factor_premium: Dict[str, float]


# Factor regime performance (historical averages)
FACTOR_REGIME_PERFORMANCE = {
    "Goldilocks": {
        "value": 0.02, "momentum": 0.04, "quality": 0.03,
        "growth": 0.05, "low_vol": 0.01,
    },
    "Reflation": {
        "value": 0.04, "momentum": 0.03, "quality": 0.02,
        "growth": 0.03, "low_vol": -0.01,
    },
    "Stagflation": {
        "value": 0.01, "momentum": -0.02, "quality": 0.04,
        "growth": -0.03, "low_vol": 0.05,
    },
    "Slowdown": {
        "value": 0.02, "momentum": -0.01, "quality": 0.03,
        "growth": 0.00, "low_vol": 0.04,
    },
}


class MultiFactorAlphaScorer:
    """
    Compute multi-factor alpha scores for stock selection.

    Combines:
    1. Cross-sectional factor scoring (rank stocks within universe)
    2. Macro-aware factor timing (tilt toward regime-appropriate factors)
    3. Optional ML-based non-linear factor interactions
    """

    def __init__(self, use_ml: bool = True):
        self.use_ml = use_ml and XGBOOST_AVAILABLE
        self.model: Optional[xgb.XGBRegressor] = None
        self.feature_names = [
            "value", "momentum", "quality", "growth", "low_vol", "macro_sync"
        ]

    def fit(self, factor_data: pd.DataFrame, forward_returns: pd.Series):
        """
        Fit ML model on historical factor data and forward returns.

        Args:
            factor_data: DataFrame with factor columns
            forward_returns: Series of 1-month forward returns
        """
        if not self.use_ml:
            return

        # Align data
        common_idx = factor_data.index.intersection(forward_returns.index)
        X = factor_data.loc[common_idx].fillna(0)
        y = forward_returns.loc[common_idx].fillna(0)

        self.model = xgb.XGBRegressor(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
        )
        self.model.fit(X, y)

        logger.info(f"Multi-factor model fitted: {len(X)} observations")

    def score_stock(
        self,
        ticker: str,
        factor_values: Dict[str, float],
        regime: str,
    ) -> FactorExposure:
        """
        Compute factor exposure and alpha score for a single stock.

        Args:
            ticker: Stock ticker
            factor_values: Dict of raw factor values
            regime: Current macro regime
        """
        # Z-score each factor (cross-sectional normalization)
        # In practice, these would be pre-computed against universe
        scores = {}
        for factor in ["value", "momentum", "quality", "growth", "low_vol"]:
            scores[factor] = factor_values.get(factor, 0)

        # Macro sync score: how well stock's factor profile matches regime
        regime_factors = FACTOR_REGIME_PERFORMANCE.get(regime, {})
        macro_sync = sum(
            scores[f] * regime_factors.get(f, 0)
            for f in scores
        )

        # Compute composite alpha
        if self.use_ml and self.model is not None:
            # ML-based prediction
            features = np.array([[scores[f] for f in self.feature_names[:-1]] + [macro_sync]])
            composite = float(self.model.predict(features)[0])
        else:
            # Linear combination with regime timing
            base_weights = {"value": 0.2, "momentum": 0.2, "quality": 0.2,
                          "growth": 0.2, "low_vol": 0.2}

            # Tilt weights toward regime-favored factors
            regime_premia = FACTOR_REGIME_PERFORMANCE.get(regime, base_weights)
            total_premia = sum(abs(v) for v in regime_premia.values())
            if total_premia > 0:
                timing_weights = {
                    f: base_weights[f] * (1 + regime_premia.get(f, 0) / total_premia)
                    for f in base_weights
                }
                # Renormalize
                total = sum(timing_weights.values())
                timing_weights = {f: w / total for f, w in timing_weights.items()}
            else:
                timing_weights = base_weights

            composite = sum(scores[f] * timing_weights[f] for f in scores)

        return FactorExposure(
            ticker=ticker,
            value_score=round(scores["value"], 3),
            momentum_score=round(scores["momentum"], 3),
            quality_score=round(scores["quality"], 3),
            growth_score=round(scores["growth"], 3),
            low_vol_score=round(scores["low_vol"], 3),
            macro_sync_score=round(macro_sync, 3),
            composite_alpha=round(composite, 3),
        )

    def score_universe(
        self,
        universe_data: pd.DataFrame,
        regime: str,
    ) -> List[FactorExposure]:
        """
        Score entire universe of stocks.

        Args:
            universe_data: DataFrame with columns [ticker, value, momentum, ...]
            regime: Current macro regime
        """
        results = []
        for _, row in universe_data.iterrows():
            ticker = row.get("ticker", "UNKNOWN")
            factors = {f: row.get(f, 0) for f in ["value", "momentum", "quality", "growth", "low_vol"]}
            exposure = self.score_stock(ticker, factors, regime)
            results.append(exposure)

        return sorted(results, key=lambda x: x.composite_alpha, reverse=True)


def get_factor_timing(regime: str) -> FactorTimingModel:
    """
    Get factor timing recommendations for current regime.

    Returns over/underweight recommendations per factor.
    """
    performance = FACTOR_REGIME_PERFORMANCE.get(regime, {})

    # Calculate relative weights based on expected performance
    if performance:
        # Shift to positive range for weighting
        shifted = {f: max(0, p + 0.05) for f, p in performance.items()}
        total = sum(shifted.values())
        weights = {f: round(p / total, 3) for f, p in shifted.items()}
    else:
        weights = {f: 0.2 for f in ["value", "momentum", "quality", "growth", "low_vol"]}

    # Expected factor premiums
    premiums = {f: round(p, 4) for f, p in performance.items()}

    return FactorTimingModel(
        regime=regime,
        factor_weights=weights,
        factor_performance={f: round(p, 4) for f, p in performance.items()},
        expected_factor_premium=premiums,
    )


def get_top_alpha_picks(
    exposures: List[FactorExposure],
    n: int = 10,
    min_alpha: float = 0.0,
) -> List[Dict]:
    """
    Get top alpha picks from scored universe.
    """
    filtered = [e for e in exposures if e.composite_alpha >= min_alpha]
    top = filtered[:n]

    return [
        {
            "ticker": e.ticker,
            "composite_alpha": e.composite_alpha,
            "factor_exposures": {
                "value": e.value_score,
                "momentum": e.momentum_score,
                "quality": e.quality_score,
                "growth": e.growth_score,
                "low_vol": e.low_vol_score,
            },
            "macro_sync": e.macro_sync_score,
        }
        for e in top
    ]


def explain_alpha(
    exposure: FactorExposure,
    regime: str,
) -> Dict:
    """
    Generate human-readable explanation of alpha score.
    """
    # Identify dominant factors
    factors = {
        "value": exposure.value_score,
        "momentum": exposure.momentum_score,
        "quality": exposure.quality_score,
        "growth": exposure.growth_score,
        "low_vol": exposure.low_vol_score,
    }
    sorted_factors = sorted(factors.items(), key=lambda x: abs(x[1]), reverse=True)

    top_factor = sorted_factors[0]
    factor_direction = "positive" if top_factor[1] > 0 else "negative"

    # Regime alignment
    regime_timing = get_factor_timing(regime)
    regime_weight = regime_timing.factor_weights.get(top_factor[0], 0.2)
    regime_alignment = "aligned" if regime_weight > 0.25 else "neutral"

    return {
        "ticker": exposure.ticker,
        "alpha_score": exposure.composite_alpha,
        "primary_driver": {
            "factor": top_factor[0],
            "exposure": top_factor[1],
            "direction": factor_direction,
        },
        "regime_alignment": regime_alignment,
        "regime": regime,
        "macro_sync": exposure.macro_sync_score,
        "factor_breakdown": factors,
    }
