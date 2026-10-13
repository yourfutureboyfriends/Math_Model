"""
SWEEP 7 — inconsistent labeling / cross-panel contradictions.

Locks:
- The CPI/NFP date contradiction: the same economic release must show the SAME date across
  /api/horizon, /api/calendar and /api/v1/event-vol (they used independent date generators).
- The risk-label collision: recommendations must use "Risk Appetite" (not "Risk Score", which
  collided with the header's complementary risk-level metric) and an unambiguous position stance.
"""


def _cpi_dates(events, key_event="event", key_date="date"):
    return sorted({e[key_date] for e in events if "CPI" in (e.get(key_event) or "")})


def test_cpi_date_consistent_across_panels(client):
    horizon = client.get("/api/horizon").json().get("horizon_events", [])
    calendar = client.get("/api/calendar").json().get("events", [])
    ev = client.get("/api/v1/event-vol").json()
    ev_events = ev.get("upcoming", []) + ([ev["next_event"]] if ev.get("next_event") else [])

    h = _cpi_dates(horizon)
    c = _cpi_dates(calendar)
    e = _cpi_dates(ev_events)
    if not (h and c and e):
        return  # if any panel has no CPI in-window, nothing to contradict
    # the NEXT CPI (earliest upcoming) must agree across all three panels
    assert h[0] == c[0] == e[0], f"CPI date disagreement — horizon {h[0]}, calendar {c[0]}, event-vol {e[0]}"


def test_recommendations_risk_labels_unambiguous(client):
    r = client.get("/api/business/recommendations")
    assert r.status_code == 200
    s = r.json().get("summary", {})
    pos = s.get("overall_position", "")
    assert pos in {"RISK-ON", "MODERATE RISK-ON", "DEFENSIVE", "BALANCED"}, f"unexpected position label: {pos}"
    ra = s.get("risk_assessment", "")
    # "Risk Score" collided with the header's complementary "Risk" metric → must say "Risk Appetite"
    assert "Risk Score" not in ra, "ambiguous 'Risk Score' label regressed"
    assert "Risk Appetite" in ra
