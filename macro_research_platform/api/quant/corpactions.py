"""
Unadjusted-for-dividends prices and cash dividends (Yahoo Finance, auto_adjust=False, actions=True), cached
per symbol as Parquet for a week. The Code Lab uses them for what total-return prices hide:

  * the traded share price (split-adjusted, not dividend-adjusted) — for board lots and tick sizes;
  * dividend yields on each ex-date (cash dividend ÷ previous close, both split-adjusted) — for the tax
    withheld at source on foreign dividends.

A symbol with no data here simply gets no lot / tick / withholding refinements (reported, never fatal).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import pandas as pd

logger = logging.getLogger(__name__)
CACHE = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "quant" / "corpactions"
TTL = 7 * 86400
BATCH = 150
_lock = threading.Lock()


def _file(sym: str) -> Path:
    return CACHE / f"{sym.replace('^', '_I_').replace('=', '_E_')}.parquet"


def _read(sym: str, fresh_only: bool) -> pd.DataFrame | None:
    p = _file(sym)
    try:
        if fresh_only and time.time() - p.stat().st_mtime >= TTL:
            return None
        return pd.read_parquet(p)
    except Exception:                                          # noqa: BLE001 — missing or unreadable: re-fetch
        return None


def _download(symbols: List[str]) -> Dict[str, pd.DataFrame]:
    import yfinance as yf
    out: Dict[str, pd.DataFrame] = {}
    for i in range(0, len(symbols), BATCH):
        part = symbols[i:i + BATCH]
        try:
            df = yf.download(part, period="max", interval="1d", auto_adjust=False, actions=True, group_by="ticker",
                             threads=True, progress=False)
        except Exception as e:                                 # noqa: BLE001 — one failed batch must not lose the rest
            logger.warning("[corpactions] batch %s failed: %s", i, e)
            continue
        for s in part:
            try:
                sub = df[s] if isinstance(df.columns, pd.MultiIndex) else df
                sub = sub[["Close", "Dividends"]].dropna(subset=["Close"])
                if len(sub) > 20:
                    sub.index = pd.DatetimeIndex(sub.index).tz_localize(None).normalize()
                    out[s] = sub.astype(float)
            except Exception:                                  # noqa: BLE001
                continue
        if len(symbols) > BATCH:
            time.sleep(1.0)
    return out


def load(symbols: Sequence[str]) -> Tuple[Dict[str, pd.DataFrame], List[str]]:
    """{symbol: DataFrame[Close (split-adjusted), Dividends (cash, split-adjusted)]} and the symbols without data."""
    have: Dict[str, pd.DataFrame] = {}
    with _lock:
        need = []
        for s in symbols:
            f = _read(s, fresh_only=True)
            if f is not None:
                have[s] = f
            else:
                need.append(s)
        if need:
            got = _download(need)
            CACHE.mkdir(parents=True, exist_ok=True)
            for s in need:
                if s in got:
                    tmp = _file(s).with_suffix(".parquet.tmp")
                    got[s].to_parquet(tmp)
                    os.replace(tmp, _file(s))
                    have[s] = got[s]
                else:
                    old = _read(s, fresh_only=False)
                    if old is not None:
                        have[s] = old
    return have, [s for s in symbols if s not in have]


def frames(symbols: Sequence[str], index: pd.DatetimeIndex) -> Tuple[pd.DataFrame, pd.DataFrame, List[str]]:
    """(share price in the quote unit, dividend yield on ex-dates) on `index` × symbols, plus symbols without data.
    The share price is the last observed close carried forward; the yield is 0 except on ex-dates (an ex-date
    that is not a session of the index counts on the next one)."""
    got, missing = load(list(symbols))
    px, dy = {}, {}
    for s, df in got.items():
        c = df["Close"].where(df["Close"] > 0)
        d = df["Dividends"].fillna(0.0)
        y = (d / c.shift(1)).where(d > 0, 0.0).fillna(0.0).clip(upper=0.5)   # a >50% "dividend" is a data error
        px[s] = c.reindex(c.index.union(index)).ffill().reindex(index)
        y = y[y > 0]
        pos = index.searchsorted(y.index)                                    # an ex-date off the index: next session
        keep = (pos < len(index)) & (y.index >= index[0])                  # nothing before the window
        dy[s] = pd.Series(y.to_numpy()[keep], index=index[pos[keep]]).groupby(level=0).sum().reindex(index, fill_value=0.0)
    cols = list(symbols)
    return (pd.DataFrame(px, index=index).reindex(columns=cols),
            pd.DataFrame(dy, index=index).reindex(columns=cols).fillna(0.0), missing)
