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
from api.quant.codelab import UNIVERSE_LIMIT as MAX_SYMBOLS   # one capability limit for loader, sandbox and UI
_SYMBOL = re.compile(r"^\^?[A-Z0-9][A-Z0-9.\-^=&]{0,14}$")      # '&' occurs in real tickers: M&M.NS, PE&OLES.MX
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


# Today's GICS sector SPDR for the large-cap list (sscore(n, 1) hedges each stock with its sector).
# Using today's map is a mild look-ahead: GOOGL/META/DIS/T/VZ moved to Communication Services in 2018
# (XLC only exists from then; earlier dates fall back to the benchmark) and V/MA to Financials in 2023.
SECTOR_ETF: Dict[str, str] = {
    **{s: "XLK" for s in ("AAPL", "MSFT", "NVDA", "CSCO", "ORCL", "INTC", "ADBE", "CRM", "AVGO", "TXN", "QCOM", "IBM", "AMD", "MU")},
    **{s: "XLC" for s in ("GOOGL", "GOOG", "META", "T", "VZ", "DIS", "NFLX", "CMCSA")},
    **{s: "XLY" for s in ("AMZN", "HD", "MCD", "NKE", "LOW", "TSLA", "SBUX", "BKNG")},
    **{s: "XLF" for s in ("BRK-B", "JPM", "V", "MA", "BAC", "GS", "MS", "WFC", "C", "AXP", "BLK", "SCHW")},
    **{s: "XLV" for s in ("JNJ", "UNH", "MRK", "ABBV", "PFE", "TMO", "ABT", "LLY", "AMGN", "BMY", "GILD", "CVS")},
    **{s: "XLP" for s in ("PG", "KO", "PEP", "WMT", "COST", "PM", "MO", "CL", "MDLZ")},
    **{s: "XLE" for s in ("XOM", "CVX", "COP", "SLB", "EOG")},
    **{s: "XLI" for s in ("HON", "CAT", "UPS", "BA", "GE", "RTX", "LMT", "DE", "UNP")},
    **{s: "XLU" for s in ("NEE", "DUK", "SO")},
    **{s: "XLB" for s in ("LIN", "APD", "SHW")},
    **{s: "XLRE" for s in ("PLD", "AMT", "EQIX")},
}


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
    """Legacy pickle path (read once for migration; never written)."""
    return CACHE / f"{sym.replace('^', '_I_').replace('=', '_E_')}.pkl"


def _pq(sym: str) -> Path:
    return CACHE / f"{sym.replace('^', '_I_').replace('=', '_E_')}.parquet"


def _read(sym: str) -> Optional[pd.DataFrame]:
    """Cached frame: portable Parquet; a legacy pickle (written by this server) is read once and migrated.
    An unreadable file counts as missing, so it is re-downloaded rather than silently half-used."""
    p = _pq(sym)
    if p.exists():
        try:
            return pd.read_parquet(p)
        except Exception as e:                               # noqa: BLE001
            logger.warning("[quant] unreadable cache %s: %s", p.name, e)
            return None
    old = _path(sym)
    if old.exists():
        try:
            df = pd.read_pickle(old)
            _write(sym, df, migrated=True)
            return df
        except Exception as e:                               # noqa: BLE001 — e.g. pickle from another pandas version
            logger.warning("[quant] legacy cache %s unreadable (%s) — will re-download", old.name, e)
    return None


def _write(sym: str, df: pd.DataFrame, migrated: bool = False) -> None:
    import os
    CACHE.mkdir(parents=True, exist_ok=True)
    p = _pq(sym)
    tmp = p.with_suffix(".parquet.tmp")
    df.to_parquet(tmp)
    os.replace(tmp, p)                                       # atomic: a crash never leaves half a file
    if not migrated or not _pq(sym).with_suffix(".json").exists():
        _write_manifest(sym, df, migrated)
    try:
        if migrated:
            _path(sym).unlink()
    except Exception:                                        # noqa: BLE001
        pass


