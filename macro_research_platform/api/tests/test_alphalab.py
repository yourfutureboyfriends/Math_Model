"""Stock Signal Lab: the rank IC, quintiles and turnover are computed right, fundamentals are point-in-time and on
today's share basis, and the adaptive composite never uses a month's IC before that month's return is known."""
import numpy as np
import pandas as pd
import pytest

from api.quant import alphalab as al


def test_rank_ic_is_one_for_a_perfect_signal_and_minus_one_reversed():
    rng = np.random.default_rng(0)
    f = rng.normal(size=(24, 120))
    assert np.nanmean(al._ic_series(f, f)) == pytest.approx(1.0)
    assert np.nanmean(al._ic_series(-f, f)) == pytest.approx(-1.0)
    noise = rng.normal(size=f.shape)
    assert abs(np.nanmean(al._ic_series(noise, f))) < 0.05


def test_quintiles_order_returns_and_turnover_counts_replacements():
    s = np.tile(np.arange(100, dtype=float), (3, 1))
    f = s / 1000
    q, top, turn = al._quintiles(s, f)
    assert np.all(np.diff(q[0]) > 0) and top[0].sum() == 20
    assert turn[1] == pytest.approx(0.0)                                   # same names: nothing replaced


def test_point_in_time_values_appear_after_filing_and_lapse_when_stale():
    ev = [(pd.Timestamp("2024-02-02"), 1.0), (pd.Timestamp("2024-05-02"), 2.0)]
    dates = pd.DatetimeIndex(["2024-01-31", "2024-02-29", "2024-05-31", "2025-09-30"])
    v, _ = al._asof(ev, dates)
    assert np.isnan(v[0]) and v[1] == 1.0 and v[2] == 2.0 and np.isnan(v[3])   # nothing before filing; stale after 400 days


def test_split_factor_restates_eps_filed_before_a_split():
    splits = pd.Series({pd.Timestamp("2024-06-10"): 10.0})
    assert al._factor_after(splits, pd.Timestamp("2024-05-01")) == 10.0
    assert al._factor_after(splits, pd.Timestamp("2024-07-01")) == 1.0


def test_adaptive_composite_has_no_look_ahead():
    """Rewriting every return after month 40 must not change any weight or score up to month 40."""
    rng = np.random.default_rng(1)
    months, n = 60, 150
    f = rng.normal(size=(months, n))
    sigs = {"a": f * 0.3 + rng.normal(size=(months, n)), "b": rng.normal(size=(months, n))}

    def run(fwd):
        d = {"dates": pd.date_range("2020-01-31", periods=months, freq="ME"), "signals": sigs, "fwd": {1: fwd},
             "members": np.ones((months, n), dtype=bool)}
        ev = {k: {"_ic": al._ic_series(v, fwd)} for k, v in sigs.items()}
        return al._composite(d, ev, window=36)
    comp1, w1 = run(f)
    f2 = f.copy()
    f2[41:] = rng.normal(size=f2[41:].shape)
    comp2, w2 = run(f2)
    upto = [w for w in w1 if w["month"] <= "2023-05"]                       # month index 40
    assert upto == [w for w in w2 if w["month"] <= "2023-05"] and len(upto) > 5
    np.testing.assert_array_equal(np.nan_to_num(comp1[:41]), np.nan_to_num(comp2[:41]))


def test_verdict_never_dresses_up_a_weak_result():
    assert al._edge_verdict({"ic_t": 0.4, "excess_vs_universe_ann": -0.01})["level"] == "none"
    assert al._edge_verdict({"ic_t": 1.3, "excess_vs_universe_ann": 0.01})["level"] == "weak"
    assert al._edge_verdict({"ic_t": 2.5, "excess_vs_universe_ann": 0.02})["level"] == "significant"
