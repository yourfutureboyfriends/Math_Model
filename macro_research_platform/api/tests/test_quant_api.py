"""Quant Lab HTTP API end to end, offline: synthetic prices, temporary accounts and app DB."""
import sqlite3

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient


def _synthetic_panel(symbols, start=None, end=None):
    rng = np.random.default_rng(abs(hash(tuple(symbols))) % 2**32)
    idx = pd.bdate_range("2004-01-01", "2024-12-31")
    syms = list(dict.fromkeys(symbols))
    r = rng.normal(0.0003, 0.01, size=(len(idx), len(syms)))
    close = pd.DataFrame(100 * np.cumprod(1 + r, axis=0), index=idx, columns=syms)
    if start:
        close = close[close.index >= pd.Timestamp(start)]
    open_ = close.shift(1).bfill()
    return {"close": close, "open": open_, "high": close, "low": close, "volume": close * 0 + 1e6}, []


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import api.core.auth as auth
    from api.core import accounts
    monkeypatch.setattr(auth, "get_db_path", lambda: str(tmp_path / "users.db"))
    accounts.invalidate_cache()
    accounts.migrate()
    accounts.set_password("quant", "Quant-Test-Pass-2026!")
    accounts.set_password("analyst", "Analyst-Test-Pass-2026!")

    def conn():
        c = sqlite3.connect(tmp_path / "app.db")
        c.row_factory = sqlite3.Row
        return c
    from api.quant import data as qdata, store
    monkeypatch.setattr(store, "_conn", conn)
    monkeypatch.setattr(store, "_ready", False)
    monkeypatch.setattr(qdata, "panel", _synthetic_panel)
    from api.main import app
    c = TestClient(app)                     # no lifespan: no scheduler / warm-up
    c.headers["Authorization"] = f"Bearer {accounts.issue_token(accounts.get_user('quant'))}"
    c.analyst = {"Authorization": f"Bearer {accounts.issue_token(accounts.get_user('analyst'))}"}
    yield c
    accounts.invalidate_cache()


SPEC = {"name": "Test trend", "universe": {"symbols": ["SPY", "TLT", "GLD"]}, "signal": "mom(126)",
        "selection": {"mode": "top_n", "n": 1}, "rebalance": "monthly", "start": "2008-01-01"}


def test_meta_lists_functions_templates_and_universes(client):
    m = client.get("/api/v1/quant/meta").json()
    assert "Returns & momentum" in m["functions"]["functions"]
    assert len(m["templates"]) >= 10 and any(t["id"] == "house_multi_trend" for t in m["templates"])
    assert any(u["id"] == "cross_asset" for u in m["universes"])


def test_validate_reports_errors(client):
    assert client.post("/api/v1/quant/validate", json={"formula": "rank(mom(252, 21))"}).json() == {"ok": True}
    bad = client.post("/api/v1/quant/validate", json={"formula": "__import__('os')"}).json()
    assert bad["ok"] is False and ("not allowed" in bad["error"] or "Unknown" in bad["error"])


def test_backtest_report_and_trial_counting(client):
    r = client.post("/api/v1/quant/backtest", json={"spec": SPEC})
    assert r.status_code == 200, r.text
    j = r.json()
    for k in ("metrics", "curve", "monthly", "robustness", "verdict", "positions", "vs_benchmark"):
        assert k in j
    assert j["robustness"]["deflated_sharpe"]["trials"] == 1
    j2 = client.post("/api/v1/quant/backtest", json={"spec": {**SPEC, "signal": "mom(189)"}}).json()
    assert j2["robustness"]["deflated_sharpe"]["trials"] == 2             # a second variant was tried
    assert client.post("/api/v1/quant/backtest", json={"spec": {**SPEC, "signal": "nope(1)"}}).status_code == 400


def test_save_edit_and_ownership(client):
    s = client.post("/api/v1/quant/strategies", json={"spec": SPEC}).json()
    assert s["name"] == "Test trend" and s["owner"] == "quant"
    up = client.put(f"/api/v1/quant/strategies/{s['id']}", json={"spec": {**SPEC, "name": "Renamed"}})
    assert up.json()["name"] == "Renamed"
    other = client.put(f"/api/v1/quant/strategies/{s['id']}", json={"spec": SPEC}, headers=client.analyst)
    assert other.status_code == 403
    assert len(client.get("/api/v1/quant/strategies").json()["strategies"]) == 1


def test_sweep_and_combine(client):
    sw = client.post("/api/v1/quant/sweep", json={"spec": {**SPEC, "signal": "mom({n})"}, "params": {"n": [63, 126, 252]}})
    assert sw.status_code == 200, sw.text
    assert len(sw.json()["rows"]) == 3 and "interpretation" in sw.json()
    cb = client.post("/api/v1/quant/combine", json={"members": [{"spec": SPEC}, {"spec": {**SPEC, "signal": "-vol(63)"}}],
                                                    "method": "erc"})
    assert cb.status_code == 200, cb.text
    assert set(cb.json()["weights"]) == {"Test trend", "Test trend′"}


def test_deploy_to_quant_trader_and_stop(client):
    d = client.post("/api/v1/quant/trader/deploy", json={"spec": SPEC, "capital": 250000})
    assert d.status_code == 200, d.text
    book = client.get("/api/v1/quant/trader?refresh=true").json()
    assert book["capital"] == 250000 and book["deployments"][0]["status"] == "too early"
    assert client.post("/api/v1/quant/trader/deploy", json={"spec": SPEC}, headers=client.analyst).status_code == 403
    assert client.delete(f"/api/v1/quant/trader/deployments/{d.json()['id']}").status_code == 200
    assert client.get("/api/v1/quant/trader?refresh=true").json()["deployments"] == []
