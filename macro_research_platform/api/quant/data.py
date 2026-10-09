"""
Market data for the Quant Lab: preset universes and a per-symbol daily OHLCV cache.

Prices are Yahoo Finance daily bars, split- and dividend-adjusted (auto_adjust), cached
per symbol under data/processed/quant/ohlcv and refreshed when older than ~18 hours.
Custom universes accept up to MAX_SYMBOLS tickers.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

logger = logging.getLogger(__name__)
CACHE = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "quant" / "ohlcv"
MAX_AGE_S = 18 * 3600
MAX_SYMBOLS = 80
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-^=]{0,14}$")
_lock = threading.Lock()

PRESETS: Dict[str, Dict] = {
    "cross_asset": {
        "label": "Cross-asset ETFs (13)",
        "symbols": ["SPY", "QQQ", "IWM", "EFA", "EEM", "IEF", "TLT", "TIP", "LQD", "GLD", "DBC", "UUP", "VNQ"],
        "note": "US/intl equities, Treasuries, TIPS, credit, gold, commodities, dollar, REITs — the classic trend-following universe.",
    },
    "us_sectors": {
        "label": "US sector ETFs (11)",
        "symbols": ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE", "XLC"],
        "note": "SPDR sectors; XLRE from 2015 and XLC from 2018.",
    },
    "country_etfs": {
        "label": "Country equity ETFs (20)",
        "symbols": ["SPY", "EWJ", "EWG", "EWU", "EWC", "EWA", "EWZ", "FXI", "EWY", "EWT", "EWH", "EWS", "EWW",
                    "EWL", "EWQ", "EWP", "EWI", "EWN", "EWD", "INDA"],
        "note": "Country momentum / value rotation universe; INDA from 2012.",
    },
    "bonds_credit": {
        "label": "Bonds & credit ETFs (9)",
        "symbols": ["SHY", "IEF", "TLT", "TIP", "LQD", "HYG", "EMB", "MBB", "AGG"],
        "note": "Duration, inflation-linked, IG/HY/EM credit, mortgages.",
    },
    "real_assets": {
        "label": "Commodities & real assets (7)",
        "symbols": ["GLD", "SLV", "DBC", "USO", "UNG", "DBA", "VNQ"],
        "note": "USO and UNG are futures funds with heavy roll costs — their long-run returns are poor by construction.",
    },
    "factor_etfs": {
        "label": "US factor ETFs (7)",
        "symbols": ["MTUM", "QUAL", "USMV", "VLUE", "SIZE", "IWF", "IWD"],
        "note": "Short history (most from 2013).",
    },
    "gem": {
        "label": "Dual momentum: US vs international (2)",
        "symbols": ["SPY", "EFA"],
        "note": "Antonacci's Global Equity Momentum universe; pair with a bond fallback (IEF/AGG).",
    },
    "gtaa5": {
        "label": "Faber GTAA-5 (5)",
        "symbols": ["SPY", "EFA", "IEF", "DBC", "VNQ"],
        "note": "US stocks, foreign stocks, bonds, commodities, REITs — Faber (2007).",
    },
    "us_megacaps": {
        "label": "US large caps (50) — survivorship-biased",
        "symbols": ["AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "BRK-B", "JPM", "JNJ", "V", "PG", "XOM", "UNH",
                    "HD", "MA", "CVX", "KO", "PEP", "MRK", "ABBV", "PFE", "WMT", "BAC", "CSCO", "ORCL", "INTC", "T",
                    "VZ", "DIS", "MCD", "NKE", "ADBE", "CRM", "COST", "TMO", "ABT", "LLY", "AVGO", "TXN", "QCOM",
                    "HON", "IBM", "CAT", "GS", "MS", "AMGN", "LOW", "UPS", "BA", "GE"],
        "note": "Today's large caps: companies that failed or shrank are missing, so stock backtests on this list are optimistic (survivorship bias).",
        "survivorship": True,
    },
}


def clean_symbols(symbols: Sequence[str]) -> Tuple[List[str], List[str]]:
    """(valid, rejected) — upper-cased, de-duplicated, order kept."""
    ok, bad, seen = [], [], set()
    for s in symbols or []:
        t = str(s).strip().upper()
        if not t or t in seen:
            continue
        seen.add(t)
        (ok if _SYMBOL.match(t) else bad).append(t)
    return ok, bad


def resolve_universe(universe: Dict) -> Tuple[List[str], bool]:
    """Symbols for a universe spec {preset} or {symbols}; plus whether it is survivorship-biased."""
    preset = (universe or {}).get("preset")
    if preset and preset != "custom":
        if preset not in PRESETS:
            raise ValueError(f"Unknown universe '{preset}'")
        p = PRESETS[preset]
        return list(p["symbols"]), bool(p.get("survivorship"))
    syms, bad = clean_symbols((universe or {}).get("symbols") or [])
    if bad:
        raise ValueError(f"Invalid ticker(s): {', '.join(bad[:5])}")
    if not syms:
        raise ValueError("The universe is empty — pick a preset or enter tickers.")
    if len(syms) > MAX_SYMBOLS:
        raise ValueError(f"At most {MAX_SYMBOLS} tickers per universe.")
    return syms, False


def _path(sym: str) -> Path:
    return CACHE / f"{sym.replace('^', '_I_').replace('=', '_E_')}.pkl"


def _fresh(sym: str) -> Optional[pd.DataFrame]:
    p = _path(sym)
    try:
        if time.time() - p.stat().st_mtime < MAX_AGE_S:
            return pd.read_pickle(p)
    except Exception:
        pass
    return None


def _download(symbols: List[str]) -> Dict[str, pd.DataFrame]:
    import yfinance as yf
    out: Dict[str, pd.DataFrame] = {}
    if not symbols:
        return out
    df = yf.download(symbols, period="max", interval="1d", auto_adjust=True, group_by="ticker",
                     threads=True, progress=False)
    for s in symbols:
        try:
            sub = df[s] if isinstance(df.columns, pd.MultiIndex) else df
            sub = sub[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
            if len(sub) > 20:
                sub.index = pd.DatetimeIndex(sub.index).tz_localize(None).normalize()
                out[s] = sub.astype(float)
        except Exception:
            continue
    return out


def load(symbols: Sequence[str]) -> Tuple[Dict[str, pd.DataFrame], List[str]]:
    """{symbol: OHLCV DataFrame} for the symbols, and the list with no data."""
    syms, _ = clean_symbols(symbols)
    have: Dict[str, pd.DataFrame] = {}
    with _lock:
        need = []
        for s in syms:
            f = _fresh(s)
            if f is not None:
                have[s] = f
            else:
                need.append(s)
        if need:
            try:
                got = _download(need)
            except Exception as e:
                logger.warning("[quant] download failed: %s", e)
                got = {}
            CACHE.mkdir(parents=True, exist_ok=True)
            for s in need:
                if s in got:
                    got[s].to_pickle(_path(s))
                    have[s] = got[s]
                else:                                   # stale cache beats nothing
                    try:
                        have[s] = pd.read_pickle(_path(s))
                    except Exception:
                        pass
    missing = [s for s in syms if s not in have]
    return have, missing


def panel(symbols: Sequence[str], start: Optional[str] = None, end: Optional[str] = None
          ) -> Tuple[Dict[str, pd.DataFrame], List[str]]:
    """Aligned (dates × symbols) frames {close, open, high, low, volume} on the union of
    trading days; prices forward-filled only inside each symbol's own history."""
    data, missing = load(symbols)
    if not data:
        return {}, missing
    idx = None
    for d in data.values():
        idx = d.index if idx is None else idx.union(d.index)
    idx = pd.DatetimeIndex(idx).sort_values()
    if start:
        idx = idx[idx >= pd.Timestamp(start)]
    if end:
        idx = idx[idx <= pd.Timestamp(end)]
    out = {}
    for field, col in (("close", "Close"), ("open", "Open"), ("high", "High"), ("low", "Low"), ("volume", "Volume")):
        frame = pd.DataFrame({s: d[col] for s, d in data.items()}).reindex(idx)
        if field != "volume":
            last = {s: d.index.max() for s, d in data.items()}
            ff = frame.ffill()
            for s in frame.columns:                       # no carrying a delisted price forward
                ff.loc[ff.index > last[s], s] = float("nan")
            frame = ff
        out[field] = frame
    order = [s for s in symbols if s in data]
    return {k: v[order] for k, v in out.items()}, missing
