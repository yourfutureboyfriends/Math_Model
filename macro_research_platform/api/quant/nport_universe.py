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
from typing import Any, Dict, List, Tuple

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


def _holdings(acc: str) -> Dict[str, Any]:
    """One N-PORT filing's equity holdings: {period, tickers, pairs (cusip → ticker), unmapped [(cusip, name)]}.
    Filings before late 2022 carry CUSIPs but no tickers; those are mapped in snapshots()."""
    path = CACHE / f"{acc}.json"
    if path.exists():
        d = json.loads(path.read_text())
        if d.get("v") == 2:
            return d
    x = _get(f"https://www.sec.gov/Archives/edgar/data/{TRUST_CIK}/{acc.replace('-', '')}/primary_doc.xml")
    period = re.search(r"<repPdDate>([^<]+)</repPdDate>", x).group(1)
    tickers, pairs, unmapped = set(), {}, []
    for block in re.findall(r"<invstOrSec>(.*?)</invstOrSec>", x, re.S):
        if "<assetCat>EC</assetCat>" not in block:
            continue
        t = re.search(r'<ticker value="([^"]+)"', block)
        c = re.search(r"<cusip>([^<]+)</cusip>", block)
        n = re.search(r"<name>([^<]+)</name>", block)
        cusip = c.group(1).strip().upper() if c and c.group(1).strip() not in ("000000000", "N/A") else None
        if t:
            tk = t.group(1).strip().upper().replace(".", "-").replace("/", "-")
            tickers.add(tk)
            if cusip:
                pairs[cusip] = tk
        elif cusip:
            unmapped.append([cusip, n.group(1).strip() if n else ""])
    d = {"v": 2, "period": period, "tickers": sorted(tickers), "pairs": pairs, "unmapped": unmapped}
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(d))
    return d


_SNAP_CACHE: Dict[Tuple[str, ...], Tuple[float, List[Tuple[pd.Timestamp, frozenset]]]] = {}


def snapshots(funds: Tuple[str, ...] = ("IJH", "IJR")) -> List[Tuple[pd.Timestamp, frozenset]]:
    """Quarter-end membership of the combined indices: [(period date, tickers)], oldest first. CUSIP-only holdings are
    mapped with the CUSIP → ticker pairs learned from later filings, then SEC / OpenFIGI / issuer-name matching."""
    hit = _SNAP_CACHE.get(funds)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    docs = []
    for f in funds:
        for acc, _ in _filings(SERIES[f][0]):
            try:
                docs.append(_holdings(acc))
            except Exception as e:                              # noqa: BLE001 — one unreadable filing is skipped
                logger.info("[nport] %s: %s", acc, e)
    learned: Dict[str, str] = {}
    for d in docs:
        learned.update(d["pairs"])
    need = {c: n for d in docs for c, n in d["unmapped"] if c not in learned}
    if need:
        mpath = CACHE / "cusip_map.json"
        try:
            known = json.loads(mpath.read_text())
        except Exception:
            known = {}
        todo = [{"cusip": c, "issuer": n} for c, n in need.items() if c not in known]
        if todo:
            try:
                from api.quant.smartmoney import _map_tickers
                for c, t in _map_tickers(todo).items():
                    known[c] = (t or "").upper().replace(".", "-").replace("/", "-") or None
            except Exception as e:                              # noqa: BLE001 — unmapped names are reported, not guessed
                logger.warning("[nport] mapping: %s", e)
            mpath.write_text(json.dumps(known))
        learned.update({c: t for c, t in known.items() if t})
    by_date: Dict[pd.Timestamp, set] = {}
    for d in docs:
        names = set(d["tickers"]) | {learned[c] for c, _ in d["unmapped"] if learned.get(c)}
        by_date.setdefault(pd.Timestamp(d["period"]), set()).update(names)
    out = [(dt, frozenset(t)) for dt, t in sorted(by_date.items())]
    _SNAP_CACHE[funds] = (time.time(), out)
    return out


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
