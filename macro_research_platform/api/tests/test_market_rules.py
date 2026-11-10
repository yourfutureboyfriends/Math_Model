"""Board lots, exchange tick sizes, dividend withholding at source and currency hedging in the Code Lab ledger."""
import numpy as np
import pandas as pd
import pytest

from api.quant import codelab as cl
from api.quant import corpactions, market_rules as mr, sandbox

Z = {"commission_bps": 0, "spread_mult": 0, "impact_coef_bps": 0, "sec_fee_bps": 0, "borrow_fee": 0,
     "financing_spread": 0, "cash_spread": 0, "no_trade_band": 0, "fx_cost_bps": 0}
IDX = pd.bdate_range("2024-01-01", periods=30)


def data(px, inst, account="USD", **kw):
    c = pd.DataFrame(px, index=IDX[:len(next(iter(px.values())))])
    return cl.Data(c, c, c, c, c * 0 + 1e9, rf=pd.Series(0.0, index=c.index), instruments=inst, account_currency=account, **kw)


def hold(d, rows):
    w = pd.DataFrame(np.nan, index=d.close.index, columns=d.close.columns)
    for i, vals in rows.items():
        w.iloc[i] = vals
    return w


JP = {"T": {"country": "JP", "currency": "JPY", "sec_fee": False}}


def test_orders_round_to_whole_board_lots():
    # one lot = 30% of capital: a 100% target buys 3 lots (90%); the shortfall is reported
    d = data({"T": [10.0] * 30}, JP, account="JPY", lot_value=pd.DataFrame({"T": 300_000.0}, index=IDX))
    res = cl.backtest(hold(d, {0: [1.0]}), d, {**Z, "capital": 1_000_000})
    assert res["ledger"]["units"]["T"] * 10.0 == pytest.approx(0.9)
    assert res["lot_residual"].sum() == pytest.approx(0.1)
    assert res["execution"]["board_lots"] is True
    off = cl.backtest(hold(d, {0: [1.0]}), d, {**Z, "capital": 1_000_000, "board_lots": 0})
    assert off["ledger"]["units"]["T"] * 10.0 == pytest.approx(1.0)


def test_a_position_smaller_than_half_a_lot_is_not_bought_and_exits_sell_odd_lots():
    d = data({"T": [10.0] * 30}, JP, account="JPY", lot_value=pd.DataFrame({"T": 300_000.0}, index=IDX))
    small = cl.backtest(hold(d, {0: [0.1]}), d, {**Z, "capital": 1_000_000})             # 0.1 < half a lot (0.15)
    assert "T" not in small["ledger"]["units"]
    big = cl.backtest(hold(d, {0: [1.0], 10: [0.0]}), d, {**Z, "capital": 1_000_000})
    assert "T" not in big["ledger"]["units"]                                               # full exit, no lot left


def test_tick_table_floors_the_spread():
    d = data({"T": [10.0] * 30}, JP)
    hs = cl.half_spread_bps(d.close, d.volume, tick_bps=pd.DataFrame({"T": 50.0}, index=IDX))
    assert hs.iloc[-1, 0] == pytest.approx(50.0)                                           # liquid, but a 1% tick
    assert mr.half_tick_bps("JP", np.array([2500.0]))[0] == pytest.approx(0.5 / 2500 * 1e4)
    assert mr.half_tick_bps("HK", np.array([400.0]))[0] == pytest.approx(0.1 / 400 * 1e4)
    assert mr.half_tick_bps("TW", np.array([1000.0]))[0] == pytest.approx(2.5 / 1000 * 1e4)
    assert 0.5 <= mr.half_tick_bps("DE", np.array([200.0]))[0] <= 2.5                     # MiFID liquid band
    assert mr.lot_frame_value("PH", 1, np.array([3.0, 30.0, 300.0])).tolist() == [1000, 100, 10]


