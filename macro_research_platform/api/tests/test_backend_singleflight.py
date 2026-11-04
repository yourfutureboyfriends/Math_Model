import asyncio
import threading
import time
import pytest
from api.utils.singleflight import shared_read, WorkCapacityError
from api.utils.cache import ttl_cache


def test_timeout_does_not_duplicate_still_running_read():
    calls = []
    gate = threading.Event()
    def slow():
        calls.append(1)
        gate.wait(2)
        return 7
    async def check():
        try:
            with pytest.raises(asyncio.TimeoutError):
                await shared_read(slow, timeout=.02)
            follower = asyncio.create_task(shared_read(slow, timeout=1))
            await asyncio.sleep(.02)
            gate.set()
            assert await follower == 7
            assert len(calls) == 1
        finally:
            gate.set()
    asyncio.run(check())


def test_cancellation_isolated_and_funds_never_share_reads():
    from api.funds import CURRENT
    calls = []
    def slow():
        calls.append(CURRENT.get())
        time.sleep(.05)
        return CURRENT.get()
    async def check():
        token = CURRENT.set('test-fund-a')
        try:
            a = asyncio.create_task(shared_read(slow))
            await asyncio.sleep(.005)
            a.cancel()
            with pytest.raises(asyncio.CancelledError):
                await a
            same = asyncio.create_task(shared_read(slow))
            CURRENT.set('test-fund-b')
            other = asyncio.create_task(shared_read(slow))
            assert await same == 'test-fund-a'
            assert await other == 'test-fund-b'
            assert sorted(calls) == ['test-fund-a', 'test-fund-b']
        finally:
            CURRENT.reset(token)
    asyncio.run(check())


def test_capacity_rejects_new_keys_but_allows_existing_followers(monkeypatch):
    from api.utils import singleflight
    monkeypatch.setattr(singleflight, 'MAX_DISTINCT_WORK', 1)
    gate = threading.Event()
    def slow(n):
        gate.wait(2)
        return n
    async def check():
        a = asyncio.create_task(shared_read(slow, 1))
        await asyncio.sleep(.02)
        b = asyncio.create_task(shared_read(slow, 1))
        try:
            with pytest.raises(WorkCapacityError):
                await shared_read(slow, 2)
        finally:
            gate.set()
        assert await a == await b == 1
    asyncio.run(check())


def test_inline_cache_coalesces_and_survives_waiter_cancellation():
    calls = []
    @ttl_cache(60)
    async def slow():
        calls.append(1)
        await asyncio.sleep(.04)
        return 8
    async def check():
        a = asyncio.create_task(slow())
        await asyncio.sleep(.005)
        b = asyncio.create_task(slow())
        a.cancel()
        with pytest.raises(asyncio.CancelledError):
            await a
        assert await b == await slow() == 8
        assert len(calls) == 1
    asyncio.run(check())


def test_thread_cache_coalesces_burst_and_releases_key_locks():
    from concurrent.futures import ThreadPoolExecutor
    from api.marketdata import core
    calls = []
    def fetch():
        calls.append(1)
        time.sleep(.04)
        return {'value': 3}
    key = 'perf:test:thread-burst'
    core._cache.pop(key, None)
    with ThreadPoolExecutor(max_workers=24) as pool:
        values = list(pool.map(lambda _: core._cached(key, 10, fetch), range(48)))
    assert values == [{'value': 3}] * 48
    assert calls == [1]
    assert key not in core._inflight and key not in core._flight_users


def test_background_refresh_queue_is_bounded():
    from api.marketdata import core
    gate = threading.Event()
    def fetch():
        gate.wait(2)
        return {'value': 1}
    try:
        for i in range(40):
            core._refresh_later(f'perf:test:bounded:{i}', fetch)
        with core._lock:
            assert len([k for k in core._refreshing if k.startswith('perf:test:bounded:')]) <= 16
    finally:
        gate.set()
    deadline = time.monotonic() + 3
    while any(k.startswith('perf:test:bounded:') for k in list(core._refreshing)) and time.monotonic() < deadline:
        time.sleep(.01)
    assert not any(k.startswith('perf:test:bounded:') for k in list(core._refreshing))


@pytest.mark.parametrize('kind,status', [('missing',404),('upstream',503),('unexpected',502)])
def test_market_adapter_preserves_error_contract(kind, status):
    from fastapi import HTTPException
    from api.marketdata import core
    from api.routers.marketdata import _run
    def fail():
        raise {'missing':core.NotFound,'upstream':core.Upstream,'unexpected':ValueError}[kind]('test failure')
    async def check():
        with pytest.raises(HTTPException) as exc:
            await _run(fail)
        assert exc.value.status_code == status
    asyncio.run(check())


def test_inline_cache_ttl_starts_when_computation_finishes():
    calls = []
    @ttl_cache(.02)
    async def slow_expiry():
        calls.append(1)
        await asyncio.sleep(.04)
        return 1
    async def check():
        assert await slow_expiry() == await slow_expiry() == 1
        assert calls == [1]
    asyncio.run(check())


def test_async_cache_evicts_expired_entries(monkeypatch):
    from api.utils import cache
    monkeypatch.setattr(cache, '_ASYNC_TTL_CACHE', {str(i):(time.monotonic()-1, i) for i in range(2100)})
    @ttl_cache(60)
    async def bounded():
        return 1
    assert asyncio.run(bounded()) == 1
    assert len(cache._ASYNC_TTL_CACHE) <= 2048


def test_static_holiday_cache_is_keyed_by_calendar_and_year(monkeypatch):
    import holidays
    from api.marketdata.workbench import _exchange_holidays
    calls = []
    def fake(calendar, years):
        calls.append((calendar, years))
        return {}
    _exchange_holidays.cache_clear()
    monkeypatch.setattr(holidays, 'financial_holidays', fake)
    try:
        _exchange_holidays('XNYS', 2026)
        _exchange_holidays('XNYS', 2026)
        _exchange_holidays('XNYS', 2027)
        _exchange_holidays('XHKG', 2026)
        assert len(calls) == 3
    finally:
        _exchange_holidays.cache_clear()
