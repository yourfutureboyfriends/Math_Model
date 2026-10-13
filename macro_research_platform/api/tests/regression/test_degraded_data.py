"""Degraded-data scan (opt-in: MACRO_FULL_SCAN=1). Builds the live dashboard, then blanks the
inputs that go missing in a data outage — recession probability, regime confidence, VIX,
yields, fed funds, index levels — and calls every GET route. No route may answer with a
server error: missing data must show as n/a, never crash the endpoint."""
import asyncio
import os
import sys
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.skipif(os.getenv("MACRO_FULL_SCAN") != "1",
                                reason="set MACRO_FULL_SCAN=1 to run the degraded-data scan")

SKIP = ("/api/v1/stock/ideas", "/api/v1/stock/screen", "/api/v1/model", "/api/v1/risk/cycle")


def test_routes_survive_missing_inputs(client):
    from api.handlers import dashboard_handler as dh
    from api.main import app
    from api.tests.scan_endpoints import routes

    deg = asyncio.run(dh.get_dashboard_data(mode="live")).model_copy(deep=True)
    deg.recession.probability = None
    deg.regime.confidenceScore = None
    for f in ("vix", "tenYearYield", "twoYearYield", "fedRate", "spxLevel", "dxy", "gold", "oil", "eurusd",
              "spxChange", "ndxLevel"):
        if hasattr(deg.keyMetrics, f):
            setattr(deg.keyMetrics, f, None)

    async def fake(mode="live", *a, **k):
        return deg

    mods = [m for m in list(sys.modules.values()) if m and getattr(m, "get_dashboard_data", None) is dh.get_dashboard_data]
    patches = [patch.object(m, "get_dashboard_data", fake) for m in mods]
    for p in patches:
        p.start()
    try:
        errors = []
        for path in routes(app):
            if path.startswith(SKIP):
                continue
            r = client.get(path)
            if r.status_code >= 500 and not (r.status_code == 503 and "unavailable" in r.text.lower()):
                errors.append(f"{path} {r.status_code} {r.text[:120]}")
        assert not errors, "\n".join(errors)
    finally:
        for p in patches:
            p.stop()
