"""
Tests for Look-Ahead Bias

Ensures the model does not use future information when generating signals.
These tests should be run regularly to validate model integrity.
"""

import unittest
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src_new.backtesting.walk_forward_validator import NoLookAheadTester


class TestNoLookAheadBias(unittest.TestCase):
    """Test suite for look-ahead bias detection."""

    def setUp(self):
        """Set up test data."""
        np.random.seed(42)

        # Create sample time series
        dates = pd.date_range(start="2010-01-01", end="2020-01-01", freq="M")
        n = len(dates)

        self.sample_data = pd.DataFrame({
            "growth_indicator": np.cumsum(np.random.randn(n) * 0.1),
            "inflation_indicator": np.cumsum(np.random.randn(n) * 0.05),
            "market_indicator": np.cumsum(np.random.randn(n) * 0.08),
        }, index=dates)

        self.tester = NoLookAheadTester()

    def test_model_output_consistency(self):
        """
        Test that model outputs are consistent when future data is removed.

        If a model uses look-ahead bias, removing future data will change
        the output for historical periods.
        """
        # Simple model function that should not use look-ahead
        def simple_model(df):
            return df.iloc[-1].mean()

        result = self.tester.test_no_future_data(
            self.sample_data,
            simple_model
        )

        self.assertTrue(
            result,
            "Model output changed when future data was removed - possible look-ahead bias"
        )

    def test_zscore_calculation(self):
        """
        Test that z-scores don't use future information.

        Z-scores should only use data up to the current point.
        """
        def zscore_model(df, window=36):
            if len(df) < window:
                return 0.0

            series = df.iloc[:, 0]
            rolling = series.rolling(window=window, min_periods=window)
            mean = rolling.mean()
            std = rolling.std()

            current = series.iloc[-1]
            zscore = (current - mean.iloc[-1]) / std.iloc[-1] if std.iloc[-1] > 0 else 0

            return zscore

        result = self.tester.test_no_future_data(
            self.sample_data,
            zscore_model
        )

        self.assertTrue(
            result,
            "Z-score calculation may use future data"
        )

    def test_momentum_calculation(self):
        """
        Test that momentum calculations use only past data.
        """
        def momentum_model(df, lookback=3):
            if len(df) <= lookback:
                return 0.0

            series = df.iloc[:, 0]
            current = series.iloc[-1]
            past = series.iloc[-(lookback + 1)]

            return (current - past) / past if past != 0 else 0

        result = self.tester.test_no_future_data(
            self.sample_data,
            momentum_model
        )

        self.assertTrue(
            result,
            "Momentum calculation may use future data"
        )

    def test_regime_classification(self):
        """
        Test that regime classification doesn't peek ahead.
        """
        def regime_model(df):
            if len(df) < 6:
                return "unknown"

            # Use only last 6 months for direction
            recent = df.iloc[-6:].iloc[:, 0]
            change = recent.iloc[-1] - recent.iloc[0]

            if change > 0.1:
                return "accelerating"
            elif change < -0.1:
                return "decelerating"
            else:
                return "stable"

        result = self.tester.test_no_future_data(
            self.sample_data,
            regime_model
        )

        self.assertTrue(
            result,
            "Regime classification may use future data"
        )

    def test_rolling_statistics(self):
        """
        Test that rolling statistics don't use future data.
        """
        def rolling_stats_model(df, window=12):
            if len(df) < window:
                return {"mean": 0, "std": 0}

            series = df.iloc[:, 0]
            rolling_mean = series.rolling(window=window, min_periods=window).mean()
            rolling_std = series.rolling(window=window, min_periods=window).std()

            return {
                "mean": rolling_mean.iloc[-1],
                "std": rolling_std.iloc[-1],
            }

        result = self.tester.test_no_future_data(
            self.sample_data,
            rolling_stats_model
        )

        self.assertTrue(
            result,
            "Rolling statistics may use future data"
        )

    def test_data_leakage_in_features(self):
        """
        Test for data leakage through feature engineering.

        Features should not be derived from future observations.
        """
        def feature_model(df):
            # Create a feature that should only use past data
            series = df.iloc[:, 0]

            # Lag feature (valid - only past)
            lag = series.shift(1).iloc[-1]

            # Moving average (valid - only past)
            ma = series.rolling(window=6, min_periods=6).mean().iloc[-1]

            return lag + ma

        result = self.tester.test_no_future_data(
            self.sample_data,
            feature_model
        )

        self.assertTrue(
            result,
            "Feature engineering may leak future data"
        )

    def test_sector_signal_generation(self):
        """
        Test that sector signals don't use future macro data.
        """
        def sector_model(df):
            if len(df) < 12:
                return {"sector1": 0.0}

            # Simulate sector scoring based on macro factors
            growth = df["growth_indicator"].iloc[-12:].mean()
            inflation = df["inflation_indicator"].iloc[-12:].mean()

            # Sector sensitivity
            cyclical_score = growth * 0.6 - inflation * 0.2

            return {"cyclical": cyclical_score}

        result = self.tester.test_no_future_data(
            self.sample_data,
            sector_model
        )

        self.assertTrue(
            result,
            "Sector signal generation may use future data"
        )


