"""
Data for the systematic macro model: a monthly macro panel and monthly asset excess returns.

Macro (FRED, monthly). Each series is transformed to be stationary and shifted by its
publication lag, so the panel at month t holds only what had been published by the end of
month t. (FRED serves revised data, not first-release vintages — a known limitation noted in
the model documentation; ALFRED vintages would remove it.)

Assets. Estimation uses long-history total-return mutual funds (adjusted closes, dividends
reinvested) so regime-conditional returns are estimated over ~40 years; trading maps each
asset class to a liquid ETF.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# series id -> (block, transform, publication lag in months)
MACRO_SERIES: Dict[str, Tuple[str, str, int]] = {
    # Growth block
    "INDPRO": ("growth", "yoy", 1),        # industrial production
    "PAYEMS": ("growth", "yoy", 1),        # nonfarm payrolls
    "UNRATE": ("growth", "neg_diff12", 1),  # unemployment rate (rise = weaker growth)
    "ICSA": ("growth", "neg_yoy", 0),      # initial claims (monthly mean of weekly)
    "HOUST": ("growth", "yoy", 1),         # housing starts
    "RRSFS": ("growth", "yoy", 1),         # real retail sales
    "TCU": ("growth", "diff12", 1),        # capacity utilisation
    "W875RX1": ("growth", "yoy", 1),       # real personal income ex transfers
    "AWHMAN": ("growth", "diff12", 1),     # average weekly hours, manufacturing
    # Inflation block
    "CPIAUCSL": ("inflation", "yoy", 1),
    "CPILFESL": ("inflation", "yoy", 1),
    "PCEPI": ("inflation", "yoy", 1),
    "PCEPILFE": ("inflation", "yoy", 1),
    "PPIACO": ("inflation", "yoy", 1),
    "AHETPI": ("inflation", "yoy", 1),     # average hourly earnings, production workers
    "WTISPLC": ("inflation", "yoy", 1),    # WTI spot
    "MICH": ("inflation", "level", 1),     # UMich 1-year inflation expectations
}
CASH_SERIES = "TB3MS"

# model asset -> (estimation proxy, tradeable ETF, environment class)
ASSETS: Dict[str, Tuple[str, str, str]] = {
    "US equity": ("VFINX", "SPY", "Equity"),
    "Developed ex-US equity": ("VGTSX", "EFA", "Equity"),
    "EM equity": ("VEIEX", "EEM", "Equity"),
    "Long Treasuries": ("VUSTX", "TLT", "Nominal bonds"),
    "Intermediate Treasuries": ("VFITX", "IEF", "Nominal bonds"),
    "TIPS": ("VIPSX", "TIP", "Inflation-linked bonds"),
    "IG credit": ("VWESX", "LQD", "Corporate credit"),
    "HY credit": ("VWEHX", "HYG", "Corporate credit"),
    "Gold": ("GC=F", "GLD", "Gold"),
    "Commodities": ("PCRIX", "DBC", "Commodities"),
}

_TTL = 24 * 3600


def transform(s: pd.Series, how: str) -> pd.Series:
    s = s.astype(float)
    if how == "yoy":
        return 100 * np.log(s).diff(12)
    if how == "neg_yoy":
        return -100 * np.log(s).diff(12)
    if how == "diff12":
        return s.diff(12)
    if how == "neg_diff12":
        return -s.diff(12)
    return s


def build_macro_panel(raw: Dict[str, pd.Series]) -> pd.DataFrame:
    """Transformed, publication-lag-shifted monthly panel (index = month the value is known)."""
    cols = {}
    for sid, (_, how, lag) in MACRO_SERIES.items():
        s = raw.get(sid)
        if s is None or s.empty:
            continue
        m = s.resample("MS").mean()
        t = transform(m, how)
        # Extend the index before shifting, so the newest release lands on the month it was
        # published in instead of falling off the end (the panel was a month stale).
        if lag:
            ext = pd.date_range(t.index[-1], periods=lag + 1, freq="MS")[1:]
            t = pd.concat([t, pd.Series(np.nan, index=ext)])
        cols[sid] = t.shift(lag)
    return pd.DataFrame(cols).sort_index()


async def load_macro_raw(years: int = 60) -> Dict[str, pd.Series]:
    from api.handlers.macro_inputs import load_fred_series
    ids = list(MACRO_SERIES) + [CASH_SERIES]
    fred = await load_fred_series(ids, days=int(years * 365.25))
    out = {}
    for sid, ds in fred.items():
        if ds and ds.values:
            out[sid] = pd.Series(ds.values, index=pd.to_datetime(ds.dates))
    return out


def _fetch_asset_prices() -> Dict[str, Dict[str, float]]:
    import yfinance as yf
    out = {}
    for name, (proxy, _, _) in ASSETS.items():
        try:
            h = yf.Ticker(proxy).history(period="max", interval="1mo", auto_adjust=True)
            if h is not None and not h.empty:
                out[name] = {str(i)[:7]: float(c) for i, c in zip(h.index, h["Close"]) if c == c}
        except Exception as e:
            logger.warning("[model] price history failed for %s (%s): %s", name, proxy, e)
    return out


def load_asset_prices() -> Dict[str, Dict[str, float]]:
    from api.handlers.macro_inputs import _disk_load, _disk_save
    hit = _disk_load("model_asset_prices", max_age=_TTL)
    if hit:
        return hit["data"]
    data = _fetch_asset_prices()
    if len(data) >= 5:
        _disk_save("model_asset_prices", {"data": data, "fetched_at": time.time()})
        return data
    stale = _disk_load("model_asset_prices")
    return stale["data"] if stale else data


def excess_returns(prices: Dict[str, Dict[str, float]], cash: pd.Series) -> pd.DataFrame:
    """Monthly simple returns minus the T-bill (annual % / 12), index = month start.
    The current, incomplete month is dropped."""
    frames = {}
    for name, px in prices.items():
        s = pd.Series(px)
        s.index = pd.to_datetime([k + "-01" for k in s.index])
        s = s.sort_index()
        s = s[~s.index.duplicated(keep="last")]
        frames[name] = s.pct_change()
    r = pd.DataFrame(frames).sort_index()
    this_month = pd.Timestamp.today().to_period("M").to_timestamp()
    r = r[r.index < this_month]
    c = (cash.resample("MS").mean() / 1200).reindex(r.index).ffill()
    return r.sub(c, axis=0)


async def load_model_data() -> Tuple[pd.DataFrame, pd.DataFrame]:
    raw = await load_macro_raw()
    panel = build_macro_panel(raw)
    prices = await asyncio.to_thread(load_asset_prices)
    cash = raw.get(CASH_SERIES, pd.Series(dtype=float))
    return panel, excess_returns(prices, cash)
