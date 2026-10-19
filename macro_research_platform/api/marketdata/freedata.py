"""
Free public series the audit found missing (2026-10): Shiller CAPE history, AAII sentiment, the New York Fed Staff
Nowcast, CBOE put/call ratios and the Nasdaq IPO calendar. Each is cached; a failed refresh serves the last good
value marked stale (api/marketdata/core._cached).

Sources (all free, no key):
  * Shiller CAPE    — Robert Shiller's ie_data.xls (shillerdata.com; the old Yale copy stops in 2023).
  * AAII            — aaii.com weekly sentiment survey spreadsheet.
  * NY Fed nowcast  — newyorkfed.org Staff Nowcast chart-data download.
  * CBOE put/call   — cdn.cboe.com daily market statistics JSON (one file per session).
  * IPOs            — api.nasdaq.com IPO calendar (priced, upcoming, filed, withdrawn).
"""
from __future__ import annotations

import io
import logging
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from api.marketdata.core import _cached, NotFound

logger = logging.getLogger(__name__)

BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/126 Safari/537.36",
              "Accept": "application/json, text/plain, */*"}


def _get(url: str, timeout: float = 30, **kw):
    import requests
    r = requests.get(url, headers=BROWSER_UA, timeout=timeout, **kw)
    r.raise_for_status()
    return r


def _pct_rank(values: List[float], x: float) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return round(100.0 * sum(v <= x for v in vals) / len(vals), 1) if vals else None


# ── Shiller CAPE ──────────────────────────────────────────────────────────────
def shiller_cape() -> Dict[str, Any]:
    """Monthly S&P 500 cyclically adjusted P/E (10-year real earnings) since 1881, with the latest value's
    percentile and z-score against the whole history and since 1990."""
    def fetch():
        import pandas as pd
        url = None
        try:
            html = _get("https://shillerdata.com/", timeout=20).text
            m = re.search(r'((?:https?:)?//[^"\']+/ie_data\.xls[^"\']*)', html)
            url = ("https:" + m.group(1)) if m and m.group(1).startswith("//") else (m.group(1) if m else None)
        except Exception as e:
            logger.info("[cape] shillerdata.com link lookup failed: %s", e)
        content = _get(url or "http://www.econ.yale.edu/~shiller/data/ie_data.xls", timeout=60).content
        x = pd.read_excel(io.BytesIO(content), sheet_name="Data", skiprows=7)
        x = x[pd.to_numeric(x["Date"], errors="coerce").notna() & pd.to_numeric(x["CAPE"], errors="coerce").notna()]
        yr = x["Date"].astype(float)
        months = ((yr - yr.astype(int)) * 100).round().astype(int).clip(1, 12)
        dates = [f"{int(y)}-{int(mm):02d}" for y, mm in zip(yr, months)]
        vals = [round(float(v), 2) for v in x["CAPE"].astype(float)]
        if not vals:
            raise NotFound("Shiller data has no CAPE rows.")
        import numpy as np
        latest = vals[-1]
        recent = [v for d, v in zip(dates, vals) if d >= "1990-01"]
        return {
            "series": [{"month": d, "cape": v} for d, v in zip(dates, vals)],
            "latest": latest, "latest_month": dates[-1],
            "percentile_all": _pct_rank(vals, latest), "percentile_since_1990": _pct_rank(recent, latest),
            "mean_all": round(float(np.mean(vals)), 1), "mean_since_1990": round(float(np.mean(recent)), 1),
            "z_since_1990": round(float((latest - np.mean(recent)) / np.std(recent, ddof=1)), 2) if len(recent) > 2 else None,
            "earnings_yield_pct": round(100.0 / latest, 2),
            "source": "Robert Shiller, ie_data.xls (" + ("shillerdata.com" if url else "Yale copy") + ")",
            "note": "Monthly; Shiller updates the file irregularly, so the latest month can lag by a few months.",
        }
    return _cached("free:cape", 7 * 86400, fetch)


