"""
Base data client for all external data sources.

Provides common functionality for:
- API rate limiting
- Response caching
- Error handling
- Data validation
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import hashlib
import json

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Cache directory
CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class DataSourceStatus:
    """Status of a data source."""
    source_name: str
    last_successful_fetch: Optional[datetime] = None
    last_failed_fetch: Optional[datetime] = None
    last_error: Optional[str] = None
    is_available: bool = True
    series_count: int = 0
    data_quality_score: float = 0.0


@dataclass
class SeriesMetadata:
    """Metadata for a data series."""
    series_id: str
    source: str
    frequency: str
    category: str
    description: str = ""
    units: str = ""
    last_observation_date: Optional[datetime] = None
    next_release_date: Optional[datetime] = None
    revision_status: str = "final"  # preliminary, revised, final
    source_reliability: float = 0.8
    is_sample_data: bool = False


@dataclass
class DataFreshness:
    """Freshness information for a data series."""
    series_id: str
    latest_date: Optional[datetime] = None
    days_since_update: Optional[int] = None
    status: str = "unknown"  # fresh, acceptable, stale, severely_stale, missing
    freshness_score: float = 0.0
    expected_update_frequency: str = "monthly"
    staleness_threshold_days: int = 45


class BaseDataClient(ABC):
    """Abstract base class for all data clients."""

    def __init__(
        self,
        source_name: str,
        base_url: str,
        api_key: Optional[str] = None,
        rate_limit: Optional[int] = None,
        rate_limit_period: str = "minute",
        cache_duration_hours: int = 24,
    ):
        self.source_name = source_name
        self.base_url = base_url
        self.api_key = api_key
        self.rate_limit = rate_limit
        self.rate_limit_period = rate_limit_period
        self.cache_duration_hours = cache_duration_hours

        # Rate limiting
        self._last_request_time: Optional[datetime] = None
        self._request_count = 0
        self._request_window_start: Optional[datetime] = None

        # Setup session with retries
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Status tracking
        self.status = DataSourceStatus(source_name=source_name)

        logger.info(f"Initialized {source_name} client")

    def _check_rate_limit(self):
        """Check and enforce rate limiting."""
        if not self.rate_limit:
            return

        now = datetime.now()

        # Initialize window
        if self._request_window_start is None:
            self._request_window_start = now
            self._request_count = 0

        # Calculate window duration
        window_seconds = {
            "minute": 60,
            "hour": 3600,
            "day": 86400,
        }.get(self.rate_limit_period, 60)

        # Reset window if expired
        if (now - self._request_window_start).total_seconds() > window_seconds:
            self._request_window_start = now
            self._request_count = 0

        # Check if rate limit exceeded
        if self._request_count >= self.rate_limit:
            sleep_seconds = window_seconds - (now - self._request_window_start).total_seconds()
            if sleep_seconds > 0:
                logger.warning(f"Rate limit reached for {self.source_name}. Sleeping {sleep_seconds:.0f}s")
                time.sleep(sleep_seconds)
                self._request_window_start = datetime.now()
                self._request_count = 0

        self._request_count += 1

    def _get_cache_key(self, endpoint: str, params: Dict) -> str:
        """Generate cache key for a request."""
        key_data = f"{self.source_name}:{endpoint}:{json.dumps(params, sort_keys=True)}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get cache file path for a cache key."""
        return CACHE_DIR / f"{self.source_name}_{cache_key}.parquet"

    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cached data is still valid."""
        if not cache_path.exists():
            return False

        cache_age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
        return cache_age < timedelta(hours=self.cache_duration_hours)

    def _load_from_cache(self, cache_key: str) -> Optional[pd.DataFrame]:
        """Load data from cache if valid."""
        cache_path = self._get_cache_path(cache_key)

        if self._is_cache_valid(cache_path):
            try:
                logger.debug(f"Loading from cache: {cache_key}")
                return pd.read_parquet(cache_path)
            except Exception as e:
                logger.warning(f"Failed to load from cache: {e}")

        return None

    def _save_to_cache(self, cache_key: str, data: pd.DataFrame):
        """Save data to cache."""
        cache_path = self._get_cache_path(cache_key)
        try:
            data.to_parquet(cache_path, compression="zstd")
            logger.debug(f"Saved to cache: {cache_key}")
        except Exception as e:
            logger.warning(f"Failed to save to cache: {e}")

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        method: str = "GET",
        use_cache: bool = True,
    ) -> Tuple[Optional[Dict], bool]:
        """
        Make API request with caching and error handling.

        Returns:
            Tuple of (response_data, was_cached)
        """
        params = params or {}

        # Check cache
        if use_cache and method == "GET":
            cache_key = self._get_cache_key(endpoint, params)
            cached_data = self._load_from_cache(cache_key)
            if cached_data is not None:
                return cached_data.to_dict(), True

        # Rate limiting
        self._check_rate_limit()

        # Make request
        url = f"{self.base_url}/{endpoint}"

        try:
            if method == "GET":
                response = self.session.get(url, params=params, timeout=30)
            else:
                response = self.session.post(url, json=params, timeout=30)

            response.raise_for_status()

            # Parse response
            try:
                data = response.json()
            except ValueError:
                data = {"raw": response.text}

            # Save to cache
            if use_cache:
                df = pd.DataFrame(data) if isinstance(data, list) else pd.DataFrame([data])
                self._save_to_cache(cache_key, df)

            # Update status
            self.status.last_successful_fetch = datetime.now()
            self.status.is_available = True

            return data, False

        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {self.source_name}: {e}")
            self.status.last_failed_fetch = datetime.now()
            self.status.last_error = str(e)
            self.status.is_available = False
            return None, False

    @abstractmethod
    def fetch_series(
        self,
        series_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Tuple[Optional[pd.DataFrame], SeriesMetadata]:
        """
        Fetch a data series from the source.

        Returns:
            Tuple of (data DataFrame, metadata)
        """
        pass

    @abstractmethod
    def get_series_info(self, series_id: str) -> Optional[SeriesMetadata]:
        """Get metadata for a series."""
        pass

    def check_freshness(
        self,
        series_id: str,
        expected_frequency: str = "monthly",
    ) -> DataFreshness:
        """Check data freshness for a series."""
        # Get series metadata
        metadata = self.get_series_info(series_id)

        freshness = DataFreshness(
            series_id=series_id,
            expected_update_frequency=expected_frequency,
        )

        if metadata is None or metadata.last_observation_date is None:
            freshness.status = "missing"
            return freshness

        freshness.latest_date = metadata.last_observation_date

        # Calculate staleness
        now = datetime.now()
        days_since = (now - freshness.latest_date).days
        freshness.days_since_update = days_since

        # Define thresholds by frequency
        thresholds = {
            "daily": 7,
            "weekly": 14,
            "monthly": 45,
            "quarterly": 120,
            "annual": 420,
        }
        threshold = thresholds.get(expected_frequency, 45)
        freshness.staleness_threshold_days = threshold

        # Classify status
        if days_since <= threshold // 2:
            freshness.status = "fresh"
            freshness.freshness_score = 1.0
        elif days_since <= threshold:
            freshness.status = "acceptable"
            freshness.freshness_score = 0.7
        elif days_since <= threshold * 2:
            freshness.status = "stale"
            freshness.freshness_score = 0.4
        else:
            freshness.status = "severely_stale"
            freshness.freshness_score = 0.0

        return freshness

    def get_status(self) -> DataSourceStatus:
        """Get current status of this data source."""
        return self.status

    def health_check(self) -> bool:
        """Check if data source is healthy."""
        return self.status.is_available


def calculate_data_quality_score(
    completeness: float,
    freshness: float,
    stability: float,
    source_reliability: float,
    revision_risk: float,
) -> float:
    """
    Calculate overall data quality score.

    Args:
        completeness: 0-1, fraction of expected observations present
        freshness: 0-1, recency of data
        stability: 0-1, absence of large jumps/revisions
        source_reliability: 0-1, source trustworthiness
        revision_risk: 0-1, risk of significant revision (inverted)

    Returns:
        Quality score 0-1
    """
    weights = {
        "completeness": 0.30,
        "freshness": 0.25,
        "stability": 0.20,
        "source_reliability": 0.15,
        "revision_risk": 0.10,
    }

    score = (
        weights["completeness"] * completeness +
        weights["freshness"] * freshness +
        weights["stability"] * stability +
        weights["source_reliability"] * source_reliability +
        weights["revision_risk"] * (1 - revision_risk)
    )

    return round(score, 2)


def classify_quality_level(score: float) -> str:
    """Classify quality score into level."""
    if score >= 0.8:
        return "high"
    elif score >= 0.6:
        return "medium"
    else:
        return "low"
