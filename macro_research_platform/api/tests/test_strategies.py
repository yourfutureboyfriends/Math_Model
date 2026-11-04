"""Strategy Lab engine and signals: no look-ahead, drift and cost accounting, signal logic."""
import numpy as np

from api.calculations import strategies as sg


def _px(T=800, N=5, seed=4, drifts=None):
    rng = np.random.default_rng(seed)
    d = np.array(drifts if drifts is not None else np.linspace(-0.0006, 0.0008, N))
    return 100 * np.exp(np.cumsum(d + 0.01 * rng.standard_normal((T, N)), axis=0))


def _dates(T):
    base = np.datetime64("2015-01-01")
    return [str(base + k) for k in range(T)]


def test_buy_and_hold_matches_price_path():
    px = _px(N=1, drifts=[0.0004])
    d = _dates(px.shape[0])
    out = sg.run_monthly(px, d, lambda t: np.array([1.0]), cost_bps=0.0, start=0)
    first = d.index(out["dates"][0])
    assert np.isclose(out["equity"][-1], px[-1, 0] / px[first, 0])


def test_no_lookahead():
    px = _px()
    d = _dates(px.shape[0])
    a = sg.run_monthly(px, d, lambda t: sg.trend_weights(px, t))
    px2 = px.copy()
    px2[700:] *= 0.5
    b = sg.run_monthly(px2, d, lambda t: sg.trend_weights(px2, t))
    k = 700 - d.index(a["dates"][0])
    assert np.allclose(a["returns"][:k], b["returns"][:k])


def test_costs_reduce_returns():
    px = _px()
    d = _dates(px.shape[0])
    free = sg.run_monthly(px, d, lambda t: sg.trend_weights(px, t), cost_bps=0.0)
    paid = sg.run_monthly(px, d, lambda t: sg.trend_weights(px, t), cost_bps=50.0)
    assert paid["equity"][-1] < free["equity"][-1]


def test_trend_goes_long_uptrend_short_downtrend():
    px = _px(drifts=[0.002, -0.002, 0.002, -0.002, 0.0])
    w = sg.trend_weights(px, px.shape[0] - 1)
    assert w[0] > 0 and w[1] < 0
    assert (sg.trend_weights(px, px.shape[0] - 1, long_only=True) >= 0).all()


def test_sector_momentum_picks_winners_and_respects_market_filter():
    px = _px(N=6, drifts=[0.005, 0.004, 0.0, -0.001, -0.002, 0.0005])
    w = sg.sector_momentum_weights(px, px.shape[0] - 1, top=2)
    assert set(np.flatnonzero(w)) == {0, 1}
    crash = px.copy()
    crash[-30:, 5] *= 0.5                                 # market column below its average
    assert sg.sector_momentum_weights(crash, crash.shape[0] - 1, top=2, market_col=5).sum() == 0


def test_low_vol_picks_quiet_names():
    rng = np.random.default_rng(1)
    vols = np.linspace(0.005, 0.04, 20)
    px = 100 * np.exp(np.cumsum(vols * rng.standard_normal((400, 20)), axis=0))
    w = sg.low_vol_weights(px, 399, quantile=0.2, min_names=4)
    assert set(np.flatnonzero(w)) <= set(range(6))


def test_residual_momentum_ignores_market_beta():
    rng = np.random.default_rng(2)
    M = 60
    mkt = np.cumprod(1 + 0.01 + 0.04 * rng.standard_normal(M))
    idio_good = np.cumprod(1 + 0.02 + 0.01 * rng.standard_normal(M))
    beta_hi = mkt ** 2                                     # high return only through beta
    px = np.column_stack([mkt * idio_good, beta_hi])
    s = sg.residual_momentum_scores(px, np.column_stack([mkt, mkt]), M - 1)
    assert s[0] > s[1]