# ── AAII sentiment ────────────────────────────────────────────────────────────
def aaii_sentiment(weeks: int = 104) -> Dict[str, Any]:
    """Weekly AAII investor sentiment survey: bullish / neutral / bearish shares and the bull−bear spread, with
    the spread's percentile since 1987 (a contrarian gauge)."""
    def fetch():
        import pandas as pd
        a = pd.read_excel(io.BytesIO(_get("https://www.aaii.com/files/surveys/sentiment.xls", timeout=60).content), skiprows=3)
        a["d"] = pd.to_datetime(a["Date"], errors="coerce")
        a = a.dropna(subset=["d", "Bullish", "Bearish"])
        a = a[a["Bullish"].apply(lambda v: isinstance(v, (int, float)))]
        rows = [{"date": d.date().isoformat(), "bullish": round(float(b) * 100, 1), "neutral": round(float(n) * 100, 1),
                 "bearish": round(float(be) * 100, 1), "spread": round((float(b) - float(be)) * 100, 1)}
                for d, b, n, be in zip(a["d"], a["Bullish"], a["Neutral"], a["Bearish"])]
        if not rows:
            raise NotFound("AAII file has no survey rows.")
        spreads = [r["spread"] for r in rows]
        last = rows[-1]
        pct = _pct_rank(spreads, last["spread"])
        return {"latest": last, "spread_percentile": pct,
                "average_bullish": round(sum(r["bullish"] for r in rows) / len(rows), 1),
                "average_bearish": round(sum(r["bearish"] for r in rows) / len(rows), 1),
                "contrarian": ("bullish (crowd very bearish)" if pct is not None and pct <= 10
                               else "bearish (crowd very bullish)" if pct is not None and pct >= 90 else "neutral"),
                "history": rows, "since": rows[0]["date"],
                "source": "AAII Investor Sentiment Survey (weekly, Thursday)"}
    out = _cached("free:aaii", 6 * 3600, fetch)
    return {**out, "history": out["history"][-weeks:]}


# ── New York Fed Staff Nowcast ────────────────────────────────────────────────
def nyfed_nowcast() -> Dict[str, Any]:
    """Weekly NY Fed Staff Nowcast of real GDP growth (q/q SAAR): backcast, nowcast and next-quarter forecast."""
    def fetch():
        import pandas as pd
        url = ("https://www.newyorkfed.org/medialibrary/Research/Interactives/Data/NowCast/downloads/"
               "New-York-Fed-Staff-Nowcast_download_data.xlsx")
        x = pd.read_excel(io.BytesIO(_get(url, timeout=40).content), sheet_name="Forecasts By Horizon", header=None)
        hdr = next(i for i in range(len(x)) if str(x.iat[i, 0]).strip().lower().startswith("forecast date"))
        d = x.iloc[hdr + 1:, :5]
        d.columns = ["date", "quarter", "backcast", "nowcast", "forecast"]
        d = d[pd.to_datetime(d["date"], errors="coerce").notna()]
        num = lambda v: None if pd.isna(v) else round(float(v), 2)
        rows = [{"date": pd.Timestamp(r.date).date().isoformat(), "quarter": str(r.quarter),
                 "backcast": num(r.backcast), "nowcast": num(r.nowcast), "forecast": num(r.forecast)}
                for r in d.itertuples()]
        if not rows:
            raise NotFound("NY Fed nowcast file has no rows.")
        last = rows[-1]
        cur = [r for r in rows if r["quarter"] == last["quarter"] and r["nowcast"] is not None]
        return {"latest": last, "quarter": last["quarter"].replace(":", ""),
                "nowcast": last["nowcast"], "next_quarter": last["forecast"],
                "change_4w": round(cur[-1]["nowcast"] - cur[-5]["nowcast"], 2) if len(cur) >= 5 else None,
                "history": rows[-60:],
                "source": "Federal Reserve Bank of New York, Staff Nowcast (weekly, Fridays)",
                "units": "real GDP growth, % q/q SAAR"}
    return _cached("free:nyfed_nowcast", 6 * 3600, fetch)


# ── CBOE put/call ─────────────────────────────────────────────────────────────
_PC_KEYS = {"TOTAL PUT/CALL RATIO": "total", "INDEX PUT/CALL RATIO": "index", "EQUITY PUT/CALL RATIO": "equity",
            "EXCHANGE TRADED PRODUCTS PUT/CALL RATIO": "etp", "SPX + SPXW PUT/CALL RATIO": "spx"}


def _pc_day(d: date) -> Optional[Dict[str, Any]]:
    def fetch():
        import requests
        r = requests.get(f"https://cdn.cboe.com/data/us/options/market_statistics/daily/{d.isoformat()}_daily_options",
                         headers=BROWSER_UA, timeout=20)
        if r.status_code in (403, 404):
            return {"date": d.isoformat(), "missing": True}
        r.raise_for_status()
        out = {"date": d.isoformat()}
        for x in r.json().get("ratios") or []:
            k = _PC_KEYS.get((x.get("name") or "").strip().upper())
            if k:
                try:
                    out[k] = float(x.get("value"))
                except (TypeError, ValueError):
                    pass
        return out if len(out) > 1 else {"date": d.isoformat(), "missing": True}
    # a past session never changes: cache a week; today's file may still be filling
    return _cached(f"free:pc:{d}", 7 * 86400 if d < date.today() else 1800, fetch)


