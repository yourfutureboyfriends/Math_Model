"""
fred_connector.py — Pull macro data from the FRED API.

Financial context:
  The Federal Reserve Economic Data (FRED) database is the gold standard for
  free, comprehensive US macroeconomic data. It contains over 800,000 time
  series from 100+ sources including the Fed, BEA, BLS, and Census Bureau.

  Key series for this model:
    - GDP (GDP): Real gross domestic product, quarterly
    - CPI (CPIAUCSL): Consumer price index, monthly
    - Core CPI (CPILFESL): CPI ex-food/energy, monthly
    - PPI (PPIACO): Producer price index, monthly
    - Unemployment (UNRATE): Unemployment rate, monthly
    - Industrial production (INDPRO): Manufacturing/mining output, monthly
    - Retail sales (RSXFS): Total retail sales, monthly
    - PCE (PCEPI): Personal consumption expenditures price index
    - M2 (M2SL): Money supply measure, monthly
    - Fed Funds (FEDFUNDS): Policy rate, monthly
    - 10Y Treasury (DGS10): 10-year yield, daily
    - 2Y Treasury (DGS2): 2-year yield, daily
    - VIX (VIXCLS): Volatility index, daily
    - HY spreads (BAMLH0A0HYM2): High yield credit spreads, monthly

  API access: Free with registration at https://fred.stlouisfed.org/docs/api/api_key.html

Design notes:
  - Implements caching to avoid redundant API calls
  - Handles frequency conversion (daily -> monthly)
  - Graceful degradation: returns empty DataFrame if API unavailable
"""

import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import logging

# Set up logging
logger = logging.getLogger(__name__)

# Try to import fredapi, provide stub if unavailable
try:
    from fredapi import Fred
    FREDAPI_AVAILABLE = True
except ImportError:
    FREDAPI_AVAILABLE = False
    logger.warning("fredapi package not installed. FRED data will be unavailable.")


