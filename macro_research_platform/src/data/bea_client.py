"""
BEA (Bureau of Economic Analysis) API Client.

Provides access to:
- National Income and Product Accounts (NIPA)
- Fixed Assets
- Regional data
- International data
"""

import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .base_client import BaseDataClient, SeriesMetadata, logger


class BeaClient(BaseDataClient):
    """
    Client for BEA API.

    Documentation: https://apps.bea.gov/API/bea_web_service_api_user_guide.htm
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("BEA_API_KEY")

        if not self.api_key:
            logger.warning("BEA_API_KEY not set. BEA client will use placeholder mode.")

        super().__init__(
            source_name="bea",
            base_url="https://apps.bea.gov/api/data",
            api_key=self.api_key,
            rate_limit=100,
            rate_limit_period="day",
            cache_duration_hours=24 * 7,  # Weekly refresh for BEA
        )

    def fetch_nipa_series(
        self,
        table_name: str,
        frequency: str = "Q",  # A, Q, M
    ) -> Tuple[Optional[pd.DataFrame], SeriesMetadata]:
        """
        Fetch NIPA table data.

        Args:
            table_name: BEA table name (e.g., "T10101")
            frequency: A (annual), Q (quarterly), M (monthly)

        Returns:
            DataFrame and metadata
        """
        if not self.api_key:
            logger.warning(f"No BEA API key, returning sample data for {table_name}")
            return self._get_sample_data(table_name, "quarterly")

        params = {
            "UserID": self.api_key,
            "Method": "GetData",
            "DatasetName": "NIPA",
            "TableName": table_name,
            "Frequency": frequency,
            "Year": "ALL",
            "ResultFormat": "JSON",
        }

        try:
            data, _ = self._make_request("", params=params)

            if data and "BEAAPI" in data:
                results = data["BEAAPI"].get("Results", {})
                if "Data" in results:
                    df = pd.DataFrame(results["Data"])
                    # Parse and clean
                    df["DataValue"] = pd.to_numeric(df["DataValue"].str.replace(",", ""), errors="coerce")
                    df["TimePeriod"] = pd.to_datetime(df["TimePeriod"])
                    df = df.set_index("TimePeriod")[["DataValue"]]
                    df.columns = [f"BEA_{table_name}"]

                    metadata = SeriesMetadata(
                        series_id=f"BEA_{table_name}",
                        source="bea",
                        frequency="quarterly" if frequency == "Q" else "annual",
                        category="national_accounts",
                        description=f"BEA {table_name}",
                        last_observation_date=df.index.max(),
                        source_reliability=0.95,
                    )

                    return df, metadata

        except Exception as e:
            logger.error(f"BEA fetch failed: {e}")

        return self._get_sample_data(table_name, "quarterly")

    def fetch_gdp_current_dollar(self) -> Tuple[Optional[pd.DataFrame], SeriesMetadata]:
        """Fetch current-dollar GDP (Table 1.1.5)."""
        return self.fetch_nipa_series("T10105")

    def fetch_gdp_real(self) -> Tuple[Optional[pd.DataFrame], SeriesMetadata]:
        """Fetch real GDP (Table 1.1.6)."""
        return self.fetch_nipa_series("T10106")

    def _get_sample_data(
        self,
        series_id: str,
        frequency: str,
    ) -> Tuple[Optional[pd.DataFrame], SeriesMetadata]:
        """Generate sample BEA data."""
        import numpy as np

        periods = 40 if frequency == "quarterly" else 10
        end_date = datetime.now()

        if frequency == "quarterly":
            dates = pd.date_range(end=end_date, periods=periods, freq="Q")
            values = 20000 + np.cumsum(np.random.randn(periods) * 100)
        else:
            dates = pd.date_range(end=end_date, periods=periods, freq="Y")
            values = 20000 + np.cumsum(np.random.randn(periods) * 400)

        df = pd.DataFrame({series_id: values}, index=dates)

        metadata = SeriesMetadata(
            series_id=series_id,
            source="bea",
            frequency=frequency,
            category="national_accounts",
            description=f"Sample BEA data for {series_id}",
            last_observation_date=dates[-1],
            source_reliability=0.5,
            is_sample_data=True,
        )

        return df, metadata

    def get_series_info(self, series_id: str) -> Optional[SeriesMetadata]:
        """Get metadata for a BEA series."""
        return SeriesMetadata(
            series_id=series_id,
            source="bea",
            frequency="quarterly",
            category="national_accounts",
            description=f"BEA series {series_id}",
        )

    def fetch_series(self, series_id: str, **kwargs):
        """Generic fetch method (BEA-specific tables)."""
        return self.fetch_nipa_series(series_id)
