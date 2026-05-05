"""
Point-in-Time Data Store

Bridgewater-inspired principle: All data must be timestamped and aligned to
when it was actually known, not when the activity occurred.

This module prevents lookahead bias by tracking:
- observation_date: when the activity occurred (e.g., March 2024 CPI)
- release_date: when the data was first published
- vintage_date: which revision we're using
- as_of_date: the perspective date for the analysis
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class PITDataPoint:
    """
    Single point-in-time data observation.

    This is the atomic unit of macro data in the system.
    """
    series_id: str                    # e.g., "CPIAUCSL"
    observation_date: datetime        # Period this data refers to
    release_date: datetime            # When this value was first published
    value: float                      # The actual data value
    vintage_date: Optional[datetime] = None  # Which revision (None = first release)
    source: str = "FRED"              # Data source
    source_type: str = "release"      # release, revision, realtime
    last_updated: Optional[datetime] = None    # When we fetched this
    revision_status: str = "final"    # final, provisional, estimated
    data_quality_score: float = 1.0   # 0-1, based on staleness and revision

    def is_available_as_of(self, as_of_date: datetime) -> bool:
        """Check if this data point was available as of a given date."""
        return self.release_date <= as_of_date

    def get_information_lag(self) -> timedelta:
        """Time between observation and release."""
        return self.release_date - self.observation_date


@dataclass
class PITSeries:
    """
    A time series of point-in-time data points.

    Maintains multiple vintages for the same conceptual series.
    """
    series_id: str
    series_name: str
    frequency: str                    # M, Q, A, D
    category: str                     # growth, inflation, labor, etc.
    unit: str                         # percent, index, millions, etc.
    seasonal_adjustment: str          # SA, NSA
    data_points: List[PITDataPoint] = field(default_factory=list)
    vintage_history: Dict[datetime, List[PITDataPoint]] = field(default_factory=dict)

    def add_observation(self, point: PITDataPoint) -> None:
        """Add a new data point to this series."""
        self.data_points.append(point)

        # Organize by vintage
        vintage = point.vintage_date or point.release_date
        if vintage not in self.vintage_history:
            self.vintage_history[vintage] = []
        self.vintage_history[vintage].append(point)

    def get_value_as_of(
        self,
        observation_date: datetime,
        as_of_date: datetime
    ) -> Optional[PITDataPoint]:
        """
        Get what we knew about a specific observation date as of a given date.

        This is the core point-in-time lookup that prevents lookahead bias.
        """
        # Filter to points that were available as_of_date
        available = [
            p for p in self.data_points
            if p.observation_date == observation_date
            and p.release_date <= as_of_date
        ]

        if not available:
            return None

        # Return the latest revision available as of that date
        return max(available, key=lambda x: x.release_date)

    def get_series_as_of(
        self,
        as_of_date: datetime,
        min_observations: int = 12
    ) -> pd.Series:
        """
        Get the entire series as it would have appeared on a given date.

        This is the key function for backtesting - it simulates what you
        would have known on any historical date.
        """
        values = []
        dates = []

        # Get all unique observation dates
        obs_dates = sorted(set(p.observation_date for p in self.data_points))

        for obs_date in obs_dates:
            point = self.get_value_as_of(obs_date, as_of_date)
            if point:
                dates.append(obs_date)
                values.append(point.value)

        if len(values) < min_observations:
            logger.warning(
                f"Series {self.series_id} has only {len(values)} observations as of {as_of_date}"
            )

        return pd.Series(values, index=pd.DatetimeIndex(dates), name=self.series_id)

    def get_revision_history(self, observation_date: datetime) -> List[PITDataPoint]:
        """Get all revisions for a specific observation."""
        return [
            p for p in self.data_points
            if p.observation_date == observation_date
        ]


class PointInTimeStore:
    """
    Central store for all point-in-time macro data.

    Maintains multiple PITSeries and provides query capabilities
    aligned to specific dates to prevent lookahead bias.
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path("data/pit_store")
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.series: Dict[str, PITSeries] = {}
        self._load_existing()

    def _load_existing(self) -> None:
        """Load existing PIT data from storage."""
        if not self.storage_path.exists():
            return

        # TODO: Implement persistent storage
        pass

    def register_series(
        self,
        series_id: str,
        series_name: str,
        frequency: str,
        category: str,
        unit: str,
        seasonal_adjustment: str = "SA"
    ) -> PITSeries:
        """Register a new series in the store."""
        if series_id in self.series:
            logger.warning(f"Series {series_id} already exists, returning existing")
            return self.series[series_id]

        series = PITSeries(
            series_id=series_id,
            series_name=series_name,
            frequency=frequency,
            category=category,
            unit=unit,
            seasonal_adjustment=seasonal_adjustment,
        )
        self.series[series_id] = series
        return series

    def add_observation(self, point: PITDataPoint) -> None:
        """Add a data point to the appropriate series."""
        if point.series_id not in self.series:
            logger.error(f"Series {point.series_id} not registered")
            return

        self.series[point.series_id].add_observation(point)

    def get_series(
        self,
        series_id: str,
        as_of_date: Optional[datetime] = None
    ) -> Optional[Union[PITSeries, pd.Series]]:
        """
        Get a series, optionally as of a specific date.

        If as_of_date is provided, returns the series as it would
        have appeared on that date (point-in-time).
        """
        if series_id not in self.series:
            return None

        pit_series = self.series[series_id]

        if as_of_date is None:
            return pit_series

        return pit_series.get_series_as_of(as_of_date)

    def get_panel_as_of(
        self,
        series_ids: List[str],
        as_of_date: datetime,
        min_observations: int = 12
    ) -> pd.DataFrame:
        """
        Get multiple series as of a specific date.

        Returns a DataFrame with series as columns, dates as index,
        containing only data that was known as of the specified date.
        """
        data = {}

        for series_id in series_ids:
            series = self.get_series(series_id, as_of_date)
            if series is not None and isinstance(series, pd.Series):
                if len(series) >= min_observations:
                    data[series_id] = series

        if not data:
            logger.warning(f"No valid series found as of {as_of_date}")
            return pd.DataFrame()

        return pd.DataFrame(data)

    def get_latest_values(
        self,
        as_of_date: Optional[datetime] = None
    ) -> Dict[str, PITDataPoint]:
        """
        Get the latest value for each series as of a given date.

        Useful for current snapshot analysis.
        """
        as_of = as_of_date or datetime.now()
        latest = {}

        for series_id, series in self.series.items():
            # Get all points available as_of
            available = [
                p for p in series.data_points
                if p.release_date <= as_of
            ]

            if available:
                # Get the most recent observation
                latest_point = max(available, key=lambda x: x.observation_date)
                latest[series_id] = latest_point

        return latest

    def check_lookahead_bias(
        self,
        series_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Tuple[datetime, timedelta]]:
        """
        Analyze information lags to understand data availability.

        Returns list of (observation_date, information_lag) tuples.
        """
        if series_id not in self.series:
            return []

        series = self.series[series_id]
        lags = []

        for point in series.data_points:
            if start_date <= point.observation_date <= end_date:
                lags.append((
                    point.observation_date,
                    point.get_information_lag()
                ))

        return lags

    def get_data_quality_report(self) -> pd.DataFrame:
        """
        Generate a report on data quality across all series.
        """
        reports = []

        for series_id, series in self.series.items():
            if not series.data_points:
                continue

            total_points = len(series.data_points)
            revisions = sum(1 for p in series.data_points if p.vintage_date is not None)

            # Average information lag
            lags = [p.get_information_lag().days for p in series.data_points]
            avg_lag = np.mean(lags) if lags else 0

            # Quality score
            quality_scores = [p.data_quality_score for p in series.data_points]
            avg_quality = np.mean(quality_scores) if quality_scores else 0

            reports.append({
                "series_id": series_id,
                "series_name": series.series_name,
                "category": series.category,
                "total_points": total_points,
                "revisions": revisions,
                "avg_information_lag_days": avg_lag,
                "avg_quality_score": avg_quality,
                "latest_observation": max(p.observation_date for p in series.data_points),
                "latest_release": max(p.release_date for p in series.data_points),
            })

        return pd.DataFrame(reports)


