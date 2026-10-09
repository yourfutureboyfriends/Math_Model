"""Markets functions, offline: option maths, DCF, dividend streaks, industry mapping, foreign
listing lines, and the per-user watchlists / alerts / journal."""
import math
import sqlite3
import sys
import types

import numpy as np
import pandas as pd
import pytest

from api.marketdata import core, security, usertools


@pytest.fixture(autouse=True)
def clear():
    core._cache.clear()
    yield
    core._cache.clear()


# ── options ──────────────────────────────────────────────────────────────────
def test_black_scholes_iv_round_trip_and_parity():
    S, T, r, q = 100.0, 0.25, 0.04, 0.01
    K = np.array([80.0, 100.0, 120.0])
    sig = np.array([0.35, 0.25, 0.30])
    for call in (True, False):
        price = security.bs_price(S, K, T, r, q, sig, call)
        iv = security.implied_vol(price, S, K, T, r, q, call)
        assert np.allclose(iv, sig, atol=1e-4)
    gc = security.bs_greeks(S, K, T, r, q, sig, True)
    gp = security.bs_greeks(S, K, T, r, q, sig, False)
    assert np.allclose(gc["delta"] - gp["delta"], math.exp(-q * T), atol=1e-9)      # put–call delta parity
    assert (gc["gamma"] > 0).all() and (gc["vega"] > 0).all() and (gc["theta"] < 0).all()


def test_implied_vol_nan_below_intrinsic():
    iv = security.implied_vol(np.array([5.0]), 100.0, np.array([80.0]), 0.25, 0.04, 0.0, True)   # intrinsic ≈ 20.8
    assert np.isnan(iv[0])


# ── DCF ──────────────────────────────────────────────────────────────────────
def _inp(**over):
    base = {"symbol": "X", "currency": "USD", "price_currency": "USD", "price": 50.0, "revenue": 1000.0, "ebit": 200.0,
            "shares": 100.0, "market_cap": 5000.0, "debt": 1000.0, "cash": 200.0, "leases": 0.0, "minority_interest": 0.0,
            "beta": 1.0, "risk_free": 0.04, "cost_of_debt": 0.05, "tax_marginal": 0.25, "tax_effective": 0.25,
            "sales_to_capital": 2.0, "growth": 0.05, "roic": 0.15, "is_financial": False, "risk_free_matched": True}
    base.update(over)
    return base


def test_dcf_uses_wacc_for_fcff_and_market_weights():
    from api.marketdata import dcf
    w = dcf.wacc(_inp(), erp=0.05)
    ke, kd = 0.04 + 0.05, 0.05 * 0.75
    assert w["cost_of_equity"] == pytest.approx(ke)
    assert w["wacc"] == pytest.approx((5000 * ke + 1000 * kd) / 6000)       # FCFF discounted at WACC, not ke


def test_dcf_hand_check_terminal_value_driver_formula():
    from api.marketdata import dcf
    v = dcf.value(_inp(), growth=0.03, terminal_growth=0.03, years=3, discount=0.08, ronic=0.12, mid_year=False)
    rev, pv = 1000.0, 0.0
    for y in range(1, 4):                        # constant growth = terminal → fade is flat
        new = rev * 1.03
        fcff = new * 0.2 * 0.75 - (new - rev) / 2.0
        pv += fcff / 1.08 ** y
        rev = new
    tv = rev * 1.03 * 0.2 * 0.75 * (1 - 0.03 / 0.12) / (0.08 - 0.03)
    ev = pv + tv / 1.08 ** 3
    assert v["enterprise_value"] == pytest.approx(ev)
    assert v["per_share"] == pytest.approx((ev - 1000 + 200) / 100)


def test_dcf_mid_year_raises_value_and_growth_fades():
    from api.marketdata import dcf
    a = dcf.value(_inp(), growth=0.20, terminal_growth=0.02, years=10, discount=0.09, mid_year=False)
    b = dcf.value(_inp(), growth=0.20, terminal_growth=0.02, years=10, discount=0.09, mid_year=True)
    assert b["per_share"] > a["per_share"]
    gs = [r["growth"] for r in b["projection"]]
    assert gs[0] == pytest.approx(0.20) and gs[-1] == pytest.approx(0.02) and all(x >= y for x, y in zip(gs, gs[1:]))


def test_dcf_checks_and_reverse():
    from api.marketdata import dcf
    v = dcf.value(_inp(is_financial=True), terminal_growth=0.05)
    assert any("Financial firm" in c for c in v["checks"]) and any("risk-free" in c for c in v["checks"])
    with pytest.raises(core.NotFound):
        dcf.value(_inp(), terminal_growth=0.06, discount=0.05)
    g = dcf.reverse(_inp(price=40.0), terminal_growth=0.02, discount=0.09)
    assert g is not None and dcf.value(_inp(), growth=g, terminal_growth=0.02, discount=0.09)["per_share"] == pytest.approx(40.0, rel=1e-4)


