"""
BLS (Bureau of Labor Statistics) API Client.

Provides access to:
- Consumer Price Index (CPI)
- Producer Price Index (PPI)
- Employment statistics
- Wage data
"""

import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .base_client import BaseDataClient, SeriesMetadata, logger


class BlsClient(BaseDataClient):
    """
    Client for BLS API v2.

    Documentation: https://www.bls.gov/developers/api_signature_v2.htm
    """

    # Common BLS series IDs
    SERIES = {
        # CPI
        "CPI_U_ALL": "CUUR0000SA0",  # All items
        "CPI_U_CORE": "CUUR0000SA0L1E",  # Core (ex food and energy)
        "CPI_U_FOOD": "CUUR0000SAF1",
        "CPI_U_ENERGY": "CUUR0000SA0E",

        # PPI
        "PPI_ALL": "WPUFD4",  # Finished goods
        "PPI_CORE": "WPUFD49207",  # Core PPI

        # Employment
        "UNEMPLOYMENT_RATE": "LNS14000000",
        "NONFARM_PAYROLLS": "CES0000000001",
        "LABOR_FORCE_PARTICIPATION": "LNS11300000",

        # Wages
        "AVG_HOURLY_EARNINGS": "CES0500000003",
    }

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("BLS_API_KEY")

        if not self.api_key:
            logger.warning("BLS_API_KEY not set. Using sample data mode.")

        super().__init__(
            source_name="bls",
            base_url="https://api.bls.gov/publicAPI/v2/timeseries/data",
            api_key=self.api_key,
            rate_limit=500,
            rate_limit_period="day",
            cache_duration_hours=24,
        )

    def fetch_series(
        self,
        series_id: str,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
    ) -> Tuple[Optional[pd.DataFrame], SeriesMetadata]:
        """
        Fetch a BLS time series.

        Args:
            series_id: BLS series ID
            start_year: Start year
            end_year: End year

        Returns:
            DataFrame and metadata
        """
        if not self.api_key:
            return self._get_sample_data(series_id)

        # Default date range
        if end_year is None:
            end_year = datetime.now().year
        if start_year is None:
            start_year = end_year - 10

        headers = {"Content-type": "application/json"}
        data = {
            "seriesid": [series_id],
            "startyear": str(start_year),
            "endyear": str(end_year),
            "registrationkey": self.api_key,
        }

        try:
            import json
            response_data, _ = self._make_request(
                "",
                params={},  # Data goes in body for POST
                method="POST",
            )

            # Note: BLS requires POST, would need to adjust base_client
            # For now, fall back to sample data
            logger.warning("BLS POST request requires additional implementation, using sample data")
            return self._get_sample_data(series_id)

        except Exception as e:
            logger.error(f"BLS fetch failed: {e}")
            return self._get_sample_data(series_id)

    def fetch_cpi(self) -> Tuple[Optional[pd.DataFrame], SeriesMetadata]:
        """Fetch CPI data."""
        return self.fetch_series(self.SERIES["CPI_U_ALL"])

    def fetch_core_cpi(self) -> Tuple[Optional[pd.DataFrame], SeriesMetadata]:
        """Fetch Core CPI data."""
        return self.fetch_series(self.SERIES["CPI_U_CORE"])

    def fetch_payrolls(self) -> Tuple[Optional[pd.DataFrame], SeriesMetadata]:
        """Fetch nonfarm payrolls."""
        return self.fetch_series(self.SERIES["NONFARM_PAYROLLS"])

    def fetch_unemployment_rate(self) -> Tuple[Optional[pd.DataFrame], SeriesMetadata]:
        """Fetch unemployment rate."""
        return self.fetch_series(self.SERIES["UNEMPLOYMENT_RATE"])

    def _get_sample_data(self, series_id: str) -> Tuple[Optional[pd.DataFrame], SeriesMetadata]:
        """Generate sample BLS data."""
        import numpy as np

        dates = pd.date_range(end=datetime.now(), periods=120, freq="M")

        # Generate appropriate values based on series type
        if "UNRATE" in series_id or "UNEMPLOYMENT" in series_id.upper():
            values = 5.0 + np.random.randn(120) * 1.5
            values = np.clip(values, 2, 15)
        elif "CPI" in series_id.upper():
            values = 250 + np.cumsum(np.random.randn(120) * 0.3)
        elif "EARNINGS" in series_id.upper():
            values = 25 + np.cumsum(np.random.randn(120) * 0.05)
        else:
            values = 100 + np.cumsum(np.random.randn(120) * 0.5)

        df = pd.DataFrame({series_id: values}, index=dates)

        metadata = SeriesMetadata(
            series_id=series_id,
            source="bls",
            frequency="monthly",
            category="prices" if "CPI" in series_id.upper() or "PPI" in series_id.upper() else "labour",
            description=f"Sample BLS data for {series_id}",
            last_observation_date=dates[-1],
            source_reliability=0.5,
            is_sample_data=True,
        )

        return df, metadata

    def get_series_info(self, series_id: str) -> Optional[SeriesMetadata]:
        """Get metadata for a BLS series."""
        return SeriesMetadata(
            series_id=series_id,
            source="bls",
            frequency="monthly",
            category="labour",
            description=f"BLS series {series_id}",
        )
