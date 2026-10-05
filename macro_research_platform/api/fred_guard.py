"""
FRED circuit breaker.

FRED protects itself from high request volume by refusing a client (HTTP 429, or an Akamai
403 "Access Denied" page). The app has ~15 independent FRED call sites (warm loops, release
calendars, model fits, per-panel fetches); none backed off, so every refusal was retried —
prolonging the block — while panels quietly fell back (e.g. the recession headline switched
models).

`install()` wraps requests' Session.request once, for URLs on api.stlouisfed.org only:
  * a 403/429 opens the breaker: FRED calls fail fast (ConnectionError, which every caller
    already handles by serving cached data) for a cooling-off period;
  * each further refusal while probing doubles the period (5 min → 10 → 20 … capped at 2 h);
  * the first successful response closes it.

It also THROTTLES FRED traffic so the breaker rarely has to open: FRED allows ~120 requests
per minute per key, and a cold start (warm loops, calendars, model fits in parallel) used to
fire far more than that within seconds, get 429'd, and lose FRED for five minutes. Requests
now wait for a slot: at most MAX_CONCURRENT in flight, MIN_INTERVAL apart, and at most
MAX_PER_MINUTE in any rolling 60s.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Dict

logger = logging.getLogger(__name__)

HOST = "api.stlouisfed.org"
BASE_COOLDOWN = 300.0
MAX_COOLDOWN = 7200.0

_lock = threading.Lock()
_state: Dict[str, float] = {"open_until": 0.0, "cooldown": BASE_COOLDOWN, "trips": 0}
_installed = False

MAX_CONCURRENT = 4
MIN_INTERVAL = 0.3          # seconds between request starts
MAX_PER_MINUTE = 100        # below FRED's ~120/min per key
_slots = threading.BoundedSemaphore(MAX_CONCURRENT)
_starts: list = []          # start times within the last 60s
_pace_lock = threading.Lock()


def _wait_for_slot(now=time.time, sleep=time.sleep) -> float:
    """Block until a request may start under the pacing rules; returns seconds waited."""
    waited = 0.0
    while True:
        with _pace_lock:
            t = now()
            while _starts and t - _starts[0] >= 60:
                _starts.pop(0)
            gap = (_starts[-1] + MIN_INTERVAL - t) if _starts else 0.0
            window = (_starts[0] + 60 - t) if len(_starts) >= MAX_PER_MINUTE else 0.0
            delay = max(gap, window, 0.0)
            if delay == 0.0:
                _starts.append(t)
                return waited
        sleep(delay)
        waited += delay


def is_open(now: float | None = None) -> bool:
    return (time.time() if now is None else now) < _state["open_until"]


def status() -> Dict:
    now = time.time()
    return {"open": is_open(now), "retry_in_s": max(0, round(_state["open_until"] - now)),
            "cooldown_s": _state["cooldown"], "trips": int(_state["trips"])}


def record(status_code: int, now: float | None = None) -> None:
    now = time.time() if now is None else now
    with _lock:
        if status_code in (403, 429):
            if now < _state["open_until"]:
                return      # a request already in flight when the breaker opened: no escalation
            _state["open_until"] = now + _state["cooldown"]
            _state["trips"] += 1
            logger.warning("[FRED] refused (HTTP %s) — pausing FRED requests for %.0f min",
                           status_code, _state["cooldown"] / 60)
            _state["cooldown"] = min(MAX_COOLDOWN, _state["cooldown"] * 2)
        elif status_code < 400:
            if _state["trips"]:
                logger.info("[FRED] requests accepted again — breaker closed")
            _state.update(open_until=0.0, cooldown=BASE_COOLDOWN, trips=0)


def reset() -> None:
    with _lock:
        _state.update(open_until=0.0, cooldown=BASE_COOLDOWN, trips=0)
    with _pace_lock:
        _starts.clear()


def install() -> None:
    """Idempotently wrap requests.Session.request for FRED URLs."""
    global _installed
    if _installed:
        return
    import requests
    original = requests.sessions.Session.request

    def guarded(self, method, url, *args, **kwargs):
        if HOST not in str(url):
            return original(self, method, url, *args, **kwargs)
        if is_open():
            raise requests.exceptions.ConnectionError(
                f"FRED circuit breaker open (retry in {status()['retry_in_s']}s)")
        with _slots:
            _wait_for_slot()
            if is_open():       # opened while this request was queued
                raise requests.exceptions.ConnectionError(
                    f"FRED circuit breaker open (retry in {status()['retry_in_s']}s)")
            resp = original(self, method, url, *args, **kwargs)
        record(resp.status_code)
        return resp

    requests.sessions.Session.request = guarded
    _installed = True
