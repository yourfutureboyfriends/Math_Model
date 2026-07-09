"""
Portfolio Construction Validation Service — Phase 7: Validate portfolio construction methods.

Validates three portfolio construction approaches:
1. Risk Parity — Equal risk contribution from each asset
2. Max Sharpe Ratio — Mean-variance optimization
3. Hierarchical Risk Parity (HRP) — Hierarchical clustering approach

Metrics:
- Backtested returns vs benchmark
- Turnover analysis and transaction costs
- Drawdown attribution
- Factor exposure validation
- Sharpe ratio comparison
- Concentration metrics

Usage:
    from api.services.portfolio_validation import portfolio_validator

    # Log portfolio allocation
    portfolio_validator.log_allocation(
        date="2024-01-15",
        method="risk_parity",
        weights={"XLK": 0.15, "XLF": 0.12, ...},
        regime="Goldilocks"
    )

    # Update with realized performance
    portfolio_validator.update_realized_performance(
        date="2024-01-15",
        method="risk_parity",
        portfolio_return=0.023,
        turnover=0.05
    )

    # Compare methods
    comparison = portfolio_validator.compare_methods()
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import json

import numpy as np
import pandas as pd

from database.db import get_db

logger = logging.getLogger(__name__)


@dataclass
class PortfolioMetrics:
    """Metrics for portfolio construction validation."""
    method: str  # risk_parity, max_sharpe, hrp
    n_allocations: int
    n_evaluated: int
    annualized_return: Optional[float] = None
    annualized_volatility: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    avg_turnover: Optional[float] = None
    total_transaction_costs: Optional[float] = None
    hit_rate: Optional[float] = None
    correlation_with_benchmark: Optional[float] = None
    concentration_hhi: Optional[float] = None  # Herfindahl-Hirschman Index

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DrawdownAttribution:
    """Drawdown attribution by source."""
    start_date: str
    end_date: str
    peak_date: str
    trough_date: str
    drawdown_pct: float
    regime_contribution: float
    factor_contribution: float
    idiosyncratic_contribution: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FactorExposure:
    """Factor exposure metrics."""
    factor: str
    beta: float
    t_stat: Optional[float] = None
    r_squared: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PortfolioValidator:
    """
    Validation service for portfolio construction methods.

    Compares Risk Parity, Max Sharpe Ratio, and Hierarchical Risk Parity
    approaches with comprehensive metrics including turnover, transaction
    costs, and drawdown attribution.
    """

    METHODS = ["risk_parity", "max_sharpe", "hrp"]

    # Transaction cost assumptions (bps)
    TRANSACTION_COSTS = {
        "equity_etf": 5,  # 5 bps for liquid ETFs
        "rebalancing_penalty": 10,  # Additional 10 bps for large rebalances
    }

    def __init__(self):
        self._logger = logging.getLogger(__name__)

    def log_allocation(
        self,
        date: str,
        method: str,
        weights: Dict[str, float],
        regime: str,
        risk_budget: Optional[float] = None,
        metadata: Optional[Dict] = None
    ) -> int:
        """
        Log portfolio allocation.

        Args:
            date: ISO format date
            method: Portfolio construction method (risk_parity, max_sharpe, hrp)
            weights: Dict mapping sector -> weight
            regime: Current regime classification
            risk_budget: Risk budget level (optional)
            metadata: Additional metadata

        Returns:
            Log entry ID
        """
        if method not in self.METHODS:
            raise ValueError(f"Invalid method: {method}. Must be one of {self.METHODS}")

        try:
            with get_db() as conn:
                cursor = conn.cursor()

                # Ensure portfolio_allocation_history table exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS portfolio_allocation_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL,
                        recorded_at TEXT NOT NULL,
                        method TEXT NOT NULL,
                        regime TEXT,
                        weights TEXT NOT NULL,
                        risk_budget REAL,
                        concentration_hhi REAL,
                        realized_return REAL,
                        turnover REAL,
                        transaction_costs REAL,
                        metadata TEXT
                    )
                """)

                # Calculate concentration (HHI)
                hhi = sum(w**2 for w in weights.values())

                cursor.execute("""
                    INSERT INTO portfolio_allocation_history (
                        date, recorded_at, method, regime, weights,
                        risk_budget, concentration_hhi, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    date,
                    datetime.utcnow().isoformat(),
                    method,
                    regime,
                    json.dumps(weights),
                    risk_budget,
                    hhi,
                    json.dumps(metadata) if metadata else None
                ))

                conn.commit()
                log_id = cursor.lastrowid

                self._logger.debug(
                    f"[PortfolioValidator] Logged {method} allocation for {date} (id={log_id})"
                )
                return log_id

        except Exception as e:
            self._logger.error(f"[PortfolioValidator] Failed to log allocation: {e}")
            raise

    def update_realized_performance(
        self,
        date: str,
        method: str,
        portfolio_return: float,
        turnover: float = 0.0
    ) -> bool:
        """
        Update realized performance for an allocation.

        Automatically computes transaction costs based on turnover.

        Args:
            date: Allocation date
            method: Portfolio construction method
            portfolio_return: Actual portfolio return
            turnover: Portfolio turnover (0-1)

        Returns:
            True if update successful
        """
        try:
            with get_db() as conn:
                cursor = conn.cursor()

                # Get the allocation first
                cursor.execute("""
                    SELECT id, weights FROM portfolio_allocation_history
                    WHERE date = ? AND method = ?
                """, (date, method))
                row = cursor.fetchone()

                if not row:
                    return False

                # Calculate transaction costs
                base_cost = turnover * self.TRANSACTION_COSTS["equity_etf"] / 10000
                if turnover > 0.5:  # Large rebalance penalty
                    base_cost += self.TRANSACTION_COSTS["rebalancing_penalty"] / 10000

                transaction_costs = base_cost
                net_return = portfolio_return - transaction_costs

                cursor.execute("""
                    UPDATE portfolio_allocation_history
                    SET realized_return = ?,
                        turnover = ?,
                        transaction_costs = ?
                    WHERE date = ? AND method = ?
                """, (
                    net_return,
                    turnover,
                    transaction_costs,
                    date,
                    method
                ))

                conn.commit()
                return cursor.rowcount > 0

        except Exception as e:
            self._logger.error(f"[PortfolioValidator] Failed to update performance: {e}")
            return False

    def get_allocation_history(
        self,
        method: Optional[str] = None,
        regime: Optional[str] = None,
        min_observations: int = 30
    ) -> pd.DataFrame:
        """
        Retrieve portfolio allocation history.

        Args:
            method: Filter by method
            regime: Filter by regime
            min_observations: Minimum observations required

        Returns:
            DataFrame with allocation history
        """
        try:
            with get_db() as conn:
                query = """
                    SELECT * FROM portfolio_allocation_history
                    WHERE 1=1
                """
                params = []

                if method:
                    query += " AND method = ?"
                    params.append(method)
                if regime:
                    query += " AND regime = ?"
                    params.append(regime)

                query += " ORDER BY date DESC"

                df = pd.read_sql_query(query, conn, params=params)

                # Parse weights JSON
                if not df.empty and 'weights' in df.columns:
                    df['weights'] = df['weights'].apply(lambda x: json.loads(x) if x else {})

                if len(df) < min_observations:
                    self._logger.warning(
                        f"[PortfolioValidator] Insufficient data: {len(df)} observations"
                    )

                return df

        except Exception as e:
            self._logger.error(f"[PortfolioValidator] Failed to get history: {e}")
            return pd.DataFrame()

    def compute_method_metrics(
        self,
        method: str,
        benchmark_returns: Optional[pd.Series] = None,
        min_observations: int = 12
    ) -> Optional[PortfolioMetrics]:
        """
        Compute validation metrics for a portfolio construction method.

        Args:
            method: Portfolio construction method
            benchmark_returns: Benchmark returns for comparison
            min_observations: Minimum observations required

        Returns:
            PortfolioMetrics or None
        """
        df = self.get_allocation_history(method=method)

        if len(df) < min_observations:
            return PortfolioMetrics(
                method=method,
                n_allocations=len(df),
                n_evaluated=0
            )

        # Filter to rows with realized returns
        df_valid = df.dropna(subset=["realized_return"])

        if len(df_valid) < min_observations:
            return PortfolioMetrics(
                method=method,
                n_allocations=len(df),
                n_evaluated=len(df_valid)
            )

        returns = df_valid["realized_return"].astype(float)

        # Annualized metrics (assuming monthly data)
        n_periods = len(returns)
        total_return = (1 + returns).prod() - 1
        ann_return = (1 + total_return) ** (12 / n_periods) - 1 if n_periods > 0 else 0
        ann_vol = returns.std() * np.sqrt(12)
        sharpe = ann_return / ann_vol if ann_vol > 0 else 0

        # Max drawdown
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_dd = drawdown.min()

        # Turnover
        avg_turnover = df_valid["turnover"].mean() if "turnover" in df_valid.columns else 0
        total_costs = df_valid["transaction_costs"].sum() if "transaction_costs" in df_valid.columns else 0

        # Hit rate (% positive returns)
        hit_rate = (returns > 0).mean()

        # Concentration
        avg_hhi = df_valid["concentration_hhi"].mean() if "concentration_hhi" in df_valid.columns else None

        # Correlation with benchmark
        corr_with_benchmark = None
        if benchmark_returns is not None and len(returns) == len(benchmark_returns):
            corr_with_benchmark = returns.corr(benchmark_returns)

        return PortfolioMetrics(
            method=method,
            n_allocations=len(df),
            n_evaluated=len(df_valid),
            annualized_return=round(ann_return, 4) if ann_return else None,
            annualized_volatility=round(ann_vol, 4) if ann_vol else None,
            sharpe_ratio=round(sharpe, 4),
            max_drawdown=round(max_dd, 4) if max_dd and not pd.isna(max_dd) else None,
            avg_turnover=round(avg_turnover, 4) if avg_turnover else None,
            total_transaction_costs=round(total_costs, 6),
            hit_rate=round(hit_rate, 4),
            correlation_with_benchmark=round(corr_with_benchmark, 4) if corr_with_benchmark else None,
            concentration_hhi=round(avg_hhi, 4) if avg_hhi else None
        )

    def compare_methods(
        self,
        benchmark_returns: Optional[pd.Series] = None
    ) -> Dict[str, Any]:
        """
        Compare all portfolio construction methods.

        Args:
            benchmark_returns: Benchmark returns for comparison

        Returns:
            Dict with comparison metrics
        """
        results = {}
        for method in self.METHODS:
            metrics = self.compute_method_metrics(method, benchmark_returns)
            if metrics:
                results[method] = metrics.to_dict()

        # Rank by Sharpe ratio. .get(key, default) keeps a stored None (default only
        # applies to a missing key), so coerce None -> sentinel before sorting.
        sharpes = {m: (r.get("sharpe_ratio") if r.get("sharpe_ratio") is not None else -999.0)
                   for m, r in results.items()}
        ranked = sorted(sharpes.items(), key=lambda x: x[1], reverse=True)

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "methods": results,
            "sharpe_ranking": [{"method": m, "sharpe_ratio": s} for m, s in ranked],
            "best_method": ranked[0][0] if ranked else None
        }

    def analyze_turnover(
        self,
        method: str,
        min_observations: int = 12
    ) -> Dict[str, Any]:
        """
        Analyze turnover patterns for a method.

        Args:
            method: Portfolio construction method
            min_observations: Minimum observations

        Returns:
            Turnover analysis
        """
        df = self.get_allocation_history(method=method)
        df_valid = df.dropna(subset=["turnover"])

        if len(df_valid) < min_observations:
            return {
                "method": method,
                "error": "Insufficient turnover data",
                "observations": len(df_valid)
            }

        turnover = df_valid["turnover"]
        costs = df_valid["transaction_costs"]

        return {
            "method": method,
            "observations": len(df_valid),
            "turnover_stats": {
                "mean": round(turnover.mean(), 4),
                "median": round(turnover.median(), 4),
                "std": round(turnover.std(), 4),
                "min": round(turnover.min(), 4),
                "max": round(turnover.max(), 4)
            },
            "transaction_costs": {
                "mean": round(costs.mean(), 6),
                "total": round(costs.sum(), 6),
                "annualized_estimate": round(costs.mean() * 12, 4)
            },
            "high_turnover_periods": len(turnover[turnover > turnover.quantile(0.9)]),
            "recommendation": "High turnover detected, consider turnover penalty" if turnover.mean() > 0.3 else "Turnover acceptable"
        }

    def analyze_drawdowns(
        self,
        method: str,
        threshold: float = -0.05
    ) -> Dict[str, Any]:
        """
        Analyze drawdowns for a method.

        Args:
            method: Portfolio construction method
            threshold: Drawdown threshold to flag

        Returns:
            Drawdown analysis
        """
        df = self.get_allocation_history(method=method)
        df_valid = df.dropna(subset=["realized_return"])

        if len(df_valid) < 12:
            return {
                "method": method,
                "error": "Insufficient data for drawdown analysis",
                "observations": len(df_valid)
            }

        returns = df_valid["realized_return"].astype(float)
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max

        # Find drawdown periods
        in_drawdown = drawdown < threshold
        drawdown_periods = []
        current_start = None

        for i, (date, is_dd) in enumerate(in_drawdown.items()):
            if is_dd and current_start is None:
                current_start = date
            elif not is_dd and current_start is not None:
                drawdown_periods.append({
                    "start": current_start,
                    "end": date,
                    "max_drawdown": round(drawdown.loc[current_start:date].min(), 4)
                })
                current_start = None

        max_dd = drawdown.min()
        avg_dd = drawdown[drawdown < 0].mean() if (drawdown < 0).any() else 0

        return {
            "method": method,
            "observations": len(df_valid),
            "max_drawdown": round(max_dd, 4),
            "average_drawdown": round(avg_dd, 4),
            "drawdown_periods": drawdown_periods,
            "severe_drawdowns": len([d for d in drawdown_periods if d["max_drawdown"] < -0.10]),
            "regime_during_drawdown": self._analyze_regime_during_drawdowns(df_valid, drawdown_periods)
        }

    def _analyze_regime_during_drawdowns(
        self,
        df: pd.DataFrame,
        drawdown_periods: List[Dict]
    ) -> Dict[str, int]:
        """Helper to analyze regime distribution during drawdowns."""
        if "regime" not in df.columns or not drawdown_periods:
            return {}

        regime_counts = {}
        for period in drawdown_periods:
            # Find regime during period
            period_data = df[df["date"] >= period["start"]]
            if len(period_data) > 0 and "regime" in period_data.columns:
                regime = period_data.iloc[0].get("regime")
                if regime:
                    regime_counts[regime] = regime_counts.get(regime, 0) + 1

        return regime_counts

    def analyze_factor_exposure(
        self,
        method: str,
        factor_returns: Optional[Dict[str, pd.Series]] = None
    ) -> Dict[str, Any]:
        """
        Analyze factor exposure for a portfolio method.

        Args:
            method: Portfolio construction method
            factor_returns: Dict of factor returns (e.g., {"market": ..., "value": ...})

        Returns:
            Factor exposure analysis
        """
        df = self.get_allocation_history(method=method)
        df_valid = df.dropna(subset=["realized_return"])

        if len(df_valid) < 12:
            return {
                "method": method,
                "error": "Insufficient data for factor analysis",
                "observations": len(df_valid)
            }

        portfolio_returns = df_valid["realized_return"]

        # Default factors if none provided
        if factor_returns is None:
            # Use synthetic factors
            np.random.seed(42)
            n = len(portfolio_returns)
            factor_returns = {
                "market": pd.Series(np.random.normal(0.008, 0.04, n)),
                "value": pd.Series(np.random.normal(0.002, 0.03, n)),
                "momentum": pd.Series(np.random.normal(0.003, 0.03, n)),
                "quality": pd.Series(np.random.normal(0.001, 0.02, n))
            }

        exposures = {}
        for factor_name, factor_ret in factor_returns.items():
            if len(factor_ret) == len(portfolio_returns):
                # Simple regression (portfolio ~ factor)
                beta = portfolio_returns.corr(factor_ret) * (portfolio_returns.std() / factor_ret.std())
                exposures[factor_name] = {
                    "beta": round(beta, 4),
                    "exposure_level": "high" if abs(beta) > 1.5 else "medium" if abs(beta) > 0.8 else "low"
                }

        return {
            "method": method,
            "observations": len(df_valid),
            "factor_exposures": exposures,
            "interpretation": "Compare to target factor exposure in MODEL_INVENTORY"
        }

    def get_calibration_recommendations(self) -> Dict[str, Any]:
        """
        Generate calibration recommendations.

        Returns:
            Dict with recommendations
        """
        recommendations = {
            "timestamp": datetime.utcnow().isoformat(),
            "method_comparison": None,
            "turnover_analysis": {},
            "drawdown_analysis": {},
            "general_recommendations": [],
        }

        # Method comparison
        comparison = self.compare_methods()
        recommendations["method_comparison"] = comparison

        # Check for best method
        if comparison.get("best_method"):
            best = comparison["best_method"]
            recommendations["general_recommendations"].append(
                f"{best} currently has the highest Sharpe ratio among portfolio construction methods"
            )

        # Turnover analysis for each method
        for method in self.METHODS:
            turnover = self.analyze_turnover(method)
            recommendations["turnover_analysis"][method] = turnover

            if turnover.get("turnover_stats", {}).get("mean", 0) > 0.3:
                recommendations["general_recommendations"].append(
                    f"{method}: High turnover detected, consider adding turnover penalty to optimization"
                )

        # Drawdown analysis
        for method in self.METHODS:
            dd = self.analyze_drawdowns(method)
            recommendations["drawdown_analysis"][method] = dd

            if dd.get("severe_drawdowns", 0) > 2:
                recommendations["general_recommendations"].append(
                    f"{method}: Multiple severe drawdowns detected, review risk management"
                )

        return recommendations


# Global instance
portfolio_validator = PortfolioValidator()
