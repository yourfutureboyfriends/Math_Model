import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    from api.routers import data_export as de
    fake = {"SPY": {"2026-01-02": 600.0, "2026-01-05": 601.0, "2026-02-02": 610.0},
            "fred:UNRATE": {"2026-01-01": 4.4, "2026-02-01": 4.5}}
    monkeypatch.setattr(de, "_series", lambda i, start: {d: v for d, v in fake[i].items() if d >= start})
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(de.router)
    return TestClient(app)


def test_history_csv_wide_and_monthly(client):
    r = client.get("/api/v1/data/history?ids=SPY,fred:UNRATE&start=2026-01-01&freq=M")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0] == "date,SPY,fred:UNRATE"
    assert lines[1] == "2026-01,601.0,4.4" and lines[2] == "2026-02,610.0,4.5"


def test_bad_ids_rejected(client):
    assert client.get("/api/v1/data/history?ids=../etc").status_code == 422
    assert client.get("/api/v1/data/latest?ids=" + ",".join(["SPY"] * 26)).status_code == 422


def test_latest_json(client):
    r = client.get("/api/v1/data/latest?ids=SPY,fred:UNRATE&format=json").json()
    assert r["rows"][0] == {"id": "SPY", "value": 610.0, "date": "2026-02-02", "note": ""}
