"""
Risk Budgeting

Implements risk parity and risk budgeting portfolio construction.

Key concepts:
- Risk parity: Equal risk contribution from each asset
- Risk budgeting: Target specific risk contributions
- Risk clustering: Group assets by risk similarity
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize

logger = logging.getLogger(__name__)


@dataclass
class RiskBudget:
    """Risk budget allocation for an asset."""
    asset: str
    target_risk_contribution: float  # As % of total portfolio risk
    current_risk_contribution: float
    deviation: float


class RiskBudgetingEngine:
    """
    Construct portfolios using risk budgeting approach.

    Risk budgeting explicitly allocates risk rather than capital.
    """

    def __init__(self):
        self.risk_budgets: Dict[str, float] = {}
        self.risk_target: float = 0.10  # 10% annual volatility

    def set_risk_budgets(self, budgets: Dict[str, float]) -> None:
        """
        Set target risk budgets by asset.

        Args:
            budgets: Dict of asset to target risk contribution (should sum to 1)
        """
        total = sum(budgets.values())
        if abs(total - 1.0) > 0.01:
            logger.warning(f"Risk budgets sum to {total}, normalizing")
            budgets = {k: v / total for k, v in budgets.items()}

        self.risk_budgets = budgets
        logger.info(f"Set risk budgets: {budgets}")

    def calculate_risk_contributions(
        self,
        weights: np.ndarray,
        cov_matrix: np.ndarray,
    ) -> np.ndarray:
        """
        Calculate marginal risk contribution for each asset.

        Args:
            weights: Portfolio weights
            cov_matrix: Covariance matrix

        Returns:
            Risk contributions as array
        """
        port_vol = np.sqrt(weights @ cov_matrix @ weights)

        if port_vol == 0:
            return np.zeros_like(weights)

        # Marginal contribution to risk
        mcr = (cov_matrix @ weights) / port_vol

        # Component contribution to risk
        ccr = weights * mcr

        return ccr

    def calculate_risk_parity_weights(
        self,
        cov_matrix: np.ndarray,
        asset_names: List[str],
        max_weight: float = 0.30,
        min_weight: float = 0.01,
    ) -> Dict[str, float]:
        """
        Calculate risk parity weights.

        Risk parity equalizes risk contribution across assets.

        Args:
            cov_matrix: Covariance matrix
            asset_names: List of asset names
            max_weight: Maximum weight constraint
            min_weight: Minimum weight constraint

        Returns:
            Dict of asset to weight
        """
        n = len(asset_names)

        # Objective: minimize difference between risk contributions
        def objective(weights):
            if np.sum(weights) == 0:
                return 1e10

            rc = self.calculate_risk_contributions(weights, cov_matrix)
            port_vol = np.sqrt(weights @ cov_matrix @ weights)

            if port_vol == 0:
                return 1e10

            # Target: equal risk contribution
            target_rc = port_vol / n
            return np.sum((rc - target_rc) ** 2)

        # Constraints
        constraints = [
            {"type": "eq", "fun": lambda w: np.sum(w) - 1},  # Sum to 1
        ]

        # Bounds
        bounds = [(min_weight, max_weight) for _ in range(n)]

        # Initial guess (inverse volatility)
        inv_vols = 1 / np.sqrt(np.diag(cov_matrix))
        init_weights = inv_vols / np.sum(inv_vols)

        # Optimize
        result = minimize(
            objective,
            init_weights,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
        )

        if result.success:
            weights = result.x
            return {asset: round(w, 4) for asset, w in zip(asset_names, weights)}
        else:
            logger.error(f"Risk parity optimization failed: {result.message}")
            # Fallback to inverse volatility
            weights = init_weights / np.sum(init_weights)
            return {asset: round(w, 4) for asset, w in zip(asset_names, weights)}

    def calculate_risk_budget_weights(
        self,
        cov_matrix: np.ndarray,
        asset_names: List[str],
        risk_budgets: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """
        Calculate weights to match target risk budgets.

        Args:
            cov_matrix: Covariance matrix
            asset_names: List of asset names
            risk_budgets: Target risk budgets (if None, use equal)

        Returns:
            Dict of asset to weight
        """
        n = len(asset_names)

        if risk_budgets is None:
            risk_budgets = {asset: 1.0 / n for asset in asset_names}

        # Normalize budgets
        total_budget = sum(risk_budgets.values())
        budgets = np.array([risk_budgets.get(asset, 0) / total_budget for asset in asset_names])

        # Objective: match risk contributions to budgets
        def objective(weights):
            if np.sum(weights) == 0:
                return 1e10

            rc = self.calculate_risk_contributions(weights, cov_matrix)
            port_vol = np.sqrt(weights @ cov_matrix @ weights)

            if port_vol == 0:
                return 1e10

            # Target risk contributions
            target_rc = budgets * port_vol
            return np.sum((rc - target_rc) ** 2)

        # Constraints
        constraints = [
            {"type": "eq", "fun": lambda w: np.sum(w) - 1},
        ]

        # Bounds
        bounds = [(0.0, 0.40) for _ in range(n)]

        # Initial guess
        init_weights = budgets / np.sum(budgets)

        # Optimize
        result = minimize(
            objective,
            init_weights,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
        )

        if result.success:
            weights = result.x
            return {asset: round(w, 4) for asset, w in zip(asset_names, weights)}
        else:
            logger.error(f"Risk budget optimization failed: {result.message}")
            return {asset: round(b, 4) for asset, b in zip(asset_names, budgets)}

    def calculate_diversification_ratio(
        self,
        weights: np.ndarray,
        cov_matrix: np.ndarray,
    ) -> float:
        """
        Calculate diversification ratio.

        DR = Weighted average vol / Portfolio vol
        Higher is better (more diversification)

        Args:
            weights: Portfolio weights
            cov_matrix: Covariance matrix

        Returns:
            Diversification ratio
        """
        weighted_vol = np.sum(weights * np.sqrt(np.diag(cov_matrix)))
        port_vol = np.sqrt(weights @ cov_matrix @ weights)

        return weighted_vol / port_vol if port_vol > 0 else 0

    def cluster_assets(
        self,
        returns: pd.DataFrame,
        n_clusters: int = 4,
    ) -> Dict[str, int]:
        """
        Cluster assets by return correlation.

        Args:
            returns: DataFrame of asset returns
            n_clusters: Number of clusters

        Returns:
            Dict of asset to cluster_id
        """
        from sklearn.cluster import AgglomerativeClustering

        # Calculate correlation matrix
        corr = returns.corr()

        # Convert to distance matrix
        distance = 1 - np.abs(corr)

        # Cluster
        clustering = AgglomerativeClustering(
            n_clusters=n_clusters,
            linkage="average",
            metric="precomputed",
        )
        labels = clustering.fit_predict(distance)

        return dict(zip(returns.columns, labels))

    def hierarchical_risk_parity(
        self,
        returns: pd.DataFrame,
    ) -> Dict[str, float]:
        """
        Hierarchical Risk Parity (Marcos Lopez de Prado).

        Uses hierarchical clustering to allocate risk.

        Args:
            returns: DataFrame of asset returns

        Returns:
            Dict of asset to weight
        """
        # Step 1: Cluster assets
        clusters = self.cluster_assets(returns)

        # Step 2: Calculate inverse variance weights within each cluster
        cluster_weights = {}
        vols = returns.std()

        for cluster_id in set(clusters.values()):
            cluster_assets = [a for a, c in clusters.items() if c == cluster_id]
            inv_vols = 1 / vols[cluster_assets]
            cluster_weights[cluster_id] = inv_vols / inv_vols.sum()

        # Step 3: Calculate cluster-level weights (inverse variance of clusters)
        cluster_returns = {}
        for cluster_id, weights in cluster_weights.items():
            cluster_assets = [a for a, c in clusters.items() if c == cluster_id]
            cluster_returns[cluster_id] = (returns[cluster_assets] * weights).sum(axis=1)

        cluster_ret_df = pd.DataFrame(cluster_returns)
        cluster_vols = cluster_ret_df.std()
        inv_cluster_vols = 1 / cluster_vols
        cluster_allocations = inv_cluster_vols / inv_cluster_vols.sum()

        # Step 4: Final weights
        final_weights = {}
        for cluster_id, allocation in cluster_allocations.items():
            for asset in [a for a, c in clusters.items() if c == cluster_id]:
                final_weights[asset] = allocation * cluster_weights[cluster_id][asset]

        return {k: round(v, 4) for k, v in final_weights.items()}

    def generate_risk_report(
        self,
        weights: Dict[str, float],
        cov_matrix: pd.DataFrame,
    ) -> Dict:
        """Generate risk decomposition report."""
        w = np.array([weights.get(a, 0) for a in cov_matrix.index])

        port_vol = np.sqrt(w @ cov_matrix.values @ w)
        risk_contributions = self.calculate_risk_contributions(w, cov_matrix.values)

        # Risk contribution percentages
        rc_pct = risk_contributions / port_vol if port_vol > 0 else np.zeros_like(risk_contributions)

        report = {
            "portfolio_volatility": round(port_vol, 4),
            "annualized_volatility": round(port_vol * np.sqrt(252), 4),
            "diversification_ratio": round(self.calculate_diversification_ratio(w, cov_matrix.values()), 2),
            "risk_contributions": {
                asset: {
                    "absolute": round(float(rc), 4),
                    "percentage": round(float(rc_pct[i]), 4),
                }
                for i, (asset, rc) in enumerate(zip(cov_matrix.index, risk_contributions))
            },
        }

        # Identify risk concentrations
        max_rc = max(rc_pct)
        if max_rc > 0.4:
            report["warning"] = f"High risk concentration: {cov_matrix.index[np.argmax(rc_pct)]} at {max_rc:.1%}"

        return report


def calculate_maximum_diversification_weights(
    cov_matrix: pd.DataFrame,
) -> Dict[str, float]:
    """
    Calculate maximum diversification portfolio.

    Maximizes diversification ratio.

    Args:
        cov_matrix: Covariance matrix

    Returns:
        Dict of asset to weight
    """
    n = len(cov_matrix)

    def diversification_ratio(weights):
        w = np.array(weights)
        vols = np.sqrt(np.diag(cov_matrix.values))
        port_vol = np.sqrt(w @ cov_matrix.values @ w)
        return -(w @ vols) / port_vol if port_vol > 0 else 0

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
    bounds = [(0, 1) for _ in range(n)]
    init = np.ones(n) / n

    result = minimize(diversification_ratio, init, method="SLSQP", bounds=bounds, constraints=constraints)

    if result.success:
        weights = result.x
        return {asset: round(w, 4) for asset, w in zip(cov_matrix.index, weights)}
    else:
        return {asset: 1.0 / n for asset in cov_matrix.index}
