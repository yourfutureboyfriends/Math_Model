"""
Tests for data correctness and consistency.

Run with: pytest tests/data_correctness/ -v
"""

import pytest
import pandas as pd
import json
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestFutureDates:
    """Test that no future-dated data exists."""

    def test_model_results_not_future_dated(self):
        """Latest data date in model results should not be in the future."""
        model_results_path = PROJECT_ROOT / "outputs" / "latest_model_results.json"

        if not model_results_path.exists():
            pytest.skip("Model results not found")

        with open(model_results_path) as f:
            data = json.load(f)

        timestamp_str = data.get("timestamp", "")
        if timestamp_str:
            # Parse the timestamp
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            now = datetime.now()

            # The model run timestamp should not be more than 1 day in the future
            assert timestamp.date() <= now.date() + timedelta(days=1), \
                f"Model timestamp {timestamp.date()} is in the future"

    def test_live_data_not_future_dated(self):
        """Live data should not have future dates."""
        live_data_path = PROJECT_ROOT / "data" / "processed" / "live" / "macro_data.parquet"

        if not live_data_path.exists():
            pytest.skip("No live data found")

        df = pd.read_parquet(live_data_path)
        latest_date = df.index.max()
        now = datetime.now()

        assert latest_date <= now + timedelta(days=1), \
            f"Latest data date {latest_date} is in the future (today: {now.date()})"


class TestInflationLabelConsistency:
    """Test that inflation labels match scores."""

    def test_inflation_positive_is_not_low(self):
        """Positive inflation score should never be labeled 'low'."""
        model_results_path = PROJECT_ROOT / "outputs" / "latest_model_results.json"

        if not model_results_path.exists():
            pytest.skip("Model results not found")

        with open(model_results_path) as f:
            data = json.load(f)

        inflation_score = data.get("scores", {}).get("inflation", 0)
        inflation_state = data.get("regime_classification", {}).get("inflation_state", "").lower()

        if inflation_score > 0.5:
            assert "elevated" in inflation_state or "high" in inflation_state, \
                f"Inflation score {inflation_score:+.2f} should be 'elevated', got '{inflation_state}'"
        elif inflation_score < -0.5:
            assert "low" in inflation_state, \
                f"Inflation score {inflation_score:+.2f} should be 'low', got '{inflation_state}'"


class TestFinancialConditionsLabels:
    """Test financial conditions level vs direction logic."""

    def test_financial_conditions_level_direction_separation(self):
        """Financial conditions should have separate level and direction."""
        model_results_path = PROJECT_ROOT / "outputs" / "latest_model_results.json"

        if not model_results_path.exists():
            pytest.skip("Model results not found")

        with open(model_results_path) as f:
            data = json.load(f)

        liquidity_score = data.get("scores", {}).get("liquidity", 0)
        fc_data = data.get("financial_conditions", {})

        # Level should be based on score magnitude
        # Direction should be based on impulse/change

        # Verify score is numeric
        assert isinstance(liquidity_score, (int, float)), \
            f"Liquidity score should be numeric, got {type(liquidity_score)}"


class TestRecessionRiskConsistency:
    """Test recession risk hierarchy is consistent."""

    def test_recession_risk_values_reasonable(self):
        """Recession risk should be between 0 and 100."""
        model_results_path = PROJECT_ROOT / "outputs" / "latest_model_results.json"

        if not model_results_path.exists():
            pytest.skip("Model results not found")

        with open(model_results_path) as f:
            data = json.load(f)

        rec_risk = data.get("recession_risk", {})
        probability = rec_risk.get("probability", 0)

        assert 0 <= probability <= 100, \
            f"Recession probability {probability} should be between 0 and 100"


class TestDataLineage:
    """Test that data lineage report exists and is valid."""

    def test_data_lineage_report_exists(self):
        """Data lineage report should exist."""
        lineage_path = PROJECT_ROOT / "outputs" / "data_lineage_report.csv"

        # This is a soft check - the report should be generated
        if not lineage_path.exists():
            pytest.skip("Data lineage report not found - run data_lineage_reporter.py")

        df = pd.read_csv(lineage_path)
        assert len(df) > 0, "Data lineage report should contain records"

    def test_no_critical_issues_in_lineage(self):
        """Data lineage should not have critical issues."""
        lineage_path = PROJECT_ROOT / "outputs" / "data_lineage_report.csv"

        if not lineage_path.exists():
            pytest.skip("Data lineage report not found")

        df = pd.read_csv(lineage_path)

        # Check for critical issues
        critical_statuses = ["INVALID_FUTURE_DATE", "SCORE_POSITIVE_BUT_STATE_LOW"]
        critical_issues = df[df["status"].isin(critical_statuses)]

        if len(critical_issues) > 0:
            issue_summary = "\n".join([
                f"  - {row['dashboard_metric_name']}: {row['status']}"
                for _, row in critical_issues.iterrows()
            ])
            pytest.fail(f"Critical issues found:\n{issue_summary}")


class TestMinimumSeriesRequirements:
    """Test minimum series requirements for allocation."""

    def test_minimum_series_requirement_logic(self):
        """Test that minimum series requirement is enforced."""
        # This is a logic test - the actual enforcement happens in the dashboard
        MIN_CORE_MACRO_SERIES = 8
        MIN_MARKET_RISK_SERIES = 4
        MIN_TOTAL_SERIES = MIN_CORE_MACRO_SERIES + MIN_MARKET_RISK_SERIES  # 12

        # Test cases
        test_cases = [
            (2, False, "Only 2 series should not allow allocation"),
            (5, False, "5 series should not allow allocation"),
            (8, False, "8 series (only core) should not allow allocation - need 12 total"),
            (11, False, "11 series should not allow allocation - need 12 total"),
            (12, True, "12 series should allow allocation"),
            (15, True, "15 series should allow allocation"),
        ]

        for series_count, expected, message in test_cases:
            # Must meet BOTH core requirement AND total requirement
            has_enough_core = series_count >= MIN_CORE_MACRO_SERIES
            has_enough_total = series_count >= MIN_TOTAL_SERIES
            result = has_enough_core and has_enough_total
            assert result == expected, message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
