"""Technical snapshot: formulas checked on constructed series with known answers."""
import numpy as np
import pandas as pd
import pytest

from api.calculations import technicals as t


def _bars(close, high=None, low=None, volume=None):
    idx = pd.bdate_range("2024-01-01", periods=len(close))
    c = pd.Series(close, index=idx, dtype=float)
    return pd.DataFrame({"open": c, "high": high if high is not None else c, "low": low if low is not None else c,
                         "close": c, "volume": volume if volume is not None else 1000.0}, index=idx)


def test_rsi_extremes_and_balance():
    up = pd.Series(np.arange(1, 60, dtype=float))
    assert t.rsi(up) == 100.0                                    # only gains
    down = pd.Series(np.arange(60, 1, -1, dtype=float))
    assert t.rsi(down) == pytest.approx(0.0, abs=1e-9)           # only losses
    zig = pd.Series([10, 11] * 40, dtype=float)
    assert t.rsi(zig) == pytest.approx(50.0, abs=5)              # equal gains and losses


def test_atr_constant_range():
    n = 60
    c = np.full(n, 100.0)
    a = t.atr(pd.Series(c + 1), pd.Series(c - 1), pd.Series(c))
    assert a == pytest.approx(2.0)                               # high − low every day


def test_snapshot_moving_averages_bollinger_and_drawdown():
    c = np.r_[np.linspace(100, 200, 250), np.linspace(200, 150, 50)]
    s = t.snapshot(_bars(c))
    assert s["sma20"] == pytest.approx(c[-20:].mean()) and s["sma200"] == pytest.approx(c[-200:].mean())
    assert s["vs_sma50"] == pytest.approx(c[-1] / c[-50:].mean() - 1, abs=1e-4)
    b = s["bollinger"]
    assert b["middle"] == pytest.approx(c[-20:].mean()) and b["upper"] - b["middle"] == pytest.approx(2 * c[-20:].std(), abs=1e-3)
    assert s["max_drawdown_1y"] == pytest.approx(150 / 200 - 1, abs=1e-6)
    assert s["levels"]["high52w"] == pytest.approx(200.0, abs=0.5)
    assert s["macd"]["state"] == "below signal"                  # falling: MACD under its signal


def test_volume_spike_and_relative_strength():
    vol = np.full(100, 1000.0)
    vol[-1] = 5000.0
    vol[:-1] += np.random.default_rng(1).normal(0, 50, 99)
    c = np.linspace(100, 130, 100)
    bars = _bars(c, volume=vol)
    bench = pd.Series(np.linspace(100, 110, 100), index=bars.index)
    s = t.snapshot(bars, bench, bars["close"])
    assert s["unusual_volume"] and s["volume_z"] > 10
    rs3 = s["relative_strength_vs_benchmark"]["3m"]
    i0 = bars.index.searchsorted(bars.index[-1] - pd.Timedelta(days=92))
    assert rs3 == pytest.approx(c[-1] / c[i0] - bench.iloc[-1] / bench.iloc[i0], abs=1e-4)


def test_short_history_is_unavailable_not_invented():
    assert t.snapshot(_bars(np.linspace(1, 2, 10)))["available"] is False
