"""
Regression tests for the model-review fixes (growth signal, zero handling, regime
ordering, recession model, probit CI recursion).
Run: pytest api/tests/test_signal_fixes.py
"""
import math

import pytest

from api.calculations.signals import (
    calculate_growth_signal, calculate_inflation_signal,
    calculate_liquidity_signal, calculate_risk_signal,
)
from api.calculations.regime import classify_regime
from api.calculations.metrics import calculate_recession_probability
from api.calculations.models import estrella_mishkin_recession_prob


def _path(daily_ret, n=260, start=5000.0):
    return [start * (1 + daily_ret) ** i for i in range(n)]


# ── Growth signal ────────────────────────────────────────────────────────────
def test_growth_depends_on_the_market_not_the_level():
    up = calculate_growth_signal(None, _path(0.001))[0]
    down = calculate_growth_signal(None, _path(-0.001))[0]
    flat = calculate_growth_signal(None, _path(0.0))[0]
    assert up > flat > down
    # Same returns at a different price level -> same score (scale invariant)
    assert calculate_growth_signal(None, _path(0.001, start=3000))[0] == up


def test_growth_trend_direction_is_not_inverted():
    # Accelerating rally: flat for 200 days then rising -> improving
    accel = _path(0.0, 200) + _path(0.001, 60, start=5000)[1:]
    assert calculate_growth_signal(None, accel)[1] == "improving"
    # Rally that rolls over -> deteriorating
    roll = _path(0.001, 200) + [5000 * 1.001 ** 199 * (1 - 0.001) ** i for i in range(1, 60)]
    assert calculate_growth_signal(None, roll)[1] == "deteriorating"


def test_growth_unavailable_on_short_history():
    assert calculate_growth_signal(5800, [5700, 5750]) == (None, "unavailable", [])


def test_growth_history_is_real_and_ends_at_now():
    closes = _path(0.001)
    score, _, hist = calculate_growth_signal(None, closes)
    assert len(hist) == 5 and hist[-1] == score


# ── Zero / missing handling ──────────────────────────────────────────────────
def test_zero_fed_funds_is_valid_and_loosest():
    zirp = calculate_liquidity_signal(100, 1.0, 0.0)[0]
    tiny = calculate_liquidity_signal(100, 1.0, 0.0001)[0]
    assert zirp == pytest.approx(tiny, abs=0.01)


def test_missing_inputs_return_unavailable():
    assert calculate_inflation_signal(None, None)[0] is None
    # one component alone is enough
    assert calculate_inflation_signal(3.0, None)[0] == 0.5
    assert calculate_liquidity_signal(104, 4.5, None)[0] is None
    assert calculate_risk_signal(None)[0] is None


def test_scalar_signals_do_not_fabricate_history():
    for _, _, hist in (calculate_inflation_signal(3.0, 2.3),
                       calculate_liquidity_signal(100, 4.5, 4.0),
                       calculate_risk_signal(18.0)):
        assert len(hist) == 1


# ── Regime ordering ──────────────────────────────────────────────────────────
def test_strong_growth_tight_liquidity_is_not_contraction():
    assert classify_regime(0.9, 0.2, 0.1)[0] == "expansion"


def test_weak_growth_tight_liquidity_mid_inflation_is_contraction():
    assert classify_regime(0.45, 0.5, 0.1)[0] == "contraction"


def test_midpoint_growth_low_inflation_is_goldilocks():
    assert classify_regime(0.5, 0.45, 0.5)[0] == "goldilocks"


def test_duration_respects_cap():
    _, conf, dur = classify_regime(1.0, 0.0, 1.0)
    assert conf <= 0.95 and dur <= 24


# ── Recession model ──────────────────────────────────────────────────────────
def test_recession_uses_estrella_mishkin():
    r = calculate_recession_probability(-0.66)
    assert r["emProbitProb"] == pytest.approx(estrella_mishkin_recession_prob(-0.66), abs=1e-4)
    assert r["probability"] == r["emProbitProb"]
    assert r["logisticProb"] is None          # no fitted model supplied


def test_recession_prefers_fitted_probit_when_available():
    r = calculate_recession_probability(1.0, fed_funds=4.0, fitted_probit_prob=0.22)
    assert r["probability"] == 0.22 and r["level"] == "Moderate"


