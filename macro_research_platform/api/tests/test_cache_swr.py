"""Stale-while-revalidate in the market-data cache: a lapsed entry is served at once and refreshed behind; live
quotes (short TTLs) and very old entries still wait for a fresh fetch."""
import time

from api.marketdata import core


def _counter():
    n = {"c": 0}

    def fetch():
        n["c"] += 1
        time.sleep(0.3)
        return {"v": n["c"]}
    return n, fetch


def test_lapsed_entry_served_at_once_and_refreshed_behind():
    n, fetch = _counter()
    k = "test:swr:a"
    assert core._cached(k, 600, fetch) == {"v": 1}
    core._cache[k] = (time.time() - 700, core._cache[k][1])            # past its TTL, within SWR_FACTOR × TTL
    t = time.time()
    assert core._cached(k, 600, fetch) == {"v": 1} and time.time() - t < 0.1
    deadline = time.time() + 3
    while core._cache[k][1] == {"v": 1} and time.time() < deadline:
        time.sleep(0.05)
    assert core._cached(k, 600, fetch) == {"v": 2} and n["c"] == 2        # refreshed once, behind


def test_short_ttls_and_very_old_entries_wait():
    n, fetch = _counter()
    core._cache["test:swr:q"] = (time.time() - 70, {"v": 0})
    t = time.time()
    assert core._cached("test:swr:q", 60, fetch) == {"v": 1} and time.time() - t >= 0.3      # a quote: never stale
    core._cache["test:swr:o"] = (time.time() - 10_000, {"v": 0})
    assert core._cached("test:swr:o", 600, fetch) == {"v": 2}                                 # beyond 4 × TTL
