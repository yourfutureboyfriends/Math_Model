"""Quant Lab: formula safety and correctness, engine timing/costs, robustness statistics,
trial counting and the Macro Trader's order → fill cycle (all offline, synthetic data)."""
import math
import sqlite3

import numpy as np
import pandas as pd
import pytest

from api.quant import engine, expr, robust


def _frames(n=600, m=4, seed=0, drift=0.0004):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2010-01-01", periods=n)
    r = rng.normal(drift, 0.01, size=(n, m))
    close = pd.DataFrame(100 * np.cumprod(1 + r, axis=0), index=idx, columns=[f"A{i}" for i in range(m)])
    open_ = close.shift(1).fillna(close.iloc[0]) * (1 + rng.normal(0, 0.002, size=(n, m)))
    return close, open_


def _ctx(close, open_=None):
    return expr.Ctx(close, open_, close, close, close * 0 + 1e6, mkt=close.iloc[:, 0])


# ── formula language ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", [
    "__import__('os').system('ls')", "close.__class__", "close[0]", "(lambda: 1)()",
    "open('x')", "mom(252, skip=21)", "'text'", "[1, 2]", "x if 1 else 2",
])
def test_formula_rejects_code(bad):
    with pytest.raises(expr.ExprError):
        expr.parse(bad)


def test_unknown_function_suggests():
    with pytest.raises(expr.ExprError, match="Did you mean 'mom'"):
        expr.parse("momm(252)")


def test_mom_and_rank_values():
    close, _ = _frames()
    ctx = _ctx(close)
    m = expr.evaluate("mom(252, 21)", ctx)
    t = 400
    assert m.iloc[t, 1] == pytest.approx(close.iloc[t - 21, 1] / close.iloc[t - 252, 1] - 1)
    rk = expr.evaluate("rank(mom(252, 21))", ctx).iloc[t]
    assert sorted(rk.round(4)) == [0.25, 0.5, 0.75, 1.0]


def test_comparisons_and_logic_give_ones_and_zeros():
    close, _ = _frames()
    out = expr.evaluate("(close > sma(close, 50)) & (rsi(2) < 101)", _ctx(close))
    assert set(np.unique(out.to_numpy())) <= {0.0, 1.0}


def test_formula_has_no_lookahead():
    close, _ = _frames()
    t = 300
    a = expr.evaluate("zscore(close, 20) + rank(mom(126)) + rsi(14) + highest(close, 50)", _ctx(close)).iloc[: t + 1]
    future = close.copy()
    future.iloc[t + 1:] *= 3.0                                  # change only the future
    b = expr.evaluate("zscore(close, 20) + rank(mom(126)) + rsi(14) + highest(close, 50)", _ctx(future)).iloc[: t + 1]
    pd.testing.assert_frame_equal(a, b)


# ── engine ───────────────────────────────────────────────────────────────────
def _prep(spec, close, open_):
    ctx = _ctx(close, open_)
    pan = {"close": close, "open": open_, "high": close, "low": close, "volume": close * 0 + 1e6}
    return {"pan": pan, "uni": list(close.columns), "missing": [], "survivorship": False,
            "score": expr.evaluate(spec["signal"], ctx),
            "filter": expr.evaluate(spec["filter"], ctx) if spec["filter"] else None,
            "vol": expr.evaluate("vol(63)", ctx)}


def _spec(**kw):
    base = {"universe": {"symbols": ["A0"]}, "signal": "close / close", "selection": {"mode": "threshold", "min_score": 0},
            "weighting": "equal", "rebalance": "monthly", "execution": "next_close", "costs": {"bps": 0, "borrow_bps": 0},
            "start": "2010-03-01"}
    base.update(kw)
    return engine.normalize(base)


def test_buy_and_hold_matches_asset_with_zero_costs():
    close, open_ = _frames(m=1)
    spec = _spec()
    sim = engine.simulate(spec, _prep(spec, close, open_))
    r = np.array(sim["net"])
    asset = close["A0"].pct_change().reindex(pd.DatetimeIndex(sim["dates"])).to_numpy()
    # fully invested from the first day after the initial order
    assert np.allclose(r[1:], asset[1:], atol=1e-12)