def test_recession_monotonic_in_spread():
    probs = [calculate_recession_probability(s)["probability"] for s in (2.0, 1.0, 0.0, -1.0)]
    assert probs == sorted(probs)


def test_sahm_rule_is_real_value_with_half_point_threshold():
    assert calculate_recession_probability(1.0, sahm_value=0.53)["sahmSignal"] == "Signal"
    assert calculate_recession_probability(1.0, sahm_value=0.20)["sahmSignal"] == "No Signal"
    assert calculate_recession_probability(1.0)["sahmValue"] is None


def test_recession_unavailable_without_spread():
    r = calculate_recession_probability(None)
    assert r["probability"] is None and r["level"] == "Unavailable"


# ── Probit CI must not recurse ───────────────────────────────────────────────
def test_probit_ci_failure_does_not_recurse():
    from api.models_ml.recession_probit import RecessionProbitModel

    class Broken:
        def cov_params(self):
            raise RuntimeError("boom")

    m = RecessionProbitModel()
    m.result = Broken()
    lo, hi = m._bootstrap_ci(1.0, 4.0)
    assert math.isnan(lo) and math.isnan(hi)


# ── Sector allocation sums to 100% ───────────────────────────────────────────
def test_sector_allocations_sum_to_one_and_have_no_bonds():
    from api.calculations.metrics import calculate_sector_allocation
    for regime in ("goldilocks", "reflation", "stagflation", "slowdown",
                   "contraction", "expansion", "recovery"):
        secs = calculate_sector_allocation(regime, 0.5, 0.5)["sectors"]
        assert abs(sum(s["allocation"] for s in secs) - 1.0) < 0.03   # rounding to 2dp
        assert all(s["name"] != "Bonds" for s in secs)


def test_sector_allocation_zero_growth_is_not_defaulted():
    from api.calculations.metrics import calculate_sector_allocation
    lo = calculate_sector_allocation("slowdown", 0.0, 0.9)["confidence"]
    mid = calculate_sector_allocation("slowdown", 0.5, 0.9)["confidence"]
    assert lo > mid       # |growth - inflation| is larger at growth=0


# ── Sortino uses downside deviation over all periods ─────────────────────────
def test_sortino_downside_deviation():
    import numpy as np
    from api.calculations.risk_parity import performance_stats
    r = np.array([0.01, -0.01, 0.02, -0.02, 0.01])
    dd = np.sqrt(np.mean(np.minimum(r, 0) ** 2))
    expected = round(r.mean() * 252 / (dd * np.sqrt(252)), 2)
    assert performance_stats(r)["sortino"] == expected
    assert performance_stats(np.array([0.01, 0.02, 0.0]))["sortino"] is None


# ── Walk-forward risk parity has no look-ahead ───────────────────────────────
def test_walk_forward_uses_only_trailing_data():
    import numpy as np
    from api.calculations.risk_parity import walk_forward_returns
    rng = np.random.default_rng(0)
    rets = rng.normal(0, 0.01, (300, 3))
    seen_ends = []

    def fn(window):
        seen_ends.append(window[-1].copy())
        return np.ones(3) / 3

    oos, w = walk_forward_returns(rets, fn, lookback=100, rebalance=50)
    assert oos.size == 200 and len(seen_ends) == 4
    # each estimation window ends the day BEFORE the first day it is applied to
    for k, end in enumerate(seen_ends):
        assert np.array_equal(end, rets[100 + 50 * k - 1])
    assert np.allclose(oos, rets[100:].mean(axis=1))


# ── Signal backtest reports independent (non-overlapping) evidence ──────────
def test_backtest_independent_hit_rate():
    import numpy as np
    from api.calculations.backtest import backtest_signal
    closes = 100 * np.cumprod(1 + np.full(400, 0.001))   # always up
    out = backtest_signal(closes, ["BULLISH"] * 400, horizon=21)
    assert out["observations"] == 379
    assert out["independent_observations"] == 19
    assert out["hit_rate_independent"] == 1.0
    assert out["hit_rate_p_value"] < 0.001


