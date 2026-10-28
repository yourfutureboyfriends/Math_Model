"""Several funds kept apart: own database each (positions, settings, audit), fund-aware caches, membership."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def env(tmp_path, monkeypatch):
    import api.core.auth as auth
    from api import funds
    from api.core import accounts
    main_db = str(tmp_path / "main.db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{main_db}")
    import api.config as cfg
    monkeypatch.setattr(cfg, "DATABASE_URL", f"sqlite:///{main_db}")
    monkeypatch.setattr(auth, "get_db_path", lambda: main_db)
    monkeypatch.setattr(funds, "FUNDS_DIR", tmp_path / "funds")
    accounts.invalidate_cache()
    accounts.migrate()
    for u in ("pm", "analyst"):
        accounts.set_password(u, f"Fund-{u}-Pass-2026!x")
    from api.main import app

    def client(user, fund=None):
        c = TestClient(app)
        c.headers["Authorization"] = f"Bearer {accounts.issue_token(accounts.get_user(user))}"
        if fund:
            c.headers["X-Fund"] = fund
        return c
    yield client
    accounts.invalidate_cache()


def test_funds_keep_positions_settings_and_audit_apart(env):
    pm = env("pm")
    r = pm.post("/api/v1/funds", json={"id": "bifs", "name": "BIFS", "base_currency": "GBP", "benchmark": "BIFS", "capital": 250000})
    assert r.status_code == 200, r.text
    names = {f["id"]: f for f in pm.get("/api/v1/funds").json()["funds"]}
    assert set(names) == {"main", "bifs"} and names["bifs"]["base_currency"] == "GBP" and names["main"]["base_currency"] == "USD"
    mine, bifs = env("pm"), env("pm", "bifs")
    assert mine.post("/api/v1/portfolio/positions", json={"symbol": "AAPL", "quantity": 10, "avg_cost": 200}).status_code == 200
    assert bifs.post("/api/v1/portfolio/positions", json={"symbol": "AZN.L", "quantity": 5, "avg_cost": 11000}).status_code == 200
    from api import portfolio_store, funds
    tok = funds.CURRENT.set("main")
    try:
        assert [p["symbol"] for p in portfolio_store.list_positions(None)] == ["AAPL"]
    finally:
        funds.CURRENT.reset(tok)
    tok = funds.CURRENT.set("bifs")
    try:
        assert [p["symbol"] for p in portfolio_store.list_positions(None)] == ["AZN.L"]
        from api import fund_store, audit_store
        assert fund_store.get_settings()["capital"] == 250000 and fund_store.get_settings()["base_currency"] == "GBP"
    finally:
        funds.CURRENT.reset(tok)
    assert mine.get("/api/v1/fund/settings").json()["base_currency"] == "USD"
    assert bifs.get("/api/v1/fund/settings").json()["base_currency"] == "GBP"


def test_unknown_fund_and_membership(env):
    pm = env("pm")
    pm.post("/api/v1/funds", json={"id": "corp-b", "name": "Corporation B", "members": ["pm"]})
    assert env("analyst", "corp-b").get("/api/v1/fund/settings").status_code == 403       # not a member
    assert env("pm", "corp-b").get("/api/v1/fund/settings").status_code == 200
    assert env("pm", "nope").get("/api/v1/fund/settings").status_code == 404
    assert "corp-b" not in {f["id"] for f in env("analyst").get("/api/v1/funds").json()["funds"]}
    assert pm.post("/api/v1/funds", json={"id": "Bad Id!", "name": "x"}).status_code == 400


def test_cached_endpoints_answer_per_fund():
    import asyncio
    from api import funds
    from api.utils.cache import ttl_cache
    calls = []

    @ttl_cache(600)
    async def book_view():
        calls.append(funds.current())
        return funds.current()
    for fid in ("main", "bifs", "main", "bifs"):
        tok = funds.CURRENT.set(fid)
        try:
            assert asyncio.run(book_view()) == fid
        finally:
            funds.CURRENT.reset(tok)
    assert calls == ["main", "bifs"]                    # each fund computed once, never served the other's
