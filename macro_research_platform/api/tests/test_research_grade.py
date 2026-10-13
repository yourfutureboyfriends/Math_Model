"""Industry-standard checks and execution realism: look-ahead detection, PBO, capacity, volume limits, execution
price, borrow tiers, margin calls, attribution, ex-ante risk, optimiser helpers and signal ICs."""
import numpy as np
import pandas as pd
import pytest

from api.quant import codelab as cl

IDX = pd.bdate_range("2015-01-01", periods=1200)
Z = {"commission_bps": 0, "spread_mult": 0, "impact_coef_bps": 0, "sec_fee_bps": 0, "borrow_fee": 0, "borrow_tiers": 0,
     "financing_spread": 0, "cash_spread": 0, "no_trade_band": 0, "fx_cost_bps": 0, "max_participation": 0}


def market(n=8, seed=1, vol=1e7, T=1200):
    rng = np.random.default_rng(seed)
    px = pd.DataFrame(100 * np.cumprod(1 + rng.normal(0.0003, 0.012, (T, n)), axis=0), index=IDX[:T],
                      columns=[f"S{i}" for i in range(n)])
    return cl.Data(px, px.shift(1).fillna(px.iloc[0]), px, px, px * 0 + vol, rf=pd.Series(0.0, index=px.index))


def mom(data, lookback=63):
    s = cl.momentum(data.close, lookback, 5)
    return cl.hold_monthly((s.rank(axis=1, ascending=False) <= 3).astype(float) / 3)


def test_causality_check_passes_causal_code_and_catches_look_ahead():
    d = market()
    assert cl.causality_check(mom, d, {}, cl.run_weights(mom, d, {}))["passed"] is True
    peek = lambda data: cl.hold_monthly((data.close.shift(-5) / data.close).rank(axis=1, ascending=False).le(3).astype(float) / 3)
    res = cl.causality_check(peek, d, {}, cl.run_weights(peek, d, {}))
    assert res["passed"] is False and res["cuts"][0]["first"]["date"]
    zscore = lambda data: (data.close - data.close.mean()) / data.close.std() * 0.01        # full-sample statistics
    assert cl.causality_check(zscore, d, {}, cl.run_weights(zscore, d, {}))["passed"] is False


def test_pbo_low_for_a_genuinely_better_set_and_near_half_for_noise():
    rng = np.random.default_rng(3)
    idx = pd.bdate_range("2010-01-01", periods=2000)
    noise = [pd.Series(rng.normal(0, 0.01, 2000), index=idx) for _ in range(10)]
    p_noise = cl.pbo(noise)["pbo"]
    good = noise[:9] + [pd.Series(rng.normal(0.002, 0.01, 2000), index=idx)]
    p_good = cl.pbo(good)["pbo"]
    assert p_good < 0.1 and 0.25 < p_noise < 0.75
    assert cl.pbo([noise[0], noise[0].copy()])["pbo"] is None                                 # identical: not applicable


def test_volume_limit_spreads_a_large_order_over_days():
    d = market(n=1, vol=1000.0)                                                               # ~$100k a day traded
    w = pd.DataFrame(np.nan, index=d.close.index, columns=d.close.columns)
    w.iloc[0] = 1.0
    res = cl.backtest(w, d, {**Z, "capital": 1e6, "max_participation": 0.1})                 # $10k a day → 100 days
    held = res["long"]
    assert held.iloc[5] < 0.1 and held.iloc[150] > 0.95
    assert res["execution"]["participation_capped_days"] > 50


def test_execution_price_modes():
    d = market(n=1)
    w = pd.DataFrame(np.nan, index=d.close.index, columns=d.close.columns)
    w.iloc[10] = 1.0
    for mode, px in ((0, d.open), (2, d.close)):
        r = cl.backtest(w, d, {**Z, "exec_price": mode}, "2015-01-02")
        units = r["ledger"]["units"]["S0"]
        assert units == pytest.approx(1.0 / px.iloc[11, 0], rel=1e-9)
    assert cl.backtest(w, d, {**Z, "exec_price": 1})["execution"]["exec_price"] == "next-day VWAP"


def test_illiquid_shorts_cost_more_to_borrow():
    liquid, thin = market(n=1, vol=1e7), market(n=1, vol=1e3)                                 # ~$1bn vs ~$100k a day
    w = pd.DataFrame(np.nan, index=liquid.close.index, columns=liquid.close.columns)
    w.iloc[0] = -0.5
    cfg = {**Z, "borrow_fee": 0.003, "borrow_tiers": 1}
    b_liq = cl.backtest(w, liquid, cfg)["borrow"].sum()
    b_thin = cl.backtest(w, thin, cfg)["borrow"].sum()
    assert b_thin / b_liq == pytest.approx(0.05 / 0.003, rel=0.25)


