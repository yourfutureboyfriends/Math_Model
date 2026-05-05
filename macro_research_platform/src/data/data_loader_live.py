"""
Live Data Loader - Strict Mode Implementation

Enforces clear separation between live and sample data modes.
NEVER silently falls back to sample data in live mode.
"""

import logging
from pathlib import Path
from datetime import datetime
from typing import Tuple, Optional, Dict, Any
import pandas as pd
import os

logger = logging.getLogger(__name__)

# Paths - IMPORTANT: Must match fred_live_fetcher.py paths exactly
# The fetcher saves to src/data/raw/live/ not data/raw/live/
PROJECT_ROOT = Path(__file__).parent.parent.parent
RAW_LIVE_DIR = PROJECT_ROOT / "src" / "data" / "raw" / "live"
PROCESSED_LIVE_DIR = PROJECT_ROOT / "data" / "processed" / "live"
METADATA_DIR = PROJECT_ROOT / "data" / "metadata"
SAMPLE_PATH = PROJECT_ROOT / "data" / "raw" / "sample_macro_data.csv"

for d in [RAW_LIVE_DIR, PROCESSED_LIVE_DIR, METADATA_DIR]:
    d.mkdir(parents=True, exist_ok=True)


class DataModeError(Exception):
    """Raised when data cannot be loaded in the requested mode."""
    pass


class LiveDataLoader:
    """
    Strict data loader with clear mode enforcement.

    MODE RULES:
    - "live": ONLY uses data/processed/live/ - NEVER falls back to sample
    - "sample": ONLY uses sample data - clearly labeled
    """

    def __init__(self, mode: str = "live"):
        self.mode = mode.lower()
        self._validate_mode()

    def _validate_mode(self):
        """Validate mode is supported."""
        if self.mode not in ["live", "sample"]:
            raise ValueError(f"Invalid mode: {self.mode}. Must be 'live' or 'sample'")

    def load(self) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Load data according to mode.

        Returns:
            Tuple of (DataFrame, metadata)

        Raises:
            DataModeError: If live data is requested but not available
        """
        if self.mode == "live":
            return self._load_live_data()
        elif self.mode == "sample":
            return self._load_sample_data()

    def _load_live_data(self) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """Load ONLY from processed live data directory."""
        logger.info("LOADING LIVE DATA MODE")
        logger.info(f"Looking for data in: {PROCESSED_LIVE_DIR}")

        # Check for processed live data
        processed_file = PROCESSED_LIVE_DIR / "macro_data.parquet"

        if processed_file.exists():
            logger.info(f"Found processed live data: {processed_file}")
            df = pd.read_parquet(processed_file)
            metadata = self._get_live_metadata(df)
            logger.info(f"Loaded {len(df)} rows from live processed data")
            return df, metadata

        # Check for raw live data that needs processing
        # Only use the MOST RECENT file, not all files
        raw_files = sorted(
            RAW_LIVE_DIR.glob("*.parquet"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        if raw_files:
            latest_file = raw_files[0]
            logger.info(f"Processing latest raw file: {latest_file.name}")
            df = self._process_raw_live_files([latest_file])
            if not df.empty:
                # Save processed
                df.to_parquet(processed_file, compression="zstd")
                metadata = self._get_live_metadata(df)
                logger.info(f"Processed and saved {len(df)} rows")
                return df, metadata

        # NO FALLBACK - raise error
        raise DataModeError(
            f"LIVE DATA NOT FOUND\n"
            f"Checked: {processed_file}\n"
            f"Checked: {RAW_LIVE_DIR}\n\n"
            f"To get live data, run:\n"
            f"  python pipeline.py --mode refresh-live-data\n\n"
            f"Or to use sample data:\n"
            f"  python pipeline.py --mode run-sample"
        )

    def _load_sample_data(self) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """Load from sample data."""
        logger.info("LOADING SAMPLE DATA MODE")

        if not SAMPLE_PATH.exists():
            raise DataModeError(
                f"Sample data not found at {SAMPLE_PATH}\n"
                f"Generate it with: python scripts/generate_sample_data.py"
            )

        df = pd.read_csv(SAMPLE_PATH, parse_dates=["date"])
        df = df.sort_values("date").reset_index(drop=True)
        df = df.set_index("date")

        metadata = {
            "source": "sample",
            "source_type": "sample",
            "mode": "sample",
            "latest_date": df.index.max(),
            "rows": len(df),
            "loaded_at": datetime.now(),
            "is_live": False,
            "is_sample": True,
            "warning": "SAMPLE DATA - NOT FOR LIVE DECISIONS"
        }

        logger.info(f"Loaded {len(df)} rows from SAMPLE data (up to {df.index.max()})")
        return df, metadata

    def _process_raw_live_files(self, files) -> pd.DataFrame:
        """Process raw live files into combined DataFrame."""
        dataframes = []

        for f in files:
            try:
                if f.suffix == ".parquet":
                    df = pd.read_parquet(f)
                else:
                    df = pd.read_csv(f, parse_dates=True)

                # Ensure date index
                if "date" in df.columns:
                    df = df.set_index("date")
                elif "Date" in df.columns:
                    df = df.set_index("Date")

                dataframes.append(df)
                logger.info(f"Loaded {f.name}: {len(df)} rows")
            except Exception as e:
                logger.error(f"Failed to load {f}: {e}")

        if not dataframes:
            return pd.DataFrame()

        # Combine
        combined = pd.concat(dataframes, axis=1)
        combined = combined.sort_index()
        combined = combined.dropna(how="all")

        # CRITICAL: Check data completeness BEFORE resampling
        # If we have scattered data points in the current month but most series
        # end in the previous month, we should cap at previous month-end
        today = datetime.now()
        current_month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Check if any dates are in current month (same year/month as today)
        max_date = combined.index.max()
        if max_date.year == today.year and max_date.month == today.month:
            # Count data completeness BEFORE resample
            current_dates = combined[combined.index >= current_month_start]
            prev_dates = combined[combined.index < current_month_start]

            # How many series have actual (non-forward-filled) data in current month?
            # Compare to typical recent month
            if len(prev_dates) > 0:
                # Use last week of previous month as baseline for "complete"
                # Get dates from last 7 days of previous month
                last_week_start = (current_month_start - pd.Timedelta(days=7))
                last_prev_week = prev_dates[prev_dates.index >= last_week_start]
                avg_daily_series_prev = last_prev_week.notna().sum(axis=1).mean() if len(last_prev_week) > 0 else 12

                # Current month actual data (not resampled yet)
                current_actual = current_dates.notna().sum(axis=1).mean() if len(current_dates) > 0 else 0

                completeness_ratio = current_actual / max(avg_daily_series_prev, 1)

                if completeness_ratio < 0.3:
                    logger.warning(f"Incomplete current month data ({current_actual:.0f} series vs {avg_daily_series_prev:.0f} typical), "
                                  f"capping at previous month-end")
                    combined = combined[combined.index < current_month_start]

        # Clean up FRED data: forward fill and resample to month-end
        # FRED daily data resampled to monthly creates NaNs at month-start dates
        combined = combined.ffill()
        # Resample to month-end to ensure consistent monthly frequency
        combined = combined.resample('ME').last()
        combined = combined.dropna(how="all")

        # Final safety: cap any remaining future dates at today
        if combined.index.max() > today:
            logger.warning(f"Capping future date: {combined.index.max()}")
            combined = combined[combined.index <= today]

        return combined

    def _get_live_metadata(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Generate metadata for live data."""
        latest_date = df.index.max() if not df.empty else None
        days_since = (datetime.now() - latest_date).days if latest_date else None

        # Determine staleness
        if days_since is None:
            status = "unknown"
        elif days_since <= 45:
            status = "current"
        elif days_since <= 90:
            status = "acceptable"
        else:
            status = "stale"

        return {
            "source": "live",
            "source_type": "cached_live" if status == "current" else "cached_live_stale",
            "mode": "live",
            "latest_date": latest_date,
            "days_since_update": days_since,
            "data_status": status,
            "rows": len(df),
            "columns": len(df.columns),
            "loaded_at": datetime.now(),
            "is_live": True,
            "is_sample": False,
            "can_generate_current_view": status in ["current", "acceptable"],
        }


