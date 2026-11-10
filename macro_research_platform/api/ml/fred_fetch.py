"""Resilient FRED reads for the ML input builders (the panel and the extended series).

A daily rebuild fetches 70–100 series in a row. FRED rate-limits bursts (about 120 requests a minute), so a single
pass can fail partway and — before this — cached a panel with whole groups missing (every price series one day) for a
full day, silently removing inflation from every model. Each series is now retried, and one that still fails keeps
its last good copy from the previous build: its last value is still the latest known value, so this adds no
look-ahead, and the series is named in the log as carried."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Iterable

logger = logging.getLogger(__name__)
RETRIES = 3
MIN_SHARE = 0.5          # a build with fewer of its series than this is refused, not cached


def get_series(f: Any, sid: str, **kwargs):
    """FRED series with retries and a short back-off; raises the last error when every attempt fails."""
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            return f.get_series(sid, **kwargs)
        except Exception as e:                                          # noqa: BLE001 — retried, then re-raised
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last if last else RuntimeError(sid)


def keep_last_good(cache_name: str, out: Dict[str, Dict[str, float]], expected: Iterable[str]) -> Dict[str, Dict[str, float]]:
    """Fill keys that failed this build from the previous build's cached copy."""
    from api.handlers.macro_inputs import _disk_load
    prev = ((_disk_load(f"ri_{cache_name}") or {}).get("data")) or {}
    carried = [k for k in expected if k not in out and prev.get(k)]
    for k in carried:
        out[k] = prev[k]
    if carried:
        logger.warning("[ml.inputs] %s: %d series failed to refresh and keep their last good copy: %s",
                       cache_name, len(carried), ", ".join(carried))
    expected = list(expected)
    if expected and len([k for k in expected if out.get(k)]) < MIN_SHARE * len(expected):
        # a mostly failed build (rate limit, outage) must not replace a good cache: raising makes the cache layer
        # keep serving the previous copy instead of saving this one for a day
        raise RuntimeError(f"{cache_name}: only {len(out)} of {len(expected)} series available; previous copy kept")
    return out
