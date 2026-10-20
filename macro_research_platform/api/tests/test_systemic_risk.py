"""Published systemic-risk / cycle indicators: properties each method must satisfy."""
import math

import numpy as np
import pytest

from api.calculations import systemic_risk as sr


def test_turbulence_flags_unusual_days():
    rng = np.random.default_rng(0)
    r = rng.normal(0, 0.01, size=(600, 4))
    r[-1] = [0.08, -0.08, 0.08, -0.08]                  # extreme, correlation-breaking day
    t = sr.turbulence_series(r, window=500, min_window=252)
    assert np.isnan(t[:252]).all() and not np.isnan(t[-1])
    assert sr.percentile_of_last(t) == pytest.approx(100.0)
    # chi-square-like: mean turbulence ≈ number of assets for multivariate normal data
    assert 2 < np.nanmean(t[252:-1]) < 6


def test_absorption_ratio_rises_with_coupling():
    rng = np.random.default_rng(1)
    common = rng.normal(0, 0.01, size=(500, 1))
    loose = rng.normal(0, 0.01, size=(500, 10))
    tight = common + 0.2 * loose
    assert sr.absorption_ratio(tight) > 0.9 > sr.absorption_ratio(loose)
    assert 0 < sr.absorption_ratio(loose) <= 1


def test_standardized_shift_sign():
    base = np.concatenate([np.full(240, 0.5) + np.linspace(0, 0.01, 240), np.full(15, 0.6)])
    assert sr.standardized_shift(base) > 1
    assert sr.standardized_shift(np.ones(100)) is None       # not enough history


def test_svensson_reproduces_published_yields():
    # Fed GSW parameters for 2026-09-25 and its published 1Y / 2Y zero yields.
    p = (2.22044605712841e-14, 3.97814920828024, 5.14227802330804, 16.6601016755639, 1.814994, 15.523129)
    assert sr.svensson_zero_yield(1, *p) == pytest.approx(4.5623, abs=1e-3)
    assert sr.svensson_zero_yield(2, *p) == pytest.approx(4.8039, abs=1e-3)


def test_ntfs_sign_follows_expected_policy_path():
    flat = (4.0, 0.0, 0.0, 0.0, 1.5, 10.0)                  # flat curve: no change priced
    assert sr.near_term_forward_spread(flat) == pytest.approx(0.0, abs=1e-9)
    inverted = (3.0, 2.0, 0.0, 0.0, 1.0, 10.0)              # short rates above long: easing priced
    assert sr.near_term_forward_spread(inverted) < 0


def test_probit_fit_recovers_direction():
    rng = np.random.default_rng(2)
    x = rng.normal(0, 1, 800)
    y = (rng.normal(0, 1, 800) < -0.5 - 1.2 * x).astype(int)  # lower x → more recessions
    m = sr.fit_recession_probit(x, y)
    assert m["slope"] < -0.8 and sr.probit_prob(m, -2) > sr.probit_prob(m, 2)


def test_environment_balance():
    even = {"Equity": 1, "Nominal bonds": 1, "Inflation-linked bonds": 1, "Commodities": 1}
    split = sr.environment_risk_split(even)
    assert all(v == pytest.approx(0.25) for v in split.values()) and sr.balance_score(split) == 1.0
    eq_only = sr.environment_risk_split({"Equity": 1})
    assert eq_only["Rising growth"] == 0.5 and sr.balance_score(eq_only) < 0.5
    w = sr.environment_balanced_weights({k: 0.1 for k in sr.ASSET_ENVIRONMENTS})
    assert sum(w.values()) == pytest.approx(1.0, abs=1e-3)
    # equal vols → each environment carries equal risk
    risk = {k: v * 0.1 for k, v in w.items()}
    assert sr.balance_score(sr.environment_risk_split(risk)) == pytest.approx(1.0, abs=1e-3)


def test_desk_systemic_warning_routes():
    from api.calculations.desk import build_queue
    cyc = {"turbulence": {"turbulent": True, "avg_20d": 15.2}, "absorption_ratio": {"standardized_shift": 1.4},
           "near_term_forward_spread": {"value_pp": -0.3}}
    q = build_queue("risk", "r", orders=[], cycle=cyc)
    item = next(i for i in q if i["kind"] == "systemic")
    assert item["priority"] == "high" and "easing priced" in item["detail"]
    assert not any(i["kind"] == "systemic" for i in build_queue("risk", "r", orders=[],
                   cycle={"turbulence": {"turbulent": False}, "absorption_ratio": {"standardized_shift": 0.2},
                          "near_term_forward_spread": {"value_pp": 0.9}}))
