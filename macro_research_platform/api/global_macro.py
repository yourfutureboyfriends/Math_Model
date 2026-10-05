"""
Developed-markets macro monitor: Americas, Europe and Asia-Pacific on one page, from
official sources, every value dated and graded against its release calendar.

Sources (all free, no keys):
  * BIS WS_CBPOL — daily central-bank policy rates (Fed, ECB, BoE, SNB, Riksbank, Norges,
    BoJ, RBA, RBNZ, BoC, BoK, HKMA)
  * OECD SDMX — CPI (COICOP-2018 and 1999 datasets), harmonised unemployment, quarterly
    real GDP growth, monthly long-term (10Y) and 3-month interest rates
  * Eurostat — euro-area GDP (not in the OECD growth table)
  * FRED — US CPI / 10Y / 3M (daily, consistent with the rest of the platform)
  * Yahoo — equity indices and FX (FX re-dated to its NY session, api/market_dates.py)

Why not FRED for everything: the OECD Main Economic Indicators mirrored on FRED stopped
updating in early 2025 (UK/Canada CPI end 2025-03, Japan absent) — the old regional panel
showed 18-month-old values as current.

Results are cached on disk (6h); if a source fails, the last good copy is used and marked.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from api.calculations.global_macro import (
    currency_return, in_usd, latest_by_area, macro_quadrant, period_date, period_return, policy_stats,
    recent_moves)

logger = logging.getLogger(__name__)

OECD = "https://sdmx.oecd.org/public/rest/data"
BIS = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0"
EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
_CSV = {"Accept": "application/vnd.sdmx.data+csv; charset=utf-8"}
_TTL = 6 * 3600

# code, name, region, OECD code(s), BIS policy code, central bank, inflation target (%),
# equity index, FX ticker, FX quoted as USD/xxx?
ECONOMIES: List[Dict[str, Any]] = [
    {"code": "US", "name": "United States", "region": "Americas", "oecd": "USA", "bis": "US",
     "cb": "Fed", "target": 2.0, "index": "^GSPC", "index_name": "S&P 500", "fx": None, "ccy": "USD"},
    {"code": "CA", "name": "Canada", "region": "Americas", "oecd": "CAN", "bis": "CA",
     "cb": "BoC", "target": 2.0, "index": "^GSPTSE", "index_name": "S&P/TSX", "fx": "USDCAD=X", "usd_base": True, "ccy": "CAD"},
    {"code": "EA", "name": "Euro area", "region": "Europe", "oecd": "EA", "oecd_fin": "EA20", "bis": "XM",
     "cb": "ECB", "target": 2.0, "index": "^STOXX50E", "index_name": "Euro Stoxx 50", "fx": "EURUSD=X", "usd_base": False, "ccy": "EUR"},
    {"code": "DE", "name": "Germany", "region": "Europe", "oecd": "DEU", "bis": "XM", "cb": "ECB", "target": 2.0,
     "index": "^GDAXI", "index_name": "DAX", "fx": "EURUSD=X", "usd_base": False, "ccy": "EUR"},
    {"code": "FR", "name": "France", "region": "Europe", "oecd": "FRA", "bis": "XM", "cb": "ECB", "target": 2.0,
     "index": "^FCHI", "index_name": "CAC 40", "fx": "EURUSD=X", "usd_base": False, "ccy": "EUR"},
    {"code": "IT", "name": "Italy", "region": "Europe", "oecd": "ITA", "bis": "XM", "cb": "ECB", "target": 2.0,
     "index": "FTSEMIB.MI", "index_name": "FTSE MIB", "fx": "EURUSD=X", "usd_base": False, "ccy": "EUR"},
    {"code": "ES", "name": "Spain", "region": "Europe", "oecd": "ESP", "bis": "XM", "cb": "ECB", "target": 2.0,
     "index": "^IBEX", "index_name": "IBEX 35", "fx": "EURUSD=X", "usd_base": False, "ccy": "EUR"},
    {"code": "NL", "name": "Netherlands", "region": "Europe", "oecd": "NLD", "bis": "XM", "cb": "ECB", "target": 2.0,
     "index": "^AEX", "index_name": "AEX", "fx": "EURUSD=X", "usd_base": False, "ccy": "EUR"},
    {"code": "GB", "name": "United Kingdom", "region": "Europe", "oecd": "GBR", "bis": "GB",
     "cb": "BoE", "target": 2.0, "index": "^FTSE", "index_name": "FTSE 100", "fx": "GBPUSD=X", "usd_base": False, "ccy": "GBP"},
    {"code": "CH", "name": "Switzerland", "region": "Europe", "oecd": "CHE", "bis": "CH",
     "cb": "SNB", "target": 1.0, "index": "^SSMI", "index_name": "SMI", "fx": "USDCHF=X", "usd_base": True, "ccy": "CHF"},
    {"code": "SE", "name": "Sweden", "region": "Europe", "oecd": "SWE", "bis": "SE",
     "cb": "Riksbank", "target": 2.0, "index": "^OMX", "index_name": "OMXS30", "fx": "USDSEK=X", "usd_base": True, "ccy": "SEK"},
    {"code": "NO", "name": "Norway", "region": "Europe", "oecd": "NOR", "bis": "NO",
     "cb": "Norges Bank", "target": 2.0, "index": "OSEBX.OL", "index_name": "OSEBX", "fx": "USDNOK=X", "usd_base": True, "ccy": "NOK"},
    {"code": "JP", "name": "Japan", "region": "Asia-Pacific", "oecd": "JPN", "bis": "JP",
     "cb": "BoJ", "target": 2.0, "index": "^N225", "index_name": "Nikkei 225", "fx": "USDJPY=X", "usd_base": True, "ccy": "JPY"},
    {"code": "AU", "name": "Australia", "region": "Asia-Pacific", "oecd": "AUS", "bis": "AU",
     "cb": "RBA", "target": 2.5, "index": "^AXJO", "index_name": "ASX 200", "fx": "AUDUSD=X", "usd_base": False, "ccy": "AUD"},
    {"code": "NZ", "name": "New Zealand", "region": "Asia-Pacific", "oecd": "NZL", "bis": "NZ",
     "cb": "RBNZ", "target": 2.0, "index": "^NZ50", "index_name": "NZX 50", "fx": "NZDUSD=X", "usd_base": False, "ccy": "NZD"},
    {"code": "KR", "name": "South Korea", "region": "Asia-Pacific", "oecd": "KOR", "bis": "KR",
     "cb": "BoK", "target": 2.0, "index": "^KS11", "index_name": "KOSPI", "fx": "USDKRW=X", "usd_base": True, "ccy": "KRW"},
    {"code": "HK", "name": "Hong Kong", "region": "Asia-Pacific", "oecd": None, "bis": "HK",
     "cb": "HKMA", "target": None, "index": "^HSI", "index_name": "Hang Seng", "fx": "USDHKD=X", "usd_base": True, "ccy": "HKD",
     "note": "USD peg: HKMA base rate tracks the Fed; no OECD macro coverage"},
    {"code": "SG", "name": "Singapore", "region": "Asia-Pacific", "oecd": None, "bis": None,
     "cb": "MAS", "target": None, "index": "^STI", "index_name": "STI", "fx": "USDSGD=X", "usd_base": True, "ccy": "SGD",
     "note": "MAS steers the exchange rate, not a policy rate; no OECD macro coverage"},
]
REGIONS = ("Americas", "Europe", "Asia-Pacific")
# Long-run potential growth (% y/y), used only to label a growth quadrant. Round, consensus-
# style figures — an assumption shown with the result, not a measured value.
TREND_GROWTH = {"US": 2.0, "CA": 1.8, "EA": 1.2, "DE": 1.0, "FR": 1.1, "IT": 0.7, "ES": 1.7, "NL": 1.4,
                "GB": 1.4, "CH": 1.6, "SE": 1.9, "NO": 1.6, "JP": 0.6, "AU": 2.4, "NZ": 2.2, "KR": 2.0}


# ── HTTP + cache ─────────────────────────────────────────────────────────────
def _get(url: str, params: Optional[dict] = None, headers: Optional[dict] = None, timeout: float = 60):
    import requests
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r


def _cached(name: str, fetch, ttl: float = _TTL) -> Tuple[Any, Dict]:
    """(payload, meta) — fresh from disk cache, else fetched, else the last good copy."""
    from api.handlers.macro_inputs import _disk_load, _disk_save
    fresh = _disk_load(f"gm_{name}", max_age=ttl)
    if fresh is not None:
        return fresh.get("data"), {"source_status": "ok", "fetched_at": fresh.get("fetched_at")}
    try:
        data = fetch()
        _disk_save(f"gm_{name}", {"data": data, "fetched_at": time.time()})
        return data, {"source_status": "ok", "fetched_at": time.time()}
    except Exception as e:
        logger.warning("[global_macro] %s fetch failed: %s", name, e)
        stale = _disk_load(f"gm_{name}")
        if stale is not None:
            return stale.get("data"), {"source_status": "stale-cache", "fetched_at": stale.get("fetched_at"),
                                       "error": str(e)[:120]}
        return None, {"source_status": "unavailable", "error": str(e)[:120]}


def _oecd(flow: str, key: str, start: str) -> List[Dict]:
    r = _get(f"{OECD}/{flow}/{key}", {"startPeriod": start, "dimensionAtObservation": "AllDimensions"},
             headers=_CSV, timeout=120)
    return list(csv.DictReader(io.StringIO(r.text)))


def _bis_policy(codes: List[str], start: str) -> Dict[str, List[Tuple[str, float]]]:
    r = _get(f"{BIS}/D.{'+'.join(codes)}", {"startPeriod": start, "format": "csv"}, timeout=120)
    out: Dict[str, List[Tuple[str, float]]] = {}
    for row in csv.DictReader(io.StringIO(r.text)):
        try:
            v = float(row["OBS_VALUE"])
        except (KeyError, ValueError):
            continue
        if v == v:                                   # BIS sends literal NaN for some days
            out.setdefault(row["REF_AREA"], []).append((row["TIME_PERIOD"], v))
    return out


def _eurostat(dataset: str, params: Dict[str, str]) -> Dict[str, float]:
    r = _get(f"{EUROSTAT}/{dataset}", {**params, "format": "JSON", "lang": "EN"})
    j = r.json()
    idx = j.get("dimension", {}).get("time", {}).get("category", {}).get("index", {})
    inv = {v: k for k, v in idx.items()}
    return {inv[int(k)]: float(v) for k, v in (j.get("value") or {}).items() if int(k) in inv}


def _areas(key: str = "oecd") -> str:
    return "+".join(sorted({e.get(key) or e.get("oecd") for e in ECONOMIES if e.get("oecd")}))


# ── Fetch every source (blocking; run in a thread) ───────────────────────────
def _fetch_all(today: date) -> Dict[str, Any]:
    y2 = (today - timedelta(days=760)).isoformat()
    m_start = f"{today.year - 1}-{today.month:02d}"
    q_start = f"{today.year - 2}-Q1"
    areas, areas_fin = _areas(), _areas("oecd_fin")
    jobs = {
        "policy": lambda: _bis_policy(sorted({e["bis"] for e in ECONOMIES if e["bis"]}), y2),
        "cpi18": lambda: _oecd("OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0",
                               f"{areas}.M+Q.N+HICP.CPI.PA...GY", m_start),
        "cpi99": lambda: _oecd("OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0",
                               f"{areas}.M+Q.N.CPI.PA._T.N.GY", m_start),
        "unemp": lambda: _oecd("OECD.SDD.TPS,DSD_LFS@DF_IALFS_UNE_M,1.0",
                               f"{areas}.UNE_LF_M.PT_LF_SUB._Z.Y._T.Y_GE15._Z.M+Q", m_start),
        "gdp": lambda: _oecd("OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA_EXPENDITURE_GROWTH_OECD,1.1",
                             f"Q..{areas}...B1GQ......GY+G1.", q_start),
        "rates": lambda: _oecd("OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0", f"{areas_fin}.M.IRLT+IR3TIB.PA.....", m_start),
        "ea_gdp": lambda: {"GY": _eurostat("namq_10_gdp", {"geo": "EA20", "unit": "CLV_PCH_SM", "s_adj": "SCA",
                                                            "na_item": "B1GQ", "sinceTimePeriod": q_start}),
                           "G1": _eurostat("namq_10_gdp", {"geo": "EA20", "unit": "CLV_PCH_PRE", "s_adj": "SCA",
                                                            "na_item": "B1GQ", "sinceTimePeriod": q_start})},
    }
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {k: pool.submit(_cached, k, fn) for k, fn in jobs.items()}
        return {k: f.result() for k, f in futures.items()}


# ── Release-calendar grading for each value ──────────────────────────────────
# (frequency, publication lag after the period ends, grace) for the international sources.
_CAL = {"policy": ("D", 3, 5), "cpi": ("M", 20, 25), "cpi_q": ("Q", 30, 20), "unemp": ("M", 35, 30),
        "unemp_q": ("Q", 60, 30), "gdp": ("Q", 60, 30), "rate_m": ("M", 10, 20)}


def _grade(kind: str, period: Optional[str], today: date) -> Dict:
    from api.release_calendar import SeriesSpec, assess
    if not period:
        return {"state": "UNAVAILABLE", "status": "UNKNOWN"}
    freq, lag, grace = _CAL[kind]
    spec = SeriesSpec(kind, kind, kind, freq, lag, grace, "Global")
    a = assess(spec, date.fromisoformat(period_date(period)), today)
    return {"state": a["state"], "status": a["status"], "next_expected_release": a["next_expected_release"]}


def _cell(value: Optional[float], period: Optional[str], kind: str, today: date, source: str,
          digits: int = 2, **extra) -> Dict:
    return {"value": None if value is None else round(value, digits), "period": period, "source": source,
            **_grade(kind, period, today), **extra}


# ── Build the monitor ────────────────────────────────────────────────────────
def _cpi_index(rows18, rows99):
    prefer = {e["oecd"]: [("METHODOLOGY", "N"), ("METHODOLOGY", "HICP")] for e in ECONOMIES if e.get("oecd")}
    tot = [r for r in (rows18 or []) if r.get("EXPENDITURE") in ("_T", "CP00", "TOTAL")]
    out = latest_by_area(tot, prefer=prefer)
    for area, pv in latest_by_area(rows99 or []).items():        # GBR / AUS / KOR / NZL / USA
        if area not in out or period_date(pv[0]) > period_date(out[area][0]):
            out[area] = pv
    return out


async def build_global_macro(today: Optional[date] = None) -> Dict[str, Any]:
    from api.handlers.macro_inputs import load_fred_series
    from api.handlers.market_handler import _fetch_dated_closes_literal

    today = today or date.today()
    raw = await asyncio.to_thread(_fetch_all, today)
    data = {k: v[0] for k, v in raw.items()}
    sources = {k: v[1] for k, v in raw.items()}

    fred = await load_fred_series(["CPIAUCSL", "DGS10", "DGS3MO", "UNRATE", "A191RL1Q225SBEA"])
    tickers = sorted({e["index"] for e in ECONOMIES} | {e["fx"] for e in ECONOMIES if e["fx"]})
    closes = dict(zip(tickers, await asyncio.gather(*[_fetch_dated_closes_literal(t) for t in tickers])))

    policy_series = data["policy"] or {}
    cpi = _cpi_index(data["cpi18"], data["cpi99"])
    unemp = latest_by_area(data["unemp"] or [])
    gdp_rows = data["gdp"] or []
    gdp_yy = latest_by_area([r for r in gdp_rows if r.get("TRANSFORMATION") == "GY"])
    gdp_qq = latest_by_area([r for r in gdp_rows if r.get("TRANSFORMATION") == "G1"])
    rate_rows = data["rates"] or []
    ten = latest_by_area([r for r in rate_rows if r.get("MEASURE") == "IRLT"])
    three = latest_by_area([r for r in rate_rows if r.get("MEASURE") == "IR3TIB"])
    ea = data["ea_gdp"] or {}

    us_policy = policy_stats(policy_series.get("US", []), today)
    ytd_start = f"{today.year - 1}-12-31"
    m1_start = (today - timedelta(days=30)).isoformat()
    rows = []
    for e in ECONOMIES:
        o, of = e.get("oecd"), e.get("oecd_fin") or e.get("oecd")
        row: Dict[str, Any] = {k: e.get(k) for k in ("code", "name", "region", "cb", "target", "ccy", "note")}

        # Policy rate (BIS daily)
        pol = policy_stats(policy_series.get(e["bis"], []), today) if e["bis"] else {"available": False}
        row["policy"] = ({**pol, **_grade("policy", pol["as_of"], today), "source": "BIS"} if pol.get("available")
                         else {"available": False, "reason": e.get("note") or "no policy-rate series"})

        # CPI y/y
        if e["code"] == "US" and fred.get("CPIAUCSL"):
            s = fred["CPIAUCSL"]
            # Match the same month a year earlier BY DATE: FRED has no Oct-2025 CPI (not
            # published during the 2025 shutdown), so counting back 12 rows spans 13 months.
            last = s.latest_date
            prior = f"{int(last[:4]) - 1}{last[4:]}"
            base = dict(zip(s.dates, s.values)).get(prior)
            yoy = (s.latest / base - 1) * 100 if base else None
            row["cpi"] = _cell(yoy, s.latest_date[:7], "cpi", today, "FRED CPIAUCSL (SA)")
        elif o and o in cpi:
            p, v = cpi[o]
            row["cpi"] = _cell(v, p, "cpi_q" if "-Q" in p else "cpi", today, "OECD")
        else:
            row["cpi"] = _cell(None, None, "cpi", today, "—")

        # Unemployment
        if e["code"] == "US" and fred.get("UNRATE"):
            s_ = fred["UNRATE"]
            row["unemployment"] = _cell(s_.latest, s_.latest_date[:7], "unemp", today, "FRED UNRATE", 1)
        elif o and o in unemp:
            p, v = unemp[o]
            row["unemployment"] = _cell(v, p, "unemp_q" if "-Q" in p else "unemp", today, "OECD harmonised", 1)
        else:
            row["unemployment"] = _cell(None, None, "unemp", today, "—")

        # Real GDP growth
        if e["code"] == "EA" and ea.get("GY"):
            p = max(ea["GY"])
            row["gdp"] = _cell(ea["GY"][p], p, "gdp", today, "Eurostat", 1, qoq=ea.get("G1", {}).get(p))
        elif o and o in gdp_yy:
            p, v = gdp_yy[o]
            row["gdp"] = _cell(v, p, "gdp", today, "OECD", 1, qoq=round(gdp_qq[o][1], 2) if o in gdp_qq else None)
        else:
            row["gdp"] = _cell(None, None, "gdp", today, "—")

        # 10Y and 3M (monthly averages, comparable across countries); US also live daily.
        row["ten_year"] = _cell(ten[of][1], ten[of][0], "rate_m", today, "OECD monthly avg") if of in ten \
            else _cell(None, None, "rate_m", today, "—")
        row["three_month"] = _cell(three[of][1], three[of][0], "rate_m", today, "OECD monthly avg") if of in three \
            else _cell(None, None, "rate_m", today, "—")
        if e["code"] == "US" and fred.get("DGS10"):
            row["ten_year_live"] = {"value": fred["DGS10"].latest, "date": fred["DGS10"].latest_date, "source": "FRED DGS10"}

        # Derived
        pv, cv = row["policy"].get("rate"), row["cpi"]["value"]
        row["real_policy_rate"] = None if pv is None or cv is None else round(pv - cv, 2)
        row["policy_vs_fed_bp"] = (None if pv is None or not us_policy.get("available")
                                   else round((pv - us_policy["rate"]) * 100))
        row["inflation_gap"] = None if cv is None or e.get("target") is None else round(cv - e["target"], 2)
        us_ten = ten.get("USA")
        row["ten_year_vs_us_bp"] = (round((ten[of][1] - us_ten[1]) * 100)
                                    if of in ten and us_ten and ten[of][0] == us_ten[0] and e["code"] != "US" else None)
        row["trend_growth"] = TREND_GROWTH.get(e["code"])
        row["quadrant"] = macro_quadrant(row["gdp"]["value"], cv, row["trend_growth"], e.get("target"))
        row["curve_bp"] = (round((ten[of][1] - three[of][1]) * 100)
                           if of in ten and of in three and ten[of][0] == three[of][0] else None)

        # Markets: local and USD returns
        eq, fx = closes.get(e["index"]) or {}, closes.get(e["fx"]) or {} if e["fx"] else {}
        ccy_1m = currency_return(fx, m1_start, e.get("usd_base", False)) if e["fx"] else 0.0
        ccy_ytd = currency_return(fx, ytd_start, e.get("usd_base", False)) if e["fx"] else 0.0
        eq_1m, eq_ytd = period_return(eq, m1_start), period_return(eq, ytd_start)
        days = sorted(eq)
        row["equity"] = {
            "index": e["index_name"], "ticker": e["index"],
            "level": round(eq[days[-1]], 2) if days else None, "as_of": days[-1] if days else None,
            "change_1d": round((eq[days[-1]] / eq[days[-2]] - 1) * 100, 2) if len(days) > 1 else None,
            "return_1m": _pct(eq_1m), "return_ytd": _pct(eq_ytd),
            "return_ytd_usd": _pct(in_usd(eq_ytd, ccy_ytd)),
        }
        fdays = sorted(fx)
        row["fx"] = None if not e["fx"] else {
            "pair": e["fx"].replace("=X", ""), "spot": round(fx[fdays[-1]], 4) if fdays else None,
            "as_of": fdays[-1] if fdays else None,
            "ccy_vs_usd_1m": _pct(ccy_1m), "ccy_vs_usd_ytd": _pct(ccy_ytd),
        }
        rows.append(row)

    moves = recent_moves({e["cb"]: policy_series.get(e["bis"], []) for e in ECONOMIES
                          if e["bis"] and e["code"] in ("US", "EA", "GB", "CH", "SE", "NO", "JP", "AU", "NZ", "CA", "KR", "HK")},
                         since=(today - timedelta(days=120)).isoformat())
    return {
        "available": any(r["policy"].get("available") for r in rows),
        "as_of": today.isoformat(),
        "regions": list(REGIONS),
        "economies": rows,
        "recent_policy_moves": moves,
        "sources": sources,
        "notes": ["10Y/3M are OECD monthly averages so cross-country spreads compare the same month; "
                  "the US latest daily 10Y close is shown separately.",
                  "Quadrant = real GDP growth vs an assumed trend rate (shown) and CPI vs the "
                  "central bank's target (+0.5pp band).",
                  "Equity USD returns combine the local index with the currency's move vs USD.",
                  "Each value is graded against its release calendar (CURRENT / DUE / LATE / MISSING)."],
    }


def _pct(x: Optional[float]) -> Optional[float]:
    return None if x is None else round(x * 100, 2)
