"""
Corporate data on free official / public sources:

  actions(symbol)        CACS — a company's dividends (ex-date, pay date, growth), splits, upcoming events
  actions_calendar()     CACS — market-wide ex-dividend and split calendar for the coming two weeks (Nasdaq)
  management(symbol)     MGMT — officers, pay, age, governance risk scores, and insiders' recent trades
  segments(symbol)       PGEO — revenue (and operating income) by business segment, product and region, from the
                                inline XBRL in the latest 10-K (US filers)
  debt_maturities(sym)   DDIS — the maturity ladder of long-term debt (XBRL), with cash and interest cover
  deals()                MA   — announced, pending US mergers (EDGAR full-text search of 8-Ks): offer terms parsed
                                from the filing, target price, and the merger-arbitrage spread
"""
from __future__ import annotations

import concurrent.futures as cf
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from api.marketdata.core import NotFound, Upstream, _cached, _f, _info

logger = logging.getLogger(__name__)
NASDAQ_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
             "Accept": "application/json, text/plain, */*", "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}


def _d(x) -> Optional[str]:
    if x is None:
        return None
    try:
        if isinstance(x, (int, float)):
            return datetime.utcfromtimestamp(x).strftime("%Y-%m-%d")
        return pd.Timestamp(x).strftime("%Y-%m-%d")
    except Exception:
        return None


# ── CACS ─────────────────────────────────────────────────────────────────────
def actions(symbol: str) -> Dict[str, Any]:
    from api.marketdata.core import div_yield, yahoo_call
    s = symbol.strip().upper()

    def build():
        import yfinance as yf
        t = yf.Ticker(s)
        i = _info(s)
        div = yahoo_call(lambda: t.dividends)
        spl = yahoo_call(lambda: t.splits)
        try:
            cal = yahoo_call(lambda: t.calendar) or {}
        except Exception:
            cal = {}
        pays = []
        if div is not None and len(div):
            div.index = pd.to_datetime(div.index).tz_localize(None)
            for d, v in div.iloc[::-1].items():
                pays.append({"ex_date": d.strftime("%Y-%m-%d"), "amount": float(v)})
        by_year = {}
        for p in pays:
            by_year[p["ex_date"][:4]] = by_year.get(p["ex_date"][:4], 0.0) + p["amount"]
        yrs = sorted(by_year)[-11:-1]                           # complete years
        growth = None
        if len(yrs) >= 6 and by_year[yrs[-6]] > 0:
            growth = (by_year[yrs[-1]] / by_year[yrs[-6]]) ** (1 / 5) - 1
        streak = 0
        for a, b in zip(yrs[::-1][:-1], yrs[::-1][1:]):
            if by_year[a] > by_year[b] * 1.001:
                streak += 1
            else:
                break
        freq = None
        if len(pays) >= 4:
            gaps = np.diff([pd.Timestamp(p["ex_date"]) for p in pays[:5][::-1]]).astype("timedelta64[D]").astype(int)
            g = float(np.median(gaps))
            freq = "monthly" if g < 45 else "quarterly" if g < 120 else "semi-annual" if g < 250 else "annual"
        splits = []
        if spl is not None and len(spl):
            for d, v in spl.iloc[::-1].items():
                r = float(v)
                splits.append({"date": pd.Timestamp(d).strftime("%Y-%m-%d"), "ratio": r,
                               "label": f"{r:g}-for-1" if r >= 1 else f"1-for-{1 / r:g} (reverse)"})
        upcoming = []
        if cal:
            if cal.get("Ex-Dividend Date"):
                upcoming.append({"event": "Ex-dividend", "date": _d(cal["Ex-Dividend Date"])})
            if cal.get("Dividend Date"):
                upcoming.append({"event": "Dividend paid", "date": _d(cal["Dividend Date"])})
            for e in (cal.get("Earnings Date") or [])[:1]:
                upcoming.append({"event": "Earnings", "date": _d(e), "detail": f"EPS est. {cal.get('Earnings Average'):.2f}" if cal.get("Earnings Average") else None})
        if i.get("exDividendDate"):
            exd = _d(i["exDividendDate"])
            if exd and not any(u["event"] == "Ex-dividend" and u["date"] == exd for u in upcoming):
                upcoming.append({"event": "Ex-dividend", "date": exd})
        today = date.today().isoformat()
        for u in upcoming:
            u["past"] = bool(u.get("date") and u["date"] < today)
        return {"symbol": s, "name": i.get("longName") or i.get("shortName"), "currency": i.get("currency"),
                "dividend_rate": _f(i.get("dividendRate")), "yield": div_yield(i), "payout_ratio": _f(i.get("payoutRatio")),
                "frequency": freq, "growth_5y": growth, "raise_streak_years": streak, "annual": [{"year": y, "total": by_year[y]} for y in sorted(by_year)[-20:]],
                "dividends": pays[:40], "splits": splits, "upcoming": sorted(upcoming, key=lambda u: u.get("date") or ""),
                "source": "Yahoo Finance (dividend and split history, calendar)"}
    return _cached(f"cacs:{s}", 6 * 3600, build)


