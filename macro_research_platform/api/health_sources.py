"""
Per-source data-feed health probing (data-trust layer).

Actively probes each upstream dependency (FRED, market data, database) with a
real request and measures response time, so the UI can show a PM exactly which
feed is live, degraded, or down. Results are cached briefly so a burst of health
polls does not hammer the upstreams.

Each source reports:
  status        : "live" | "degraded" | "down"
  latency_ms    : measured round-trip in milliseconds (None if not reached)
  detail        : short human-readable note (value seen, HTTP code, or error)
  last_checked  : ISO-8601 UTC timestamp of the probe
"""
from __future__ import annotations

import time
import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Latency thresholds (ms) above which a reachable source is flagged "degraded".
_FRED_DEGRADED_MS = 2500
_MARKET_DEGRADED_MS = 4000  # yfinance baseline is ~1-3s; flag only genuinely slow responses
_DB_DEGRADED_MS = 250

_CACHE: Dict[str, Any] = {"data": None, "ts": 0.0}
_CACHE_TTL = 30  # seconds


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _classify(latency_ms: float, degraded_above: float) -> str:
    return "live" if latency_ms <= degraded_above else "degraded"


def _probe_fred() -> Dict[str, Any]:
    from api.config import FRED_API_KEY
    if not FRED_API_KEY or FRED_API_KEY == "your_fred_api_key_here":
        return {"status": "down", "latency_ms": None, "detail": "FRED_API_KEY not configured"}
    import requests
    t0 = time.perf_counter()
    try:
        r = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={"series_id": "DGS10", "api_key": FRED_API_KEY,
                    "file_type": "json", "sort_order": "desc", "limit": 1},
            timeout=(3, 8),
        )
        ms = round((time.perf_counter() - t0) * 1000)
        if r.status_code == 200:
            obs = r.json().get("observations") or []
            val = obs[0].get("value") if obs else None
            return {"status": _classify(ms, _FRED_DEGRADED_MS), "latency_ms": ms,
                    "detail": f"DGS10={val}" if val not in (None, ".") else "HTTP 200, no value"}
        return {"status": "degraded", "latency_ms": ms, "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "down", "latency_ms": round((time.perf_counter() - t0) * 1000),
                "detail": str(e)[:120]}


def _probe_market() -> Dict[str, Any]:
    t0 = time.perf_counter()
    try:
        from api.providers.yahoo_provider import YahooFinanceProvider
        rec = YahooFinanceProvider().fetch_single("SPX")
        ms = round((time.perf_counter() - t0) * 1000)
        if rec is not None and getattr(rec, "price", None):
            return {"status": _classify(ms, _MARKET_DEGRADED_MS), "latency_ms": ms,
                    "detail": f"SPX {rec.price:.2f}"}
        return {"status": "degraded", "latency_ms": ms, "detail": "no price returned"}
    except Exception as e:
        return {"status": "down", "latency_ms": round((time.perf_counter() - t0) * 1000),
                "detail": str(e)[:120]}


def _resolve_sqlite_path() -> str | None:
    from api.config import DATABASE_URL
    if not DATABASE_URL or not DATABASE_URL.startswith("sqlite"):
        return None
    # sqlite:///relative.db  or  sqlite:////absolute.db
    path = DATABASE_URL.split("sqlite:///", 1)[-1]
    import os
    if not os.path.isabs(path):
        here = os.path.dirname(os.path.abspath(__file__))  # api/
        for base in (here, os.path.dirname(here)):
            candidate = os.path.join(base, path)
            if os.path.exists(candidate):
                return candidate
        return os.path.join(here, path)
    return path


def _probe_db() -> Dict[str, Any]:
    from api.config import DATABASE_URL
    if not DATABASE_URL:
        return {"status": "down", "latency_ms": None, "detail": "DATABASE_URL not configured"}
    if not DATABASE_URL.startswith("sqlite"):
        # Non-sqlite backend: report configured but unprobed rather than guess.
        return {"status": "degraded", "latency_ms": None,
                "detail": f"unprobed backend: {DATABASE_URL.split('://', 1)[0]}"}
    import sqlite3
    path = _resolve_sqlite_path()
    t0 = time.perf_counter()
    try:
        conn = sqlite3.connect(path, timeout=3)
        conn.execute("SELECT 1")
        conn.close()
        ms = round((time.perf_counter() - t0) * 1000)
        return {"status": _classify(ms, _DB_DEGRADED_MS), "latency_ms": ms, "detail": "sqlite OK"}
    except Exception as e:
        return {"status": "down", "latency_ms": round((time.perf_counter() - t0) * 1000),
                "detail": str(e)[:120]}


def get_sources_health(force: bool = False) -> Dict[str, Any]:
    """Probe every upstream (cached ~30s) and return an aggregate health report."""
    now = time.time()
    cached = _CACHE.get("data")
    if not force and cached and now - _CACHE["ts"] < _CACHE_TTL:
        return cached

    sources = {
        "fred": _probe_fred(),
        "market_data": _probe_market(),
        "database": _probe_db(),
    }
    checked = _now_iso()
    for v in sources.values():
        v["last_checked"] = checked

    live = sum(1 for v in sources.values() if v["status"] == "live")
    degraded = sum(1 for v in sources.values() if v["status"] == "degraded")
    total = len(sources)
    overall = "healthy" if live == total else ("down" if live == 0 and degraded == 0 else "degraded")

    data = {
        "overall": overall,
        "live": live,
        "degraded": degraded,
        "down": total - live - degraded,
        "total": total,
        "sources": sources,
        "checked_at": checked,
        "cache_ttl_seconds": _CACHE_TTL,
    }
    _CACHE["data"] = data
    _CACHE["ts"] = now
    return data
