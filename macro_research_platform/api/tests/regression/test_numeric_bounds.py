"""
SWEEP 1 — impossible numeric values.

Locks the class of bug behind prior recession-probability / momentum out-of-range issues:
percentages, probabilities and scores must stay within their declared ranges on the live
dashboard payload.
"""


def _num(v):
    """Accept either a scalar or a {'value': n} metric wrapper."""
    if isinstance(v, dict):
        return v.get("value")
    return v


def test_dashboard_scores_and_probabilities_in_range(client):
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    d = r.json()
    km = d.get("keyMetrics", {})

    # growth / inflation / risk / recession are 0-100 signal scores
    for key in ("growth", "inflation", "risk", "recession"):
        v = _num(km.get(key))
        if v is not None:
            assert 0 <= v <= 100, f"keyMetrics.{key} out of [0,100]: {v}"

    # regime confidence is a 0-1 probability
    reg = d.get("regime") or {}
    conf = reg.get("confidenceScore")
    if conf is not None:
        assert 0.0 <= conf <= 1.0, f"regime.confidenceScore out of [0,1]: {conf}"

    # recession probability is a 0-1 fraction
    rec = d.get("recession") or {}
    p = rec.get("probability")
    if p is not None:
        assert 0.0 <= p <= 1.0, f"recession.probability out of [0,1]: {p}"


def test_recession_component_probabilities_in_range(client):
    r = client.get("/api/dashboard")
    rec = r.json().get("recession") or {}
    for key in ("logisticProb", "emProbitProb"):
        v = rec.get(key)
        if v is not None:
            assert 0.0 <= v <= 1.0, f"recession.{key} out of [0,1]: {v}"


def test_var_values_nonnegative(client):
    """VaR loss magnitudes must be non-negative dollar amounts."""
    r = client.get("/api/v1/risk/var")
    if r.status_code != 200 or not r.json().get("available"):
        return
    var = r.json().get("var", {})
    for conf_level, methods in var.items():
        for method, horizons in (methods or {}).items():
            for h, val in (horizons or {}).items():
                assert val is None or val >= 0, f"VaR {conf_level}/{method}/{h} negative: {val}"