# ── HMM: per-axis states recover all four quadrants ─────────────────────────
def test_hmm_recovers_all_quadrants_on_synthetic_regimes():
    import numpy as np
    import pandas as pd
    from api.models_ml.regime_hmm import MacroRegimeHMM
    rng = np.random.default_rng(1)
    blocks = [(+1, -1, "Goldilocks"), (+1, +1, "Reflation"),
              (-1, +1, "Stagflation"), (-1, -1, "Slowdown")] * 3
    rows, truth = [], []
    for g, i, name in blocks:
        for _ in range(30):
            rows.append((g * 1.5 + rng.normal(0, 0.4), i * 1.5 + rng.normal(0, 0.4)))
            truth.append(name)
    df = pd.DataFrame(rows, columns=["growth_z", "inflation_z"])
    df.insert(0, "date", pd.date_range("1990-01-01", periods=len(df), freq="MS"))
    m = MacroRegimeHMM()
    m.fit(df)
    seq = [s["regime"] for s in m.get_historical_sequence(df)]
    assert set(seq) == {"Goldilocks", "Reflation", "Stagflation", "Slowdown"}
    assert np.mean([a == b for a, b in zip(seq, truth)]) > 0.9
    cur = m.predict_current()
    assert cur["regime"] == "Slowdown"
    assert abs(sum(cur["regime_probabilities"].values()) - 1) < 1e-6


def test_hmm_drops_rows_with_missing_features_instead_of_zero_filling():
    import numpy as np
    import pandas as pd
    from api.models_ml.regime_hmm import MacroRegimeHMM
    rng = np.random.default_rng(2)
    df = pd.DataFrame({"date": pd.date_range("2000-01-01", periods=120, freq="MS"),
                       "growth_z": rng.normal(size=120), "inflation_z": rng.normal(size=120)})
    df.loc[10, "inflation_z"] = np.nan
    m = MacroRegimeHMM()
    assert m.fit(df)["n_samples"] == 119
    dates = [s["date"] for s in m.get_historical_sequence(df)]
    assert "2000-11-01" not in dates and len(dates) == 119


# ── CPI is only visible after its release date (no look-ahead) ───────────────
def test_cpi_release_series_has_no_lookahead():
    import pandas as pd
    from api.handlers.macro_inputs import cpi_release_series
    panel = pd.DataFrame({"cpi_yoy": [3.0, 3.5]},
                         index=pd.to_datetime(["2026-07-01", "2026-08-01"]))
    s = cpi_release_series(panel)
    assert s.asof("2026-08-31") == 3.0      # July CPI out mid-Aug; Aug CPI not yet
    assert s.asof("2026-09-15") == 3.5      # Aug CPI published ~mid-Sep
    assert s.asof("2026-08-10") is None     # nothing published yet


# ── Monthly quadrant regime history ──────────────────────────────────────────
def test_quadrant_history_is_contiguous_and_unpadded():
    import numpy as np
    import pandas as pd
    from api.calculations.regime import quadrant_regime_history, current_run_length
    idx = pd.date_range("2000-01-01", periods=120, freq="MS")
    t = np.arange(120)
    g = pd.Series(np.sin(t / 6.0), index=idx)
    i = pd.Series(np.cos(t / 9.0), index=idx)
    i.iloc[60] = np.nan                                   # an unpublished month
    h = quadrant_regime_history(g, i)
    assert idx[60] not in h.index                         # gap kept as a gap, not filled
    assert h.index[0] >= idx[23]                          # needs 24 months for a z-score
    assert set(h["regime"]) <= {"Goldilocks", "Reflation", "Slowdown", "Stagflation"}
    assert h["confidence"].between(0.5, 0.95).all()
    assert current_run_length(["A", "B", "B", "B"]) == 3 and current_run_length([]) == 0


def test_quadrant_history_uses_signs_symmetrically():
    import pandas as pd
    from api.calculations.regime import quadrant_regime_history
    idx = pd.date_range("2000-01-01", periods=40, freq="MS")
    g = pd.Series([0.0] * 39 + [5.0], index=idx)          # growth spikes up
    i = pd.Series([0.0] * 39 + [-5.0], index=idx)         # inflation drops
    assert quadrant_regime_history(g, i)["regime"].iloc[-1] == "Goldilocks"
