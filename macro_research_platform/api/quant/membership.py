"""
Point-in-time S&P 500 membership — which stocks were in the index on each date, including those
later removed, acquired or bankrupt. Lets a strategy choose only among names that were index members
*at the time*, instead of today's survivors.

Sources (free):
  * snapshots on every change date since 1996-01-02 (github.com/hanshof/sp500_constituents,
    sp_500_historical_components.csv), cached weekly;
  * after that file's last date, Wikipedia's current constituent table: names with a later
    "Date added" join on that date; names in the last snapshot but no longer listed are treated as
    removed on the first such addition date (the exact date is not in the data — approximation).

Limitations, reported with every result: membership is as of each snapshot; well-known renames are mapped
to today's symbol (RENAMES), others stay as the symbol of the time; many removed names have no free price
history and are listed as dropped — the remaining survivorship effect is reported, not hidden.
"""
from __future__ import annotations

import io
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)
CACHE = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "quant" / "membership"
HIST_URL = "https://raw.githubusercontent.com/hanshof/sp500_constituents/main/sp_500_historical_components.csv"
WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
TTL = 7 * 86400
UA = {"User-Agent": "Mozilla/5.0 (macro research terminal)"}


# Renames only — the same company continuing under a new symbol (never an acquisition), so its price
# history on Yahoo sits under the new ticker. Old symbol → current Yahoo symbol.
RENAMES = {"FB": "META", "ANTM": "ELV", "ABC": "COR", "RE": "EG", "WLTW": "WTW", "BLL": "BALL", "FISV": "FI",
           "PKI": "RVTY", "CDAY": "DAY", "SQ": "XYZ", "HFC": "DINO", "FLT": "CPAY", "PEAK": "DOC", "DISCA": "WBD",
           "COG": "CTRA", "ADS": "BFH", "NLOK": "GEN", "FBHS": "FBIN", "TWX": None}


def _norm(t: str) -> str:
    """Symbol only ('RVTY (PREVIOUSLY PKI)' → 'RVTY'), Yahoo class separator, renames mapped."""
    import re
    m = re.match(r"[A-Za-z0-9][A-Za-z0-9.\-/]*", str(t).strip())
    x = (m.group(0) if m else str(t).strip()).upper().replace(".", "-").replace("/", "-")
    return RENAMES.get(x) or x


def _get(url: str) -> str:
    import requests
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    return r.text


def _cached_text(name: str, url: str) -> Optional[str]:
    p = CACHE / name
    try:
        if time.time() - p.stat().st_mtime < TTL:
            return p.read_text()
    except OSError:
        pass
    try:
        txt = _get(url)
        CACHE.mkdir(parents=True, exist_ok=True)
        p.write_text(txt)
        return txt
    except Exception as e:                                      # noqa: BLE001 — stale beats nothing, but say so
        logger.warning("[membership] %s download failed: %s", name, e)
        try:
            return p.read_text()
        except OSError:
            return None


def snapshots() -> Tuple[List[Tuple[pd.Timestamp, frozenset]], Dict[str, Any]]:
    """[(date, members)] sorted by date, plus provenance."""
    hist = _cached_text("sp500_history.csv", HIST_URL)
    if hist is None:
        raise ValueError("S&P 500 membership history is unavailable (no network and no cached copy).")
    df = pd.read_csv(io.StringIO(hist))
    snaps = [(pd.Timestamp(d), frozenset(_norm(t) for t in str(ts).split(",") if t))
             for d, ts in zip(df["date"], df["tickers"])]
    snaps.sort(key=lambda x: x[0])
    info: Dict[str, Any] = {"source": HIST_URL, "first": str(snaps[0][0].date()), "history_last": str(snaps[-1][0].date())}
    wiki = _cached_text("sp500_wikipedia.html", WIKI_URL)
    if wiki:
        try:
            snaps, extra = _extend_with_current(snaps, wiki)
            info.update(extra)
        except Exception as e:                                  # noqa: BLE001
            info["wikipedia_error"] = str(e)[:200]
    return snaps, info


def _extend_with_current(snaps, wiki_html: str):
    """Append post-history changes from the current constituent list (see module docstring)."""
    cur = pd.read_html(io.StringIO(wiki_html))[0]
    cur["Symbol"] = cur["Symbol"].map(_norm)
    cur["added"] = pd.to_datetime(cur["Date added"], errors="coerce")
    last_date, last_set = snaps[-1]
    current = frozenset(cur["Symbol"])
    later = cur[cur["added"] > last_date].sort_values("added")
    removed = sorted(last_set - current)
    out = list(snaps)
    members = set(last_set)
    first_add = later["added"].iloc[0] if len(later) else None
    for d, grp in later.groupby("added"):
        if first_add is not None and d == first_add:
            members -= set(removed)                             # removal dates unknown: on the first later addition
        members |= set(grp["Symbol"])
        out.append((pd.Timestamp(d), frozenset(members)))
    if set(members) != set(current):                            # reconcile to today's list exactly
        out.append((pd.Timestamp.today().normalize(), current))
    return out, {"current_source": WIKI_URL, "current_count": len(current), "post_history_additions": int(len(later)),
                 "post_history_removals_approximate": removed}


def universe_since(start: str) -> Tuple[List[str], Dict[str, Any]]:
    """Every ticker that was a member at any time on or after `start` (including the snapshot in force then).
    Symbols the data layer cannot accept are reported in info['unparseable'], never silently dropped."""
    from api.quant import data as qdata
    snaps, info = snapshots()
    s = pd.Timestamp(start)
    names: set = set()
    before = [x for x in snaps if x[0] <= s]
    if before:
        names |= before[-1][1]
    for d, m in snaps:
        if d > s:
            names |= m
    valid, bad = qdata.clean_symbols(sorted(names))
    info["unparseable"] = bad
    return valid, info


def members_frame(index: pd.DatetimeIndex, tickers: List[str]) -> pd.DataFrame:
    """Boolean (dates × tickers): True where the ticker was an index member on that date (as of the latest
    snapshot on or before it). Uses only snapshots dated on or before each day — no look-ahead."""
    snaps, _ = snapshots()
    dates = pd.DatetimeIndex([d for d, _ in snaps])
    import numpy as np
    pos = dates.searchsorted(index, side="right") - 1
    col = {t: i for i, t in enumerate(tickers)}
    arr = np.zeros((len(index), len(tickers)), dtype=bool)
    for k in sorted(set(pos)):
        if k < 0:
            continue
        rows = pos == k
        for t in snaps[k][1]:
            j = col.get(t)
            if j is not None:
                arr[rows, j] = True
    return pd.DataFrame(arr, index=index, columns=tickers)
