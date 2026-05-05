"""
Data Quality Engine

Validates and scores data quality for macro research.
Ensures data integrity before use in models.

Based on data quality dimensions:
- Completeness: missing values
- Timeliness: staleness, information lag
- Consistency: revisions, outliers
- Validity: range checks, logical constraints
- Provenance: source reliability
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class DataQualityReport:
    """Quality assessment for a single data series."""
    series_id: str
    total_observations: int
    missing_values: int
    missing_pct: float
    first_available: Optional[datetime]
    last_available: Optional[datetime]
    data_span_days: Optional[int]
    avg_information_lag_days: float
    revision_count: int
    revision_pct: float
    outlier_count: int
    outlier_pct: float
    staleness_days: Optional[int]
    quality_score: float  # 0-1 composite score
    warnings: List[str]
    recommendations: List[str]


class DataQualityEngine:
    """
    Validates macro data quality before model use.

    Implements checks for:
    - Missing data patterns
    - Timeliness and staleness
    - Outliers and anomalies
    - Revision magnitude
    - Logical consistency
    """

    # Quality thresholds
    MIN_OBSERVATIONS = 12
    MAX_MISSING_PCT = 0.20
    MAX_STALENESS_DAYS = 90
    MAX_REVISION_PCT = 0.30
    OUTLIER_ZSCORE = 3.0

    def __init__(self):
        self.quality_thresholds = {
            "min_observations": 12,
            "max_missing_pct": 0.20,
            "max_staleness_days": 90,
            "max_revision_pct": 0.30,
            "outlier_zscore": 3.0,
        }

    def assess_series(
        self,
        series: pd.Series,
        series_id: str = "unknown",
        release_dates: Optional[pd.Series] = None,
        revision_history: Optional[pd.DataFrame] = None,
    ) -> DataQualityReport:
        """
        Comprehensive quality assessment of a time series.
        """
        warnings = []
        recommendations = []

        total_obs = len(series)
        missing = series.isna().sum()
        missing_pct = missing / total_obs if total_obs > 0 else 0

        # Date range
        if hasattr(series.index, 'min'):
            first = series.index.min()
            last = series.index.max()
            span = (last - first).days if hasattr(last - first, 'days') else None
        else:
            first = last = span = None

        # Staleness
        staleness = None
        if last is not None:
            staleness = (datetime.now() - last).days

        # Information lag (if release dates provided)
        avg_lag = 0.0
        if release_dates is not None and len(release_dates) > 0:
            lags = [(r - o).days for o, r in zip(series.index, release_dates)]
            avg_lag = np.mean(lags) if lags else 0.0

        # Revision analysis
        revision_count = 0
        revision_pct = 0.0
        if revision_history is not None and len(revision_history) > 0:
            revision_count = len(revision_history) - 1  # First vintage not a revision
            revision_pct = revision_count / len(series) if len(series) > 0 else 0

        # Outlier detection
        outlier_count = 0
        outlier_pct = 0.0
        if total_obs > 0:
            clean = series.dropna()
            if len(clean) > 0:
                zscores = np.abs((clean - clean.mean()) / clean.std())
                outlier_count = (zscores > self.OUTLIER_ZSCORE).sum()
                outlier_pct = outlier_count / len(clean)

        # Generate warnings
        if missing_pct > self.MAX_MISSING_PCT:
            warnings.append(f"High missing data: {missing_pct:.1%}")
            recommendations.append("Consider interpolation or use alternative series")

        if staleness and staleness > self.MAX_STALENESS_DAYS:
            warnings.append(f"Stale data: {staleness} days old")
            recommendations.append("Refresh data source")

        if outlier_pct > 0.05:
            warnings.append(f"High outlier rate: {outlier_pct:.1%}")
            recommendations.append("Review outliers, may indicate data errors")

        if total_obs < self.MIN_OBSERVATIONS:
            warnings.append(f"Insufficient observations: {total_obs} < {self.MIN_OBSERVATIONS}")
            recommendations.append("Wait for more data before using in models")

        # Composite quality score
        quality_score = self._calculate_quality_score(
            total_obs, missing_pct, staleness or 0,
            revision_pct, outlier_pct
        )

        return DataQualityReport(
            series_id=series_id,
            total_observations=total_obs,
            missing_values=missing,
            missing_pct=missing_pct,
            first_available=first if isinstance(first, datetime) else None,
            last_available=last if isinstance(last, datetime) else None,
            data_span_days=span,
            avg_information_lag_days=avg_lag,
            revision_count=revision_count,
            revision_pct=revision_pct,
            outlier_count=int(outlier_count),
            outlier_pct=outlier_pct,
            staleness_days=staleness,
            quality_score=quality_score,
            warnings=warnings,
            recommendations=recommendations,
        )

    def _calculate_quality_score(
        self,
        n_obs: int,
        missing_pct: float,
        staleness: int,
        revision_pct: float,
        outlier_pct: float,
    ) -> float:
        """
        Calculate composite quality score (0-1).
        """
        scores = []

        # Observation count score
        if n_obs >= 60:
            scores.append(1.0)
        elif n_obs >= 24:
            scores.append(0.8)
        elif n_obs >= 12:
            scores.append(0.6)
        else:
            scores.append(0.3)

        # Missing data score
        scores.append(max(0, 1 - missing_pct / self.MAX_MISSING_PCT))

        # Staleness score
        if staleness <= 30:
            scores.append(1.0)
        elif staleness <= 60:
            scores.append(0.8)
        elif staleness <= 90:
            scores.append(0.6)
        else:
            scores.append(max(0, 1 - staleness / 180))

        # Revision score (lower is better)
        scores.append(max(0, 1 - revision_pct / self.MAX_REVISION_PCT))

        # Outlier score
        scores.append(max(0, 1 - outlier_pct / 0.10))

        return np.mean(scores)

    def assess_panel(
        self,
        df: pd.DataFrame,
        release_dates: Optional[Dict[str, pd.Series]] = None,
    ) -> pd.DataFrame:
        """
        Assess quality for all series in a panel.
        """
        reports = []

        for col in df.columns:
            r_dates = release_dates.get(col) if release_dates else None
            report = self.assess_series(df[col], col, r_dates)
            reports.append({
                "series_id": report.series_id,
                "quality_score": report.quality_score,
                "missing_pct": report.missing_pct,
                "staleness_days": report.staleness_days,
                "last_available": report.last_available,
                "warnings": len(report.warnings),
                "usable": report.quality_score > 0.5 and len(report.warnings) < 3,
            })

        return pd.DataFrame(reports)

    def validate_for_modeling(
        self,
        df: pd.DataFrame,
        min_quality_score: float = 0.5,
        max_missing_pct: float = 0.20,
    ) -> Tuple[pd.DataFrame, Dict]:
        """
        Validate panel for modeling use.

        Returns clean DataFrame and validation report.
        """
        validation = {
            "original_series": len(df.columns),
            "passed_series": 0,
            "failed_series": [],
            "dropped_due_to_quality": [],
            "dropped_due_to_missing": [],
        }

        quality_report = self.assess_panel(df)

        # Filter to passing series
        passing = quality_report[
            (quality_report["quality_score"] >= min_quality_score) &
            (quality_report["missing_pct"] <= max_missing_pct)
        ]

        validation["passed_series"] = len(passing)
        validation["failed_series"] = list(
            quality_report[~quality_report.index.isin(passing.index)]["series_id"]
        )

        # Return clean panel
        clean_df = df[passing["series_id"]].dropna()

        return clean_df, validation

    def check_for_lookahead_bias(
        self,
        df: pd.DataFrame,
        as_of_date: datetime,
        release_dates: Optional[Dict[str, datetime]] = None,
    ) -> List[str]:
        """
        Check for potential lookahead bias in a dataset.

        Returns warnings about any series that might include future information.
        """
        warnings = []

        for col in df.columns:
            series_last = df[col].last_valid_index()
            if series_last is None:
                continue

            # If we have release date info, use it
            if release_dates and col in release_dates:
                release = release_dates[col]
                if release > as_of_date:
                    warnings.append(f"{col}: data from {series_last} released {release}, after as_of_date")
            else:
                # Estimate based on typical lags
                estimated_release = series_last + timedelta(days=30)
                if estimated_release > as_of_date:
                    warnings.append(f"{col}: last data {series_last}, estimated release after {as_of_date}")

        return warnings

    def get_quality_summary(self, reports: List[DataQualityReport]) -> Dict:
        """Summarize quality across multiple series."""
        if not reports:
            return {"status": "No data"}

        scores = [r.quality_score for r in reports]
        warnings_count = sum(len(r.warnings) for r in reports)

        return {
            "series_count": len(reports),
            "avg_quality_score": np.mean(scores),
            "min_quality_score": min(scores),
            "high_quality_series": sum(1 for s in scores if s > 0.8),
            "usable_series": sum(1 for s in scores if s > 0.5),
            "total_warnings": warnings_count,
            "status": "Good" if np.mean(scores) > 0.7 else "Acceptable" if np.mean(scores) > 0.5 else "Poor",
        }


class DataLineageTracker:
    """
    Track data lineage for audit and reproducibility.

    Records:
    - Data source and version
    - Transformation steps
    - Quality checks applied
    - Usage in models
    """

    def __init__(self):
        self.lineage_log: List[Dict] = []

    def record_data_ingestion(
        self,
        series_id: str,
        source: str,
        source_version: str,
        ingestion_time: datetime,
        record_count: int,
    ) -> None:
        """Record data ingestion event."""
        self.lineage_log.append({
            "event": "ingestion",
            "series_id": series_id,
            "source": source,
            "source_version": source_version,
            "time": ingestion_time,
            "record_count": record_count,
        })

    def record_transformation(
        self,
        series_id: str,
        transformation: str,
        parameters: Dict,
        output_series_id: Optional[str] = None,
    ) -> None:
        """Record data transformation."""
        self.lineage_log.append({
            "event": "transformation",
            "series_id": series_id,
            "transformation": transformation,
            "parameters": parameters,
            "output_series_id": output_series_id,
            "time": datetime.now(),
        })

    def record_quality_check(
        self,
        series_id: str,
        check_type: str,
        result: str,
        score: Optional[float] = None,
    ) -> None:
        """Record quality validation."""
        self.lineage_log.append({
            "event": "quality_check",
            "series_id": series_id,
            "check_type": check_type,
            "result": result,
            "score": score,
            "time": datetime.now(),
        })

    def get_lineage(self, series_id: str) -> List[Dict]:
        """Get complete lineage for a series."""
        return [e for e in self.lineage_log if e.get("series_id") == series_id]

    def export_lineage(self, filepath: str) -> None:
        """Export lineage to file for audit."""
        pd.DataFrame(self.lineage_log).to_csv(filepath, index=False)