def actions_calendar(days: int = 14) -> Dict[str, Any]:
    def build():
        import requests

        def one(d: date):
            out = {"divs": [], "splits": []}
            try:
                j = requests.get("https://api.nasdaq.com/api/calendar/dividends", params={"date": d.isoformat()}, headers=NASDAQ_UA, timeout=20).json()
                for r in (((j.get("data") or {}).get("calendar") or {}).get("rows") or []):
                    out["divs"].append({"date": d.isoformat(), "symbol": r.get("symbol"), "name": r.get("companyName"), "amount": _f(r.get("dividend_Rate")),
                                        "annual": _f(r.get("indicated_Annual_Dividend")), "pay_date": r.get("payment_Date"), "announced": r.get("announcement_Date")})
            except Exception as e:
                logger.info("[cacs] divs %s: %s", d, e)
            return out
        start = date.today()
        dates = [start + timedelta(days=k) for k in range(days) if (start + timedelta(days=k)).weekday() < 5]
        with cf.ThreadPoolExecutor(4) as ex:
            res = list(ex.map(one, dates))
        divs = [x for r in res for x in r["divs"]]
        splits = []
        try:
            j = requests.get("https://api.nasdaq.com/api/calendar/splits", headers=NASDAQ_UA, timeout=20).json()
            for r in ((j.get("data") or {}).get("rows") or []):
                splits.append({"symbol": r.get("symbol"), "name": r.get("name"), "ratio": r.get("ratio"), "date": r.get("executionDate"),
                               "announced": r.get("announcedDate")})
        except Exception as e:
            logger.info("[cacs] splits: %s", e)
        if not divs and not splits:
            raise Upstream("Nasdaq's corporate-actions calendar is unavailable right now.")
        divs = [d for d in divs if d["symbol"] and d["amount"]]
        return {"dividends": divs, "splits": splits, "from": dates[0].isoformat() if dates else None, "to": dates[-1].isoformat() if dates else None,
                "source": "Nasdaq dividend and split calendars"}
    return _cached(f"cacscal:{days}", 6 * 3600, build)


# ── MGMT ─────────────────────────────────────────────────────────────────────
def management(symbol: str) -> Dict[str, Any]:
    s = symbol.strip().upper()

    def build():
        i = _info(s)
        offs = i.get("companyOfficers") or []
        if not offs:
            raise NotFound(f"No management data for {s}.")
        people = [{"name": re.sub(r"^(Mr\.|Ms\.|Mrs\.|Dr\.|Prof\.)\s+", "", (o.get("name") or "").replace("  ", " ")).strip(),
                   "title": o.get("title"), "age": o.get("age"), "born": o.get("yearBorn"), "pay": _f(o.get("totalPay")),
                   "exercised": _f(o.get("exercisedValue")), "fiscal_year": o.get("fiscalYear")} for o in offs]
        risk = {k: i.get(k) for k in ("auditRisk", "boardRisk", "compensationRisk", "shareHolderRightsRisk", "overallRisk")}
        insiders = None
        try:
            from api.marketdata.extras import insiders as ins
            d = ins(s, 25)
            insiders = {"summary": d.get("summary"), "rows": (d.get("rows") or d.get("transactions") or [])[:15]}
        except Exception:
            insiders = None
        paid = [p for p in people if p["pay"]]
        return {"symbol": s, "name": i.get("longName") or i.get("shortName"), "employees": i.get("fullTimeEmployees"),
                "people": people, "total_disclosed_pay": sum(p["pay"] for p in paid) if paid else None,
                "risk": risk, "risk_as_of": _d(i.get("governanceEpochDate")), "insiders": insiders,
                "held_by_insiders": _f(i.get("heldPercentInsiders")), "held_by_institutions": _f(i.get("heldPercentInstitutions")),
                "note": "Officers and pay as disclosed in the latest proxy (via Yahoo). Governance scores are ISS QualityScores: 1 = lowest "
                        "governance risk, 10 = highest.", "source": "Yahoo Finance (officers, ISS governance), SEC Form 4"}
    return _cached(f"mgmt:{s}", 12 * 3600, build)