def load_model_data(mode: str = "live") -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Load data with strict mode enforcement.

    Args:
        mode: "live" or "sample"

    Returns:
        Tuple of (DataFrame, metadata)

    Raises:
        DataModeError: If data cannot be loaded in requested mode
    """
    loader = LiveDataLoader(mode=mode)
    return loader.load()


def get_data_status() -> Dict[str, Any]:
    """Get current data status without loading."""
    status = {
        "live_processed_exists": (PROCESSED_LIVE_DIR / "macro_data.parquet").exists(),
        "live_raw_files": len(list(RAW_LIVE_DIR.glob("*"))),
        "sample_exists": SAMPLE_PATH.exists(),
        "processed_path": str(PROCESSED_LIVE_DIR / "macro_data.parquet"),
        "sample_path": str(SAMPLE_PATH),
    }

    # Check if live data exists and get its date
    if status["live_processed_exists"]:
        try:
            df = pd.read_parquet(PROCESSED_LIVE_DIR / "macro_data.parquet")
            status["live_latest_date"] = df.index.max()
            status["live_rows"] = len(df)
        except Exception as e:
            status["live_error"] = str(e)

    return status


if __name__ == "__main__":
    # Debug: show data status
    print("=== DATA STATUS ===")
    status = get_data_status()
    for k, v in status.items():
        print(f"{k}: {v}")

    print("\n=== TRYING LIVE MODE ===")
    try:
        df, meta = load_model_data("live")
        print(f"SUCCESS: Loaded {len(df)} rows")
        print(f"Latest date: {meta.get('latest_date')}")
        print(f"Status: {meta.get('data_status')}")
    except DataModeError as e:
        print(f"FAILED: {e}")

    print("\n=== TRYING SAMPLE MODE ===")
    try:
        df, meta = load_model_data("sample")
        print(f"SUCCESS: Loaded {len(df)} rows")
        print(f"Latest date: {meta.get('latest_date')}")
        print(f"Is sample: {meta.get('is_sample')}")
    except DataModeError as e:
        print(f"FAILED: {e}")
