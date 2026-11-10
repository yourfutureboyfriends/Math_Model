"""Trading desk HTTP API: pitch workflow with roles and four-eyes, and the pre-trade assessment endpoint."""
import pytest
from fastapi.testclient import TestClient

BODY = {"thesis": "Margin recovery as the oncology pipeline converts; consensus underestimates 2027 EPS.",
        "horizon_years": 3, "scenarios": {"bear": {"value": 10000, "probability": 0.25}, "base": {"value": 15000, "probability": 0.5},
                                          "bull": {"value": 19000, "probability": 0.25}},
        "kill_criteria": [{"type": "price_below", "level": 10500}]}


@pytest.fixture()
def clients(tmp_path, monkeypatch):
    from api import portfolio_store
    import api.core.auth as auth
    from api.core import accounts
    path = str(tmp_path / "d.db")
    monkeypatch.setattr(portfolio_store, "_db_path", lambda: path)
    monkeypatch.setattr(auth, "get_db_path", lambda: path)
    accounts.invalidate_cache()
    accounts.migrate()
    for u in ("pm", "analyst", "risk"):
        accounts.set_password(u, f"Desk-{u}-Pass-2026!x")
    from api.marketdata import core
    monkeypatch.setattr(core, "quote", lambda s: {"price": 12824.0, "currency": "GBp", "market_state": "CLOSED"})
    monkeypatch.setattr(core, "statements", lambda s: {"ratios": {"operating_margin": 0.25}})
    from api.main import app
    out = {}
    for u in ("pm", "analyst", "risk"):
        c = TestClient(app)
        c.headers["Authorization"] = f"Bearer {accounts.issue_token(accounts.get_user(u))}"
        out[u] = c
    out["anon"] = TestClient(app)
    yield out
    accounts.invalidate_cache()


def test_pitch_workflow_roles_and_four_eyes(clients):
    an, pm, risk, anon = clients["analyst"], clients["pm"], clients["risk"], clients["anon"]
    assert anon.get("/api/v1/pitches").status_code == 401                       # research is not public
    assert risk.post("/api/v1/pitches", json={"symbol": "AZN.L", "body": BODY}).status_code == 403
    r = an.post("/api/v1/pitches", json={"symbol": "AZN.L", "title": "AstraZeneca", "body": BODY})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    assert an.post("/api/v1/pitches", json={"symbol": "X", "body": {**BODY, "horizon_years": 9}}).status_code == 400
    assert an.post(f"/api/v1/pitches/{pid}/submit").json()["status"] == "submitted"
    assert an.post(f"/api/v1/pitches/{pid}/decision", json={"decision": "approve"}).status_code == 403   # not a PM
    d = pm.post(f"/api/v1/pitches/{pid}/decision", json={"decision": "approve", "notes": "PMC: 3% initial"})
    assert d.status_code == 200 and d.json()["status"] == "approved" and d.json()["approved_price"] == 12824.0
    g = an.get(f"/api/v1/pitches/{pid}").json()
    assert g["valuation"]["expected_value"] == 14750.0 and g["kill_criteria_status"][0]["status"] == "ok"
    v = an.post(f"/api/v1/pitches/{pid}/versions", json={"body": {**BODY, "horizon_years": 4}, "note": "longer"}).json()
    assert v["current_version"] == 2 and v["status"] == "submitted"


def test_pretrade_assessment_requires_sign_in_and_is_audited(clients, monkeypatch):
    from api.handlers import pretrade_feasibility as pf
    monkeypatch.setattr(pf, "assess", lambda *a, **k: {"symbol": "AZN.L", "size": {"quantity": 10.0},
                                                         "assessment": {"verdict": "feasible"}, "costs": {"total_bps": 57.0}})
    assert clients["anon"].post("/api/v1/trading/pretrade-assessment", json={"symbol": "AZN.L", "side": "BUY", "quantity": 10}).status_code == 401
    r = clients["risk"].post("/api/v1/trading/pretrade-assessment", json={"symbol": "AZN.L", "side": "BUY", "quantity": 10})
    assert r.status_code == 200 and r.json()["assessment"]["verdict"] == "feasible"
