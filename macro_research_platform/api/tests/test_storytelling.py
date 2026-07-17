"""
Known-answer tests for signal storytelling / attribution (Phase 2).
Run: pytest api/tests/test_storytelling.py
"""
from api.calculations.storytelling import (
    explain_growth, explain_inflation, explain_liquidity, explain_risk,
)


def test_growth_explains_positive_momentum():
    # Rising SPX -> growth improving, recent return is the driver, explanation mentions S&P.
    r = explain_growth(6000.0, [5000, 5200, 5500, 5800])
    assert r["signal"] == "Growth"
    assert "S&P 500" in r["explanation_text"]
    assert r["contributions"][0]["contribution"] > 0        # positive momentum
    assert r["driver"] in ("SPX recent return", "SPX trailing return")


def test_inflation_reports_curve_spread():
    r = explain_inflation(4.5, 4.0)                          # +50bps steep
    assert "10Y−2Y" in r["explanation_text"]
    assert "+50bps" in r["explanation_text"]
    assert r["trend"] in ("steepening", "stable", "flattening")


def test_inflation_inverted_curve():
    r = explain_inflation(4.0, 4.5)                          # inverted
    assert r["trend"] == "inverted"


def test_liquidity_driver_is_ranked_first():
    r = explain_liquidity(dxy=95.0, ten_yr=4.5, fed_rate=5.0)
    assert r["signal"] == "Liquidity"
    # driver must be the larger-magnitude contribution and match the ranked head
    assert r["driver"].startswith(r["contributions"][0]["input"][:6])
    assert "score" in r["explanation_text"]


def test_risk_reads_vix():
    calm = explain_risk(12.0)
    stress = explain_risk(35.0)
    assert calm["score"] > stress["score"]                  # low VIX = more risk appetite
    assert "VIX at 12.0" in calm["explanation_text"]
    assert stress["trend"] == "stress"


def test_all_return_ranked_contributions():
    for r in (explain_growth(5800, [5700, 5750, 5800]),
              explain_inflation(4.5, 4.2), explain_liquidity(104, 4.5, 5.0),
              explain_risk(18)):
        c = r["contributions"]
        mags = [abs(x["contribution"]) for x in c]
        assert mags == sorted(mags, reverse=True)           # ranked by |contribution|
