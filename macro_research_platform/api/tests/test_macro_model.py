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


# ── Economies: the euro-area and rest-of-world models share the method ──────────────────────────────────────────
def test_par_bond_returns_match_bond_maths():
    from api.model.sources import par_bond_returns
    idx = pd.date_range("2020-01-01", periods=3, freq="MS")
    flat = par_bond_returns(pd.Series([3.0, 3.0, 3.0], index=idx), years=10, freq=1)
    # unchanged yield: a par bond earns its yield (one month of a 3% annual yield ≈ 0.247%)
    assert flat.iloc[0] == pytest.approx((1.03) ** (1 / 12) - 1, abs=2e-5)
    up = par_bond_returns(pd.Series([3.0, 4.0], index=idx[:2]), years=10, freq=1)
    # +100 bp on a 10-year par bond loses about its modified duration (~8.5) in price
    assert -0.09 < up.iloc[0] < -0.075


def test_economy_specs_are_consistent():
    from api.model.economies import ECONOMIES
    assert set(ECONOMIES) == {"us", "ea", "row"}
    for e in ECONOMIES.values():
        blocks = set(e.blocks().values())
        assert blocks == {"growth", "inflation"}, e.id
        assert e.anchors[0] in e.series and e.series[e.anchors[0]][0] == "growth", e.id
        assert e.anchors[1] in e.series and e.series[e.anchors[1]][0] == "inflation", e.id
        assert set(e.benchmark) <= set(e.assets), e.id
        assert all(t in {"yoy", "neg_yoy", "diff12", "neg_diff12", "level"} for _, t, _ in e.series.values()), e.id
        assert all(lag >= 0 for _, _, lag in e.series.values()), e.id
        assert e.sources and e.limitations and set(e.labels) >= set(e.series), e.id
    assert ECONOMIES["us"].tradeable and not ECONOMIES["ea"].tradeable and not ECONOMIES["row"].tradeable


def test_non_us_model_runs_end_to_end_and_reports_its_economy(monkeypatch):
    """A synthetic economy through the real engine: factors use its anchors, a stale input is left out and
    reported, the 60/40 uses its own legs, and orders are refused for a research-only economy."""
    import asyncio
    import dataclasses
    from api.model import engine as me
    from api.model.economies import ECONOMIES
    panel, rets, _, env = _synthetic(n=300)
    raw = {}
    for c in panel.columns:                       # raw "levels" whose 'level' transform is the synthetic series
        raw[c] = panel[c]
    raw["STALE"] = panel["G1"].iloc[:200]         # stops ~8 years early → excluded
    spec = {c: ("growth" if c in ("INDPRO", "G1", "G2", "G3") else "inflation", "level", 0) for c in panel.columns}
    spec["STALE"] = ("growth", "level", 0)
    rets = rets.rename(columns={"Eq": "Home equity", "Bond": "Home bonds"})

    async def loader():
        return raw, rets
    econ = dataclasses.replace(ECONOMIES["ea"], id="xx", name="Test", series=spec, labels={k: k for k in spec},
                               anchors=("INDPRO", "CPIAUCSL"), benchmark=("Home equity", "Home bonds"),
                               assets={"Home equity": ("-", "-", "Equity"), "Home bonds": ("-", "-", "Nominal bonds"),
                                       "Gold": ("-", "-", "Gold"), "Comm": ("-", "-", "Commodities")}, loader=loader)
    monkeypatch.setattr(me, "get_economy", lambda eid="us": econ)
    monkeypatch.setattr(me, "_save_snapshot", lambda *a: None)
    monkeypatch.setattr(me, "_CACHE", {})
    p = {"min_history_months": 60}
    r = asyncio.run(me.run_model(p, persist=False, force=True, economy="xx"))
    assert r["available"] and r["economy"]["id"] == "xx" and r["economy"]["tradeable"] is False
    used = {c["key"]: c["used"] for c in r["data"]["series"]}
    assert used["STALE"] is False and used["INDPRO"] is True
    assert "STALE" not in r["state"]["loadings"]["growth"] and r["state"]["loadings"]["growth"]["INDPRO"] > 0
    assert r["backtest"]["sixty_forty"] == {"equity": "Home equity", "bonds": "Home bonds"}
    assert sum(r["regime"]["probabilities"].values()) == pytest.approx(1.0, abs=1e-3)
    with pytest.raises(ValueError):
        asyncio.run(me.model_orders(r, "tactical", 1e6))
