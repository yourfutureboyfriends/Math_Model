"""
Nowcast Model Validation Service — Phase 9: Validate real-time macro nowcasts.

Validates bridge regression nowcasts for macro variables:
1. Bridge Regression Backtest — Monthly GDP/activity nowcasts vs realized
2. Real-time vs Revised Data — Compare nowcasts with different data vintages
3. Vintage Data Analysis — Track prediction through data revisions
4. Revision Impact Quantification — Measure impact of data revisions

Usage:
    from api.services.nowcast_validation import nowcast_validator

    # Log nowcast
    nowcast_validator.log_nowcast(
        date="2024-01-15",
        variable="gdp_growth",
        nowcast_value=2.5,
        vintage="2024-01-15_realtime",
        predictors={"pmi": 52.3, "claims": 215000}
    )

    # Update with realized (revised) value
    nowcast_validator.update_realized(
        date="2024-01-15",
        variable="gdp_growth",
        realized_value=2.3,
        final_vintage="2024-03-15_revised"
    )

    # Analyze vintage performance
    vintage_analysis = nowcast_validator.analyze_vintage_performance()
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
class NowcastMetrics:
    """Metrics for nowcast validation."""
    variable: str
    n_nowcasts: int
    n_evaluated: int
    rmse: Optional[float] = None
    mae: Optional[float] = None
    bias: Optional[float] = None
    correlation: Optional[float] = None
    revision_impact: Optional[float] = None  # Impact of data revisions
    realtime_vs_revised_diff: Optional[float] = None
    direction_accuracy: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VintageComparison:
    """Comparison between real-time and revised nowcasts."""
    variable: str
    vintage_type: str  # "realtime" or "revised"
    mean_error: float
    std_error: float
    max_revision: float
    avg_revision: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RevisionImpact:
    """Impact of data revisions on nowcast accuracy."""
    variable: str
    initial_error: float
    revised_error: float
    improvement: float  # How much revision improved the prediction
    revision_magnitude: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class NowcastValidator:
    """
    Validation service for bridge regression nowcasts.

    Validates:
    - Bridge regression backtest
    - Real-time vs revised data comparison
    - Vintage data analysis
    - Revision impact quantification
    """

    NOWCAST_VARIABLES = [
        "gdp_growth",      # GDP growth nowcast
        "activity_index",  # Monthly activity index
        "inflation_nowcast",  # Inflation nowcast
        "employment_change",  # Employment nowcast
    ]

    def __init__(self):
        self._logger = logging.getLogger(__name__)

    def log_nowcast(
        self,
        date: str,
        variable: str,
        nowcast_value: float,
        vintage: str,
        predictors: Dict[str, float],
        confidence_interval: Optional[Tuple[float, float]] = None,
        regime: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> int:
        """
        Log a nowcast prediction.

        Args:
            date: ISO format date (nowcast date)
            variable: Variable being nowcast
            nowcast_value: Predicted value
            vintage: Data vintage used (e.g., "2024-01-15_realtime")
            predictors: Dict of predictor values used
            confidence_interval: (lower, upper) confidence bounds
            regime: Current regime classification
            metadata: Additional metadata

        Returns:
            Log entry ID
        """
        if variable not in self.NOWCAST_VARIABLES:
            self._logger.warning(f"Unknown variable: {variable}")

        try:
            with get_db() as conn:
                cursor = conn.cursor()

                # Ensure nowcast_history table exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS nowcast_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL,
                        recorded_at TEXT NOT NULL,
                        variable TEXT NOT NULL,
                        nowcast_value REAL NOT NULL,
                        vintage TEXT NOT NULL,
                        predictors TEXT,
                        confidence_lower REAL,
                        confidence_upper REAL,
                        regime TEXT,
                        realized_value REAL,
                        realized_vintage TEXT,
                        forecast_error REAL,
                        absolute_error REAL,
                        squared_error REAL,
                        revision_impact REAL,
                        metadata TEXT
                    )
                """)

                ci_lower = confidence_interval[0] if confidence_interval else None
                ci_upper = confidence_interval[1] if confidence_interval else None

                cursor.execute("""
                    INSERT INTO nowcast_history (
                        date, recorded_at, variable, nowcast_value, vintage,
                        predictors, confidence_lower, confidence_upper, regime, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    date,
                    datetime.utcnow().isoformat(),
                    variable,
                    nowcast_value,
                    vintage,
                    json.dumps(predictors),
                    ci_lower,
                    ci_upper,
                    regime,
                    json.dumps(metadata) if metadata else None
                ))

                conn.commit()
                log_id = cursor.lastrowid

                self._logger.debug(
                    f"[NowcastValidator] Logged nowcast for {variable} on {date} (id={log_id})"
                )
                return log_id

        except Exception as e:
            self._logger.error(f"[NowcastValidator] Failed to log nowcast: {e}")
            raise

    def update_realized(
        self,
        date: str,
        variable: str,
        realized_value: float,
        final_vintage: str,
        revision_history: Optional[List[Dict]] = None
    ) -> bool:
        """
        Update realized value for a nowcast.

        Automatically computes forecast error metrics.

        Args:
            date: Nowcast date
            variable: Variable name
            realized_value: Actual realized value
            final_vintage: Final data vintage
            revision_history: List of revisions over time

        Returns:
            True if update successful
        """
        try:
            with get_db() as conn:
                cursor = conn.cursor()

                # Get the nowcast first
                cursor.execute("""
                    SELECT id, nowcast_value FROM nowcast_history
                    WHERE date = ? AND variable = ?
                """, (date, variable))
                row = cursor.fetchone()

                if not row:
                    return False

                nowcast_id = row["id"]
                nowcast = row["nowcast_value"]

                error = realized_value - nowcast
                abs_error = abs(error)
                sq_error = error ** 2

                # Calculate revision impact if revision history provided
                revision_impact = None
                if revision_history and len(revision_history) > 1:
                    # Compare first vintage vs final
                    first_value = revision_history[0].get("value")
                    final_value = revision_history[-1].get("value")
                    if first_value is not None and final_value is not None:
                        revision_impact = abs(final_value - first_value)

                cursor.execute("""
                    UPDATE nowcast_history
                    SET realized_value = ?,
                        realized_vintage = ?,
                        forecast_error = ?,
                        absolute_error = ?,
                        squared_error = ?,
                        revision_impact = ?
                    WHERE id = ?
                """, (
                    realized_value,
                    final_vintage,
                    error,
                    abs_error,
                    sq_error,
                    revision_impact,
                    nowcast_id
                ))

                conn.commit()
                return cursor.rowcount > 0

        except Exception as e:
            self._logger.error(f"[NowcastValidator] Failed to update realized: {e}")
            return False

    def get_nowcast_history(
        self,
        variable: Optional[str] = None,
        vintage: Optional[str] = None,
        min_observations: int = 30
    ) -> pd.DataFrame:
        """
        Retrieve nowcast history.

        Args:
            variable: Filter by variable
            vintage: Filter by vintage
            min_observations: Minimum observations required

        Returns:
            DataFrame with nowcast history
        """
        try:
            with get_db() as conn:
                query = """
                    SELECT * FROM nowcast_history
                    WHERE 1=1
                """
                params = []

                if variable:
                    query += " AND variable = ?"
                    params.append(variable)
                if vintage:
                    query += " AND vintage = ?"
                    params.append(vintage)

                query += " ORDER BY date DESC"

                df = pd.read_sql_query(query, conn, params=params)

                if len(df) < min_observations:
                    self._logger.warning(
                        f"[NowcastValidator] Insufficient data: {len(df)} observations"
                    )

                return df

        except Exception as e:
            self._logger.error(f"[NowcastValidator] Failed to get history: {e}")
            return pd.DataFrame()

    def compute_variable_metrics(
        self,
        variable: str,
        min_observations: int = 12
    ) -> Optional[NowcastMetrics]:
        """
        Compute validation metrics for a nowcast variable.

        Args:
            variable: Variable name
            min_observations: Minimum observations required

        Returns:
            NowcastMetrics or None
        """
        df = self.get_nowcast_history(variable=variable)

        if len(df) < min_observations:
            return NowcastMetrics(
                variable=variable,
                n_nowcasts=len(df),
                n_evaluated=0
            )

        df_valid = df.dropna(subset=["realized_value", "nowcast_value"])

        if len(df_valid) < min_observations:
            return NowcastMetrics(
                variable=variable,
                n_nowcasts=len(df),
                n_evaluated=len(df_valid)
            )

        nowcasts = df_valid["nowcast_value"].astype(float)
        realized = df_valid["realized_value"].astype(float)

        # Basic metrics
        correlation = nowcasts.corr(realized)
        errors = nowcasts - realized
        rmse = np.sqrt((errors ** 2).mean())
        mae = errors.abs().mean()
        bias = errors.mean()

        # Direction accuracy (% correct sign predictions)
        direction_correct = ((nowcasts > 0) & (realized > 0)) | ((nowcasts < 0) & (realized < 0))
        direction_acc = direction_correct.mean()

        # Revision impact
        revision_impact = df_valid["revision_impact"].mean() if "revision_impact" in df_valid.columns else None

        # Real-time vs revised difference
        rt_vs_rev = df_valid["revision_impact"].mean() if "revision_impact" in df_valid.columns else None

        return NowcastMetrics(
            variable=variable,
            n_nowcasts=len(df),
            n_evaluated=len(df_valid),
            rmse=round(rmse, 4),
            mae=round(mae, 4),
            bias=round(bias, 4),
            correlation=round(correlation, 4) if correlation and not pd.isna(correlation) else None,
            direction_accuracy=round(direction_acc, 4),
            revision_impact=round(revision_impact, 4) if revision_impact and not pd.isna(revision_impact) else None,
            realtime_vs_revised_diff=round(rt_vs_rev, 4) if rt_vs_rev and not pd.isna(rt_vs_rev) else None
        )

    def compare_realtime_vs_revised(
        self,
        variable: str,
        min_observations: int = 12
    ) -> Dict[str, Any]:
        """
        Compare real-time nowcasts vs revised data nowcasts.

        Args:
            variable: Variable to analyze
            min_observations: Minimum observations

        Returns:
            Comparison results
        """
        df = self.get_nowcast_history(variable=variable)
        df_valid = df.dropna(subset=["realized_value"])

        if len(df_valid) < min_observations:
            return {
                "variable": variable,
                "error": "Insufficient data for comparison",
                "observations": len(df_valid)
            }

        # Group by vintage type
        realtime = df_valid[df_valid["vintage"].str.contains("realtime", na=False)]
        revised = df_valid[df_valid["vintage"].str.contains("revised", na=False)]

        results = {
            "variable": variable,
            "realtime": {
                "n_observations": len(realtime),
                "mean_error": round((realtime["forecast_error"]).mean(), 4) if len(realtime) > 0 else None,
                "std_error": round((realtime["forecast_error"]).std(), 4) if len(realtime) > 0 else None,
                "rmse": round(np.sqrt((realtime["forecast_error"] ** 2).mean()), 4) if len(realtime) > 0 else None,
            },
            "revised": {
                "n_observations": len(revised),
                "mean_error": round((revised["forecast_error"]).mean(), 4) if len(revised) > 0 else None,
                "std_error": round((revised["forecast_error"]).std(), 4) if len(revised) > 0 else None,
                "rmse": round(np.sqrt((revised["forecast_error"] ** 2).mean()), 4) if len(revised) > 0 else None,
            }
        }

        # Calculate revision impact
        if len(realtime) > 0 and len(revised) > 0:
            rt_rmse = results["realtime"]["rmse"]
            rev_rmse = results["revised"]["rmse"]
            if rt_rmse and rev_rmse:
                results["revision_impact"] = {
                    "rmse_improvement": round(rt_rmse - rev_rmse, 4),
                    "pct_improvement": round((rt_rmse - rev_rmse) / rt_rmse * 100, 2) if rt_rmse > 0 else 0
                }

        return {
            "timestamp": datetime.utcnow().isoformat(),
            **results
        }

    def analyze_vintage_performance(
        self,
        variable: str = "gdp_growth"
    ) -> Dict[str, Any]:
        """
        Analyze performance across different data vintages.

        Args:
            variable: Variable to analyze

        Returns:
            Vintage performance analysis
        """
        df = self.get_nowcast_history(variable=variable)
        df_valid = df.dropna(subset=["realized_value"])

        if len(df_valid) < 12:
            return {
                "variable": variable,
                "error": "Insufficient data",
                "observations": len(df_valid)
            }

        # Extract unique vintages
        vintages = df_valid["vintage"].unique()

        vintage_metrics = {}
        for vintage in vintages:
            vintage_df = df_valid[df_valid["vintage"] == vintage]
            if len(vintage_df) > 0:
                errors = vintage_df["forecast_error"]
                vintage_metrics[vintage] = {
                    "n_observations": len(vintage_df),
                    "rmse": round(np.sqrt((errors ** 2).mean()), 4),
                    "mae": round(errors.abs().mean(), 4),
                    "bias": round(errors.mean(), 4)
                }

        # Find best vintage
        best_vintage = min(vintage_metrics.items(), key=lambda x: x[1]["rmse"]) if vintage_metrics else None

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "variable": variable,
            "vintages_analyzed": len(vintage_metrics),
            "vintage_metrics": vintage_metrics,
            "best_vintage": best_vintage[0] if best_vintage else None,
            "recommendation": f"Use {best_vintage[0]} vintage for best accuracy" if best_vintage else "Insufficient data"
        }

    def quantify_revision_impact(
        self,
        variable: str = "gdp_growth"
    ) -> Dict[str, Any]:
        """
        Quantify the impact of data revisions on nowcast accuracy.

        Args:
            variable: Variable to analyze

        Returns:
            Revision impact quantification
        """
        df = self.get_nowcast_history(variable=variable)
        df_valid = df.dropna(subset=["realized_value", "revision_impact"])

        if len(df_valid) < 10:
            return {
                "variable": variable,
                "error": "Insufficient data with revision history",
                "observations": len(df_valid)
            }

        revision_impacts = df_valid["revision_impact"].astype(float)
        errors = df_valid["absolute_error"].astype(float)

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "variable": variable,
            "observations": len(df_valid),
            "revision_impact_stats": {
                "mean": round(revision_impacts.mean(), 4),
                "median": round(revision_impacts.median(), 4),
                "std": round(revision_impacts.std(), 4),
                "max": round(revision_impacts.max(), 4),
                "min": round(revision_impacts.min(), 4)
            },
            "correlation_with_error": round(revision_impacts.corr(errors), 4),
            "interpretation": "Higher revision impact suggests data instability affects nowcast accuracy"
        }

    def get_calibration_recommendations(self) -> Dict[str, Any]:
        """
        Generate calibration recommendations.

        Returns:
            Dict with recommendations
        """
        recommendations = {
            "timestamp": datetime.utcnow().isoformat(),
            "variable_metrics": {},
            "vintage_comparison": {},
            "revision_impact": None,
            "general_recommendations": [],
        }

        # Variable metrics
        for variable in self.NOWCAST_VARIABLES:
            metrics = self.compute_variable_metrics(variable)
            if metrics:
                recommendations["variable_metrics"][variable] = metrics.to_dict()

                # Check RMSE
                if metrics.rmse and metrics.rmse > 1.0:
                    recommendations["general_recommendations"].append(
                        f"{variable}: High RMSE ({metrics.rmse:.2f}), consider additional predictors"
                    )

                # Check bias
                if metrics.bias and abs(metrics.bias) > 0.2:
                    recommendations["general_recommendations"].append(
                        f"{variable}: Significant bias ({metrics.bias:.2f}), recalibrate model"
                    )

        # Vintage comparison for GDP growth
        rt_vs_rev = self.compare_realtime_vs_revised("gdp_growth")
        recommendations["vintage_comparison"] = rt_vs_rev

        if rt_vs_rev.get("revision_impact", {}).get("pct_improvement", 0) > 10:
            recommendations["general_recommendations"].append(
                "Large revision impact detected - build revision-adjusted confidence intervals"
            )

        # Revision impact
        rev_impact = self.quantify_revision_impact("gdp_growth")
        recommendations["revision_impact"] = rev_impact

        return recommendations


# Global instance
nowcast_validator = NowcastValidator()
