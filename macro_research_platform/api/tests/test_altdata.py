"""
Known-answer tests for alternative-data signal math (Phase 7).
Run: pytest api/tests/test_altdata.py
"""
import numpy as np
import pytest

from api.calculations.altdata import (
    zscore, percentile_rank, term_structure, rolling_correlation, correlation_breakdown,
)


def test_zscore_at_mean_is_zero():
    assert zscore(5.0, [1, 3, 5, 7, 9]) == pytest.approx(0.0, abs=1e-9)


def test_zscore_degenerate_none():
    assert zscore(5.0, [5, 5, 5, 5, 5]) is None


def test_percentile_rank():
    assert percentile_rank(3, [1, 2, 3, 4, 5, 6]) == pytest.approx(100 * 2 / 6, abs=0.1)


def test_term_structure_contango():
    t = term_structure(14, 15, 18, 20)   # 3m (18) > spot (15) -> contango
    assert t["state"] == "contango"
    assert t["slope_3m_spot"] == pytest.approx(18 / 15 - 1)


def test_term_structure_backwardation():
    t = term_structure(40, 38, 30, 28)   # spot (38) > 3m (30) -> backwardation
    assert t["state"] == "backwardation"


def test_rolling_correlation_perfect():
    r = np.array([0.01, -0.02, 0.03, -0.01, 0.02, 0.0, 0.01])
    corr = rolling_correlation(r, r, window=5)
    assert corr[-1] == pytest.approx(1.0, abs=1e-9)


def test_rolling_correlation_anticorrelated():
    r = np.array([0.01, -0.02, 0.03, -0.01, 0.02, 0.0, 0.01])
    corr = rolling_correlation(r, -r, window=5)
    assert corr[-1] == pytest.approx(-1.0, abs=1e-9)


def test_correlation_breakdown_flags_flip():
    rng = np.random.default_rng(0)
    a = rng.normal(0, 0.01, 300)
    # b tracks a for most history (positive corr), then flips to anti-correlated recently
    b = np.concatenate([a[:250] + rng.normal(0, 0.002, 250), -a[250:] + rng.normal(0, 0.002, 50)])
    res = correlation_breakdown(a, b, window=63, breach_z=2.0)
    assert res["available"] is True
    assert res["current_correlation"] < 0        # flipped negative
    assert res["breakdown"] is True              # far from its positive history


def test_correlation_breakdown_stable_not_flagged():
    rng = np.random.default_rng(1)
    a = rng.normal(0, 0.01, 300)
    b = a + rng.normal(0, 0.002, 300)            # consistently correlated
    res = correlation_breakdown(a, b, window=63)
    assert res["available"] is True
    assert res["breakdown"] is False
