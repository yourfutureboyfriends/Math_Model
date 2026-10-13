"""Freshness report: never block a request on a cold FRED check when a recent report exists."""
import time

import pytest

from api import data_freshness as dfr


@pytest.fixture
def env(tmp_path, monkeypatch):
    calls = []

    def compute(today=None):
        calls.append(today)
        time.sleep(0.3)
        res = {"available": True, "unknown": 0, "total": 1, "tag": f"fresh{len(calls)}"}
        if today is None:
            dfr._FRESHNESS_CACHE.update(data=res, ts=time.time())
        return res
    monkeypatch.setattr(dfr, "_FRESHNESS_SNAPSHOT", tmp_path / "freshness.json")
    monkeypatch.setattr(dfr, "_FRESHNESS_CACHE", {"data": None, "ts": 0.0})
    monkeypatch.setattr(dfr, "_FRESHNESS_REFRESH", {"thread": None})
    monkeypatch.setattr(dfr, "_compute_live_freshness", compute)
    return calls


def _join():
    t = dfr._FRESHNESS_REFRESH["thread"]
    if t:
        t.join(5)


def test_cold_start_serves_disk_report_then_refreshes(env):
    dfr._save_freshness_snapshot({"tag": "disk"}, time.time() - 3600)
    t0 = time.perf_counter()
    assert dfr.get_live_freshness()["tag"] == "disk"
    assert time.perf_counter() - t0 < 0.1
    _join()
    assert dfr.get_live_freshness()["tag"] == "fresh1" and len(env) == 1


def test_expired_cache_returns_at_once_with_one_refresh(env):
    dfr._FRESHNESS_CACHE.update(data={"tag": "old"}, ts=time.time() - 400)
    assert [dfr.get_live_freshness()["tag"] for _ in range(3)] == ["old"] * 3
    _join()
    assert len(env) == 1


def test_force_and_today_compute_inline(env):
    assert dfr.get_live_freshness(force=True)["tag"] == "fresh1"
    assert dfr.get_live_freshness(today="2026-01-01")["tag"] == "fresh2"


def test_nothing_cached_computes_inline(env):
    assert dfr.get_live_freshness()["tag"] == "fresh1"
