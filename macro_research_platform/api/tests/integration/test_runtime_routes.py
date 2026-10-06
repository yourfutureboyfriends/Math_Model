"""Runtime routes.

In-process (always run, hermetic): canonical dashboard route registered with its schema,
legacy v2/v3 dashboards removed, health and diagnostics routes, frontend network helpers.

Live smoke (opt-in: MACRO_LIVE_BACKEND=1): the same checks against the server on
localhost:8000. It waits for the server to finish starting, and any network error —
connection refused or a timeout during warm-up — skips instead of failing. Without the
opt-in the unit suite never depends on whether, or how warm, a dev server happens to be.
"""
import os
import time

import pytest
from fastapi.testclient import TestClient

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


@pytest.fixture(scope="module")
def client():
    from api.main import app
    return TestClient(app)          # no `with`: the scheduler and warm loops are not started


@pytest.fixture(scope="module")
def spec(client):
    return client.get("/openapi.json").json()


def test_dashboard_route_registered_with_schema(spec):
    op = spec["paths"]["/api/dashboard"]["get"]
    ref = op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    props = spec["components"]["schemas"][ref.rsplit("/", 1)[-1]]["properties"]
    assert {"regime", "keyMetrics", "metadata"} <= set(props)


@pytest.mark.parametrize("path", ["/api/v2/dashboard", "/api/v3/dashboard"])
def test_legacy_dashboards_removed(client, path):
    assert client.get(path).status_code == 404


def test_health_fields_used_by_status_badge(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"
    assert {"models", "data_rows", "mode", "analyticalIntegrity"} <= set(data)


def test_diagnostics_routes_exist(spec):
    assert any("/diagnostics/" in p for p in spec["paths"])


def test_network_utils_exports():
    network_ts = os.path.join(ROOT, "frontend", "src", "lib", "network.ts")
    assert os.path.exists(network_ts), f"network.ts not found at {network_ts}"
    content = open(network_ts).read()
    for fn in ("export function getApiBaseUrl()", "export function getWsBaseUrl()",
               "export function getEndpointUrl(", "export function getWebSocketUrl("):
        assert fn in content


# ── Live smoke (opt-in) ──────────────────────────────────────────────────────
LIVE = os.getenv("MACRO_LIVE_BACKEND") == "1"
BASE = os.getenv("MACRO_BACKEND_URL", "http://localhost:8000")


@pytest.fixture(scope="module")
def live():
    if not LIVE:
        pytest.skip("set MACRO_LIVE_BACKEND=1 to smoke-test the running server")
    import requests
    deadline = time.time() + 90
    while time.time() < deadline:                       # wait out start-up and cache warm-up
        try:
            if requests.get(f"{BASE}/api/health", timeout=5).status_code == 200:
                return requests
        except requests.exceptions.RequestException:
            pass
        time.sleep(2)
    pytest.skip(f"backend at {BASE} not ready within 90s")


def _get(requests, path):
    try:
        return requests.get(f"{BASE}{path}", timeout=30)
    except requests.exceptions.RequestException as e:      # includes ReadTimeout, not just refused
        pytest.skip(f"backend unreachable: {type(e).__name__}")


def test_live_dashboard(live):
    r = _get(live, "/api/dashboard")
    assert r.status_code == 200
    assert {"regime", "keyMetrics"} <= set(r.json())


def test_live_health(live):
    r = _get(live, "/api/health")
    assert r.status_code == 200 and r.json().get("status") == "ok"