def test_costs_charged_on_turnover():
    close, open_ = _frames(m=1)
    s0, s1 = _spec(), _spec(costs={"bps": 10, "borrow_bps": 0})
    a = engine.simulate(s0, _prep(s0, close, open_))
    b = engine.simulate(s1, _prep(s1, close, open_))
    # one initial buy of 100% NAV; later monthly rebalances only trim drift (zero for 1 asset)
    assert sum(b["cost"]) == pytest.approx(0.001, rel=1e-6)
    assert np.prod(1 + np.array(b["net"])) < np.prod(1 + np.array(a["net"]))


def test_engine_trades_next_bar_not_same_bar():
    close, open_ = _frames(m=2, n=400)
    spec = _spec(universe={"symbols": ["A0", "A1"]}, signal="mom(5)", selection={"mode": "top_n", "n": 1},
                 rebalance="daily")
    base = engine.simulate(spec, _prep(spec, close, open_))
    # A huge jump in A1 on day k must not be earned unless A1 was already held on day k-1
    k = 300
    c2 = close.copy()
    c2.iloc[k:, 1] *= 1.5
    o2 = open_.copy()
    o2.iloc[k:, 1] *= 1.5
    alt = engine.simulate(spec, _prep(spec, c2, o2))
    d = sim_dates_index = base["dates"]
    i = d.index(close.index[k].strftime("%Y-%m-%d"))
    assert np.allclose(base["net"][:i], alt["net"][:i])


def test_long_short_is_dollar_neutral_and_fallback_used():
    close, open_ = _frames(m=6)
    spec = _spec(universe={"symbols": list(close.columns)}, signal="mom(60)",
                 selection={"mode": "long_short", "n": 2, "long_only": False}, weighting="equal")
    w = engine.target_weights(spec, np.array([5, 4, 3, 2, 1, 0.0]), np.ones(6, bool), np.full(6, 0.2), 6)
    assert w.sum() == pytest.approx(0) and np.abs(w).sum() == pytest.approx(1)
    spec_fb = _spec(universe={"symbols": ["A0", "A1"]}, signal="mom(20)", selection={"mode": "top_n", "n": 1, "min_score": 10},
                    fallback="A2")
    close3, open3 = close[["A0", "A1", "A2"]], open_[["A0", "A1", "A2"]]
    prep = _prep(spec_fb, close3[["A0", "A1"]], open3[["A0", "A1"]])
    prep["pan"] = {"close": close3, "open": open3, "high": close3, "low": close3, "volume": close3 * 0}
    sim = engine.simulate(spec_fb, prep)
    assert sim["today"][sim["cols"].index("A2")] == pytest.approx(1.0)      # nothing qualifies → fallback


def test_spec_validation_messages():
    with pytest.raises(engine.SpecError, match="signal"):
        engine.normalize({"universe": {"preset": "cross_asset"}, "signal": ""})
    with pytest.raises(engine.SpecError, match="Unknown function"):
        engine.normalize({"universe": {"preset": "cross_asset"}, "signal": "foo(1)"})
    with pytest.raises(engine.SpecError, match="Invalid ticker"):
        engine.normalize({"universe": {"symbols": ["SPY", "BAD TICKER!"]}, "signal": "mom(20)"})


# ── robustness ───────────────────────────────────────────────────────────────
def test_pbo_high_for_pure_noise_variants():
    rng = np.random.default_rng(3)
    noise = rng.normal(0, 0.01, size=(2000, 20))
    assert robust.pbo_cscv(noise)["pbo"] > 0.3


def test_pbo_low_when_one_variant_is_genuinely_better():
    rng = np.random.default_rng(4)
    m = rng.normal(0, 0.01, size=(2000, 10))
    m[:, 0] += 0.002
    assert robust.pbo_cscv(m)["pbo"] < 0.1


