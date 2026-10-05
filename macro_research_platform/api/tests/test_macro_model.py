"""Systematic macro model: each stage's defining property, plus no look-ahead."""
import math

import numpy as np
import pandas as pd
import pytest

from api.model import core
from api.model.core import ModelParams


def _synthetic(n=360, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("1990-01-01", periods=n, freq="MS")
    g = np.cumsum(rng.normal(0, 0.3, n)) * 0.2 + np.sin(np.arange(n) / 18)
    i = np.cumsum(rng.normal(0, 0.3, n)) * 0.2 + np.cos(np.arange(n) / 25)
    panel = pd.DataFrame({f"G{k}": g + rng.normal(0, 0.3, n) for k in range(4)} |
                         {f"I{k}": i + rng.normal(0, 0.3, n) for k in range(4)}, index=idx)
    panel = panel.rename(columns={"G0": "INDPRO", "I0": "CPIAUCSL"})
    dg = pd.Series(g, index=idx).diff(3).fillna(0)
    rets = pd.DataFrame({
        "Eq": 0.006 + 0.01 * np.sign(dg) + rng.normal(0, 0.04, n),
        "Bond": 0.002 - 0.004 * np.sign(dg) + rng.normal(0, 0.015, n),
        "Gold": 0.003 + rng.normal(0, 0.035, n),
        "Comm": 0.002 + rng.normal(0, 0.05, n),
    }, index=idx)
    blocks = {c: ("growth" if c in ("INDPRO", "G1", "G2", "G3") else "inflation") for c in panel.columns}
    env = {"Eq": "Equity", "Bond": "Nominal bonds", "Gold": "Gold", "Comm": "Commodities"}
    return panel, rets, blocks, env


def test_diffusion_factor_recovers_common_component():
    panel, *_ = _synthetic()
    f, load = core.diffusion_factor(panel[["INDPRO", "G1", "G2", "G3"]], "INDPRO")
    assert load["INDPRO"] > 0 and f.corr(panel["INDPRO"]) > 0.9
    assert abs(f.mean()) < 1e-9 and abs(f.std(ddof=0) - 1) < 1e-9


def test_quadrant_probabilities_are_a_distribution():
    q = core.quadrant_probabilities(0.7, 0.2)
    assert sum(q.values()) == pytest.approx(1.0)
    assert q["Goldilocks"] == pytest.approx(0.7 * 0.8)
    assert max(q, key=q.get) == "Goldilocks"


def test_regime_means_shrink_toward_overall():
    idx = pd.date_range("2000-01-01", periods=40, freq="MS")
    r = pd.DataFrame({"A": [0.02] * 20 + [0.0] * 20}, index=idx)
    lab = pd.Series(["Goldilocks"] * 20 + ["Stagflation"] * 20, index=idx)
    cond, counts = core.regime_conditional_means(r, lab, k=20)
    assert counts["Goldilocks"] == 20
    assert cond.loc["A", "Goldilocks"] == pytest.approx((20 * 0.02 + 20 * 0.01) / 40)
    assert cond.loc["A", "Reflation"] == pytest.approx(0.01)          # no data → overall mean


def test_black_litterman_limits():
    cov = np.diag([0.002, 0.0005, 0.001])
    w = np.array([0.3, 0.5, 0.2])
    views = np.array([0.02, -0.01, 0.0])
    mu0, pi = core.black_litterman(cov, w, views, 2.5, 0.05, 1e-9)
    assert np.allclose(mu0, pi, atol=1e-6)                             # no confidence → equilibrium
    mu_inf, _ = core.black_litterman(cov, w, views, 2.5, 0.05, 1e9)
    assert np.allclose(mu_inf, views, atol=1e-6)                       # full confidence → views


def test_optimizer_respects_bounds_and_vol_target():
    cov = np.diag([0.003, 0.0004, 0.002])
    mu = np.array([0.01, 0.002, 0.006])
    w = core.optimize(mu, cov, 2.5, 0.4, 0.10 / math.sqrt(12))
    assert (w >= -1e-9).all() and (w <= 0.4 + 1e-9).all() and w.sum() <= 1 + 1e-9
    assert math.sqrt(w @ cov @ w) * math.sqrt(12) <= 0.10 + 1e-6


def test_strategic_scaling_respects_gross_limit():
    cov = np.diag([0.0001, 0.0001])
    w = core.scale_to_target(np.array([0.5, 0.5]), cov, 0.10 / math.sqrt(12), 1.5)
    assert w.sum() == pytest.approx(1.5)                               # vol target unreachable: capped


def test_decision_has_no_look_ahead():
    panel, rets, blocks, env = _synthetic()
    p = ModelParams(min_history_months=60, cov_months=36)
    t = rets.index[250]
    d1 = core.decide(panel, rets, blocks, env, t, p)
    panel2, rets2 = panel.copy(), rets.copy()
    panel2.loc[panel2.index > t] = 99.0                                 # scramble the future
    rets2.loc[rets2.index > t] = -0.5
    d2 = core.decide(panel2, rets2, blocks, env, t, p)
    assert np.allclose(d1.weights, d2.weights) and d1.regime_probs == d2.regime_probs


def test_backtest_runs_and_reports_tilt_test():
    from api.model.backtest import run_backtest
    panel, rets, blocks, env = _synthetic()
    bt = run_backtest(panel, rets, blocks, env, ModelParams(min_history_months=60, cov_months=36),
                      start="2010-01-01")
    assert bt["available"] and "Tactical (net of costs)" in bt["stats"]
    assert bt["tactical_vs_strategic"]["t_stat"] is not None
    assert bt["forecast_skill"]["growth_direction"]["brier"] <= 0.3
