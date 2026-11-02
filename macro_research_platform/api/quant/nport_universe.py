"""
Point-in-time index membership from ETF holdings filed with the SEC (form N-PORT, quarterly since late 2019).

Free historical constituent lists exist for the S&P 500 only. For the S&P MidCap 400 and SmallCap 600, the iShares
funds that track them (IJH, IJR) report their complete holdings — with tickers — at every quarter-end. Each snapshot
says exactly which stocks were in the index on that date, including names later removed, acquired or bankrupt, so a
backtest on it carries no survivorship bias. Between snapshots membership is held constant (index changes inside a
quarter are picked up at the next quarter-end — a small timing approximation, reported).
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)
CACHE = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "quant" / "nport"
SERIES = {"IJH": ("S000004307", "S&P MidCap 400"), "IJR": ("S000004313", "S&P SmallCap 600")}
TRUST_CIK = 1100663


def _get(url: str, **params) -> str:
    import requests
    from api.providers.sec_edgar import USER_AGENT
    time.sleep(0.15)                                            # SEC fair access: well under 10 requests a second
    r = requests.get(url, params=params or None, headers={"User-Agent": USER_AGENT}, timeout=60)
    r.raise_for_status()
    return r.text


def _filings(series_id: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for start in (0, 100, 200):
        t = _get("https://www.sec.gov/cgi-bin/browse-edgar", action="getcompany", CIK=series_id, type="NPORT-P",
                 count=100, start=start, output="atom")
        acc = re.findall(r"<accession-number>([^<]+)</accession-number>", t)
        out += list(zip(acc, re.findall(r"<filing-date>([^<]+)</filing-date>", t)))
        if len(acc) < 100:
            break
    return out


def _holdings(acc: str) -> Tuple[str, List[str]]:
    """(report period date, tickers of the equity holdings) of one N-PORT filing, cached on disk."""
    path = CACHE / f"{acc}.json"
    if path.exists():
        d = json.loads(path.read_text())
        return d["period"], d["tickers"]
    x = _get(f"https://www.sec.gov/Archives/edgar/data/{TRUST_CIK}/{acc.replace('-', '')}/primary_doc.xml")
    period = re.search(r"<repPdDate>([^<]+)</repPdDate>", x).group(1)
    tickers = []
    for block in re.findall(r"<invstOrSec>(.*?)</invstOrSec>", x, re.S):
        if "<assetCat>EC</assetCat>" not in block:
            continue
        m = re.search(r'<ticker value="([^"]+)"', block)
        if m:
            tickers.append(m.group(1).strip().upper().replace(".", "-").replace("/", "-"))
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"period": period, "tickers": sorted(set(tickers))}))
    return period, sorted(set(tickers))


def snapshots(funds: Tuple[str, ...] = ("IJH", "IJR")) -> List[Tuple[pd.Timestamp, frozenset]]:
    """Quarter-end membership of the combined indices: [(period date, tickers)], oldest first."""
    by_date: Dict[pd.Timestamp, set] = {}
    for f in funds:
        for acc, _ in _filings(SERIES[f][0]):
            try:
                period, tickers = _holdings(acc)
            except Exception as e:                              # noqa: BLE001 — one unreadable filing is skipped
                logger.info("[nport] %s: %s", acc, e)
                continue
            by_date.setdefault(pd.Timestamp(period), set()).update(tickers)
    return [(d, frozenset(t)) for d, t in sorted(by_date.items())]


def universe_since(start: str, funds: Tuple[str, ...] = ("IJH", "IJR")) -> Tuple[List[str], Dict]:
    snaps = snapshots(funds)
    names = set()
    for d, t in snaps:
        if d >= pd.Timestamp(start) - pd.DateOffset(months=3):
            names |= t
    return sorted(names), {"snapshots": len(snaps), "first": str(snaps[0][0].date()) if snaps else None,
                           "source": "SEC N-PORT holdings of iShares " + " and ".join(f"{f} ({SERIES[f][1]})" for f in funds)}


def members_frame(index: pd.DatetimeIndex, tickers: List[str], funds: Tuple[str, ...] = ("IJH", "IJR")) -> pd.DataFrame:
    """True where the ticker was in the latest quarter-end snapshot on or before each date — no look-ahead."""
    import numpy as np
    snaps = snapshots(funds)
    dates = pd.DatetimeIndex([d for d, _ in snaps])
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