def _write_manifest(sym: str, df: pd.DataFrame, migrated: bool = False) -> None:
    """Sidecar describing a cached series: when and how it was fetched, what it covers and with which library
    versions — so a stale or incompatible cache is visible, and pickles are never the only record."""
    import hashlib
    import json
    import numpy as np
    try:
        body = {"symbol": sym, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "source": "Yahoo Finance",
                "adjustment": "auto_adjust=True (splits and dividends folded into OHLC; total return)",
                "rows": int(len(df)), "first": str(df.index.min().date()), "last": str(df.index.max().date()),
                "close_sha256": hashlib.sha256(np.ascontiguousarray(df["Close"].to_numpy(float)).tobytes()).hexdigest()[:16],
                "pandas": pd.__version__, "numpy": np.__version__, "format": "parquet (pyarrow)",
                "migrated_from_pickle": migrated}
        if migrated:
            body["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_path(sym).stat().st_mtime))
        _pq(sym).with_suffix(".json").write_text(json.dumps(body))
    except Exception:                                         # noqa: BLE001 — the manifest must never block data
        pass


def _fresh(sym: str) -> Optional[pd.DataFrame]:
    for p in (_pq(sym), _path(sym)):
        try:
            if p.exists() and time.time() - p.stat().st_mtime < MAX_AGE_S:
                return _read(sym)
        except Exception:                                    # noqa: BLE001
            pass
    return None


BATCH = 150                            # tickers per Yahoo request — thousands in one call fail or time out


def _download(symbols: List[str]) -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    for i in range(0, len(symbols), BATCH):
        try:
            out.update(_download_batch(symbols[i:i + BATCH]))
        except Exception as e:                               # noqa: BLE001 — one failed batch must not lose the rest
            logger.warning("[quant] batch %s–%s failed: %s", i, i + BATCH, e)
        if len(symbols) > BATCH:
            time.sleep(1.0)                                   # be polite to Yahoo between batches
    return out


def _download_batch(symbols: List[str]) -> Dict[str, pd.DataFrame]:
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


LAST_REPORT = threading.local()


def load(symbols: Sequence[str]) -> Tuple[Dict[str, pd.DataFrame], List[str]]:
    """{symbol: OHLCV DataFrame} for the symbols, and the list with no data. Symbols served from an
    out-of-date cache because the download failed are listed in `LAST_REPORT.stale` (this thread)."""
    syms, _ = clean_symbols(symbols)
    have: Dict[str, pd.DataFrame] = {}
    stale: List[str] = []
    with _lock:
        need = []
        if len(syms) > 50:                              # Parquet reads release the GIL: read thousands in parallel
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(8) as ex:
                frames = list(ex.map(_fresh, syms))
        else:
            frames = [_fresh(s) for s in syms]
        for s, f in zip(syms, frames):
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
                    _write(s, got[s])
                    have[s] = got[s]
                else:                                   # stale cache beats nothing — but say so
                    old = _read(s)
                    if old is not None:
                        have[s] = old
                        stale.append(s)
    missing = [s for s in syms if s not in have]
    LAST_REPORT.stale = stale
    return have, missing


def panel(symbols: Sequence[str], start: Optional[str] = None, end: Optional[str] = None, fill: bool = True
          ) -> Tuple[Dict[str, pd.DataFrame], List[str]]:
    """Aligned (dates × symbols) frames {close, open, high, low, volume} on the union of trading days.
    fill=True: prices forward-filled inside each symbol's own history (convenient marks; hides missing bars).
    fill=False: raw observations — NaN wherever a symbol has no bar that day (the Code Lab uses this and
    keeps an explicit `observed` mask)."""
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
    # Assembled positionally: one index lookup per symbol, written straight into arrays (aligning thousands of
    # series column by column through pandas took minutes for a global universe).
    order = [s for s in symbols if s in data]
    import numpy as np
    fields = (("close", "Close"), ("open", "Open"), ("high", "High"), ("low", "Low"), ("volume", "Volume"))
    arr = {f: np.full((len(idx), len(order)), np.nan) for f, _ in fields}
    last_pos = np.full(len(order), -1)
    for j, s in enumerate(order):
        d = data[s]
        if not d.index.is_unique:
            d = d[~d.index.duplicated(keep="last")]
        pos = idx.get_indexer(d.index)
        hit = pos >= 0
        if hit.any():
            last_pos[j] = pos[hit].max()
        for f, col in fields:
            arr[f][pos[hit], j] = d[col].to_numpy(float)[hit]
    out = {}
    for f, _ in fields:
        a = arr[f]
        if f != "volume" and fill:
            a = pd.DataFrame(a).ffill().to_numpy().copy()
            a[np.arange(len(idx))[:, None] > last_pos[None, :]] = np.nan     # no carrying a delisted price forward
        out[f] = pd.DataFrame(a, index=idx, columns=order)
    return out, missing
