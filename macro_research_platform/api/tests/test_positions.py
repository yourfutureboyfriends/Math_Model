"""Positions and tiers per fund: role and capabilities come from the person's position in that fund."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def env(tmp_path, monkeypatch):
    import api.core.auth as auth
    from api import funds
    from api.core import accounts
    path = str(tmp_path / "d.db")
    monkeypatch.setattr(funds, "db_path", lambda fund_id=None: path)
    monkeypatch.setattr(auth, "get_db_path", lambda: path)
    accounts.invalidate_cache()
    accounts.migrate()
    for u in ("pm", "risk", "analyst", "quant"):
        accounts.set_password(u, f"Pos-{u}-Pass-2026!x")
    from api import positions
    positions._bust()
    positions.seed("bifs")
    from api.main import app

    def client(user):
        c = TestClient(app)
        c.headers["Authorization"] = f"Bearer {accounts.issue_token(accounts.get_user(user))}"
        return c
    yield client
    positions._bust()
    accounts.invalidate_cache()


def test_templates_cover_every_tier_and_valid_capabilities():
    from api import positions
    for name, ps in positions.TEMPLATES.items():
        assert {p["tier"] for p in ps} == {1, 2, 3, 4}, name
        for p in ps:
            assert p["base_role"] in positions.BASE_ROLES and set(p["capabilities"]) <= set(positions.CAPABILITIES)


def test_position_overrides_role_and_capabilities(env):
    from api import positions
    pm, analyst, admin_like = env("pm"), env("analyst"), None
    assert pm.get("/api/v1/positions/me").json()["position"] is None           # no position: account role applies
    positions.assign("pm", "treasurer", "admin")                              # pm account → Treasurer (read-only)
    me = pm.get("/api/v1/positions/me").json()
    assert me["position"]["title"] == "Treasurer" and me["read_only"] and me["capabilities"]["budget_approve"]
    assert pm.get("/api/v1/governance").status_code == 200                    # reads allowed
    r = pm.post("/api/v1/orders", json={"symbol": "ISF.L", "side": "BUY", "quantity": 1})
    assert r.status_code == 403 and "read-only" in r.text                     # writes refused
    positions.assign("analyst", "head_of_trading", "admin")                   # analyst account → Head of Trading (pm)
    me = analyst.get("/api/v1/positions/me").json()
    assert me["role"] == "pm" and me["capabilities"]["execute_orders"] and not me["capabilities"]["approve_orders"]


def test_capabilities_gate_actions(env):
    from api import positions
    risk = env("risk")
    positions.assign("risk", "equity_analyst", "admin")                       # risk account seated as an analyst
    r = risk.post("/api/v1/governance/controls/halt", json={"reason": "test halt"})
    assert r.status_code == 403 and "does not include" in r.text
    positions.assign("risk", "head_of_risk", "admin")
    assert risk.post("/api/v1/governance/controls/halt", json={"reason": "test halt", "test": True}).status_code == 200


def test_managers_assign_but_not_themselves_and_seats_are_limited(env):
    from api import positions
    analyst, quant = env("analyst"), env("quant")
    assert quant.post("/api/v1/positions/assign", json={"username": "pm", "position_key": "cio"}).status_code == 403
    positions.assign("analyst", "chair", "admin")
    assert analyst.post("/api/v1/positions/assign", json={"username": "pm", "position_key": "cio"}).status_code == 200
    assert analyst.post("/api/v1/positions/assign", json={"username": "analyst", "position_key": "cio"}).status_code == 403
    assert analyst.post("/api/v1/positions/assign", json={"username": "risk", "position_key": "cio"}).status_code == 400  # 1 seat
    r = analyst.post("/api/v1/positions", json={"key": "head_of_macro", "title": "Head of Macro", "tier": 2, "base_role": "analyst",
                                                "capabilities": ["pitch_submit", "nonsense"], "panels": ["macro-model"]})
    assert r.status_code == 200 and r.json()["capabilities"] == ["pitch_submit"]


def test_unpositioned_users_keep_todays_permissions(env):
    from api import positions
    assert positions.capabilities_for({"role": "risk", "username": "x"}) >= {"approve_orders", "resume_trading"}
    assert "execute_orders" not in positions.capabilities_for({"role": "risk", "username": "x"})
    assert positions.capabilities_for({"role": "admin", "username": "a"}) == set(positions.CAPABILITIES)
