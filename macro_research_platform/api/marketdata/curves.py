"""
GC — government bond yield curves from each issuer's official daily data (free, no keys):

  US  US Treasury par yield curve (1 month – 30 years)
  DE  Deutsche Bundesbank zero-coupon curve for Bunds (1 – 30 years)
  EA  ECB euro-area AAA government curve (1 – 30 years)
  GB  Bank of England nominal zero-coupon gilt curve (5, 10, 20 years)
  JP  Ministry of Finance JGB curve (1 – 40 years)
  CA  Bank of Canada benchmark bonds (2, 3, 5, 7, 10 years, long)
  AU  Reserve Bank of Australia government bonds (2, 3, 5, 10 years)

Each curve comes with its value one week and one month earlier, so the screen can show how the
curve has moved. Daily data, a day or two behind the market; tenors in years.
"""
from __future__ import annotations

import csv
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from api.marketdata.core import Upstream, _cached

logger = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (MacroTerminal research)"}
Hist = Dict[str, Dict[float, float]]          # date → {tenor: yield}


def _get(url: str, **kw):
    import requests
    r = requests.get(url, headers=UA, timeout=30, **kw)
    r.raise_for_status()
    return r


def _us() -> Hist:
    out: Hist = {}
    cols = {"1 Mo": 1 / 12, "2 Mo": 2 / 12, "3 Mo": 0.25, "4 Mo": 4 / 12, "6 Mo": 0.5, "1 Yr": 1, "2 Yr": 2, "3 Yr": 3, "5 Yr": 5,
            "7 Yr": 7, "10 Yr": 10, "20 Yr": 20, "30 Yr": 30}
    y = date.today().year
    for yr in (y, y - 1) if date.today().month <= 2 else (y,):
        txt = _get(f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{yr}/all",
                   params={"type": "daily_treasury_yield_curve", "field_tdr_date_value": yr, "_format": "csv"}).text
        for row in csv.DictReader(io.StringIO(txt)):
            d = datetime.strptime(row["Date"], "%m/%d/%Y").date().isoformat()
            out[d] = {t: float(row[c]) for c, t in cols.items() if row.get(c) not in (None, "", "N/A")}
    return out


def _bundesbank() -> Hist:
    out: Hist = {}
    def one(t: int):
        key = f"D.I.ZST.ZI.EUR.S1311.B.A604.R{t:02d}XX.R.A.A._Z._Z.A"
        txt = _get(f"https://api.statistiken.bundesbank.de/rest/data/BBSIS/{key}", params={"lastNObservations": 40, "format": "csv"}).text
        rows = []
        for line in txt.splitlines():
            p = line.split(";")
            if len(p) >= 2 and len(p[0]) == 10 and p[0][4] == "-" and p[1] not in ("", "."):
                rows.append((p[0], float(p[1].replace(",", "."))))
        return t, rows
    with ThreadPoolExecutor(6) as ex:
        for t, rows in ex.map(one, (1, 2, 3, 5, 7, 10, 15, 20, 30)):
            for d, v in rows:
                out.setdefault(d, {})[float(t)] = v
    return out


