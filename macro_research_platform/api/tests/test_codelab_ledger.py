"""Code Lab engine accounting, execution and causality — acceptance fixtures for the quant handoff (P1 #1–4, P2 #7)."""
import numpy as np
import pandas as pd
import pytest

from api.quant import codelab as cl

IDX = pd.bdate_range("2024-01-01", periods=40)
Z = {"commission_bps": 0, "spread_mult": 0, "impact_coef_bps": 0, "sec_fee_bps": 0, "borrow_fee": 0,
     "financing_spread": 0, "cash_spread": 0, "no_trade_band": 0}


def mk(close, open_=None, observed=None, vol=1e8, rf=0.0, idx=IDX):
    c = pd.DataFrame(close, index=idx[:len(next(iter(close.values())))])
    o = c.shift(1).fillna(c.iloc[0]) if open_ is None else pd.DataFrame(open_, index=c.index)
    v = pd.DataFrame(vol, index=c.index, columns=c.columns)
    obs = None if observed is None else pd.DataFrame(observed, index=c.index)
    return cl.Data(c, o, c, c, v, rf=pd.Series(rf, index=c.index), observed=obs)


def target(d, rows):
    w = pd.DataFrame(np.nan, index=d.close.index, columns=d.close.columns)
    for i, vals in rows.items():
        w.iloc[i] = vals
    return w


def reconcile(res, d):
    led = res["ledger"]
    assert led["reconciles"]
    marks = d.close.ffill().iloc[-1]
    sec = sum(u * marks[k] for k, u in led["units"].items())
    assert sec + led["cash"] == pytest.approx(led["nav"], abs=1e-9)
    assert (1 + res["ret"]).prod() == pytest.approx(led["nav"], rel=1e-9)        # returns chain to the ledger NAV


# ── P1 #2: self-financing ledger ────────────────────────────────────────────
def test_fee_is_paid_from_cash_and_post_fee_weights_follow_nav():
    d = mk({"A": [100.0] * 40, "B": [50.0] * 40})
    res = cl.backtest(target(d, {1: [0.5, 0.5]}), d, {**Z, "commission_bps": 1000})       # 10% commission
    led = res["ledger"]
    # orders are sized to post-fee NAV: buy X with X + 10%·X = 1 → X = 1/1.1, fee 0.1/1.1, no hidden margin loan
    assert led["nav"] == pytest.approx(1 / 1.1, rel=1e-6)
    assert led["cash"] == pytest.approx(0.0, abs=1e-6)
    assert res["holdings_last"]["A"] == pytest.approx(0.5, abs=1e-4)                  # weights vs post-fee NAV
    assert res["commission"].sum() == pytest.approx(0.1 / 1.1, rel=1e-6)
    reconcile(res, d)


def test_round_trip_unchanged_target_gap_and_intraday_reconcile():
    close = np.r_[[100.0] * 10, [120.0] * 10, [90.0] * 20]
    open_ = np.r_[[100.0] * 10, [110.0], [120.0] * 9, [95.0], [90.0] * 19]               # overnight gaps on 10 and 20
    d = mk({"A": close}, {"A": open_})
    res = cl.backtest(target(d, {2: [1.0], 25: [0.0]}), d, {**Z, "commission_bps": 10})
    # buy at 100 (day 3 open), sell at 90 (day 26 open): NAV = (90/100) less two commissions
    exp = 0.9 * (1 - 0.001) / (1 + 0.001)                                             # buy 1/1.001 of NAV, sell less 10 bp
    assert res["ledger"]["nav"] == pytest.approx(exp, rel=1e-6)
    assert res["ledger"]["units"] == {} and res["ledger"]["cash"] == pytest.approx(exp, rel=1e-6)
    reconcile(res, d)


def test_financing_and_cash_interest_settle_into_cash():
    d = mk({"A": [100.0] * 40}, rf=0.04 / 252)
    lev = cl.backtest(target(d, {0: [2.0]}), d, {**Z, "financing_spread": 0.01})
    # borrowed 1× NAV: pays (4% + 1%)/252 a day on it
    assert lev["financing"].iloc[5] == pytest.approx(-(0.04 + 0.01) / 252, rel=5e-3)
    cash_only = cl.backtest(target(d, {0: [0.0]}), d, {**Z, "cash_spread": 0.01})
    assert cash_only["ret"].iloc[5] == pytest.approx((0.04 - 0.01) / 252, rel=1e-9)  # remuneration is configurable
    reconcile(lev, d)


