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


class Gate:
    """The fake rebuild blocks until the test opens the gate — so "the caller did not wait for the rebuild" is
    checked deterministically (the gate is still shut when the answer arrives), not with a wall-clock budget
    that a busy machine can blow."""

    def __init__(self, open_=False):
        self.open = open_
        self._ev = None

    def event(self):
        if self._ev is None:                      # created inside the running loop
            self._ev = asyncio.Event()
            if self.open:
                self._ev.set()
        return self._ev

    def release(self):
        self.open = True
        if self._ev is not None:
            self._ev.set()


class Calls(list):
    gate: Gate


@pytest.fixture
def env(tmp_path, monkeypatch):
    calls = Calls()
    gate = Gate()

    async def build(mode="live"):
        calls.append(mode)
        await gate.event().wait()    # a slow rebuild: callers must not wait for it
        return FakeDash(f"fresh{len(calls)}")

    monkeypatch.setattr(dh, "_SNAPSHOT_DIR", tmp_path)
    monkeypatch.setattr(dh, "DashboardData", FakeDash)
    monkeypatch.setattr(dh, "_build_dashboard_data", build)
    monkeypatch.setattr(dh, "_DASHBOARD_CACHE", {})
    monkeypatch.setattr(dh, "_DASHBOARD_LOCKS", {})
    monkeypatch.setattr(dh, "_REFRESHING", {})
    calls.gate = gate
    return calls


async def _settle():
    for t in list(dh._REFRESHING.values()):
        await t


def test_cold_start_serves_disk_snapshot_then_refreshes(env):
    async def go():
        dh._save_snapshot("live", time.time() - 300, FakeDash("disk"))
        d = await asyncio.wait_for(dh.get_dashboard_data("live"), timeout=30)
        assert not env.gate.open                       # answered while the rebuild was still blocked
        assert d.tag == "disk" and d.metadata.dataStatus == "stale" and "snapshot" in d.metadata.validationWarnings
        env.gate.release()
        await _settle()
        assert (await dh.get_dashboard_data("live")).tag == "fresh1"
        assert json.loads(dh._snapshot_path("live").read_text())["data"]["tag"] == "fresh1"
    asyncio.run(go())


def test_expired_cache_served_instantly_with_single_refresh(env):
    async def go():
        dh._DASHBOARD_CACHE["live"] = (time.time() - 120, FakeDash("old"))
        out = await asyncio.wait_for(asyncio.gather(*(dh.get_dashboard_data("live") for _ in range(5))), timeout=30)
        assert not env.gate.open                       # all five answered while the rebuild was still blocked
        assert {d.tag for d in out} == {"old"}
        env.gate.release()
        await _settle()
        assert env == ["live"], "concurrent requests must trigger one rebuild"
    asyncio.run(go())


def test_no_cache_no_snapshot_builds_inline(env):
    env.gate.release()                                 # nothing to serve, so the caller waits for the build
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