# ── PGEO: segments from the 10-K's inline XBRL ───────────────────────────────
REV_CONCEPTS = ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet")
AXES = {"srt:ProductOrServiceAxis": "Products & services", "us-gaap:StatementBusinessSegmentsAxis": "Business segments",
        "srt:StatementGeographicalAxis": "Regions", "srt:ConsolidationItemsAxis": None}
COUNTRY = {"country:US": "United States", "country:CN": "China", "country:JP": "Japan", "country:GB": "United Kingdom", "country:DE": "Germany",
           "country:FR": "France", "country:IN": "India", "country:CA": "Canada", "country:KR": "South Korea", "country:TW": "Taiwan",
           "country:NL": "Netherlands", "country:IE": "Ireland", "country:SG": "Singapore", "country:CH": "Switzerland", "country:MX": "Mexico",
           "country:BR": "Brazil", "country:AU": "Australia", "country:IT": "Italy", "country:ES": "Spain", "country:HK": "Hong Kong"}


def _member_label(m: str) -> str:
    if m in COUNTRY:
        return COUNTRY[m]
    x = m.split(":")[-1]
    x = re.sub(r"(Segment)?Member$", "", x)
    x = re.sub(r"(?<=[a-z])and(?=[A-Z])", "And", x)                 # "HomeandAccessories"
    x = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", x)
    x = re.sub(r"\bI (Phone|Pad|Pod|Cloud|Mac)\b", r"i\1", x)
    return x.replace(" And ", " & ").replace(" and ", " & ").strip()


