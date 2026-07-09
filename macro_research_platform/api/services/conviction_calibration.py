"""
Conviction Calibration Service — Phase 4: Validate conviction scoring.

Validates that higher conviction scores lead to better realized outcomes:
1. Conviction components: regime confidence, recession agreement, signal dispersion
2. Bucket forecasts by conviction score
3. Measure realized forward Sharpe in each bucket
4. Validate monotonicity: higher conviction → better outcomes

Usage:
    from api.services.conviction_calibration import conviction_calibrator

    # Log conviction with forecast
    conviction_calibrator.log_conviction(
        date="2024-01-15",
        conviction_score=0.75,
        components={
            "regime_confidence": 0.8,
            "recession_agreement": 0.7,
            "signal_dispersion": 0.6,
        },
        risk_budget=0.75
    )

    # Update with realized return
    conviction_calibrator.update_realized_return("2024-01-15", 0.025)

    # Analyze calibration
    calibration = conviction_calibrator.analyze_calibration()

    # Check monotonicity
    monotonicity = conviction_calibrator.test_monotonicity()
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
class ConvictionComponents:
    """Components of conviction score."""
    regime_confidence: float = 0.5
    recession_agreement: float = 0.5
    signal_dispersion: float = 0.5
    momentum_confirmation: float = 0.5
    volatility_stability: float = 0.5

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass
class ConvictionBucket:
    """Metrics for a conviction bucket."""
    bucket_name: str
    min_score: float
    max_score: float
    n_forecasts: int
    avg_conviction: float
    avg_realized_return: Optional[float] = None
    realized_volatility: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    hit_rate: Optional[float] = None
    monotonic_rank: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ConvictionCalibrator:
    """
    Calibration service for conviction scoring.

    Validates that conviction scores are well-calibrated by:
    1. Bucketing forecasts by conviction level
    2. Measuring realized outcomes in each bucket
    3. Testing for monotonicity (higher conviction → better outcomes)
    4. Providing calibration recommendations
    """

    # Default conviction bucket boundaries
    DEFAULT_BUCKETS = [
        (0.0, 0.3, "LOW"),
        (0.3, 0.6, "MEDIUM"),
        (0.6, 1.0, "HIGH"),
    ]

    def __init__(self):
        self._logger = logging.getLogger(__name__)
        self._buckets = self.DEFAULT_BUCKETS

    def log_conviction(
        self,
        date: str,
        conviction_score: float,
        components: Dict[str, float],
        risk_budget: float,
        forecast_horizon: str = "1M",
        metadata: Optional[Dict] = None
    ) -> int:
        """
        Log conviction score with components.

        Args:
            date: ISO format date
            conviction_score: Overall conviction (0-1)
            components: Dict of component scores
            risk_budget: Risk budget assigned
            forecast_horizon: Forecast horizon ("1M", "3M", "6M", "12M")
            metadata: Additional metadata

        Returns:
            Log entry ID
        """
        try:
            with get_db() as conn:
                cursor = conn.cursor()

                # Ensure conviction_history table exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS conviction_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL,
                        recorded_at TEXT NOT NULL,
                        conviction_score REAL NOT NULL,
                        regime_confidence REAL,
                        recession_agreement REAL,
                        signal_dispersion REAL,
                        momentum_confirmation REAL,
                        volatility_stability REAL,
                        risk_budget REAL,
                        forecast_horizon TEXT,
                        realized_return_1m REAL,
                        realized_return_3m REAL,
                        realized_return_6m REAL,
                        realized_return_12m REAL,
                        metadata TEXT
                    )
                """)

                cursor.execute("""
                    INSERT INTO conviction_history (
                        date, recorded_at, conviction_score,
                        regime_confidence, recession_agreement, signal_dispersion,
                        momentum_confirmation, volatility_stability,
                        risk_budget, forecast_horizon, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    date,
                    datetime.utcnow().isoformat(),
                    conviction_score,
                    components.get('regime_confidence'),
                    components.get('recession_agreement'),
                    components.get('signal_dispersion'),
                    components.get('momentum_confirmation'),
                    components.get('volatility_stability'),
                    risk_budget,
                    forecast_horizon,
                    json.dumps(metadata) if metadata else None
                ))

                conn.commit()
                log_id = cursor.lastrowid

                self._logger.debug(f"[ConvictionCalibrator] Logged conviction for {date} (id={log_id})")
                return log_id

        except Exception as e:
            self._logger.error(f"[ConvictionCalibrator] Failed to log conviction: {e}")
            raise

    def update_realized_return(
        self,
        date: str,
        realized_return: float,
        horizon: str = "1M"
    ) -> bool:
        """
        Update realized return for a historical conviction entry.

        Args:
            date: Date of forecast
            realized_return: Actual realized return
            horizon: Which horizon to update ("1M", "3M", "6M", "12M")

        Returns:
            True if update successful
        """
        column_map = {
            "1M": "realized_return_1m",
            "3M": "realized_return_3m",
            "6M": "realized_return_6m",
            "12M": "realized_return_12m",
        }

        column = column_map.get(horizon)
        if not column:
            self._logger.error(f"[ConvictionCalibrator] Invalid horizon: {horizon}")
            return False

        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    UPDATE conviction_history
                    SET {column} = ?
                    WHERE date = ?
                """, (realized_return, date))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            self._logger.error(f"[ConvictionCalibrator] Failed to update return: {e}")
            return False

    def get_conviction_history(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        min_observations: int = 30
    ) -> pd.DataFrame:
        """
        Retrieve conviction history with realized returns.

        Args:
            start_date: Start date filter
            end_date: End date filter
            min_observations: Minimum observations required

        Returns:
            DataFrame with conviction history
        """
        try:
            with get_db() as conn:
                query = """
                    SELECT * FROM conviction_history
                    WHERE conviction_score IS NOT NULL
                """
                params = []

                if start_date:
                    query += " AND date >= ?"
                    params.append(start_date)
                if end_date:
                    query += " AND date <= ?"
                    params.append(end_date)

                query += " ORDER BY date DESC"

                df = pd.read_sql_query(query, conn, params=params)

                if len(df) < min_observations:
                    self._logger.warning(
                        f"[ConvictionCalibrator] Insufficient data: {len(df)} observations "
                        f"(need {min_observations})"
                    )

                return df

        except Exception as e:
            self._logger.error(f"[ConvictionCalibrator] Failed to get history: {e}")
            return pd.DataFrame()

    def compute_conviction_buckets(
        self,
        horizon: str = "1M",
        custom_buckets: Optional[List[Tuple[float, float, str]]] = None
    ) -> List[ConvictionBucket]:
        """
        Compute metrics for each conviction bucket.

        Args:
            horizon: Which horizon to analyze ("1M", "3M", "6M", "12M")
            custom_buckets: Optional custom bucket definitions

        Returns:
            List of ConvictionBucket with realized outcomes
        """
        buckets_def = custom_buckets or self._buckets
        df = self.get_conviction_history()

        return_column = f"realized_return_{horizon.lower()}"
        if return_column not in df.columns:
            self._logger.error(f"[ConvictionCalibrator] Return column {return_column} not found")
            return []

        # Filter to rows with realized returns
        df_valid = df.dropna(subset=[return_column, 'conviction_score'])

        if len(df_valid) < 10:
            self._logger.warning(f"[ConvictionCalibrator] Insufficient realized data: {len(df_valid)}")
            return []

        bucket_results = []

        for i, (min_score, max_score, name) in enumerate(buckets_def):
            mask = (df_valid['conviction_score'] >= min_score) & \
                   (df_valid['conviction_score'] < max_score)
            bucket_df = df_valid[mask]

            if len(bucket_df) < 3:
                # Empty bucket
                bucket_results.append(ConvictionBucket(
                    bucket_name=name,
                    min_score=min_score,
                    max_score=max_score,
                    n_forecasts=len(bucket_df),
                    avg_conviction=bucket_df['conviction_score'].mean() if len(bucket_df) > 0 else (min_score + max_score) / 2,
                ))
                continue

            returns = bucket_df[return_column].astype(float)
            avg_return = returns.mean()
            volatility = returns.std()
            sharpe = avg_return / volatility if volatility > 0 else 0
            hit_rate = (returns > 0).mean()

            bucket_results.append(ConvictionBucket(
                bucket_name=name,
                min_score=min_score,
                max_score=max_score,
                n_forecasts=len(bucket_df),
                avg_conviction=bucket_df['conviction_score'].mean(),
                avg_realized_return=round(avg_return, 4),
                realized_volatility=round(volatility, 4),
                sharpe_ratio=round(sharpe, 4),
                hit_rate=round(hit_rate, 4),
                monotonic_rank=i + 1,
            ))

        return bucket_results

    def test_monotonicity(
        self,
        horizon: str = "1M"
    ) -> Dict[str, Any]:
        """
        Test if higher conviction leads to better outcomes (monotonicity).

        Args:
            horizon: Which horizon to analyze

        Returns:
            Dict with monotonicity test results
        """
        buckets = self.compute_conviction_buckets(horizon)

        if len(buckets) < 2:
            return {
                "test": "monotonicity",
                "passed": False,
                "reason": "Insufficient buckets for test",
                "buckets_available": len(buckets),
            }

        # Filter to buckets with data
        valid_buckets = [b for b in buckets if b.avg_realized_return is not None]

        if len(valid_buckets) < 2:
            return {
                "test": "monotonicity",
                "passed": False,
                "reason": "Insufficient buckets with realized data",
                "buckets_with_data": len(valid_buckets),
            }

        # Check if Sharpe ratios increase with conviction
        shapres = [b.sharpe_ratio for b in valid_buckets if b.sharpe_ratio is not None]
        returns = [b.avg_realized_return for b in valid_buckets if b.avg_realized_return is not None]

        # Spearman rank correlation (should be positive)
        try:
            from scipy import stats
            ranks = list(range(1, len(valid_buckets) + 1))
            spearman_sharpe, p_value_sharpe = stats.spearmanr(ranks, shapres)
            spearman_return, p_value_return = stats.spearmanr(ranks, returns)
        except ImportError:
            # Fallback without scipy
            spearman_sharpe = self._manual_rank_correlation(ranks, shapres)
            spearman_return = self._manual_rank_correlation(ranks, returns)
            p_value_sharpe = None
            p_value_return = None

        # Monotonicity check: count violations
        violations = 0
        for i in range(len(valid_buckets) - 1):
            if valid_buckets[i].sharpe_ratio and valid_buckets[i+1].sharpe_ratio:
                if valid_buckets[i].sharpe_ratio > valid_buckets[i+1].sharpe_ratio:
                    violations += 1

        monotonicity_score = 1.0 - (violations / max(1, len(valid_buckets) - 1))

        # Determine if passed
        passed = monotonicity_score >= 0.7 and spearman_sharpe > 0

        return {
            "test": "monotonicity",
            "horizon": horizon,
            "passed": passed,
            "monotonicity_score": round(monotonicity_score, 4),
            "spearman_sharpe": round(spearman_sharpe, 4) if spearman_sharpe else None,
            "p_value_sharpe": round(p_value_sharpe, 4) if p_value_sharpe else None,
            "spearman_return": round(spearman_return, 4) if spearman_return else None,
            "p_value_return": round(p_value_return, 4) if p_value_return else None,
            "violations": violations,
            "total_comparisons": len(valid_buckets) - 1,
            "buckets": [b.to_dict() for b in valid_buckets],
        }

    def _manual_rank_correlation(self, x: List, y: List) -> float:
        """Manual calculation of Spearman rank correlation (fallback)."""
        n = len(x)
        if n < 2:
            return 0.0

        # Rank the data
        x_ranks = pd.Series(x).rank().tolist()
        y_ranks = pd.Series(y).rank().tolist()

        # Calculate correlation
        mean_x = sum(x_ranks) / n
        mean_y = sum(y_ranks) / n

        numerator = sum((x_ranks[i] - mean_x) * (y_ranks[i] - mean_y) for i in range(n))
        denom_x = sum((xi - mean_x) ** 2 for xi in x_ranks) ** 0.5
        denom_y = sum((yi - mean_y) ** 2 for yi in y_ranks) ** 0.5

        if denom_x == 0 or denom_y == 0:
            return 0.0

        return numerator / (denom_x * denom_y)

    def compute_component_importance(
        self,
        horizon: str = "1M"
    ) -> Dict[str, Any]:
        """
        Compute importance of each conviction component.

        Analyzes which components contribute most to accurate conviction.

        Args:
            horizon: Which horizon to analyze

        Returns:
            Dict with component importance scores
        """
        df = self.get_conviction_history(min_observations=30)

        return_column = f"realized_return_{horizon.lower()}"
        if return_column not in df.columns:
            return {"error": f"Column {return_column} not found"}

        df_valid = df.dropna(subset=[return_column, 'conviction_score'])

        if len(df_valid) < 20:
            return {
                "error": "Insufficient data for component analysis",
                "observations": len(df_valid),
            }

        components = [
            'regime_confidence',
            'recession_agreement',
            'signal_dispersion',
            'momentum_confirmation',
            'volatility_stability',
        ]

        results = {}

        for component in components:
            if component not in df_valid.columns:
                continue

            # Correlation with realized returns
            corr = df_valid[component].corr(df_valid[return_column])

            # Correlation with overall conviction
            corr_conviction = df_valid[component].corr(df_valid['conviction_score'])

            # Importance: how well does this component predict accuracy?
            # Measure: |correlation with returns| weighted by correlation with conviction
            importance = abs(corr) * corr_conviction if corr_conviction and corr else 0

            results[component] = {
                "correlation_with_returns": round(corr, 4) if corr else None,
                "correlation_with_conviction": round(corr_conviction, 4) if corr_conviction else None,
                "importance_score": round(importance, 4),
            }

        # Sort by importance
        sorted_results = dict(sorted(
            results.items(),
            key=lambda x: x[1].get('importance_score', 0),
            reverse=True
        ))

        return {
            "horizon": horizon,
            "observations": len(df_valid),
            "components": sorted_results,
            "recommendation": "Consider adjusting weights based on importance scores",
        }

    def get_calibration_recommendations(self) -> Dict[str, Any]:
        """
        Generate calibration recommendations.

        Returns:
            Dict with specific recommendations for improving conviction calibration
        """
        recommendations = {
            "timestamp": datetime.utcnow().isoformat(),
            "monotonicity_tests": {},
            "component_analysis": {},
            "general_recommendations": [],
        }

        # Test monotonicity for each horizon
        for horizon in ["1M", "3M", "6M", "12M"]:
            result = self.test_monotonicity(horizon)
            recommendations["monotonicity_tests"][horizon] = result

            if not result.get("passed", False):
                recommendations["general_recommendations"].append(
                    f"Conviction calibration fails monotonicity at {horizon} horizon. "
                    f"Consider recalibrating component weights."
                )

        # Component importance
        comp_analysis = self.compute_component_importance("1M")
        recommendations["component_analysis"] = comp_analysis

        if "components" in comp_analysis:
            top_component = list(comp_analysis["components"].keys())[0]
            bottom_component = list(comp_analysis["components"].keys())[-1]

            recommendations["general_recommendations"].append(
                f"Increase weight on {top_component} (highest importance)"
            )
            recommendations["general_recommendations"].append(
                f"Consider reducing weight on {bottom_component} (lowest importance)"
            )

        # Check if we have enough data
        df = self.get_conviction_history()
        if len(df) < 100:
            recommendations["general_recommendations"].append(
                f"Insufficient conviction history ({len(df)} records). "
                f"Log more forecasts for reliable calibration."
            )

        return recommendations

    def compute_risk_budget_calibration(
        self,
        horizon: str = "1M"
    ) -> Dict[str, Any]:
        """
        Analyze relationship between risk budget and realized outcomes.

        Validates that higher risk budget assignments lead to proportionally
        higher returns (not just higher volatility).

        Args:
            horizon: Which horizon to analyze

        Returns:
            Dict with risk budget calibration metrics
        """
        df = self.get_conviction_history()
        return_column = f"realized_return_{horizon.lower()}"

        if return_column not in df.columns:
            return {"error": f"Return column {return_column} not found"}

        df_valid = df.dropna(subset=[return_column, 'risk_budget'])

        if len(df_valid) < 20:
            return {
                "error": "Insufficient data",
                "observations": len(df_valid),
            }

        # Correlation between risk budget and returns
        rb_return_corr = df_valid['risk_budget'].corr(df_valid[return_column])

        # Correlation between risk budget and |returns| (volatility)
        rb_vol_corr = df_valid['risk_budget'].corr(df_valid[return_column].abs())

        # Compute risk-adjusted return by risk budget bucket
        df_valid['rb_bucket'] = pd.cut(df_valid['risk_budget'], bins=3, labels=['LOW', 'MEDIUM', 'HIGH'])

        bucket_metrics = df_valid.groupby('rb_bucket').agg({
            return_column: ['mean', 'std', 'count'],
            'risk_budget': 'mean',
        }).round(4)

        return {
            "horizon": horizon,
            "observations": len(df_valid),
            "risk_budget_return_correlation": round(rb_return_corr, 4) if rb_return_corr else None,
            "risk_budget_volatility_correlation": round(rb_vol_corr, 4) if rb_vol_corr else None,
            "bucket_metrics": bucket_metrics.to_dict(),
            "recommendation": (
                "Risk budget well calibrated" if rb_return_corr and rb_return_corr > 0.3
                else "Consider recalibrating risk budget scaling"
            ),
        }


# Global instance
conviction_calibrator = ConvictionCalibrator()