class FredConnector:
    """
    Connector to Federal Reserve Economic Data (FRED) API.

    Handles:
      - API authentication
      - Data fetching with caching
      - Frequency conversion (daily -> monthly aggregation)
      - Series alignment to common date range
    """

    def __init__(self, api_key: Optional[str] = None, cache_dir: Optional[Path] = None):
        """
        Initialize the FRED connector.

        Args:
            api_key: FRED API key. If None, attempts to load from FRED_API_KEY env var.
            cache_dir: Directory to cache fetched data. If None, uses config default.
        """
        self.api_key = api_key
        self.client: Optional[object] = None
        self._initialized = False

        # Import config here to avoid circular imports
        from settings import FRED_CACHE_DIR
        self.cache_dir = Path(cache_dir) if cache_dir else FRED_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _initialize(self) -> bool:
        """
        Initialize the FRED API client.

        Returns:
            True if initialization successful, False otherwise.
        """
        if self._initialized:
            return True

        if not FREDAPI_AVAILABLE:
            logger.warning("fredapi package not available. Cannot fetch FRED data.")
            return False

        if not self.api_key:
            import os
            self.api_key = os.getenv("FRED_API_KEY", "")

        if not self.api_key:
            logger.warning("No FRED API key provided. Set FRED_API_KEY environment variable.")
            return False

        try:
            self.client = Fred(api_key=self.api_key)
            self._initialized = True
            logger.info("FRED API client initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize FRED client: {e}")
            return False

    def fetch_series(
        self,
        series_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        frequency: Optional[str] = None,
        units: Optional[str] = None,
        force_refresh: bool = False,
    ) -> pd.Series:
        """
        Fetch a single series from FRED.

        Args:
            series_id: FRED series ID (e.g., "GDP", "CPIAUCSL")
            start_date: Start date as "YYYY-MM-DD". Defaults to 5 years ago.
            end_date: End date as "YYYY-MM-DD". Defaults to today.
            frequency: Frequency code ("d"=daily, "m"=monthly, "q"=quarterly, "a"=annual)
            units: Units code ("lin"=levels, "pc1"=YoY%, "chg"=change)
            force_refresh: If True, ignore cache and re-fetch from API

        Returns:
            pd.Series indexed by date, or empty Series if fetch fails.
        """
        if not self._initialize():
            return pd.Series(dtype=float)

        # Default date range: last 10 years
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=3650)).strftime("%Y-%m-%d")

        # Cache key
        cache_file = self.cache_dir / f"{series_id}_{start_date}_{end_date}_{frequency}_{units}.csv"

        # Check cache unless force refresh
        if not force_refresh and cache_file.exists():
            cache_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            from settings import REFRESH_CACHE_HOURS

            if cache_age < timedelta(hours=REFRESH_CACHE_HOURS):
                logger.debug(f"Loading {series_id} from cache")
                s = pd.read_csv(cache_file, index_col=0, parse_dates=True).iloc[:, 0]
                s.name = series_id
                return s

        # Fetch from API
        try:
            logger.info(f"Fetching {series_id} from FRED API")

            # Build observation parameters
            params = {
                "observation_start": start_date,
                "observation_end": end_date,
            }
            if frequency:
                freq_map = {"d": "d", "m": "m", "q": "q", "a": "a"}
                if frequency in freq_map:
                    params["frequency"] = freq_map[frequency]
            if units:
                params["units"] = units

            series = self.client.get_series(series_id, **params)

            # Rename to series_id
            series.name = series_id

            # Convert to monthly if daily
            if frequency == "d" or (series.index.freq is None and len(series) > 500):
                # Convert daily to month-end
                series = series.resample("ME").last()

            # Save to cache
            series.to_csv(cache_file)

            return series

        except Exception as e:
            logger.error(f"Failed to fetch {series_id}: {e}")
            return pd.Series(dtype=float)

    def fetch_multiple(
        self,
        series_map: dict[str, tuple],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """
        Fetch multiple series and align them.

        Args:
            series_map: Dict mapping internal column name to (series_id, freq, units)
            start_date: Start date as "YYYY-MM-DD"
            end_date: End date as "YYYY-MM-DD"
            force_refresh: If True, ignore cache and re-fetch

        Returns:
            DataFrame with columns named by series_map keys, indexed by date.
        """
        data = {}

        for col_name, (series_id, freq, units) in series_map.items():
            series = self.fetch_series(
                series_id=series_id,
                start_date=start_date,
                end_date=end_date,
                frequency=freq,
                units=units,
                force_refresh=force_refresh,
            )
            if not series.empty:
                data[col_name] = series

        if not data:
            logger.warning("No data fetched from FRED")
            return pd.DataFrame()

        # Combine into DataFrame
        df = pd.DataFrame(data)

        # Forward fill any missing values (FRED sometimes has gaps)
        df = df.ffill()

        return df

    def get_series_info(self, series_id: str) -> dict:
        """
        Get metadata about a FRED series.

        Args:
            series_id: FRED series ID

        Returns:
            Dictionary with series metadata or empty dict if unavailable.
        """
        if not self._initialize():
            return {}

        try:
            info = self.client.get_series_info(series_id)
            return {
                "id": info.get("id"),
                "title": info.get("title"),
                "frequency": info.get("frequency_short"),
                "units": info.get("units_short"),
                "notes": info.get("notes", "")[:500],  # Truncate long notes
            }
        except Exception as e:
            logger.error(f"Failed to get info for {series_id}: {e}")
            return {}

    def is_available(self) -> bool:
        """Check if FRED API is available and configured."""
        return self._initialize()


# Convenience function for direct usage
def fetch_fred_data(
    api_key: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Fetch all configured macro indicators from FRED.

    This is a convenience wrapper that fetches the standard set of indicators
    used by the macro regime model.

    Args:
        api_key: FRED API key. If None, uses FRED_API_KEY env var.
        start_date: Start date as "YYYY-MM-DD"
        end_date: End date as "YYYY-MM-DD"

    Returns:
        DataFrame with all standard indicators, indexed by date.
    """
    connector = FredConnector(api_key=api_key)

    if not connector.is_available():
        logger.warning("FRED API not available. Returning empty DataFrame.")
        return pd.DataFrame()

    from settings import FRED_SERIES

    return connector.fetch_multiple(
        series_map=FRED_SERIES,
        start_date=start_date,
        end_date=end_date,
    )
