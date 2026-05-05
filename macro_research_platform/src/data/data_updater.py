"""
Data Updater Module

Manages data refresh from all sources with fallback handling.
Provides command-line interface for data operations.
"""

import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import pandas as pd

from .fred_client import FredClient
from .base_client import DataSourceStatus
from .data_freshness import (
    check_series_freshness,
    generate_freshness_report,
    ModelFreshnessReport,
    save_freshness_report,
    SeriesFreshness,
)

logger = logging.getLogger(__name__)

# Paths
DATA_DIR = Path(__file__).parent.parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUTS_DIR = Path(__file__).parent.parent.parent / "outputs"

for d in [RAW_DIR, PROCESSED_DIR, OUTPUTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


class DataUpdater:
    """
    Manages data updates from all sources.

    Handles:
    - Fetching new data from APIs
    - Validating data quality
    - Saving to appropriate locations
    - Fallback to cached data
    - Generating freshness reports
    """

    def __init__(self):
        self.clients = {}
        self._init_clients()
        self.update_log = []

    def _init_clients(self):
        """Initialize all data clients."""
        try:
            self.clients["fred"] = FredClient()
            logger.info("Initialized FRED client")
        except Exception as e:
            logger.warning(f"Could not initialize FRED client: {e}")
            self.clients["fred"] = None

    def update_series(
        self,
        series_id: str,
        source: str,
        source_series_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Tuple[Optional[pd.DataFrame], Dict[str, Any]]:
        """
        Update a single series from its source.

        Returns:
            Tuple of (DataFrame, metadata dict)
        """
        client = self.clients.get(source)

        if client is None:
            logger.warning(f"No client available for source: {source}")
            return self._load_cached_or_sample(series_id, source)

        try:
            # Fetch from source
            lookup_id = source_series_id or series_id
            df, metadata = client.fetch_series(
                lookup_id,
                start_date=start_date,
                end_date=end_date,
            )

            if df is not None and not df.empty:
                # Save raw data
                raw_path = RAW_DIR / f"{series_id}.parquet"
                df.to_parquet(raw_path, compression="zstd")

                # Log success
                self.update_log.append({
                    "series_id": series_id,
                    "source": source,
                    "status": "success",
                    "observations": len(df),
                    "latest_date": metadata.last_observation_date,
                    "timestamp": datetime.now(),
                })

                meta = {
                    "source": source,
                    "latest_date": metadata.last_observation_date,
                    "is_sample": metadata.is_sample_data,
                    "observations": len(df),
                }

                return df, meta

        except Exception as e:
            logger.error(f"Failed to update {series_id} from {source}: {e}")

        # Fallback to cached/sample
        return self._load_cached_or_sample(series_id, source)

    def _load_cached_or_sample(
        self,
        series_id: str,
        source: str,
    ) -> Tuple[Optional[pd.DataFrame], Dict[str, Any]]:
        """Load from cache or generate sample data."""
        # Try cached
        cached_path = RAW_DIR / f"{series_id}.parquet"
        if cached_path.exists():
            try:
                df = pd.read_parquet(cached_path)
                latest_date = df.index.max()

                self.update_log.append({
                    "series_id": series_id,
                    "source": source,
                    "status": "cached",
                    "observations": len(df),
                    "latest_date": latest_date,
                    "timestamp": datetime.now(),
                })

                return df, {
                    "source": source,
                    "latest_date": latest_date,
                    "is_sample": False,
                    "is_cached": True,
                }
            except Exception as e:
                logger.warning(f"Failed to load cached data for {series_id}: {e}")

        # Generate sample data
        from .fred_client import FredClient
        client = FredClient()
        df, metadata = client._get_sample_data(series_id)

        if df is not None:
            self.update_log.append({
                "series_id": series_id,
                "source": "sample",
                "status": "sample",
                "observations": len(df),
                "latest_date": metadata.last_observation_date,
                "timestamp": datetime.now(),
            })

        return df, {
            "source": "sample",
            "latest_date": metadata.last_observation_date if metadata else None,
            "is_sample": True,
        }

    def refresh_all_live_data(
        self,
        indicator_configs: List[Dict],
    ) -> ModelFreshnessReport:
        """
        Refresh all configured series from live sources.

        Args:
            indicator_configs: List of indicator config dicts

        Returns:
            Freshness report
        """
        logger.info(f"Starting refresh of {len(indicator_configs)} series")

        series_data = {}

        for config in indicator_configs:
            series_id = config["series_id"]
            source = config.get("source", "sample")
            source_series_id = config.get("source_series_id")
            frequency = config.get("frequency", "monthly")

            # Update from source
            df, meta = self.update_series(
                series_id=series_id,
                source=source,
                source_series_id=source_series_id,
            )

            # Track for freshness report
            series_data[series_id] = (
                meta.get("latest_date"),
                frequency,
                meta.get("is_sample", False),
                meta.get("source", "sample"),
            )

        # Generate freshness report
        report = generate_freshness_report(series_data)

        # Save report
        save_freshness_report(report, OUTPUTS_DIR)

        # Save update log
        log_df = pd.DataFrame(self.update_log)
        if not log_df.empty:
            log_df.to_csv(OUTPUTS_DIR / "data_update_log.csv", index=False)

        return report

    def check_freshness(
        self,
        indicator_configs: List[Dict],
    ) -> ModelFreshnessReport:
        """
        Check freshness without updating.

        Args:
            indicator_configs: List of indicator config dicts

        Returns:
            Freshness report
        """
        series_data = {}

        for config in indicator_configs:
            series_id = config["series_id"]
            frequency = config.get("frequency", "monthly")

            # Check cached/sample
            df, meta = self._load_cached_or_sample(
                series_id,
                config.get("source", "sample"),
            )

            series_data[series_id] = (
                meta.get("latest_date"),
                frequency,
                meta.get("is_sample", False),
                meta.get("source", "sample"),
            )

        return generate_freshness_report(series_data)

    def get_source_status(self) -> Dict[str, DataSourceStatus]:
        """Get status of all data sources."""
        status = {}
        for name, client in self.clients.items():
            if client:
                status[name] = client.get_status()
            else:
                status[name] = DataSourceStatus(
                    source_name=name,
                    is_available=False,
                    last_error="Client not initialized",
                )
        return status


def create_indicator_configs() -> List[Dict]:
    """Create list of indicator configurations from YAML config."""
    try:
        from ...config import get_indicator_mapping
        mapping = get_indicator_mapping()
        indicators = mapping.get("indicators", {})

        configs = []
        for name, cfg in indicators.items():
            configs.append({
                "series_id": name,
                "source": cfg.get("source", "sample"),
                "source_series_id": cfg.get("source_series_id"),
                "frequency": cfg.get("frequency", "monthly"),
            })

        return configs
    except Exception as e:
        logger.error(f"Failed to load indicator configs: {e}")
        return []


def main():
    """Command-line interface for data operations."""
    parser = argparse.ArgumentParser(
        description="Data updater for macro regime model",
    )

    parser.add_argument(
        "--mode",
        choices=["refresh", "check", "status"],
        default="check",
        help="Operation mode",
    )

    parser.add_argument(
        "--series",
        help="Update specific series only",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUTS_DIR,
        help="Output directory for reports",
    )

    args = parser.parse_args()

    updater = DataUpdater()

    if args.mode == "refresh":
        configs = create_indicator_configs()

        if args.series:
            configs = [c for c in configs if c["series_id"] == args.series]

        report = updater.refresh_all_live_data(configs)

        print(f"\nRefresh complete!")
        print(f"Overall status: {report.overall_status}")
        print(f"Latest model date: {report.latest_model_date}")
        print(f"Fresh: {report.fresh_count}, Stale: {report.stale_count}, Sample: {report.sample_count}")

        if report.warnings:
            print("\nWarnings:")
            for w in report.warnings:
                print(f"  - {w}")

    elif args.mode == "check":
        configs = create_indicator_configs()
        report = updater.check_freshness(configs)

        print(f"\nData Freshness Check")
        print(f"====================")
        print(f"Overall status: {report.overall_status}")
        print(f"Latest model date: {report.latest_model_date}")
        print(f"Can generate current allocation: {report.can_generate_current_allocation}")

        if report.warnings:
            print("\nWarnings:")
            for w in report.warnings:
                print(f"  ⚠️  {w}")

        # Save report
        md_path, csv_path = save_freshness_report(report, args.output)
        print(f"\nReports saved:")
        print(f"  - {md_path}")
        print(f"  - {csv_path}")

    elif args.mode == "status":
        status = updater.get_source_status()

        print("\nData Source Status")
        print("==================")
        for name, s in status.items():
            status_icon = "✅" if s.is_available else "❌"
            print(f"\n{status_icon} {name}")
            print(f"   Available: {s.is_available}")
            if s.last_successful_fetch:
                print(f"   Last success: {s.last_successful_fetch}")
            if s.last_error:
                print(f"   Last error: {s.last_error}")


if __name__ == "__main__":
    main()
