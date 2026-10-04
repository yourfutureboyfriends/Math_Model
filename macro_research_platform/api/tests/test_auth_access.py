"""Authentication & authorization: real login, token-verified identity, role checks,
four-eyes on orders. Uses a temporary positions DB so no real book is touched."""
import pytest
from fastapi.testclient import TestClient

from api import portfolio_store


@pytest.fixture(scope="module")
def app_client(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("db") / "auth.db")
    mp = pytest.MonkeyPatch()
    mp.setattr(portfolio_store, "_db_path", lambda: path)
    import api.core.auth as auth
    mp.setattr(auth, "get_db_path", lambda: path)
    auth.init_users_table()
    from api.main import app
    with TestClient(app) as c:
        yield c
    mp.undo()


def _login(c, user, pw):
    return c.post("/api/auth/login", data={"username": user, "password": pw})


def _h(c, user, pw):
    return {"Authorization": f"Bearer {_login(c, user, pw).json()['access_token']}"}


def test_bad_credentials_are_401_not_200(app_client):
    r = _login(app_client, "pm", "wrong")
    assert r.status_code == 401 and r.json()["success"] is False
    assert _login(app_client, "nobody", "x").status_code == 401


def test_good_login_returns_signed_token_and_role(app_client):
    r = _login(app_client, "risk", "risk123")
    j = r.json()
    assert r.status_code == 200 and j["role"] == "risk" and j["access_token"].count(".") == 2
    me = app_client.get("/api/auth/me", headers={"Authorization": f"Bearer {j['access_token']}"}).json()
    assert me["username"] == "risk" and me["role"] == "risk"


def test_sensitive_reads_and_all_writes_need_a_token(app_client):
    assert app_client.get("/api/v1/portfolio/positions").status_code == 401
    assert app_client.get("/api/v1/blotter").status_code == 401
    assert app_client.post("/api/v1/orders", json={"symbol": "SPY", "side": "BUY", "quantity": 1}).status_code == 401
    assert app_client.get("/api/v1/portfolio/positions",
                          headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401
    assert app_client.get("/api/health").status_code == 200          # public


def test_forged_x_user_header_is_ignored(app_client):
    r = app_client.post("/api/v1/portfolio/positions",
                        json={"symbol": "SPY", "quantity": 1, "avg_cost": 100},
                        headers={"X-User": "admin"})
    assert r.status_code == 401


def test_roles_enforced_on_position_edits(app_client):
    r = app_client.post("/api/v1/portfolio/positions", json={"symbol": "SPY", "quantity": 1, "avg_cost": 100},
                        headers=_h(app_client, "analyst", "analyst123"))
    assert r.status_code == 403
    r = app_client.post("/api/v1/portfolio/positions", json={"symbol": "SPY", "quantity": 1, "avg_cost": 100},
                        headers=_h(app_client, "pm", "pm123"))
    assert r.status_code == 200


def test_order_four_eyes_and_roles(app_client, monkeypatch):
    from api.routers import fund

    async def _fake_pretrade(symbol, quantity, book):
        return {"decision": "PASS", "reasons": [], "checks": []}
    monkeypatch.setattr(fund, "_run_pretrade", _fake_pretrade)

    pm, risk, analyst = (_h(app_client, *c) for c in
                         (("pm", "pm123"), ("risk", "risk123"), ("analyst", "analyst123")))
    oid = app_client.post("/api/v1/orders", json={"symbol": "SPY", "side": "BUY", "quantity": 5},
                          headers=pm).json()["order"]["id"]
    assert app_client.post(f"/api/v1/orders/{oid}/approve", json={}, headers=analyst).status_code == 403
    # Old generic transition route can't be used to skip the order workflow
    r = app_client.post(f"/api/v1/portfolio/trade-ideas/{oid}/transition",
                        json={"state": "Approved"}, headers=risk)
    assert r.status_code == 409
    ok = app_client.post(f"/api/v1/orders/{oid}/approve", json={}, headers=risk)
    assert ok.status_code == 200 and ok.json()["order"]["approved_by"] == "risk"

    oid2 = app_client.post("/api/v1/orders", json={"symbol": "SPY", "side": "BUY", "quantity": 5},
                           headers=_h(app_client, "admin", "admin123")).json()["order"]["id"]
    # admin may approve, but not their own order
    assert app_client.post(f"/api/v1/orders/{oid2}/approve", json={},
                           headers=_h(app_client, "admin", "admin123")).status_code == 403
