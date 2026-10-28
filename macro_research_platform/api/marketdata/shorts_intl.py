"""
SI outside the US — short positions from each market's regulator, all free and official:
  · UK (FCA): aggregated net short positions (ANSP) per issuer, % of issued shares — the current file and its history.
    Since the 2026 UK short-selling reforms the FCA publishes the aggregate rather than each holder.
  · Hong Kong (SFC): aggregated reportable short positions per stock, weekly (shares and HK$), as a % of shares
    outstanding.
  · Japan (JPX): each short seller holding ≥ 0.5% of shares outstanding, from the daily disclosure files; a holder's
    latest report stands until it falls below the threshold.
"""
from __future__ import annotations

import concurrent.futures as cf
import io
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from api.marketdata.core import NotFound, Upstream, _cached, _f, _info, _norm

logger = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (research platform; short-position data)"}
FCA_CURRENT = "https://www.fca.org.uk/publication/documents/aggregated-current-net-short-positions.csv"
FCA_HISTORIC = "https://www.fca.org.uk/publication/documents/aggregated-historic-net-short-positions.csv"
SFC_PAGE = "https://www.sfc.hk/en/Regulatory-functions/Market/Short-position-reporting/Aggregated-reportable-short-positions-of-specified-shares"
JPX_PAGE = "https://www.jpx.co.jp/english/markets/public/short-selling/index.html"
JPX_THRESHOLD = 0.005
JPX_FILES = 20


def _get(url: str, timeout: int = 40) -> requests.Response:
    r = requests.get(url, headers=UA, timeout=timeout)
    if r.status_code != 200:
        raise Upstream(f"{url.split('/')[2]} returned HTTP {r.status_code}.")
    return r


def market_of(symbol: str) -> Optional[str]:
    """'UK', 'HK' or 'JP' for a London, Hong Kong or Tokyo listing; None otherwise."""
    return {"L": "UK", "HK": "HK", "T": "JP"}.get(symbol.rpartition(".")[2] if "." in symbol else "")


def short_positions(symbol: str) -> Dict[str, Any]:
    """Regulator-published short positions for a London, Hong Kong or Tokyo listing."""
    s = symbol.strip().upper()
    m = market_of(s)
    if m == "UK":
        return _uk(s)
    if m == "HK":
        return _hk(s)
    if m == "JP":
        return _jp(s)
    raise NotFound(f"Short-position data here covers US (FINRA), UK (FCA), Hong Kong (SFC) and Japan (JPX) listings — not {s}.")


# ── UK ───────────────────────────────────────────────────────────────────────
def _uk_files() -> Dict[str, pd.DataFrame]:
    def fetch():
        cur = pd.read_csv(io.StringIO(_get(FCA_CURRENT).content.decode("utf-8-sig")))
        hist = pd.read_csv(io.StringIO(_get(FCA_HISTORIC).content.decode("utf-8-sig")))
        for df in (cur, hist):
            df.columns = ["name", "isin", "pct", "date", *df.columns[4:]]
            df["key"] = df["name"].map(lambda x: _norm(str(x)))
        return {"current": cur, "historic": hist}
    return _cached("si:fca", 6 * 3600, fetch)


def _uk(s: str) -> Dict[str, Any]:
    i = _info(s)
    key = _norm(i.get("longName") or i.get("shortName") or "")
    f = _uk_files()
    cur, hist = f["current"], f["historic"]
    mine_c, mine_h = cur[cur["key"] == key], hist[hist["key"] == key]
    if mine_c.empty and mine_h.empty:
        raise NotFound(f"No aggregated net short position published for {i.get('longName') or s} — the FCA publishes one when "
                       "holders' net shorts add up to at least 0.2% of issued shares.")
    pts = [{"date": pd.to_datetime(r["date"], dayfirst=True).strftime("%Y-%m-%d"), "pct": float(r["pct"]) / 100}
           for _, r in pd.concat([mine_h, mine_c]).iterrows()]
    pts = sorted({p["date"]: p for p in pts}.values(), key=lambda p: p["date"])
    latest = mine_c.iloc[0] if not mine_c.empty else None
    return {"symbol": s, "market": "UK", "name": i.get("longName"),
            "aggregate_pct": float(latest["pct"]) / 100 if latest is not None else 0.0,
            "as_of": pd.to_datetime(latest["date"], dayfirst=True).strftime("%Y-%m-%d") if latest is not None else None,
            "current": latest is not None, "history": pts[-120:], "holders": [],
            "note": ("Aggregated net short position: the sum of all holders' net shorts as a % of issued shares, published by the FCA "
                     "when it reaches 0.2%. Not current = it has fallen below that." if latest is not None else
                     "No current aggregate is published (below 0.2% of issued shares); the history shows earlier positions."),
            "source": "Financial Conduct Authority — aggregated net short positions"}


