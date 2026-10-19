"""Parity of the QuantConnect-style indicators (api/quant/qcalgo.py) with LEAN's own reference values.

Data: QuantConnect LEAN's Tests/TestData files (Apache License 2.0, github.com/QuantConnect/Lean), copied unchanged to
api/tests/data/lean/. The same files and columns LEAN's indicator tests use; values compared once LEAN reports them.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from api.quant import qcalgo as q

D = Path(__file__).parent / "data" / "lean"


def _bars(df):
    for i, r in enumerate(df.itertuples()):
        o = getattr(r, "Open", r.Close)
        yield q.TradeBar(q.Symbol("SPY"), i, o, getattr(r, "High", r.Close), getattr(r, "Low", r.Close), r.Close, 0.0)


def _run(ind, df, col, bars=False, attr=None, scale=1.0):
    ref = pd.to_numeric(df[col], errors="coerce").to_numpy()
    ours = []
    for b in _bars(df):
        ind.update(b) if bars else ind.update(b.time, b.close)
        ours.append((getattr(ind, attr).value if attr else ind.current.value) * scale if ind.is_ready else np.nan)
    ours = np.array(ours)
    ok = np.isfinite(ref) & np.isfinite(ours)
    assert ok.sum() > 100
    return np.abs(ours[ok] - ref[ok]), np.abs(ref[ok])


CASES = [
    ("spy_with_indicators.txt", "SMA14", lambda: q.SimpleMovingAverage(14), {}),
    ("spy_with_indicators.txt", "EMA14", lambda: q.ExponentialMovingAverage(14), {}),
    ("spy_ema.csv", "EMA14", lambda: q.ExponentialMovingAverage(14), {}),
    ("spy_with_indicators.txt", "RSI 14 Wilder", lambda: q.RelativeStrengthIndex(14, q.MovingAverageType.WILDERS), {}),
    ("spy_with_indicators.txt", "RSI 14", lambda: q.RelativeStrengthIndex(14, q.MovingAverageType.SIMPLE), {}),
    ("spy_atr_wilder.txt", "Average True Range 14", lambda: q.AverageTrueRange(14), {"bars": True}),
    ("spy_bollinger_bands.txt", "Moving Average 20", lambda: q.BollingerBands(20, 2), {}),
    ("spy_bollinger_bands.txt", "Bollinger Bands® 20 2 Top", lambda: q.BollingerBands(20, 2), {"attr": "upper_band"}),
    ("spy_bollinger_bands.txt", "Bollinger Bands® 20 2 Bottom", lambda: q.BollingerBands(20, 2), {"attr": "lower_band"}),
    ("spy_with_macd.txt", "MACD", lambda: q.MovingAverageConvergenceDivergence(12, 26, 9), {}),
    ("spy_with_macd.txt", "Signal", lambda: q.MovingAverageConvergenceDivergence(12, 26, 9), {"attr": "signal"}),
    ("spy_with_adx.txt", "ADX 14", lambda: q.AverageDirectionalIndex(14), {"bars": True}),
    ("spy_with_rocp50.txt", "Rate of Change % 50", lambda: q.RateOfChangePercent(50), {}),
    ("spy_with_rocp50.txt", "Rate of Change % 50", lambda: q.RateOfChange(50), {"scale": 100.0}),   # LEAN's own ROC test
    ("spy_max.txt", "MAX_5", lambda: q.Maximum(5), {}),
    ("spy_min.txt", "MIN_5", lambda: q.Minimum(5), {}),
]


@pytest.mark.parametrize("fname,col,make,kw", CASES, ids=[f"{c[0]}:{c[1]}" for c in CASES])
def test_matches_lean_reference(fname, col, make, kw):
    df = pd.read_csv(D / fname)
    if "Close" not in df and "close" in df:
        df["Close"] = df["close"]
    err, ref = _run(make(), df, col, **kw)
    # LEAN's tests compare to 1e-3 absolute on the file's rounded values; we hold 1e-4 relative or 1e-3 absolute
    assert np.all((err <= 1e-3) | (err <= 1e-4 * ref)), f"max abs error {err.max():.2e}"
