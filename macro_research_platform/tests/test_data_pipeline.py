"""
Data Pipeline Tests — Range validation for BUG-01, BUG-02, BUG-04.

These tests validate that the pipeline correctly:
- Rejects invalid values outside hard bounds
- Accepts valid values within typical ranges
- Applies correct unit conversions

Run with: pytest tests/test_data_pipeline.py -v
"""
import math
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.data_pipeline import (
    PIPELINE_BOUNDS,
    PIPELINE_FALLBACKS,
    validate_pipeline_value,
    fetch_fred_value,
)


# ═════════════════════════════════════════════════════════════════════════════
# BUG-01: CPI SERIES VALIDATION
# CPI must be in range [-5%, 25%] — index levels (~319) must be rejected
# ═════════════════════════════════════════════════════════════════════════════
class TestCPIRange:
    """CPI YoY must pass through valid inflation values, reject index levels."""

    def test_cpi_bounds_defined(self):
        """Pipeline must have CPI bounds defined."""
        assert "cpi_yoy" in PIPELINE_BOUNDS
        lo, hi = PIPELINE_BOUNDS["cpi_yoy"]
        assert lo == -5.0
        assert hi == 25.0

    def test_valid_inflation_3_3_passes(self):
        """March 2026 CPI = 3.3% must pass through."""
        result = validate_pipeline_value("cpi_yoy", 3.3)
        assert abs(result - 3.3) < 0.01

    def test_index_level_319_rejected(self):
        """CPI index level (~319) must be rejected → fallback."""
        result = validate_pipeline_value("cpi_yoy", 319.0)
        assert result != 319.0
        assert result == PIPELINE_FALLBACKS["cpi_yoy"]

    def test_deflation_minus_5_boundary(self):
        """CPI = -5% at boundary — should pass."""
        result = validate_pipeline_value("cpi_yoy", -5.0)
        assert abs(result - (-5.0)) < 0.01

    def test_hyperinflation_25_boundary(self):
        """CPI = 25% at boundary — should pass."""
        result = validate_pipeline_value("cpi_yoy", 25.0)
        assert abs(result - 25.0) < 0.01

    def test_deflation_below_bounds_rejected(self):
        """CPI < -5% must be rejected."""
        result = validate_pipeline_value("cpi_yoy", -10.0)
        assert result == PIPELINE_FALLBACKS["cpi_yoy"]

    def test_hyperinflation_above_bounds_rejected(self):
        """CPI > 25% must be rejected."""
        result = validate_pipeline_value("cpi_yoy", 50.0)
        assert result == PIPELINE_FALLBACKS["cpi_yoy"]

    def test_none_returns_fallback(self):
        """None value must return fallback."""
        result = validate_pipeline_value("cpi_yoy", None)
        assert result == PIPELINE_FALLBACKS["cpi_yoy"]

    def test_nan_returns_fallback(self):
        """NaN value must return fallback."""
        result = validate_pipeline_value("cpi_yoy", float("nan"))
        assert result == PIPELINE_FALLBACKS["cpi_yoy"]


# ═════════════════════════════════════════════════════════════════════════════
# BUG-02: FED FUNDS RATE VALIDATION
# Fed Funds must be in [0%, 25%] — stale pre-cut values should be flagged
# ═════════════════════════════════════════════════════════════════════════════
class TestFedFundsRange:
    """Fed Funds must accept post-cut 3.64%, reject extreme values."""

    def test_fed_funds_bounds_defined(self):
        """Pipeline must have Fed Funds bounds defined."""
        assert "fed_funds" in PIPELINE_BOUNDS
        lo, hi = PIPELINE_BOUNDS["fed_funds"]
        assert lo == 0.0
        assert hi == 25.0

    def test_post_cut_3_64_passes(self):
        """Mar/Apr 2026 Fed Funds = 3.64% must pass through."""
        result = validate_pipeline_value("fed_funds", 3.64)
        assert abs(result - 3.64) < 0.01

    def test_pre_cut_4_68_passes_but_suspicious(self):
        """Pre-cut 4.68% is within bounds but should be flagged by monitoring."""
        # Note: 4.68% is technically valid (within [0, 25])
        # but is stale — this is where soft bounds / monitoring helps
        result = validate_pipeline_value("fed_funds", 4.68)
        assert 0 <= result <= 25

    def test_extreme_30_percent_rejected(self):
        """30% Fed Funds is implausible and must be rejected."""
        result = validate_pipeline_value("fed_funds", 30.0)
        assert result == PIPELINE_FALLBACKS["fed_funds"]

    def test_zero_rate_passes(self):
        """0% Fed Funds (ZIRP) at boundary — should pass."""
        result = validate_pipeline_value("fed_funds", 0.0)
        assert abs(result - 0.0) < 0.01

    def test_negative_rate_rejected(self):
        """Negative Fed Funds must be rejected."""
        result = validate_pipeline_value("fed_funds", -0.5)
        assert result == PIPELINE_FALLBACKS["fed_funds"]


