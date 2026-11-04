"""Known-answer tests for the Four Quadrants framework (Phase 1)."""
from api.calculations.quadrants import (
    surprise_z, classify_quadrant, quadrant_view, REGIME_TO_QUADRANT,
)


def test_classify_four_quadrants():
    assert classify_quadrant(1.0, 1.0) == "Reflation"       # growth↑ inflation↑
    assert classify_quadrant(1.0, -1.0) == "Goldilocks"     # growth↑ inflation↓
    assert classify_quadrant(-1.0, 1.0) == "Stagflation"    # growth↓ inflation↑
    assert classify_quadrant(-1.0, -1.0) == "Deflation"     # growth↓ inflation↓


def test_surprise_positive_when_latest_above_trend():
    # ~2 with small variance, then a jump to 5 -> large positive surprise
    assert surprise_z([2.0, 2.1, 1.9, 2.05, 1.95, 5.0]) > 1.0


def test_surprise_negative_when_latest_below_trend():
    assert surprise_z([5.0, 5.1, 4.9, 5.05, 4.95, 2.0]) < -1.0


def test_surprise_none_on_short_series():
    assert surprise_z([1, 2]) is None


def test_quadrant_view_cross_validation_aligned():
    # goldilocks regime + growth↑ inflation↓ -> both say Goldilocks
    v = quadrant_view(1.0, -1.0, regime_6="goldilocks")
    assert v["quadrant"] == "Goldilocks"
    assert v["agreement"] is True and v["cross_validation"] == "aligned"
    assert "favored" in v["playbook"]


def test_quadrant_view_cross_validation_disagreement():
    # stagflation regime maps to Stagflation, but surprises say Goldilocks -> flagged
    v = quadrant_view(1.0, -1.0, regime_6="stagflation")
    assert v["agreement"] is False
    assert "DISAGREEMENT" in v["cross_validation"]


def test_quadrant_view_unavailable():
    assert quadrant_view(None, 0.5)["available"] is False


def test_regime_map_covers_six():
    for r in ("goldilocks", "expansion", "reflation", "stagflation", "slowdown", "contraction"):
        assert r in REGIME_TO_QUADRANT
