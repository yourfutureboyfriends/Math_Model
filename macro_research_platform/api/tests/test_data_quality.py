"""
Known-answer tests for data-quality checks (Phase 9).
Run: pytest api/tests/test_data_quality.py
"""
import numpy as np
from api.calculations.data_quality import (
    detect_jump_outliers, detect_zscore_outliers, quality_report,
)


def test_jump_outlier_flags_bad_tick():
    closes = [100, 101, 102, 51, 103]   # 102 -> 51 is a ~50% drop (bad tick)
    issues = detect_jump_outliers(closes, 0.25)
    assert len(issues) >= 1
    assert issues[0]["index"] == 3
    assert issues[0]["pct_change"] < -0.4


def test_jump_outlier_ignores_normal_moves():
    closes = [100, 101, 99, 102, 100]   # small moves
    assert detect_jump_outliers(closes, 0.25) == []


def test_zscore_outlier():
    vals = list(np.full(50, 10.0) + np.random.default_rng(0).normal(0, 0.1, 50))
    vals[25] = 100.0                     # extreme outlier
    issues = detect_zscore_outliers(vals, 6.0)
    assert any(i["index"] == 25 for i in issues)


def test_quality_report_pass():
    closes = list(100 + np.cumsum(np.random.default_rng(1).normal(0, 0.5, 100)))
    r = quality_report("CLEAN", closes)
    assert r["status"] in ("PASS", "WARN")     # no hard jumps
    assert r["jump_count"] == 0


def test_quality_report_fail_on_jump():
    closes = [100] * 20 + [40] + [100] * 20    # a 60% bad tick
    r = quality_report("BADTICK", closes, jump_threshold=0.25)
    assert r["status"] == "FAIL"
    assert r["jump_count"] >= 1


def test_quality_report_insufficient_data():
    r = quality_report("SHORT", [100, 101])
    assert r["status"] == "UNKNOWN"