def segments(symbol: str) -> Dict[str, Any]:
    from api.marketdata.extras import _company_only, _sec_get
    s = symbol.strip().upper()
    _company_only(s, "Segment data")

    def build():
        from lxml import etree
        from api.providers import sec_edgar
        res = sec_edgar.resolve(s)
        cik = res.get("cik") if isinstance(res, dict) else res
        if not cik:
            raise NotFound(f"Segment data comes from SEC filings; {s} doesn't file 10-Ks with the SEC.")
        sub = _sec_get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json").json()["filings"]["recent"]
        idx = next((k for k, f in enumerate(sub["form"]) if f in ("10-K", "20-F", "40-F")), None)
        if idx is None:
            raise NotFound(f"No annual report (10-K / 20-F) on EDGAR for {s}.")
        acc, doc = sub["accessionNumber"][idx].replace("-", ""), sub["primaryDocument"][idx]
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{doc}"
        raw = _sec_get(url, timeout=90).content
        root = etree.fromstring(raw, etree.XMLParser(recover=True, huge_tree=True))
        if root is None:
            raise NotFound("The annual report couldn't be parsed.")
        XI, DI, IX = "{http://www.xbrl.org/2003/instance}", "{http://xbrl.org/2006/xbrldi}", "{http://www.xbrl.org/2013/inlineXBRL}"
        ctx = {}
        for c in root.iter(f"{XI}context"):
            dims = [(m.get("dimension"), (m.text or "").strip()) for m in c.iter(f"{DI}explicitMember")]
            sd, ed = c.find(f".//{XI}startDate"), c.find(f".//{XI}endDate")
            ctx[c.get("id")] = (dims, sd.text if sd is not None else None, ed.text if ed is not None else None)
        facts: Dict[tuple, float] = {}
        for f in root.iter(f"{IX}nonFraction"):
            name = (f.get("name") or "").split(":")[-1]
            kind = "revenue" if name in REV_CONCEPTS else "operating_income" if name == "OperatingIncomeLoss" else None
            if not kind:
                continue
            dims, sd, ed = ctx.get(f.get("contextRef"), ([], None, None))
            if not sd or not ed:
                continue
            days = (pd.Timestamp(ed) - pd.Timestamp(sd)).days
            if days < 330 or days > 380:                          # annual figures only
                continue
            try:
                v = float("".join(f.itertext()).replace(",", "").strip() or "nan") * 10 ** int(f.get("scale") or 0)
            except ValueError:
                continue
            if f.get("sign") == "-":
                v = -v
            dims = [d for d in dims if d[0] != "srt:ConsolidationItemsAxis" or d[1] != "us-gaap:OperatingSegmentsMember"]
            if len(dims) > 1:
                continue
            axis, member = dims[0] if dims else (None, None)
            key = (kind, axis, member, ed)
            if key not in facts or name == REV_CONCEPTS[0]:
                facts[key] = v
        total = {ed: v for (k, a, m, ed), v in facts.items() if k == "revenue" and a is None}
        years = sorted({ed for (_, _, _, ed) in facts})[-3:]
        out = {}
        for axis, label in AXES.items():
            if not label:
                continue
            members = sorted({m for (k, a, m, ed) in facts if a == axis and k == "revenue"})
            if len(members) < 2:
                continue
            rows = []
            for m in members:
                rev = {ed: facts.get(("revenue", axis, m, ed)) for ed in years}
                oi = {ed: facts.get(("operating_income", axis, m, ed)) for ed in years}
                last = rev.get(years[-1])
                prev = rev.get(years[-2]) if len(years) > 1 else None
                rows.append({"member": m, "name": _member_label(m), "revenue": rev, "operating_income": oi,
                             "growth": (last / prev - 1) if last and prev else None,
                             "margin": (oi.get(years[-1]) / last) if last and oi.get(years[-1]) is not None else None,
                             "share": (last / total.get(years[-1])) if last and total.get(years[-1]) else None})
            rows = [r for r in rows if r["revenue"].get(years[-1])]
            # generic roll-ups (us-gaap Product / Service) overlap the company's own lines: drop them when those exist
            # roll-ups (us-gaap Product = iPhone + Mac + …) double count: drop one when it equals the sum of lines it contains
            ly = years[-1]
            specific = [r for r in rows if not r["member"].startswith("us-gaap:")]
            spec_sum = sum(r["revenue"][ly] for r in specific)
            rows = [r for r in rows if not (r["member"].startswith("us-gaap:") and len(specific) >= 2 and spec_sum
                                             and abs(spec_sum - r["revenue"][ly]) / r["revenue"][ly] < 0.03)]
            rows.sort(key=lambda r: -(r["revenue"].get(years[-1]) or 0))
            # drop aggregate members that equal the total (e.g. "Total segments")
            if rows and total.get(years[-1]) and abs(rows[0]["revenue"][years[-1]] - total[years[-1]]) < 1:
                rows = rows[1:]
            if len(rows) >= 2:
                out[label] = rows
        if not out:
            raise NotFound(f"{s}'s latest annual report has no tagged revenue breakdown by segment or region.")
        return {"symbol": s, "form": sub["form"][idx], "filed": sub["filingDate"][idx], "period_end": sub.get("reportDate", [None] * len(sub["form"]))[idx],
                "years": years, "total_revenue": {ed: total.get(ed) for ed in years}, "breakdowns": out, "url": url,
                "note": "Read from the inline XBRL tags of the latest annual report — the company's own segment and geographic disclosure. "
                        "Categories overlap across breakdowns (products vs regions), each sums to roughly total revenue.",
                "source": "SEC EDGAR (inline XBRL)"}
    return _cached(f"pgeo2:{s}", 24 * 3600, build)


# ── DDIS: debt maturity ladder ───────────────────────────────────────────────
DEBT_TAGS = [("LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths", "Year 1"), ("LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo", "Year 2"),
             ("LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree", "Year 3"), ("LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour", "Year 4"),
             ("LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive", "Year 5"), ("LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive", "After year 5")]


