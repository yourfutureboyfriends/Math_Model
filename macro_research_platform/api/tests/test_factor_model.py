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
    rng = np.random.default_rng(3)
    fac = {"equity": rng.normal(0, 0.01, 500), "rates": rng.normal(0, 0.006, 500)}
    contrib = contribution_to_vol({"equity": 1.0, "rates": 0.5}, fac)
    assert sum(contrib.values()) == pytest.approx(1.0, abs=1e-3)
    assert contrib["equity"] > contrib["rates"]


def test_contribution_to_vol_uses_correlation():
    # Long equity + long a factor that is -1 correlated with it: the second one hedges.
    rng = np.random.default_rng(4)
    eq = rng.normal(0, 0.01, 500)
    fac = {"equity": eq, "hedge": -eq + rng.normal(0, 0.002, 500)}
    contrib = contribution_to_vol({"equity": 1.0, "hedge": 0.5}, fac)
    assert contrib["hedge"] < 0 < contrib["equity"]


def test_style_factors_are_long_short_spreads():
    from api.calculations.factor_model import build_factor_returns, FACTOR_TICKERS
    t = {k: np.full(5, 0.0) for k in FACTOR_TICKERS}
    t["SPY"] = np.full(5, 0.01); t["IWM"] = np.full(5, 0.03)
    t["IWD"] = np.full(5, 0.02); t["IWF"] = np.full(5, 0.005)
    f = build_factor_returns(t)
    assert f["size"][0] == pytest.approx(0.02) and f["value"][0] == pytest.approx(0.015)
    assert "growth" not in f          # value already is value-minus-growth


def test_stress_shocks_translate_to_factor_space():
    from api.calculations.var_model import STRESS_SCENARIOS, to_factor_shocks
    gfc = to_factor_shocks(STRESS_SCENARIOS["gfc_2008"]["shocks"])
    assert gfc["equity"] == -0.42
    assert gfc["size"] == pytest.approx(-0.03)        # IWM -45% vs SPY -42%
    assert gfc["value"] == pytest.approx(-0.04)       # IWD -44% vs IWF -40%
    assert gfc["credit"] == pytest.approx(-0.30 - 0.45 * 0.14)


def test_factor_proxy_registry():
    assert FACTOR_PROXIES["equity"] == "SPY"
    assert len(FACTOR_PROXIES) >= 8


def test_non_core_factors_are_orthogonal_to_equity_and_rates():
    from api.calculations.factor_model import orthogonalize_factors
    rng = np.random.default_rng(0)
    eq, rt = rng.normal(0, 0.01, 500), rng.normal(0, 0.008, 500)
    credit = 0.4 * eq - 0.6 * rt + rng.normal(0.0002, 0.003, 500)
    f = orthogonalize_factors({"equity": eq, "rates": rt, "credit": credit})
    assert abs(np.corrcoef(f["credit"], eq)[0, 1]) < 1e-8 and abs(np.corrcoef(f["credit"], rt)[0, 1]) < 1e-8
    assert f["credit"].mean() == pytest.approx(credit.mean())
    assert np.array_equal(f["equity"], eq)


def test_scenario_shocks_map_into_orthogonal_space():
    from api.calculations.factor_model import orthogonal_shocks
    betas = {"credit": {"equity": 0.4, "rates": -0.6}}
    out = orthogonal_shocks({"equity": -0.4, "rates": 0.1, "credit": -0.3}, betas)
    # credit beyond what equity/rates imply: -0.3 - (0.4*-0.4 + -0.6*0.1) = -0.08
    assert out["credit"] == pytest.approx(-0.08) and out["equity"] == -0.4