def cboe_put_call(sessions: int = 30) -> Dict[str, Any]:
    """Daily CBOE put/call ratios (total, equity, index, SPX) for the last `sessions` sessions, the 10-day
    average equity ratio and its percentile within the window."""
    days, d = [], date.today()
    while len(days) < sessions + 12 and (date.today() - d).days < 70:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as ex:
        got = list(ex.map(lambda x: _safe(_pc_day, x), days))
    rows = sorted([g for g in got if g and not g.get("missing") and g.get("equity") is not None],
                  key=lambda r: r["date"])[-sessions:]
    if not rows:
        raise NotFound("CBOE daily market statistics unavailable.")
    eq = [r["equity"] for r in rows]
    avg10 = round(sum(eq[-10:]) / len(eq[-10:]), 3)
    last = rows[-1]
    return {"latest": last, "equity_10d_avg": avg10, "equity_percentile_window": _pct_rank(eq, last["equity"]),
            "contrarian": ("bullish (heavy put buying)" if last["equity"] >= 0.8
                           else "bearish (complacent call buying)" if last["equity"] <= 0.5 else "neutral"),
            "history": rows, "source": "Cboe daily market statistics (cdn.cboe.com)",
            "note": "Equity put/call ≥ 0.8 has marked fear, ≤ 0.5 complacency (rule of thumb, not a tested signal)."}


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception as e:
        logger.debug("[freedata] %s%s: %s", getattr(fn, "__name__", fn), a, e)
        return None


# ── Nasdaq IPO calendar ───────────────────────────────────────────────────────
def nasdaq_ipos(months_back: int = 1, months_ahead: int = 1) -> Dict[str, Any]:
    """US IPOs from Nasdaq's calendar (NYSE and Nasdaq listings): priced, upcoming (expected), filed, withdrawn."""
    def month(ym: str):
        def fetch():
            j = _get("https://api.nasdaq.com/api/ipo/calendar", params={"date": ym}, timeout=20).json()
            return j.get("data") or {}
        return _cached(f"free:ipo:{ym}", 3600, fetch)

    today = date.today()
    yms = []
    for k in range(-months_back, months_ahead + 1):
        y, m = today.year, today.month + k
        while m < 1:
            y, m = y - 1, m + 12
        while m > 12:
            y, m = y + 1, m - 12
        yms.append(f"{y}-{m:02d}")
    rows, seen = [], set()

    def add(r, status, date_key):
        key = (r.get("dealID"), status)
        if key in seen:
            return
        seen.add(key)
        dt = r.get(date_key) or ""
        mdy = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", dt)
        iso = f"{mdy.group(3)}-{int(mdy.group(1)):02d}-{int(mdy.group(2)):02d}" if mdy else None
        num = lambda s: float(re.sub(r"[^\d.]", "", s)) if s and re.sub(r"[^\d.]", "", s) else None
        rows.append({"date": iso, "symbol": r.get("proposedTickerSymbol"), "name": r.get("companyName"),
                     "exchange": r.get("proposedExchange"), "price": r.get("proposedSharePrice"),
                     "shares": num(r.get("sharesOffered")), "value": num(r.get("dollarValueOfSharesOffered")),
                     "status": status})

    for ym in yms:
        try:
            d = month(ym)
        except Exception as e:
            logger.info("[ipo] nasdaq %s: %s", ym, e)
            continue
        for r in ((d.get("priced") or {}).get("rows") or []):
            add(r, "priced", "pricedDate")
        for r in (((d.get("upcoming") or {}).get("upcomingTable") or {}).get("rows") or []):
            add(r, "expected", "expectedPriceDate")
        for r in ((d.get("filed") or {}).get("rows") or []):
            add(r, "filed", "filedDate")
        for r in ((d.get("withdrawn") or {}).get("rows") or []):
            add(r, "withdrawn", "withdrawDate")
    if not rows:
        raise NotFound("Nasdaq IPO calendar returned no deals.")
    rows.sort(key=lambda x: x["date"] or "", reverse=True)
    return {"ipos": rows, "source": "Nasdaq IPO calendar (api.nasdaq.com; NYSE and Nasdaq listings)",
            "note": "'expected' = scheduled with a price range; 'priced' = priced, trading; 'filed' = S-1 filed, "
                    "no date; 'withdrawn' = pulled."}
