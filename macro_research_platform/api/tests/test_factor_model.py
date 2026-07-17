"""
Known-answer tests for the multi-factor risk model (Phase 2).
Run: pytest api/tests/test_factor_model.py
"""
import numpy as np
import pytest

from api.calculations.factor_model import (
    returns_from_closes,
    estimate_factor_loadings,
    regression_fit,
    aggregate_portfolio_loadings,
    contribution_to_vol,
    FACTOR_PROXIES,
)


def test_returns_from_closes():
    r = returns_from_closes([100, 110, 99])
    assert r[0] == pytest.approx(0.10)
    assert r[1] == pytest.approx(-0.10)


def test_known_answer_single_factor_beta():
    # Position return = 1.5 * equity factor exactly -> beta_equity ~ 1.5.
    rng = np.random.default_rng(0)
    eq = rng.normal(0, 0.01, 400)
    pos = 1.5 * eq
    loadings = estimate_factor_loadings(pos, {"equity": eq})
    assert loadings["equity"] == pytest.approx(1.5, abs=1e-6)


def test_known_answer_two_factor_betas():
    rng = np.random.default_rng(1)
    eq = rng.normal(0, 0.01, 500)
    rates = rng.normal(0, 0.008, 500)
    pos = 1.2 * eq - 0.4 * rates + rng.normal(0, 1e-6, 500)  # tiny noise
    loadings = estimate_factor_loadings(pos, {"equity": eq, "rates": rates})
    assert loadings["equity"] == pytest.approx(1.2, abs=1e-2)
    assert loadings["rates"] == pytest.approx(-0.4, abs=1e-2)


def test_r_squared_high_for_clean_fit():
    rng = np.random.default_rng(2)
    eq = rng.normal(0, 0.01, 300)
    pos = 0.9 * eq  # perfectly explained
    r2 = regression_fit(pos, {"equity": eq})
    assert r2 > 0.99


def test_insufficient_data_returns_empty():
    assert estimate_factor_loadings([0.01, 0.02], {"equity": [0.01, 0.02]}) == {}


def test_aggregate_portfolio_loadings_weighted():
    # Two positions: A beta_equity 1.0 at weight 0.6, B beta_equity 2.0 at weight 0.4.
    agg = aggregate_portfolio_loadings(
        [{"equity": 1.0}, {"equity": 2.0}], [0.6, 0.4]
    )
    assert agg["equity"] == pytest.approx(0.6 * 1.0 + 0.4 * 2.0)  # 1.4


def test_short_position_subtracts_loading():
    # A short (negative weight) reduces net equity beta.
    agg = aggregate_portfolio_loadings([{"equity": 1.0}, {"equity": 1.0}], [1.0, -1.0])
    assert agg["equity"] == pytest.approx(0.0, abs=1e-9)


def test_contribution_to_vol_sums_to_one():
    contrib = contribution_to_vol({"equity": 1.0, "rates": 0.5}, {"equity": 0.15, "rates": 0.08})
    assert sum(contrib.values()) == pytest.approx(1.0, abs=1e-6)
    assert all(0.0 <= v <= 1.0 for v in contrib.values())


def test_factor_proxy_registry():
    assert FACTOR_PROXIES["equity"] == "SPY"
    assert len(FACTOR_PROXIES) >= 8
