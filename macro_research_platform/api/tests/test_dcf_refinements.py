"""DCF refinements (Oct 2026): reinvestment anchored on actual net capex, cyclical firms earning their cost of
capital on new investment, terminal growth rules, and the through-cycle margin path."""
import pytest

from api.marketdata import dcf


def base(**kw):
    inp = {"symbol": "TEST", "revenue": 100e9, "ebit": 20e9, "shares": 1e9, "price": 100.0, "market_cap": 100e9,
           "currency": "USD", "price_currency": "USD", "debt": 10e9, "cash": 5e9, "risk_free": 0.045, "erp": 0.045,
           "beta": 1.0, "cost_of_debt": 0.055, "tax_marginal": 0.21, "tax_effective": 0.18, "growth": 0.08, "growth_y1": 0.08,
           "sales_to_capital": 2.0, "roic": 0.20, "industry_benchmark": {"industry": "Software"}}
    inp.update(kw)
    return inp


def test_heavy_actual_capex_lowers_value_vs_the_ratio_rule():
    light = dcf.value(base())
    heavy = dcf.value(base(net_capex_to_revenue=0.40))          # an AI build-out: net capex 40% of revenue
    assert heavy["per_share"] < 0.8 * light["per_share"]
    assert heavy["projection"][0]["reinvestment"] > 3 * light["projection"][0]["reinvestment"]
    # by year 6 the anchor has faded: reinvestment follows the sales-to-capital rule again
    assert heavy["projection"][5]["reinvestment"] == pytest.approx(light["projection"][5]["reinvestment"], rel=1e-9)


def test_an_explicit_sales_to_capital_overrides_the_anchor():
    a = dcf.value(base(net_capex_to_revenue=0.40), sales_to_capital=2.0)
    b = dcf.value(base(), sales_to_capital=2.0)
    assert a["per_share"] == pytest.approx(b["per_share"])


def test_cyclical_firms_earn_their_cost_of_capital_on_new_investment():
    franchise = dcf.value(base(cyclical=False), method="two_stage")     # the two-stage terminal RONIC rule
    cyclical = dcf.value(base(cyclical=True), method="two_stage")
    assert cyclical["assumptions"]["ronic"] == pytest.approx(cyclical["assumptions"]["discount_terminal"])
    assert franchise["assumptions"]["ronic"] > franchise["assumptions"]["discount_terminal"]
    assert cyclical["per_share"] < franchise["per_share"]


def test_terminal_growth_rules(monkeypatch):
    monkeypatch.setattr(dcf, "TERMINAL_RULE", "rf")
    assert dcf.default_terminal_growth(base(risk_free=0.05)) == pytest.approx(0.05)
    monkeypatch.setattr(dcf, "TERMINAL_RULE", "gdp")
    assert dcf.default_terminal_growth(base(risk_free=0.05)) == pytest.approx(dcf.LR_NOMINAL_GROWTH["USD"])
    assert dcf.default_terminal_growth(base(risk_free=0.006, currency="CHF")) == pytest.approx(0.006)   # rf below the cap
    assert dcf.default_terminal_growth(base(risk_free=-0.002, currency="JPY")) == 0.0


def test_peak_cyclical_margin_returns_to_through_cycle_in_three_years():
    v = dcf.value(base(ebit=40e9, target_margin_default=0.20, margin_fade_years=dcf.CYCLICAL_FADE_YEARS))
    m = [r["margin"] for r in v["projection"]]
    assert m[0] < 0.40 and m[2] == pytest.approx(0.20) and m[9] == pytest.approx(0.20)
