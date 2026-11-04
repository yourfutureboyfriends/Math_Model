"""
Known-answer tests for signal storytelling / attribution (Phase 2).
Run: pytest api/tests/test_storytelling.py
"""
from api.calculations.storytelling import (
    explain_growth, explain_inflation, explain_liquidity, explain_risk,
)

# ~1 year of steadily rising daily closes (+0.05%/day)
RISING = [5000 * 1.0005 ** i for i in range(250)]


def test_growth_explains_positive_momentum():
    # Rising SPX -> growth improving, recent return is the driver, explanation mentions S&P.
    r = explain_growth(RISING[-1] * 1.0005, RISING)
    assert r["signal"] == "Growth"
    assert "S&P 500" in r["explanation_text"]
    assert r["contributions"][0]["contribution"] > 0        # positive momentum
    assert r["driver"] in ("SPX 1M return", "SPX 6M return")


def test_growth_unavailable_without_enough_history():
    r = explain_growth(5800, [5700, 5750, 5800])
    assert r["score"] is None and r["trend"] == "unavailable"


def test_missing_inputs_are_unavailable_not_defaulted():
    assert explain_inflation(None, None)["score"] is None
    assert explain_liquidity(None, 4.5, 5.0)["score"] is None
    assert explain_risk(None)["score"] is None


def test_inflation_reports_cpi_and_breakeven():
    r = explain_inflation(3.4, 2.36)
    assert "CPI 3.4% YoY" in r["explanation_text"]
    assert "10Y breakeven 2.36%" in r["explanation_text"]
    assert r["trend"] in ("elevated", "contained", "subdued")


def test_inflation_hot_vs_cool():
    assert explain_inflation(6.0, 3.2)["trend"] == "elevated"
    assert explain_inflation(1.0, 1.6)["trend"] == "subdued"


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
    for r in (explain_growth(RISING[-1], RISING[:-1]),
              explain_inflation(3.0, 2.3), explain_liquidity(104, 4.5, 5.0),
              explain_risk(18)):
        c = r["contributions"]
        mags = [abs(x["contribution"]) for x in c]
        assert mags == sorted(mags, reverse=True)           # ranked by |contribution|
