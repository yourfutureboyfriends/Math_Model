"""Bond maths, implied vol, formula charts, deal parsing, segment labels (offline)."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from api.marketdata import corporate as C, fixed_income as F, workbench as W


def test_par_bond_yields_its_coupon():
    m = F.bond_measures(0.04, date(2036, 10, 15), date(2026, 10, 15), 2, price=100)
    assert m["ytm"] == pytest.approx(0.04, abs=1e-7)
    assert m["accrued"] == pytest.approx(0, abs=1e-9)
    assert 8.0 < m["modified"] < 8.3                               # 10-year 4% bond


def test_price_yield_round_trip_and_accrual():
    m = F.bond_measures(0.05, date(2031, 2, 15), date(2026, 5, 15), 2, ytm=0.06)
    back = F.bond_measures(0.05, date(2031, 2, 15), date(2026, 5, 15), 2, price=m["clean"])
    assert back["ytm"] == pytest.approx(0.06, abs=1e-7)
    assert m["accrued"] == pytest.approx(2.5 * 89 / 181, rel=1e-3)   # 89 of 181 days since 15 Feb
    assert m["dv01"] == pytest.approx(m["modified"] * m["dirty"] / 1e4)


def test_bond_calc_grid_is_monotonic():
    out = F.bond_calc(0.0425, "2036-08-15", price=98.5, settle="2026-10-13")
    prices = [g["price"] for g in out["grid"]]
    assert all(a > b for a, b in zip(prices, prices[1:]))
    zero = next(g for g in out["grid"] if g["shift_bp"] == 0)
    assert zero["price"] == pytest.approx(98.5, abs=1e-6)


def test_black_scholes_implied_vol_recovers_sigma():
    for call in (True, False):
        for K in (80, 100, 120):
            p = W._bs_price(100, K, 0.5, 0.04, 0.01, 0.27, call)
            assert W._implied_vol(p, 100, K, 0.5, 0.04, 0.01, call) == pytest.approx(0.27, abs=1e-4)
    assert W._implied_vol(0.0, 100, 50, 0.5, 0.04, 0.0, True) is None  # below intrinsic


def test_formula_parser_and_sandbox(monkeypatch):
    idx = pd.bdate_range("2020-01-01", periods=1500)
    data = {"AAA": pd.Series(np.linspace(10, 20, len(idx)), index=idx), "BBB": pd.Series(np.full(len(idx), 5.0), index=idx),
            "BTC-USD": pd.Series(np.linspace(1, 2, len(idx)), index=idx)}
    monkeypatch.setattr(W, "_series", lambda k, start: data[k])
    out = W.formula_chart(["AAA/BBB", "{BTC-USD}*2", "AAA^2/100", "ma(AAA,10)"], "max")
    last = {l["expr"]: l["last"] for l in out["lines"]}
    assert last["AAA/BBB"] == pytest.approx(4.0)
    assert last["{BTC-USD}*2"] == pytest.approx(4.0)
    assert last["AAA^2/100"] == pytest.approx(4.0)
    for bad in ["__import__('os')", "AAA.__class__", "[AAA]", "lambda: 1"]:
        with pytest.raises(W.NotFound):
            W.formula_chart([bad])


def test_expected_close_and_names():
    assert C._expected_close("The transaction is expected to close in the first half of 2027, subject to") == "2027-06-30"
    assert C._expected_close("expected to be completed in the fourth quarter of 2026") == "2026-12-31"
    assert C._norm_name("MarketAxess Holdings Inc.") == C._norm_name("MARKETAXESS HOLDINGS INC")
    assert C._member_label("aapl:IPhoneMember") == "iPhone"
    assert C._member_label("aapl:WearablesHomeandAccessoriesMember") == "Wearables Home & Accessories"
    assert C._member_label("country:CN") == "China"


def test_exchanges_shape():
    out = W.exchanges()
    assert len(out["exchanges"]) >= 20
    assert all(x["status"] in ("open", "closed", "lunch break") for x in out["exchanges"])
