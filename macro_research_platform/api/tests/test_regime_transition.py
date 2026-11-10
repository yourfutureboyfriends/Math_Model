"""
Known-answer tests for empirical regime transition matrix (Phase 6B).
Run: pytest api/tests/test_regime_transition.py
"""
from api.calculations.regime import empirical_transition_matrix, forward_outlook


def test_transition_counts_and_probs():
    # A->A->B->A->B : from A: {A:1, B:2} -> P(A|A)=1/3, P(B|A)=2/3 ; from B: {A:1} -> P(A|B)=1
    seq = ["A", "A", "B", "A", "B"]
    m = empirical_transition_matrix(seq)
    assert m["states"] == ["A", "B"]
    assert m["transitions"] == 4
    assert m["matrix"]["A"]["A"] == round(1 / 3, 3)
    assert m["matrix"]["A"]["B"] == round(2 / 3, 3)
    assert m["matrix"]["B"]["A"] == 1.0


def test_forward_outlook_ranks_and_persistence():
    m = empirical_transition_matrix(["Expansion"] * 8 + ["Slowdown"] + ["Expansion"] * 3)
    out = forward_outlook(m, "Expansion")
    assert out["current"] == "Expansion"
    # stays in Expansion most of the time -> high stay prob, ranked head is Expansion
    assert out["ranked"][0]["regime"] == "Expansion"
    assert out["stay_prob"] > 0.7
    assert out["expected_persistence_periods"] and out["expected_persistence_periods"] > 3
    # the one recorded change is to Slowdown
    assert out["most_likely_change"]["to"] == "Slowdown"


def test_absorbing_state_persistence_none():
    m = empirical_transition_matrix(["X", "X", "X"])
    out = forward_outlook(m, "X")
    assert out["stay_prob"] == 1.0
    assert out["expected_persistence_periods"] is None   # 1/(1-1) guarded


def test_empty_and_unknown():
    m = empirical_transition_matrix([])
    assert m["states"] == []
    out = forward_outlook(m, "Nope")
    assert out["ranked"] == []
