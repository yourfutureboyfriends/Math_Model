"""
OHLCV bars at a chosen interval and period (Yahoo Finance), for the interactive charts.

Intervals: 5m, 15m, 1h, 1d, 1wk, 1mo. Yahoo serves 5m/15m for the last 60 days and 1h for
the last 730 days; a request outside those limits is refused with the allowed periods
rather than silently returning something else. Daily and longer bars are split- and
dividend-adjusted; intraday bars are as traded. Cached ~1 min intraday, 10 min otherwise.
"""
from __future__ import annotations

import math
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

INTERVALS = ("5m", "15m", "1h", "1d", "1wk", "1mo")
PERIODS = ("1d", "5d", "1mo", "3mo", "6mo", "ytd", "1y", "2y", "5y", "10y", "max")
_PERIOD_DAYS = {"1d": 1, "5d": 5, "1mo": 31, "3mo": 92, "6mo": 183, "ytd": 366, "1y": 366, "2y": 731,
                "5y": 1827, "10y": 3653, "max": 100000}
_MAX_DAYS = {"5m": 60, "15m": 60, "1h": 730}
_CACHE: Dict[Tuple[str, str, str], Tuple[float, Dict[str, Any]]] = {}
_lock = threading.Lock()


def allowed(interval: str, period: str) -> bool:
    return interval in INTERVALS and period in PERIODS and _PERIOD_DAYS[period] <= _MAX_DAYS.get(interval, 10 ** 9)


def allowed_periods(interval: str) -> List[str]:
    return [p for p in PERIODS if allowed(interval, p)]


def _num(x) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def bars(symbol: str, interval: str = "1d", period: str = "1y") -> Dict[str, Any]:
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbol required")
    if not allowed(interval, period):
        raise ValueError(f"{interval} bars are available for: {', '.join(allowed_periods(interval)) or 'none'}")
    key = (sym, interval, period)
    ttl = 60 if interval in _MAX_DAYS else 600
    with _lock:
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
    import yfinance as yf
    t = yf.Ticker(sym)
    df = t.history(period=period, interval=interval, auto_adjust=interval not in _MAX_DAYS, prepost=False)
    if df is None or df.empty:
        raise LookupError(f"no {interval} data for {sym}")
    intraday = interval in _MAX_DAYS
    out_bars = []
    for ts, row in df.iterrows():
        c = _num(row.get("Close"))
        if c is None:
            continue
        o, h, l = (_num(row.get(k)) for k in ("Open", "High", "Low"))
        out_bars.append({"t": ts.isoformat() if intraday else ts.strftime("%Y-%m-%d"),
                         "o": o if o is not None else c, "h": h if h is not None else c,
                         "l": l if l is not None else c, "c": c, "v": _num(row.get("Volume")) or 0})
    try:
        fi = t.fast_info
        ccy, tz = fi.get("currency"), fi.get("timezone")
    except Exception:
        ccy, tz = None, None
    out = {"symbol": sym, "interval": interval, "period": period, "intraday": intraday, "currency": ccy,
           "timezone": tz, "bars": out_bars, "allowed_periods": allowed_periods(interval)}
    with _lock:
        _CACHE[key] = (time.time(), out)
        if len(_CACHE) > 300:
            _CACHE.pop(next(iter(_CACHE)))
    return out