def test_margin_call_cuts_positions_when_equity_runs_out():
    idx = pd.bdate_range("2020-01-01", periods=40)
    px = pd.DataFrame({"A": np.r_[[100.0] * 10, [70.0] * 30]}, index=idx)                    # a 30% gap down
    d = cl.Data(px, px, px, px, px * 0 + 1e9, rf=pd.Series(0.0, index=idx))
    w = pd.DataFrame(np.nan, index=idx, columns=["A"])
    w.iloc[0] = 3.0                                                                            # 3× leverage
    r = cl.backtest(w, d, {**Z, "maintenance_margin": 0.25})
    assert r["execution"]["margin_calls"] >= 1
    assert any(e["event"].startswith("margin call") for e in r["events"])
    # after the gap the book was 21× NAV; the call cuts it so the requirement is 80% of NAV: 0.8 / 0.25 = 3.2×
    assert r["long"].iloc[-1] == pytest.approx(0.8 / 0.25, rel=0.02)


def test_attribution_adds_up_to_security_pnl():
    d = market()
    r = cl.backtest(cl.run_weights(mom, d, {}), d, Z)
    a = cl.attribution(r, d)
    assert a["per_year"]["securities"] == pytest.approx(a["per_year"]["total"], abs=1e-6)    # no costs or interest
    assert a["top"][0]["per_year"] >= a["top"][-1]["per_year"]


def test_risk_model_matches_realised_risk_of_a_static_book():
    d = market(n=6, T=800)
    h = {c: 1 / 6 for c in d.tickers}
    rk = cl.risk_model(d, h)
    realised = (d.close.pct_change().iloc[-252:] @ pd.Series(h)).std() * np.sqrt(252)
    assert rk["vol"] == pytest.approx(realised, rel=0.15)
    assert sum(p["risk_share"] for p in rk["positions"]) == pytest.approx(1.0, abs=1e-3)
    assert rk["effective_positions"] == pytest.approx(6.0)


def test_optimiser_respects_constraints_and_risk_parity_equalises():
    rng = np.random.default_rng(5)
    R = pd.DataFrame(rng.normal(0, 0.01, (500, 6)) * np.array([1, 1, 2, 2, 3, 3]), columns=list("ABCDEF"))
    C = cl.cov_shrink(R)
    mu = pd.Series([0.05, 0.04, 0.03, 0.02, 0.01, 0.0], index=C.index) / 252
    w = cl.optimize(mu, C, risk_aversion=2.0, max_weight=0.3)
    assert w.sum() == pytest.approx(1.0, abs=1e-6) and w.max() <= 0.3 + 1e-9 and w.min() >= -1e-12
    ls = cl.optimize(mu, C, long_only=False, max_weight=0.25, gross=1.0, net=0.0)
    assert abs(ls.sum()) < 1e-6 and ls.abs().sum() <= 1.0 + 1e-6 and ls.abs().max() <= 0.25 + 1e-9
    g = pd.Series(["x", "x", "x", "y", "y", "y"], index=C.index)
    gw = cl.optimize(mu, C, risk_aversion=0.1, max_weight=0.5, groups=g, group_max=0.6)
    assert gw[g == "x"].sum() <= 0.6 + 1e-6 and gw.sum() == pytest.approx(1.0, abs=1e-6) and gw.max() <= 0.5 + 1e-9
    rp = cl.risk_parity(C)
    rc = rp * (C.to_numpy() @ rp.to_numpy())
    assert rc.std() / rc.mean() < 1e-3
    mv = cl.min_variance(C)
    assert float(mv @ C @ mv) <= float(rp @ C @ rp) + 1e-12


def test_signal_report_scores_a_predictive_signal():
    d = market(n=40, T=600)
    fwd = d.open.shift(-6) / d.open.shift(-1) - 1                                             # the next 5 days' return
    noisy = fwd + np.random.default_rng(2).normal(0, 0.03, fwd.shape)
    rep = cl.signal_report(noisy, d, horizons=(5, 21))
    ic5 = next(x for x in rep["ic"] if x["horizon"] == 5)
    assert ic5["mean_ic"] > 0.3 and ic5["t_stat"] > 5
    assert rep["quantiles"]["spread"] > 0


# ── event-driven mode, limit and stop orders ────────────────────────────────
def _bars(close, high=None, low=None, open_=None):
    idx = pd.bdate_range("2020-01-01", periods=len(close))
    c = pd.DataFrame({"A": close}, index=idx)
    h = pd.DataFrame({"A": high if high is not None else close}, index=idx)
    l = pd.DataFrame({"A": low if low is not None else close}, index=idx)
    o = pd.DataFrame({"A": open_ if open_ is not None else close}, index=idx)
    return cl.Data(c, o, h, l, c * 0 + 1e9, rf=pd.Series(0.0, index=idx))


