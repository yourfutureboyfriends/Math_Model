"""The pipeline must invalidate the cache that is actually served.

api/main.py held a second dict named _DASHBOARD_CACHE, shaped {"data", "timestamp", "mode"}, and
passed it to run_daily_pipeline. Every reader — the snapshot builder, the book router, the field
alerts — read the handler's cache instead, keyed mode -> (timestamp, data). So the daily pipeline
set cache_cleared=True while the served build stayed put, and cacheAgeSeconds was time.time() minus
a timestamp that was only ever 0.0, i.e. roughly 57 years.

The identity assertion is the point of this file: it fails if the two ever diverge again, which is
what a same-named module-level dict in a 1,700-line assembler makes easy to do.
"""
import threading
import time

import pytest

from api import data_pipeline, main
from api.handlers import dashboard_handler as dh


def test_main_and_the_handler_share_one_cache_object():
    assert main._served_dashboard_cache() is dh.served_cache()
    assert main._served_dashboard_cache() is dh._DASHBOARD_CACHE


def test_a_build_stored_by_the_handler_is_visible_to_main():
    cache = dh.served_cache()
    cache.clear()
    try:
        cache["live"] = (time.time(), object())
        assert main._served_dashboard_cache().get("live") is not None
    finally:
        cache.clear()


def test_invalidate_cache_clears_the_mode_keyed_shape():
    cache = {"live": (time.time(), object()), "backtest": (time.time(), object())}
    data_pipeline.invalidate_cache(cache, threading.Lock())
    # The old implementation set cache["data"] = None and cache["timestamp"] = 0.0, which left both
    # real entries in place and added two keys nothing reads.
    assert cache == {}


def test_run_daily_pipeline_reports_cleared_only_when_the_served_cache_is_empty(monkeypatch):
    monkeypatch.setattr(data_pipeline, "fetch_all_latest_values", lambda: {})
    monkeypatch.setattr(data_pipeline, "update_csv", lambda row: True)

    cache = dh.served_cache()
    cache["live"] = (time.time(), object())
    try:
        status = data_pipeline.run_daily_pipeline(cache, threading.Lock())
        assert status["cache_cleared"] is True
        assert cache == {}, "cache_cleared was reported but the served build survived"
    finally:
        cache.clear()


def test_run_daily_pipeline_does_not_claim_cleared_when_the_csv_write_fails(monkeypatch):
    monkeypatch.setattr(data_pipeline, "fetch_all_latest_values", lambda: {})
    monkeypatch.setattr(data_pipeline, "update_csv", lambda row: False)

    cache = dh.served_cache()
    cache["live"] = (time.time(), object())
    try:
        status = data_pipeline.run_daily_pipeline(cache, threading.Lock())
        assert status["cache_cleared"] is False
        assert "live" in cache, "nothing was refreshed, so the served build must be kept"
    finally:
        cache.clear()


def test_cache_age_comes_from_the_served_build_not_a_zero_timestamp():
    # The regression: time.time() - 0.0 ≈ 1.79e9 seconds ≈ 57 years, served as cacheAgeSeconds.
    cache = dh.served_cache()
    cache.clear()
    try:
        assert cache.get("live") is None            # cold: no build, so no age to report
        cache["live"] = (time.time() - 42.0, object())
        entry = main._served_dashboard_cache().get("live")
        age = time.time() - entry[0]
        assert age == pytest.approx(42.0, abs=2.0)
        assert age < 3600, "a served build's age must be bounded, not the epoch offset"
    finally:
        cache.clear()
