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
