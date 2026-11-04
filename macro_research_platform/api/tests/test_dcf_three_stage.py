"""Three-stage DCF (Morningstar's structure): moat-driven fade, RONIC = WACC in perpetuity, building-block cost of
equity, effective-tax fallback, growth half-life and the uncertainty-based margin of safety."""
import pytest

from api.marketdata import dcf
from api.tests.test_dcf_refinements import base


def test_moat_rating_from_return_history():
    assert dcf.moat(base(roic=0.35, roic_history=[0.33, 0.30, 0.36]), 0.08)["rating"] == "wide"
    assert dcf.moat(base(roic=0.13, roic_history=[0.12, 0.11, 0.05]), 0.08)["rating"] == "narrow"
    assert dcf.moat(base(roic=0.06, roic_history=[0.07, 0.09, 0.05]), 0.08)["rating"] == "none"
    assert dcf.moat(base(roic=0.35, roic_history=[0.33, 0.30, 0.36], cyclical=True), 0.08)["rating"] == "narrow"
    assert dcf.moat(base(roic=None, roic_history=[]), 0.08)["fade_years"] == dcf.MOAT_FADE_YEARS["none"]


def test_three_stage_perpetuity_is_growth_neutral():
    # RONIC = WACC in perpetuity: terminal value = NOPAT(N+1) / WACC, so the perpetual growth rate barely matters
    lo = dcf.value(base(), method="three_stage", terminal_growth=0.02)
    hi = dcf.value(base(), method="three_stage", terminal_growth=0.04)
    a = hi["assumptions"]
    assert a["ronic"] == pytest.approx(a["discount_terminal"])
    nopat_next = hi["projection"][-1]["nopat"] * 1.04
    assert hi["terminal_value"] == pytest.approx(nopat_next / a["discount_terminal"], rel=1e-9)
    two_lo = dcf.value(base(), method="two_stage", terminal_growth=0.02)
    two_hi = dcf.value(base(), method="two_stage", terminal_growth=0.04)
    assert abs(hi["per_share"] / lo["per_share"] - 1) < abs(two_hi["per_share"] / two_lo["per_share"] - 1)


def test_longer_moat_fade_is_worth_more_and_ronic_fades_to_wacc():
    short = dcf.value(base(), method="three_stage", fade_years=1)
    long_ = dcf.value(base(), method="three_stage", fade_years=20)
    assert long_["per_share"] > short["per_share"]
    fade = [r for r in long_["projection"] if r["stage"] == "fade"]
    assert len(fade) == 20 and fade[0]["ronic"] > fade[-1]["ronic"]
    assert fade[-1]["ronic"] == pytest.approx(long_["assumptions"]["discount_terminal"])


def test_building_block_cost_of_equity():
    usd = dcf.building_block_ke(base(), 1.0)
    assert usd["cost_of_equity"] == pytest.approx(dcf.BB_REAL_RETURN + dcf.BB_INFLATION_USD)          # 9% for average risk
    assert dcf.building_block_ke(base(), 0.6)["cost_of_equity"] == pytest.approx(usd["cost_of_equity"] - 0.015)
    assert dcf.building_block_ke(base(), 2.2)["cost_of_equity"] == pytest.approx(usd["cost_of_equity"] + 0.045)
    w = dcf.wacc(base(), ke_method="building_block")
    assert w["ke_method"] == "building_block" and w["cost_of_equity"] == pytest.approx(usd["cost_of_equity"])


def test_growth_half_life_decays_consensus_growth(monkeypatch):
    monkeypatch.setattr(dcf, "GROWTH_HALF_LIFE", 2.0)
    v = dcf.value(base(growth=0.40, growth_y1=0.40), method="three_stage", years=10)
    g = [r["growth"] for r in v["projection"]]
    gT = v["assumptions"]["terminal_growth"]
    assert g[2] == pytest.approx(0.40) and g[4] == pytest.approx(gT + (0.40 - gT) * 0.5)   # two years after the consensus
    assert g[9] < 0.10


def test_uncertainty_margin_of_safety():
    low, high, ext = dcf.uncertainty(0.15), dcf.uncertainty(0.40), dcf.uncertainty(0.90)
    assert (low["rating"], low["buy_below"], low["sell_above"]) == ("low", 0.8, 1.25)
    assert (high["rating"], high["buy_below"], high["sell_above"]) == ("high", 0.6, 1.55)
    assert ext["rating"] == "extreme" and ext["sell_above"] == pytest.approx(4.0)
    assert dcf.uncertainty(0.15, terminal_share=0.9)["rating"] == "medium"          # mostly terminal value: one notch up
