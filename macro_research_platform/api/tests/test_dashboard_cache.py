"""Dashboard cache: stale-while-revalidate and the on-disk snapshot. No request may wait on a
5-25s build when a usable dashboard exists (the frontend times out at 8s)."""
import asyncio
import copy
import json
import time
from types import SimpleNamespace

import pytest

from api.handlers import dashboard_handler as dh


class FakeDash:
    def __init__(self, tag, degraded=False):
        self.tag = tag
        self.metadata = SimpleNamespace(dataStatus="current", validationWarnings=None)
        self.recession = SimpleNamespace(logisticProb=None if degraded else 0.1)

    def model_copy(self, deep=False):
        return copy.deepcopy(self)

    def model_dump_json(self):
        return json.dumps({"tag": self.tag})

    @classmethod
    def model_validate(cls, raw):
        return cls(raw["tag"])


@pytest.fixture
def env(tmp_path, monkeypatch):
    calls = []

    async def build(mode="live"):
        calls.append(mode)
        await asyncio.sleep(0.3)
        return FakeDash(f"fresh{len(calls)}")

    monkeypatch.setattr(dh, "_SNAPSHOT_DIR", tmp_path)
    monkeypatch.setattr(dh, "DashboardData", FakeDash)
    monkeypatch.setattr(dh, "_build_dashboard_data", build)
    monkeypatch.setattr(dh, "_DASHBOARD_CACHE", {})
    monkeypatch.setattr(dh, "_DASHBOARD_LOCKS", {})
    monkeypatch.setattr(dh, "_REFRESHING", {})
    return calls


async def _settle():
    for t in list(dh._REFRESHING.values()):
        await t


def test_cold_start_serves_disk_snapshot_then_refreshes(env):
    async def go():
        dh._save_snapshot("live", time.time() - 300, FakeDash("disk"))
        t0 = time.perf_counter()
        d = await dh.get_dashboard_data("live")
        assert time.perf_counter() - t0 < 0.1
        assert d.tag == "disk" and d.metadata.dataStatus == "stale" and "snapshot" in d.metadata.validationWarnings
        await _settle()
        assert (await dh.get_dashboard_data("live")).tag == "fresh1"
        assert json.loads(dh._snapshot_path("live").read_text())["data"]["tag"] == "fresh1"
    asyncio.run(go())


def test_expired_cache_served_instantly_with_single_refresh(env):
    async def go():
        dh._DASHBOARD_CACHE["live"] = (time.time() - 120, FakeDash("old"))
        t0 = time.perf_counter()
        out = await asyncio.gather(*(dh.get_dashboard_data("live") for _ in range(5)))
        assert time.perf_counter() - t0 < 0.1
        assert {d.tag for d in out} == {"old"}
        await _settle()
        assert env == ["live"], "concurrent requests must trigger one rebuild"
    asyncio.run(go())


def test_no_cache_no_snapshot_builds_inline(env):
    assert asyncio.run(dh.get_dashboard_data("live")).tag == "fresh1"


def test_failing_refresh_keeps_last_good_and_flags_it(env, monkeypatch):
    async def boom(mode="live"):
        raise RuntimeError("FRED down")
    monkeypatch.setattr(dh, "_build_dashboard_data", boom)

    async def go():
        dh._DASHBOARD_CACHE["live"] = (time.time() - 1200, FakeDash("old"))
        d = await dh.get_dashboard_data("live")
        await _settle()
        assert d.tag == "old" and d.metadata.dataStatus == "stale" and "failing" in d.metadata.validationWarnings
        assert dh._DASHBOARD_CACHE["live"][1].metadata.dataStatus == "current"   # the cached copy is not mutated
    asyncio.run(go())


def test_degraded_build_not_saved_as_snapshot(env):
    dh._store("live", FakeDash("degraded", degraded=True))
    assert not dh._snapshot_path("live").exists()