def test_dividend_adjusted_series_reconciles():
    # adjusted prices embed the dividend: a total-return series with a 2% step is P&L, not a lost dividend
    d = mk({"A": np.r_[[98.0] * 20, [100.0] * 20]})
    res = cl.backtest(target(d, {0: [1.0]}), d, Z)
    assert res["ledger"]["nav"] == pytest.approx(100 / 98, rel=1e-9)
    reconcile(res, d)


# ── P1 #3: missing opens, stale marks, ended listings ───────────────────────
def test_missing_open_never_fills_at_the_close_and_order_stays_pending():
    close = np.r_[[100.0] * 4, [110.0] * 36]
    open_ = np.r_[[100.0] * 4, [np.nan], [110.0] * 35]                                 # no opening print on day 4
    d = mk({"A": close}, {"A": open_})
    res = cl.backtest(target(d, {3: [1.0]}), d, Z)
    assert res["turnover"].iloc[3] == 0                                                  # day 4: nothing executable
    assert res["turnover"].iloc[4] > 0                                                   # filled at day 5's open (110)
    assert res["execution"]["unfilled_order_days"] == 1
    assert res["ledger"]["nav"] == pytest.approx(1.0, rel=1e-12)                        # bought at 110, still 110


def test_zero_volume_bar_is_not_executable_and_stale_marks_are_flagged():
    close = [100.0] * 40
    obs = np.ones(40, bool)
    obs[10:15] = False                                                                   # suspension: no bars
    d = mk({"A": close}, observed={"A": obs}, vol=np.r_[[1e8] * 5, [0.0], [1e8] * 34].reshape(-1, 1))
    res = cl.backtest(target(d, {4: [1.0], 9: [0.0]}), d, Z)
    assert res["turnover"].iloc[4] == 0 and res["turnover"].iloc[5] > 0               # zero-volume day skipped
    assert res["turnover"].iloc[9:14].sum() == 0                                         # cannot sell while suspended
    assert res["execution"]["stale_position_days"] == 5
    assert res["ledger"]["units"] == {}                                                  # sold when trading resumed


def test_ended_listing_is_settled_at_last_close():
    close = np.r_[[100.0] * 20, [80.0] * 5, [np.nan] * 15]
    d = mk({"A": close, "B": [10.0] * 40})
    d.provenance["delisting_events"] = {"A": {"effective_date": str(IDX[25].date()), "known_at": str(IDX[25].date())}}
    res = cl.backtest(target(d, {0: [1.0, 0.0]}), d, {**Z, "delist_haircut": 0.25})
    assert res["ledger"]["units"] == {}
    assert res["ledger"]["cash"] == pytest.approx(0.8 * 0.75, rel=1e-9)
    assert any(e["event"].startswith("listing ended") for e in res["events"])


def test_exchange_holiday_and_unexplained_gap():
    # a holiday is a date absent for every asset; an unexplained gap is a missing bar for one asset only
    idx = IDX.delete(10)
    d = mk({"A": [100.0] * 39, "B": [100.0] * 39}, observed={"A": np.ones(39, bool), "B": np.r_[[True] * 20, [False], [True] * 18]}, idx=idx)
    res = cl.backtest(target(d, {19: [0.5, 0.5]}), d, Z)
    assert res["turnover"].iloc[19] == pytest.approx(0.5)                                # only A can trade on B's gap day
    assert res["turnover"].iloc[20] == pytest.approx(0.5)                                # B fills the next day
    reconcile(res, d)


# ── P1 #4: causal schedules and explicit decisions ──────────────────────────
def test_hold_helpers_are_causal():
    full = pd.DataFrame({"A": np.arange(40.0)}, index=IDX)
    hf = cl.hold_monthly(full)
    for n in (5, 12, 23, 33):
        hp = cl.hold_monthly(full.iloc[:n])
        pd.testing.assert_frame_equal(hp, hf.iloc[:n])                                   # appending data revises nothing
    assert list(hf.dropna().index) == [IDX[0], IDX[23]]                                  # first trading day of Jan and Feb


