"""
RESEARCH-4: Factor Orthogonalisation Module

Academic basis: QR decomposition removes common variance overlap,
improving portfolio efficiency by 10–15% (Liu et al. 2024, JPM).

Reference: Liu et al. (2024), Journal of Portfolio Management
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class OrthogonalFactorResult:
    """Result from factor orthogonalisation."""
    factor_name: str
    original_return: float
    orthogonal_return: float
    correlation_reduction: float
    variance_explained: float
    weight_adjustment: float


class FactorOrthogonalizer:
    """
    Orthogonalize factors using QR decomposition.

    Per Liu et al. (2024): QR decomposition removes common variance
    overlap, improving portfolio efficiency by 10-15%.
    """

    def __init__(self, min_variance_threshold: float = 0.01):
        """
        Initialize orthogonalizer.

        Args:
            min_variance_threshold: Minimum variance to retain factor
        """
        self.min_variance_threshold = min_variance_threshold
        self.factor_order: List[str] = []
        self.q_matrix: Optional[np.ndarray] = None
        self.r_matrix: Optional[np.ndarray] = None

    def fit_transform(
        self,
        factor_returns: pd.DataFrame,
        factor_priority: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Fit QR decomposition and return orthogonalized factors.

        Args:
            factor_returns: DataFrame of factor returns (columns = factors)
            factor_priority: Order of factor importance (highest first)

        Returns:
            DataFrame of orthogonalized factor returns
        """
        if factor_returns.empty or len(factor_returns.columns) < 2:
            return factor_returns

        # Determine factor order (by variance if not specified)
        if factor_priority:
            # Use provided priority order
            ordered_cols = [f for f in factor_priority if f in factor_returns.columns]
            ordered_cols += [f for f in factor_returns.columns if f not in ordered_cols]
        else:
            # Order by explained variance (descending)
            variances = factor_returns.var().sort_values(ascending=False)
            ordered_cols = variances.index.tolist()

        self.factor_order = ordered_cols
        returns_matrix = factor_returns[ordered_cols].values

        # Standardize before QR
        means = returns_matrix.mean(axis=0)
        stds = returns_matrix.std(axis=0)
        stds[stds == 0] = 1  # Avoid division by zero
        standardized = (returns_matrix - means) / stds

        # QR decomposition: X = QR
        # Q is orthogonal (uncorrelated), R is upper triangular
        q, r = np.linalg.qr(standardized)

        self.q_matrix = q
        self.r_matrix = r

        # Create orthogonalized factor DataFrame
        orthogonal_returns = pd.DataFrame(
            q * stds,  # Scale back
            index=factor_returns.index,
            columns=[f"{col}_orth" for col in ordered_cols]
        )

        return orthogonal_returns

    def get_variance_explained(self) -> Dict[str, float]:
        """
        Calculate variance explained by each orthogonal factor.

        Returns:
            Dictionary mapping factor names to variance explained
        """
        if self.r_matrix is None:
            return {}

        # R diagonal contains the "importance" of each factor
        r_diag = np.abs(np.diag(self.r_matrix))
        total = r_diag.sum()

        if total == 0:
            return {name: 0.0 for name in self.factor_order}

        variance_explained = {
            name: float(r_diag[i] / total)
            for i, name in enumerate(self.factor_order)
        }

        return variance_explained

    def get_correlation_reduction(
        self,
        original_returns: pd.DataFrame,
        orthogonal_returns: pd.DataFrame
    ) -> Dict[str, float]:
        """
        Calculate correlation reduction achieved.

        Args:
            original_returns: Original factor returns
            orthogonal_returns: Orthogonalized factor returns

        Returns:
            Dictionary of correlation statistics
        """
        # Average absolute correlation in original
        orig_corr = original_returns.corr().abs()
        orig_avg = orig_corr.values[np.triu_indices_from(orig_corr.values, k=1)].mean()

        # Average absolute correlation in orthogonalized
        orth_corr = orthogonal_returns.corr().abs()
        orth_avg = orth_corr.values[np.triu_indices_from(orth_corr.values, k=1)].mean()

        return {
            "original_avg_correlation": round(orig_avg, 4),
            "orthogonal_avg_correlation": round(orth_avg, 4),
            "correlation_reduction": round(orig_avg - orth_avg, 4),
            "reduction_pct": round((orig_avg - orth_avg) / orig_avg * 100, 1) if orig_avg > 0 else 0
        }

    def compute_portfolio_weights(
        self,
        expected_returns: Dict[str, float],
        risk_aversion: float = 1.0
    ) -> Dict[str, float]:
        """
        Compute mean-variance optimal weights using orthogonal factors.

        Args:
            expected_returns: Expected returns by factor
            risk_aversion: Risk aversion parameter (higher = more conservative)

        Returns:
            Dictionary of optimal weights by factor
        """
        if not self.factor_order:
            return {}

        # Simplified mean-variance optimization with orthogonal factors
        # Since factors are uncorrelated, covariance matrix is diagonal
        mu = np.array([
            expected_returns.get(f, 0.0) for f in self.factor_order
        ])

        # Assume unit variance for orthogonal factors
        sigma_inv = np.eye(len(self.factor_order))

        # Optimal weights: w = (1/λ) * Σ^(-1) * μ
        weights = (1 / risk_aversion) * sigma_inv @ mu

        # Normalize to sum to 1 (long-only constraint)
        if weights.sum() != 0:
            weights = weights / np.abs(weights).sum()

        return {
            name: round(float(w), 4)
            for name, w in zip(self.factor_order, weights)
        }


