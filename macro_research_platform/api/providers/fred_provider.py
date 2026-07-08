"""
FRED Data Provider — Raw economic data access from Federal Reserve Economic Data.

Fetches macroeconomic time series from the St. Louis Fed API.
No business logic, no caching, no fallbacks.
"""

import logging
import os
from typing import Dict, Optional, Any, List
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class FREDObservation:
    """Single FRED observation."""
    series_id: str
    date: str
    value: float
    realtime_start: Optional[str] = None
    realtime_end: Optional[str] = None


@dataclass
class FREDResult:
    """Result of a FRED fetch operation."""
    success: bool
    data: Optional[List[FREDObservation]]
    error: Optional[str] = None
    latency_ms: float = 0.0
    records_fetched: int = 0


class FREDProvider:
    """
    Provider for FRED (Federal Reserve Economic Data) API.

    Responsibilities:
    - Fetch raw macroeconomic series
    - Handle API key from environment
    - Parse FRED JSON responses
    - Log failures clearly

    Does NOT:
    - Cache data
    - Apply unit conversions (normalization layer handles this)
    - Provide fallback values
    """

    BASE_URL = "https://api.stlouisfed.org/fred"

    # Common series IDs
    SERIES = {
        # Interest rates
        "FEDFUNDS": "Federal Funds Effective Rate",
        "DFEDTARU": "Federal Funds Target Rate (Upper)",
        "DGS1MO": "1-Month Treasury",
        "DGS3MO": "3-Month Treasury",
        "DGS2": "2-Year Treasury",
        "DGS5": "5-Year Treasury",
        "DGS10": "10-Year Treasury",
        "DGS30": "30-Year Treasury",
        "T10Y2Y": "10-Year minus 2-Year Spread",
        "T10Y3M": "10-Year minus 3-Month Spread",

        # Inflation
        "CPIAUCSL": "Consumer Price Index (All Urban)",
        "CPILFESL": "Core CPI (Less Food & Energy)",
        "PCE": "Personal Consumption Expenditures",

        # Growth
        "GDP": "Gross Domestic Product",
        "A191RL1Q225SBEA": "Real GDP Growth",
        "INDPRO": "Industrial Production Index",

        # Labor
        "UNRATE": "Unemployment Rate",
        "PAYEMS": "Nonfarm Payrolls",
        "SAHMREALTIME": "Sahm Rule Real-Time",
        "CIVPART": "Labor Force Participation",

        # Credit
        "BAMLH0A0HYM2": "High Yield Spread",
        "M2SL": "M2 Money Supply",

        # Leading indicators
        "USSLIND": "Leading Index",

        # Volatility
        "VIXCLS": "VIX Close",
    }

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FRED_API_KEY", "")
        if not self.api_key or self.api_key == "your_fred_api_key_here":
            logger.warning("FRED_API_KEY not set - FRED calls will fail")

    def fetch_latest(
        self,
        series_id: str,
        limit: int = 1
    ) -> Optional[FREDObservation]:
        """
        Fetch the latest observation for a series.

        Args:
            series_id: FRED series ID (e.g., "FEDFUNDS")
            limit: Number of observations to fetch

        Returns:
            FREDObservation or None
        """
        import time
        start_time = time.time()

        if not self.api_key:
            return None

        try:
            import requests

            # FRED transforms (year-over-year %, etc.) are a `units` query param, not a
            # series-id suffix. Translate a trailing _PC1/_PCH/_PCA so ids like
            # "CPIAUCSL_PC1" resolve to CPIAUCSL with units=pc1 instead of 400ing.
            real_series_id, units = series_id, "lin"
            for suffix, unit in (("_PC1", "pc1"), ("_PCH", "pch"), ("_PCA", "pca")):
                if series_id.endswith(suffix):
                    real_series_id, units = series_id[: -len(suffix)], unit
                    break

            url = f"{self.BASE_URL}/series/observations"
            params = {
                "series_id": real_series_id,
                "api_key": self.api_key,
                "units": units,
                "file_type": "json",
                "sort_order": "desc",
                "limit": limit,
            }

            resp = requests.get(url, params=params, timeout=(3, 8))
            data = resp.json()

            latency_ms = (time.time() - start_time) * 1000

            if resp.status_code != 200:
                logger.warning(f"FRED API error for {series_id}: {data.get('error_message', 'Unknown')}")
                return None

            observations = data.get("observations", [])
            if not observations:
                logger.warning(f"No observations for FRED series {series_id}")
                return None

            # Filter out missing values
            valid_obs = [
                obs for obs in observations
                if obs.get("value") not in (".", "", None)
            ]

            if not valid_obs:
                return None

            obs = valid_obs[0]
            return FREDObservation(
                series_id=series_id,
                date=obs.get("date"),
                value=float(obs.get("value")),
                realtime_start=obs.get("realtime_start"),
                realtime_end=obs.get("realtime_end")
            )

        except Exception as e:
            logger.warning(f"FRED fetch failed for {series_id}: {e}")
            return None

    def fetch_series(
        self,
        series_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None
    ) -> FREDResult:
        """
        Fetch a full time series from FRED.

        Args:
            series_id: FRED series ID
            start_date: Optional start date (YYYY-MM-DD)
            end_date: Optional end date (YYYY-MM-DD)
            limit: Maximum observations

        Returns:
            FREDResult with data or error
        """
        import time
        start_time = time.time()

        if not self.api_key:
            return FREDResult(
                success=False,
                data=None,
                error="FRED_API_KEY not configured"
            )

        try:
            import requests

            url = f"{self.BASE_URL}/series/observations"
            params = {
                "series_id": series_id,
                "api_key": self.api_key,
                "file_type": "json",
                "sort_order": "asc",
            }

            if start_date:
                params["observation_start"] = start_date
            if end_date:
                params["observation_end"] = end_date
            if limit:
                params["limit"] = limit

            resp = requests.get(url, params=params, timeout=(3, 10))
            data = resp.json()

            latency_ms = (time.time() - start_time) * 1000

            if resp.status_code != 200:
                error_msg = data.get('error_message', f'HTTP {resp.status_code}')
                return FREDResult(
                    success=False,
                    data=None,
                    error=f"FRED API error: {error_msg}",
                    latency_ms=latency_ms
                )

            observations = data.get("observations", [])
            if not observations:
                return FREDResult(
                    success=False,
                    data=None,
                    error="No observations returned",
                    latency_ms=latency_ms
                )

            # Parse observations
            results = []
            for obs in observations:
                val = obs.get("value")
                if val in (".", "", None):
                    continue
                try:
                    results.append(FREDObservation(
                        series_id=series_id,
                        date=obs.get("date"),
                        value=float(val),
                        realtime_start=obs.get("realtime_start"),
                        realtime_end=obs.get("realtime_end")
                    ))
                except (ValueError, TypeError):
                    continue

            return FREDResult(
                success=True,
                data=results,
                latency_ms=latency_ms,
                records_fetched=len(results)
            )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            error_msg = f"FRED fetch failed: {e}"
            logger.error(error_msg)
            return FREDResult(
                success=False,
                data=None,
                error=error_msg,
                latency_ms=latency_ms
            )

    def fetch_multiple(
        self,
        series_ids: List[str],
        limit: int = 1
    ) -> Dict[str, Optional[FREDObservation]]:
        """
        Fetch latest values for multiple series.

        Args:
            series_ids: List of FRED series IDs
            limit: Observations per series

        Returns:
            Dict mapping series_id to observation or None
        """
        results = {}
        for series_id in series_ids:
            results[series_id] = self.fetch_latest(series_id, limit)
        return results
