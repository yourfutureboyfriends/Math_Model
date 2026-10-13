"""Account security: forced change of default passwords, password policy, lockout,
persisted logout revocation, admin user management. Uses a throwaway users DB."""
import pytest
from fastapi.testclient import TestClient

from api import portfolio_store

ADMIN_PW = "Sec-Admin-Pass-2026!"


@pytest.fixture()
def c(tmp_path):
    path = str(tmp_path / "sec.db")
    mp = pytest.MonkeyPatch()
    mp.setattr(portfolio_store, "_db_path", lambda: path)
    import api.core.auth as auth
    from api.core import accounts
    mp.setattr(auth, "get_db_path", lambda: path)
    accounts.invalidate_cache()
    accounts.migrate()
    accounts.set_password("admin", ADMIN_PW)       # other seeded users keep their defaults
    from api.main import app
    with TestClient(app) as client:
        yield client
    mp.undo()
    accounts.invalidate_cache()


def _login(c, u, pw):
    return c.post("/api/auth/login", data={"username": u, "password": pw})


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _token(c, u, pw):
    r = _login(c, u, pw)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_default_password_forces_change_before_anything_else(c):
    r = _login(c, "pm", "pm123")
    assert r.status_code == 200 and r.json()["must_change_password"] is True
    t = r.json()["access_token"]
    blocked = c.get("/api/v1/blotter", headers=_h(t))
    assert blocked.status_code == 403 and blocked.json()["code"] == "password_change_required"
    assert c.get("/api/auth/me", headers=_h(t)).json()["must_change_password"] is True
    assert c.get("/api/auth/status").json()["default_credentials_active"] is True


def test_change_password_policy_and_token_rotation(c):
    old = _token(c, "pm", "pm123")
    weak = c.post("/api/auth/change-password", headers=_h(old),
                  json={"current_password": "pm123", "new_password": "short"})
    assert weak.status_code == 400 and weak.json()["detail"]["problems"]
    has_user = c.post("/api/auth/change-password", headers=_h(old),
                      json={"current_password": "pm123", "new_password": "My-pm-Password-99"})
    assert has_user.status_code == 400
    wrong = c.post("/api/auth/change-password", headers=_h(old),
                   json={"current_password": "nope", "new_password": "Str0ng-Enough-Pass"})
    assert wrong.status_code == 400
    ok = c.post("/api/auth/change-password", headers=_h(old),
                json={"current_password": "pm123", "new_password": "Str0ng-Enough-Pass"})
    assert ok.status_code == 200
    new = ok.json()["access_token"]
    assert c.get("/api/v1/blotter", headers=_h(old)).status_code == 401      # old session dead
    assert c.get("/api/v1/blotter", headers=_h(new)).status_code == 200
    assert _login(c, "pm", "pm123").status_code == 401
    assert _login(c, "pm", "Str0ng-Enough-Pass").json()["must_change_password"] is False


def test_lockout_after_repeated_failures_and_admin_unlock(c):
    codes = [_login(c, "risk", "bad").status_code for _ in range(5)]
    assert codes[:4] == [401] * 4 and codes[4] == 429
    assert _login(c, "risk", "risk123").status_code == 429                   # even the right one
    admin = _token(c, "admin", ADMIN_PW)
    assert c.post("/api/admin/users/risk/unlock", headers=_h(admin)).status_code == 200
    assert _login(c, "risk", "risk123").status_code == 200


def test_logout_revocation_is_persisted(c):
    from api.core import accounts
    t = _token(c, "admin", ADMIN_PW)
    assert c.get("/api/v1/blotter", headers=_h(t)).status_code == 200
    assert c.post("/api/auth/logout", headers=_h(t)).status_code == 200
    accounts.invalidate_cache()                    # i.e. a restart: the DB still knows
    assert c.get("/api/v1/blotter", headers=_h(t)).status_code == 401


def test_admin_user_management(c):
    admin = _token(c, "admin", ADMIN_PW)
    pm = _token(c, "pm", "pm123")
    assert c.get("/api/admin/users", headers=_h(pm)).status_code == 403
    users = c.get("/api/admin/users", headers=_h(admin)).json()["users"]
    assert {u["username"] for u in users} >= {"admin", "pm", "risk"}
    assert "hashed_password" not in users[0]

    r = c.post("/api/admin/users", headers=_h(admin),
               json={"username": "trader1", "role": "analyst", "display_name": "Trader One"})
    temp = r.json()["temporary_password"]
    assert r.status_code == 200 and len(temp) >= 12
    assert c.post("/api/admin/users", headers=_h(admin),
                  json={"username": "trader1", "role": "analyst"}).status_code == 400
    assert c.post("/api/admin/users", headers=_h(admin),
                  json={"username": "x2", "role": "god"}).status_code == 400
    login = _login(c, "trader1", temp).json()
    assert login["role"] == "analyst" and login["must_change_password"] is True

    # role change applies immediately and invalidates the old token
    t1 = login["access_token"]
    assert c.put("/api/admin/users/trader1", headers=_h(admin), json={"role": "pm"}).status_code == 200
    assert c.get("/api/auth/me", headers=_h(t1)).status_code == 401

    # disabling: tokens die, login refused
    t2 = _token(c, "trader1", temp)
    assert c.put("/api/admin/users/trader1", headers=_h(admin), json={"disabled": True}).status_code == 200
    assert c.get("/api/auth/me", headers=_h(t2)).status_code == 401
    assert _login(c, "trader1", temp).status_code == 403

    # reset: new temp works and must be changed; the old one doesn't
    c.put("/api/admin/users/trader1", headers=_h(admin), json={"disabled": False})
    temp2 = c.post("/api/admin/users/trader1/reset-password", headers=_h(admin)).json()["temporary_password"]
    assert _login(c, "trader1", temp).status_code == 401
    assert _login(c, "trader1", temp2).json()["must_change_password"] is True

    # guards
    assert c.put("/api/admin/users/admin", headers=_h(admin), json={"disabled": True}).status_code == 400
    assert c.put("/api/admin/users/admin", headers=_h(admin), json={"role": "pm"}).status_code == 400
    assert c.put("/api/admin/users/ghost", headers=_h(admin), json={"role": "pm"}).status_code == 404
    actions = {d["action"] for d in
               c.get("/api/v1/audit/decisions", headers=_h(admin)).json()["decisions"]}
    assert {"user_created", "user_updated", "password_reset"} <= actions


def test_password_policy_unit():
    from api.core.accounts import password_problems, generate_temp_password
    assert password_problems("admin123")
    assert password_problems("alllowercaseletters")
    assert not password_problems("Good-Pass-2026")
    assert not password_problems(generate_temp_password())
