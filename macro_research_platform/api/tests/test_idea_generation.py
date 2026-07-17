"""
Known-answer tests for trade-idea generation (Phase 6 gap-closure).
Run: pytest api/tests/test_idea_generation.py
"""
from api.calculations.idea_generation import desired_tilts, generate_ideas


def test_desired_tilts_contraction_is_defensive():
    # Contraction: underweight equity, long duration, low risk appetite.
    t = desired_tilts("contraction")
    assert t["equity"] == -1          # underweight risk
    assert t["rates"] == 1            # long duration
    assert t["credit"] == -1          # risk-off → reduce credit
    assert t["volatility"] == 1       # own vol as a hedge


def test_desired_tilts_reflation_is_procyclical():
    t = desired_tilts("reflation")
    assert t["equity"] == 1
    assert t["commodity"] == 1        # commodities as inflation hedge
    assert t["rates"] == -1           # short duration
    assert t["value"] == 1 and t["growth"] == -1


def test_desired_tilts_unknown_regime_empty():
    assert desired_tilts("no-such-regime") == {}


def test_generate_realign_when_opposite_sign():
    # Regime wants long duration, but the book is short rates → REALIGN, LONG TLT.
    ideas = generate_ideas({"rates": -500_000.0}, "contraction", gross_exposure=1_000_000)
    rates = next(i for i in ideas if i["factor"] == "rates")
    assert rates["kind"] == "REALIGN"
    assert rates["direction"] == "LONG"
    assert rates["proxy"] == "TLT"
    assert rates["severity"] == 500_000.0


def test_generate_initiate_when_flat():
    # Flat book, reflation regime → propose initiating the tilts (e.g. long commodity).
    ideas = generate_ideas({}, "reflation", gross_exposure=1_000_000)
    commodity = next(i for i in ideas if i["factor"] == "commodity")
    assert commodity["kind"] == "INITIATE"
    assert commodity["direction"] == "LONG"
    assert commodity["proxy"] == "DBC"


def test_generate_skips_aligned_exposure():
    # Book already long rates in a long-duration regime → no rates idea emitted.
    ideas = generate_ideas({"rates": 400_000.0}, "contraction", gross_exposure=1_000_000)
    assert all(i["factor"] != "rates" for i in ideas)


def test_generate_ranked_by_severity():
    ideas = generate_ideas({"rates": -900_000.0, "equity": 100_000.0},
                           "contraction", gross_exposure=1_000_000)
    assert ideas[0]["severity"] >= ideas[-1]["severity"]
    assert ideas[0]["rank"] == 1
