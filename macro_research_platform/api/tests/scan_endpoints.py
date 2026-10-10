"""
Endpoint scanner: call every parameterless GET route and check each response against
invariants that held real bugs in this codebase. Used by test_endpoint_scan.py; can also be
run directly (`python -m api.tests.scan_endpoints`) for a full report.

Invariants
  * HTTP status < 500, body is JSON.
  * No NaN / ±Infinity anywhere.
  * Fields named like probabilities lie in [0, 1] (or [0, 100] when named *_pct / *Pct).
  * Prices / levels / spot values are not negative.
  * No hard-coded placeholder strings ("TBD", "lorem", "mock", "sample data", "placeholder").
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Tuple

SKIP_PREFIXES = ("/api/auth/", "/api/admin/", "/docs", "/openapi", "/redoc", "/ws", "/socket.io",
                 "/api/report/generate")          # binary PDF
SKIP_EXACT = {"/api/data/refresh"}
PLACEHOLDER = re.compile(r"\b(TBD|lorem ipsum|mock data|sample data|placeholder|dummy)\b", re.I)
PROB_KEY = re.compile(r"(^|_)(prob|probability)$|Prob(ability)?$", re.I)
PRICE_KEY = re.compile(r"^(price|spot|level|close|last_price|nav)$", re.I)


def routes(app) -> List[str]:
    out = []
    for r in app.routes:
        path = getattr(r, "path", "")
        methods = getattr(r, "methods", set()) or set()
        if "GET" not in methods or "{" in path or not path.startswith("/api"):
            continue
        if path in SKIP_EXACT or path.startswith(SKIP_PREFIXES):
            continue
        out.append(path)
    return sorted(set(out))


def _walk(obj: Any, path: str = "$"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:200]):
            yield from _walk(v, f"{path}[{i}]")
    else:
        yield path, obj


def check(body: Any) -> List[str]:
    issues = []
    for p, v in _walk(body):
        key = p.rsplit(".", 1)[-1].split("[")[0]
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            issues.append(f"{p}: non-finite {v}")
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            if PROB_KEY.search(key):
                hi = 100 if key.lower().endswith("pct") else 1
                if not (0 <= v <= hi):
                    issues.append(f"{p}: probability out of range ({v})")
            if PRICE_KEY.match(key) and v < 0:
                issues.append(f"{p}: negative price/level ({v})")
        elif isinstance(v, str) and PLACEHOLDER.search(v):
            issues.append(f"{p}: placeholder text {v[:60]!r}")
    return issues


def scan(client, paths: List[str]) -> Dict[str, Tuple[int, List[str]]]:
    report = {}
    for path in paths:
        try:
            r = client.get(path)
        except Exception as e:                       # an unhandled exception is a 500
            report[path] = (500, [f"raised {type(e).__name__}: {str(e)[:120]}"])
            continue
        issues = []
        if r.status_code >= 500:
            issues.append(f"HTTP {r.status_code}: {r.text[:160]}")
        else:
            ctype = r.headers.get("content-type", "")
            if "json" in ctype:
                try:
                    issues += check(r.json())
                except ValueError as e:
                    issues.append(f"invalid JSON: {e}")
        report[path] = (r.status_code, issues)
    return report


if __name__ == "__main__":                            # pragma: no cover - manual report
    import tempfile
    import time
    from fastapi.testclient import TestClient
    import api.core.auth as auth
    from api.core import accounts
    tmp = tempfile.mkdtemp()
    auth.get_db_path = lambda: f"{tmp}/users.db"       # never touch real accounts
    accounts.migrate()
    accounts.set_password("admin", "Scanner-Admin-Pass-2026!")
    from api.main import app
    with TestClient(app) as c:
        c.headers["Authorization"] = f"Bearer {accounts.issue_token(accounts.get_user('admin'))}"
        paths = routes(app)
        t = time.time()
        rep = scan(c, paths)
        bad = {p: v for p, v in rep.items() if v[1]}
        print(f"{len(paths)} endpoints scanned in {time.time() - t:.0f}s; {len(bad)} with issues")
        for p, (code, issues) in sorted(bad.items()):
            print(f"\n{p} [{code}]")
            for i in issues[:8]:
                print("   ", i)
