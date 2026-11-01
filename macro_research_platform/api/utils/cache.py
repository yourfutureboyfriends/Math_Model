"""Thread-safe TTL cache manager."""
from datetime import datetime
from threading import Lock
from typing import Optional, Callable, Any
import logging
from api.workflows.telemetry import count

logger = logging.getLogger(__name__)


class TTLCache:
    """Thread-safe cache with time-to-live."""

    def __init__(self, ttl_seconds: int, name: str = "cache"):
        """
        Initialize TTL cache.

        Args:
            ttl_seconds: Time to live in seconds
            name: Cache name for logging
        """
        self.ttl = ttl_seconds
        self.name = name
        self.data: Optional[Any] = None
        self.timestamp: Optional[datetime] = None
        self.lock = Lock()

    def get(self, fetch_fn: Callable[[], Any]) -> Any:
        """
        Get cached data or fetch fresh data.

        Args:
            fetch_fn: Function to fetch fresh data if cache expired

        Returns:
            Cached or fresh data
        """
        with self.lock:
            if self.is_valid():
                logger.debug(f"[{self.name}] Cache hit")
                return self.data

            logger.info(f"[{self.name}] Cache miss, fetching fresh data")
            try:
                self.data = fetch_fn()
                self.timestamp = datetime.now()
                return self.data
            except Exception as e:
                logger.error(f"[{self.name}] Fetch failed: {e}")
                # Return stale data if available, else raise
                if self.data is not None:
                    logger.warning(f"[{self.name}] Returning stale data")
                    return self.data
                raise

    def is_valid(self) -> bool:
        """Check if cache is still valid."""
        if self.data is None or self.timestamp is None:
            return False
        elapsed = (datetime.now() - self.timestamp).total_seconds()
        return elapsed < self.ttl

    def invalidate(self):
        """Force cache invalidation."""
        with self.lock:
            logger.info(f"[{self.name}] Cache invalidated")
            self.data = None
            self.timestamp = None

    def get_age(self) -> Optional[float]:
        """Get cache age in seconds."""
        if self.timestamp is None:
            return None
        return (datetime.now() - self.timestamp).total_seconds()


# ── Async endpoint TTL cache decorator (P1 perf) ──────────────────────────────
import time as _time
import functools as _functools
import asyncio as _asyncio

_ASYNC_CACHE_LOCK = Lock()
_ASYNC_TTL_CACHE = {}   # key -> (expires_at, value)


def ttl_cache(seconds: float, offload: bool = False):
    """Cache an async endpoint's result for `seconds`, keyed by function name + args.

    For endpoints that re-fetch live FRED/market data on every call (health, cot, rates,
    market, yield-curve, calendar) this turns repeat calls into instant hits without
    changing what the data means. TTL should match how often the source actually moves.

    offload=True runs a cache miss in a worker thread with its own event loop, so an
    endpoint that does blocking I/O or heavy numpy work can't freeze the main event loop
    (which would stall every other request, health checks included). Concurrent misses
    for the same key share one computation. Only for endpoints that don't touch objects
    bound to the main loop (the startup warm loop already runs these the same way).
    """
    def deco(fn):
        inflight: dict = {}

        @_functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            # the current fund is part of the key: one fund's book analytics never answer for another
            from api.funds import CURRENT as _FUND
            key = f"{fn.__module__}.{fn.__name__}|{_FUND.get()}|{args!r}|{tuple(sorted(kwargs.items()))!r}"
            now = _time.monotonic()
            with _ASYNC_CACHE_LOCK:
                hit = _ASYNC_TTL_CACHE.get(key)
            if hit is not None and hit[0] > now:
                count('async_cache.hit')
                return hit[1]
            loop = _asyncio.get_running_loop()
            fkey = (id(loop), key)
            fut = inflight.get(fkey)
            if fut is None:
                count('async_cache.miss')
                fut = loop.create_task(_asyncio.to_thread(_asyncio.run, fn(*args, **kwargs)) if offload else fn(*args, **kwargs))
                inflight[fkey] = fut

                def _done(f, fkey=fkey, key=key):
                    inflight.pop(fkey, None)
                    if not f.cancelled() and f.exception() is None:
                        # TTL starts after completion, not before a slow upstream request.
                        with _ASYNC_CACHE_LOCK:
                            _ASYNC_TTL_CACHE[key] = (_time.monotonic() + seconds, f.result())
                            if len(_ASYNC_TTL_CACHE) > 2048:
                                # Remove expired entries first; then evict earliest expiry.
                                for old_key, hit in list(_ASYNC_TTL_CACHE.items()):
                                    if hit[0] <= _time.monotonic():
                                        _ASYNC_TTL_CACHE.pop(old_key, None)
                                if len(_ASYNC_TTL_CACHE) > 2048:
                                    for old_key in sorted(_ASYNC_TTL_CACHE, key=lambda k: _ASYNC_TTL_CACHE[k][0])[:512]:
                                        _ASYNC_TTL_CACHE.pop(old_key, None)
                fut.add_done_callback(_done)
            else:
                count('async_cache.joined')
            value = await _asyncio.shield(fut)
            return value
        return wrapper
    return deco
