"""
FRED Live Data Fetcher

Fetches live data from FRED API and saves to data/raw/live/
Does NOT use sample data - fails clearly if FRED is unavailable.
"""

import logging
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd

# Load .env file
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Output directory
LIVE_RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "live"
LIVE_RAW_DIR.mkdir(parents=True, exist_ok=True)

# Core FRED indicators for the model
FRED_INDICATORS = {
    # Growth
    "us_unemployment_rate": {"series_id": "UNRATE", "frequency": "m", "units": "lin"},
    "us_industrial_production": {"series_id": "INDPRO", "frequency": "m", "units": "pc1"},
    "us_retail_sales": {"series_id": "RSAFS", "frequency": "m", "units": "pc1"},
    # GDP Nowcast inputs
    "us_payrolls": {"series_id": "PAYEMS", "frequency": "m", "units": "pc1"},
    "us_retail_sales_ex": {"series_id": "RSXFS", "frequency": "m", "units": "pc1"},
    "us_housing_starts": {"series_id": "HOUST", "frequency": "m", "units": "lin"},
    "us_initial_claims": {"series_id": "ICSA", "frequency": "w", "units": "lin"},
    "us_real_gdp": {"series_id": "GDPC1", "frequency": "q", "units": "pc1"},

    # Inflation
    "us_cpi": {"series_id": "CPIAUCSL", "frequency": "m", "units": "pc1"},
    "us_core_cpi": {"series_id": "CPILFESL", "frequency": "m", "units": "pc1"},
    "us_ppi": {"series_id": "PPIACO", "frequency": "m", "units": "pc1"},

    # Rates
    "us_10y_yield": {"series_id": "DGS10", "frequency": "d", "units": "lin"},
    "us_2y_yield": {"series_id": "DGS2", "frequency": "d", "units": "lin"},
    "us_3m_yield": {"series_id": "DGS3MO", "frequency": "d", "units": "lin"},
    "us_fed_funds": {"series_id": "FEDFUNDS", "frequency": "m", "units": "lin"},
    # Real yields / valuation
    "us_10y_tips_yield": {"series_id": "DFII10", "frequency": "d", "units": "lin"},
    "us_10y_breakeven": {"series_id": "T10YIE", "frequency": "d", "units": "lin"},

    # Credit
    "baa_credit_spread": {"series_id": "BAA10Y", "frequency": "d", "units": "lin"},
    "high_yield_spread": {"series_id": "BAMLH0A0HYM2", "frequency": "m", "units": "lin"},
    "ig_credit_spread": {"series_id": "BAMLC0A0CM", "frequency": "d", "units": "lin"},
    "ted_spread": {"series_id": "TEDRATE", "frequency": "d", "units": "lin"},

    # Liquidity / Monetary
    "us_m2": {"series_id": "M2SL", "frequency": "m", "units": "pc1"},
    "us_fed_balance_sheet": {"series_id": "WALCL", "frequency": "w", "units": "lin"},
    "us_sofr": {"series_id": "SOFR", "frequency": "d", "units": "lin"},

    # Sentiment
    "us_consumer_sentiment": {"series_id": "UMCSENT", "frequency": "m", "units": "lin"},

    # Market/Macro
    "vix": {"series_id": "VIXCLS", "frequency": "d", "units": "lin"},
    "vix_3m": {"series_id": "VIX3M", "frequency": "d", "units": "lin"},
    "dollar_index": {"series_id": "DTWEXBGS", "frequency": "d", "units": "lin"},
    "oil_price": {"series_id": "DCOILWTICO", "frequency": "d", "units": "lin"},
    "sp500": {"series_id": "SP500", "frequency": "d", "units": "lin"},
}