def create_pit_from_fred(
    series_id: str,
    fred_data: pd.Series,
    release_lag_days: int = 30,
    category: str = "unknown",
) -> PITSeries:
    """
    Create a PITSeries from FRED data with estimated release dates.

    Since FRED API doesn't always provide true vintage data, we estimate
    release dates based on typical publication schedules.

    Args:
        series_id: FRED series code
        fred_data: Series of values from FRED
        release_lag_days: estimated days between obs and release
        category: economic category

    Returns:
        PITSeries with estimated point-in-time data
    """
    from ..data_loader import INDICATOR_CONFIG

    series = PITSeries(
        series_id=series_id,
        series_name=INDICATOR_CONFIG.get(series_id, {}).get("description", series_id),
        frequency="M",  # Assume monthly, adjust based on data
        category=category,
        unit="index",
    )

    for obs_date, value in fred_data.items():
        if pd.isna(value):
            continue

        # Estimate release date (this is approximate!)
        release_date = obs_date + timedelta(days=release_lag_days)

        point = PITDataPoint(
            series_id=series_id,
            observation_date=obs_date.to_pydatetime() if hasattr(obs_date, 'to_pydatetime') else obs_date,
            release_date=release_date,
            value=float(value),
            source="FRED",
            source_type="estimated",  # Mark as estimated since we don't have true vintage
            data_quality_score=0.7,  # Lower quality due to estimated release dates
        )

        series.add_observation(point)

    return series
