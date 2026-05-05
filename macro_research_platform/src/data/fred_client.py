"""
FRED (Federal Reserve Economic Data) API Client.

Provides access to:
- Economic time series data
- Series metadata
- Category information
- Real-time and historical observations
"""

import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

import pandas as pd

from .base_client import BaseDataClient, SeriesMetadata, DataFreshness, logger


class FredClient(BaseDataClient):
    """
    Client for FRED API.

    FRED provides economic data from the Federal Reserve and other sources.
    Rate limit: 120 requests per minute (with API key)
    Documentation: https://fred.stlouisfed.org/docs/api/fred/
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_duration_hours: int = 24,
    ):
        # Get API key from environment or argument
        self.api_key = api_key or os.getenv("FRED_API_KEY")

        if not self.api_key:
            logger.warning("FRED_API_KEY not set. Using sample data mode.")

        super().__init__(
            source_name="fred",
            base_url="https://api.stlouisfed.org/fred",
            api_key=self.api_key,
            rate_limit=100,
            rate_limit_period="minute",
            cache_duration_hours=cache_duration_hours,
        )

    def _make_fred_request(
        self,
        endpoint: str,
        params: Dict[str, Any],
    ) -> Optional[Dict]:
        """Make a request to FRED API."""
        if not self.api_key:
            logger.error("Cannot make FRED request: API key not available")
            return None

        params["api_key"] = self.api_key
        params["file_type"] = "json"

        data, _ = self._make_request(
            f"{endpoint}",
            params=params,
            use_cache=True,
        )

        return data

    def get_series_info(self, series_id: str) -> Optional[SeriesMetadata]:
        """Get metadata for a FRED series."""
        if not self.api_key:
            return self._get_sample_metadata(series_id)

        data = self._make_fred_request(
            "series",
            {"series_id": series_id},
        )

        if not data or "seriess" not in data:
            logger.warning(f"Could not fetch series info for {series_id}")
            return None

        series_data = data["seriess"][0]

        return SeriesMetadata(
            series_id=series_id,
            source="fred",
            frequency=series_data.get("frequency_short", "M").lower(),
            category=series_data.get("category", "economic"),
            description=series_data.get("title", ""),
            units=series_data.get("units", ""),
            last_observation_date=None,  # Will be populated when fetching data
            source_reliability=0.95,
            is_sample_data=False,
        )

    def fetch_series(
        self,
        series_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        frequency: Optional[str] = None,
    ) -> Tuple[Optional[pd.DataFrame], SeriesMetadata]:
        """
        Fetch a data series from FRED.

        Args:
            series_id: FRED series ID (e.g., 'GDPC1', 'UNRATE')
            start_date: Start date for data
            end_date: End date for data
            frequency: Frequency to convert to (optional)

        Returns:
            Tuple of (DataFrame with date/value columns, metadata)
        """
        if not self.api_key:
            logger.warning(f"No FRED API key, returning sample data for {series_id}")
            return self._get_sample_data(series_id)

        # Get metadata first
        metadata = self.get_series_info(series_id)
        if not metadata:
            return None, SeriesMetadata(
                series_id=series_id,
                source="fred",
                frequency="unknown",
                category="unknown",
            )

        # Build request params
        params = {
            "series_id": series_id,
            "sort_order": "asc",
        }

        if start_date:
            params["observation_start"] = start_date.strftime("%Y-%m-%d")
        if end_date:
            params["observation_end"] = end_date.strftime("%Y-%m-%d")

        # Fetch observations
        data = self._make_fred_request("observations", params)

        if not data or "observations" not in data:
            logger.warning(f"No observations returned for {series_id}")
            return None, metadata

        # Convert to DataFrame
        observations = data["observations"]
        df = pd.DataFrame(observations)

        if df.empty:
            logger.warning(f"Empty data returned for {series_id}")
            return None, metadata

        # Parse dates and values
        df["date"] = pd.to_datetime(df["date"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")

        # Drop missing values
        df = df.dropna(subset=["value"])

        # Set date as index
        df = df.set_index("date")[["value"]]
        df.columns = [series_id]

        # Update metadata with latest date
        if not df.empty:
            metadata.last_observation_date = df.index.max()

        logger.info(f"Fetched {len(df)} observations for {series_id}")

        return df, metadata

    def fetch_multiple_series(
        self,
        series_ids: List[str],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Fetch multiple series and merge into a single DataFrame.

        Args:
            series_ids: List of FRED series IDs
            start_date: Start date
            end_date: End date

        Returns:
            DataFrame with series as columns and dates as index
        """
        all_data = {}

        for series_id in series_ids:
            df, _ = self.fetch_series(series_id, start_date, end_date)
            if df is not None and not df.empty:
                all_data[series_id] = df[series_id]

        if not all_data:
            logger.warning("No data fetched for any series")
            return pd.DataFrame()

        return pd.DataFrame(all_data)

    def search_series(
        self,
        search_text: str,
        limit: int = 10,
    ) -> List[Dict]:
        """Search for FRED series by text."""
        if not self.api_key:
            logger.error("Cannot search: FRED API key not available")
            return []

        data = self._make_fred_request(
            "series/search",
            {
                "search_text": search_text,
                "limit": limit,
            },
        )

        if data and "seriess" in data:
            return data["seriess"]

        return []

    def get_category_series(
        self,
        category_id: int = 0,
        limit: int = 100,
    ) -> List[Dict]:
        """Get series for a FRED category."""
        if not self.api_key:
            logger.error("Cannot fetch category: FRED API key not available")
            return []

        data = self._make_fred_request(
            "category/series",
            {
                "category_id": category_id,
                "limit": limit,
            },
        )

        if data and "seriess" in data:
            return data["seriess"]

        return []

    def _get_sample_data(self, series_id: str) -> Tuple[Optional[pd.DataFrame], SeriesMetadata]:
        """Generate sample data for testing without API key."""
        import numpy as np

        # Generate sample dates (monthly, last 5 years)
        dates = pd.date_range(
            end=datetime.now(),
            periods=60,
            freq="M",
        )

        # Generate sample values based on series ID
        np.random.seed(hash(series_id) % 2**32)

        if "UNRATE" in series_id or "RATE" in series_id:
            values = 5 + np.random.randn(60) * 1.5
        elif "GDP" in series_id or "PAYEMS" in series_id:
            values = 100 + np.cumsum(np.random.randn(60) * 0.5)
        elif "CPI" in series_id or "PPI" in series_id:
            values = 2 + np.random.randn(60) * 0.5
        elif "STOCK" in series_id or "SP500" in series_id or "VIX" in series_id:
            values = 100 * np.exp(np.cumsum(np.random.randn(60) * 0.05))
        else:
            values = np.random.randn(60) * 10 + 50

        df = pd.DataFrame({series_id: values}, index=dates)

        metadata = SeriesMetadata(
            series_id=series_id,
            source="fred",
            frequency="monthly",
            category="sample",
            description=f"Sample data for {series_id}",
            units="index",
            last_observation_date=dates[-1],
            source_reliability=0.5,
            is_sample_data=True,
        )

        logger.info(f"Generated sample data for {series_id}")

        return df, metadata

    def _get_sample_metadata(self, series_id: str) -> SeriesMetadata:
        """Generate sample metadata."""
        return SeriesMetadata(
            series_id=series_id,
            source="fred",
            frequency="monthly",
            category="sample",
            description=f"Sample data for {series_id}",
            is_sample_data=True,
            source_reliability=0.5,
        )


# Convenience function
def get_fred_client() -> FredClient:
    """Get a configured FRED client."""
    return FredClient()
