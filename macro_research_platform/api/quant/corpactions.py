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
        if len(symbols) > 50:                                   # Parquet reads release the GIL: read in parallel
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(8) as ex:
                frames_ = list(ex.map(lambda x: _read(x, fresh_only=True), symbols))
        else:
            frames_ = [_read(x, fresh_only=True) for x in symbols]
        for s, f in zip(symbols, frames_):
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
    import numpy as np
    got, missing = load(list(symbols))
    cols = list(symbols)
    px = np.full((len(index), len(cols)), np.nan)
    dy = np.zeros((len(index), len(cols)))
    ix = index.values
    for j, s in enumerate(cols):
        df = got.get(s)
        if df is None:
            continue
        if not df.index.is_unique:
            df = df[~df.index.duplicated(keep="last")]
        c = df["Close"].where(df["Close"] > 0)
        cv = c.to_numpy(float)
        # the last close on or before each session (as-of), carried forward — positional, no per-column reindexing
        k = np.searchsorted(df.index.values, ix, side="right") - 1
        valid = np.isfinite(cv)
        lastv = pd.Series(np.where(valid, cv, np.nan)).ffill().to_numpy()
        px[:, j] = np.where(k >= 0, lastv[np.maximum(k, 0)], np.nan)
        d = df["Dividends"].fillna(0.0).to_numpy(float)
        prev = np.r_[np.nan, cv[:-1]]
        y = np.where(d > 0, d / prev, 0.0)
        y = np.clip(np.nan_to_num(y), None, 0.5)                             # a >50% "dividend" is a data error
        hit = y > 0
        if hit.any():
            pos = index.searchsorted(df.index[hit])                           # an ex-date off the index: next session
            keep = (pos < len(index)) & (df.index[hit] >= index[0])          # nothing before the window
            np.add.at(dy[:, j], pos[keep], y[hit][keep])
    return (pd.DataFrame(px, index=index, columns=cols), pd.DataFrame(dy, index=index, columns=cols), missing)
