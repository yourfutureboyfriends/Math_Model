"""Analyst pitch review: validation, versioning, PMC four-eyes workflow, valuation and kill criteria."""
from datetime import date

import pytest

from api import pitches, portfolio_store

BODY = {"thesis": "Margin recovery as the oncology pipeline converts; consensus underestimates 2027 EPS.",
        "horizon_years": 3, "valuation_method": "DCF + EV/EBITDA cross-check",
        "scenarios": {"bear": {"value": 10000, "probability": 0.25}, "base": {"value": 15000, "probability": 0.5},
                      "bull": {"value": 19000, "probability": 0.25}},
        "entry_range": {"low": 12000, "high": 13200}, "target_weight": 0.03,
        "catalysts": [{"event": "Q3 results", "expected_date": "2026-10-30", "date_confidence": "scheduled"}],
        "kill_criteria": [{"type": "price_below", "level": 10500, "description": "breaks the bear case"},
                          {"type": "drawdown_from_entry", "threshold": 0.2},
                          {"type": "metric_below", "metric": "operating_margin", "threshold": 0.2},
                          {"type": "underperform_benchmark", "threshold": 0.15},
                          {"type": "date_passed", "date": "2026-01-01"}, {"type": "manual", "description": "CEO leaves"}]}


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "p.db")
    monkeypatch.setattr(portfolio_store, "_db_path", lambda: path)


def test_validation_rejects_unusable_pitches():
    for bad, msg in ((dict(BODY, thesis="short"), "thesis"), (dict(BODY, horizon_years=7), "horizon"),
                     (dict(BODY, scenarios={**BODY["scenarios"], "bear": {"value": 16000, "probability": 0.25}}), "bear ≤ base"),
                     (dict(BODY, scenarios={**BODY["scenarios"], "bull": {"value": 19000, "probability": 0.5}}), "add up to 1"),
                     (dict(BODY, kill_criteria=[]), "kill_criteria")):
        with pytest.raises(ValueError, match=msg):
            pitches.validate(bad)


def test_valuation_against_price():
    v = pitches.valuation_vs_price(pitches.validate(BODY), 12824.0)
    assert v["expected_value"] == pytest.approx(0.25 * 10000 + 0.5 * 15000 + 0.25 * 19000)
    assert v["expected_return"] == pytest.approx(14750 / 12824 - 1, abs=1e-4)
    assert v["reward_to_risk"] == pytest.approx((19000 - 12824) / (12824 - 10000), abs=0.01)
    assert v["annualised_expected_return"] == pytest.approx((14750 / 12824) ** (1 / 3) - 1, abs=1e-4)
    assert v["in_entry_range"] is True


def test_versions_and_four_eyes_committee_decision():
    p = pitches.create("azn.l", "AstraZeneca", "analyst", BODY)
    assert p["symbol"] == "AZN.L" and p["status"] == "draft" and len(p["versions"]) == 1
    pitches.transition(p["id"], "analyst", "submitted")
    with pytest.raises(PermissionError):
        pitches.transition(p["id"], "analyst", "approved")                     # the author cannot approve
    p = pitches.transition(p["id"], "pm", "approved", "PMC 24 Oct: 3% initial", price=12824.0)
    assert p["status"] == "approved" and p["decided_by"] == "pm" and p["approved_price"] == 12824.0
    p = pitches.add_version(p["id"], "analyst", dict(BODY, horizon_years=4), "longer horizon")
    assert p["current_version"] == 2 and p["status"] == "submitted"            # a revision goes back to the PMC
    assert p["versions"][0]["payload"]["horizon_years"] == 3                   # history kept
    with pytest.raises(ValueError):
        pitches.transition(p["id"], "pm", "closed")                            # submitted → closed is not allowed


def test_kill_criteria_checks():
    p = pitches.create("AZN.L", "AZN", "analyst", BODY)
    res = {k["type"]: k for k in pitches.check_kill_criteria(p, price=10400.0, entry_price=13500.0,
                                                               metrics={"operating_margin": 0.25},
                                                               relative_since_approval=-0.05, today=date(2026, 10, 25))}
    assert res["price_below"]["status"] == "triggered"
    assert res["drawdown_from_entry"]["status"] == "triggered" and res["drawdown_from_entry"]["observed"] == pytest.approx(10400 / 13500 - 1, abs=1e-4)
    assert res["metric_below"]["status"] == "ok" and res["underperform_benchmark"]["status"] == "ok"
    assert res["date_passed"]["status"] == "triggered" and res["manual"]["status"] == "manual"
    none = {k["type"]: k["status"] for k in pitches.check_kill_criteria(p, None, None)}
    assert none["price_below"] == "not_evaluable"                              # no price: not guessed
