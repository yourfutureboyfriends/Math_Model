"""Known-answer tests for Bridgewater 3-stream signal agreement (Phase 3)."""
from api.calculations.stream_agreement import (
    macro_stream, intermarket_stream, flows_stream, stream_agreement,
)


def test_macro_stream_risk_on():
    # strong growth + loose liquidity + low inflation -> risk-on
    assert macro_stream(growth=0.7, inflation=0.3, liquidity=0.7) == 1


def test_macro_stream_risk_off():
    assert macro_stream(growth=0.3, inflation=0.8, liquidity=0.3) == -1


def test_intermarket_inversion_is_risk_off():
    assert intermarket_stream(curve_2s10s=-0.3, hy_spread=600, risk_appetite=0.3) == -1


def test_flows_crowded_shorts_are_contrarian_risk_on():
    assert flows_stream(cot_extremes_long=0, cot_extremes_short=2, put_call=1.3) == 1


def test_all_three_agree_high_conviction():
    r = stream_agreement(1, 1, 1)
    assert r["agreeing_streams"] == 3
    assert r["conviction"] == "high"
    assert r["sizing_multiplier"] == 1.5
    assert r["consensus_direction"] == "risk-on"


def test_two_agree_one_opposes_is_conflicted():
    r = stream_agreement(1, 1, -1)
    assert r["agreeing_streams"] == 2
    assert r["opposing_streams"] == 1
    assert r["conviction"] == "conflicted"
    assert r["sizing_multiplier"] == 0.7


def test_two_agree_one_neutral_is_moderate():
    r = stream_agreement(1, 1, 0)
    assert r["conviction"] == "moderate"
    assert r["sizing_multiplier"] == 1.2


def test_all_neutral_is_low_conviction():
    r = stream_agreement(0, 0, 0)
    assert r["conviction"] == "low"
    assert r["consensus_direction"] == "neutral / conflicted"
    assert r["sizing_multiplier"] == 0.5
