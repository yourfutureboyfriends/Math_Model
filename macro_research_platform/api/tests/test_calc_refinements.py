"""Refined calculations: tail risk (ES, Cornish–Fisher, EWMA, FHS), VaR backtests, flow-adjusted track record with
Sharpe inference, and spread estimators — each against a known answer."""
import math

import numpy as np
import pytest


def test_expected_shortfall_and_normal_consistency():
    from api.calculations import var_model as vm
    rng = np.random.default_rng(1)
    p = rng.normal(0, 1000, 200_000)
    # normal ES 97.5% = σ φ(1.96)/0.025 ≈ 2.338σ; historical converges to it
    assert vm.expected_shortfall_normal(p, 0.975) == pytest.approx(2337.8, rel=0.01)
    assert vm.expected_shortfall_hist(p, 0.975) == pytest.approx(2337.8, rel=0.02)
    assert vm.expected_shortfall_hist(p, 0.975) > vm.historical_var(p, 0.975)


def test_cornish_fisher_reduces_to_normal_and_rises_with_fat_left_tails():
    from api.calculations import var_model as vm
    rng = np.random.default_rng(2)
    normal = rng.normal(0, 1, 100_000)
    assert vm.cornish_fisher_var(normal, 0.99) == pytest.approx(vm.parametric_var(normal, 0.99), rel=0.03)
    fat = rng.standard_t(4, 100_000) - np.where(rng.random(100_000) < 0.02, 3, 0)   # fat, left-skewed
    assert vm.cornish_fisher_var(fat, 0.99) > vm.parametric_var(fat, 0.99)


def test_ewma_and_fhs_react_to_rising_volatility():
    from api.calculations import var_model as vm
    rng = np.random.default_rng(3)
    p = np.concatenate([rng.normal(0, 1, 500), rng.normal(0, 3, 40)])           # volatility just tripled
    assert vm.ewma_var(p, 0.95) > 2 * vm.historical_var(p[:500], 0.95)
    assert vm.filtered_hs(p, 0.95)["var"] > vm.historical_var(p, 0.95)


def test_var_backtest_kupiec_and_basel_traffic_light():
    from api.calculations import var_model as vm
    n = 250
    var = np.ones(n)
    losses = np.zeros(n)
    losses[[10, 60, 120]] = 2.0                                                # 3 exceptions at 99%
    r = vm.var_backtest(losses, var, 0.99)
    assert r["exceptions"] == 3 and r["green_max"] == 4 and r["red_from"] == 10 and r["traffic_light"] == "green"
    losses[[11, 12, 13, 14, 15, 16, 17, 18]] = 2.0                             # 11 exceptions, clustered
    r = vm.var_backtest(losses, var, 0.99)
    assert r["traffic_light"] == "red" and r["kupiec_p"] < 0.01 and r["christoffersen_ind_p"] < 0.05
    # Kupiec LR at x = expected is ~0
    l2 = np.zeros(1000); l2[:50] = 2
    assert vm.var_backtest(l2, np.ones(1000), 0.95)["kupiec_lr"] == pytest.approx(0.0, abs=1e-6)


def test_track_record_removes_capital_flows():
    from api.calculations.fund import track_record, twr_index
    navs = [100.0, 101.0, 1101.0, 1112.01]                                    # +1%, then +1000 subscribed, then +1%
    flows = [0.0, 0.0, 1000.0, 0.0]
    idx = twr_index(navs, flows)
    assert idx[2] == pytest.approx(101.0) and idx[3] == pytest.approx(102.01)
    raw = track_record(navs)
    adj = track_record(navs, flows=flows)
    assert raw["total_return"] > 9 and adj["total_return"] == pytest.approx(0.0201, abs=1e-4) and adj["flow_adjusted"]
    # a withdrawal is not a drawdown
    assert track_record([100.0, 50.0, 50.5], flows=[0.0, -50.0, 0.0])["max_drawdown"] == 0.0


def test_probabilistic_sharpe_grows_with_sample_length():
    from api.calculations.fund import track_record
    rng = np.random.default_rng(4)
    r = rng.normal(0.0004, 0.01, 1500)
    navs = list(100 * np.cumprod(1 + r))
    short, long = track_record(navs[:120]), track_record(navs)
    assert long["probabilistic_sharpe"] > short["probabilistic_sharpe"]
    assert 0 < short["sharpe_se_annual"] and long["sharpe_se_annual"] < short["sharpe_se_annual"]
    assert long["longest_drawdown_days"] >= 1


def _roll_market(spread=0.01, n=3000, seed=5):
    """Efficient price random walk; trades at mid ± half spread; daily high/low from intraday trades."""
    rng = np.random.default_rng(seed)
    hi, lo, cl = [], [], []
    m = 100.0
    for _ in range(n):
        path = m * np.exp(np.cumsum(rng.normal(0, 0.01 / math.sqrt(390), 390)))
        trades = path * (1 + spread / 2 * rng.choice([-1, 1], 390))
        hi.append(trades.max()); lo.append(trades.min()); cl.append(trades[-1])
        m = path[-1]
    return cl, hi, lo


def test_spread_estimators_recover_a_known_spread():
    from api.calculations import portfolio_analytics as pa
    cl, hi, lo = _roll_market(0.01)
    ar = pa.abdi_ranaldo_spread(cl, hi, lo)
    cs = pa.corwin_schultz_spread(hi, lo, cl)
    assert ar == pytest.approx(0.01, rel=0.35) and cs is not None and cs > 0


def test_corwin_schultz_overnight_adjustment_ignores_gaps():
    from api.calculations import portfolio_analytics as pa
    # identical 1%-range days separated by a 5% overnight gap: without adjustment the gap inflates the estimate
    hi, lo, cl = [101.0, 106.05], [100.0, 105.0], [100.5, 105.5]
    assert pa.corwin_schultz_spread(hi, lo, cl) <= pa.corwin_schultz_spread(hi, lo)
