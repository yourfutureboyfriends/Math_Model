"""Macro model cold start: the last result on disk is served at once (a cold run took ~5 min)."""
import asyncio
import time

from api.model import engine as me


def test_cold_call_serves_snapshot_without_computing(tmp_path, monkeypatch):
    monkeypatch.setattr(me, "_SNAPSHOT_DIR", tmp_path)
    monkeypatch.setattr(me, "_CACHE", {})
    monkeypatch.setattr(me, "_REFRESHING", {})
    key = me.params_hash(me.ModelParams.from_dict(None))
    me._save_snapshot(key, {"available": True, "tag": "disk"})
    calls = []

    async def slow_load():
        calls.append(1)
        await asyncio.sleep(10)
    import dataclasses
    from api.model.economies import ECONOMIES
    slow_us = dataclasses.replace(ECONOMIES["us"], loader=slow_load)
    monkeypatch.setattr(me, "get_economy", lambda eid="us": slow_us)

    async def go():
        t0 = time.perf_counter()
        out = await me.run_model(None)
        assert time.perf_counter() - t0 < 0.5
        assert out["tag"] == "disk" and out["snapshot"]["note"]
        await asyncio.sleep(0.05)                  # the background refresh has started
        assert calls == [1]
    asyncio.run(go())


def test_old_snapshot_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(me, "_SNAPSHOT_DIR", tmp_path)
    me._save_snapshot("k", {"available": True})
    monkeypatch.setattr(me, "_SNAPSHOT_MAX_AGE", -1)
    assert me._load_snapshot("k") is None
