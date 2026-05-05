"""
Test dashboard signal snapshot section.

Verifies that the Latest Signal Snapshot section builds correctly without
undefined variable errors.
"""

import pytest
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.metric_interpretation import (
    interpret_growth,
    interpret_inflation,
    interpret_financial_conditions_ease,
    interpret_risk_appetite,
    interpret_credit_stress,
    interpret_recession_risk,
)


class TestDashboardSignalSnapshot:
    """Test signal snapshot builds without undefined variable errors."""

    def test_risk_appetite_interpretation(self):
        """Test risk appetite interpretation with actual values."""
        r_latest = -0.20
        r_change = 0.0

        # This should not raise NameError
        r_interp_obj = interpret_risk_appetite(r_latest, r_change)

        # Extract level and direction (mimics dashboard logic)
        r_level = r_interp_obj.level
        r_direction = r_interp_obj.direction

        # Build interpretation string
        r_interp_str = f"{r_level}, {r_direction}"

        assert r_level is not None
        assert r_direction is not None
        assert isinstance(r_interp_str, str)

    def test_signal_snapshot_row_building(self):
        """Test building signal snapshot rows with all metrics."""
        # Test data matching current dashboard state
        test_scores = {
            "growth": 0.08,
            "inflation": 1.07,
            "liquidity": 0.64,
            "risk": -0.20,
        }

        snapshot_data = []

        # Growth
        g_latest = test_scores["growth"]
        g_change = 0.0
        g_interp = interpret_growth(g_latest, g_change)
        snapshot_data.append({
            "Signal": "Growth",
            "Latest Score": f"{g_latest:+.2f}",
            "3M Change": f"{g_change:+.2f}",
            "State": g_interp.level,
            "Direction": g_interp.direction,
            "Interpretation": g_interp.interpretation
        })

        # Inflation
        i_latest = test_scores["inflation"]
        i_change = 1.75  # Rising
        i_interp = interpret_inflation(i_latest, i_change)
        snapshot_data.append({
            "Signal": "Inflation",
            "Latest Score": f"{i_latest:+.2f}",
            "3M Change": f"{i_change:+.2f}",
            "State": i_interp.level,
            "Direction": i_interp.direction,
            "Interpretation": i_interp.interpretation
        })

        # Financial Conditions
        l_latest = test_scores["liquidity"]
        l_change = -0.2
        fc_interp_obj = interpret_financial_conditions_ease(l_latest, l_change)
        snapshot_data.append({
            "Signal": "Fin. Conditions",
            "Latest Score": f"{l_latest:+.2f}",
            "3M Change": f"{l_change:+.2f}",
            "State": fc_interp_obj.level,
            "Direction": fc_interp_obj.direction,
            "Interpretation": fc_interp_obj.interpretation
        })

        # Risk Appetite - The problematic section
        r_latest = test_scores["risk"]
        r_change = 0.0
        r_interp_obj = interpret_risk_appetite(r_latest, r_change)

        # This mimics the fixed dashboard code
        r_level = r_interp_obj.level
        r_direction = r_interp_obj.direction

        r_interp_str = f"{r_level}, {r_direction}"
        if r_level == "Risk-On" and r_direction == "Deteriorating":
            r_interp_str = "Risk-On → Softening (risk appetite remains positive but softening)"
        elif r_level == "Risk-Off" and r_direction == "Improving":
            r_interp_str = "Risk-Off → Improving (risk appetite recovering from risk-off levels)"

        snapshot_data.append({
            "Signal": "Risk Appetite",
            "Latest Score": f"{r_latest:+.2f}",
            "3M Change": f"{r_change:+.2f}",
            "State": r_interp_obj.level,
            "Direction": r_interp_obj.direction,
            "Interpretation": r_interp_obj.interpretation
        })

        # Verify no errors and correct structure
        assert len(snapshot_data) == 4

        # Check expected values
        inflation_row = [r for r in snapshot_data if r["Signal"] == "Inflation"][0]
        assert "Elevated" in inflation_row["State"], f"Expected 'Elevated', got '{inflation_row['State']}'"

        risk_row = [r for r in snapshot_data if r["Signal"] == "Risk Appetite"][0]
        assert "Neutral" in risk_row["State"], f"Expected 'Neutral', got '{risk_row['State']}'"

        fc_row = [r for r in snapshot_data if r["Signal"] == "Fin. Conditions"][0]
        assert "Easy" in fc_row["State"], f"Expected 'Easy', got '{fc_row['State']}'"

        growth_row = [r for r in snapshot_data if r["Signal"] == "Growth"][0]
        assert "Neutral" in growth_row["State"] or "Strong" in growth_row["State"], f"Unexpected state: {growth_row['State']}"

    def test_no_name_error_with_edge_cases(self):
        """Test that edge cases don't cause NameError."""
        # Empty series handling
        r_latest = 0.0
        r_change = 0.0

        r_interp_obj = interpret_risk_appetite(r_latest, r_change)

        # These should not raise NameError
        r_level = r_interp_obj.level
        r_direction = r_interp_obj.direction

        assert r_level is not None
        assert r_direction is not None

    def test_safe_defaults_for_missing_data(self):
        """Test safe defaults when data is missing."""
        # Simulate missing series with safe defaults
        score = 0.0 if None is None else 0.0
        change = 0.0 if None is None else 0.0

        r_interp_obj = interpret_risk_appetite(score, change)

        # Should still work
        assert r_interp_obj.level is not None
        assert r_interp_obj.direction is not None
        assert r_interp_obj.interpretation is not None

    def test_interpretation_returns_expected_values(self):
        """Test that interpretation functions return expected values."""
        # Risk Appetite at -0.20 should be Neutral
        r_interp = interpret_risk_appetite(-0.20, 0.0)
        assert r_interp.level == "Neutral", f"Expected 'Neutral', got '{r_interp.level}'"

        # Inflation at +1.07 should be Elevated
        i_interp = interpret_inflation(1.07, 1.75)
        assert "Elevated" in i_interp.level, f"Expected 'Elevated', got '{i_interp.level}'"

        # Financial Conditions at +0.64 should be Easy
        fc_interp = interpret_financial_conditions_ease(0.64, -0.2)
        assert fc_interp.level == "Easy", f"Expected 'Easy', got '{fc_interp.level}'"

        # Growth at +0.08 should be Neutral
        g_interp = interpret_growth(0.08, 0.0)
        assert g_interp.level == "Neutral", f"Expected 'Neutral', got '{g_interp.level}'"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
