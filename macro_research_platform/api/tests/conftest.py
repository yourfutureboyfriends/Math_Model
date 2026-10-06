"""Unit tests run without live FRED by default.

A full run fires hundreds of FRED requests; FRED answers bursts with 429/403 and then
blocks the IP, which took the running platform's data offline. Tests that need FRED skip
without a key. Set MACRO_LIVE_FRED=1 to run them against the real API.
"""
import os

if os.environ.get("MACRO_LIVE_FRED") != "1":
    os.environ["FRED_API_KEY"] = ""


import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolated_dashboard_snapshot(tmp_path_factory):
    """Dashboard builds during tests must not overwrite (or be served from) the running
    platform's on-disk snapshot."""
    from api.handlers import dashboard_handler as dh
    mp = pytest.MonkeyPatch()
    mp.setattr(dh, "_SNAPSHOT_DIR", tmp_path_factory.mktemp("dash_snapshot"))
    from api import data_freshness as dfr
    mp.setattr(dfr, "_FRESHNESS_SNAPSHOT", tmp_path_factory.mktemp("fresh_snapshot") / "freshness.json")
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
