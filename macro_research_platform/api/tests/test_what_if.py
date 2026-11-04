"""What-if scenarios: slider → factor-shock maths and the portfolio aggregation (api/what_if.py)."""
import pytest

from api import what_if


def test_sliders_map_to_factor_returns():
    s = what_if.slider_shocks({"equity_pct": -0.2, "rates_bp": 100, "credit_bp": 200, "commodities_pct": 0.1,
                               "usd_pct": 0.05, "vix_pts": 10}, vix_level=20.0)
    assert s["equity"] == -0.2
    assert s["rates"] == pytest.approx(-0.165)          # +100bp on a ~16.5-duration long Treasury fund
    assert s["credit"] == pytest.approx(-0.07)          # +200bp on a ~3.5 spread duration
    assert s["commodity"] == 0.1 and s["usd"] == 0.05
    assert s["volatility"] == pytest.approx(0.5)        # +10 pts from a VIX of 20


def test_sliders_are_clamped_and_vix_needs_a_level():
    s = what_if.slider_shocks({"equity_pct": -5, "rates_bp": 10_000, "vix_pts": 30}, vix_level=None)
    lo, _ = what_if.LIMITS["equity_pct"]
    assert s["equity"] == lo
    assert s["rates"] == pytest.approx(-what_if.TLT_DURATION * what_if.LIMITS["rates_bp"][1] / 1e4)
    assert s["volatility"] == 0.0


def test_portfolio_move_weights_betas_and_reports_unestimated_assets():
    loads = {"SPY": {"equity": 1.0}, "TLT": {"rates": 1.0}}
    out = what_if._portfolio_move({"Eq": 0.6, "Bonds": 0.3, "Mystery": 0.1, "Zero": 0.0},
                                  {"Eq": "SPY", "Bonds": "TLT", "Mystery": "XYZ", "Zero": "SPY"},
                                  loads, {"equity": -0.3, "rates": 0.1})
    assert out["return"] == pytest.approx(0.6 * -0.3 + 0.3 * 0.1)
    assert [a["asset"] for a in out["by_asset"]] == ["Eq", "Bonds"]          # worst contribution first
    assert out["not_estimated"] == ["Mystery"]
