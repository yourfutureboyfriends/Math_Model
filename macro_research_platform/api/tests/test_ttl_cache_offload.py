"""ttl_cache(offload=True): a cold miss must not block the event loop, and concurrent
misses for one key must share a single computation."""
import asyncio
import time

from api.utils.cache import ttl_cache


def test_offloaded_miss_does_not_block_loop_and_is_single_flight():
    calls = []

    @ttl_cache(60, offload=True)
    async def slow(x):
        calls.append(x)
        time.sleep(0.5)          # blocking work, as in the real endpoints
        return x * 2

    async def main():
        ticks = 0

        async def heartbeat():
            nonlocal ticks
            for _ in range(8):
                await asyncio.sleep(0.05)
                ticks += 1

        results = await asyncio.gather(slow(21), slow(21), slow(21), heartbeat())
        return results[:3], ticks

    results, ticks = asyncio.run(main())
    assert results == [42, 42, 42]
    assert calls == [21]             # one computation for three concurrent requests
    assert ticks == 8                # the loop kept running while the work was blocking
    assert asyncio.run(slow(21)) == 42 and calls == [21]   # served from cache


def test_default_ttl_cache_still_runs_inline():
    @ttl_cache(60)
    async def f():
        return asyncio.get_running_loop() is not None

    assert asyncio.run(f()) is True
