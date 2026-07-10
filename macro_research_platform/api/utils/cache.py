"""Thread-safe TTL cache manager."""
from datetime import datetime
from threading import Lock
from typing import Optional, Callable, Any
import logging

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

_ASYNC_TTL_CACHE = {}   # key -> (expires_at, value)


def ttl_cache(seconds: float):
    """Cache an async endpoint's result for `seconds`, keyed by function name + args.

    For endpoints that re-fetch live FRED/market data on every call (health, cot, rates,
    market, yield-curve, calendar) this turns repeat calls into instant hits without
    changing what the data means. TTL should match how often the source actually moves.
    """
    def deco(fn):
        @_functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            key = f"{fn.__module__}.{fn.__name__}|{args!r}|{tuple(sorted(kwargs.items()))!r}"
            now = _time.time()
            hit = _ASYNC_TTL_CACHE.get(key)
            if hit is not None and hit[0] > now:
                return hit[1]
            value = await fn(*args, **kwargs)
            _ASYNC_TTL_CACHE[key] = (now + seconds, value)
            return value
        return wrapper
    return deco
