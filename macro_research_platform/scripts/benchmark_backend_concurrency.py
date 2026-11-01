"""Synthetic concurrency benchmark; no live providers or portfolio mutations.
Run from project root: ../.venv/bin/python scripts/benchmark_backend_concurrency.py
"""
import asyncio
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.utils.singleflight import shared_read


async def trial(shared, requests=64):
    calls = 0
    def provider():
        nonlocal calls
        calls += 1
        time.sleep(.08)
        return 1
    async def read():
        if shared:
            return await shared_read(provider)
        return await asyncio.to_thread(provider)
    started = time.perf_counter()
    jobs = [asyncio.create_task(read()) for _ in range(requests)]
    await asyncio.sleep(.01)
    probe_start = time.perf_counter()
    await asyncio.to_thread(lambda: None)
    probe_ms = (time.perf_counter() - probe_start) * 1000
    values = await asyncio.gather(*jobs)
    assert values == [1] * requests
    return {'requests': requests, 'provider_calls': calls, 'elapsed_ms': round((time.perf_counter()-started)*1000,2),
            'unrelated_worker_probe_ms': round(probe_ms,2)}


if __name__ == '__main__':
    print(json.dumps({'method': '64 simultaneous identical reads; synthetic 80ms blocking provider; default asyncio executor',
                      'before_adapter': asyncio.run(trial(False)), 'shared_adapter': asyncio.run(trial(True))}, indent=2))