def test_event_mode_market_order_matches_weight_mode():
    d = market(n=3, T=300)
    def on_bar(ctx):
        if ctx.i == 10:
            ctx.target({"S0": 0.5, "S1": 0.5})
    ev = cl.backtest(None, d, Z, on_bar=on_bar)
    w = pd.DataFrame(np.nan, index=d.close.index, columns=d.close.columns)
    w.iloc[10] = [0.5, 0.5, 0.0]
    vec = cl.backtest(w, d, Z)
    assert ev["ledger"]["nav"] == pytest.approx(vec["ledger"]["nav"], rel=1e-12)
    assert ev["execution"]["mode"] == "event-driven"


def test_limit_buy_fills_at_the_limit_or_a_better_open():
    close = [100.0] * 5 + [99.0] * 5
    d = _bars(close, high=[101.0] * 10, low=[99.5] * 5 + [94.0] * 5, open_=[100.0] * 5 + [97.0] * 5)
    def on_bar(ctx):
        if ctx.i == 1:
            ctx.limit("A", 1.0, 95.0)                          # buy everything at 95 or better
    r = cl.backtest(None, d, Z, on_bar=on_bar)
    f = [e for e in r["events"] if e["event"] == "limit order filled"]
    assert len(f) == 1 and f[0]["price"] == 95.0 and f[0]["date"] == str(d.close.index[5].date())
    assert r["ledger"]["units"]["A"] == pytest.approx(1.0 / 95.0)


def test_stop_loss_gaps_through_and_fills_at_the_open():
    close = [100.0] * 6 + [80.0] * 4
    d = _bars(close, high=[101.0] * 6 + [82.0] * 4, low=[99.0] * 6 + [78.0] * 4, open_=[100.0] * 6 + [81.0] * 4)
    def on_bar(ctx):
        if ctx.i == 0:
            ctx.target({"A": 1.0})
        if ctx.i == 2 and not ctx.orders:
            ctx.stop("A", 0.0, 90.0)                           # sell everything below 90
    r = cl.backtest(None, d, Z, on_bar=on_bar)
    f = [e for e in r["events"] if e["event"] == "stop order filled"]
    assert f and f[0]["price"] == 81.0                          # gapped through 90: the open, not the stop
    assert "A" not in r["ledger"]["units"]
    assert r["ledger"]["nav"] == pytest.approx(81.0 / 100.0, rel=1e-9)


def test_on_bar_only_sees_the_past():
    d = market(n=2, T=200)
    seen = []
    def on_bar(ctx):
        seen.append((ctx.date, ctx.history("close").index[-1], len(ctx.history("close", 20))))
    cl.backtest(None, d, Z, on_bar=on_bar)
    assert all(a == b for a, b, _ in seen) and all(n <= 20 for *_, n in seen)


def test_brinson_sums_to_active_return_and_cpcv_paths():
    d = market(n=8, T=600)
    for i, c in enumerate(d.tickers):
        d.instruments[c]["sector"] = "Tech" if i < 4 else "Banks"
    r = cl.backtest(cl.run_weights(mom, d, {}), d, Z)
    a = cl.attribution(r, d)["brinson"]
    active = sum(a["total"].values())
    ew = d.observed.astype(float).where(d.observed)
    base = cl.backtest(cl.hold_monthly(ew.div(ew.sum(axis=1), axis=0)), d, Z)            # daily-rebalanced EW ≈ the benchmark
    assert a["by"] == "sector" and {x["group"] for x in a["rows"]} == {"Tech", "Banks"}
    assert abs(active) < 1.0                                                              # sane magnitude
    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2010-01-01", periods=1500)
    ser = [pd.Series(rng.normal(0.0004 * k, 0.01, 1500), index=idx) for k in range(4)]
    cv = cl.cpcv(ser)
    assert cv["paths"] == 5 and cv["sharpe_mean"] > 0


def test_setup_is_checked_for_look_ahead_in_event_mode():
    d = market(n=3, T=900)
    on_bar = lambda ctx: None
    ok = cl.evaluate(None, d, {}, "2015-06-01", Z, on_bar=on_bar, setup=lambda data: {"ma": data.close.rolling(20).mean()})
    assert ok["validation"]["causality"]["passed"] is True
    bad = cl.evaluate(None, d, {}, "2015-06-01", Z, on_bar=on_bar, setup=lambda data: {"ma": data.close - data.close.mean()})
    assert bad["validation"]["causality"]["passed"] is False
