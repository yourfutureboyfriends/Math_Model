"""
SWEEP 3 — silent failure / swallowed errors, and typed error paths.

Locks the /api/ask 503 bug: it called the broken get_risk_indicators() (RiskIndicator with a
string `value`) and passed a string `confidence` where the schema wants a float — raising on
every call. It must now return a valid AskResponse with a numeric confidence.
"""


def test_ask_endpoint_returns_valid_response_not_503(client):
    for q in ["what is the current regime?", "recession probability?", "equity positioning?", "outlook?"]:
        r = client.post("/api/ask", json={"question": q})
        assert r.status_code == 200, f"/api/ask 503-regressed for {q!r}: {r.text[:200]}"
        body = r.json()
        assert isinstance(body.get("answer"), str) and body["answer"]
        # confidence must be a float in [0,1] (was a string 'high'/'medium' → 503)
        c = body.get("confidence")
        assert isinstance(c, (int, float)) and 0.0 <= c <= 1.0


def test_ask_growth_framed_as_signal_not_pct_deviation(client):
    """The 0-100 growth SIGNAL must be framed as 'N/100', not '+N% vs trend'."""
    r = client.post("/api/ask", json={"question": "what is the current regime?"})
    assert r.status_code == 200
    answer = r.json()["answer"]
    assert "vs trend" not in answer, "misleading '% vs trend' framing regressed"
    assert "/100" in answer