def test_deflated_sharpe_falls_with_more_trials():
    rng = np.random.default_rng(5)
    r = rng.normal(0.0004, 0.01, 2500)
    one = robust.deflated_sharpe(r, 1)["dsr"]
    many = robust.deflated_sharpe(r, 100)["dsr"]
    assert many < one


def test_bootstrap_and_metrics_shapes():
    rng = np.random.default_rng(6)
    r = rng.normal(0.0005, 0.01, 1500)
    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2015-01-01", periods=1500)]
    b = robust.block_bootstrap(r)
    assert b["sharpe_p05"] < b["sharpe_p95"]
    m = robust.metrics(r, dates)
    assert m["max_drawdown"] <= 0 and m["t_stat"] is not None
    v = robust.verdict({"metrics": {"t_stat": 2.5, "sharpe": 0.8, "years": 6}, "robustness": {
        "deflated_sharpe": {"dsr": 0.97, "trials": 1}, "is_oos": {"is_sharpe": 0.8, "oos_sharpe": 0.7, "decay": 0.1, "split_date": "x"},
        "bootstrap": {"sharpe_p05": 0.1, "sharpe_p95": 1.2}}})
    assert v["grade"] == "mixed"                          # t < 3 caps the grade


# ── persistence: trial counting ──────────────────────────────────────────────
def test_trials_count_distinct_variants(tmp_path, monkeypatch):
    from api.quant import store
    db = tmp_path / "q.db"

    def conn():
        c = sqlite3.connect(db)
        c.row_factory = sqlite3.Row
        return c
    monkeypatch.setattr(store, "_conn", conn)
    monkeypatch.setattr(store, "_ready", False)
    assert store.trials("u", None, "h1")[0] == 1
    store.record_run("u", None, "h1", 0.5)
    store.record_run("u", None, "h1", 0.5)                # same variant twice counts once
    store.record_run("u", None, "h2", 0.7)
    assert store.trials("u", None, "h3")[0] == 3
    assert store.trials("u", None, "h2")[0] == 2
    assert store.trials("other", None, "h1")[0] == 1


# ── Macro Trader cycle ───────────────────────────────────────────────────────
def test_macro_trader_orders_then_fills_at_next_open(tmp_path, monkeypatch):
    from api import macro_trader as mt
    db = tmp_path / "m.db"

    def conn():
        c = sqlite3.connect(db)
        c.row_factory = sqlite3.Row
        return c
    monkeypatch.setattr(mt, "_conn", conn)
    monkeypatch.setattr(mt, "_ready", False)
    idx = pd.bdate_range("2026-01-05", periods=3)

    def bars(upto):
        out = {}
        for sym, p in (("SPY", 100.0), ("IEF", 50.0)):
            df = pd.DataFrame({"Open": [p, p * 1.01, p * 1.02], "High": p, "Low": p, "Close": [p, p * 1.01, p * 1.02],
                               "Volume": 1.0}, index=idx)
            out[sym] = df.iloc[:upto]
        return out
    s = {**mt.DEFAULTS, "cost_bps": 10.0}
    tg = {"weights": {"SPY": 0.6, "IEF": 0.3}, "regime": "Goldilocks"}
    r1 = mt._cycle(s, tg, bars(1))
    assert r1["orders"] == 2 and r1["filled"] == 0
    r2 = mt._cycle(s, tg, bars(2))
    assert r2["filled"] == 2
    with conn() as c:
        pos = {r["symbol"]: r["shares"] for r in c.execute("SELECT * FROM macro_trader_positions")}
        fills = c.execute("SELECT fill_price, fill_date FROM macro_trader_orders WHERE symbol='SPY'").fetchone()
    assert pos["SPY"] == pytest.approx(6000, rel=1e-6)          # 60% of $1m at the order's close price
    assert fills["fill_price"] == pytest.approx(101.0) and fills["fill_date"] == idx[1].strftime("%Y-%m-%d")
