"""
Trading-date alignment for Yahoo daily bars.

Yahoo dates spot-FX daily bars (tickers ending "=X") one day AFTER the New-York session
they belong to: the bar labelled D+1 tracks the FRED noon rate of day D (daily-change
correlation 0.69-0.77 vs 0.2-0.3 same-day) and moves against DXY on day D (corr -0.79 vs
-0.16 same-day). Aligned naively by date, FX was a day out of step with equities, rates
and DXY — wrong daily changes (DXY -0.17% next to EUR/USD -0.62%) and biased correlations.

`align_daily(ticker, dates)` returns, per bar, the NY trading date it belongs to, or None
to drop it: FX bars are moved to the previous business day, and the bar dated today (still
forming) and weekend-dated bars (partial Sunday-evening sessions) are dropped. Every other
asset class keeps its dates. Crypto ("-USD") trades weekends and is left alone.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, List, Optional, Sequence, Tuple, TypeVar

T = TypeVar("T")


def is_spot_fx(ticker: str) -> bool:
    return str(ticker).upper().endswith("=X")


def previous_business_day(d: date) -> date:
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _as_date(x) -> date:
    if isinstance(x, date):
        return x if type(x) is date else date(x.year, x.month, x.day)
    return date.fromisoformat(str(x)[:10])


def align_daily(ticker: str, dates: Iterable, today: Optional[date] = None) -> List[Optional[date]]:
    """The NY session date each daily bar belongs to (None = drop the bar)."""
    ds = [_as_date(d) for d in dates]
    if not is_spot_fx(ticker):
        return ds
    today = today or date.today()
    out: List[Optional[date]] = []
    for d in ds:
        out.append(None if d >= today or d.weekday() >= 5 else previous_business_day(d))
    return out


def align_pairs(ticker: str, dates: Sequence, values: Sequence[T],
                today: Optional[date] = None) -> List[Tuple[str, T]]:
    """[(iso_date, value)] after alignment, dropped bars removed, later duplicates win."""
    merged = {}
    for d, v in zip(align_daily(ticker, dates, today), values):
        if d is not None:
            merged[d.isoformat()] = v
    return sorted(merged.items())


def align_frame(ticker: str, hist, today: Optional[date] = None):
    """Same alignment for a yfinance history DataFrame (returns a new frame)."""
    if hist is None or getattr(hist, "empty", True) or not is_spot_fx(ticker):
        return hist
    import pandas as pd
    new = align_daily(ticker, hist.index, today)
    keep = [d is not None for d in new]
    out = hist.loc[keep].copy()
    out.index = pd.DatetimeIndex([pd.Timestamp(d) for d in new if d is not None])
    return out[~out.index.duplicated(keep="last")]
