"""FRED circuit breaker: back off on refusals, fail fast while open, close on success."""
import pytest
import requests

from api import fred_guard


@pytest.fixture(autouse=True)
def _clean():
    fred_guard.reset()
    yield
    fred_guard.reset()


def test_refusal_opens_breaker_and_backoff_doubles():
    fred_guard.record(429, now=1000.0)
    assert fred_guard.is_open(now=1001.0) and not fred_guard.is_open(now=1000.0 + 301)
    fred_guard.record(403, now=2000.0)                      # still refused after cooling off
    assert fred_guard.is_open(now=2000.0 + 599) and not fred_guard.is_open(now=2000.0 + 601)


def test_success_closes_and_resets_cooldown():
    fred_guard.record(403, now=1000.0)
    fred_guard.record(200, now=1400.0)
    assert not fred_guard.is_open(now=1401.0) and fred_guard.status()["cooldown_s"] == fred_guard.BASE_COOLDOWN


def test_cooldown_is_capped():
    for k in range(20):
        fred_guard.record(429, now=k * 10_000.0)
    assert fred_guard.status()["cooldown_s"] == fred_guard.MAX_COOLDOWN


def test_open_breaker_fails_fast_for_fred_only(monkeypatch):
    fred_guard.install()
    fred_guard.record(429)
    with pytest.raises(requests.exceptions.ConnectionError):
        requests.get("https://api.stlouisfed.org/fred/series?series_id=GDP", timeout=1)
    # other hosts are untouched by the guard (no network call made here: the error would differ)
    assert fred_guard.HOST == "api.stlouisfed.org"


def test_in_flight_refusals_do_not_escalate():
    for k in range(8):                        # a burst of concurrent refusals
        fred_guard.record(403, now=1000.0 + k * 0.01)
    st = fred_guard.status()
    assert st["trips"] == 1 and st["cooldown_s"] == fred_guard.BASE_COOLDOWN * 2