def test_dividends_from_foreign_listings_lose_withholding_tax():
    dy = pd.DataFrame({"T": 0.0}, index=IDX)
    dy.iloc[10, 0] = 0.02                                                                   # 2% dividend on day 10
    inst = {"T": {"country": "JP", "currency": "JPY", "sec_fee": False, "wht": 0.15315}}
    usd = data({"T": [10.0] * 30}, inst, account="USD", div_yield=dy)
    res = cl.backtest(hold(usd, {0: [1.0]}), usd, Z)
    assert res["dividend_tax"].sum() == pytest.approx(0.02 * 0.15, rel=1e-6)               # capped at the 15% treaty rate
    assert res["ledger"]["nav"] == pytest.approx(1 - 0.003, rel=1e-6)
    nocap = cl.backtest(hold(usd, {0: [1.0]}), usd, {**Z, "wht_treaty_cap": 1.0})
    assert nocap["dividend_tax"].sum() == pytest.approx(0.02 * 0.15315, rel=1e-6)
    home = data({"T": [10.0] * 30}, inst, account="JPY", div_yield=dy)                     # domestic: nothing withheld
    assert cl.backtest(hold(home, {0: [1.0]}), home, Z)["dividend_tax"].sum() == 0.0
    assert mr.wht_rate("US", "USD", "EUR") == 0.15 and mr.wht_rate("US", "USD", "USD") == 0.0


def test_fx_hedge_removes_the_currency_move_and_earns_the_rate_differential():
    # a JPY stock flat in yen; the yen gains 4% against the dollar on day 15
    fx = pd.DataFrame({"JPY": np.r_[[1 / 150] * 15, [1 / 150 * 1.04] * 15]}, index=IDX)   # USD per yen
    px = (fx["JPY"] * 1500.0).to_numpy()                                                    # ¥1,500 in USD
    rf_ccy = pd.DataFrame({"JPY": 0.0}, index=IDX)
    kw = dict(fx=fx, rf_ccy=rf_ccy)
    d = data({"T": px}, JP, account="USD", **kw)
    w = hold(d, {0: [1.0]})
    assert cl.backtest(w, d, Z)["ledger"]["nav"] == pytest.approx(1.04)                     # unhedged: the currency gain
    hedged = cl.backtest(w, d, {**Z, "fx_hedge": 1.0, "fx_hedge_cost_bps": 0.0})
    assert hedged["ledger"]["nav"] == pytest.approx(1.0, abs=1e-9)                          # hedged: none of it
    assert hedged["execution"]["fx_hedged"] == ["JPY"]
    # with US rates 5% and yen rates 0%, the hedge earns the 5% differential on the hedged notional
    d2 = cl.Data(d.close, d.open, d.high, d.low, d.volume, rf=pd.Series(0.05 / 252, index=IDX), instruments=JP, **kw)
    carry = cl.backtest(w, d2, {**Z, "fx_hedge": 1.0, "fx_hedge_cost_bps": 0.0})
    assert carry["hedge"].sum() - hedged["hedge"].sum() == pytest.approx(28 * 0.05 / 252, rel=0.05)   # exposure 1–1.04
    # a currency with no rate history cannot be priced as a hedge: it stays unhedged, and says so
    d3 = data({"T": px}, JP, account="USD", fx=fx, rf_ccy=pd.DataFrame({"JPY": np.nan}, index=IDX))
    r3 = cl.backtest(w, d3, {**Z, "fx_hedge": 1.0})
    assert r3["ledger"]["nav"] == pytest.approx(1.04) and r3["execution"]["fx_unhedged"] == ["JPY"]


def test_fx_hedge_header_and_precedence():
    body = '\ndef strategy(data):\n    return data.close * 0\n'
    assert sandbox.check('UNIVERSE = ["SPY"]\nFX_HEDGE = 0.5' + body)["fx_hedge"] == 0.5
    with pytest.raises(sandbox.SandboxError, match="FX_HEDGE"):
        sandbox.check('UNIVERSE = ["SPY"]\nFX_HEDGE = 2' + body)
    st = cl.load_strategy('UNIVERSE = ["SPY"]\nFX_HEDGE = 1.0' + body)
    assert cl.run_costs(st, {"capital": 1e6}) == {"capital": 1e6, "fx_hedge": 1.0}
    assert cl.run_costs(st, {"fx_hedge": 0.0})["fx_hedge"] == 0.0                         # explicit setting wins


def test_dividend_yields_are_ex_date_cash_over_previous_close(monkeypatch):
    days = pd.bdate_range("2023-12-20", periods=20)
    df = pd.DataFrame({"Close": 100.0, "Dividends": 0.0}, index=days)
    df.loc[days[1], "Dividends"] = 9.0                                                     # before the window: ignored
    df.loc[days[12], "Dividends"] = 2.0
    monkeypatch.setattr(corpactions, "load", lambda syms: ({"X": df}, []))
    idx = days[5:]
    px, dy, missing = corpactions.frames(["X"], idx)
    assert dy["X"].sum() == pytest.approx(0.02) and dy["X"].loc[days[12]] == pytest.approx(0.02)
    assert px["X"].iloc[-1] == 100.0 and missing == []