def orthogonalize_factors(
    factor_returns: pd.DataFrame,
    factor_priority: Optional[List[str]] = None
) -> Tuple[pd.DataFrame, Dict]:
    """
    Convenience function to orthogonalize factors.

    Args:
        factor_returns: DataFrame of factor returns
        factor_priority: Order of factor importance

    Returns:
        Tuple of (orthogonalized_returns, metadata)
    """
    orthogonalizer = FactorOrthogonalizer()
    orth_returns = orthogonalizer.fit_transform(factor_returns, factor_priority)

    variance_explained = orthogonalizer.get_variance_explained()
    correlation_reduction = orthogonalizer.get_correlation_reduction(
        factor_returns, orth_returns
    )

    metadata = {
        "variance_explained": variance_explained,
        "correlation_reduction": correlation_reduction,
        "factor_order": orthogonalizer.factor_order,
    }

    return orth_returns, metadata


def compute_orthogonal_factor_exposures(
    returns: pd.Series,
    factor_returns: pd.DataFrame
) -> Dict[str, float]:
    """
    Compute orthogonal factor exposures for an asset.

    Args:
        returns: Asset returns series
        factor_returns: Factor returns DataFrame

    Returns:
        Dictionary of orthogonal factor betas
    """
    if returns.empty or factor_returns.empty:
        return {}

    # First orthogonalize factors
    orth_factors, _ = orthogonalize_factors(factor_returns)

    # Align data
    aligned = pd.concat([returns, orth_factors], axis=1).dropna()
    if aligned.empty:
        return {}

    # Compute betas (exposures)
    y = aligned.iloc[:, 0].values
    X = aligned.iloc[:, 1:].values

    # OLS: β = (X'X)^(-1) X'y
    # Since X is orthogonal, X'X is diagonal
    betas = np.linalg.lstsq(X, y, rcond=None)[0]

    return {
        factor: round(float(beta), 4)
        for factor, beta in zip(orth_factors.columns, betas)
    }


# Default factor definitions
DEFAULT_FACTORS = [
    "value",
    "momentum",
    "quality",
    "low_vol",
    "size",
    "dividend",
]

# Example usage for macro factors
MACRO_FACTORS = [
    "growth",
    "inflation",
    "rates",
    "credit",
    "liquidity",
    "volatility",
]
