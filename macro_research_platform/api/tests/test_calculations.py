"""
Bounds-check unit tests for the core financial models.

These assert that every model output stays within its documented, sane range — the
kind of check that would have caught the historical bugs (recession reading 100% at a
mildly inverted curve; momentum reading +1820%). Run: pytest api/tests/test_calculations.py
"""
import math
import pytest

from api.calculations.models import (
    estrella_mishkin_recession_prob,
    yield_curve_spread_bps,
    copper_gold_ratio,
    momentum_12_1,
    ensemble_agreement,
    MODELS,
)


# ── Recession probability ────────────────────────────────────────────────────
@pytest.mark.parametrize("spread_pp", [-3.0, -1.0, -0.66, -0.1, 0.0, 0.5, 1.0, 2.5, 5.5])
def test_recession_prob_within_unit_interval(spread_pp):
    p = estrella_mishkin_recession_prob(spread_pp)
    assert 0.0 <= p <= 1.0, f"prob {p} out of [0,1] at spread {spread_pp}"


def test_recession_prob_reference_point_minus_066():
    # NY Fed model at a 66bp inversion is ~45%, NOT ~100% (the historical bug).
    p = estrella_mishkin_recession_prob(-0.66)
    assert 0.40 <= p <= 0.55, f"expected ~0.45 at -0.66pp, got {p}"


def test_recession_prob_normal_curve_is_low():
    # A normal, positively-sloped curve must give a LOW recession read.
    p = estrella_mishkin_recession_prob(1.0)
    assert p < 0.15, f"normal curve should be low recession prob, got {p}"


def test_recession_prob_monotonic_in_inversion():
    # More inversion (more negative spread) => higher recession probability.
    assert estrella_mishkin_recession_prob(-1.5) > estrella_mishkin_recession_prob(0.5)


def test_recession_prob_rejects_basis_point_units():
    # -66 (bps) passed where pp expected must raise, not silently return ~1.0.
    with pytest.raises(ValueError):
        estrella_mishkin_recession_prob(-66.0)


# ── Yield-curve spread ───────────────────────────────────────────────────────
def test_yield_spread_sign_and_magnitude():
    assert yield_curve_spread_bps(4.49, 4.23) == pytest.approx(26.0, abs=0.6)
    assert yield_curve_spread_bps(4.0, 4.5) < 0  # inversion is negative


def test_yield_spread_within_sane_range():
    bps = yield_curve_spread_bps(4.49, 5.25)
    assert -400 <= bps <= 400


# ── Copper/gold ratio ────────────────────────────────────────────────────────
def test_copper_gold_ratio_below_ten():
    r = copper_gold_ratio(4.2, 2000.0)
    assert 0 < r < 10, f"copper/gold {r} outside plausible (0,10)"


def test_copper_gold_ratio_rejects_zero_gold():
    with pytest.raises(ValueError):
        copper_gold_ratio(4.2, 0.0)


# ── Momentum ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("p1,p12", [(110, 100), (85, 100), (100, 100), (250, 100)])
def test_momentum_within_bounds(p1, p12):
    m = momentum_12_1(price_now=p1, price_1m_ago=p1, price_12m_ago=p12)
    assert -1.0 <= m <= 3.0, f"momentum {m} outside [-100%, +300%]"


def test_momentum_realistic_value():
    # ~18% gain over the 12-1 window.
    m = momentum_12_1(price_now=118, price_1m_ago=118, price_12m_ago=100)
    assert 0.15 <= m <= 0.20


def test_momentum_absurd_base_price_is_clamped():
    # A stale/split-mismatched base price can't produce a 1820% reading.
    m = momentum_12_1(price_now=100, price_1m_ago=100, price_12m_ago=5)
    assert m <= 3.0


# ── Ensemble agreement ───────────────────────────────────────────────────────
def test_ensemble_agreement_all_agree_is_one():
    assert ensemble_agreement(["BULLISH", "BULLISH", "BULLISH", "BULLISH"]) == 1.0


def test_ensemble_agreement_within_unit_interval():
    for sigs in ([], ["A"], ["A", "B"], ["A", "A", "B"], ["A", "B", "C", "A"]):
        a = ensemble_agreement(sigs)
        assert 0.0 <= a <= 1.0


def test_ensemble_agreement_majority():
    assert ensemble_agreement(["UP", "UP", "DOWN"]) == pytest.approx(2 / 3, abs=1e-4)


# ── Methodology registry integrity ───────────────────────────────────────────
def test_methodology_registry_complete():
    ids = {m["id"] for m in MODELS}
    for required in ("recession_estrella_mishkin", "copper_gold_ratio", "momentum_12_1"):
        assert required in ids
    for m in MODELS:
        assert m["formula"] and m["citation"] and "range" in m["output"]
