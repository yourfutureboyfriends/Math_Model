"""
Known-answer tests for alternative-data signal math (Phase 7).
Run: pytest api/tests/test_altdata.py
"""
import numpy as np
import pytest

from api.calculations.altdata import (
    zscore, percentile_rank, term_structure, rolling_correlation, correlation_breakdown,
    correlation_matrix, historical_band,
)


def test_historical_band_flags_spike():
    # 200 values around 100, then a spike to 160 -> should be anomalous (high z).
    closes = list(np.full(200, 100.0) + np.random.default_rng(3).normal(0, 1.0, 200))
    closes.append(160.0)
    band = historical_band(closes, window=252)
    assert band is not None
    assert band["is_anomalous"] is True
    assert band["z_score"] > 2


def test_historical_band_normal_not_flagged():
    closes = list(np.full(200, 50.0) + np.random.default_rng(4).normal(0, 1.0, 200))
    band = historical_band(closes, window=252)
    assert band is not None
    assert band["is_anomalous"] is False
    assert abs(band["z_score"]) <= 2


def test_historical_band_insufficient_data():
    assert historical_band([1.0, 2.0, 3.0]) is None


def test_correlation_matrix_known_values():
    rng = np.random.default_rng(0)
    base = rng.normal(0, 1, 200)
    data = {
        "A": base,
        "B": base,               # identical -> +1.0
        "C": -base,              # inverse  -> -1.0
        "D": rng.normal(0, 1, 200),  # independent -> ~0
    }
    res = correlation_matrix(data, window=200)
    assert res["labels"] == ["A", "B", "C", "D"]
    m = res["matrix"]
    assert m[0][0] == 1.0                 # diagonal
    assert m[0][1] == 1.0                 # A vs B identical
    assert m[0][2] == -1.0                # A vs C inverse
    assert abs(m[0][3]) < 0.2             # A vs D independent


def test_correlation_matrix_respects_window():
    rng = np.random.default_rng(1)
    data = {"X": rng.normal(0, 1, 500), "Y": rng.normal(0, 1, 500)}
    res = correlation_matrix(data, window=90)
    assert res["observations"] == 90
    assert res["window"] == 90


def test_correlation_matrix_insufficient_data():
    res = correlation_matrix({"X": [0.1, 0.2], "Y": [0.1, 0.2]}, window=90)
    assert res["matrix"] == []


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
