"""
Data Freshness Module

Tracks and reports on data freshness across all sources.
Implements staleness detection and freshness scoring.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yaml

from ..data.base_client import DataFreshness

logger = logging.getLogger(__name__)


@dataclass
class FreshnessRule:
    """Rules for determining data staleness by frequency."""
    frequency: str
    staleness_threshold_days: int
    warning_threshold_days: int


# Default freshness rules
DEFAULT_FRESHNESS_RULES = [
    FreshnessRule("daily", 7, 5),
    FreshnessRule("weekly", 14, 10),
    FreshnessRule("monthly", 45, 35),
    FreshnessRule("quarterly", 120, 90),
    FreshnessRule("annual", 420, 365),
]


@dataclass
class SeriesFreshness:
    """Complete freshness information for a series."""
    series_id: str
    source: str
    latest_observation_date: Optional[datetime]
    days_since_update: Optional[int]
    expected_frequency: str
    staleness_threshold_days: int
    status: str  # fresh, acceptable, stale, severely_stale, missing
    freshness_score: float  # 0-1
    is_sample_data: bool
    data_quality: str  # high, medium, low


@dataclass
class ModelFreshnessReport:
    """Overall freshness report for the model."""
    report_date: datetime
    overall_status: str  # current, delayed, stale, historical
    latest_model_date: Optional[datetime]
    series_count: int
    fresh_count: int
    acceptable_count: int
    stale_count: int
    severely_stale_count: int
    missing_count: int
    sample_count: int
    can_generate_current_allocation: bool
    warnings: List[str] = field(default_factory=list)
    series_details: List[SeriesFreshness] = field(default_factory=list)


def get_staleness_threshold(frequency: str) -> int:
    """Get staleness threshold for a given frequency."""
    rules = {r.frequency: r.staleness_threshold_days for r in DEFAULT_FRESHNESS_RULES}
    return rules.get(frequency.lower(), 45)  # Default to monthly


def calculate_freshness_score(
    days_since_update: int,
    threshold_days: int,
) -> float:
    """
    Calculate freshness score based on staleness.

    Score is 1.0 when fresh, declining to 0 when severely stale.
    """
    if days_since_update <= threshold_days / 2:
        return 1.0
    elif days_since_update <= threshold_days:
        # Linear decline from 1.0 to 0.7
        return 1.0 - 0.3 * (days_since_update - threshold_days / 2) / (threshold_days / 2)
    elif days_since_update <= threshold_days * 2:
        # Linear decline from 0.7 to 0.0
        return 0.7 - 0.7 * (days_since_update - threshold_days) / threshold_days
    else:
        return 0.0


def classify_data_status(
    days_since_update: Optional[int],
    threshold_days: int,
    is_sample: bool = False,
) -> str:
    """Classify data status based on staleness."""
    if is_sample:
        return "sample"

    if days_since_update is None:
        return "missing"

    if days_since_update <= threshold_days / 2:
        return "fresh"
    elif days_since_update <= threshold_days:
        return "acceptable"
    elif days_since_update <= threshold_days * 2:
        return "stale"
    else:
        return "severely_stale"


def check_series_freshness(
    series_id: str,
    latest_date: Optional[datetime],
    frequency: str,
    is_sample: bool = False,
    source: str = "unknown",
) -> SeriesFreshness:
    """Check freshness for a single series."""
    threshold = get_staleness_threshold(frequency)

    if latest_date:
        days_since = (datetime.now() - latest_date).days
        freshness_score = calculate_freshness_score(days_since, threshold)
        status = classify_data_status(days_since, threshold, is_sample)
    else:
        days_since = None
        freshness_score = 0.0
        status = "missing"

    # Determine data quality
    if status == "fresh":
        quality = "high"
    elif status in ["acceptable", "stale"]:
        quality = "medium"
    else:
        quality = "low"

    return SeriesFreshness(
        series_id=series_id,
        source=source,
        latest_observation_date=latest_date,
        days_since_update=days_since,
        expected_frequency=frequency,
        staleness_threshold_days=threshold,
        status=status,
        freshness_score=freshness_score,
        is_sample_data=is_sample,
        data_quality=quality,
    )


def generate_freshness_report(
    series_data: Dict[str, Tuple[Optional[datetime], str, bool, str]],
) -> ModelFreshnessReport:
    """
    Generate a comprehensive freshness report.

    Args:
        series_data: Dict mapping series_id to (latest_date, frequency, is_sample, source)

    Returns:
        ModelFreshnessReport with full freshness analysis
    """
    report = ModelFreshnessReport(
        report_date=datetime.now(),
        series_count=len(series_data),
        fresh_count=0,
        acceptable_count=0,
        stale_count=0,
        severely_stale_count=0,
        missing_count=0,
        sample_count=0,
        latest_model_date=None,
        overall_status="unknown",
        can_generate_current_allocation=False,
    )

    all_dates = []

    for series_id, (latest_date, frequency, is_sample, source) in series_data.items():
        freshness = check_series_freshness(
            series_id=series_id,
            latest_date=latest_date,
            frequency=frequency,
            is_sample=is_sample,
            source=source,
        )

        report.series_details.append(freshness)

        # Update counts
        if freshness.status == "fresh":
            report.fresh_count += 1
        elif freshness.status == "acceptable":
            report.acceptable_count += 1
        elif freshness.status == "stale":
            report.stale_count += 1
        elif freshness.status == "severely_stale":
            report.severely_stale_count += 1
        elif freshness.status == "missing":
            report.missing_count += 1
        elif freshness.status == "sample":
            report.sample_count += 1

        # Track latest date
        if latest_date:
            all_dates.append(latest_date)

    # Determine overall status
    if report.sample_count == report.series_count:
        report.overall_status = "sample_only"
        report.warnings.append(
            "WARNING: Model is using sample data only. Not suitable for live allocation."
        )
    elif report.severely_stale_count > report.series_count * 0.5:
        report.overall_status = "historical"
        report.warnings.append(
            "WARNING: Majority of data is severely stale. Model represents historical view only."
        )
    elif report.stale_count + report.severely_stale_count > report.series_count * 0.3:
        report.overall_status = "delayed"
        report.warnings.append(
            "WARNING: Significant data staleness detected. Reduced confidence recommended."
        )
    else:
        report.overall_status = "current"

    # Set latest model date
    if all_dates:
        report.latest_model_date = min(all_dates)  # Most constrained by earliest series

    # Determine if current allocation can be generated
    critical_series_stale = sum(
        1 for s in report.series_details
        if s.status in ["stale", "severely_stale", "missing"]
        and s.series_id in ["us_unemployment_rate", "us_cpi_yoy", "us_10y_yield"]
    )

    report.can_generate_current_allocation = (
        report.overall_status != "sample_only" and
        critical_series_stale < 2 and
        report.severely_stale_count < report.series_count * 0.4
    )

    return report


def format_freshness_report(report: ModelFreshnessReport) -> str:
    """Format freshness report as markdown."""
    lines = [
        "# Data Freshness Report",
        f"",
        f"**Report Date:** {report.report_date.strftime('%Y-%m-%d %H:%M')}",
        f"**Overall Status:** {report.overall_status.upper()}",
        f"**Latest Model Data Date:** {report.latest_model_date.strftime('%Y-%m-%d') if report.latest_model_date else 'N/A'}",
        f"",
        "## Summary",
        f"",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Total Series | {report.series_count} |",
        f"| Fresh | {report.fresh_count} |",
        f"| Acceptable | {report.acceptable_count} |",
        f"| Stale | {report.stale_count} |",
        f"| Severely Stale | {report.severely_stale_count} |",
        f"| Missing | {report.missing_count} |",
        f"| Sample Data | {report.sample_count} |",
        f"",
        "## Warnings",
        f"",
    ]

    if report.warnings:
        for warning in report.warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- No warnings")

    lines.extend([
        f"",
        "## Series Details",
        f"",
        f"| Series | Source | Latest Date | Days Old | Status | Score |",
        f"|--------|--------|-------------|----------|--------|-------|",
    ])

    # Sort by status severity
    status_order = {"severely_stale": 0, "stale": 1, "missing": 2, "acceptable": 3, "fresh": 4, "sample": 5}
    sorted_details = sorted(
        report.series_details,
        key=lambda x: status_order.get(x.status, 99),
    )

    for s in sorted_details:
        date_str = s.latest_observation_date.strftime("%Y-%m-%d") if s.latest_observation_date else "N/A"
        days_str = str(s.days_since_update) if s.days_since_update else "N/A"
        score_str = f"{s.freshness_score:.2f}"

        lines.append(
            f"| {s.series_id} | {s.source} | {date_str} | {days_str} | {s.status} | {score_str} |"
        )

    lines.extend([
        f"",
        "## Recommendations",
        f"",
    ])

    if not report.can_generate_current_allocation:
        lines.append(
            "**Current allocation view is NOT recommended.** "
            "Data is insufficient or too stale for live decision-making."
        )
    elif report.overall_status == "delayed":
        lines.append(
            "**Reduced confidence recommended.** "
            "Some indicators are stale; consider position sizing accordingly."
        )
    else:
        lines.append("Data freshness is acceptable for current allocation decisions.")

    return "\n".join(lines)


def save_freshness_report(
    report: ModelFreshnessReport,
    output_dir: Path,
) -> Tuple[Path, Path]:
    """Save freshness report to CSV and Markdown."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save markdown
    md_path = output_dir / "latest_data_status.md"
    md_path.write_text(format_freshness_report(report))

    # Save CSV details
    csv_path = output_dir / "data_freshness_report.csv"
    df = pd.DataFrame([
        {
            "series_id": s.series_id,
            "source": s.source,
            "latest_date": s.latest_observation_date,
            "days_since_update": s.days_since_update,
            "expected_frequency": s.expected_frequency,
            "status": s.status,
            "freshness_score": s.freshness_score,
            "is_sample": s.is_sample_data,
            "data_quality": s.data_quality,
        }
        for s in report.series_details
    ])
    df.to_csv(csv_path, index=False)

    return md_path, csv_path


