"""
test_sector_model.py — Test sector model functions.

Tests cover:
  - Sector score computation
  - OW/UW threshold logic
  - Portfolio construction
  - Signal generation
"""

import pytest
import pandas as pd
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.sector_model import (
    compute_sector_scores,
    get_sector_signals,
    get_sector_table,
    SECTOR_CONFIG,
    SIGNAL_THRESHOLDS,
)
from src.portfolio_constructor import (
    PortfolioConstructor,
    construct_model_portfolio,
)


class TestSectorScoring:
    """Test sector score computation."""

    def test_sector_scores_computed(self):
        """Test that all sectors get scores."""
        scores = compute_sector_scores(
            regime="Goldilocks",
            growth_score=0.5,
            liquidity_score=0.3,
            risk_score=-0.2,
        )

        # All sectors should have scores
        assert len(scores) == len(SECTOR_CONFIG)
        for sector in SECTOR_CONFIG:
            assert sector in scores
            assert isinstance(scores[sector], (int, float))

    def test_score_ranges(self):
        """Test that sector scores are in reasonable ranges."""
        scores = compute_sector_scores(
            regime="Goldilocks",
            growth_score=0.5,
            liquidity_score=0.3,
            risk_score=-0.2,
        )

        # Scores should typically be in [-2, 2] range
        for score in scores.values():
            assert -3 <= score <= 3

    def test_regime_dependence(self):
        """Test that scores differ by regime."""
        goldilocks_scores = compute_sector_scores(
            regime="Goldilocks",
            growth_score=0.5,
            liquidity_score=0.3,
            risk_score=-0.2,
        )

        stagflation_scores = compute_sector_scores(
            regime="Stagflation",
            growth_score=-0.5,
            liquidity_score=-0.3,
            risk_score=0.2,
        )

        # At least some sectors should have different scores
        differences = [
            abs(goldilocks_scores[s] - stagflation_scores[s])
            for s in SECTOR_CONFIG
        ]
        assert max(differences) > 0.1


class TestSignalGeneration:
    """Test signal generation (OW/N/UW)."""

    def test_ow_threshold(self):
        """Test Overweight threshold."""
        sector_scores = {s: 0.6 for s in SECTOR_CONFIG}  # All above threshold
        signals = get_sector_signals(sector_scores)

        for signal in signals.values():
            assert signal == "Overweight"

    def test_uw_threshold(self):
        """Test Underweight threshold."""
        sector_scores = {s: -0.6 for s in SECTOR_CONFIG}  # All below threshold
        signals = get_sector_signals(sector_scores)

        for signal in signals.values():
            assert signal == "Underweight"

    def test_neutral_range(self):
        """Test Neutral range."""
        sector_scores = {s: 0.0 for s in SECTOR_CONFIG}  # All in middle
        signals = get_sector_signals(sector_scores)

        for signal in signals.values():
            assert signal == "Neutral"

    def test_boundary_values(self):
        """Test exact boundary values."""
        # At +0.5, should be OW (>= threshold)
        signals = get_sector_signals({"Test": 0.5})
        assert signals["Test"] == "Overweight"

        # At -0.5, should be UW (<= threshold)
        signals = get_sector_signals({"Test": -0.5})
        assert signals["Test"] == "Underweight"


class TestSectorTable:
    """Test sector table generation."""

    def test_table_structure(self):
        """Test that sector table has correct structure."""
        sector_scores = compute_sector_scores(
            regime="Goldilocks",
            growth_score=0.5,
            liquidity_score=0.3,
            risk_score=-0.2,
        )
        signals = get_sector_signals(sector_scores)
        table = get_sector_table(sector_scores, signals)

        # Should have expected columns
        assert "Sector" in table.columns
        assert "Signal" in table.columns
        assert "Score" in table.columns
        assert "Rationale" in table.columns

        # Should have one row per sector
        assert len(table) == len(SECTOR_CONFIG)

    def test_table_sorting(self):
        """Test that table is sorted by score."""
        # Create scores with clear ordering
        sector_scores = {s: i * 0.1 for i, s in enumerate(SECTOR_CONFIG)}
        signals = {s: "Neutral" for s in SECTOR_CONFIG}
        table = get_sector_table(sector_scores, signals)

        # Should be sorted descending by score
        scores = table["Score"].tolist()
        assert scores == sorted(scores, reverse=True)


class TestPortfolioConstruction:
    """Test portfolio construction."""

    def test_base_weights(self):
        """Test that base weights are equal."""
        constructor = PortfolioConstructor()

        signals = {s: "Neutral" for s in SECTOR_CONFIG}
        portfolio = constructor.construct(signals)

        # All weights should be equal (1/7)
        weights = portfolio["Model Weight"].tolist()
        assert all(abs(w - 1/7) < 0.001 for w in weights)

    def test_ow_tilt(self):
        """Test OW tilt applied correctly."""
        constructor = PortfolioConstructor()

        signals = {s: "Overweight" if i == 0 else "Neutral" for i, s in enumerate(SECTOR_CONFIG)}
        portfolio = constructor.construct(signals)

        # First sector should have higher weight
        ow_weight = portfolio.iloc[0]["Model Weight"]
        neutral_weight = portfolio.iloc[1]["Model Weight"]
        assert ow_weight > neutral_weight

    def test_uw_tilt(self):
        """Test UW tilt applied correctly."""
        constructor = PortfolioConstructor()

        signals = {s: "Underweight" if i == 0 else "Neutral" for i, s in enumerate(SECTOR_CONFIG)}
        portfolio = constructor.construct(signals, sector_scores={s: -0.6 if i == 0 else 0.0 for i, s in enumerate(SECTOR_CONFIG)})

        # Find the UW sector row
        uw_row = portfolio[portfolio["Sector"] == list(SECTOR_CONFIG.keys())[0]].iloc[0]
        assert uw_row["Signal"] == "Underweight"
        assert uw_row["Deviation"] < 0  # Negative deviation = UW

    def test_max_constraint(self):
        """Test maximum weight constraint."""
        constructor = PortfolioConstructor(max_weight=0.20, tilt_magnitude=0.10)

        signals = {s: "Overweight" for s in SECTOR_CONFIG}
        portfolio = constructor.construct(signals)

        # No weight should exceed max
        for weight in portfolio["Model Weight"]:
            assert weight <= 0.20 + 0.001  # Allow small tolerance

    def test_min_constraint(self):
        """Test minimum weight constraint."""
        constructor = PortfolioConstructor(min_weight=0.05, tilt_magnitude=0.10)

        signals = {s: "Underweight" for s in SECTOR_CONFIG}
        portfolio = constructor.construct(signals)

        # No weight should be below min
        for weight in portfolio["Model Weight"]:
            assert weight >= 0.05 - 0.001  # Allow small tolerance

    def test_weights_sum_to_one(self):
        """Test that weights sum to 100%."""
        constructor = PortfolioConstructor()

        signals = {s: "Overweight" if i % 2 == 0 else "Underweight" for i, s in enumerate(SECTOR_CONFIG)}
        portfolio = constructor.construct(signals)

        total = portfolio["Model Weight"].sum()
        assert abs(total - 1.0) < 0.001


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_scores(self):
        """Test behavior with empty scores."""
        signals = get_sector_signals({})
        assert len(signals) == 0

    def test_single_sector(self):
        """Test with single sector."""
        scores = {"Test Sector": 0.5}
        signals = get_sector_signals(scores)
        assert signals["Test Sector"] == "Overweight"

        portfolio = construct_model_portfolio(signals, scores)
        assert len(portfolio) == 1
        assert portfolio["Model Weight"].iloc[0] == 1.0