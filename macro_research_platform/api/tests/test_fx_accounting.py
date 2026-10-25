"""Multi-currency fund accounting (BIFS audit #1–#4): a GBP fund holding US, London and Tokyo stocks."""
import pytest

from api.calculations import fx_accounting as fa
from api.calculations.blotter import blotter_totals, cash_balance

# USD per unit: GBP 1.30 today / 1.25 at entry; JPY 0.0065 today / 0.0070 at entry
RATES = {("GBP", None): 1.30, ("GBP", "2026-01-05"): 1.25, ("JPY", None): 0.0065, ("JPY", "2026-01-05"): 0.0070}


@pytest.fixture(autouse=True)
def fixed_rates(monkeypatch):
    monkeypatch.setattr(fa, "usd_per_major", lambda major, on=None: 1.0 if major.upper() == "USD" else RATES[(major.upper(), on)])


def pos(symbol, qty, avg, price, ccy, entry="2026-01-05", **kw):
    return {"symbol": symbol, "quantity": qty, "avg_cost": avg, "current_price": price, "currency": ccy, "entry_date": entry, **kw}


def test_us_stock_in_a_gbp_fund_splits_local_and_fx_pnl():
    p = fa.convert_position(pos("AAPL", 100, 200.0, 250.0, "USD"), "GBP", 1.0)
    assert p["cost_basis"] == pytest.approx(100 * 200 / 1.25)                 # £16,000 at the entry-date rate
    assert p["market_value"] == pytest.approx(100 * 250 / 1.30, abs=0.01)     # £19,230.77 today
    assert p["unrealized_pnl"] == pytest.approx(p["market_value"] - p["cost_basis"], abs=0.01)
    assert p["fx_pnl"] == pytest.approx(100 * 250 * (1 / 1.30 - 1 / 1.25), abs=0.01)   # USD fell vs GBP: a loss
    assert p["local_pnl"] + p["fx_pnl"] == pytest.approx(p["unrealized_pnl"], abs=0.02)
    assert p["value_currency"] == "GBP"


def test_pence_listing_in_a_gbp_fund_is_exact():
    p = fa.convert_position(pos("AZN.L", 100, 11000.0, 12824.0, "GBp"), "GBP", 0.013)
    assert p["market_value"] == 12824.0 and p["cost_basis"] == 11000.0 and p["fx_pnl"] == 0.0


def test_yen_listing_in_a_usd_fund_and_the_cost_rate_on_the_position():
    p = fa.convert_position(pos("7203.T", 100, 2500.0, 3105.0, "JPY"), "USD", 0.0065)
    assert p["cost_basis"] == pytest.approx(100 * 2500 * 0.0070) and p["market_value"] == pytest.approx(100 * 3105 * 0.0065)
    q = fa.convert_position(pos("7203.T", 100, 2500.0, 3105.0, "JPY", cost_usd_per_unit=0.0068), "USD", 0.0065)
    assert q["cost_basis"] == pytest.approx(100 * 2500 * 0.0068)              # the stored rate wins over the entry date


def test_cash_uses_base_currency_cost_not_local_units():
    """Audit finding: 100 AZN.L at 11,000p was subtracted from cash as 1,100,000 (pounds/dollars)."""
    book = [fa.convert_position(pos("AZN.L", 100, 11000.0, 12824.0, "GBp"), "GBP", 0.013),
            fa.convert_position(pos("7203.T", 100, 2500.0, 3105.0, "JPY"), "GBP", 0.0065)]
    cash = cash_balance(1_000_000.0, book, 0.0, 0.0)
    assert cash == pytest.approx(1_000_000 - 11000 - 100 * 2500 * 0.0070 / 1.25, abs=0.01)


def test_blotter_totals_convert_each_fill_at_its_own_rates():
    trades = [{"realized_pnl": 50000.0, "commission": 1000.0, "quantity": 10, "price": 12000, "usd_per_unit": 0.013, "base_per_usd": 1 / 1.3},
              {"realized_pnl": 100.0, "commission": 5.0, "quantity": 1, "price": 100}]          # an old row: face value
    t = blotter_totals(trades)
    assert t["realized_pnl"] == pytest.approx(50000 * 0.01 + 100) and t["commissions"] == pytest.approx(1000 * 0.01 + 5)


def test_fill_rate_is_weighted_into_the_position(tmp_path, monkeypatch):
    from api import blotter_store, portfolio_store
    path = str(tmp_path / "b.db")
    monkeypatch.setattr(portfolio_store, "_db_path", lambda: path)
    blotter_store._initialized.discard(path)
    blotter_store.book_fill("Main", "7203.T", 100, 2500.0, 0.0, "pm", fx={"currency": "JPY", "usd_per_unit": 0.0070})
    blotter_store.book_fill("Main", "7203.T", 300, 2600.0, 0.0, "pm", fx={"currency": "JPY", "usd_per_unit": 0.0066})
    p = portfolio_store.list_positions(None)[0]
    assert p["quantity"] == 400 and p["cost_usd_per_unit"] == pytest.approx((100 * 0.0070 + 300 * 0.0066) / 400)
    blotter_store.book_fill("Main", "7203.T", -200, 3000.0, 0.0, "pm", fx={"currency": "JPY", "usd_per_unit": 0.0060})
    assert portfolio_store.list_positions(None)[0]["cost_usd_per_unit"] == pytest.approx((100 * 0.0070 + 300 * 0.0066) / 400)
