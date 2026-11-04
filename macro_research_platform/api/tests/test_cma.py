"""Known-answer tests for the shared long-term CMA builder (observed building blocks)."""
from datetime import datetime
from api.calculations.cma import longterm_forecasts

EY = {"SPY": 4.0, "IWM": 5.0, "EFA": 6.5, "EEM": 8.0}      # earnings yields, %
VOLS = {"SPY": 15.0, "IWM": 20.0, "EFA": 14.0, "EEM": 18.0, "AGG": 6.0}


def _by_name(out):
    return {f["assetClass"]: f for f in out["forecasts"]}


def test_bond_leg_equals_ten_year():
    out = longterm_forecasts(4.6, datetime(2026, 1, 1))
    assert _by_name(out)["US Bonds"]["expectedReturn"] == 4.6


def test_equity_is_earnings_yield_plus_breakeven():
    out = longterm_forecasts(4.6, datetime(2026, 1, 1), breakeven=2.3, earnings_yields=EY)
    f = _by_name(out)
    assert f["US Large Cap"]["expectedReturn"] == round(4.0 + 2.3, 1)
    assert f["Emerging Markets"]["expectedReturn"] == round(8.0 + 2.3, 1)
    assert f["US Large Cap"]["components"] == {"earnings_yield": 4.0, "inflation": 2.3}


def test_equities_omitted_without_valuation_or_breakeven():
    assert set(_by_name(longterm_forecasts(4.6, earnings_yields=EY))) == {"US Bonds"}
    partial = longterm_forecasts(4.6, breakeven=2.3, earnings_yields={"SPY": 4.0})
    assert set(_by_name(partial)) == {"US Large Cap", "US Bonds"}


def test_sharpe_is_excess_return_over_realized_vol():
    out = longterm_forecasts(4.6, risk_free=3.9, breakeven=2.3, earnings_yields=EY, vols=VOLS)
    lc = _by_name(out)["US Large Cap"]
    assert lc["volatility"] == 15.0
    assert lc["sharpeRatio"] == round((4.0 + 2.3 - 3.9) / 15.0, 2)


def test_no_sharpe_without_risk_free_or_vol():
    out = longterm_forecasts(4.6, breakeven=2.3, earnings_yields=EY, vols=VOLS)
    assert all(f["sharpeRatio"] is None for f in out["forecasts"])
    out = longterm_forecasts(4.6, risk_free=3.9, breakeven=2.3, earnings_yields=EY)
    assert all(f["volatility"] is None and f["sharpeRatio"] is None for f in out["forecasts"])


def test_no_assumed_confidence():
    out = longterm_forecasts(4.6, breakeven=2.3, earnings_yields=EY)
    assert all(f["confidence"] is None for f in out["forecasts"])


def test_unavailable_when_no_inputs():
    out = longterm_forecasts(None)
    assert out["available"] is False and out["forecasts"] == []


def test_methodology_is_honest_not_gmo_model():
    out = longterm_forecasts(4.6)
    assert "building-block" in out["methodology"].lower()
    assert not out["methodology"].startswith("GMO Model")
    assert set(out) >= {"forecasts", "methodology", "asOfDate", "disclaimer", "lastUpdated"}