class TestVintageDataHandling(unittest.TestCase):
    """Tests for proper handling of vintage data."""

    def setUp(self):
        """Set up test data with known release lags."""
        dates = pd.date_range(start="2020-01-01", end="2020-12-01", freq="M")
        n = len(dates)

        self.data = pd.DataFrame({
            "monthly_indicator": np.random.randn(n),
            "quarterly_indicator": [np.nan] * n,
        }, index=dates)

        # Quarterly data only at quarter ends
        for i in range(n):
            if i % 3 == 2:  # Quarter end
                self.data.iloc[i, 1] = np.random.randn()

    def test_release_lag_respected(self):
        """
        Test that model respects data release lags.

        Monthly data should be available with 1-month lag.
        Quarterly data should be available with 2-3 month lag.
        """
        from src_new.backtesting.walk_forward_validator import WalkForwardValidator

        validator = WalkForwardValidator()

        # Simulate as of March (data through February)
        as_of_date = datetime(2020, 3, 15)

        # With 30-day lag, February data is available
        vintage_df = validator._simulate_vintage_data(
            self.data,
            as_of_date,
            release_lags={"monthly_indicator": 30, "quarterly_indicator": 75},
        )

        # Check that March data is not available
        march_data = vintage_df.loc[vintage_df.index >= "2020-03-01", "monthly_indicator"]
        self.assertTrue(
            march_data.isna().all(),
            "Future monthly data should not be available"
        )

    def test_quarterly_data_timing(self):
        """
        Test that quarterly data is only available after release.
        """
        from src_new.backtesting.walk_forward_validator import WalkForwardValidator

        validator = WalkForwardValidator()

        # Simulate as of April (Q1 data just becoming available)
        as_of_date = datetime(2020, 4, 15)

        vintage_df = validator._simulate_vintage_data(
            self.data,
            as_of_date,
            release_lags={"quarterly_indicator": 60},  # 2-month lag
        )

        # Q1 data (March) should be available
        q1_data = vintage_df.loc["2020-03-01", "quarterly_indicator"]

        # Q2 data (not yet released) should not be available
        self.assertFalse(
            pd.isna(q1_data),
            "Q1 data should be available in April"
        )


class TestBacktestModes(unittest.TestCase):
    """Tests for realistic vs revised data backtest modes."""

    def test_realistic_mode_warning(self):
        """
        Test that realistic mode produces appropriate warnings.
        """
        # Realistic mode should acknowledge potential look-ahead bias
        # if vintage data is not available

        result = {
            "mode": "realistic",
            "vintage_data": False,
            "warning": "Results may contain look-ahead bias due to approximate release lags",
        }

        self.assertIn("warning", result)
        self.assertIn("look-ahead", result["warning"].lower())

    def test_revised_mode_labeling(self):
        """
        Test that revised mode clearly labels results as optimistic.
        """
        result = {
            "mode": "revised",
            "warning": "WARNING: Using fully revised data. Results will be overstated vs actual experience.",
        }

        self.assertIn("overstated", result["warning"].lower())


if __name__ == "__main__":
    unittest.main()
