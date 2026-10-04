"""Full endpoint scan (opt-in: MACRO_FULL_SCAN=1 — it calls every GET route, which is a
burst of upstream requests). Every route must answer without a server error and pass the
invariants in api/tests/scan_endpoints.py. A 503 whose detail says the data is unavailable
is an honest answer, not a failure."""
import os

import pytest

from api.tests.scan_endpoints import routes, scan

pytestmark = pytest.mark.skipif(os.getenv("MACRO_FULL_SCAN") != "1",
                                reason="set MACRO_FULL_SCAN=1 to scan every endpoint")


def test_every_get_endpoint(client):
    from api.main import app
    report = scan(client, routes(app))
    failures = {}
    for path, (code, issues) in report.items():
        real = [i for i in issues if not (code == 503 and "unavailable" in i.lower())]
        if real:
            failures[path] = real
    assert not failures, "\n".join(f"{p}: {v[:3]}" for p, v in sorted(failures.items()))
