"""A missing recession model must not read as "no recession risk".

`get_recommendations_data` used to substitute 0.0 for an unavailable probability. That satisfied
`rec_prob < 0.2`, so a FRED outage combined with a benign risk-appetite signal produced the most
bullish stance on the platform, erased the `- rec_prob * 0.15` penalty in the SPY target and the
`+ rec_prob * 0.10` term in the GLD hedge, and could not trigger DEFENSIVE because a missing VIX
also became 0. The backup regime classifier had the same shape: a dead-centre reading matched no
quadrant and fell through to "goldilocks".

Least information produced most bullish advice. These pin the other direction.
"""
import asyncio
from types import SimpleNamespace

import pytest

from api.handlers import business_handler as bh


def _dashboard(*, regime=None, growth=70.0, inflation=30.0, risk=80.0, liquidity=60.0,
               ten_yr=4.0, vix=15.0, recession=0.10, confidence=0.8):
    return SimpleNamespace(
        regime=SimpleNamespace(current=regime, confidenceScore=confidence),
        scores=SimpleNamespace(growth=growth, inflation=inflation, risk=risk, liquidity=liquidity),
        keyMetrics=SimpleNamespace(tenYearYield=ten_yr, vix=vix),
        recession=SimpleNamespace(probability=recession),
    )


@pytest.fixture
def patched(monkeypatch):
    """Stub the two awaits so the test exercises the decision logic, not the data pipeline."""
    async def _no_expected_returns():
        return {"returns": []}
    monkeypatch.setattr(bh, "get_expected_returns_data", _no_expected_returns)

    def _run(dashboard):
        async def _fake(mode="live"):
            return dashboard
        import api.handlers.dashboard_handler as dh
        monkeypatch.setattr(dh, "get_dashboard_data", _fake)
        return asyncio.run(bh.get_recommendations_data())
    return _run


def _sizing(result, asset):
    return next(r for r in result["position_sizing"] if r["asset"] == asset)["target"]


def _scorecard(result, signal):
    return next(r for r in result["signal_scorecard"] if r["signal"] == signal)


def test_missing_recession_data_cannot_produce_a_risk_on_stance(patched):
    # risk appetite 0.80 with an unknown recession probability: the old code returned RISK-ON.
    out = patched(_dashboard(recession=None, vix=None))
    assert out["summary"]["overall_position"] == "BALANCED"
    assert out["summary"]["degraded_inputs"] == ["recession_probability", "vix"]


def test_missing_recession_data_neutralises_sizing_rather_than_maximising_it(patched):
    degraded = patched(_dashboard(recession=None, vix=None))
    no_risk = patched(_dashboard(recession=0.0))          # what the old fallback effectively was
    # growth 0.70 -> 0.15 + (0.70-0.30)*0.2 = 0.23 with no recession penalty at all. Unknown now
    # takes the midpoint of its own range (0.5) instead of 0.0, so it must sit strictly below the
    # no-risk case and below the penalty-free ceiling. Compared as relationships, not exact
    # floats: the served targets are rounded to 2dp and 0.215/0.155 sit on a rounding knife-edge.
    spy_degraded, spy_no_risk = _sizing(degraded, "SPY"), _sizing(no_risk, "SPY")
    assert spy_degraded < spy_no_risk <= 0.23
    assert spy_degraded == pytest.approx(spy_no_risk - 0.5 * 0.15, abs=0.011)
    # the hedge must not collapse to its floor just because the input is missing
    assert _sizing(degraded, "GLD") > _sizing(no_risk, "GLD")
    assert _sizing(degraded, "VIX Hedge") > 0.02


def test_known_inputs_still_reach_risk_on_and_report_nothing_degraded(patched):
    out = patched(_dashboard(recession=0.10, vix=15.0, risk=80.0))
    assert out["summary"]["overall_position"] == "RISK-ON"
    assert out["summary"]["degraded_inputs"] == []
    # the real probability still drives the sizing, not the midpoint: a known 10% must size above
    # the unknown case and below no recession risk at all.
    spy = _sizing(out, "SPY")
    assert _sizing(patched(_dashboard(recession=None, vix=None)), "SPY") < spy < _sizing(
        patched(_dashboard(recession=0.0)), "SPY")


def test_high_recession_probability_still_goes_defensive(patched):
    out = patched(_dashboard(recession=0.55, vix=18.0, risk=80.0))
    assert out["summary"]["overall_position"] == "DEFENSIVE"
    assert out["summary"]["degraded_inputs"] == []


def test_missing_vix_alone_is_reported_and_does_not_read_as_calm(patched):
    out = patched(_dashboard(recession=0.10, vix=None, risk=80.0))
    assert out["summary"]["degraded_inputs"] == ["vix"]
    assert out["summary"]["overall_position"] == "BALANCED"


def test_unclassifiable_regime_is_unknown_not_goldilocks(patched):
    # growth 0.50 / inflation 0.45 / liquidity 0.50 matches none of the four quadrants.
    out = patched(_dashboard(regime=None, growth=50.0, inflation=45.0, liquidity=50.0))
    assert out["summary"]["regime"] == "Unknown"
    assert _scorecard(out, "Regime")["status"] == "Grey"
    assert any("Mixed signals" in t for t in out["summary"]["key_themes"])


def test_missing_recession_probability_still_displays_as_na(patched):
    out = patched(_dashboard(recession=None, vix=None))
    assert _scorecard(out, "Recession Risk")["value"] == "n/a"
    assert _scorecard(out, "Recession Risk")["status"] == "Grey"
    assert "recession probability n/a" in out["summary"]["risk_assessment"]


def test_a_known_recession_signal_still_goes_defensive_when_vix_is_missing(patched):
    """The cap exists to stop missing data leaning IN; it must not suppress a defensive trigger
    the available data fully justifies. Gating the whole chain on both inputs being present made a
    55% recession probability with the VIX feed down read BALANCED."""
    out = patched(_dashboard(recession=0.55, vix=None, risk=80.0))
    assert out["summary"]["overall_position"] == "DEFENSIVE"
    assert out["summary"]["degraded_inputs"] == ["vix"]


def test_a_known_high_vix_still_goes_defensive_when_the_recession_model_is_down(patched):
    out = patched(_dashboard(recession=None, vix=38.0, risk=80.0))
    assert out["summary"]["overall_position"] == "DEFENSIVE"
    assert out["summary"]["degraded_inputs"] == ["recession_probability"]
