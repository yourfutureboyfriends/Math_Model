"""
OECD Data API Client.

Fetches key macro indicators from the OECD SDMX REST API.
No API key required — public endpoint.

Key series:
  - Composite Leading Indicators (CLI): forward-looking growth signal for each G20 country
  - CPI inflation: cross-country comparison
  - Unemployment rates: labour market depth
  - Business confidence surveys

OECD CLI Methodology:
  The OECD CLI is designed to provide early signals of turning points in
  economic activity. Amplitude-adjusted so amplitude matches GDP cycles.
  CLI > 100 = above-trend, < 100 = below-trend.
  Month-on-month change in CLI = leading indicator of GDP direction.

References:
  OECD (2012), OECD System of Composite Leading Indicators
  OECD Data Explorer: https://data-explorer.oecd.org/

Endpoint: https://sdmx.oecd.org/public/rest/data/{dataset}/{filter}
"""

import io
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

logger = logging.getLogger(__name__)


class OecdClient:
    """
    Client for OECD SDMX REST API.

    Fetches CLI (Composite Leading Indicators) and other macro series
    for the US and major trading partners.

    Usage:
        client = OecdClient()
        df = client.fetch_all_series()
    """

    BASE_URL = "https://sdmx.oecd.org/public/rest/data"

    # Country codes for key economies
    COUNTRIES = {
        "USA": "United States",
        "EA19": "Euro Area",
        "CHN": "China",
        "JPN": "Japan",
        "GBR": "United Kingdom",
        "G-7": "G7 Average",
    }

    # OECD CLI series definitions
    # Format: (dataset, key_filter, local_column_name)
    CLI_SERIES = [
        ("MEI_CLI", "USA.LOLITOAA.M",  "oecd_us_cli"),
        ("MEI_CLI", "EA19.LOLITOAA.M", "oecd_eu_cli"),
        ("MEI_CLI", "CHN.LOLITOAA.M",  "oecd_china_cli"),
        ("MEI_CLI", "JPN.LOLITOAA.M",  "oecd_japan_cli"),
        ("MEI_CLI", "GBR.LOLITOAA.M",  "oecd_uk_cli"),
    ]

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        cache_hours: int = 24 * 7,   # Weekly refresh (OECD publishes monthly)
        timeout: int = 30,
    ):
        if cache_dir is None:
            # Default: project-level cache
            _here = Path(__file__).parent.parent.parent
            cache_dir = _here / "data" / "processed" / "oecd_cache"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_hours = cache_hours
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.sdmx.data+csv;version=1.0.0",
            "User-Agent": "MacroResearchPlatform/2.0",
        })

    def _cache_path(self, dataset: str, key: str) -> Path:
        safe_key = key.replace("/", "_").replace(".", "_")
        return self.cache_dir / f"{dataset}_{safe_key}.csv"

    def _is_fresh(self, path: Path) -> bool:
        if not path.exists():
            return False
        age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
        return age < timedelta(hours=self.cache_hours)

    def fetch_series(
        self,
        dataset: str,
        key: str,
        local_name: str,
        start_period: str = "2000-01",
        force_refresh: bool = False,
    ) -> Optional[pd.Series]:
        """
        Fetch a single OECD SDMX series.

        Args:
            dataset:    OECD dataset identifier (e.g., "MEI_CLI")
            key:        SDMX key filter (e.g., "USA.LOLITOAA.M")
            local_name: Column name to assign in the output DataFrame
            start_period: ISO 8601 period start (e.g., "2000-01")
            force_refresh: Ignore cache

        Returns:
            pd.Series indexed by date, or None if fetch fails
        """
        cache_file = self._cache_path(dataset, key)

        if not force_refresh and self._is_fresh(cache_file):
            try:
                s = pd.read_csv(cache_file, index_col=0, parse_dates=True).iloc[:, 0]
                s.name = local_name
                logger.debug(f"OECD cache hit: {local_name}")
                return s
            except Exception:
                pass

        url = f"{self.BASE_URL}/{dataset}/{key}"
        params = {
            "startPeriod": start_period,
            "format": "csvfile",
        }

        try:
            logger.info(f"Fetching OECD series: {dataset}/{key}")
            resp = self.session.get(url, params=params, timeout=self.timeout)

            if resp.status_code == 404:
                logger.warning(f"OECD series not found: {dataset}/{key}")
                return None

            resp.raise_for_status()

            # Parse SDMX CSV response
            df = pd.read_csv(io.StringIO(resp.text))

            # OECD SDMX CSV format: TIME_PERIOD column + OBS_VALUE column
            if "TIME_PERIOD" not in df.columns or "OBS_VALUE" not in df.columns:
                # Try alternate column names
                time_col = next(
                    (c for c in df.columns if "TIME" in c.upper() or "PERIOD" in c.upper()), None
                )
                val_col = next(
                    (c for c in df.columns if "OBS" in c.upper() or "VALUE" in c.upper()), None
                )
                if not time_col or not val_col:
                    logger.warning(f"Unexpected OECD CSV format for {local_name}: {df.columns.tolist()}")
                    return None
            else:
                time_col, val_col = "TIME_PERIOD", "OBS_VALUE"

            df = df[[time_col, val_col]].copy()
            df[time_col] = pd.to_datetime(df[time_col], infer_datetime_format=True)
            df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
            df = df.dropna().sort_values(time_col)
            series = df.set_index(time_col)[val_col]
            series.index.name = "date"
            series.name = local_name

            # Resample to month-end for consistency
            series = series.resample("ME").last()

            # Cache
            series.to_csv(cache_file)
            logger.info(f"OECD series fetched: {local_name} ({len(series)} obs)")
            return series

        except requests.exceptions.Timeout:
            logger.warning(f"OECD request timed out for {local_name}")
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"OECD request failed for {local_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching OECD {local_name}: {e}")
            return None

    def fetch_all_series(
        self,
        start_period: str = "2000-01",
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """
        Fetch all configured CLI and macro series.

        Returns:
            DataFrame with OECD series as columns, indexed by month-end date.
            Empty columns are dropped. Returns empty DataFrame on complete failure.
        """
        collected = {}

        for dataset, key, local_name in self.CLI_SERIES:
            series = self.fetch_series(
                dataset, key, local_name,
                start_period=start_period,
                force_refresh=force_refresh
            )
            if series is not None and not series.empty:
                collected[local_name] = series

        if not collected:
            logger.warning("No OECD series could be fetched — check network connectivity")
            return pd.DataFrame()

        df = pd.DataFrame(collected)
        logger.info(f"OECD data assembled: {len(df)} rows, {len(df.columns)} series")
        return df

    def compute_global_cli_composite(self, df: Optional[pd.DataFrame] = None) -> Optional[pd.Series]:
        """
        Compute an equal-weighted composite CLI across available economies.

        The composite OECD CLI is a better global growth leading indicator
        than any single country CLI.

        Returns:
            pd.Series of global CLI composite, or None if no data available.
        """
        if df is None:
            df = self.fetch_all_series()
        if df.empty:
            return None

        cli_cols = [c for c in df.columns if "cli" in c.lower()]
        if not cli_cols:
            return None

        # Compute MoM % change for each CLI (standardised)
        changes = df[cli_cols].pct_change(1)
        composite = changes.mean(axis=1)
        composite.name = "global_cli_composite"
        return composite

    def is_available(self) -> bool:
        """Quick connectivity test."""
        try:
            resp = self.session.get(
                f"{self.BASE_URL}/MEI_CLI/USA.LOLITOAA.M",
                params={"startPeriod": "2024-01", "endPeriod": "2024-03", "format": "csvfile"},
                timeout=5
            )
            return resp.status_code in (200, 204)
        except Exception:
            return False
