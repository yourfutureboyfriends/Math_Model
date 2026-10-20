"""Synthetic listed options: specs, pricing, expiry calendars, notional sizing and settlement in the ledger."""
import numpy as np
import pandas as pd
import pytest

from api.quant import codelab as cl
from api.quant import options as op
from api.quant import sandbox


def test_specs_are_validated_and_named():
    s = op.parse([{"underlying": "spy", "type": "put", "moneyness": 0.95}, {"underlying": "QQQ", "type": "call", "delta": 0.25,
                  "expiry": "weekly"}, {"underlying": "SPY", "type": "put", "tenor_days": 60}])
    assert [x["name"] for x in s] == ["SPY_P95_1M", "QQQ_CD25_W", "SPY_P100_60D"]
    for bad in ([{"underlying": "SPY", "type": "straddle"}], [{"underlying": "SPY", "type": "put", "moneyness": 3}],
                [{"underlying": "SPY", "type": "put", "moneyness": 1, "delta": 0.3}], [{"underlying": "SPY", "type": "put", "foo": 1}],
                [{"underlying": "SPY", "type": "put"}] * 2):
        with pytest.raises(ValueError):
            op.parse(bad)
    h = sandbox.check('UNIVERSE = ["SPY"]\nOPTIONS = [{"underlying": "SPY", "type": "put"}]\ndef strategy(data):\n    return data.close * 0\n')
    assert h["options"][0]["name"] == "SPY_P100_1M"


def test_black_scholes_put_call_parity_and_expiry():
    S, K, T, r, q, v = 100.0, 95.0, 0.25, 0.04, 0.015, 0.22
    c, dc = op.bs(S, K, T, r, q, v, True)
    p, dp = op.bs(S, K, T, r, q, v, False)
    assert c - p == pytest.approx(S * np.exp(-q * T) - K * np.exp(-r * T), abs=1e-9)
    assert dc - dp == pytest.approx(np.exp(-q * T), abs=1e-12)
    assert float(op.bs(90.0, 95.0, 0.0, r, q, v, False)[0]) == 5.0                       # expiry: intrinsic
    assert float(op.bs(100.0, 95.0, 0.0, r, q, v, False)[0]) == 0.0


def test_skew_puts_richer_than_calls_and_delta_strikes():
    atm = 0.2
    lo = op.skewed_vol(atm, 100, 90, 1 / 12, True, False)
    hi = op.skewed_vol(atm, 100, 110, 1 / 12, True, True)
    assert lo > atm > hi
    K = op._strike(100.0, 30 / 365, 0.04, 0.0, 0.2, {"type": "put", "delta": 0.25, "moneyness": 1.0}, True)
    vol = float(op.skewed_vol(0.2, 100, K, 30 / 365, True, False))
    assert abs(float(op.bs(100, K, 30 / 365, 0.04, 0.0, vol, False)[1]) + 0.25) < 0.03   # ≈ a 25-delta put
    assert op.strike_increment(400) == 5.0 and K == round(K)


def test_monthly_expiries_are_third_fridays_and_holidays_move_earlier():
    assert op._third_friday(2020, 3) == pd.Timestamp("2020-03-20")
    sessions = pd.bdate_range("2024-03-01", "2024-06-30").drop(pd.Timestamp("2024-04-19"))   # pretend a holiday
    sch = op._schedule({"expiry": "monthly", "months": 1, "tenor_days": 30}, sessions)
    exp = [sessions[e] for _, e, _ in sch]
    assert exp[:3] == [pd.Timestamp("2024-03-15"), pd.Timestamp("2024-04-18"), pd.Timestamp("2024-05-17")]
    assert all(s2 == e1 for (_, e1, _), (s2, _, _) in zip(sch, sch[1:]))                    # struck at the last expiry
    # the last contract expires after the data ends: live to the last session, with its real expiry date
    assert sch[-1][1] == len(sessions) - 1 and sch[-1][2] == pd.Timestamp("2024-07-19")
    fixed = op._schedule({"expiry": "fixed", "months": 1, "tenor_days": 30}, sessions)
    assert fixed[-1][2] > sessions[-1] and fixed[0][2] == pd.Timestamp("2024-04-01")


def _opt_data(spot, value, settle, vol=1e9):
    idx = pd.bdate_range("2024-01-01", periods=len(spot))
    c = pd.DataFrame({"X": spot, "X_P": value}, index=idx)
    st = pd.DataFrame({"X": np.nan, "X_P": settle}, index=idx)
    opt = {"notional": pd.DataFrame({"X_P": np.asarray(spot) / np.asarray(value)}, index=idx),
           "spot_open": pd.DataFrame({"X_P": spot}, index=idx), "spot": pd.DataFrame({"X_P": spot}, index=idx),
           "roll": pd.DataFrame({"X_P": np.isfinite(settle)}, index=idx)}
    inst = {"X": {"country": "US", "currency": "USD", "sec_fee": False}, "X_P": {"country": "US", "currency": "USD", "sec_fee": False}}
    return cl.Data(c, c, c, c, c * 0 + vol, rf=pd.Series(0.0, index=idx), instruments=inst, settle=st, options=opt)


Z = {"commission_bps": 0, "spread_mult": 0, "impact_coef_bps": 0, "sec_fee_bps": 0, "borrow_fee": 0,
     "financing_spread": 0, "cash_spread": 0, "no_trade_band": 0, "board_lots": 0}


def test_option_weights_are_notional_and_expiry_settles_then_rolls():
    # writing puts on 100% of NAV: spot 100, put worth 2 → 0.01 units of NAV per $ notional; it expires 10 in the money
    n = 12
    spot = np.r_[[100.0] * 5, [90.0] * 7]
    value = np.r_[[2.0] * 5, [10.0] * 2, [3.0] * 5]        # day 6: expiry (new contract struck at 90 worth 3)
    settle = np.full(n, np.nan)
    settle[6] = 10.0
    d = _opt_data(spot, value, settle)
    w = pd.DataFrame(np.nan, index=d.close.index, columns=["X", "X_P"])
    w.iloc[0] = [0.0, -1.0]
    res = cl.backtest(w, d, Z)
    units_before = -1.0 / 100.0                                              # 1.0 × NAV ÷ spot 100
    assert res["nav"].iloc[0] == pytest.approx(1.0)                          # premium in cash, liability marked at 2
    ev = [e for e in res["events"] if e["event"].startswith("option expired")]
    assert ev and ev[0]["value"] == pytest.approx(units_before * 10.0)       # pays the 10 intrinsic per unit
    # rolled: the standing −100% notional is re-established in the new contract at the next open (spot 90)
    assert res["ledger"]["units"]["X_P"] == pytest.approx(-res["nav"].iloc[6] / 90.0, rel=1e-6)
    assert res["execution"]["options_expired"] == 1 and res["execution"]["option_notional_max"] == pytest.approx(1.0, abs=0.12)


def test_short_options_pay_no_stock_borrow():
    n = 10
    d = _opt_data([100.0] * n, [2.0] * n, np.full(n, np.nan))
    w = pd.DataFrame(np.nan, index=d.close.index, columns=["X", "X_P"])
    w.iloc[0] = [0.0, -1.0]
    assert cl.backtest(w, d, {**Z, "borrow_fee": 0.5})["borrow"].sum() == 0.0
