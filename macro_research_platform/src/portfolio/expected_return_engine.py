"""
Expected Return Engine

Combines signals to generate expected returns by asset class.

Implements:
- Signal combination (weighted average)
- Alpha factor construction
- Expected return estimates with confidence
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ExpectedReturn:
    """Expected return for an asset class."""
    asset_class: str
    expected_return: float
    confidence: float  # 0-1
    volatility_estimate: float
    sharpe_estimate: float
    signal_contributions: Dict[str, float]
    time_horizon: str  # short, medium, long


class ExpectedReturnEngine:
    """
    Generate expected returns from systematic signals.

    Combines multiple signals with weights to produce
    asset class expected returns.
    """

    # Historical volatilities by asset class (annualized)
    DEFAULT_VOLATILITIES = {
        "equities": 0.16,
        "rates": 0.05,
        "credit": 0.08,
        "commodities": 0.20,
        "fx": 0.10,
        "emerging_markets": 0.22,
        "real_estate": 0.18,
    }

    # Risk-free rate assumption
    RISK_FREE_RATE = 0.04

    def __init__(self):
        self.signal_weights: Dict[str, float] = {}
        self.signal_decay: Dict[str, float] = {}  # Half-life in days
        self.return_history: Dict[str, List[ExpectedReturn]] = {}

    def set_signal_weights(self, weights: Dict[str, float]) -> None:
        """
        Set weights for combining signals.

        Args:
            weights: Dict of signal_name to weight (should sum to 1)
        """
        total = sum(weights.values())
        if abs(total - 1.0) > 0.01:
            logger.warning(f"Signal weights sum to {total}, normalizing")
            weights = {k: v / total for k, v in weights.items()}

        self.signal_weights = weights
        logger.info(f"Set signal weights: {weights}")

    def calculate_expected_returns(
        self,
        signals: Dict[str, Dict[str, float]],  # signal_name -> asset -> score
        asset_classes: List[str],
        as_of_date: Optional[datetime] = None,
    ) -> Dict[str, ExpectedReturn]:
        """
        Calculate expected returns for each asset class.

        Args:
            signals: Dict of signal outputs by asset
            asset_classes: List of asset classes to calculate for
            as_of_date: Calculation date

        Returns:
            Dict of asset_class to ExpectedReturn
        """
        results = {}

        for asset in asset_classes:
            # Combine signals for this asset
            weighted_return = 0
            contributions = {}
            total_weight = 0

            for signal_name, signal_scores in signals.items():
                if asset not in signal_scores:
                    continue

                weight = self.signal_weights.get(signal_name, 0)
                if weight == 0:
                    continue

                score = signal_scores[asset]
                weighted_return += score * weight
                contributions[signal_name] = score * weight
                total_weight += weight

            if total_weight > 0:
                weighted_return /= total_weight

            # Scale to annualized expected return
            # Typical signal range is -1 to 1, map to -15% to +15%
            annualized_return = weighted_return * 0.15

            # Get volatility estimate
            vol = self.DEFAULT_VOLATILITIES.get(asset, 0.15)

            # Calculate Sharpe estimate
            excess_return = annualized_return - self.RISK_FREE_RATE
            sharpe = excess_return / vol if vol > 0 else 0

            # Confidence based on signal agreement
            if len(contributions) > 1:
                # Higher confidence if signals agree
                signs = [np.sign(v) for v in contributions.values() if v != 0]
                if len(set(signs)) == 1:
                    confidence = 0.7  # All agree
                else:
                    confidence = 0.4  # Mixed signals
            else:
                confidence = 0.3

            expected_return = ExpectedReturn(
                asset_class=asset,
                expected_return=round(annualized_return, 4),
                confidence=round(confidence, 2),
                volatility_estimate=vol,
                sharpe_estimate=round(sharpe, 2),
                signal_contributions=contributions,
                time_horizon="medium",  # Default
            )

            results[asset] = expected_return

            # Store history
            if asset not in self.return_history:
                self.return_history[asset] = []
            self.return_history[asset].append(expected_return)

        return results

    def calculate_alpha_factors(
        self,
        data: pd.DataFrame,
        factor_definitions: Dict[str, Dict],
    ) -> pd.DataFrame:
        """
        Calculate alpha factor scores.

        Args:
            data: DataFrame with raw data
            factor_definitions: Dict of factor_name to definition

        Returns:
            DataFrame with alpha factor scores
        """
        alphas = pd.DataFrame(index=data.index)

        for factor_name, definition in factor_definitions.items():
            # Extract definition parameters
            inputs = definition.get("inputs", [])
            transform = definition.get("transform", "zscore")
            neutralize = definition.get("neutralize", None)

            # Calculate raw factor
            if len(inputs) == 1:
                raw_factor = data[inputs[0]]
            else:
                # Combine multiple inputs
                weights = definition.get("input_weights", [1.0 / len(inputs)] * len(inputs))
                raw_factor = sum(data[inputs[i]] * weights[i] for i in range(len(inputs)))

            # Apply transform
            if transform == "zscore":
                factor = (raw_factor - raw_factor.mean()) / raw_factor.std()
            elif transform == "rank":
                factor = raw_factor.rank(pct=True) * 2 - 1  # -1 to 1
            elif transform == "percentile":
                factor = raw_factor.rank(pct=True)
            else:
                factor = raw_factor

            # Neutralize if specified
            if neutralize:
                # Simple sector neutralization
                factor = factor - factor.groupby(data[neutralize]).transform("mean")

            alphas[factor_name] = factor

        return alphas

    def combine_alpha_factors(
        self,
        alphas: pd.DataFrame,
        factor_weights: Dict[str, float],
        factor_ic: Optional[Dict[str, float]] = None,
    ) -> pd.Series:
        """
        Combine multiple alpha factors into composite score.

        Args:
            alphas: DataFrame with alpha factor scores
            factor_weights: Dict of factor to weight
            factor_ic: Optional factor IC for optimization

        Returns:
            Series with composite alpha scores
        """
        # Normalize weights
        total_weight = sum(factor_weights.values())
        weights = {k: v / total_weight for k, v in factor_weights.items()}

        # If IC provided, optimize weights
        if factor_ic:
            # Weight by IC / volatility (simplified)
            ic_weights = {
                k: factor_ic.get(k, 0) / alphas[k].std()
                for k in weights.keys()
            }
            total_ic = sum(abs(v) for v in ic_weights.values())
            if total_ic > 0:
                weights = {k: abs(v) / total_ic for k, v in ic_weights.items()}

        # Calculate composite
        composite = pd.Series(0.0, index=alphas.index)
        for factor, weight in weights.items():
            if factor in alphas.columns:
                composite += alphas[factor] * weight

        return composite

    def generate_return_forecast_report(
        self,
        expected_returns: Dict[str, ExpectedReturn],
    ) -> Dict:
        """Generate comprehensive return forecast report."""
        # Sort by Sharpe ratio
        sorted_returns = sorted(
            expected_returns.values(),
            key=lambda x: x.sharpe_estimate,
            reverse=True,
        )

        total_expected_return = np.mean([r.expected_return for r in expected_returns.values()])

        return {
            "summary": {
                "assets_covered": len(expected_returns),
                "avg_expected_return": round(total_expected_return, 4),
                "risk_free_rate": self.RISK_FREE_RATE,
            },
            "asset_forecasts": [
                {
                    "asset": r.asset_class,
                    "expected_return": r.expected_return,
                    "volatility": r.volatility_estimate,
                    "sharpe": r.sharpe_estimate,
                    "confidence": r.confidence,
                    "time_horizon": r.time_horizon,
                }
                for r in sorted_returns
            ],
            "top_opportunities": [
                {
                    "asset": r.asset_class,
                    "expected_return": r.expected_return,
                    "rationale": f"Sharpe ratio: {r.sharpe_estimate}",
                }
                for r in sorted_returns[:3] if r.sharpe_estimate > 0.3
            ],
            "risk_warnings": [
                {
                    "asset": r.asset_class,
                    "expected_return": r.expected_return,
                    "rationale": f"Negative Sharpe: {r.sharpe_estimate}",
                }
                for r in sorted_returns[-3:] if r.sharpe_estimate < 0
            ],
        }


def estimate_factor_returns(
    factor_exposures: pd.DataFrame,
    asset_returns: pd.Series,
    method: str = "regression",
) -> Dict[str, float]:
    """
    Estimate factor returns from historical data.

    Args:
        factor_exposures: DataFrame of factor exposures
        asset_returns: Series of asset returns
        method: Estimation method

    Returns:
        Dict of factor to estimated return
    """
    if method == "regression":
        from sklearn.linear_model import Ridge

        # Ridge regression for stability
        model = Ridge(alpha=1.0)
        model.fit(factor_exposures, asset_returns)

        return dict(zip(factor_exposures.columns, model.coef_))

    elif method == "ic_weighted":
        # Weight by information coefficient
        ics = {}
        for factor in factor_exposures.columns:
            ic = np.corrcoef(factor_exposures[factor].shift(1).dropna(),
                             asset_returns[asset_returns.index.isin(factor_exposures[factor].shift(1).dropna().index)])[0, 1]
            ics[factor] = ic if not np.isnan(ic) else 0

        return ics

    else:
        return {factor: 0.0 for factor in factor_exposures.columns}
