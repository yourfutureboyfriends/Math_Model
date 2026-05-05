"""
data_pipeline.py — Orchestrates loading from multiple sources with fallback logic.

Financial context:
  A robust data pipeline needs to handle multiple scenarios:
    1. Development: No API key available, use sample data
    2. Production: Pull live data from FRED, supplement with manual data
    3. Hybrid: Some indicators from FRED, some from manual sources (e.g., PMI)
    4. Testing: Consistent sample data for reproducible results

  The pipeline implements a priority system:
    1. Check if FRED API is configured and available
    2. If yes, fetch configured series
    3. Merge with manual override data (for indicators not on FRED)
    4. If FRED unavailable or DATA_SOURCE="sample", use sample CSV
    5. Validate the final dataset has all required indicators
    6. Report data freshness for dashboard display

Usage:
  from data.connectors import load_data

  # Auto-detect source based on config
  df, metadata = load_data()

  # Force sample data
  df, metadata = load_data(source="sample")

  # Force FRED with manual supplements
  df, metadata = load_data(source="mixed")
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional, Literal, Tuple
import logging

logger = logging.getLogger(__name__)


class DataPipeline:
    """
    Orchestrates data loading from multiple sources with intelligent fallback.
    """

    def __init__(self):
        """Initialize the data pipeline with configuration."""
        # Import config (do here to avoid circular imports)
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from settings import (
            DATA_SOURCE, SAMPLE_DATA_PATH, FRED_CACHE_DIR, REFRESH_CACHE_HOURS
        )
        from data.connectors.fred_connector import FredConnector
        from data.connectors.manual_override import ManualOverrideLoader

        self.config_source = DATA_SOURCE
        self.sample_path = Path(SAMPLE_DATA_PATH)
        self.cache_dir = Path(FRED_CACHE_DIR)
        self.refresh_hours = REFRESH_CACHE_HOURS

        self.fred = FredConnector()
        self.manual = ManualOverrideLoader()

    def _load_sample_data(self) -> pd.DataFrame:
        """Load data from the sample CSV file."""
        logger.info(f"Loading sample data from {self.sample_path}")

        if not self.sample_path.exists():
            raise FileNotFoundError(
                f"Sample data not found at {self.sample_path}. "
                "Generate sample data first: python scripts/generate_sample_data.py"
            )

        df = pd.read_csv(self.sample_path, parse_dates=["date"])
        df = df.sort_values("date").reset_index(drop=True)
        df = df.set_index("date")

        logger.info(f"Loaded sample data: {len(df)} rows, {len(df.columns)} columns")
        return df

    def _load_fred_data(self) -> pd.DataFrame:
        """Load data from FRED API."""
        if not self.fred.is_available():
            logger.warning("FRED API not available. Check FRED_API_KEY environment variable.")
            return pd.DataFrame()

        from settings import FRED_SERIES

        logger.info("Fetching data from FRED API")
        df = self.fred.fetch_multiple(
            series_map=FRED_SERIES,
            force_refresh=False,  # Use cache if fresh
        )

        if df.empty:
            logger.warning("No data retrieved from FRED API")
            return pd.DataFrame()

        logger.info(f"Fetched FRED data: {len(df)} rows, {len(df.columns)} columns")
        return df

    def _merge_with_manual(self, fred_df: pd.DataFrame) -> pd.DataFrame:
        """Merge FRED data with manual overrides."""
        return self.manual.merge_with_fred_data(fred_df, manual_priority=True)

    def _validate_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, dict]:
        """
        Validate the loaded data against indicator configuration.

        Returns:
            Tuple of (validated DataFrame, metadata dict)
        """
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from src.data_loader import INDICATOR_CONFIG

        required_cols = list(INDICATOR_CONFIG.keys())
        available_cols = [c for c in required_cols if c in df.columns]
        missing_cols = [c for c in required_cols if c not in df.columns]

        if missing_cols:
            logger.warning(f"Missing indicators: {missing_cols}")

        # Calculate data freshness
        latest_date = df.index.max() if not df.empty else None
        earliest_date = df.index.min() if not df.empty else None

        metadata = {
            "rows": len(df),
            "columns": len(df.columns),
            "available_indicators": available_cols,
            "missing_indicators": missing_cols,
            "coverage_pct": len(available_cols) / len(required_cols) * 100,
            "earliest_date": earliest_date,
            "latest_date": latest_date,
            "data_age_days": (datetime.now() - latest_date).days if latest_date else None,
            "loaded_at": datetime.now(),
        }

        logger.info(
            f"Data validation: {metadata['coverage_pct']:.0f}% coverage "
            f"({len(available_cols)}/{len(required_cols)} indicators)"
        )

        return df, metadata

    def load(
        self,
        source: Optional[Literal["sample", "fred", "mixed"]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Tuple[pd.DataFrame, dict]:
        """
        Load macro data from the specified source.

        Args:
            source: Data source to use. If None, uses config DATA_SOURCE.
                   "sample": Use local CSV only
                   "fred": Use FRED API only
                   "mixed": Use FRED + manual overrides (default when configured)
            start_date: Filter data from this date (inclusive)
            end_date: Filter data to this date (inclusive)

        Returns:
            Tuple of (DataFrame, metadata dict)
        """
        effective_source = source or self.config_source
        logger.info(f"Loading data with source='{effective_source}'")

        df = pd.DataFrame()
        source_used = effective_source

        try:
            if effective_source == "sample":
                df = self._load_sample_data()

            elif effective_source == "fred":
                df = self._load_fred_data()
                if df.empty:
                    logger.warning("FRED data unavailable, falling back to sample")
                    df = self._load_sample_data()
                    source_used = "sample (fred unavailable)"

            elif effective_source == "mixed":
                # Try FRED first
                fred_df = self._load_fred_data()

                if fred_df.empty:
                    logger.warning("FRED unavailable, using sample + manual data")
                    df = self._load_sample_data()
                    source_used = "sample + manual (fred unavailable)"
                else:
                    # Merge FRED with manual data
                    df = self._merge_with_manual(fred_df)
                    source_used = "fred + manual"

            else:
                raise ValueError(f"Unknown data source: {effective_source}")

        except Exception as e:
            logger.error(f"Error loading data from {effective_source}: {e}")
            logger.info("Falling back to sample data")
            df = self._load_sample_data()
            source_used = "sample (error fallback)"

        # Filter by date range if specified
        if start_date:
            df = df[df.index >= start_date]
        if end_date:
            df = df[df.index <= end_date]

        # Validate and build metadata
        df, metadata = self._validate_data(df)
        metadata["source"] = source_used

        return df, metadata

    def get_data_freshness(self) -> dict:
        """
        Get freshness information for all data sources.

        Returns:
            Dict with freshness info for dashboard display.
        """
        info = {
            "fred_available": self.fred.is_available(),
            "manual_files": [],
            "cache_files": [],
        }

        # Check manual files
        manual_files = list(self.manual.data_dir.glob("*.csv"))
        for f in manual_files:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            info["manual_files"].append({
                "name": f.name,
                "last_modified": mtime,
                "age_days": (datetime.now() - mtime).days,
            })

        # Check cache files
        if self.cache_dir.exists():
            cache_files = list(self.cache_dir.glob("*.csv"))
            for f in cache_files:
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                info["cache_files"].append({
                    "name": f.name,
                    "last_modified": mtime,
                    "age_days": (datetime.now() - mtime).days,
                })

        return info


# Global pipeline instance for reuse
_pipeline: Optional[DataPipeline] = None


def load_data(
    source: Optional[Literal["sample", "fred", "mixed"]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Tuple[pd.DataFrame, dict]:
    """
    Convenience function to load data using the global pipeline.

    Args:
        source: Data source override. If None, uses config.
        start_date: Start date filter (YYYY-MM-DD)
        end_date: End date filter (YYYY-MM-DD)

    Returns:
        Tuple of (DataFrame, metadata dict)
    """
    global _pipeline

    if _pipeline is None:
        _pipeline = DataPipeline()

    return _pipeline.load(source=source, start_date=start_date, end_date=end_date)


def get_data_freshness() -> dict:
    """Get data freshness information for dashboard display."""
    global _pipeline

    if _pipeline is None:
        _pipeline = DataPipeline()

    return _pipeline.get_data_freshness()