# ── dividends ────────────────────────────────────────────────────────────────
def test_dividend_streak_ignores_one_bad_payment(monkeypatch):
    idx = pd.to_datetime([f"{y}-{m:02d}-15" for y in range(2015, 2026) for m in (3, 6, 9, 12)])
    vals = [0.10 + 0.01 * (d.year - 2015) for d in idx]
    s = pd.Series(vals, index=idx)
    s[pd.Timestamp("2018-06-15")] = 0.50                       # a bad / special record
    class T:
        dividends = s
        splits = pd.Series(dtype=float)
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=lambda sym: T()))
    monkeypatch.setattr(security, "_info", lambda sym: {"currency": "USD", "dividendYield": 2.5})
    d = security.dividends("X")
    assert d["consecutive_increases"] == 10 and d["dividend_yield"] == pytest.approx(0.025)


# ── classification helpers ───────────────────────────────────────────────────
def test_industry_names_map_to_screener_labels():
    assert security._screen_industry("Software - Application") == "Software—Application"
    assert security._screen_industry("Auto Manufacturers") == "Auto Manufacturers"
    assert security._screen_industry(None) is None


def test_foreign_share_lines():
    assert security._foreign_line("1BMW.MI") and security._foreign_line("0YG8.L")
    assert not security._foreign_line("ENI.MI") and not security._foreign_line("HSBA.L")


# ── user tools ───────────────────────────────────────────────────────────────
@pytest.fixture()
def db(tmp_path, monkeypatch):
    def conn():
        c = sqlite3.connect(tmp_path / "u.db")
        c.row_factory = sqlite3.Row
        return c
    monkeypatch.setattr(usertools, "_conn", conn)
    monkeypatch.setattr(usertools, "_ready", False)


def test_watchlists_crud_and_validation(db):
    lists = usertools.list_watchlists("ann")
    assert len(lists) == 1 and "^VIX" in lists[0]["symbols"]          # starter list, index tickers allowed
    w = usertools.create_watchlist("ann", "Tech", ["nvda", "msft", "NVDA"])
    assert w["symbols"] == ["NVDA", "MSFT"]
    usertools.update_watchlist("ann", w["id"], None, ["AAPL"])
    assert [l["symbols"] for l in usertools.list_watchlists("ann") if l["id"] == w["id"]] == [["AAPL"]]
    with pytest.raises(LookupError):
        usertools.update_watchlist("bob", w["id"], "x", None)        # other users can't touch it
    with pytest.raises(ValueError):
        usertools.create_watchlist("ann", "Bad", ["not a ticker"])


def test_alert_rules_and_trigger(db, monkeypatch):
    assert usertools.fires("above", 100, 101, None) and not usertools.fires("above", 100, 99, None)
    assert usertools.fires("change_down", 3, None, -0.035) and not usertools.fires("change_down", 3, None, -0.02)
    a = usertools.create_alert("ann", "spy", "above", 500)
    usertools.create_alert("ann", "QQQ", "below", 100)
    monkeypatch.setattr(usertools, "quotes", lambda syms: [{"symbol": "SPY", "price": 510.0, "change_1d": 0.01},
                                                            {"symbol": "QQQ", "price": 400.0, "change_1d": 0.0}])
    assert usertools.check_alerts() == {"checked": 2, "triggered": 1}
    trig = usertools.triggered_unseen("ann")
    assert [t["id"] for t in trig] == [a["id"]] and trig[0]["triggered_price"] == 510.0
    assert usertools.mark_seen("ann") == 1 and usertools.triggered_unseen("ann") == []
    with pytest.raises(ValueError):
        usertools.create_alert("ann", "SPY", "change_up", 150)


def test_journal_pnl_and_stats(db):
    usertools.create_journal("ann", {"symbol": "aapl", "side": "long", "quantity": 10, "entry": 100, "exit": 110, "tags": ["momentum"]})
    usertools.create_journal("ann", {"symbol": "TSLA", "side": "short", "quantity": 5, "entry": 200, "exit": 220})
    usertools.create_journal("ann", {"symbol": "MSFT", "side": "idea", "thesis": "watch Azure growth"})
    j = usertools.list_journal("ann")
    rows = {r["symbol"]: r for r in j["entries"]}
    assert rows["AAPL"]["pnl"] == pytest.approx(100) and rows["AAPL"]["status"] == "closed"
    assert rows["TSLA"]["return_pct"] == pytest.approx(-0.10) and rows["TSLA"]["pnl"] == pytest.approx(-100)
    assert j["stats"]["closed"] == 2 and j["stats"]["win_rate"] == pytest.approx(0.5) and j["stats"]["open"] == 1
    with pytest.raises(ValueError):
        usertools.create_journal("ann", {"side": "sideways"})