def test_identical_target_scheduled_rebalance_trades_back_to_target():
    a = np.r_[[100.0] * 10, [200.0] * 30]
    d = mk({"A": a, "B": [100.0] * 40})
    w = target(d, {0: [0.5, 0.5], 20: [0.5, 0.5]})                                      # same target, explicit decision
    res = cl.backtest(w, d, Z)
    assert res["turnover"].iloc[20] > 0.3                                                # drifted to 2/3–1/3, rebalanced
    no_decision = cl.backtest(target(d, {0: [0.5, 0.5]}), d, Z)
    assert no_decision["turnover"].iloc[20] == 0


def test_next_open_execution_has_exactly_one_lag():
    close = np.r_[[100.0] * 10, [150.0] * 30]                                           # jumps on day 10 (at the open)
    open_ = np.r_[[100.0] * 10, [150.0] * 30]
    d = mk({"A": close}, {"A": open_})
    early = cl.backtest(target(d, {8: [1.0]}), d, Z)["ledger"]["nav"]                    # filled day 9 at 100
    late = cl.backtest(target(d, {9: [1.0]}), d, Z)["ledger"]["nav"]                     # filled day 10 at 150
    assert early == pytest.approx(1.5) and late == pytest.approx(1.0)


# ── P1 #1: one continuous account through walk-forward switches ────────────
def _two_strategy_data():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2014-01-01", "2021-12-31")
    a = 100 * np.cumprod(1 + rng.normal(0.0004, 0.01, len(idx)))
    b = 100 * np.cumprod(1 + rng.normal(0.0001, 0.01, len(idx)))
    return mk({"A": a, "B": b}, idx=idx)


def test_switching_parameter_sets_trades_and_pays_transition_costs():
    d = _two_strategy_data()
    idx = d.close.index
    WA = cl.hold_monthly(pd.DataFrame({"A": 1.0, "B": 0.0}, index=idx))
    WB = cl.hold_monthly(pd.DataFrame({"A": 0.0, "B": 1.0}, index=idx))
    combos = [{"x": "a"}, {"x": "b"}]
    chosen = [{"year": 2019, "params": {"x": "a"}}, {"year": 2020, "params": {"x": "b"}}, {"year": 2021, "params": {"x": "b"}}]
    Wc, Dc, switches = cl.continuous_walk_forward([WA, WB], chosen, combos, idx)
    res = cl.backtest(Wc, d, {**Z, "commission_bps": 10}, "2019-01-01", decisions=Dc)
    wk = res["turnover"][(res["turnover"].index >= pd.Timestamp("2020-01-01")) & (res["turnover"].index < pd.Timestamp("2020-01-08"))]
    switch_day = wk.idxmax()                                                             # decided 1 Jan, filled next open
    assert res["turnover"].loc[switch_day] == pytest.approx(2.0, rel=2e-3)              # sell all A, buy all B (net of fees)
    # commission reconciles to traded notional exactly (costs are a fraction of the previous close's NAV)
    nav_prev = (1 + res["ret"]).cumprod().shift(1).loc[switch_day]
    nav_open = nav_prev * d.open.loc[switch_day, "A"] / d.close.shift(1).loc[switch_day, "A"]
    assert res["commission"].loc[switch_day] * nav_prev == pytest.approx(10e-4 * res["turnover"].loc[switch_day] * nav_open, rel=1e-9)
    assert [s["date"][:4] for s in switches] == ["2020"]
    reconcile(res, d)


def test_switch_to_same_holdings_creates_no_transition_trade():
    d = _two_strategy_data()
    idx = d.close.index
    WA = cl.hold_monthly(pd.DataFrame({"A": 1.0, "B": 0.0}, index=idx))
    WA2 = cl.hold_monthly(pd.DataFrame({"A": 1.0, "B": 0.0}, index=idx))
    chosen = [{"year": 2019, "params": {"x": 1}}, {"year": 2020, "params": {"x": 2}}]
    Wc, Dc, _ = cl.continuous_walk_forward([WA, WA2], chosen, [{"x": 1}, {"x": 2}], idx)
    res = cl.backtest(Wc, d, {**Z, "no_trade_band": 0.01}, "2019-01-01", decisions=Dc)
    jan20 = res["turnover"][(res["turnover"].index >= pd.Timestamp("2020-01-01")) & (res["turnover"].index < pd.Timestamp("2020-01-10"))]
    assert jan20.max() < 0.02                                                            # only drift back to target


