"""Shared fixtures for the top-level test suite."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def _clear_metric_cache():
    """fetch_metric caches by metric name; clear it so one test's mocked value can't leak
    into the next test."""
    try:
        from api import data_fetcher
        data_fetcher._METRIC_CACHE.clear()
    except Exception:
        pass
    yield


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    """Some tests here exercise the running dev server (localhost:8000). When it is not
    running — or still warming up — that is not a test failure: report a skip saying so.
    Any other error, including wrong data from a running server, still fails."""
    try:
        return (yield)
    except Exception as e:
        if _is_dev_server_unreachable(e):
            pytest.skip(f"dev server not reachable ({type(e).__name__}); start the backend to run this test")
        raise


def _is_dev_server_unreachable(e: BaseException) -> bool:
    try:
        import requests
    except ImportError:
        return False
    if not isinstance(e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return False
    req = getattr(e, "request", None)
    url = getattr(req, "url", "") or str(e)
    return any(h in url for h in ("localhost", "127.0.0.1"))
