"""Role desk: who gets which action items (four-eyes routing), and the endpoint."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from api import portfolio_store
from api.calculations.desk import build_queue

ORDERS = [
    {"id": 1, "symbol": "SPY", "side": "BUY", "quantity": 10, "state": "Proposed", "created_by": "pm"},
    {"id": 2, "symbol": "TLT", "side": "SELL", "quantity": 5, "state": "Under Review", "created_by": "risk"},
    {"id": 3, "symbol": "GLD", "side": "BUY", "quantity": 2, "state": "Approved", "created_by": "pm"},
    {"id": 4, "symbol": "QQQ", "side": "BUY", "quantity": 1, "state": "Approved", "created_by": "pm",
     "executed_trade_id": 9},
]
LIMITS = {"breaches": [{"metric": "single_name", "label": "Largest single name", "value": 0.2,
                        "hard": 0.15, "unit": "% NAV"}],
          "warnings": [{"metric": "gross_exposure", "label": "Gross exposure", "value": 1.6,
                        "soft": 1.5, "unit": "% NAV"}]}
FRESH = {"available": True, "series": [
    {"series_id": "CPIAUCSL", "name": "CPI", "status": "FRESH", "frequency": "M", "unit": "% YoY",
     "next_expected_release": "2026-10-15"},
    {"series_id": "M2SL", "name": "M2", "status": "CRITICAL", "periods_behind": 3, "frequency": "M",
     "last_observation_date": "2026-05-01", "next_expected_release": "2026-07-27"},
]}
TODAY = date(2026, 10, 13)


def kinds(q):
    return [i["kind"] for i in q]


def test_risk_approves_others_orders_never_its_own():
    q = build_queue("risk", "risk", orders=ORDERS, limits=LIMITS, freshness=FRESH, today=TODAY)
    approve = next(i for i in q if i["kind"] == "approve")
    assert approve["ref"] == [1]                      # #2 is risk's own → not routed to risk
    assert "waiting" in kinds(q)                      # ...it shows as awaiting someone else
    assert "execute" not in kinds(q)                  # risk doesn't execute
    assert "breach" in kinds(q) and q[0]["priority"] == "high"


def test_pm_executes_approved_unexecuted_orders():
    q = build_queue("pm", "pm", orders=ORDERS, limits=LIMITS, freshness=FRESH, today=TODAY)
    ex = next(i for i in q if i["kind"] == "execute")
    assert ex["ref"] == [3]                           # #4 already executed
    assert "approve" not in kinds(q)
    assert next(i for i in q if i["kind"] == "waiting")["ref"] == [1]


def test_analyst_gets_data_issues_and_upcoming_releases_not_trading():
    q = build_queue("analyst", "analyst", orders=ORDERS, limits=LIMITS, freshness=FRESH, today=TODAY)
    assert set(kinds(q)) == {"data", "release"}
    assert next(i for i in q if i["kind"] == "data")["priority"] == "high"
    assert "CPI" in next(i for i in q if i["kind"] == "release")["title"]


def test_pm_sees_data_problems_at_lower_priority():
    q = build_queue("pm", "pm", orders=[], freshness=FRESH, today=TODAY)
    assert next(i for i in q if i["kind"] == "data")["priority"] == "medium"


def test_admin_sees_everything_plus_accounts_and_queue_is_sorted():
    users = [{"username": "x", "locked": True}, {"username": "y", "must_change_password": True}]
    q = build_queue("admin", "admin", orders=ORDERS, limits=LIMITS, freshness=FRESH, users=users, today=TODAY)
    assert {"approve", "execute", "breach", "warning", "data", "account"} <= set(kinds(q))
    prio = [i["priority"] for i in q]
    assert prio == sorted(prio, key={"high": 0, "medium": 1, "info": 2}.get)


def test_empty_state_is_an_empty_queue():
    assert build_queue("quant", "quant", orders=[]) == []


@pytest.fixture()
def client(tmp_path, monkeypatch):
    path = str(tmp_path / "desk.db")
    monkeypatch.setattr(portfolio_store, "_db_path", lambda: path)
    import api.core.auth as auth
    from api.core import accounts
    monkeypatch.setattr(auth, "get_db_path", lambda: path)
    accounts.invalidate_cache()
    accounts.migrate()
    for u in ("pm", "risk"):
        accounts.set_password(u, f"Desk-{u}-Pass-2026!")
    # Keep the endpoint test offline-fast: stub the network-bound blocks.
    import api.routers.desk as desk_mod
    async def _fund():
        return {"available": False, "reason": "stub"}
    async def _macro():
        return {"available": True, "regime": "reflation"}
    monkeypatch.setattr(desk_mod, "_fund_block", _fund)
    monkeypatch.setattr(desk_mod, "_macro_block", _macro)
    import api.main as main_mod
    async def _gm():
        return {"recent_policy_moves": []}
    monkeypatch.setattr(main_mod, "get_global_macro_v1", _gm)
    async def _cyc():
        return {"turbulence": {}, "absorption_ratio": {}, "near_term_forward_spread": {}}
    monkeypatch.setattr(main_mod, "get_cycle_risk_v1", _cyc)
    import api.data_freshness as df
    monkeypatch.setattr(df, "get_live_freshness", lambda force=False, today=None: FRESH)
    from api.main import app
    with TestClient(app) as c:
        yield c
    accounts.invalidate_cache()


def test_desk_endpoint_requires_auth_and_is_role_specific(client):
    assert client.get("/api/v1/desk").status_code == 401
    tok = client.post("/api/auth/login", data={"username": "pm", "password": "Desk-pm-Pass-2026!"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    r = client.post("/api/v1/orders", headers=h, json={"symbol": "SPY", "side": "BUY", "quantity": 1})
    assert r.status_code in (200, 201, 404)               # 404 only if no price history offline
    d = client.get("/api/v1/desk", headers=h).json()
    assert d["user"]["role"] == "pm" and d["focus"]["title"] == "Portfolio Manager"
    assert d["macro"]["regime"] == "reflation" and d["fund"]["available"] is False
    assert any(i["kind"] == "data" for i in d["queue"])
    assert "unit" in d["data"]["prints"][0]                # the UI formats values by unit
    rk = client.post("/api/auth/login", data={"username": "risk", "password": "Desk-risk-Pass-2026!"}).json()["access_token"]
    d2 = client.get("/api/v1/desk", headers={"Authorization": f"Bearer {rk}"}).json()
    assert d2["focus"]["title"] == "Risk Officer"
    if r.status_code in (200, 201):
        assert any(i["kind"] == "approve" for i in d2["queue"])