def debt_maturities(symbol: str) -> Dict[str, Any]:
    s = symbol.strip().upper()

    def build():
        from api.providers import sec_edgar
        res = sec_edgar.resolve(s)
        cik = res.get("cik") if isinstance(res, dict) else res
        if not cik:
            raise NotFound(f"The maturity ladder comes from SEC filings; {s} doesn't file with the SEC.")
        facts = (sec_edgar.company_facts(int(cik)) or {}).get("facts", {}).get("us-gaap", {})

        def latest(tag):
            units = (facts.get(tag) or {}).get("units", {}).get("USD") or []
            annual = [u for u in units if u.get("form") in ("10-K", "20-F", "10-K/A")]
            if not annual:
                return None, None
            u = max(annual, key=lambda u: (u.get("end") or "", u.get("filed") or ""))
            return float(u["val"]), u.get("end")
        ladder, as_of = [], None
        for tag, label in DEBT_TAGS:
            v, end = latest(tag)
            if v is not None:
                ladder.append({"bucket": label, "amount": v, "as_of": end})
                as_of = max(as_of or end, end)
        ladder = [x for x in ladder if x["as_of"] == as_of]
        if not ladder:
            raise NotFound(f"{s} doesn't tag a debt maturity schedule in its filings.")
        i = {}
        try:
            i = _info(s)
        except Exception:
            pass
        total = sum(x["amount"] for x in ladder)
        cash = _f(i.get("totalCash"))
        ebitda = _f(i.get("ebitda"))
        interest, _ = latest("InterestExpense")
        if interest is None:
            interest, _ = latest("InterestExpenseNonoperating")
        near = sum(x["amount"] for x in ladder if x["bucket"] in ("Year 1", "Year 2"))
        return {"symbol": s, "as_of": as_of, "ladder": ladder, "total_scheduled": total, "cash": cash, "ebitda": ebitda,
                "interest_expense": interest, "interest_cover": ebitda / interest if ebitda and interest else None,
                "due_2y": near, "cash_covers_2y": (cash / near) if cash and near else None,
                "net_debt_to_ebitda": ((_f(i.get("totalDebt")) or 0) - (cash or 0)) / ebitda if ebitda else None,
                "note": "Principal repayments of long-term debt by year, as tagged in the latest annual report (excludes commercial paper "
                        "and leases unless the company includes them).", "source": "SEC EDGAR XBRL; Yahoo Finance (cash, EBITDA)"}
    return _cached(f"ddis:{s}", 24 * 3600, build)


# ── MA: merger arbitrage ─────────────────────────────────────────────────────
PRICE_RX = re.compile(r"(?:right to receive|receive|for)\s+(?:an amount in cash equal to\s+)?\$\s?(\d{1,4}(?:\.\d{1,4})?)\s+(?:per share\s+)?in cash", re.I)
STOCK_RX = re.compile(r"(\d+\.\d{2,6})\s+(?:shares|of a share)\s+of\s+(?:the\s+)?(?:common stock|Class A common stock|ordinary shares)\s+of\s+([A-Z][\w&.,' -]{2,60}?)[,(]", re.I)
CLOSE_RX = re.compile(r"expected to (?:close|be completed|be consummated)\s+(?:in|during|by|before|at the end of)\s+(?:the\s+)?(first|second|third|fourth|1st|2nd|3rd|4th)?\s*(half|quarter)?\s*(?:of\s+)?(?:calendar\s+|fiscal\s+)?(?:year\s+)?(20\d\d)", re.I)


def _norm_name(n: str) -> str:
    n = re.sub(r"[^a-z0-9 ]", " ", n.lower())
    n = re.sub(r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|holdings?|group|the|n v|s a|llc|lp)\b", " ", n)
    return " ".join(n.split()[:2])


def _ticker_for(name: str) -> Optional[str]:
    try:
        from api.providers import sec_edgar
        key = _norm_name(name)
        for t, v in sec_edgar.ticker_map().items():
            if _norm_name(v["name"]) == key and "-" not in t:
                return t
    except Exception:
        pass
    return None


