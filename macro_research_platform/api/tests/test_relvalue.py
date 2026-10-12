"""Stat arb, pairs trading and the market-making simulator — offline, on synthetic data with known structure."""
import numpy as np
import pandas as pd
import pytest

from api.quant import expr, mm, pairs
from api.tests.test_quant_api import client  # noqa: F401 — fixture


def _ou_universe(n=1200, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    rm = rng.normal(0, 0.01, n)
    m = pd.Series(100 * np.cumprod(1 + rm), index=idx)
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = 0.85 * x[t - 1] + rng.normal(0, 0.01)
    ou = 50 * np.cumprod(1 + 1.2 * rm + np.diff(np.r_[0, x]))
    rw = 30 * np.cumprod(1 + rm + rng.normal(0, 0.01, n))
    return pd.DataFrame({"OU": ou, "RW": rw}, index=idx), m, x


def _ou_panel(n=1200, k=10, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    rm = rng.normal(0, 0.01, n)
    x = np.zeros((n, k))
    for t in range(1, n):
        x[t] = 0.85 * x[t - 1] + rng.normal(0, 0.01, k)
    r = rm[:, None] * rng.uniform(0.8, 1.3, k) + np.diff(np.vstack([np.zeros(k), x]), axis=0)
    close = pd.DataFrame(50 * np.cumprod(1 + r, axis=0), index=idx, columns=[f"S{i}" for i in range(k)])
    return close, pd.Series(100 * np.cumprod(1 + rm), index=idx), pd.DataFrame(x, index=idx, columns=close.columns)


def test_sscore_tracks_and_predicts_mean_reverting_residuals():
    # A–L centre the s-score across the universe, so test on a universe, not a single stock.
    close, m, x = _ou_panel()
    s = expr.evaluate("sscore(60)", expr.Ctx(close, mkt=m))
    assert s.notna().mean().mean() > 0.8
    assert np.mean([s[c].corr(x[c]) for c in close]) > 0.4
    fwd = x.shift(-5) - x                                          # the residual's next-week move
    assert np.mean([s[c].corr(fwd[c]) for c in close]) < -0.15    # high s-score → residual falls
    assert s.iloc[:60].isna().all().all()                         # needs a full window


def test_sscore_has_no_lookahead():
    close, m, _ = _ou_universe()
    full = expr.evaluate("sscore(60)", expr.Ctx(close, mkt=m))
    cut = expr.evaluate("sscore(60)", expr.Ctx(close.iloc[:700], mkt=m.iloc[:700]))
    pd.testing.assert_frame_equal(full.iloc[:700], cut)


def test_resid_removes_market_beta():
    close, m, _ = _ou_universe()
    e = expr.evaluate("resid(252)", expr.Ctx(close, mkt=m)).iloc[300:]
    mr = m.pct_change().iloc[300:]
    assert abs(e["RW"].corr(mr)) < 0.1


def _cointegrated(n=1500, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2012-01-01", periods=n)
    lb = np.cumsum(rng.normal(0, 0.012, n)) + 4
    sp = np.zeros(n)
    for t in range(1, n):
        sp[t] = 0.93 * sp[t - 1] + rng.normal(0, 0.01)
    la = 0.5 + 0.9 * lb + sp
    lc = np.cumsum(rng.normal(0, 0.012, n)) + 4                   # unrelated random walk
    return pd.DataFrame({"AAA": np.exp(la), "BBB": np.exp(lb), "CCC": np.exp(lc)}, index=idx)


def test_pairs_scan_finds_the_cointegrated_pair(monkeypatch):
    df = _cointegrated()
    monkeypatch.setattr(pairs, "_closes", lambda syms, start=None: df[list(syms)])
    r = pairs.scan(["AAA", "BBB", "CCC"], years=3, min_corr=0.0)
    top = r["pairs"][0]
    assert {top["a"], top["b"]} == {"AAA", "BBB"} and top["p_value"] < 0.01
    assert 5 <= top["half_life_days"] <= 20                       # true half-life ln2/−ln0.93 ≈ 9.6
    assert r["pairs_tested"] >= 2


def test_pairs_backtest_profits_on_a_true_pair_and_trades_next_day(monkeypatch):
    df = _cointegrated()
    monkeypatch.setattr(pairs, "_closes", lambda syms, start=None: df[list(syms)])
    r = pairs.backtest("AAA", "BBB", lookback=252, bps=1)
    assert r["metrics"]["sharpe"] > 1 and r["metrics"]["trades"] > 10
    # Hedge ratio near the true 0.9 and the position never uses same-day information.
    assert 0.7 < r["hedge_ratio_now"] < 1.1
    with pytest.raises(pairs.PairsError):
        pairs.backtest("AAA", "BBB", entry=0.5, exit=1.0)


def _bars(n_days=5, per_day=390, seed=2):
    rng = np.random.default_rng(seed)
    idx = []
    for d in pd.bdate_range("2026-09-01", periods=n_days):
        idx += list(pd.date_range(d + pd.Timedelta(hours=9, minutes=30), periods=per_day, freq="1min"))
    c = 100 + np.cumsum(rng.normal(0, 0.02, len(idx)))
    o = np.r_[c[0], c[:-1]]
    hi = np.maximum(o, c) + np.abs(rng.normal(0, 0.02, len(idx)))
    lo = np.minimum(o, c) - np.abs(rng.normal(0, 0.02, len(idx)))
    return pd.DataFrame({"Open": o, "High": hi, "Low": lo, "Close": c, "Volume": 1e4}, index=pd.DatetimeIndex(idx))


def test_market_maker_accounting_and_inventory_control(monkeypatch):
    df = _bars()
    monkeypatch.setattr(mm, "_bars", lambda s, i: df)
    r = mm.simulate("TEST", half_spread_bps=2, max_inventory=5, rebate_per_share=0.002)
    for run in r["runs"].values():
        parts = run["spread_capture"] + run["inventory_pnl"] + run["rebates"] - run["flatten_cost"]
        assert abs(parts - run["total_pnl"]) < 0.05
        assert run["max_abs_inventory"] <= 5 and run["days"] == 5
        assert abs(sum(d["pnl"] for d in run["by_day"]) - run["total_pnl"]) < 0.05
    assert r["runs"]["avellaneda_stoikov"]["avg_abs_inventory"] <= r["runs"]["symmetric"]["avg_abs_inventory"]


def test_relvalue_endpoints_require_sign_in_and_work(client, monkeypatch):  # noqa: F811
    df = _cointegrated()
    monkeypatch.setattr(pairs, "_closes", lambda syms, start=None: df[[s for s in syms if s in df]])
    monkeypatch.setattr(mm, "_bars", lambda s, i: _bars(3))
    r = client.get("/api/v1/quant/pairs/scan", params={"symbols": "AAA,BBB,CCC", "years": 3, "min_corr": 0})
    assert r.status_code == 200 and r.json()["pairs"]
    assert client.get("/api/v1/quant/pairs/backtest", params={"a": "AAA", "b": "BBB"}).status_code == 200
    assert client.get("/api/v1/quant/pairs/backtest", params={"a": "AAA", "b": "BBB", "entry": 0.1}).status_code == 400
    assert client.get("/api/v1/quant/mm", params={"symbol": "TEST"}).status_code == 200
    assert client.get("/api/v1/quant/mm", params={"symbol": "TEST", "interval": "1d"}).status_code == 422
    client.headers.pop("Authorization")
    assert client.get("/api/v1/quant/mm", params={"symbol": "TEST"}).status_code == 401
