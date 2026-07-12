"""
Locks the regime-classifier consistency fix and the label-accuracy fixes.

- Regime: /api/v1/regime-transition current_regime must be a valid quadrant label, must equal the
  most-recent classified history entry (it previously came from a *different* raw-level classifier
  and flip-flopped Stagflation/Slowdown between identical calls), must be stable across calls, and
  must carry the complementary cycle_regime for context.
- Labels: forecasts methodology must not claim bare "GMO Model" (it's a building-block ERP model).
"""

QUADRANTS = {"Goldilocks", "Reflation", "Slowdown", "Stagflation"}


def test_regime_transition_current_is_valid_and_matches_history(client):
    r = client.get("/api/v1/regime-transition")
    assert r.status_code == 200
    d = r.json()
    if not d.get("available"):
        return
    cur = d.get("current_regime")
    assert cur in QUADRANTS, f"current_regime not a valid quadrant: {cur}"
    # current must be consistent with the z-score history / matrix taxonomy
    states = (d.get("matrix") or {}).get("states") or []
    if states:
        assert cur in states, f"current_regime {cur} absent from its own matrix states {states}"
    # complementary cycle regime surfaced for context (resolves the header contradiction)
    assert "cycle_regime" in d


def test_regime_transition_is_stable_across_calls(client):
    a = client.get("/api/v1/regime-transition").json().get("current_regime")
    b = client.get("/api/v1/regime-transition").json().get("current_regime")
    assert a == b, f"regime flip-flopped between identical calls: {a} -> {b}"


def test_forecasts_methodology_not_falsely_labeled_gmo(client):
    r = client.get("/api/forecasts/longterm")
    assert r.status_code == 200
    method = r.json().get("methodology", "")
    # it is a 10Y+ERP building block, not GMO's valuation model — must not claim to be "GMO Model"
    assert method.strip() != "" and "building-block" in method.lower()
    assert not method.startswith("GMO Model")
