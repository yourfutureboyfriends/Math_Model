"""A FRED batch that hits its deadline must keep the series that finished and fall back to
the last good (disk) copy for the rest — not blank every input on the dashboard."""
import asyncio
import time

from api.handlers import macro_inputs as mi


def test_timeout_keeps_finished_series_and_uses_disk_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(mi, "_DISK_DIR", tmp_path)
    monkeypatch.setattr(mi, "_FRED_SERIES_CACHE", {})
    mi._disk_save("series_SLOW_30d", {"dates": ["2026-01-01"], "values": [4.2]})

    def fake(sid, days):
        if sid == "SLOW":
            time.sleep(1.0)
        return mi.DatedSeries(sid, ["2026-10-01"], [1.0])
    monkeypatch.setattr(mi, "_fetch_fred_history_sync", fake)

    async def go():
        out = await mi.load_fred_series(["FAST1", "FAST2", "SLOW"], days=30, timeout=0.3)
        assert out["FAST1"].latest == 1.0 and out["FAST2"].latest == 1.0
        assert out["SLOW"].latest == 4.2, "slow series falls back to its disk copy"
        await asyncio.sleep(1.0)                    # the slow fetch finishes in the background
        assert mi._FRED_SERIES_CACHE["SLOW"][1].latest == 1.0
    asyncio.run(go())
