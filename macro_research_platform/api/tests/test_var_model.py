"""
Known-answer tests for VaR & stress math (Phase 3).
Run: pytest api/tests/test_var_model.py
"""
import numpy as np
import pytest

from api.calculations.var_model import (
    portfolio_pnl_series, historical_var, parametric_var, monte_carlo_var,
    scale_horizon, component_var_by_position, scenario_pnl, reverse_stress,
    concentration, days_to_liquidate, suggest_size_for_var, STRESS_SCENARIOS,
)


def test_suggest_size_for_var_budget():
    # daily_vol 2%, price 100, VaR limit $1000 at 95%: max notional = 1000/(1.645*0.02)
    s = suggest_size_for_var(0.02, 100.0, 1000.0, 0.95, 1)
    assert s["max_notional"] == pytest.approx(1000 / (1.6448536 * 0.02), rel=1e-3)
    assert s["suggested_shares"] == int(s["max_notional"] / 100.0)


def test_suggest_size_smaller_for_higher_vol():
    lo = suggest_size_for_var(0.01, 100.0, 1000.0)["max_notional"]
    hi = suggest_size_for_var(0.04, 100.0, 1000.0)["max_notional"]
    assert hi < lo  # higher vol -> smaller allowed size


def test_portfolio_pnl_series():
    R = np.array([[0.01, -0.02], [-0.01, 0.03]])
    mv = [1000.0, 2000.0]
    pnl = portfolio_pnl_series(mv, R)
    assert pnl[0] == pytest.approx(1000 * 0.01 + 2000 * -0.02)   # -30
    assert pnl[1] == pytest.approx(1000 * -0.01 + 2000 * 0.03)   # 50


def test_parametric_var_matches_normal_quantile():
    # P&L ~ N(0, 1000): 95% VaR ~ 1.645*1000.
    rng = np.random.default_rng(0)
    pnl = rng.normal(0, 1000, 200_000)
    v = parametric_var(pnl, 0.95)
    assert v == pytest.approx(1645, rel=0.03)


def test_historical_var_percentile():
    pnl = np.arange(-100, 100)  # -100..99
    v = historical_var(pnl, 0.95)  # 5th percentile of -100..99 ~ -90
    assert 85 <= v <= 95


def test_var_99_greater_than_95():
    rng = np.random.default_rng(1)
    pnl = rng.normal(0, 500, 100_000)
    assert parametric_var(pnl, 0.99) > parametric_var(pnl, 0.95)


def test_scale_horizon_sqrt_time():
    assert scale_horizon(100.0, 10) == pytest.approx(100 * (10 ** 0.5), abs=0.01)


def test_monte_carlo_close_to_parametric_single_asset():
    # Single asset, mv=1000, daily sigma 0.02 -> pnl sigma = 20 -> 95% VaR ~ 32.9.
    rng = np.random.default_rng(2)
    R = rng.normal(0, 0.02, (2000, 1))
    mc = monte_carlo_var([1000.0], R, 0.95, n_sims=50000)
    assert mc == pytest.approx(1.645 * 20, rel=0.10)


def test_component_var_sums_to_total():
    rng = np.random.default_rng(3)
    R = rng.normal(0, 0.01, (500, 3))
    mv = [1000.0, -500.0, 800.0]
    pnl = portfolio_pnl_series(mv, R)
    total = parametric_var(pnl, 0.95)
    comps = component_var_by_position(["A", "B", "C"], mv, R, total)
    assert sum(c["component_var"] for c in comps) == pytest.approx(total, rel=0.05)


def test_scenario_pnl_known():
    dexp = {"equity": 100000.0, "rates": -20000.0}   # $ P&L per 1.0 factor return
    res = scenario_pnl(dexp, {"equity": -0.10, "rates": 0.05})
    assert res["by_factor"]["equity"] == pytest.approx(-10000)
    assert res["by_factor"]["rates"] == pytest.approx(-1000)
    assert res["total_pnl"] == pytest.approx(-11000)


def test_reverse_stress_shock():
    dexp = {"equity": 100000.0, "rates": -50000.0}
    rows = reverse_stress(dexp, target_loss=10000.0)
    eq = next(r for r in rows if r["factor"] == "equity")
    assert eq["required_shock"] == pytest.approx(-0.10)   # -10000/100000
    # smallest |shock| first
    assert abs(rows[0]["required_shock"]) <= abs(rows[-1]["required_shock"])


def test_concentration_known_weights():
    positions = [
        {"symbol": "A", "market_value": 6000, "book": "X"},
        {"symbol": "B", "market_value": -3000, "book": "X"},
        {"symbol": "C", "market_value": 1000, "book": "Y"},
    ]  # gross = 10000
    c = concentration(positions, limit_pct=0.5)
    assert c["largest_name"] == "A" and c["largest_weight"] == pytest.approx(0.6)
    assert c["top5_concentration"] == pytest.approx(1.0)
    assert any(b["symbol"] == "A" for b in c["breaches"])  # 0.6 > 0.5


def test_days_to_liquidate():
    assert days_to_liquidate(100000, 500000, 0.20) == pytest.approx(1.0)  # 100k / (0.2*500k)
    assert days_to_liquidate(100, None) is None


def test_stress_scenarios_registry():
    assert "gfc_2008" in STRESS_SCENARIOS
    for s in STRESS_SCENARIOS.values():
        assert "label" in s and "equity" in s["shocks"]
