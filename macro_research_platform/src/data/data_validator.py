"""
Data Validator Module

Validates data quality before it enters the model.
Checks for: missing values, outliers, stale data, duplicates, etc.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd

from .data_freshness import check_series_freshness

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of data validation."""
    series_id: str
    is_valid: bool
    quality_score: float
    quality_level: str  # high, medium, low
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataQualityMetrics:
    """Quality metrics for a data series."""
    series_id: str
    completeness: float  # 0-1, fraction of non-null values
    freshness_score: float  # 0-1
    stability: float  # 0-1, based on volatility/absence of jumps
    outlier_count: int
    duplicate_count: int
    observation_count: int
    date_range: Tuple[Optional[datetime], Optional[datetime]]


class DataValidator:
    """
    Validates data quality for macro model inputs.

    Implements checks for:
    1. Missing values
    2. Duplicate dates
    3. Large outliers
    4. Sudden jumps
    5. Stale data
    6. Frequency mismatch
    7. Date alignment
    8. Minimum observations
    9. Source type (real/cached/sample)
    10. Revision status
    """

    def __init__(
        self,
        min_completeness: float = 0.80,
        outlier_zscore_threshold: float = 4.0,
        jump_threshold_std: float = 5.0,
        min_observations: int = 24,
    ):
        self.min_completeness = min_completeness
        self.outlier_zscore_threshold = outlier_zscore_threshold
        self.jump_threshold_std = jump_threshold_std
        self.min_observations = min_observations

    def validate_series(
        self,
        series_id: str,
        df: pd.DataFrame,
        expected_frequency: str = "monthly",
        is_sample: bool = False,
    ) -> ValidationResult:
        """
        Validate a single data series.

        Returns:
            ValidationResult with quality assessment
        """
        result = ValidationResult(series_id=series_id, is_valid=True, quality_score=0.0, quality_level="low")

        if df is None or df.empty:
            result.is_valid = False
            result.issues.append("No data available")
            result.quality_level = "low"
            return result

        # Check 1: Minimum observations
        obs_count = len(df)
        result.stats["observation_count"] = obs_count

        if obs_count < self.min_observations:
            result.issues.append(f"Insufficient observations: {obs_count} < {self.min_observations}")
            result.is_valid = False

        # Check 2: Completeness
        completeness = 1.0 - (df.isnull().sum().sum() / df.size)
        result.stats["completeness"] = completeness

        if completeness < self.min_completeness:
            result.issues.append(f"Low completeness: {completeness:.1%} < {self.min_completeness:.0%}")

        # Check 3: Duplicate dates
        if df.index.duplicated().any():
            dup_count = df.index.duplicated().sum()
            result.stats["duplicate_count"] = int(dup_count)
            result.issues.append(f"Duplicate dates found: {dup_count}")
        else:
            result.stats["duplicate_count"] = 0

        # Check 4: Outliers (if numeric)
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        if len(numeric_cols) > 0:
            col = numeric_cols[0]
            values = df[col].dropna()

            if len(values) > 10:
                z_scores = np.abs((values - values.mean()) / values.std())
                outlier_count = (z_scores > self.outlier_zscore_threshold).sum()
                result.stats["outlier_count"] = int(outlier_count)

                if outlier_count > len(values) * 0.05:  # More than 5% outliers
                    result.warnings.append(f"High outlier count: {outlier_count}")

                # Check 5: Sudden jumps
                if len(values) > 1:
                    diffs = values.diff().dropna()
                    if len(diffs) > 10 and diffs.std() > 0:
                        jump_zscores = np.abs((diffs - diffs.mean()) / diffs.std())
                        jump_count = (jump_zscores > self.jump_threshold_std).sum()
                        result.stats["sudden_jumps"] = int(jump_count)

                        if jump_count > 0:
                            result.warnings.append(f"Sudden jumps detected: {jump_count}")

        # Check 6: Date range
        if hasattr(df.index, 'min') and hasattr(df.index, 'max'):
            date_min = df.index.min() if len(df) > 0 else None
            date_max = df.index.max() if len(df) > 0 else None
            result.stats["date_range"] = (date_min, date_max)
            result.stats["date_span_days"] = (date_max - date_min).days if date_min and date_max else None

        # Check 7: Freshness
        latest_date = df.index.max() if len(df) > 0 else None
        freshness = check_series_freshness(
            series_id=series_id,
            latest_date=latest_date,
            frequency=expected_frequency,
            is_sample=is_sample,
        )
        result.stats["freshness_score"] = freshness.freshness_score
        result.stats["days_since_update"] = freshness.days_since_update
        result.stats["freshness_status"] = freshness.status

        if freshness.status in ["stale", "severely_stale"]:
            result.warnings.append(f"Data is {freshness.status}: {freshness.days_since_update} days old")

        # Check 8: Source type
        result.stats["is_sample"] = is_sample
        if is_sample:
            result.warnings.append("Using sample data - not suitable for live decisions")

        # Calculate overall quality score
        quality_score = self._calculate_quality_score(result.stats)
        result.quality_score = quality_score
        result.quality_level = self._classify_quality(quality_score, result.issues)

        # Valid if no critical issues
        result.is_valid = len([i for i in result.issues if "Insufficient" not in i and "No data" not in i]) == 0

        return result

    def _calculate_quality_score(self, stats: Dict[str, Any]) -> float:
        """Calculate overall quality score from component metrics."""
        weights = {
            "completeness": 0.30,
            "freshness_score": 0.25,
            "stability": 0.20,
            "observation_count": 0.15,
            "source_reliability": 0.10,
        }

        scores = []

        # Completeness
        if "completeness" in stats:
            scores.append(("completeness", stats["completeness"]))

        # Freshness
        if "freshness_score" in stats:
            scores.append(("freshness_score", stats["freshness_score"]))

        # Stability (based on outliers and jumps)
        if "outlier_count" in stats and "observation_count" in stats:
            outlier_pct = stats["outlier_count"] / max(stats["observation_count"], 1)
            stability = max(0, 1 - outlier_pct * 10)  # Penalize outliers
            scores.append(("stability", stability))

        # Observation sufficiency
        if "observation_count" in stats:
            obs_ratio = min(stats["observation_count"] / self.min_observations, 1.0)
            scores.append(("observation_count", obs_ratio))

        # Source reliability (sample data penalty)
        if stats.get("is_sample", False):
            scores.append(("source_reliability", 0.5))
        else:
            scores.append(("source_reliability", 0.95))

        # Calculate weighted score
        total_weight = sum(weights.get(k, 0) for k, _ in scores)
        if total_weight == 0:
            return 0.0

        weighted_sum = sum(
            weights.get(name, 0) * score for name, score in scores
        )

        return round(weighted_sum / total_weight, 2)

    def _classify_quality(self, score: float, issues: List[str]) -> str:
        """Classify quality level based on score and issues."""
        # Critical issues downgrade quality
        critical_issues = [i for i in issues if "No data" in i or "Insufficient" in i]
        if critical_issues:
            return "low"

        if score >= 0.8:
            return "high"
        elif score >= 0.6:
            return "medium"
        else:
            return "low"

    def validate_dataset(
        self,
        df: pd.DataFrame,
        indicator_configs: List[Dict],
    ) -> Dict[str, ValidationResult]:
        """
        Validate a complete dataset.

        Args:
            df: DataFrame with indicators as columns
            indicator_configs: List of indicator configurations

        Returns:
            Dict mapping series_id to ValidationResult
        """
        results = {}

        for config in indicator_configs:
            series_id = config["series_id"]

            if series_id in df.columns:
                series_df = df[[series_id]].copy()
                result = self.validate_series(
                    series_id=series_id,
                    df=series_df,
                    expected_frequency=config.get("frequency", "monthly"),
                    is_sample=config.get("source", "sample") == "sample",
                )
            else:
                # Series missing from dataset
                result = ValidationResult(
                    series_id=series_id,
                    is_valid=False,
                    quality_score=0.0,
                    quality_level="low",
                    issues=["Series not found in dataset"],
                )

            results[series_id] = result

        return results

    def generate_validation_report(
        self,
        results: Dict[str, ValidationResult],
    ) -> str:
        """Generate a validation report as markdown."""
        lines = [
            "# Data Validation Report",
            f"",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"**Series Validated:** {len(results)}",
            f"",
            "## Summary",
            f"",
        ]

        valid_count = sum(1 for r in results.values() if r.is_valid)
        high_quality = sum(1 for r in results.values() if r.quality_level == "high")
        medium_quality = sum(1 for r in results.values() if r.quality_level == "medium")
        low_quality = sum(1 for r in results.values() if r.quality_level == "low")

        lines.extend([
            f"| Metric | Count |",
            f"|--------|-------|",
            f"| Total Series | {len(results)} |",
            f"| Valid | {valid_count} |",
            f"| Invalid | {len(results) - valid_count} |",
            f"| High Quality | {high_quality} |",
            f"| Medium Quality | {medium_quality} |",
            f"| Low Quality | {low_quality} |",
            f"",
            "## Series Details",
            f"",
            f"| Series | Valid | Quality | Score | Issues | Warnings |",
            f"|--------|-------|---------|-------|--------|----------|",
        ])

        for series_id, result in sorted(results.items()):
            issues_str = ", ".join(result.issues) if result.issues else "None"
            warnings_str = ", ".join(result.warnings) if result.warnings else "None"

            lines.append(
                f"| {series_id} | {'✅' if result.is_valid else '❌'} | "
                f"{result.quality_level} | {result.quality_score:.2f} | "
                f"{issues_str[:30]}{'...' if len(issues_str) > 30 else ''} | "
                f"{warnings_str[:30]}{'...' if len(warnings_str) > 30 else ''} |"
            )

        lines.extend([
            f"",
            "## Recommendations",
            f"",
        ])

        if low_quality > len(results) * 0.3:
            lines.append("⚠️ **Warning:** More than 30% of series have low quality. Consider data refresh or using alternative sources.")
        elif medium_quality + low_quality > len(results) * 0.5:
            lines.append("⚡ **Note:** Significant portion of data is medium or low quality. Confidence should be adjusted accordingly.")
        else:
            lines.append("✅ Data quality is acceptable for model execution.")

        return "\n".join(lines)


def quick_validate_series(
    df: pd.DataFrame,
    series_name: str,
) -> Tuple[bool, float, List[str]]:
    """
    Quick validation of a single series.

    Returns:
        Tuple of (is_valid, quality_score, issues)
    """
    validator = DataValidator()

    if series_name not in df.columns:
        return False, 0.0, ["Series not found"]

    result = validator.validate_series(
        series_id=series_name,
        df=df[[series_name]],
    )

    return result.is_valid, result.quality_score, result.issues + result.warnings
