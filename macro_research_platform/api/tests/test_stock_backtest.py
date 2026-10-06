"""Stock entry-model backtest: exits, no look-ahead, one trade at a time, sizing, hygiene."""
import numpy as np

from api.calculations import stock_backtest as bt
from api.calculations.stock_timing import signal_frame


def _series(n=700, drift=0.0008, vol=0.012, seed=1):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(drift + vol * rng.standard_normal(n)))
    o = c * (1 + 0.002 * rng.standard_normal(n))
    h = np.maximum(o, c) * (1 + np.abs(0.006 * rng.standard_normal(n)))
    l = np.minimum(o, c) * (1 - np.abs(0.006 * rng.standard_normal(n)))
    dates = [f"D{k:05d}" for k in range(n)]
    return dates, o, h, l, c


def test_exit_rules():
    o = np.array([100, 100, 100, 100.0]); c = o.copy()
    h = np.array([101, 101, 111, 101.0]); l = np.array([99, 99, 99, 99.0])
    assert bt._exit(o, h, l, c, 1, 95, 110, 63)[1:] == (110, "target")
    l2 = l.copy(); l2[2] = 94
    assert bt._exit(o, h, l2, c, 1, 95, 110, 63)[1:] == (95, "stop")        # stop and target same day → stop
    o3 = o.copy(); o3[2] = 90
    assert bt._exit(o3, h, l, c, 1, 95, 110, 63)[1:] == (90, "stop")       # gap through the stop fills at the open
    j, px, why = bt._exit(o, np.full(4, 101.0), l, c, 1, 95, 110, 2)
    assert (j, why) == (2, "time")


def test_signal_frame_has_no_lookahead():
    _, o, h, l, c = _series()
    full = signal_frame(c, h, l)
    for i in (300, 450, 699):
        part = signal_frame(c[: i + 1], h[: i + 1], l[: i + 1])
        assert np.allclose(full.iloc[i].to_numpy(), part.iloc[i].to_numpy(), equal_nan=True)


def test_trades_are_sequential_and_after_warmup():
    dates, o, h, l, c = _series(n=1200)
    trades = bt.simulate("X", dates, o, h, l, c)
    assert trades, "an up-trending series should produce signals"
    for v in bt.VARIANTS:
        ts = sorted((t for t in trades if t.variant == v), key=lambda t: t.entry_i)
        assert all(t.entry_i > bt.WARMUP for t in ts)
        for a, b in zip(ts, ts[1:]):
            assert b.entry_i > a.exit_i, "one position per stock at a time"
        for t in ts:
            assert t.stop < t.entry < t.target
            assert abs((t.target - t.entry) / (t.entry - t.stop) - bt.TARGET_R) < 1e-9


def test_stop_out_costs_one_r_plus_costs():
    t = bt.Trade("X", "model", "BUY", 0, 1, "a", "b", 100.0, 95.0, 110.0, 95.0, "stop", 0.5, 0.0, 0.001)
    assert abs(t.r - (-1 - 0.1 / 5)) < 1e-9


def test_regime_labels_and_gate():
    dates, o, h, l, c = _series(n=1200)
    off = np.zeros(c.size)
    trades = bt.simulate("X", dates, o, h, l, c, regime_ok=off)
    assert all(t.label == "BUY_SMALL" for t in trades if t.variant == "model")
    assert not [t for t in trades if t.variant == "regime_gate"]


def test_clean_ohlc_repairs_bad_tick():
    c = np.array([100, 101, 300, 102, 103.0])
    o, h, l, c2 = bt.clean_ohlc(c, c, c, c)
    assert c2[2] == 101 and (h >= l).all()


def test_portfolio_risk_sizing_and_gross_cap():
    dates = [f"D{k}" for k in range(5)]
    c = np.array([100, 100, 102, 104, 106.0])
    mk = lambda s: bt.Trade(s, "model", "BUY", 1, 4, "D1", "D4", 100.0, 95.0, 110.0, 106.0, "time", 0.5, 0, 0.0)
    trades = [mk(f"S{k}") for k in range(15)]
    closes = {t.symbol: c for t in trades}
    ds = {t.symbol: dates for t in trades}
    p = bt.portfolio(trades, closes, ds, dates)
    # 0.5% risk on a 5% stop = 10% of NAV each → 10 fit under 100% gross, 5 skipped
    assert p["taken"] == 10 and p["skipped"] == 5
    assert abs(p["nav"][-1] - 1.06) < 1e-9


def test_perf_annualises_by_date_span_not_bar_count():
    # 600 bars spread over two calendar years (a multi-market union calendar): 2 years, not 600/252
    import datetime as dt
    d0 = dt.date(2020, 1, 1)
    cal = [(d0 + dt.timedelta(days=round(k * 731 / 599))).isoformat() for k in range(600)]
    ret = np.full(600, (1.21 ** (1 / 600)) - 1)          # +21% in total
    assert abs(bt.perf(ret, cal)["cagr"] - 0.10) < 0.002