def test_evaluate_is_prefix_stable_and_later_prices_cannot_change_earlier_results():
    d = _two_strategy_data()

    def strat(data, lb=63):
        m = data.close.pct_change(lb)
        w = (m.rank(axis=1) == 2).astype(float)
        return cl.hold_monthly(w.where(m.notna().all(axis=1)))

    full = cl.evaluate(strat, d, {"lb": [21, 63]}, "2014-01-01")
    cut = pd.Timestamp("2020-06-30")
    pre = cl.Data(d.close[:cut], d.open[:cut], d.high[:cut], d.low[:cut], d.volume[:cut], rf=d.rf[:cut])
    part = cl.evaluate(strat, pre, {"lb": [21, 63]}, "2014-01-01")
    n = len(part["returns"])
    np.testing.assert_allclose(full["returns"][:n], part["returns"], rtol=0, atol=1e-12)
    assert [c["params"] for c in full["optimisation"]["chosen"] if c["year"] <= 2020] == [c["params"] for c in part["optimisation"]["chosen"]]
    # perturb prices after the cut: earlier returns unchanged
    shocked = d.close.copy()
    shocked.loc[shocked.index > cut] *= 1.5
    sd = cl.Data(shocked, shocked.shift(1).fillna(shocked.iloc[0]), shocked, shocked, d.volume, rf=d.rf)
    pert = cl.evaluate(strat, sd, {"lb": [21, 63]}, "2014-01-01")
    np.testing.assert_allclose(pert["returns"][:n - 1], part["returns"][:n - 1], rtol=0, atol=1e-12)


def test_evaluate_reports_baseline_holdout_and_provenance():
    d = _two_strategy_data()

    def strat(data):
        return cl.hold_monthly(pd.DataFrame({"A": 1.0, "B": 0.0}, index=data.close.index))
    r = cl.evaluate(strat, d, {}, "2015-01-01", holdout="2020-01-01", code_hash="abc")
    assert r["baseline_equal_weight"]["cagr"] is not None
    assert r["holdout"]["holdout"]["years"] > 1 and r["holdout"]["in_sample"]["years"] > 4
    p = r["provenance"]
    assert p["engine_version"] == cl.ENGINE_VERSION and p["code_hash"] == "abc" and p["data_hash"]
    assert "exploratory" in p["record_type"]


# ── P2 #7: one metric definition ────────────────────────────────────────────
def test_metrics_match_robust(monkeypatch):
    from api.quant import rates, robust
    idx = pd.bdate_range("2015-01-01", periods=1500)
    r = pd.Series(np.random.default_rng(4).normal(0.0004, 0.011, 1500), index=idx)
    rf = pd.Series(0.03 / 252, index=idx)
    monkeypatch.setattr(rates, "daily", lambda i, ccy="USD": pd.Series(0.03 / 252, index=pd.DatetimeIndex(pd.to_datetime(list(i)))))
    a = cl.metrics(r, rf)
    b = robust.metrics(r.to_numpy(), [d.strftime("%Y-%m-%d") for d in idx])
    for k in ("cagr", "vol", "sharpe", "sortino", "max_drawdown", "calmar"):
        assert a[k] == pytest.approx(b[k], abs=2e-3), k


def test_no_trade_band_never_blocks_entries_or_exits():
    cols = {f"S{i}": [100.0] * 40 for i in range(500)}                                   # 500 positions of 0.2%
    d = mk(cols)
    w = target(d, {0: [1 / 500] * 500, 20: [0.0] * 500})
    res = cl.backtest(w, d, {**Z, "no_trade_band": 0.0025})
    assert res["turnover"].iloc[0] == pytest.approx(1.0, rel=1e-9)                       # bought despite 0.2% < band
    assert res["turnover"].iloc[20] == pytest.approx(1.0, rel=1e-9)                      # and sold
    assert res["ledger"]["units"] == {}


