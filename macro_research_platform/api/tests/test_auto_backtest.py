"""Auto-book portfolio backtest: accounting, no look-ahead, controls, overfitting statistics."""
import numpy as np

from api.calculations import auto_backtest as ab
from api.calculations.stock_timing import signal_frame


def _panel(N=8, T=900, seed=2, shock_from=None):
    rng = np.random.default_rng(seed)
    drift = np.linspace(-0.0004, 0.0012, N)
    c = 100 * np.exp(np.cumsum(drift + 0.013 * rng.standard_normal((T, N)), axis=0))
    if shock_from is not None:
        c[shock_from:] *= 0.5
    o = c * (1 + 0.002 * rng.standard_normal((T, N)))
    h = np.maximum(o, c) * (1 + np.abs(0.005 * rng.standard_normal((T, N))))
    l = np.minimum(o, c) * (1 - np.abs(0.005 * rng.standard_normal((T, N))))
    setup, timing, atr = (np.empty((T, N)) for _ in range(3))
    for i in range(N):
        f = signal_frame(c[:, i], h[:, i], l[:, i])
        setup[:, i], timing[:, i], atr[:, i] = f["setup"], f["timing"], f["atr"]
    dates = [str(np.datetime64("2010-01-01") + k) for k in range(T)]
    return ab.Panel(dates, [f"S{i}" for i in range(N)], o, h, l, c, setup, timing, atr,
                    np.ones((T, N)), ["Developed"] * N, [f"Sec{i % 4}" for i in range(N)])


def test_accounting_and_trades():
    p = _panel()
    out = ab.run(p, ab.Rules(max_positions=4, max_per_sector=2))
    assert out["trades"], "trending stocks should trade"
    assert (out["gross"] <= 1.0 + 1e-9).all() and (out["positions"] <= 4).all()
    for t in out["trades"]:
        assert t["exit_t"] >= t["entry_t"]


def test_no_lookahead():
    a = ab.run(_panel(), ab.Rules(max_positions=4))
    b = ab.run(_panel(shock_from=700), ab.Rules(max_positions=4))
    k = 700 - 260
    assert np.allclose(a["equity"][:k], b["equity"][:k])


def test_regime_gate_blocks_entries():
    p = _panel()
    p.regime[:] = 0
    assert ab.run(p, ab.Rules())["trades"] == []


def test_control_uses_the_given_entry_rate():
    p = _panel()
    none = ab.run(p, ab.Rules(random_entries=True, random_rate=0.0))
    some = ab.run(p, ab.Rules(random_entries=True, random_rate=0.5))
    assert none["trades"] == [] and some["trades"]


def test_deflated_sharpe_penalises_more_trials():
    rng = np.random.default_rng(0)
    r = 0.0006 + 0.01 * rng.standard_normal(2500)
    few = ab.deflated_sharpe(r, [0.02, 0.03])
    many = ab.deflated_sharpe(r, list(rng.normal(0.02, 0.02, 200)))
    assert many["dsr"] < few["dsr"] and 0 <= many["dsr"] <= 1


def test_bootstrap_range_is_ordered():
    rng = np.random.default_rng(1)
    q = ab.bootstrap_range(0.0004 + 0.01 * rng.standard_normal(2000), 63)
    assert q["p5"] < q["p25"] < q["p50"] < q["p75"] < q["p95"]
