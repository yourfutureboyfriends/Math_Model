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
        for attempt in range(2):
            try:
                r = requests.get(
                    "https://api.stlouisfed.org/fred/series/observations",
                    params={"series_id": "DGS10", "api_key": FRED_API_KEY,
                            "file_type": "json", "sort_order": "desc", "limit": 1},
                    timeout=(3, 8),
                )
                break
            except requests.exceptions.ReadTimeout:
                # Connected but no answer in time: slow (e.g. while the app's own startup
                # burst is in flight), not down. Retry once before reporting.
                if attempt == 1:
                    return {"status": "degraded", "latency_ms": round((time.perf_counter() - t0) * 1000),
                            "detail": "connected, but no response within 8s (twice)"}
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


# ── Market-quote freshness ──────────────────────────────────────────────────
# A reachable feed can still serve an old quote (Yahoo FX bars land a day late; a frozen quote
# looks "live"). Each instrument's latest 5-minute bar is compared with what its market's hours
# say it should be.
_FRESH_BASKET = [("SPY", "nyse"), ("^VIX", "nyse"), ("EURUSD=X", "fx"), ("CL=F", "cme")]
_FRESH_TTL = 300
_FRESH_CACHE: Dict[str, Any] = {"data": None, "ts": 0.0}


def _nyse_open(t_ny) -> bool:
    import holidays as _hol
    if t_ny.weekday() >= 5 or t_ny.date() in _hol.financial_holidays("NYSE", years=t_ny.year):
        return False
    m = t_ny.hour * 60 + t_ny.minute
    return 9 * 60 + 30 <= m < 16 * 60


def _round_the_clock_open(t_ny, daily_break: bool) -> bool:
    """FX (Sun 17:00 – Fri 17:00 New York) and CME Globex (same week, with a 17:00–18:00 break)."""
    wd, m = t_ny.weekday(), t_ny.hour * 60 + t_ny.minute
    if wd == 5 or (wd == 4 and m >= 17 * 60) or (wd == 6 and m < (18 if daily_break else 17) * 60):
        return False
    return not (daily_break and 17 * 60 <= m < 18 * 60)


def market_open(kind: str, now_utc) -> bool:
    """Whether a market is open at `now_utc`: "nyse" regular hours, "cme" near-24h futures, otherwise round-the-clock
    FX.
    """
    from zoneinfo import ZoneInfo
    t = now_utc.astimezone(ZoneInfo("America/New_York"))
    return _nyse_open(t) if kind == "nyse" else _round_the_clock_open(t, kind == "cme")


def last_open_minute(kind: str, now_utc, step_min: int = 5, max_days: int = 6):
    """The most recent time (stepping back) its market was open — what the latest bar should be near."""
    from datetime import timedelta
    t = now_utc
    for _ in range(max_days * 24 * 60 // step_min):
        if market_open(kind, t):
            return t
        t -= timedelta(minutes=step_min)
    return None


def quote_staleness(kind: str, last_bar_utc, now_utc, tolerance_min: int = 30) -> Dict[str, Any]:
    """{status, age_min, expected_since}: stale when the last bar is more than `tolerance_min`
    older than the last moment the market was open (5-minute bars are stamped at their start)."""
    age = (now_utc - last_bar_utc).total_seconds() / 60
    ref = last_open_minute(kind, now_utc)
    lag = (ref - last_bar_utc).total_seconds() / 60 if ref else 0
    return {"status": "stale" if lag > tolerance_min else "fresh", "age_min": round(age),
            "open_now": market_open(kind, now_utc),
            "behind_market_min": round(max(lag, 0))}


def _probe_quote_freshness() -> Dict[str, Any]:
    now = time.time()
    if _FRESH_CACHE["data"] and now - _FRESH_CACHE["ts"] < _FRESH_TTL:
        return _FRESH_CACHE["data"]
    t0 = time.perf_counter()
    rows, n_stale, n_missing = {}, 0, 0
    try:
        import yfinance as yf
        now_utc = datetime.now(timezone.utc)
        for sym, kind in _FRESH_BASKET:
            try:
                h = yf.Ticker(sym).history(period="5d", interval="5m")
                if h is None or h.empty:
                    raise ValueError("no bars")
                ts = h.index[-1]
                ts = ts.tz_convert("UTC") if ts.tzinfo else ts.tz_localize("UTC")
                r = quote_staleness(kind, ts.to_pydatetime(), now_utc)
                r["last_bar"] = ts.strftime("%Y-%m-%d %H:%M UTC")
                n_stale += r["status"] == "stale"
            except Exception as e:
                r = {"status": "missing", "detail": str(e)[:80]}
                n_missing += 1
            rows[sym] = r
        ms = round((time.perf_counter() - t0) * 1000)
        status = "live" if not (n_stale or n_missing) else ("down" if n_missing == len(rows) else "degraded")
        bad = [f"{k} {v.get('behind_market_min', '?')}m behind" if v["status"] == "stale" else f"{k} missing"
               for k, v in rows.items() if v["status"] != "fresh"]
        out = {"status": status, "latency_ms": ms, "instruments": rows,
               "detail": ("all quotes current for their market hours" if not bad else "; ".join(bad))}
    except Exception as e:
        out = {"status": "down", "latency_ms": round((time.perf_counter() - t0) * 1000), "detail": str(e)[:120]}
    _FRESH_CACHE.update(data=out, ts=now)
    return out


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
        "quote_freshness": _probe_quote_freshness(),
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