def _expected_close(text: str) -> Optional[str]:
    m = CLOSE_RX.search(text)
    if not m:
        return None
    n, unit, y = (m.group(1) or "").lower(), (m.group(2) or "").lower(), int(m.group(3))
    k = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4}.get(n)
    if unit == "half" and k:
        return f"{y}-{'06-30' if k == 1 else '12-31'}"
    if unit == "quarter" and k:
        return f"{y}-{['03-31', '06-30', '09-30', '12-31'][k - 1]}"
    return f"{y}-12-31"


def deals(days: int = 150) -> Dict[str, Any]:
    from api.marketdata.extras import _sec_get

    def build():
        import requests
        from api.providers.sec_edgar import USER_AGENT
        end, start = date.today(), date.today() - timedelta(days=days)
        hits = []
        import time as _t
        for q in ('"agreement and plan of merger" "per share in cash"', '"agreement and plan of merger" "right to receive" "in cash"'):
            for page in range(3):                                  # 100 hits a page
                for attempt in range(3):                           # SEC throttles bursts: back off and retry
                    try:
                        r = requests.get("https://efts.sec.gov/LATEST/search-index", params={"q": q, "forms": "8-K", "dateRange": "custom",
                                         "startdt": start.isoformat(), "enddt": end.isoformat(), "from": page * 100},
                                         headers={"User-Agent": USER_AGENT}, timeout=30)
                        r.raise_for_status()
                        got = r.json().get("hits", {}).get("hits", [])
                        break
                    except Exception as e:
                        logger.info("[ma] search: %s", e)
                        got = []
                        _t.sleep(2 * (attempt + 1))
                hits += got
                if len(got) < 100:
                    break
        if not hits:
            raise Upstream("EDGAR full-text search is unavailable right now.")
        # one filing per company: the earliest announcement with item 1.01 (agreement signed)
        by_cik: Dict[str, Dict[str, Any]] = {}
        for h in hits:
            src = h["_source"]
            if "1.01" not in (src.get("items") or []):
                continue
            cik = (src.get("ciks") or [""])[0]
            name = (src.get("display_names") or [""])[0]
            tick = re.search(r"\(([A-Z.\-]{1,6})[,)]", name)
            rec = {"cik": cik, "name": re.sub(r"\s*\(.*$", "", name).strip().title(), "ticker": tick.group(1) if tick else None,
                   "filed": src.get("file_date"), "adsh": src.get("adsh"), "doc": h["_id"].split(":")[-1], "completed": "2.01" in (src.get("items") or [])}
            cur = by_cik.get(cik)
            if cur is None or rec["filed"] < cur["filed"]:
                by_cik[cik] = {**rec, "completed": rec["completed"] or (cur or {}).get("completed", False)}
            elif rec["completed"]:
                cur["completed"] = True

        def parse(rec):
            url = f"https://www.sec.gov/Archives/edgar/data/{int(rec['cik'])}/{rec['adsh'].replace('-', '')}/{rec['doc']}"
            try:
                html = _sec_get(url, timeout=30).text
            except Exception:
                return None
            text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
            text = text.replace("&#160;", " ").replace("&nbsp;", " ").replace("&#8220;", "“").replace("&#8221;", "”").replace("&#8217;", "’")
            cash, window_ok = None, False
            for m in re.finditer(r"right to receive\s+(?:\(i\)\s*)?(?:the same\s+)?(?:an amount in cash equal to\s+)?\$\s?([\d,]+(?:\.\d{1,4})?)(.{0,45})", text, re.I):
                if "cash" in m.group(2).lower():
                    cash = float(m.group(1).replace(",", ""))
                    # whose shares convert? in a target's 8-K the clause talks about "the Company"'s shares
                    window_ok = "Company" in text[max(0, m.start() - 500):m.start()]
                    break
            st = STOCK_RX.search(text)
            # the filer is the target when ITS shares are converted / it ends up a subsidiary or merged away
            target = bool(re.search(r"Company (?:will|would) (?:become|continue as|survive as)[^.]{0,90}(?:subsidiary|surviving)|"
                                    r"(?:share|shares) of (?:the )?Company[’']?s? (?:common|ordinary|Class A)|Company Common Stock|"
                                    r"Each (?:of the remaining )?Shares? of the Company", text, re.I))
            buyer = re.search(r"([A-Z][\w&.,’' -]{2,80}?),?\s+an?\s+[\w ]{3,40}?(?:corporation|company|limited|partnership|plc|N\.V\.|S\.A\.)[^(]{0,60}\(\s*(?:the\s+)?[“\"]\s*Parent", text)
            cp = buyer.group(1).strip(" ,") if buyer else None
            if cp and rec["name"] and cp.lower()[:12] == rec["name"].lower()[:12]:
                cp = None
            # the agreement defines the parties: "by and among X (the “Company”), Y (“Parent”) …"
            dm = re.search(r"(?:by and (?:among|between)|among)\s+([A-Z][\w&.,’' -]{2,80}?),\s+an?\s+[^(]{3,80}?\(\s*(?:the\s+)?[“\"]\s*Company\s*[”\"]\s*\)", text)
            pm = re.search(r"([A-Z][\w&.,’' -]{2,80}?),\s+an?\s+[^(]{3,80}?\(\s*(?:the\s+)?[“\"]\s*Parent\s*[”\"]\s*\)", text)
            company_def = dm.group(1).strip() if dm else None
            parent_def = pm.group(1).strip() if pm else None
            same = lambda a, b: bool(a and b) and _norm_name(a) == _norm_name(b)
            target_name, target_ticker = None, None
            if company_def and same(company_def, rec["name"]):
                is_t = True
            elif company_def and parent_def and same(parent_def, rec["name"]):
                is_t, target_name = True, company_def                  # filed by the buyer: the target is "the Company"
                target_ticker = _ticker_for(company_def)
            else:
                is_t = target and (window_ok or cash is None)
            if parent_def and not cp:
                cp = parent_def
            if cp:
                cp = re.sub(r"^(?:the\s+)?Company,\s*", "", cp).strip(" ,") or None
            return {**rec, "url": url, "is_target": is_t, "target_name": target_name, "target_ticker": target_ticker, "cash_per_share": cash, "stock_ratio": float(st.group(1)) if st else None,
                    "stock_of": st.group(2).strip() if st else None, "counterparty": cp, "expected_close": _expected_close(text),
                    "cvr": bool(re.search(r"contingent value right", text, re.I))}
        with cf.ThreadPoolExecutor(3) as ex:
            parsed = [p for p in ex.map(parse, list(by_cik.values())[:60]) if p]
        out = []
        seen_targets = set()
        for p in parsed:
            if p.get("target_ticker"):
                p["counterparty"] = p["name"]
                p["name"], p["ticker"] = p["target_name"].title(), p["target_ticker"]
            if not p["is_target"] or not p["ticker"] or not (p["cash_per_share"] or p["stock_ratio"]) or p["ticker"] in seen_targets:
                continue
            seen_targets.add(p["ticker"])
            try:
                q = _info(p["ticker"])
                px = _f(q.get("regularMarketPrice")) or _f(q.get("currentPrice"))
            except Exception:
                px = None
            p["price"] = px
            offer = p["cash_per_share"]
            if offer and px and not (0.55 * offer <= px <= 1.25 * offer):
                continue                                           # price nowhere near the offer: not this company's shares
            if offer and px:
                p["spread"] = offer / px - 1
                if p["expected_close"]:
                    yrs = max(0.05, (pd.Timestamp(p["expected_close"]) - pd.Timestamp(date.today())).days / 365.25)
                    p["annualized"] = (1 + p["spread"]) ** (1 / yrs) - 1 if p["spread"] > -0.9 else None
            p["status"] = "completed" if p["completed"] else ("no quote — likely closed" if px is None else "pending")
            out.append(p)
        out.sort(key=lambda x: x["filed"], reverse=True)
        return {"deals": out, "from": start.isoformat(), "scanned": len(by_cik),
                "note": "Found by full-text search of 8-Ks announcing a merger agreement (item 1.01) in which the filer's own shares convert "
                        "to cash or stock. Terms are read from the filing text — check the filing before acting. Spread = offer ÷ price − 1; "
                        "a wide spread means the market doubts the deal closes (regulators, financing, a vote).",
                "source": "SEC EDGAR full-text search; Yahoo Finance prices"}
    return _cached(f"ma4:{days}", 6 * 3600, build)