class FredLiveFetcher:
    """Fetches live data from FRED and saves to raw/live/."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FRED_API_KEY")
        self.client = None
        self._init_client()

    def _init_client(self) -> bool:
        """Initialize FRED client."""
        if not self.api_key:
            logger.error("NO FRED_API_KEY provided")
            return False

        try:
            from fredapi import Fred
            self.client = Fred(api_key=self.api_key)
            logger.info("FRED client initialized")
            return True
        except ImportError:
            logger.error("fredapi package not installed. Run: pip install fredapi")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize FRED client: {e}")
            return False

    def is_available(self) -> bool:
        """Check if FRED is available."""
        return self.client is not None

    def fetch_series(self, name: str, config: Dict) -> Optional[pd.Series]:
        """Fetch a single series from FRED."""
        if not self.is_available():
            return None

        series_id = config["series_id"]

        try:
            logger.info(f"Fetching {name} ({series_id}) from FRED")

            # Get last 15 years of data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=365*15)

            series = self.client.get_series(
                series_id,
                observation_start=start_date.strftime("%Y-%m-%d"),
                observation_end=end_date.strftime("%Y-%m-%d"),
                frequency=config.get("frequency"),
                units=config.get("units"),
            )

            if series.empty:
                logger.warning(f"No data returned for {name}")
                return None

            series.name = name

            # FIXED: Convert credit spreads from percentage to basis points
            # FRED returns spreads as percentages (e.g., 2.86) but we need basis points (286)
            if name in ["high_yield_spread", "baa_credit_spread", "ig_credit_spread"]:
                if series.max() < 10:  # Detect percentage format (typical range 2-10%)
                    series = series * 100
                    logger.info(f"  -> Converted {name} from percentage to basis points")

            # Convert daily to monthly
            if config.get("frequency") == "d":
                series = series.resample("ME").last()

            # CRITICAL: Cap at today to prevent future-dated data
            today = datetime.now()
            if series.index.max() > today:
                logger.warning(f"  -> Future date detected ({series.index.max()}), capping at today ({today.date()})")
                series = series[series.index <= today]

            logger.info(f"  -> Got {len(series)} observations, latest: {series.index.max()}")
            return series

        except Exception as e:
            logger.error(f"Failed to fetch {name}: {e}")
            return None

    def fetch_all(self) -> Tuple[pd.DataFrame, Dict[str, str]]:
        """
        Fetch all configured indicators.

        Returns:
            Tuple of (combined DataFrame, status dict)
        """
        if not self.is_available():
            return pd.DataFrame(), {"error": "FRED not available - check FRED_API_KEY"}

        results = {}
        errors = {}

        for name, config in FRED_INDICATORS.items():
            series = self.fetch_series(name, config)
            if series is not None:
                results[name] = series
            else:
                errors[name] = "Failed to fetch"

        if not results:
            return pd.DataFrame(), {"error": "No data fetched", "failed": errors}

        # Combine all series
        df = pd.DataFrame(results)
        df = df.sort_index()
        df = df.dropna(how="all")

        status = {
            "success": len(results),
            "failed": len(errors),
            "latest_date": df.index.max(),
            "errors": errors if errors else None,
        }

        return df, status

    def save_to_live(self, df: pd.DataFrame) -> Path:
        """Save fetched data to live directory."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = LIVE_RAW_DIR / f"fred_live_{timestamp}.parquet"

        df.to_parquet(output_file, compression="zstd")
        logger.info(f"Saved live data to {output_file}")

        # Also save metadata
        meta = {
            "timestamp": timestamp,
            "rows": len(df),
            "columns": list(df.columns),
            "date_range": [df.index.min().isoformat(), df.index.max().isoformat()],
            "source": "FRED",
        }

        meta_file = LIVE_RAW_DIR / f"fred_live_{timestamp}_metadata.json"
        import json
        with open(meta_file, "w") as f:
            json.dump(meta, f, indent=2)

        return output_file

    def refresh_live_data(self) -> Tuple[bool, str]:
        """
        Main entry point: fetch all data and save to live directory.

        Returns:
            Tuple of (success, message)
        """
        logger.info("=" * 60)
        logger.info("REFRESHING LIVE DATA FROM FRED")
        logger.info("=" * 60)

        # Check API key
        if not self.api_key:
            return False, "FRED_API_KEY is missing. Set it in .env or environment variables."

        # Fetch data
        df, status = self.fetch_all()

        if df.empty:
            error_msg = status.get("error", "Unknown error")
            return False, f"Failed to fetch live data: {error_msg}"

        # Save
        output_path = self.save_to_live(df)

        # Summary
        success_count = status.get("success", 0)
        failed_count = status.get("failed", 0)
        latest_date = status.get("latest_date")

        msg = (
            f"SUCCESS: Fetched {success_count} series, {len(df)} rows\n"
            f"Latest data: {latest_date}\n"
            f"Failed series: {failed_count}\n"
            f"Saved to: {output_path}"
        )

        return True, msg


def refresh_fred_live_data() -> Tuple[bool, str]:
    """Convenience function to refresh FRED data."""
    fetcher = FredLiveFetcher()
    return fetcher.refresh_live_data()


if __name__ == "__main__":
    # Run standalone refresh
    logging.basicConfig(level=logging.INFO)

    success, message = refresh_fred_live_data()
    print("=" * 60)
    print("RESULT:", "SUCCESS" if success else "FAILED")
    print("=" * 60)
    print(message)