# ═════════════════════════════════════════════════════════════════════════════
# BUG-04: HY SPREADS VALIDATION
# HY spreads must be in [50 bps, 2500 bps] — unit conversion must be correct
# ═════════════════════════════════════════════════════════════════════════════
class TestHySpreadsRange:
    """HY spreads must accept ~283 bps, reject 3 bps (unconverted 0.03%)."""

    def test_hy_spreads_bounds_defined(self):
        """Pipeline must have HY spreads bounds defined."""
        assert "hy_spread_bps" in PIPELINE_BOUNDS
        lo, hi = PIPELINE_BOUNDS["hy_spread_bps"]
        assert lo == 50.0
        assert hi == 2500.0

    def test_valid_283_bps_passes(self):
        """Apr 2026 HY spreads = ~283 bps must pass through."""
        result = validate_pipeline_value("hy_spread_bps", 283.0)
        assert abs(result - 283.0) < 1.0

    def test_unconverted_3_bps_rejected(self):
        """Raw 0.03% (3 bps after ×100) is below hard_min and must be rejected."""
        # This simulates forgetting to multiply by 100
        result = validate_pipeline_value("hy_spread_bps", 3.0)
        assert result == PIPELINE_FALLBACKS["hy_spread_bps"]

    def test_stress_600_bps_passes(self):
        """600 bps stress level must pass through."""
        result = validate_pipeline_value("hy_spread_bps", 600.0)
        assert abs(result - 600.0) < 1.0

    def test_crisis_2000_bps_passes(self):
        """2000 bps crisis level must pass through."""
        result = validate_pipeline_value("hy_spread_bps", 2000.0)
        assert abs(result - 2000.0) < 1.0

    def test_extreme_3000_bps_rejected(self):
        """3000 bps is above hard_max and must be rejected."""
        result = validate_pipeline_value("hy_spread_bps", 3000.0)
        assert result == PIPELINE_FALLBACKS["hy_spread_bps"]

    def test_boundary_50_bps(self):
        """50 bps at lower boundary — should pass."""
        result = validate_pipeline_value("hy_spread_bps", 50.0)
        assert abs(result - 50.0) < 0.01


# ═════════════════════════════════════════════════════════════════════════════
# ADDITIONAL PIPELINE TESTS
# ═════════════════════════════════════════════════════════════════════════════
class TestPipelineValidation:
    """General pipeline validation behavior."""

    def test_unknown_metric_uses_wide_bounds(self):
        """Unknown metrics should use wide bounds [-1e9, 1e9]."""
        result = validate_pipeline_value("unknown_metric", 1000.0)
        assert result == 1000.0

    def test_string_value_returns_fallback(self):
        """String values must return fallback."""
        result = validate_pipeline_value("cpi_yoy", "not_a_number")
        assert result == PIPELINE_FALLBACKS["cpi_yoy"]

    def test_infinite_value_returns_fallback(self):
        """Infinite values must return fallback."""
        result = validate_pipeline_value("cpi_yoy", float("inf"))
        assert result == PIPELINE_FALLBACKS["cpi_yoy"]


class TestPipelineBoundsCoverage:
    """All pipeline metrics must have bounds and fallbacks defined."""

    def test_all_metrics_have_bounds(self):
        """Every metric in PIPELINE_FALLBACKS must have bounds."""
        for metric in PIPELINE_FALLBACKS:
            assert metric in PIPELINE_BOUNDS, f"{metric} missing from PIPELINE_BOUNDS"

    def test_bounds_are_reasonable(self):
        """Bounds must have lo < hi."""
        for metric, (lo, hi) in PIPELINE_BOUNDS.items():
            assert lo < hi, f"{metric} has invalid bounds [{lo}, {hi}]"

    def test_fallbacks_within_bounds(self):
        """Fallback values must be within hard bounds."""
        for metric, fallback in PIPELINE_FALLBACKS.items():
            lo, hi = PIPELINE_BOUNDS[metric]
            assert lo <= fallback <= hi, \
                f"{metric} fallback {fallback} outside bounds [{lo}, {hi}]"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