def warn_if_model_is_stale(
    latest_date: Optional[datetime],
    threshold_days: int = 60,
) -> Tuple[bool, str]:
    """
    Check if model is stale and return warning message.

    Returns:
        Tuple of (is_stale, warning_message)
    """
    if latest_date is None:
        return True, "WARNING: No data available. Model cannot generate signals."

    days_since = (datetime.now() - latest_date).days

    if days_since > threshold_days:
        return (
            True,
            f"WARNING: Model data is {days_since} days old (last update: {latest_date.strftime('%Y-%m-%d')}). "
            f"Outputs should be treated as historical testing only, not current investment view."
        )

    return False, ""


def check_latest_observation_date(series_df: pd.DataFrame) -> Optional[datetime]:
    """Get the latest observation date from a DataFrame."""
    if series_df is None or series_df.empty:
        return None

    try:
        return series_df.index.max()
    except:
        return None


def classify_source_type(
    source: str,
    is_sample: bool,
    last_fetch: Optional[datetime],
) -> str:
    """Classify the source type for display."""
    if is_sample:
        return "sample"
    elif source == "cached":
        return "cached"
    elif last_fetch and (datetime.now() - last_fetch).days < 1:
        return "live"
    else:
        return "cached"


def calculate_data_freshness_score(
    series_list: List[SeriesFreshness],
) -> float:
    """
    Calculate overall data freshness score for the model.

    Weights by indicator importance.
    """
    if not series_list:
        return 0.0

    # Importance weights (simplified)
    importance = {
        "us_unemployment_rate": 1.0,
        "us_cpi_yoy": 1.0,
        "us_10y_yield": 0.9,
        "us_payrolls": 0.9,
        "us_nfci": 0.8,
    }

    total_weight = 0.0
    weighted_score = 0.0

    for s in series_list:
        weight = importance.get(s.series_id, 0.5)
        total_weight += weight
        weighted_score += weight * s.freshness_score

    if total_weight == 0:
        return 0.0

    return round(weighted_score / total_weight, 2)
