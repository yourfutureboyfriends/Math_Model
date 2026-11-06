"""Explicit return calendars without invented prices across missing observations."""
import numpy as np
import pandas as pd


def analysis_calendar(prices):
    prices = prices.where(np.isfinite(prices) & (prices > 0)).dropna(axis=1, how='all')
    weekends = prices.index.dayofweek >= 5
    calendar_days = bool(weekends.any() and prices.loc[weekends].notna().any().all())
    return (prices if calendar_days else prices.loc[~weekends]), 365 if calendar_days else 252


def observed_returns(series):
    """Native observed daily returns; reject gaps beyond a calendar/business day.

    Friday-to-Monday is valid for weekday instruments. Unknown holidays/missing business
    days are conservatively omitted rather than filled or annualized as one-day returns.
    """
    s = series.where(np.isfinite(series) & (series > 0)).dropna().sort_index()
    annual = 365 if (s.index.dayofweek >= 5).any() else 252
    r = s.pct_change(fill_method=None)
    if len(s) > 1:
        dates = s.index.values.astype('datetime64[D]')
        gaps = (dates[1:] - dates[:-1]).astype(int) if annual == 365 else np.busday_count(dates[:-1], dates[1:])
        r.iloc[1:] = r.iloc[1:].where((gaps >= 0) & (gaps <= 1))
    return r, annual
