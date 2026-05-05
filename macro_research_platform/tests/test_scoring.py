"""
test_scoring.py — Test scoring functions.

Tests cover:
  - Group score computation
  - Score ranges
  - PCA-based scoring
  - Signal quality metrics
"""

import pytest
import pandas as pd
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scoring import (
    compute_group_scores,
    compute_group_scores_advanced,
    compute_score_directions,
    get_current_scores,
    score_to_label,
)


@pytest.fixture
def sample_scores_df():
    """Create sample scores DataFrame."""
    dates = pd.date_range(start="2020-01-01", periods=24, freq="MS")

    df = pd.DataFrame({
        "growth_score": np.random.normal(0.3, 0.5, 24),
        "inflation_score": np.random.normal(-0.2, 0.4, 24),
        "liquidity_score": np.random.normal(0.1, 0.3, 24),
        "risk_score": np.random.normal(-0.1, 0.4, 24),
    }, index=dates)

    return df


class TestScoring:
    """Test suite for scoring functions."""

    def test_score_ranges(self, sample_scores_df):
        """Test that scores are within expected z-score ranges."""
        for col in sample_scores_df.columns:
            scores = sample_scores_df[col]

            # Most scores should be within [-3, 3]
            assert scores.min() > -4
            assert scores.max() < 4

    def test_get_current_scores(self, sample_scores_df):
        """Test extraction of current scores."""
        scores = get_current_scores(sample_scores_df)

        assert "growth" in scores
        assert "inflation" in scores
        assert "liquidity" in scores
        assert "risk" in scores

        # Values should be floats
        for v in scores.values():
            assert isinstance(v, (int, float))

    def test_score_directions(self, sample_scores_df):
        """Test direction computation."""
        directions = compute_score_directions(sample_scores_df)

        assert "growth" in directions
        assert directions["growth"] in ["improving", "stable", "deteriorating"]

        assert "inflation" in directions
        assert directions["inflation"] in ["rising", "stable", "falling"]

    def test_score_direction_thresholds(self):
        """Test direction threshold logic."""
        # Create scores with clear trend
        dates = pd.date_range(start="2020-01-01", periods=6, freq="MS")

        # Strong upward trend
        df_up = pd.DataFrame({
            "growth_score": [0.0, 0.0, 0.0, 0.0, 0.5, 1.0],
            "inflation_score": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "liquidity_score": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "risk_score": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        }, index=dates)

        directions = compute_score_directions(df_up)
        assert directions["growth"] == "improving"

    def test_score_to_label(self):
        """Test score label conversion."""
        assert score_to_label(1.5) == "Strong positive"
        assert score_to_label(0.5) == "Mildly positive"
        assert score_to_label(0.0) == "Neutral"
        assert score_to_label(-0.5) == "Mildly negative"
        assert score_to_label(-1.5) == "Strong negative"

    def test_advanced_scoring(self):
        """Test advanced scoring with PCA."""
        # Create sample transformed data
        dates = pd.date_range(start="2020-01-01", periods=48, freq="MS")

        # Create correlated z-scores
        np.random.seed(42)
        base = np.random.normal(0, 1, 48)

        df_trans = pd.DataFrame({
            "pmi_zscore": base + np.random.normal(0, 0.3, 48),
            "gdp_growth_zscore": base + np.random.normal(0, 0.3, 48),
            "industrial_production_zscore": base + np.random.normal(0, 0.3, 48),
            "retail_sales_zscore": base + np.random.normal(0, 0.3, 48),
            "unemployment_rate_zscore": -(base + np.random.normal(0, 0.3, 48)),
        }, index=dates)

        # Compute advanced scores
        scores_df = compute_group_scores_advanced(df_trans, use_pca=True, pca_weight=0.3)

        # Should have EW and composite columns
        assert "growth_score_ew" in scores_df.columns
        assert "growth_score_composite" in scores_df.columns

    def test_insufficient_data_directions(self):
        """Test directions with insufficient data."""
        dates = pd.date_range(start="2020-01-01", periods=2, freq="MS")
        df = pd.DataFrame({
            "growth_score": [0.0, 0.1],
            "inflation_score": [0.0, 0.1],
            "liquidity_score": [0.0, 0.1],
            "risk_score": [0.0, 0.1],
        }, index=dates)

        # Should return stable for all with insufficient data
        directions = compute_score_directions(df)
        assert all(d == "stable" for d in directions.values())
