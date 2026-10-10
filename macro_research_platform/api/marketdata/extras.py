"""
More terminal functions on free official data:

  WIRP  Fed rate-move probabilities from 30-day fed funds futures (CBOT ZQ, Yahoo) and the
        FOMC calendar (federalreserve.gov) — the CME FedWatch method.
  AUCT  US Treasury auction results (TreasuryDirect): yield, bid-to-cover, who bought.
  EIA   Weekly US petroleum stocks (EIA WPSR tables) and natural-gas storage (EIA WNGSR).
  WETR  Heating / cooling degree days: 16-day forecast vs the 10-year normal for major
        US demand centres (Open-Meteo forecast and ERA5 archive) — what drives gas and power.
  INSD  Insider transactions from SEC Form 4 filings (the filings themselves, parsed).
  13F   Hedge-fund and investor holdings from SEC 13F-HR filings, quarter-on-quarter changes,
        CUSIPs mapped to tickers via OpenFIGI.
"""
from __future__ import annotations

import concurrent.futures as cf
import csv
import io
import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from api.marketdata.core import NotFound, Upstream, _cached, _f

logger = logging.getLogger(__name__)
BROWSER = {"User-Agent": "Mozilla/5.0 (macro research terminal)"}


def _sec_get(url: str, timeout: int = 30):
    import requests
    from api.providers.sec_edgar import USER_AGENT
    r = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}, timeout=timeout)
    if r.status_code == 403:
        raise Upstream("SEC refused the request — set SEC_USER_AGENT to 'Your Name your@email' (SEC fair-access rule).")
    r.raise_for_status()
    return r


# ── WIRP ─────────────────────────────────────────────────────────────────────
MONTH_CODES = "FGHJKMNQUVXZ"


def _fomc_meetings() -> List[date]:
    """Scheduled FOMC decision days (second day of each meeting) from the Fed's calendar."""
    def fetch():
        import requests
        t = requests.get("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", headers=BROWSER, timeout=30).text
        out: List[date] = []
        for block in re.split(r'<div class="panel panel-default">', t):
            y = re.search(r"(\d{4}) FOMC Meetings", block)
            if not y:
                continue
            year = int(y.group(1))
            for mon, days in re.findall(r'fomc-meeting__month[^>]*><strong>([A-Za-z/]+)</strong>.*?fomc-meeting__date[^>]*>([0-9\-*]+)', block, re.S):
                last_month = mon.split("/")[-1]
                last_day = int(re.findall(r"\d+", days)[-1])
                try:
                    out.append(datetime.strptime(f"{last_month[:3]} {last_day} {year}", "%b %d %Y").date())
                except ValueError:
                    continue
        return sorted(set(out))
    return _cached("fomc:dates", 86400, fetch)


