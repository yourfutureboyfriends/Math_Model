"""Unit tests run without live FRED by default.

A full run fires hundreds of FRED requests; FRED answers bursts with 429/403 and then
blocks the IP, which took the running platform's data offline. Tests that need FRED skip
without a key. Set MACRO_LIVE_FRED=1 to run them against the real API.
"""
import os
import tempfile

if os.environ.get("MACRO_LIVE_FRED") != "1":
    os.environ["FRED_API_KEY"] = ""

# Tests never touch the running platform's database: every module resolves the app database through DATABASE_URL
# (api/core/app_db.py), so point it at a throwaway file before anything imports the config. (Deploys, stops and audit
# entries from test runs were landing in the live audit log.) MACRO_TEST_REAL_DB=1 opts out.
if os.environ.get("MACRO_TEST_REAL_DB") != "1":
    os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(prefix="macro_test_db_"), "app.db")


# MACRO_TEST_OFFLINE=1: refuse every outside connection (localhost still works), so the suite is fast and
# deterministic; tests marked `network` (they read live Yahoo / FRED / feeds) are skipped.
_OFFLINE = os.environ.get("MACRO_TEST_OFFLINE") == "1"
if _OFFLINE:
    # yfinance talks through libcurl (curl_cffi), which bypasses Python sockets: send all proxied traffic to a
    # closed local port so it fails at once too
    for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        os.environ[_k] = "http://127.0.0.1:9"
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = "localhost,127.0.0.1,::1,testserver"
    import socket as _socket
    _orig_connect = _socket.socket.connect

    def _guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if isinstance(host, str) and host not in ("127.0.0.1", "::1", "localhost") and not host.startswith("/"):
            raise OSError(f"network disabled in offline test mode ({host})")
        return _orig_connect(self, address)
    _socket.socket.connect = _guarded_connect


import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "network: reads live outside data (skipped with MACRO_TEST_OFFLINE=1)")


def pytest_collection_modifyitems(config, items):
    if _OFFLINE:
        skip = pytest.mark.skip(reason="needs the network (MACRO_TEST_OFFLINE=1)")
        for it in items:
            if "network" in it.keywords:
                it.add_marker(skip)


@pytest.fixture(autouse=True, scope="session")
def _isolated_dashboard_snapshot(tmp_path_factory):
    """Dashboard builds during tests must not overwrite (or be served from) the running
    platform's on-disk snapshot."""
    from api.handlers import dashboard_handler as dh
    mp = pytest.MonkeyPatch()
    mp.setattr(dh, "_SNAPSHOT_DIR", tmp_path_factory.mktemp("dash_snapshot"))
    from api import data_freshness as dfr
    mp.setattr(dfr, "_FRESHNESS_SNAPSHOT", tmp_path_factory.mktemp("fresh_snapshot") / "freshness.json")
    from api.model import engine as me
    mp.setattr(me, "_SNAPSHOT_DIR", tmp_path_factory.mktemp("model_snapshot"))
    from api.marketdata import core as mcore                    # screens' saved copies (survive restarts)
    mp.setattr(mcore, "PERSIST_DIR", tmp_path_factory.mktemp("screen_cache"))
    from api.providers import crypto_live as cl                 # no live exchange prices over mocked quotes
    mp.setattr(cl, "price", lambda coin: {})
    mp.setattr(cl, "prices", lambda: {"coins": {}, "source": None})
    yield
    mp.undo()


def pytest_collection_finish(session):
    """`database` must be the project-root package. A test that puts api/ on sys.path makes
    `import database.db` resolve to a stale, gitignored api/database copy whose functions
    have different signatures — failures then depend on test order."""
    import sys
    from pathlib import Path
    api_dir = Path(__file__).resolve().parents[1]
    bad = [p for p in sys.path if p and Path(p).resolve() == api_dir]
    assert not bad, f"api/ is on sys.path ({bad}); insert the project root instead"
    import database.db as d
    assert Path(d.__file__).resolve().parent == api_dir.parent / "database", d.__file__
