"""
Test dashboard imports and compilation.

Verifies dashboard.py can compile and all required imports exist.
"""

import pytest
import sys
from pathlib import Path
import py_compile
import importlib.util

PROJECT_ROOT = Path(__file__).parent.parent


class TestDashboardCompilation:
    """Test dashboard compiles without errors."""

    def test_dashboard_py_compiles(self):
        """Verify dashboard.py compiles with py_compile."""
        dashboard_path = PROJECT_ROOT / "dashboard.py"
        assert dashboard_path.exists(), "dashboard.py must exist"

        # This will raise py_compile.PyCompileError if syntax is invalid
        py_compile.compile(str(dashboard_path), doraise=True)

    def test_dashboard_imports_exist(self):
        """Verify all interpretation functions used by dashboard exist."""
        # Import the module and check functions exist
        spec = importlib.util.spec_from_file_location(
            "metric_interpretation",
            PROJECT_ROOT / "src" / "utils" / "metric_interpretation.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        required_functions = [
            "interpret_inflation",
            "interpret_growth",
            "interpret_financial_conditions_ease",
            "interpret_risk_appetite",
            "interpret_recession_risk",
            "interpret_credit_stress",
        ]

        for func_name in required_functions:
            assert hasattr(module, func_name), f"Missing function: {func_name}"

    def test_interpret_credit_stress_returns_correct_format(self):
        """Verify interpret_credit_stress returns level, direction, interpretation."""
        from src.utils.metric_interpretation import interpret_credit_stress

        # Test with normal score
        result = interpret_credit_stress(0.1)
        assert hasattr(result, "level"), "Result should have 'level' attribute"
        assert hasattr(result, "direction"), "Result should have 'direction' attribute"
        assert hasattr(result, "interpretation"), "Result should have 'interpretation' attribute"

        # Test with compressed (favorable) score - positive means compressed/favorable
        result = interpret_credit_stress(0.6)
        assert "Compressed" in result.level or "compressed" in result.level.lower()

        # Test with elevated (unfavorable) score - negative means elevated stress
        result = interpret_credit_stress(-0.6)
        assert "Elevated" in result.level or "elevated" in result.level.lower()


class TestDashboardSignalSnapshot:
    """Test Latest Signal Snapshot can be built safely."""

    def test_signal_snapshot_builds_without_error(self):
        """Build signal snapshot rows with test data."""
        from src.utils.metric_interpretation import (
            interpret_growth,
            interpret_inflation,
            interpret_financial_conditions_ease,
            interpret_risk_appetite,
            interpret_credit_stress,
            interpret_recession_risk,
        )

        # Test data
        test_data = {
            "growth": 0.08,
            "inflation": 1.07,
            "financial_conditions": 0.64,
            "risk_appetite": -0.20,
            "credit_stress": 0.00,
            "recession_risk": 0.05,
        }

        snapshot_data = []

        # Growth
        g_interp = interpret_growth(test_data["growth"], 0.0)
        snapshot_data.append({
            "Signal": "Growth",
            "State": g_interp.level,
            "Direction": g_interp.direction,
        })

        # Inflation
        i_interp = interpret_inflation(test_data["inflation"], 1.75)
        snapshot_data.append({
            "Signal": "Inflation",
            "State": i_interp.level,
            "Direction": i_interp.direction,
        })

        # Financial Conditions
        fc_interp = interpret_financial_conditions_ease(test_data["financial_conditions"], -0.2)
        snapshot_data.append({
            "Signal": "Fin. Conditions",
            "State": fc_interp.level,
            "Direction": fc_interp.direction,
        })

        # Risk Appetite
        r_interp = interpret_risk_appetite(test_data["risk_appetite"], 0.0)
        snapshot_data.append({
            "Signal": "Risk Appetite",
            "State": r_interp.level,
            "Direction": r_interp.direction,
        })

        # Credit Stress
        cs_interp = interpret_credit_stress(test_data["credit_stress"])
        snapshot_data.append({
            "Signal": "Credit Stress",
            "State": cs_interp.level,
            "Interpretation": cs_interp.interpretation,
        })

        # Recession Risk
        rec_interp = interpret_recession_risk(test_data["recession_risk"] * 100)
        snapshot_data.append({
            "Signal": "Recession Risk",
            "State": rec_interp.level,
        })

        # Verify all rows built
        assert len(snapshot_data) == 6, f"Expected 6 rows, got {len(snapshot_data)}"

        # Verify specific values
        credit_row = [r for r in snapshot_data if r["Signal"] == "Credit Stress"][0]
        assert "Normal" in credit_row["State"] or "normal" in credit_row["State"].lower(), \
            f"Expected 'Normal', got '{credit_row['State']}'"

        rec_row = [r for r in snapshot_data if r["Signal"] == "Recession Risk"][0]
        assert "Low" in rec_row["State"], f"Expected 'Low', got '{rec_row['State']}'"

    def test_no_name_error_on_import(self):
        """Verify dashboard can import all required functions."""
        # This simulates what dashboard.py does at import time
        try:
            from src.utils.metric_interpretation import (
                interpret_inflation,
                interpret_growth,
                interpret_financial_conditions_ease,
                interpret_risk_appetite,
                interpret_recession_risk,
                interpret_credit_stress,
            )
            # If we get here, imports succeeded
            assert True
        except NameError as e:
            pytest.fail(f"NameError during import: {e}")
        except ImportError as e:
            pytest.fail(f"ImportError: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
