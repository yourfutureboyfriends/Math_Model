"""Known-answer tests for the shared long-term CMA builder (dedup source of truth)."""
from datetime import datetime
from api.calculations.cma import longterm_forecasts, EQUITY_ERP, DEFAULT_10Y


def _by_name(out):
    return {f["assetClass"]: f for f in out["forecasts"]}


def test_bond_leg_equals_ten_year():
    out = longterm_forecasts(4.6, datetime(2026, 1, 1))
    assert _by_name(out)["US Bonds"]["expectedReturn"] == 4.6


def test_equity_is_ten_year_plus_erp():
    out = longterm_forecasts(4.6, datetime(2026, 1, 1))
    assert _by_name(out)["US Large Cap"]["expectedReturn"] == round(4.6 + EQUITY_ERP, 1)
    # EM carries the +2.5 offset on top of large cap
    assert _by_name(out)["Emerging Markets"]["expectedReturn"] == round(4.6 + EQUITY_ERP + 2.5, 1)


def test_sharpe_is_return_over_vol():
    out = longterm_forecasts(4.6)
    lc = _by_name(out)["US Large Cap"]
    assert lc["sharpeRatio"] == round(lc["expectedReturn"] / lc["volatility"], 2)


def test_fallback_when_no_ten_year():
    out = longterm_forecasts(None)
    assert _by_name(out)["US Bonds"]["expectedReturn"] == DEFAULT_10Y


def test_methodology_is_honest_not_gmo_model():
    out = longterm_forecasts(4.6)
    assert "building-block" in out["methodology"].lower()
    assert not out["methodology"].startswith("GMO Model")
    assert set(out) >= {"forecasts", "methodology", "asOfDate", "disclaimer", "lastUpdated"}
