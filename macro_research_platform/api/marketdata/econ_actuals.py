"""
Actual figures for non-US (and non-ALFRED) calendar releases, from free official sources:

  * Statistics Canada WDS — every data point carries its release time, so the figure published
    on the event day is matched exactly (labour force survey, CPI, GDP, retail sales, BoC rate).
  * UK Office for National Statistics — the series' latest release date must be the event day
    (CPI, labour market, monthly GDP, retail sales); BoE Bank Rate from the BoE database.
  * University of Michigan — final consumer sentiment; FRED — the Fed's target rate.

A figure is only reported when its release matches the event day; once found it is stored with
the event (calendar.py), so later revisions don't rewrite what was published.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from api.marketdata.core import _cached

logger = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (MacroTerminal research)"}
ONS = "https://www.ons.gov.uk"

# (Forex Factory country, title) → (source, id, transform, unit)
# transforms: level, diff (vs prior period), pct_mm (% vs prior period)
SOURCES: Dict[Tuple[str, str], Tuple[str, Any, str, str]] = {
    ("CAD", "Employment Change"): ("statcan", 2062811, "diff", "K"),
    ("CAD", "Unemployment Rate"): ("statcan", 2062815, "level", "%"),
    ("CAD", "CPI m/m"): ("statcan", 41690973, "pct_mm", "%"),
    ("CAD", "Common CPI y/y"): ("statcan", 108785713, "level", "%"),
    ("CAD", "Median CPI y/y"): ("statcan", 108785714, "level", "%"),
    ("CAD", "Trimmed CPI y/y"): ("statcan", 108785715, "level", "%"),
    ("CAD", "GDP m/m"): ("statcan", 65201210, "pct_mm", "%"),
    ("CAD", "Retail Sales m/m"): ("statcan", 52367097, "pct_mm", "%"),
    ("CAD", "Overnight Rate"): ("statcan_rate", 39079, "level", "%"),
    ("GBP", "CPI y/y"): ("ons", "economy/inflationandpriceindices/timeseries/d7g7/mm23", "level", "%"),
    ("GBP", "Core CPI y/y"): ("ons", "economy/inflationandpriceindices/timeseries/dko8/mm23", "level", "%"),
    ("GBP", "Unemployment Rate"): ("ons", "employmentandlabourmarket/peoplenotinwork/unemployment/timeseries/mgsx/lms", "level", "%"),
    ("GBP", "Average Earnings Index 3m/y"): ("ons", "employmentandlabourmarket/peopleinwork/earningsandworkinghours/timeseries/kac3/lms", "level", "%"),
    ("GBP", "GDP m/m"): ("ons", "economy/grossdomesticproductgdp/timeseries/ecy2/mgdp", "pct_mm", "%"),
    ("GBP", "Retail Sales m/m"): ("ons", "businessindustryandtrade/retailindustry/timeseries/j5ek/drsi", "pct_mm", "%"),
    ("GBP", "Official Bank Rate"): ("boe_rate", "IUDBEDR", "level", "%"),
    # Euro area (Eurostat; ECOICOP v2 HICP since 2026, euro-area aggregate "EA"; labour data on EA21)
    ("EUR", "CPI Flash Estimate y/y"): ("eurostat", "prc_hicp_minr?geo=EA&coicop18=TOTAL&unit=RCH_A", "level", "%"),
    ("EUR", "Core CPI Flash Estimate y/y"): ("eurostat", "prc_hicp_minr?geo=EA&coicop18=TOT_X_NRG_FOOD&unit=RCH_A", "level", "%"),
    ("EUR", "Final CPI y/y"): ("eurostat", "prc_hicp_minr?geo=EA&coicop18=TOTAL&unit=RCH_A", "level", "%"),
    ("EUR", "Final Core CPI y/y"): ("eurostat", "prc_hicp_minr?geo=EA&coicop18=TOT_X_NRG_FOOD&unit=RCH_A", "level", "%"),
    ("EUR", "CPI m/m"): ("eurostat", "prc_hicp_minr?geo=EA&coicop18=TOTAL&unit=RCH_M", "level", "%"),
    ("EUR", "Unemployment Rate"): ("eurostat", "une_rt_m?geo=EA21&s_adj=SA&age=TOTAL&sex=T&unit=PC_ACT", "level", "%"),
    ("USD", "Revised UoM Consumer Sentiment"): ("umich", None, "level", ""),
    # ISM's own release headlines on PR Newswire ("Services PMI® at 54.9%; September 2026 ISM® …")
    ("USD", "ISM Services PMI"): ("ism", "Services", "level", ""),
    ("USD", "ISM Manufacturing PMI"): ("ism", "Manufacturing", "level", ""),
    ("USD", "Federal Funds Rate"): ("fred_rate", "DFEDTARU", "level", "%"),
}


def _transform(vals: List[float], how: str) -> Optional[float]:
    if not vals:
        return None
    if how == "level":
        return vals[-1]
    if len(vals) < 2 or not vals[-2]:
        return None
    return vals[-1] - vals[-2] if how == "diff" else (vals[-1] / vals[-2] - 1) * 100


def _statcan(vector: int, how: str, day: str) -> Optional[Tuple[float, str]]:
    import requests

    def fetch():
        r = requests.post("https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods",
                          json=[{"vectorId": vector, "latestN": 4}], headers=UA, timeout=20)
        r.raise_for_status()
        return r.json()[0]["object"]["vectorDataPoint"]
    pts = _cached(f"statcan:{vector}", 1800, fetch)
    # the newest point released on the event day (Ottawa time stamps)
    idx = [i for i, p in enumerate(pts) if str(p.get("releaseTime", ""))[:10] == day]
    if not idx:
        return None
    i = idx[-1]
    v = _transform([p["value"] for p in pts[: i + 1] if p.get("value") is not None], how)
    return (v, pts[i]["refPer"]) if v is not None else None


def _statcan_rate(vector: int, day: str) -> Optional[Tuple[float, str]]:
    """A policy-rate decision: the target in force the day after the announcement."""
    import requests

    def fetch():
        r = requests.post("https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods",
                          json=[{"vectorId": vector, "latestN": 30}], headers=UA, timeout=20)
        r.raise_for_status()
        return r.json()[0]["object"]["vectorDataPoint"]
    return _rate_after([(p["refPer"], p["value"]) for p in _cached(f"statcan:{vector}:rate", 1800, fetch)], day)


def _rate_after(points: List[Tuple[str, float]], day: str) -> Optional[Tuple[float, str]]:
    nxt = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    later = sorted((d, v) for d, v in points if d >= nxt and v is not None)
    return (later[0][1], later[0][0]) if later else None


def _ons(path: str, how: str, day: str) -> Optional[Tuple[float, str]]:
    import requests
    from zoneinfo import ZoneInfo

    def fetch():
        r = requests.get(f"{ONS}/{path}/data", headers=UA, timeout=20)
        r.raise_for_status()
        return r.json()
    d = _cached(f"ons:{path}", 1800, fetch)
    rel = d.get("description", {}).get("releaseDate")
    if not rel:
        return None
    rel_day = datetime.fromisoformat(rel.replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/London")).date().isoformat()
    if rel_day != day:                          # the series' latest release isn't this event's
        return None
    obs = d.get("months") or d.get("quarters") or []
    vals = [float(o["value"]) for o in obs[-3:] if str(o.get("value", "")).strip() not in ("", "x")]
    v = _transform(vals, how)
    return (v, obs[-1]["date"]) if v is not None and obs else None


def _eurostat(query: str, day: str) -> Optional[Tuple[float, str]]:
    """Latest observation of a Eurostat series, when the dataset was updated on the event day
    (or up to two days after — the API stamps the dataset, Luxembourg time)."""
    import requests

    def fetch():
        r = requests.get(f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{query}&lastTimePeriod=2",
                         headers=UA, timeout=30)
        r.raise_for_status()
        return r.json()
    d = _cached(f"eurostat:{query}", 1800, fetch)
    upd = str(d.get("updated") or "")[:10]
    if not upd or not (0 <= (date.fromisoformat(upd) - date.fromisoformat(day)).days <= 2):
        return None
    times = sorted(d["dimension"]["time"]["category"]["index"].items(), key=lambda kv: kv[1])
    vals = d.get("value") or {}
    for period, idx in reversed(times):                  # newest period with a value
        v = vals.get(str(idx))
        if v is not None:
            return float(v), period
    return None


def _ism(kind: str, day: str) -> Optional[Tuple[float, str]]:
    """ISM's headline PMI from its press-release title (distributed via PR Newswire, found through
    Google News' RSS): the report for the month before the event, published within a day of it."""
    import re
    import requests
    from email.utils import parsedate_to_datetime

    def fetch():
        q = f'"{kind} PMI" ISM report on business'
        r = requests.get("https://news.google.com/rss/search", params={"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"},
                         headers=UA, timeout=20)
        r.raise_for_status()
        return re.findall(r"<item><title>(.*?)</title>.*?<pubDate>(.*?)</pubDate>", r.text, re.S)
    ev = date.fromisoformat(day)
    want = (ev.replace(day=1) - timedelta(days=1)).strftime("%B %Y")          # the month reported
    for title, pub in _cached(f"ism:{kind}", 1800, fetch):
        m = re.match(rf"{kind} PMI(?:®)? at ([0-9.]+)%; (\w+ \d{{4}}) ISM", title)
        if not m or m.group(2) != want:
            continue
        try:
            if abs((parsedate_to_datetime(pub).date() - ev).days) > 1:
                continue
        except Exception:
            continue
        return float(m.group(1)), want
    return None


