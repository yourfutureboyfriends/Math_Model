"""
One rate service for the platform: the 13-week Treasury bill (^IRX, Yahoo), the reference rate for
excess returns (Sharpe, Sortino) and the default remuneration of idle cash in backtests and paper books.

Conventions (one set, used everywhere):
  quote      ^IRX is a discount yield in percent; it is used directly as an annual simple rate (the
             difference from the bond-equivalent yield is a few bp at these maturities)
  daily      annual / 252 per *trading day* — a return series earns one accrual per observed session
  accrue()   the same convention between two dates: the sum of the daily rates of the sessions after
             `from_date` up to and including `to_date`
  as-of      a date takes the latest observation on or before it — never a later one; dates before the
             series starts have no rate (0, and `known()` is False) rather than a borrowed future value
Remuneration is a choice: positive broker cash need not earn the full bill rate (see cash_spread in the
Code Lab cost schema and the paper traders' settings).
"""
from __future__ import annotations

import time
from typing import Optional, Sequence

import numpy as np
import pandas as pd

_cache: dict = {}
TTL = 6 * 3600


def _irx() -> Optional[pd.Series]:
    hit = _cache.get("irx")
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    s = None
    try:
        from api.quant import data as qdata
        got, _ = qdata.load(["^IRX"])
        df = got.get("^IRX")
        if df is not None and len(df) > 100:
            s = df["Close"].astype(float)
            s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize()
            s = s[(s >= 0) & (s <= 25)]                       # percent; anything else is bad data
    except Exception:                                         # noqa: BLE001 — no network: rate 0
        s = None
    _cache["irx"] = (time.time(), s)
    return s


def known() -> bool:
    """Whether the reference rate is available at all (UI flags results computed without it)."""
    s = _irx()
    return s is not None and not s.empty


def daily(index: Sequence) -> pd.Series:
    """Daily reference rate (decimal per trading day) for each date, as of that date; 0 where unknown."""
    idx = pd.DatetimeIndex(pd.to_datetime(list(index))).normalize()
    s = _irx()
    if s is None or s.empty:
        return pd.Series(0.0, index=idx)
    asof = s.reindex(s.index.union(idx)).ffill().reindex(idx)        # latest observation on or before each date
    return (asof / 100 / 252).fillna(0.0)


def annual(start: str, end: str) -> float:
    """Average annual reference rate (decimal) over [start, end], from observations in that interval; if
    none, the latest observation on or before `start`; never a later one."""
    s = _irx()
    if s is None or s.empty:
        return 0.0
    w = s[(s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))]
    if len(w):
        return float(w.mean() / 100)
    before = s[s.index <= pd.Timestamp(start)]
    return float(before.iloc[-1] / 100) if len(before) else 0.0


def accrue(cash: float, from_date: str, to_date: str, borrow_spread: float = 0.01, cash_spread: float = 0.0) -> float:
    """Interest on a balance held from `from_date` to `to_date`: one daily accrual per trading session after
    from_date up to and including to_date (same convention as `daily`). Positive cash earns the rate less
    `cash_spread`; a negative balance (margin) pays the rate plus `borrow_spread`."""
    if not cash or to_date <= from_date:
        return 0.0
    days = pd.bdate_range(pd.Timestamp(from_date) + pd.Timedelta(days=1), pd.Timestamp(to_date))
    if not len(days):
        return 0.0
    r = daily(days)
    adj = (-cash_spread if cash > 0 else borrow_spread) / 252
    return float(cash * (r + adj).sum())


def excess(r: np.ndarray, dates: Optional[Sequence[str]]) -> np.ndarray:
    """Returns minus the T-bill rate for the same days (unchanged if no dates)."""
    r = np.asarray(r, float)
    if not dates or len(dates) != len(r):
        return r
    return r - daily(dates).to_numpy()