def test_missing_tail_does_not_predict_delisting_and_prefix_is_stable():
    obs = {"A": np.r_[[True]*20, [False]*5, [True]*15], "B": np.ones(40, bool)}
    full = mk({"A": [100.0]*40, "B": [100.0]*40}, observed=obs)
    prefix = mk({"A": [100.0]*25, "B": [100.0]*25}, observed={k:v[:25] for k,v in obs.items()})
    cost = {**Z, "delist_haircut": .25}
    a = cl.backtest(target(full, {0:[1.,0.]}),full,cost)
    b = cl.backtest(target(prefix, {0:[1.,0.]}),prefix,cost)
    pd.testing.assert_series_equal(a["nav"].iloc[:24],b["nav"])
    assert b["ledger"]["nav"] == pytest.approx(1.)
    assert b["execution"]["listings_ended"] == 0
    assert b["execution"]["stale_position_days"] > 0


def test_delisting_waits_until_announcement_is_known():
    d = mk({"A": [100.0]*40})
    d.provenance["delisting_events"] = {"A":{"effective_date":str(IDX[10].date()), "known_at":str(IDX[20].date())}}
    res = cl.backtest(target(d,{0:[1.]}),d,{**Z,"delist_haircut":.25})
    assert res["nav"].loc[IDX[19]] == pytest.approx(1.)
    assert res["nav"].loc[IDX[20]] == pytest.approx(.75)
    assert res["ledger"]["units"] == {}


def test_recent_missing_bar_is_stale_not_a_delisting():
    close = np.r_[[100.0] * 39, [np.nan]]                                                # today's bar not in yet
    d = mk({"A": close, "B": [10.0] * 40})
    res = cl.backtest(target(d, {0: [1.0, 0.0]}), d, Z)
    assert "A" in res["ledger"]["units"] and not res["events"]


# ── P1 #5: account-currency conversion and venue taxes ──────────────────────
def test_flat_foreign_stock_with_moving_fx_changes_usd_nav():
    # GBp quote stays at 100 (= £1.00); GBP/USD moves 1.25 → 1.30: the USD position gains 4%
    close_usd = np.r_[[1.25] * 20, [1.30] * 20]
    d = mk({"HSBA.L": close_usd})
    d.instruments["HSBA.L"] = {"country": "GB", "currency": "GBP", "sec_fee": False, "tax_buy_bps": 50.0, "tax_sell_bps": 0.0}
    res = cl.backtest(target(d, {0: [1.0]}), d, {**Z, "fx_cost_bps": 0.0})                      # stamp duty alone
    nav = res["ledger"]["nav"]
    assert nav == pytest.approx((1 / 1.005) * 1.30 / 1.25, rel=1e-6)                   # 0.5% stamp duty on the purchase
    assert res["fees"].sum() == pytest.approx(0.005 / 1.005, rel=1e-6)


def test_minor_units_and_fx_conversion_in_the_data_layer(monkeypatch):
    from api.quant import codeserver, data as qdata
    idx = pd.bdate_range("2024-01-01", periods=30)
    gbp = pd.DataFrame({"HSBA.L": [100.0] * 30})                                         # 100 GBp = £1
    fx = pd.DataFrame({"GBP=X": np.r_[[0.80] * 15, [0.75] * 15]})                        # £ per $1
    for f in (gbp, fx):
        f.index = idx

    def fake_panel(syms, start=None, end=None, fill=True):
        src = fx if syms == ["GBP=X"] else gbp
        return {k: src.copy() for k in ("close", "open", "high", "low")} | {"volume": src * 0 + 1e6}, []
    monkeypatch.setattr(qdata, "panel", fake_panel)
    inst = {"HSBA.L": {"currency": "GBP", "quote_currency": "GBp", "unit_divisor": 100.0, "fx_ticker": "GBP=X"}}
    out, info, _ = codeserver._to_account_currency(fake_panel(["HSBA.L"])[0], ["HSBA.L"], inst, "2024-01-01", None)
    assert out["close"]["HSBA.L"].iloc[0] == pytest.approx(1 / 0.80)                    # £1 → $1.25
    assert out["close"]["HSBA.L"].iloc[20] == pytest.approx(1 / 0.75)
    assert out["open"]["HSBA.L"].iloc[15] == pytest.approx(1 / 0.80)                    # open uses the previous FX close
