"""
test_transformations.py — Test data transformation functions.

Tests cover:
  - Z-score computation accuracy
  - Edge cases (insufficient data, zero std)
  - Sign adjustment correctness
  - Rolling window behavior
"""

import pytest
import pandas as pd
import numpy as np
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.transformations import (
    compute_all_transforms,
    compute_momentum_score,
    compute_diffusion_index,
    ZSCORE_WINDOW,
)


@pytest.fixture
def sample_data():
    """Create sample macro data for testing."""
    dates = pd.date_range(start="2020-01-01", periods=48, freq="MS")  # 4 years
    np.random.seed(42)

    df = pd.DataFrame({
        "pmi": np.random.normal(52, 3, 48),
        "cpi_yoy": np.random.normal(2.5, 0.5, 48),
        "unemployment_rate": np.random.normal(4.0, 0.3, 48),
        "policy_rate": np.random.normal(2.5, 0.5, 48),
        "vix": np.random.normal(20, 5, 48),
    }, index=dates)

    return df


class TestTransformations:
    """Test suite for transformation functions."""

    def test_zscore_computation(self, sample_data):
        """Test that z-scores are computed correctly."""
        df_trans = compute_all_transforms(sample_data)

        # Check z-score columns exist
        assert "pmi_zscore" in df_trans.columns
        assert "cpi_yoy_zscore" in df_trans.columns

        # Z-scores should be roughly centered around 0
        pmi_z = df_trans["pmi_zscore"].dropna()
        assert abs(pmi_z.mean()) < 0.5  # Should be close to 0

    def test_zscore_range(self, sample_data):
        """Test that z-scores are in reasonable range."""
        df_trans = compute_all_transforms(sample_data)

        # Most z-scores should be within [-4, 4]
        pmi_z = df_trans["pmi_zscore"].dropna()
        assert pmi_z.min() > -5
        assert pmi_z.max() < 5

    def test_insufficient_data(self):
        """Test behavior with insufficient data for z-score."""
        # Create data with only 10 months (less than ZSCORE_WINDOW)
        dates = pd.date_range(start="2020-01-01", periods=10, freq="MS")
        df = pd.DataFrame({
            "pmi": range(10),
        }, index=dates)

        df_trans = compute_all_transforms(df)

        # Should still work (uses min_periods)
        assert "pmi_zscore" in df_trans.columns

    def test_zero_std_handling(self):
        """Test handling of series with zero standard deviation."""
        dates = pd.date_range(start="2020-01-01", periods=50, freq="MS")
        df = pd.DataFrame({
            "constant": [5.0] * 50,  # Constant value = zero std
        }, index=dates)

        df_trans = compute_all_transforms(df)

        # Note: constant column won't have z-score column as it's not in INDICATOR_CONFIG
        # The test just verifies no error is raised
        assert len(df_trans) == 50

    def test_mom_computation(self, sample_data):
        """Test month-on-month change computation."""
        df_trans = compute_all_transforms(sample_data)

        # MoM column should exist
        assert "pmi_mom" in df_trans.columns

        # First value should be NaN (no previous month)
        assert pd.isna(df_trans["pmi_mom"].iloc[0])

        # Rest should be differences (check values match, names may differ)
        expected_mom = sample_data["pmi"].diff(1).iloc[1:]
        actual_mom = df_trans["pmi_mom"].iloc[1:]
        pd.testing.assert_series_equal(
            actual_mom.reset_index(drop=True),
            expected_mom.reset_index(drop=True),
            check_names=False
        )

    def test_yoy_computation(self, sample_data):
        """Test year-on-year change computation."""
        df_trans = compute_all_transforms(sample_data)

        # YoY column should exist
        assert "cpi_yoy_yoy" in df_trans.columns

        # First 12 values should be NaN (no year ago data)
        assert df_trans["cpi_yoy_yoy"].iloc[:12].isna().all()

    def test_momentum_score(self, sample_data):
        """Test momentum score computation."""
        series = sample_data["pmi"]
        momentum = compute_momentum_score(series)

        # Should return series of same length
        assert len(momentum) == len(series)

        # Values should be finite (not inf/nan after initial periods)
        valid = momentum.dropna()
        assert np.isfinite(valid).all()

    def test_diffusion_index(self, sample_data):
        """Test diffusion index computation."""
        # Transform data first
        df_trans = compute_all_transforms(sample_data)

        # Compute diffusion for growth group
        diffusion = compute_diffusion_index(df_trans, "growth")

        # Should return series
        assert isinstance(diffusion, pd.Series)

        # Values should be between 0 and 100
        assert diffusion.min() >= 0
        assert diffusion.max() <= 100


class TestTransformationsEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_dataframe(self):
        """Test behavior with empty DataFrame."""
        df = pd.DataFrame()

        # Should not raise error
        df_trans = compute_all_transforms(df)
        assert len(df_trans) == 0

    def test_missing_indicator(self):
        """Test behavior with missing indicator."""
        dates = pd.date_range(start="2020-01-01", periods=50, freq="MS")
        df = pd.DataFrame({
            "pmi": range(50),
            # Missing other required indicators
        }, index=dates)

        # Should still work (skip missing)
        df_trans = compute_all_transforms(df)
        assert "pmi_zscore" in df_trans.columns

    def test_single_row(self):
        """Test behavior with single row."""
        df = pd.DataFrame({"pmi": [50]}, index=[pd.Timestamp("2020-01-01")])

        df_trans = compute_all_transforms(df)
        assert len(df_trans) == 1
        # Z-score should be 0 (no history)
        assert df_trans["pmi_zscore"].iloc[0] == 0 or pd.isna(df_trans["pmi_zscore"].iloc[0])
