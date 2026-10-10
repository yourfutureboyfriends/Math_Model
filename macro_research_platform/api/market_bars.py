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


_WARM_DAYS = {"1d": 1.5, "1wk": 7.3, "1mo": 30.6}     # calendar days per bar, for the moving-average warm-up


def bars(symbol: str, interval: str = "1d", period: str = "1y", start: str | None = None, end: str | None = None,
         warmup: int = 0) -> Dict[str, Any]:
    """OHLCV bars for a preset period, or for a custom start/end date range (YYYY-MM-DD).
    `warmup` > 0 also returns about that many bars before the window (daily and longer bars)
    so moving averages are defined from its first bar; `first_visible` marks where it begins."""
    from datetime import date, timedelta
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbol required")
    if start:
        d0 = date.fromisoformat(start)
        d1 = date.fromisoformat(end) if end else date.today()
        if d1 < d0:
            raise ValueError("the end date is before the start date")
        if interval in _MAX_DAYS and (date.today() - d0).days > _MAX_DAYS[interval]:
            raise ValueError(f"{interval} bars only go back {_MAX_DAYS[interval]} days on the free feed — pick a later start or a daily interval")
        period = f"{start}..{d1}"
    elif not allowed(interval, period):
        raise ValueError(f"{interval} bars are available for: {', '.join(allowed_periods(interval)) or 'none'}")
    warmup = max(0, min(int(warmup or 0), 400)) if interval in _WARM_DAYS and period != "max" else 0
    vis_start = None
    if warmup:
        today = date.today()
        vis_start = (date.fromisoformat(start) if start else date(today.year, 1, 1) if period == "ytd"
                     else today - timedelta(days=_PERIOD_DAYS[period]))
    key = (sym, interval, period, warmup)
    ttl = 60 if interval in _MAX_DAYS else 600
    with _lock:
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
    import yfinance as yf
    t = yf.Ticker(sym)
    if vis_start is not None:
        d_end = date.fromisoformat(period.split("..")[1]) if start else date.today()
        df = t.history(start=str(vis_start - timedelta(days=int(warmup * _WARM_DAYS[interval]) + 5)),
                       end=str(d_end + timedelta(days=1)), interval=interval, auto_adjust=True, prepost=False)
    elif start:   # yfinance's end is exclusive: add a day so the chosen end date is included
        df = t.history(start=start, end=str(date.fromisoformat(period.split("..")[1]) + timedelta(days=1)), interval=interval,
                       auto_adjust=interval not in _MAX_DAYS, prepost=False)
    else:
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
    first_visible = 0
    if vis_start is not None:
        vs = vis_start.isoformat()
        first_visible = next((i for i, b in enumerate(out_bars) if b["t"] >= vs), len(out_bars))
        if first_visible >= len(out_bars):
            raise LookupError(f"no {interval} data for {sym} in the chosen window")
    out = {"symbol": sym, "interval": interval, "period": period, "intraday": intraday, "currency": ccy, "first_visible": first_visible,
           "timezone": tz, "bars": out_bars, "allowed_periods": allowed_periods(interval)}
    with _lock:
        _CACHE[key] = (time.time(), out)
        if len(_CACHE) > 300:
            _CACHE.pop(next(iter(_CACHE)))
    return out