# ── Hong Kong ────────────────────────────────────────────────────────────────
def _hk_files(weeks: int = 26) -> List[pd.DataFrame]:
    def fetch():
        html = _get(SFC_PAGE).text
        urls = re.findall(r'href="(https://www\.sfc\.hk/[^"]*Short_Position_Reporting_Aggregated_Data_\d{8}\.csv[^"]*)"', html)[:weeks]
        if not urls:
            raise Upstream("The SFC page lists no short-position files.")
        def one(u):
            try:
                return pd.read_csv(io.StringIO(_get(u).text))
            except Exception as e:                               # a missing week leaves a gap, not an error
                logger.warning("[si-hk] %s: %s", u, e)
                return None
        with cf.ThreadPoolExecutor(4) as ex:
            return [d for d in ex.map(one, urls) if d is not None]
    return _cached(f"si:sfc:{weeks}", 12 * 3600, fetch)


def _hk(s: str) -> Dict[str, Any]:
    code = int(s.split(".")[0])
    i = _info(s)
    shares = _f(i.get("sharesOutstanding"))
    rows = []
    for df in _hk_files():
        df.columns = ["date", "code", "name", "shares", "value_hkd"]
        hit = df[pd.to_numeric(df["code"], errors="coerce") == code]
        if not hit.empty:
            r = hit.iloc[0]
            rows.append({"date": datetime.strptime(str(r["date"]), "%d/%m/%Y").strftime("%Y-%m-%d"),
                         "shares": float(r["shares"]), "value_hkd": float(r["value_hkd"]),
                         "pct": float(r["shares"]) / shares if shares else None})
    if not rows:
        raise NotFound(f"{s} is not a designated security for short selling, or no short positions were reported.")
    rows.sort(key=lambda r: r["date"])
    last, first = rows[-1], rows[0]
    return {"symbol": s, "market": "HK", "name": i.get("longName"), "aggregate_pct": last["pct"], "as_of": last["date"],
            "current": True, "shares_short": last["shares"], "value_hkd": last["value_hkd"],
            "change_pct_points": (last["pct"] - rows[-2]["pct"]) if len(rows) > 1 and last["pct"] is not None and rows[-2]["pct"] is not None else None,
            "history": [{"date": r["date"], "pct": r["pct"], "shares": r["shares"]} for r in rows], "holders": [],
            "note": "Aggregated reportable short positions (holders above HK$30m or 0.02% of shares), published weekly by the SFC "
                    "with a one-week lag; % of shares outstanding from Yahoo.",
            "source": "Securities and Futures Commission (Hong Kong)"}


# ── Japan ────────────────────────────────────────────────────────────────────
def _jp_files() -> List[pd.DataFrame]:
    def fetch():
        html = _get(JPX_PAGE).text
        links = re.findall(r'href="(/english/markets/public/short-selling/[^"]+_Short_Positions\.xls)"', html)[:JPX_FILES]
        def one(path):
            try:
                df = pd.read_excel(io.BytesIO(_get("https://www.jpx.co.jp" + path).content), header=None, skiprows=8)
                df = df.iloc[:, [1, 2, 4, 5, 10, 11]]
                df.columns = ["date", "code", "name", "holder", "ratio", "shares"]
                return df.dropna(subset=["code", "holder"])
            except Exception as e:
                logger.warning("[si-jp] %s: %s", path, e)
                return None
        with cf.ThreadPoolExecutor(4) as ex:
            return [d for d in ex.map(one, links) if d is not None]
    return _cached("si:jpx", 12 * 3600, fetch)


def _jp(s: str) -> Dict[str, Any]:
    code = s.split(".")[0]
    i = _info(s)
    allr = pd.concat(_jp_files(), ignore_index=True) if _jp_files() else pd.DataFrame()
    mine = allr[allr["code"].astype(str).str.strip() == code] if not allr.empty else allr
    if mine.empty:
        raise NotFound(f"No short seller filed a new or changed position of ≥ 0.5% in {i.get('longName') or s} in the last "
                       f"{JPX_FILES} trading days (JPX). Holders re-report only when their position moves by 0.1 point, so an older, "
                       "unchanged position would not appear here.")
    mine = mine.assign(date=pd.to_datetime(mine["date"]))
    latest = mine.sort_values("date").groupby("holder").tail(1)                 # each holder's latest report
    holders = [{"holder": r["holder"], "pct": float(r["ratio"]), "shares": _f(r["shares"]), "date": r["date"].strftime("%Y-%m-%d")}
               for _, r in latest.iterrows() if float(r["ratio"]) >= JPX_THRESHOLD]
    holders.sort(key=lambda h: -h["pct"])
    return {"symbol": s, "market": "JP", "name": i.get("longName"), "aggregate_pct": sum(h["pct"] for h in holders),
            "as_of": mine["date"].max().strftime("%Y-%m-%d"), "current": bool(holders), "history": [], "holders": holders,
            "note": f"Short sellers holding at least 0.5% of shares outstanding, from JPX's daily disclosures (last {JPX_FILES} trading "
                    "days); each holder's latest report stands until it drops below 0.5%. The total covers disclosed holders only, and a "
                    "position unchanged for longer than the window is not shown.",
            "source": "Japan Exchange Group — short selling positions"}