def _boe_rate(code: str, day: str) -> Optional[Tuple[float, str]]:
    import requests
    start = (date.fromisoformat(day) - timedelta(days=10)).strftime("%d/%b/%Y")

    def fetch():
        r = requests.get("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp",
                         params={"csv.x": "yes", "Datefrom": start, "Dateto": "now", "SeriesCodes": code,
                                 "CSVF": "TN", "UsingCodes": "Y", "VPD": "Y", "VFD": "N"}, headers=UA, timeout=20)
        r.raise_for_status()
        out = []
        for row in csv.reader(io.StringIO(r.text)):
            try:
                out.append((datetime.strptime(row[0], "%d %b %Y").date().isoformat(), float(row[1])))
            except (ValueError, IndexError):
                continue
        return out
    pts = _cached(f"boe:{code}:{start}", 1800, fetch)
    # Bank Rate changes take effect on the announcement day
    same = [(d, v) for d, v in pts if d == day]
    return (same[0][1], same[0][0]) if same else None


def _fred_rate(series: str, day: str) -> Optional[Tuple[float, str]]:
    import requests
    start = (date.fromisoformat(day) - timedelta(days=10)).isoformat()

    def fetch():
        r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": series, "cosd": start}, headers=UA, timeout=20)
        r.raise_for_status()
        out = []
        for row in list(csv.reader(io.StringIO(r.text)))[1:]:
            try:
                out.append((row[0], float(row[1])))
            except (ValueError, IndexError):
                continue
        return out
    return _rate_after(_cached(f"fredcsv:{series}:{start}", 1800, fetch), day)


