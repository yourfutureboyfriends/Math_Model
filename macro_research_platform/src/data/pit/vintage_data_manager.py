"""
Vintage Data Manager

Integrates with ALFRED (Archival Federal Reserve Economic Data) to get
true point-in-time macro data for backtesting.

ALFRED provides historical vintages of FRED data, showing what values
were available on specific past dates.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

import pandas as pd
import requests

from .point_in_time_store import PITDataPoint, PITSeries, PointInTimeStore

logger = logging.getLogger(__name__)


class AlfredVintageClient:
    """
    Client for ALFRED vintage data.

    ALFRED provides historical snapshots of FRED data, allowing
    reconstruction of what data was available on any past date.

    API documentation: https://alfred.stlouisfed.org/help.html
    """

    BASE_URL = "https://api.stlouisfed.org/fred"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.cache_dir = Path("data/alfred_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _make_request(self, endpoint: str, params: Dict) -> Optional[Dict]:
        """Make API request with error handling."""
        if not self.api_key:
            logger.warning("No ALFRED API key provided")
            return None

        url = f"{self.BASE_URL}/{endpoint}"
        params["api_key"] = self.api_key
        params["file_type"] = "json"

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"ALFRED API request failed: {e}")
            return None

    def get_vintages(
        self,
        series_id: str,
        vintage_dates: Optional[List[datetime]] = None
    ) -> Optional[pd.DataFrame]:
        """
        Get all vintages of a series.

        Returns DataFrame with:
        - observation_date
        - vintage_date
        - value
        """
        if not self.api_key:
            logger.info(f"No API key, returning None for {series_id} vintages")
            return None

        cache_file = self.cache_dir / f"{series_id}_vintages.parquet"

        # Check cache
        if cache_file.exists():
            logger.info(f"Loading {series_id} vintages from cache")
            return pd.read_parquet(cache_file)

        # Fetch from ALFRED
        params = {"series_id": series_id}

        if vintage_dates:
            # Request specific vintages
            for vd in vintage_dates:
                params["vintage_date"] = vd.strftime("%Y-%m-%d")
        else:
            # Request all vintages
            params["vintage_date"] = "all"

        data = self._make_request("series/vintagedates", params)

        if not data or "vintage_dates" not in data:
            return None

        # Process vintage dates
        vintages = []
        for vd in data["vintage_dates"]:
            vintage_date = pd.to_datetime(vd["vintage_date"])

            # Get observations for this vintage
            obs_data = self._make_request(
                "series/observations",
                {
                    "series_id": series_id,
                    "vintage_date": vintage_date.strftime("%Y-%m-%d"),
                }
            )

            if obs_data and "observations" in obs_data:
                for obs in obs_data["observations"]:
                    vintages.append({
                        "series_id": series_id,
                        "observation_date": pd.to_datetime(obs["date"]),
                        "vintage_date": vintage_date,
                        "value": float(obs["value"]) if obs["value"] != "." else None,
                    })

        if not vintages:
            return None

        df = pd.DataFrame(vintages)

        # Cache results
        df.to_parquet(cache_file)

        return df

    def get_series_as_of(
        self,
        series_id: str,
        as_of_date: datetime
    ) -> Optional[pd.Series]:
        """
        Get a series as it appeared on a specific date.

        This is the key point-in-time query.
        """
        vintages = self.get_vintages(series_id)

        if vintages is None:
            return None

        # Filter to vintage that was current as_of_date
        current_vintage = vintages[vintages["vintage_date"] <= as_of_date]

        if current_vintage.empty:
            return None

        # Get the latest vintage as of that date
        latest_vintage = current_vintage["vintage_date"].max()

        # Return that vintage's data
        data = current_vintage[current_vintage["vintage_date"] == latest_vintage]

        return pd.Series(
            data["value"].values,
            index=pd.DatetimeIndex(data["observation_date"]),
            name=series_id
        )


class VintageDataManager:
    """
    Manages vintage data for backtesting.

    Combines ALFRED data (when available) with estimated release dates
    (when ALFRED is not available).
    """

    def __init__(
        self,
        pit_store: PointInTimeStore,
        alfred_client: Optional[AlfredVintageClient] = None
    ):
        self.pit_store = pit_store
        self.alfred = alfred_client

        # Track which series have true vintage data vs estimates
        self.vintage_quality: Dict[str, str] = {}

    def load_series_vintages(
        self,
        series_id: str,
        use_alfred: bool = True
    ) -> bool:
        """
        Load vintage data for a series into the PIT store.

        Returns True if true vintage data was loaded, False if using estimates.
        """
        if use_alfred and self.alfred:
            alfred_data = self.alfred.get_vintages(series_id)

            if alfred_data is not None and not alfred_data.empty:
                # Convert ALFRED data to PIT format
                series = PITSeries(
                    series_id=series_id,
                    series_name=series_id,  # Would look up proper name
                    frequency="M",
                    category="unknown",
                    unit="index",
                )

                for _, row in alfred_data.iterrows():
                    point = PITDataPoint(
                        series_id=series_id,
                        observation_date=row["observation_date"].to_pydatetime(),
                        release_date=row["vintage_date"].to_pydatetime(),
                        value=row["value"],
                        vintage_date=row["vintage_date"].to_pydatetime(),
                        source="ALFRED",
                        source_type="vintage",
                        data_quality_score=1.0,  # True vintage = highest quality
                    )
                    series.add_observation(point)

                self.pit_store.series[series_id] = series
                self.vintage_quality[series_id] = "true_vintage"
                return True

        # Fall back to estimated release dates
        self.vintage_quality[series_id] = "estimated"
        return False

    def get_data_availability_report(self) -> pd.DataFrame:
        """
        Report on data availability and quality across all series.
        """
        reports = []

        for series_id, quality in self.vintage_quality.items():
            series = self.pit_store.series.get(series_id)
            if not series:
                continue

            reports.append({
                "series_id": series_id,
                "vintage_quality": quality,
                "total_observations": len(series.data_points),
                "date_range": f"{min(p.observation_date for p in series.data_points)} to "
                              f"{max(p.observation_date for p in series.data_points)}",
                "revisions_available": quality == "true_vintage",
            })

        return pd.DataFrame(reports)

    def get_backtest_data_quality(self) -> str:
        """
        Assess overall quality for backtesting.
        """
        true_vintage = sum(1 for q in self.vintage_quality.values() if q == "true_vintage")
        estimated = sum(1 for q in self.vintage_quality.values() if q == "estimated")
        total = true_vintage + estimated

        if total == 0:
            return "No data loaded"

        true_pct = true_vintage / total * 100

        if true_pct >= 80:
            return f"High quality: {true_pct:.0f}% true vintage data"
        elif true_pct >= 50:
            return f"Medium quality: {true_pct:.0f}% true vintage, {100-true_pct:.0f}% estimated"
        else:
            return f"Low quality: {true_pct:.0f}% true vintage, {100-true_pct:.0f}% estimated - backtests approximate"


def check_data_availability_for_backtest(
    start_date: datetime,
    end_date: datetime,
    required_series: List[str],
    vintage_manager: VintageDataManager
) -> Dict:
    """
    Check if sufficient data is available for a backtest period.

    Returns dict with availability status and warnings.
    """
    results = {
        "backtest_period": f"{start_date.date()} to {end_date.date()}",
        "required_series": required_series,
        "available_series": [],
        "missing_series": [],
        "warnings": [],
        "usable": True,
    }

    for series_id in required_series:
        if series_id in vintage_manager.pit_store.series:
            results["available_series"].append(series_id)
        else:
            results["missing_series"].append(series_id)
            results["usable"] = False

    # Check data quality
    quality = vintage_manager.get_backtest_data_quality()
    if "Low quality" in quality or "approximate" in quality:
        results["warnings"].append(quality)

    return results