def wirp() -> Dict[str, Any]:
    def fetch():
        import calendar
        import yfinance as yf
        from api.providers.fred_provider import FREDProvider

        def _fred_last(sid):
            obs = [o for o in (FREDProvider().fetch_series(sid).data or []) if o.value is not None]
            return obs[-1].value if obs else None
        today = date.today()
        months = [(today.year + (today.month - 1 + i) // 12, (today.month - 1 + i) % 12 + 1) for i in range(0, 16)]
        syms = {f"ZQ{MONTH_CODES[m - 1]}{str(y)[2:]}.CBT": (y, m) for y, m in months}
        df = yf.download(list(syms), period="5d", progress=False, group_by="ticker", auto_adjust=False)
        implied: Dict[Tuple[int, int], float] = {}
        for s, ym in syms.items():
            try:
                c = df[s]["Close"].dropna()
                if len(c):
                    implied[ym] = 100 - float(c.iloc[-1])
            except Exception:
                continue
        if len(implied) < 3:
            raise Upstream("Fed funds futures unavailable.")
        effr = _fred_last("EFFR") or _fred_last("DFF")
        # the published target range (FRED); estimated from EFFR only if those series are unavailable
        lower, upper = _fred_last("DFEDTARL"), _fred_last("DFEDTARU")
        if lower is None or upper is None:
            lower = round((effr - 0.08) * 4) / 4 if effr else None
            upper = lower + 0.25 if lower is not None else None
        meetings = [d for d in _fomc_meetings() if d >= today]
        rows, r_pre = [], effr
        for d in meetings:
            ym = (d.year, d.month)
            if ym not in implied or r_pre is None:
                continue
            n = calendar.monthrange(d.year, d.month)[1]
            days_after = n - d.day                       # the new rate applies from the day after the decision
            if days_after >= 7:
                r_post = (implied[ym] * n - r_pre * (n - days_after)) / days_after
            else:                                        # meeting late in the month: use next month's contract
                nxt = (d.year + d.month // 12, d.month % 12 + 1)
                if nxt not in implied:
                    continue
                r_post = implied[nxt]
            move = r_post - r_pre
            steps = move / 0.25
            lo_steps = int(steps // 1) if steps >= 0 else -int((-steps) // 1) - (0 if float(steps).is_integer() else 1)
            frac = steps - lo_steps
            probs = {round(lo_steps * 25): 1 - frac, round((lo_steps + 1) * 25): frac} if frac > 1e-9 else {round(lo_steps * 25): 1.0}
            rows.append({"meeting": str(d), "implied_rate": r_post, "change_bp": move * 100, "cumulative_bp": (r_post - effr) * 100,
                         "probabilities": {f"{k:+d}bp": round(v, 3) for k, v in sorted(probs.items())},
                         "p_cut": round(sum(v for k, v in probs.items() if k < 0), 3), "p_hike": round(sum(v for k, v in probs.items() if k > 0), 3)})
            r_pre = r_post
        path = [{"month": f"{y}-{m:02d}", "implied_rate": v} for (y, m), v in sorted(implied.items())]
        return {"effective_rate": effr, "target_lower": lower, "target_upper": upper,
                "meetings": rows, "path": path, "as_of": str(today),
                "method": "CME FedWatch method: each month's fed funds future prices the average effective rate for that month; "
                          "the rate after an FOMC decision is backed out from the days before and after the meeting, chained "
                          "meeting to meeting. Probabilities split the implied move between the two nearest 25bp outcomes.",
                "source": "CBOT 30-day fed funds futures (Yahoo Finance), FOMC calendar (federalreserve.gov), EFFR (FRED)"}
    return _cached("wirp", 900, fetch)


# ── AUCT ─────────────────────────────────────────────────────────────────────
def auctions(kind: str = "Note", limit: int = 30) -> Dict[str, Any]:
    if kind not in ("Bill", "Note", "Bond", "TIPS", "FRN"):
        raise NotFound("kind: Bill, Note, Bond, TIPS or FRN")

    def fetch():
        import requests
        # fetch well beyond what's shown: each term's "vs average" needs its own previous auctions
        r = requests.get("https://www.treasurydirect.gov/TA_WS/securities/auctioned", params={"format": "json", "type": kind, "pagesize": max(150, limit)},
                         headers=BROWSER, timeout=30)
        r.raise_for_status()
        out = []
        for a in r.json():
            tot = _f(a.get("totalAccepted")) or 0
            share = lambda k: (_f(a.get(k)) or 0) / tot if tot else None
            out.append({"cusip": a.get("cusip"), "term": a.get("securityTerm"), "auction_date": str(a.get("auctionDate"))[:10],
                        "issue_date": str(a.get("issueDate"))[:10], "maturity": str(a.get("maturityDate"))[:10],
                        "high_yield": _f(a.get("highYield")) or _f(a.get("highDiscountRate")) or _f(a.get("highInvestmentRate")),
                        "bid_to_cover": _f(a.get("bidToCoverRatio")), "size_bn": (_f(a.get("offeringAmount")) or 0) / 1e9,
                        "indirect": share("indirectBidderAccepted"), "direct": share("directBidderAccepted"),
                        "dealers": share("primaryDealerAccepted"), "reopening": a.get("reopening") == "Yes"})
        # each auction vs the average of the previous ones of the same term
        for i, a in enumerate(out):
            same = [b for b in out[i + 1:] if b["term"] == a["term"] and b["bid_to_cover"]][:6]
            if same and a["bid_to_cover"]:
                a["btc_vs_avg"] = a["bid_to_cover"] - sum(b["bid_to_cover"] for b in same) / len(same)
                ind = [b["indirect"] for b in same if b["indirect"] is not None]
                a["indirect_vs_avg"] = (a["indirect"] - sum(ind) / len(ind)) if ind and a["indirect"] is not None else None
        return {"kind": kind, "auctions": out[:limit], "source": "TreasuryDirect auction results",
                "note": "Bid-to-cover above its recent average and a higher indirect (foreign and investor) share = stronger demand; "
                        "a heavy primary-dealer share = weaker. The 'tail' needs the when-issued yield, which isn't free."}
    return _cached(f"auct:{kind}:{limit}", 1800, fetch)


# ── EIA ──────────────────────────────────────────────────────────────────────
def energy() -> Dict[str, Any]:
    def fetch():
        import requests

        def table(n: str) -> List[List[str]]:
            r = requests.get(f"https://ir.eia.gov/wpsr/{n}.csv", headers=BROWSER, timeout=30)
            r.raise_for_status()
            return list(csv.reader(io.StringIO(r.content.decode("utf-8-sig", "replace"))))
        t1, t4 = table("table1"), table("table4")
        hdr = t1[0]
        keep = {"Crude Oil": "Crude oil incl. SPR", "Commercial (Excluding SPR)": "Commercial crude", "Strategic Petroleum Reserve (SPR)": "Strategic reserve (SPR)",
                "Total Motor Gasoline": "Gasoline", "Distillate Fuel Oil": "Distillates (diesel, heating oil)", "Kerosene-Type Jet Fuel": "Jet fuel",
                "Propane/Propylene": "Propane", "Total Stocks (Including SPR)": "All petroleum incl. SPR"}
        n = lambda x: _f(str(x).replace(",", "")) if x is not None else None      # "1,520.383" for totals over 1bn bbl
        petro = []
        for row in t1[1:]:
            if row and row[0] in keep:
                petro.append({"item": keep[row[0]], "latest": n(row[1]), "week_ago": n(row[2]), "change": n(row[3]),
                              "year_ago": n(row[5]), "vs_year_ago_pct": n(row[7])})
        cushing = next(({"latest": n(r[1]), "change": n(r[3]), "year_ago": n(r[4])} for r in t4 if r and r[0] == "Cushing"), None)
        g = requests.get("https://ir.eia.gov/ngs/wngsr.json", headers=BROWSER, timeout=30, allow_redirects=True)
        g.raise_for_status()
        gas = json.loads(g.content.decode("utf-8-sig"))
        regions = []
        for s in gas.get("series", []):
            c = s.get("calculated", {})
            vals = s.get("data") or []
            regions.append({"region": s.get("name"), "latest": _f(vals[0][1]) if vals else None, "change": _f(c.get("net_change")),
                            "vs_year_ago_pct": _f(c.get("pct-change_yrago")), "five_year_avg": _f(c.get("5yr-avg")),
                            "vs_5yr_pct": None})
            last, avg5 = regions[-1]["latest"], regions[-1]["five_year_avg"]
            regions[-1]["vs_5yr_pct"] = (last / avg5 - 1) * 100 if last and avg5 else None
        return {"week": hdr[1], "petroleum": petro, "cushing": cushing, "units": "million barrels",
                "gas_week": gas.get("current_week"), "gas_release": gas.get("release_date"), "gas": regions, "gas_units": "billion cubic feet",
                "source": "EIA Weekly Petroleum Status Report (tables 1, 4) and Weekly Natural Gas Storage Report"}
    return _cached("eia", 3 * 3600, fetch)


# ── WETR ─────────────────────────────────────────────────────────────────────
# Population-weighted proxy for US gas/power demand (weights ≈ metro population, millions)
DEMAND_CITIES = {"New York": (40.71, -74.01, 19.5), "Chicago": (41.88, -87.63, 9.4), "Philadelphia": (39.95, -75.17, 6.2),
                 "Boston": (42.36, -71.06, 4.9), "Detroit": (42.33, -83.05, 4.3), "Minneapolis": (44.98, -93.27, 3.7),
                 "Washington DC": (38.9, -77.04, 6.3), "Atlanta": (33.75, -84.39, 6.2), "Dallas": (32.78, -96.8, 7.9),
                 "Houston": (29.76, -95.37, 7.3), "Los Angeles": (34.05, -118.24, 12.8), "Phoenix": (33.45, -112.07, 5.0)}


def weather() -> Dict[str, Any]:
    def fetch():
        import requests
        today = date.today()
        lat = ",".join(str(v[0]) for v in DEMAND_CITIES.values())
        lon = ",".join(str(v[1]) for v in DEMAND_CITIES.values())
        fc = requests.get("https://api.open-meteo.com/v1/forecast", params={"latitude": lat, "longitude": lon, "daily": "temperature_2m_mean",
                          "temperature_unit": "fahrenheit", "forecast_days": 16, "timezone": "America/New_York"}, headers=BROWSER, timeout=30).json()
        start = date(today.year - 10, 1, 1)
        ar = requests.get("https://archive-api.open-meteo.com/v1/archive", params={"latitude": lat, "longitude": lon, "daily": "temperature_2m_mean",
                          "temperature_unit": "fahrenheit", "start_date": str(start), "end_date": str(date(today.year - 1, 12, 31)),
                          "timezone": "America/New_York"}, headers=BROWSER, timeout=60).json()
        fcl = fc if isinstance(fc, list) else [fc]
        arl = ar if isinstance(ar, list) else [ar]
        names = list(DEMAND_CITIES)
        days = fcl[0]["daily"]["time"]
        tot_w = sum(v[2] for v in DEMAND_CITIES.values())
        agg = [{"date": d, "hdd": 0.0, "cdd": 0.0, "hdd_normal": 0.0, "cdd_normal": 0.0} for d in days]
        cities = []
        for i, name in enumerate(names):
            w = DEMAND_CITIES[name][2] / tot_w
            temps = fcl[i]["daily"]["temperature_2m_mean"]
            hist: Dict[str, List[float]] = {}
            for t, v in zip(arl[i]["daily"]["time"], arl[i]["daily"]["temperature_2m_mean"]):
                if v is not None:
                    hist.setdefault(t[5:], []).append(v)
            c_h = c_hn = 0.0
            for k, (d, t) in enumerate(zip(days, temps)):
                if t is None:
                    continue
                normal = sum(hist.get(d[5:], [t])) / len(hist.get(d[5:], [t]))
                h, c, hn, cn = max(0, 65 - t), max(0, t - 65), max(0, 65 - normal), max(0, normal - 65)
                agg[k]["hdd"] += w * h
                agg[k]["cdd"] += w * c
                agg[k]["hdd_normal"] += w * hn
                agg[k]["cdd_normal"] += w * cn
                c_h += h
                c_hn += hn
            cities.append({"city": name, "temps": temps, "hdd_16d": c_h, "hdd_normal_16d": c_hn})
        tot = {k: sum(a[k] for a in agg) for k in ("hdd", "cdd", "hdd_normal", "cdd_normal")}
        return {"days": agg, "totals": tot, "cities": cities,
                "signal": _wx_signal(tot),
                "method": "Degree days vs 65°F, population-weighted across 12 US metros; normal = average of the same calendar "
                          "days over the past 10 years (ERA5 reanalysis).",
                "source": "Open-Meteo (forecast; ERA5 archive)"}
    return _cached("wetr", 3 * 3600, fetch)


def _wx_signal(t: Dict[str, float]) -> str:
    parts = []
    dh, dc = t["hdd"] - t["hdd_normal"], t["cdd"] - t["cdd_normal"]
    if abs(dh) >= 8:
        parts.append(f"{'colder' if dh > 0 else 'milder'} than normal ({dh:+.0f} heating degree days) → "
                     f"{'more' if dh > 0 else 'less'} heating demand for natural gas")
    if abs(dc) >= 8:
        parts.append(f"{'hotter' if dc > 0 else 'cooler'} than normal ({dc:+.0f} cooling degree days) → "
                     f"{'more' if dc > 0 else 'less'} power demand for air conditioning")
    return "; ".join(parts) or "temperatures close to normal over the next 16 days"


# ── INSD: Form 4 ─────────────────────────────────────────────────────────────
CODES = {"P": "Buy (open market)", "S": "Sale (open market)", "A": "Grant / award", "M": "Option exercise", "F": "Tax withholding",
         "G": "Gift", "D": "Disposition to issuer", "C": "Conversion", "X": "Option exercise", "J": "Other", "W": "Inheritance"}


def insiders(symbol: str, limit: int = 40) -> Dict[str, Any]:
    s = symbol.strip().upper()

    def fetch():
        from api.providers import sec_edgar
        res = sec_edgar.resolve(s)
        cik = res.get("cik") if isinstance(res, dict) else res
        if not cik:
            raise NotFound("Form 4 filings are for SEC-registered (mostly US) companies.")
        cik10 = str(cik).zfill(10)
        sub = _sec_get(f"https://data.sec.gov/submissions/CIK{cik10}.json").json()
        r = sub["filings"]["recent"]
        docs = [(r["accessionNumber"][i], r["primaryDocument"][i], r["filingDate"][i]) for i in range(len(r["form"]))
                if r["form"][i] in ("4", "4/A")][:limit]

        def parse(item):
            acc, doc, fdate = item
            raw = doc.split("/")[-1]                                   # strip the xsl rendering prefix
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{raw}"
            try:
                root = ET.fromstring(_sec_get(url).content)
            except Exception:
                return []
            owner = root.findtext(".//reportingOwner/reportingOwnerId/rptOwnerName") or ""
            rel = root.find(".//reportingOwner/reportingOwnerRelationship")
            role = []
            if rel is not None:
                if (rel.findtext("isDirector") or "").strip() in ("1", "true"):
                    role.append("Director")
                if (rel.findtext("isOfficer") or "").strip() in ("1", "true"):
                    role.append(rel.findtext("officerTitle") or "Officer")
                if (rel.findtext("isTenPercentOwner") or "").strip() in ("1", "true"):
                    role.append("10% owner")
            out = []
            for t in root.findall(".//nonDerivativeTable/nonDerivativeTransaction"):
                code = t.findtext("transactionCoding/transactionCode") or ""
                sh = _f(t.findtext("transactionAmounts/transactionShares/value"))
                px = _f(t.findtext("transactionAmounts/transactionPricePerShare/value"))
                ad = t.findtext("transactionAmounts/transactionAcquiredDisposedCode/value")
                out.append({"filed": fdate, "date": t.findtext("transactionDate/value"), "insider": owner.title(), "role": ", ".join(role) or "—",
                            "code": code, "type": CODES.get(code, code), "shares": sh, "price": px,
                            "value": sh * px if sh and px else None, "direction": "buy" if ad == "A" else "sell",
                            "owned_after": _f(t.findtext("postTransactionAmounts/sharesOwnedFollowingTransaction/value")),
                            "plan_10b5_1": bool(re.search(r"10b5-1", ET.tostring(root, encoding="unicode") or "")),
                            "url": url})
            return out
        with cf.ThreadPoolExecutor(4) as ex:
            rows = [x for chunk in ex.map(parse, docs) for x in chunk]
        rows.sort(key=lambda x: (x["date"] or "", x["filed"]), reverse=True)
        market = [x for x in rows if x["code"] in ("P", "S")]
        cutoff = str(date.today() - timedelta(days=180))
        buys = sum(x["value"] or 0 for x in market if x["code"] == "P" and (x["date"] or "") >= cutoff)
        sells = sum(x["value"] or 0 for x in market if x["code"] == "S" and (x["date"] or "") >= cutoff)
        return {"symbol": s, "company": sub.get("name"), "transactions": rows, "open_market_buys_6m": buys, "open_market_sales_6m": sells,
                "buyers_6m": len({x["insider"] for x in market if x["code"] == "P" and (x["date"] or "") >= cutoff}),
                "sellers_6m": len({x["insider"] for x in market if x["code"] == "S" and (x["date"] or "") >= cutoff}),
                "note": "Open-market purchases (code P) are the informative signal; sales are often pre-planned (10b5-1) or for "
                        "taxes and diversification. Grants (A), exercises (M) and tax withholding (F) are compensation mechanics.",
                "source": f"SEC EDGAR Form 4 filings (last {len(docs)})"}
    return _cached(f"insd:{s}:{limit}", 6 * 3600, fetch)


# ── 13F ──────────────────────────────────────────────────────────────────────
MANAGERS = {"0001067983": "Berkshire Hathaway (Buffett)", "0001350694": "Bridgewater Associates (Dalio)", "0001037389": "Renaissance Technologies",
            "0001336528": "Pershing Square (Ackman)", "0001649339": "Scion Asset Management (Burry)", "0001656456": "Appaloosa (Tepper)",
            "0001061768": "Baupost Group (Klarman)", "0001423053": "Citadel Advisors (Griffin)", "0001167483": "Tiger Global",
            "0001040273": "Third Point (Loeb)", "0001697748": "ARK Investment (Wood)", "0001536411": "Duquesne Family Office (Druckenmiller)",
            "0001029160": "Soros Fund Management", "0001791786": "Elliott Investment Management", "0001103804": "Viking Global"}
FIGI_CACHE = Path(__file__).resolve().parents[2] / "data" / "processed" / "cusip_tickers.json"


def _issuer_key(name: Optional[str]) -> str:
    """'CHUBB LIMITED' / 'Chubb Ltd' → 'chubb' (13F issuer names are abbreviated and upper-case)."""
    from api.marketdata.core import _norm
    return _norm(re.sub(r"\b(LIMITED|LTD|INC|CORP|CORPORATION|CO|COMPANY|PLC|NV|N\.V\.|SA|AG|HLDGS?|HOLDINGS?|GROUP|THE)\b\.?", " ",
                        str(name or "").upper()))


def _sec_names() -> Dict[str, str]:
    """Normalised SEC registrant name → ticker (first listed ticker wins: the common share)."""
    try:
        from api.providers import sec_edgar
        out: Dict[str, str] = {}
        for t, v in sec_edgar.ticker_map().items():
            out.setdefault(_issuer_key(v["name"]), t)
        return out
    except Exception:
        return {}


def _cusip_tickers(cusips: List[str]) -> Dict[str, Optional[str]]:
    """CUSIP → ticker via OpenFIGI (free, 10 per request without a key), cached on disk."""
    import requests
    try:
        cache = json.loads(FIGI_CACHE.read_text()) if FIGI_CACHE.exists() else {}
    except Exception:
        cache = {}
    todo = [c for c in dict.fromkeys(cusips) if c not in cache]
    for i in range(0, len(todo), 10):
        batch = todo[i:i + 10]
        try:
            r = requests.post("https://api.openfigi.com/v3/mapping", json=[{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"} for c in batch], timeout=20)
            if r.status_code == 429:
                break
            for c, res in zip(batch, r.json()):
                data = res.get("data") or []
                cache[c] = data[0].get("ticker") if data else None
        except Exception:
            break
    try:
        FIGI_CACHE.parent.mkdir(parents=True, exist_ok=True)
        FIGI_CACHE.write_text(json.dumps(cache))
    except Exception:
        pass
    return {c: cache.get(c) for c in cusips}


def _info_table(cik: str, acc: str) -> List[Dict[str, Any]]:
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}"
    idx = _sec_get(f"{base}/index.json").json()
    names = [x["name"] for x in idx.get("directory", {}).get("item", []) if x["name"].lower().endswith(".xml")]
    pick = next((n for n in names if "info" in n.lower()), None) or next((n for n in names if n.lower() != "primary_doc.xml"), None)
    if not pick:
        return []
    root = ET.fromstring(_sec_get(f"{base}/{pick}").content)
    ns = {"n": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {}
    q = (lambda p: "n:" + p) if ns else (lambda p: p)
    rows = []
    for it in root.findall(q("infoTable"), ns):
        val = _f(it.findtext(q("value"), namespaces=ns))
        sh = _f(it.findtext(f"{q('shrsOrPrnAmt')}/{q('sshPrnamt')}", namespaces=ns))
        rows.append({"issuer": (it.findtext(q("nameOfIssuer"), namespaces=ns) or "").strip(), "class": it.findtext(q("titleOfClass"), namespaces=ns),
                     "cusip": (it.findtext(q("cusip"), namespaces=ns) or "").strip().upper(), "value": val, "shares": sh,
                     "put_call": it.findtext(q("putCall"), namespaces=ns)})
    return rows


def thirteen_f(cik: str = "0001067983") -> Dict[str, Any]:
    cik10 = re.sub(r"\D", "", cik).zfill(10)

    def fetch():
        sub = _sec_get(f"https://data.sec.gov/submissions/CIK{cik10}.json").json()
        r = sub["filings"]["recent"]
        filings = [(r["accessionNumber"][i], r["reportDate"][i], r["filingDate"][i]) for i in range(len(r["form"])) if r["form"][i] == "13F-HR"]
        if not filings:
            raise NotFound("No 13F-HR filings for this filer.")
        cur_acc, cur_period, cur_filed = filings[0]
        cur = _info_table(cik10, cur_acc)
        prev = _info_table(cik10, filings[1][0]) if len(filings) > 1 else []

        def agg(rows):
            out: Dict[str, Dict[str, Any]] = {}
            for x in rows:
                key = x["cusip"] + ("|" + x["put_call"] if x["put_call"] else "")
                a = out.setdefault(key, {**x, "value": 0.0, "shares": 0.0})
                a["value"] += x["value"] or 0
                a["shares"] += x["shares"] or 0
            return out
        A, B = agg(cur), agg(prev)
        # SEC switched value reporting from thousands to dollars in 2023 — normalise
        scale = 1000 if cur_period < "2023-01-01" else 1
        total = sum(v["value"] for v in A.values()) * scale or 1
        tick = _cusip_tickers([v["cusip"] for v in sorted(A.values(), key=lambda v: -v["value"])[:60]])
        by_name = _sec_names()
        for v in A.values():          # OpenFIGI misses some foreign-domiciled CUSIPs (Chubb's H1467Z104): match the SEC name
            if not tick.get(v["cusip"]):
                tick[v["cusip"]] = by_name.get(_issuer_key(v["issuer"]))
        rows = []
        for k, v in sorted(A.items(), key=lambda kv: -kv[1]["value"]):
            p = B.get(k)
            chg = (v["shares"] / p["shares"] - 1) if p and p["shares"] else None
            rows.append({"issuer": v["issuer"], "ticker": tick.get(v["cusip"]), "cusip": v["cusip"], "put_call": v["put_call"],
                         "value": v["value"] * scale, "weight": v["value"] * scale / total, "shares": v["shares"],
                         "change": "new" if not p else ("added" if chg and chg > 0.005 else "reduced" if chg and chg < -0.005 else "unchanged"),
                         "shares_change_pct": chg})
        sold = [{"issuer": v["issuer"], "cusip": v["cusip"], "put_call": v["put_call"]} for k, v in B.items() if k not in A]
        return {"cik": cik10, "manager": MANAGERS.get(cik10, sub.get("name")), "filer": sub.get("name"), "period": cur_period, "filed": cur_filed,
                "previous_period": filings[1][1] if len(filings) > 1 else None, "positions": len(rows), "total_value": total,
                "holdings": rows, "sold_out": sold, "managers": [{"cik": k, "name": v} for k, v in MANAGERS.items()],
                "note": "13F filings show US-listed long positions (and listed options) at quarter end, filed up to 45 days later; "
                        "no shorts, cash, bonds or non-US shares.",
                "source": "SEC EDGAR 13F-HR information tables; tickers via OpenFIGI"}
    return _cached(f"13f:{cik10}", 12 * 3600, fetch)



# ── EIA weekly supply & demand history (EIA API v2, free key) ────────────────
EIA_SERIES = {"WCRFPUS2": ("Crude production", "kb/d"), "WCRRIUS2": ("Refinery crude runs", "kb/d"), "WPULEUS3": ("Refinery utilisation", "%"),
              "WCEIMUS2": ("Crude imports", "kb/d"), "WCREXUS2": ("Crude exports", "kb/d"), "WGFUPUS2": ("Gasoline demand", "kb/d"),
              "WDIUPUS2": ("Distillate demand", "kb/d"), "WRPUPUS2": ("Total product demand", "kb/d"), "WCESTUS1": ("Commercial crude stocks", "kb"),
              "W_EPC0_SAX_YCUOK_MBBL": ("Cushing stocks", "kb"), "WTTSTUS1": ("All petroleum stocks", "kb")}


def eia_history(weeks: int = 520) -> Dict[str, Any]:
    import os
    key = os.getenv("EIA_API_KEY") or ""
    if not key:
        raise NotFound("Supply & demand history needs a free EIA API key (EIA_API_KEY).")

    def fetch():
        import requests
        params = [("api_key", key), ("frequency", "weekly"), ("data[0]", "value"), ("sort[0][column]", "period"),
                  ("sort[0][direction]", "desc"), ("length", str(min(5000, weeks * len(EIA_SERIES))))]
        params += [("facets[series][]", sid) for sid in EIA_SERIES]
        r = requests.get("https://api.eia.gov/v2/petroleum/sum/sndw/data/", params=params, timeout=60)
        r.raise_for_status()
        rows: Dict[str, Dict[str, Any]] = {}
        for d in r.json().get("response", {}).get("data", []):
            sid, per, v = d.get("series"), d.get("period"), _f(d.get("value"))
            if sid in EIA_SERIES and v is not None:
                rows.setdefault(per, {"date": per})[sid] = v
        series = sorted(rows.values(), key=lambda x: x["date"])
        if not series:
            raise Upstream("EIA returned no data.")
        latest = series[-1]
        def ago(n):
            return series[-1 - n] if len(series) > n else {}
        def seasonal_avg(sid):
            # EIA's convention: the same week in each of the previous five years (±3 days)
            d0 = date.fromisoformat(latest["date"])
            vals = []
            for yrs in range(1, 6):
                target = d0 - timedelta(weeks=52 * yrs)
                near = [x for x in series if abs((date.fromisoformat(x["date"]) - target).days) <= 3 and x.get(sid) is not None]
                if near:
                    vals.append(near[0][sid])
            return sum(vals) / len(vals) if vals else None
        summary = [{"series": sid, "label": lab, "unit": unit, "latest": latest.get(sid), "week_change": (latest.get(sid) or 0) - (ago(1).get(sid) or 0) if ago(1).get(sid) is not None else None,
                    "year_ago": ago(52).get(sid), "five_year_avg": seasonal_avg(sid)}
                   for sid, (lab, unit) in EIA_SERIES.items()]
        return {"as_of": latest["date"], "series": series, "summary": summary, "labels": {k: v[0] for k, v in EIA_SERIES.items()},
                "units": {k: v[1] for k, v in EIA_SERIES.items()}, "source": "EIA Weekly Petroleum Status Report (API v2)"}
    return _cached(f"eiahist:{weeks}", 6 * 3600, fetch)


# ── IPO calendar (Finnhub, free key) ─────────────────────────────────────────
def ipo_calendar(days_back: int = 30, days_ahead: int = 45) -> Dict[str, Any]:
    import os
    key = os.getenv("FINNHUB_API_KEY") or ""
    if not key:
        raise NotFound("The IPO calendar needs a free Finnhub key (FINNHUB_API_KEY).")

    def fetch():
        import requests
        r = requests.get("https://finnhub.io/api/v1/calendar/ipo", timeout=20,
                         params={"from": str(date.today() - timedelta(days=days_back)), "to": str(date.today() + timedelta(days=days_ahead)), "token": key})
        r.raise_for_status()
        rows = [{"date": x.get("date"), "symbol": x.get("symbol"), "name": x.get("name"), "exchange": x.get("exchange"), "price": x.get("price"),
                 "shares": x.get("numberOfShares"), "value": x.get("totalSharesValue"), "status": x.get("status")} for x in r.json().get("ipoCalendar", [])]
        rows.sort(key=lambda x: x["date"] or "", reverse=True)
        return {"ipos": rows, "source": "Finnhub IPO calendar (mainly US listings)",
                "note": "'expected' = scheduled with a price range; 'priced' = priced, trading; 'withdrawn' = pulled."}
    return _cached(f"ipo:{days_back}:{days_ahead}", 3600, fetch)