def _ecb() -> Hist:
    out: Hist = {}
    def one(t: str):
        txt = _get(f"https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_{t}",
                   params={"lastNObservations": 40, "format": "csvdata"}).text
        rows = [(r["TIME_PERIOD"], float(r["OBS_VALUE"])) for r in csv.DictReader(io.StringIO(txt)) if r.get("OBS_VALUE")]
        tenor = int(t[:-1]) / (12 if t.endswith("M") else 1)
        return tenor, rows
    with ThreadPoolExecutor(6) as ex:
        for t, rows in ex.map(one, ("3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "15Y", "20Y", "30Y")):
            for d, v in rows:
                out.setdefault(d, {})[t] = v
    return out


def _boe() -> Hist:
    start = (date.today() - timedelta(days=50)).strftime("%d/%b/%Y")
    txt = _get("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp",
               params={"csv.x": "yes", "Datefrom": start, "Dateto": "now", "SeriesCodes": "IUDSNZC,IUDMNZC,IUDLNZC",
                       "CSVF": "TN", "UsingCodes": "Y", "VPD": "Y", "VFD": "N"}).text
    out: Hist = {}
    for row in csv.reader(io.StringIO(txt)):
        try:
            d = datetime.strptime(row[0], "%d %b %Y").date().isoformat()
        except (ValueError, IndexError):
            continue
        out[d] = {t: float(v) for t, v in zip((5.0, 10.0, 20.0), row[1:4]) if v not in ("", None)}
    return out


def _mof() -> Hist:
    out: Hist = {}
    for url in ("https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv",
                "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv"):
        try:
            raw = _get(url).content.decode("shift_jis", "replace")
        except Exception:
            continue
        lines = raw.splitlines()
        hdr = next((l.split(",") for l in lines if l.startswith("Date,")), None)
        if not hdr:
            continue
        tenors = [float(h.rstrip("Y")) if h.endswith("Y") else None for h in hdr]
        for line in lines:
            p = line.split(",")
            if not p or not p[0][:4].isdigit():
                continue
            try:
                d = datetime.strptime(p[0], "%Y/%m/%d").date()
            except ValueError:
                continue
            if d < date.today() - timedelta(days=50):
                continue
            out[d.isoformat()] = {t: float(v) for t, v in zip(tenors, p) if t and v not in ("", "-")}
        if len(out) > 25:                         # this month's file plus history is enough
            break
    return out


def _boc() -> Hist:
    names = {"BD.CDN.2YR.DQ.YLD": 2.0, "BD.CDN.3YR.DQ.YLD": 3.0, "BD.CDN.5YR.DQ.YLD": 5.0, "BD.CDN.7YR.DQ.YLD": 7.0,
             "BD.CDN.10YR.DQ.YLD": 10.0, "BD.CDN.LONG.DQ.YLD": 30.0}
    j = _get(f"https://www.bankofcanada.ca/valet/observations/{','.join(names)}/json", params={"recent": 30}).json()
    out: Hist = {}
    for o in j.get("observations", []):
        out[o["d"]] = {t: float(o[k]["v"]) for k, t in names.items() if o.get(k, {}).get("v") not in (None, "")}
    return out


def _rba() -> Hist:
    txt = _get("https://www.rba.gov.au/statistics/tables/csv/f2-data.csv").content.decode("utf-8-sig", "replace")
    out: Hist = {}
    for row in csv.reader(io.StringIO(txt)):
        try:
            d = datetime.strptime(row[0], "%d-%b-%Y").date()
        except (ValueError, IndexError):
            continue
        if d < date.today() - timedelta(days=50):
            continue
        out[d.isoformat()] = {t: float(v) for t, v in zip((2.0, 3.0, 5.0, 10.0), row[1:5]) if v not in ("", None)}
    return out


SOURCES: Dict[str, Tuple[str, str, Callable[[], Hist]]] = {
    "US": ("United States", "US Treasury par yield curve", _us),
    "DE": ("Germany", "Deutsche Bundesbank (zero-coupon, Svensson)", _bundesbank),
    "EA": ("Euro area AAA", "ECB AAA-rated euro-area government curve", _ecb),
    "GB": ("United Kingdom", "Bank of England nominal zero-coupon gilt curve", _boe),
    "JP": ("Japan", "Ministry of Finance JGB curve", _mof),
    "CA": ("Canada", "Bank of Canada benchmark bond yields", _boc),
    "AU": ("Australia", "Reserve Bank of Australia (table F2)", _rba),
}


def _point_on_or_before(h: Hist, d: str) -> Optional[Tuple[str, Dict[float, float]]]:
    keys = [k for k in sorted(h) if k <= d and h[k]]
    return (keys[-1], h[keys[-1]]) if keys else None


def _curve(code: str) -> Dict[str, Any]:
    name, source, fn = SOURCES[code]
    h = fn()
    days = [k for k in sorted(h) if h[k]]
    if not days:
        raise Upstream(f"{name}: no curve data")
    last = days[-1]
    wk = _point_on_or_before(h, (date.fromisoformat(last) - timedelta(days=7)).isoformat())
    mo = _point_on_or_before(h, (date.fromisoformat(last) - timedelta(days=30)).isoformat())
    pts = []
    for t in sorted(h[last]):
        y = h[last][t]
        pts.append({"tenor": round(t, 4), "yield": round(y, 3),
                    "change_1w_bp": round((y - wk[1][t]) * 100, 1) if wk and t in wk[1] else None,
                    "change_1m_bp": round((y - mo[1][t]) * 100, 1) if mo and t in mo[1] else None})
    def at(t):
        return next((p["yield"] for p in pts if abs(p["tenor"] - t) < 1e-6), None)
    two, ten = at(2.0), at(10.0)
    return {"code": code, "name": name, "date": last, "source": source, "points": pts,
            "week_ago": {"date": wk[0], "points": [{"tenor": round(t, 4), "yield": round(v, 3)} for t, v in sorted(wk[1].items())]} if wk else None,
            "month_ago": {"date": mo[0], "points": [{"tenor": round(t, 4), "yield": round(v, 3)} for t, v in sorted(mo[1].items())]} if mo else None,
            "slope_2s10s_bp": round((ten - two) * 100, 1) if two is not None and ten is not None else None}


def curves() -> Dict[str, Any]:
    def build():
        out, errors = {}, {}
        def one(code):
            try:
                return code, _curve(code), None
            except Exception as e:
                logger.warning("[gc] %s: %s", code, e)
                return code, None, str(e)
        with ThreadPoolExecutor(7) as ex:
            for code, c, err in ex.map(one, SOURCES):
                if c:
                    out[code] = c
                else:
                    errors[code] = err
        if not out:
            raise Upstream("No government curve could be loaded.")
        return {"curves": out, "unavailable": errors, "order": [c for c in SOURCES if c in out],
                "note": "Official daily curves from each issuer (a day or two behind the market). Tenors in years; changes in basis points.",
                "source": "; ".join(f"{v[0]}: {v[1]}" for k, v in SOURCES.items() if k in out)}
    return _cached("gc:curves", 3 * 3600, build)