def _umich(day: str) -> Optional[Tuple[float, str]]:
    """Final (revised) sentiment for the event's month, from UMich's own data file."""
    import requests

    def fetch():
        r = requests.get("https://www.sca.isr.umich.edu/files/tbmics.csv", headers=UA, timeout=20)
        r.raise_for_status()
        return list(csv.reader(io.StringIO(r.text)))
    d = date.fromisoformat(day)
    month = d.strftime("%B")
    for row in _cached("umich:tbmics", 3600, fetch):
        if len(row) >= 3 and row[0] == month and row[1] == str(d.year):
            try:
                return float(row[2]), f"{d.year}-{d.month:02d}"
            except ValueError:
                return None
    return None


def actual_for(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    src = SOURCES.get((rec.get("country"), rec.get("title")))
    if not src:
        return None
    kind, ident, how, unit = src
    day = str(rec.get("date"))[:10]
    if day > date.today().isoformat():
        return None
    try:
        got = {"statcan": lambda: _statcan(ident, how, day), "statcan_rate": lambda: _statcan_rate(ident, day),
               "ons": lambda: _ons(ident, how, day), "boe_rate": lambda: _boe_rate(ident, day),
               "eurostat": lambda: _eurostat(ident, day), "ism": lambda: _ism(ident, day),
               "fred_rate": lambda: _fred_rate(ident, day), "umich": lambda: _umich(day)}[kind]()
    except Exception as e:
        logger.debug("[eco] %s %s: %s", rec.get("country"), rec.get("title"), e)
        return None
    if not got:
        return None
    return {"actual": round(got[0], 3), "unit": unit, "period": got[1], "series": f"{kind}:{ident}" if ident else kind}
