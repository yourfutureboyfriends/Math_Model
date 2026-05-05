"""
manual_override.py — Load custom CSV files for indicators not on FRED.

Financial context:
  Not all useful macro indicators are available on FRED. Examples include:
    - PMI data from S&P Global (formerly Markit/IHS) — requires subscription
    - UK/European data from ONS, Eurostat — often in custom formats
    - Consensus estimates from Bloomberg/Reuters — proprietary
    - Alternative data (satellite imagery, credit card spending)

  This module provides a clean way to supplement FRED data with any CSV
  following the same format as the sample data.

Expected CSV format:
  - Must have a 'date' column (YYYY-MM-DD format)
  - Must have columns matching the indicator names in data_loader.INDICATOR_CONFIG
  - Monthly frequency (month-end dates preferred)
  - Missing values should be blank or NaN

Example CSV structure:
  date,pmi,wage_growth_yoy,oil_price
  2020-01-31,52.3,3.1,58.50
  2020-02-29,50.1,3.2,55.20
  ...
"""

import pandas as pd
from pathlib import Path
from typing import Optional, Union
import logging

logger = logging.getLogger(__name__)


class ManualOverrideLoader:
    """
    Loader for custom CSV data that supplements or replaces FRED data.

    Typical usage:
      1. Download PMI data from your data provider
      2. Save as data/manual/pmi_data.csv
      3. Use ManualOverrideLoader to merge with FRED data
    """

    def __init__(self, data_dir: Optional[Path] = None):
        """
        Initialize the manual override loader.

        Args:
            data_dir: Directory containing manual CSV files.
                     Defaults to PROJECT_ROOT/data/manual/
        """
        if data_dir is None:
            # Import config to get project root
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent.parent))
            from settings import PROJECT_ROOT
            self.data_dir = PROJECT_ROOT / "data" / "manual"
        else:
            self.data_dir = Path(data_dir)

        self.data_dir.mkdir(parents=True, exist_ok=True)

    def load_csv(self, filename: Union[str, Path]) -> pd.DataFrame:
        """
        Load a single manual CSV file.

        Args:
            filename: Path to CSV file (absolute) or filename relative to data_dir

        Returns:
            DataFrame indexed by date

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is malformed
        """
        filepath = Path(filename)
        if not filepath.is_absolute():
            filepath = self.data_dir / filename

        if not filepath.exists():
            raise FileNotFoundError(f"Manual data file not found: {filepath}")

        logger.info(f"Loading manual data from {filepath}")

        try:
            df = pd.read_csv(filepath, parse_dates=["date"])
            df = df.sort_values("date").reset_index(drop=True)
            df = df.set_index("date")

            # Validate we have required columns
            if len(df.columns) == 0:
                raise ValueError("CSV file has no data columns")

            # Check for empty data
            if df.empty:
                raise ValueError("CSV file is empty")

            logger.info(f"Loaded {len(df)} rows with columns: {list(df.columns)}")
            return df

        except pd.errors.EmptyDataError:
            raise ValueError("CSV file is empty")
        except pd.errors.ParserError as e:
            raise ValueError(f"Failed to parse CSV: {e}")

    def load_all_manual_data(self) -> pd.DataFrame:
        """
        Load and merge all CSV files in the manual data directory.

        Files are merged on date index. Later files overwrite earlier ones
        if there are column conflicts.

        Returns:
            Combined DataFrame with all manual data, or empty DataFrame if no files.
        """
        csv_files = sorted(self.data_dir.glob("*.csv"))

        if not csv_files:
            logger.debug(f"No manual CSV files found in {self.data_dir}")
            return pd.DataFrame()

        logger.info(f"Found {len(csv_files)} manual data files")

        combined = None
        for filepath in csv_files:
            try:
                df = self.load_csv(filepath)
                if combined is None:
                    combined = df
                else:
                    # Merge on index, keeping all columns
                    # New columns are added; overlapping columns use new data
                    combined = combined.join(df, how="outer", rsuffix="_new")

                    # For overlapping columns, prefer new data where available
                    for col in df.columns:
                        if f"{col}_new" in combined.columns:
                            # Use new data where not null, else keep old
                            combined[col] = combined[col].fillna(combined[f"{col}_new"])
                            combined = combined.drop(columns=[f"{col}_new"])

            except Exception as e:
                logger.warning(f"Failed to load {filepath}: {e}")
                continue

        if combined is None:
            return pd.DataFrame()

        # Sort by date and forward fill missing values
        combined = combined.sort_index()

        logger.info(f"Combined manual data: {len(combined)} rows, {len(combined.columns)} columns")
        return combined

    def merge_with_fred_data(
        self,
        fred_df: pd.DataFrame,
        manual_priority: bool = True,
    ) -> pd.DataFrame:
        """
        Merge FRED data with manual override data.

        Args:
            fred_df: DataFrame from FRED connector
            manual_priority: If True, manual data takes precedence over FRED
                           when columns overlap. If False, FRED takes precedence.

        Returns:
            Merged DataFrame
        """
        manual_df = self.load_all_manual_data()

        if manual_df.empty:
            logger.info("No manual data to merge")
            return fred_df

        if fred_df.empty:
            logger.info("No FRED data, using manual data only")
            return manual_df

        # Join the two datasets
        if manual_priority:
            # Manual data is source of truth where it exists
            merged = fred_df.join(manual_df, how="outer", rsuffix="_fred")

            # For overlapping columns, prefer manual
            for col in manual_df.columns:
                if col in fred_df.columns and f"{col}_fred" in merged.columns:
                    # Use manual data where available, fall back to FRED
                    merged[col] = merged[col].fillna(merged[f"{col}_fred"])
                    merged = merged.drop(columns=[f"{col}_fred"])
        else:
            # FRED data is source of truth
            merged = manual_df.join(fred_df, how="outer", rsuffix="_manual")

            for col in fred_df.columns:
                if col in manual_df.columns and f"{col}_manual" in merged.columns:
                    merged[col] = merged[f"{col}_manual"].fillna(merged[col])
                    merged = merged.drop(columns=[f"{col}_manual"])

        # Sort and clean
        merged = merged.sort_index()

        logger.info(f"Merged data: {len(merged)} rows, {len(merged.columns)} columns")
        return merged


def load_manual_data(filepath: Optional[Union[str, Path]] = None) -> pd.DataFrame:
    """
    Convenience function to load manual data.

    Args:
        filepath: Path to specific CSV file. If None, loads all files
                 from the default manual data directory.

    Returns:
        DataFrame with manual data, or empty DataFrame if no data available.
    """
    loader = ManualOverrideLoader()

    if filepath:
        return loader.load_csv(filepath)
    else:
        return loader.load_all_manual_data()
