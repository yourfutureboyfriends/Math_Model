"""TECH / SPRD maths on synthetic data (offline)."""
import numpy as np
import pandas as pd
import pytest

from api.marketdata import core, toolkit as T


def test_rsi_bounds_and_extremes():
    up = pd.Series(np.arange(1, 60, dtype=float))
    assert T._rsi(up).iloc[-1] == pytest.approx(100)
    dn = pd.Series(np.arange(60, 1, -1, dtype=float))
    assert T._rsi(dn).iloc[-1] < 1
    rnd = pd.Series(100 + np.cumsum(np.random.default_rng(0).normal(size=500)))
    r = T._rsi(rnd)
    assert ((r >= 0) & (r <= 100)).all()


def test_signal_stats_counts_each_episode_once():
    idx = pd.bdate_range("2020-01-01", periods=300)
    c = pd.Series(np.linspace(100, 130, 300), index=idx)
    mask = pd.Series(False, index=idx)
    mask.iloc[[10, 12, 15, 100]] = True                         # 10/12/15 are one episode
    s = T._signal_stats(c, mask)
    assert s["count"] == 2
    assert s["hit_20d"] == 1.0 and s["avg_20d"] > 0


def _fake_hist(series_by_symbol, monkeypatch):
    def h(sym, period="10y"):
        return pd.DataFrame({"Close": series_by_symbol[sym]})
    monkeypatch.setattr(T, "_history", h)
    monkeypatch.setattr(T, "_info", lambda s: {"shortName": s, "currency": "USD"})


def test_spread_detects_cointegration(monkeypatch):
    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2019-01-01", periods=1300)
    b = np.exp(np.cumsum(rng.normal(0, 0.01, len(idx))) + 4)
    noise = np.zeros(len(idx))
    for i in range(1, len(idx)):                                  # stationary AR(1) spread, half-life ~ 7 days
        noise[i] = 0.9 * noise[i - 1] + rng.normal(0, 0.01)
    a = np.exp(1.5 * np.log(b) + noise - 2)
    _fake_hist({"AAA": pd.Series(a, index=idx), "BBB": pd.Series(b, index=idx)}, monkeypatch)
    core._cache.pop("sprd:AAA:BBB:5:2.0:0.5", None)
    out = T.spread("AAA", "BBB", 5)
    assert out["hedge_ratio"] == pytest.approx(1.5, abs=0.05)
    assert out["coint_p"] < 0.05 and "cointegrated" in out["verdict"]
    assert 3 < out["half_life_days"] < 15
    assert out["backtest"]["trades"] > 0


def test_spread_flags_random_walks(monkeypatch):
    rng = np.random.default_rng(2)
    idx = pd.bdate_range("2019-01-01", periods=1300)
    a = np.exp(np.cumsum(rng.normal(0, 0.01, len(idx))) + 4)
    b = np.exp(np.cumsum(rng.normal(0, 0.01, len(idx))) + 4)
    _fake_hist({"CCC": pd.Series(a, index=idx), "DDD": pd.Series(b, index=idx)}, monkeypatch)
    core._cache.pop("sprd:CCC:DDD:5:2.0:0.5", None)
    out = T.spread("CCC", "DDD", 5)
    assert out["coint_p"] > 0.05 and out["verdict"].startswith(("not", "weak"))


def test_same_symbol_rejected():
    with pytest.raises(T.NotFound):
        T.spread("AAPL", "aapl")
