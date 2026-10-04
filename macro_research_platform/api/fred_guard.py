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
        resp = original(self, method, url, *args, **kwargs)
        record(resp.status_code)
        return resp

    requests.sessions.Session.request = guarded
    _installed = True
