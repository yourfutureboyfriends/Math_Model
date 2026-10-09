"""
SEC EDGAR XBRL fundamentals — official, free, no API key (data.sec.gov).

  * Ticker → CIK map (sec.gov/files/company_tickers.json), cached for a week.
  * Company facts (data.sec.gov/api/xbrl/companyfacts/CIK##########.json), cached a day.
  * Statements: annual and quarterly income/cash-flow items (Q4 derived as the 10-K year
    minus Q1–Q3), balance-sheet items, trailing-twelve-month sums, common ratios — each
    value tagged with the filing (accession) and the date it was FILED.
  * Point-in-time daily series for backtests: a value exists only from the day its filing
    became public, using the ORIGINAL as-filed number (later restatements are ignored), so
    a backtest never sees a figure before the market could.

SEC fair-access rules: ≤ 10 requests/second and a User-Agent naming the requester with a
contact address (SEC_USER_AGENT; requests without one are refused with 403).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)
CACHE = Path(__file__).resolve().parents[2] / "data" / "processed" / "sec"
USER_AGENT = os.getenv("SEC_USER_AGENT") or "MacroTerminal research admin@example.com"
FACTS_TTL = 3 * 86400                # filings arrive quarterly; 3 days keeps new 10-Qs prompt
TICKERS_TTL = 7 * 86400
_rate_lock = threading.Lock()
_last_call = [0.0]
_mem: Dict[str, Tuple[float, Any]] = {}

# Friendly name → candidate us-gaap tags (filers use different tags for the same item).
DURATION = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet",
                "RevenuesNetOfInterestExpense"],
    "gross_profit": ["GrossProfit"],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold", "CostOfServices",
                        "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"],
    "eps_diluted": ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted", "EarningsPerShareBasic"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities",
                            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    "dividends_paid": ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"],
    "rnd": ["ResearchAndDevelopmentExpense"],
    "pretax_income": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                      "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
                      "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic"],
    "income_tax": ["IncomeTaxExpenseBenefit"],
    "interest_expense": ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt", "InterestAndDebtExpense"],
    "dna": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "DepreciationAmortizationAndAccretionNet",
            "Depreciation"],
    "sbc": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"],
}
INSTANT = {
    "total_assets": ["Assets"],
    "total_liabilities": ["Liabilities"],
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "equity_incl_nci": ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "StockholdersEquity"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "long_term_debt": ["LongTermDebtNoncurrent", "LongTermDebt", "LongTermDebtAndCapitalLeaseObligations",
                       "LongTermDebtAndFinanceLeaseObligationsNoncurrent", "LongTermNotesPayable", "SeniorNotes"],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "short_term_investments": ["ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"],
    "short_term_debt": ["DebtCurrent", "LongTermDebtCurrent", "ShortTermBorrowings", "CommercialPaper"],
    "minority_interest": ["MinorityInterest"],
    "operating_lease": ["OperatingLeaseLiability", "OperatingLeaseLiabilityNoncurrent"],
    "finance_lease": ["FinanceLeaseLiability", "FinanceLeaseLiabilityNoncurrent"],
}
LABELS = {
    "revenue": "Revenue", "gross_profit": "Gross profit", "operating_income": "Operating income",
    "net_income": "Net income", "eps_diluted": "EPS (diluted)", "operating_cash_flow": "Operating cash flow",
    "capex": "Capital expenditure", "free_cash_flow": "Free cash flow", "dividends_paid": "Dividends paid",
    "rnd": "R&D", "total_assets": "Total assets", "total_liabilities": "Total liabilities", "equity": "Shareholders' equity",
    "cash": "Cash", "long_term_debt": "Long-term debt", "current_assets": "Current assets",
    "current_liabilities": "Current liabilities", "shares": "Shares outstanding", "pretax_income": "Pretax income",
    "income_tax": "Income tax", "interest_expense": "Interest expense", "dna": "Depreciation & amortisation",
    "sbc": "Stock-based compensation", "short_term_investments": "Short-term investments", "short_term_debt": "Short-term debt",
    "minority_interest": "Minority interest", "operating_lease": "Operating lease liabilities",
    "finance_lease": "Finance lease liabilities",
}


class EdgarError(RuntimeError):
    pass


def _get(url: str) -> Any:
    with _rate_lock:                                     # ≤ ~8 requests / second
        wait = 0.125 - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
    r = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}, timeout=30)
    if r.status_code == 404:
        return None
    if r.status_code == 403:
        raise EdgarError("SEC refused the request — set SEC_USER_AGENT to 'Your Name your@email' (SEC fair-access rule).")
    r.raise_for_status()
    return r.json()


def _cached(path: Path, ttl: float, fetch, keep: bool = True) -> Any:
    key = str(path)
    hit = _mem.get(key) if keep else None
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    try:
        if time.time() - path.stat().st_mtime < ttl:
            data = json.loads(path.read_text())
            if keep:
                _mem[key] = (time.time(), data)
            return data
    except Exception:
        pass
    try:
        data = fetch()
    except Exception as e:
        try:                                              # stale beats nothing
            data = json.loads(path.read_text())
            logger.warning("[sec] using stale cache for %s: %s", path.name, e)
        except Exception:
            raise e
    else:
        if data is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data))
    if keep:
        _mem[key] = (time.time(), data)
    return data


def ticker_map() -> Dict[str, Dict[str, Any]]:
    raw = _cached(CACHE / "company_tickers.json", TICKERS_TTL,
                  lambda: _get("https://www.sec.gov/files/company_tickers.json"))
    out = {}
    for v in (raw or {}).values():
        out[str(v["ticker"]).upper()] = {"cik": int(v["cik_str"]), "name": v["title"]}
    return out


def resolve(ticker: str) -> Optional[Dict[str, Any]]:
    t = ticker.strip().upper()
    m = ticker_map()
    return m.get(t) or m.get(t.replace(".", "-")) or m.get(t.replace("-", "."))


def company_facts(cik: int) -> Optional[Dict[str, Any]]:
    # Not kept in memory: one company's facts can be several MB of JSON (tens of MB parsed).
    return _cached(CACHE / "facts" / f"CIK{cik:010d}.json", FACTS_TTL,
                   lambda: _get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"), keep=False)


# ── Fact extraction ──────────────────────────────────────────────────────────
def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def _pick_tag(facts: Dict[str, Any], tags: List[str], unit_pref=("USD", "USD/shares", "shares")) -> Tuple[Optional[str], List[Dict]]:
    """The candidate tag with the most recent data (filers switch tags over time); returns
    the merged points of all candidate tags, preferring the first tag on conflicts."""
    gaap = (facts.get("facts") or {}).get("us-gaap") or {}
    merged: Dict[Tuple, Dict] = {}
    best = None
    for tag in tags:
        units = (gaap.get(tag) or {}).get("units") or {}
        unit = next((u for u in unit_pref if u in units), None)
        if not unit:
            continue
        best = best or tag
        for p in units[unit]:
            k = (p.get("start"), p["end"], p.get("accn"))
            merged.setdefault(k, {**p, "tag": tag})
    return best, list(merged.values())


def _first_filed(points: List[Dict], key) -> Dict[Any, Dict]:
    """For each period key keep the ORIGINAL filing (earliest `filed`) — point-in-time."""
    out: Dict[Any, Dict] = {}
    for p in points:
        k = key(p)
        if k is None:
            continue
        cur = out.get(k)
        if cur is None or p["filed"] < cur["filed"]:
            out[k] = p
    return out


def quarterly(points: List[Dict]) -> List[Dict]:
    """Discrete quarters. Income-statement items are filed per quarter (≈3-month facts);
    cash-flow items are filed year-to-date (3, 6, 9, 12 months from the fiscal-year start),
    so a quarter is the difference of consecutive year-to-date figures — this also derives
    Q4 from the 10-K year. Each row: end, val, filed (when the later figure was public)."""
    pts = [p for p in points if p.get("start")]
    direct = _first_filed([p for p in pts if 75 <= _days(p["start"], p["end"]) <= 105], key=lambda p: p["end"])
    cum = _first_filed(pts, key=lambda p: (p["start"], p["end"]))      # every (fy start, end) span
    rows = {e: {"end": e, "start": p["start"], "val": float(p["val"]), "filed": p["filed"], "accn": p.get("accn"),
                "form": p.get("form"), "derived": False} for e, p in direct.items()}
    by_start: Dict[str, List[Dict]] = {}
    for (s, e), p in cum.items():
        if 75 <= _days(s, e) <= 380:
            by_start.setdefault(s, []).append(p)
    for s, spans in by_start.items():
        spans.sort(key=lambda p: p["end"])
        for prev, cur in zip(spans, spans[1:]):
            gap = _days(prev["end"], cur["end"])
            if cur["end"] in rows or not 75 <= gap <= 105:
                continue
            rows[cur["end"]] = {"end": cur["end"], "start": prev["end"], "val": float(cur["val"]) - float(prev["val"]),
                                "filed": max(cur["filed"], prev["filed"]), "accn": cur.get("accn"),
                                "form": cur.get("form"), "derived": True}
    # Filers that report only discrete quarters (no year-to-date spans): Q4 = year − Q1..Q3.
    for (s_, e), y in cum.items():
        if e in rows or not 350 <= _days(s_, e) <= 380:
            continue
        inside = [r for r in rows.values() if s_ <= r["start"] and r["end"] < e and _days(s_, r["end"]) > 60]
        if len(inside) == 3:
            rows[e] = {"end": e, "start": max(r["end"] for r in inside), "val": float(y["val"]) - sum(r["val"] for r in inside),
                       "filed": y["filed"], "accn": y.get("accn"), "form": y.get("form"), "derived": True}
    return sorted(rows.values(), key=lambda r: r["end"])


def annual(points: List[Dict]) -> List[Dict]:
    years = _first_filed([p for p in points if p.get("start") and 350 <= _days(p["start"], p["end"]) <= 380
                          and str(p.get("form", "")).startswith("10-K")], key=lambda p: p["end"])
    return [{"end": e, "val": float(p["val"]), "filed": p["filed"], "accn": p.get("accn"), "fy": p.get("fy")}
            for e, p in sorted(years.items())]


def instants(points: List[Dict]) -> List[Dict]:
    pts = _first_filed([p for p in points if not p.get("start")], key=lambda p: p["end"])
    return [{"end": e, "val": float(p["val"]), "filed": p["filed"], "accn": p.get("accn")} for e, p in sorted(pts.items())]


def ttm(qrows: List[Dict]) -> List[Dict]:
    """Trailing-twelve-month sums of four consecutive quarters; `filed` = when the last of
    them became public."""
    out = []
    for i in range(3, len(qrows)):
        w = qrows[i - 3:i + 1]
        if _days(w[0]["end"], w[-1]["end"]) > 300:        # 4 consecutive quarters span ~9 months
            continue
        out.append({"end": w[-1]["end"], "val": sum(r["val"] for r in w), "filed": max(r["filed"] for r in w)})
    return out


def shares_series(facts: Dict[str, Any]) -> List[Dict]:
    dei = (facts.get("facts") or {}).get("dei") or {}
    pts = ((dei.get("EntityCommonStockSharesOutstanding") or {}).get("units") or {}).get("shares") or []
    if not pts:
        _, pts = _pick_tag(facts, ["CommonStockSharesOutstanding", "WeightedAverageNumberOfDilutedSharesOutstanding"], ("shares",))
    pts = [p for p in pts if p.get("filed")]
    best = _first_filed(pts, key=lambda p: p["filed"])
    return [{"end": p["end"], "val": float(p["val"]), "filed": f} for f, p in sorted(best.items())]


def _combine(a: List[Dict], b: List[Dict], fn) -> List[Dict]:
    """Rows present in both (matched on period end): fn(a, b); filed = the later filing."""
    bm = {r["end"]: r for r in b}
    return [{"end": r["end"], "start": r.get("start"), "val": fn(r["val"], bm[r["end"]]["val"]),
             "filed": max(r["filed"], bm[r["end"]]["filed"]), "accn": r.get("accn"), "derived": True}
            for r in a if r["end"] in bm]


def gross_profit_quarters(facts: Dict[str, Any]) -> List[Dict]:
    """Reported gross profit, else revenue − cost of revenue (many filers, e.g. Alphabet and
    Amazon, never tag GrossProfit)."""
    _, gp = _pick_tag(facts, DURATION["gross_profit"])
    rows = {r["end"]: r for r in quarterly(gp)} if gp else {}
    _, rev = _pick_tag(facts, DURATION["revenue"])
    _, cost = _pick_tag(facts, DURATION["cost_of_revenue"])
    if rev and cost:
        for r in _combine(quarterly(rev), quarterly(cost), lambda x, y: x - y):
            rows.setdefault(r["end"], r)
    return sorted(rows.values(), key=lambda r: r["end"])


def liabilities_instants(facts: Dict[str, Any]) -> List[Dict]:
    """Reported total liabilities, else total assets − total equity (incl. minority interest)."""
    _, li = _pick_tag(facts, INSTANT["total_liabilities"])
    rows = {r["end"]: r for r in instants(li)} if li else {}
    _, a = _pick_tag(facts, INSTANT["total_assets"])
    _, e = _pick_tag(facts, INSTANT["equity_incl_nci"])
    if a and e:
        for r in _combine(instants(a), instants(e), lambda x, y: x - y):
            rows.setdefault(r["end"], r)
    return sorted(rows.values(), key=lambda r: r["end"])


# ── Statements (for the UI) ──────────────────────────────────────────────────
def statements(ticker: str, years: int = 10, quarters: int = 12) -> Dict[str, Any]:
    ent = resolve(ticker)
    if not ent:
        raise LookupError(f"{ticker} is not an SEC filer (ETFs, funds and most foreign listings are not covered).")
    facts = company_facts(ent["cik"])
    if not facts:
        raise LookupError(f"No XBRL financial data on file for {ticker}.")
    ann: Dict[str, Dict[str, float]] = {}
    qtr: Dict[str, Dict[str, float]] = {}
    tags: Dict[str, str] = {}
    for name, cands in DURATION.items():
        if name == "cost_of_revenue":
            continue
        tag, pts = _pick_tag(facts, cands)
        if name == "gross_profit":
            qrows = gross_profit_quarters(facts)
            if qrows:
                tags[name] = tag or "Revenue − cost of revenue"
                for r in qrows[-quarters:]:
                    qtr.setdefault(r["end"], {})[name] = r["val"]
            if tag:
                for r in annual(pts)[-years:]:
                    ann.setdefault(r["end"], {})[name] = r["val"]
            else:
                _, rv = _pick_tag(facts, DURATION["revenue"])
                _, cs = _pick_tag(facts, DURATION["cost_of_revenue"])
                if rv and cs:
                    for r in _combine(annual(rv), annual(cs), lambda x, y: x - y)[-years:]:
                        ann.setdefault(r["end"], {})[name] = r["val"]
            continue
        if not tag:
            continue
        tags[name] = tag
        for r in annual(pts)[-years:]:
            ann.setdefault(r["end"], {})[name] = r["val"]
        for r in quarterly(pts)[-quarters:]:
            qtr.setdefault(r["end"], {})[name] = r["val"]
    for name, cands in INSTANT.items():
        if name == "equity_incl_nci":
            continue
        tag, pts = _pick_tag(facts, cands)
        if name == "total_liabilities":
            inst_rows = liabilities_instants(facts)
            tag = tag or ("Assets − equity" if inst_rows else None)
        else:
            inst_rows = instants(pts) if tag else []
        if not tag:
            continue
        tags[name] = tag
        inst = {r["end"]: r["val"] for r in inst_rows}
        for e in ann:
            if e in inst:
                ann[e][name] = inst[e]
        for e in qtr:
            if e in inst:
                qtr[e][name] = inst[e]
    for table in (ann, qtr):
        for row in table.values():
            if "operating_cash_flow" in row and "capex" in row:
                row["free_cash_flow"] = row["operating_cash_flow"] - row["capex"]
    sh = shares_series(facts)
    latest_q = sorted(qtr)[-4:] if len(qtr) >= 4 else []

    def ttm_of(k):
        vals = [qtr[e].get(k) for e in latest_q]
        return sum(vals) if latest_q and all(v is not None for v in vals) else None
    last_bal = qtr[sorted(qtr)[-1]] if qtr else {}
    t = {k: ttm_of(k) for k in ("revenue", "gross_profit", "operating_income", "net_income", "eps_diluted", "operating_cash_flow", "capex",
                                "pretax_income", "income_tax", "interest_expense", "dna", "sbc")}

    def ratio(a, b):
        return round(a / b, 4) if a is not None and b not in (None, 0) else None
    fcf = t["operating_cash_flow"] - t["capex"] if t["operating_cash_flow"] is not None and t["capex"] is not None else None
    ratios = {"gross_margin": ratio(t["gross_profit"], t["revenue"]), "operating_margin": ratio(t["operating_income"], t["revenue"]),
              "net_margin": ratio(t["net_income"], t["revenue"]), "roe": ratio(t["net_income"], last_bal.get("equity")),
              "roa": ratio(t["net_income"], last_bal.get("total_assets")),
              "debt_to_equity": ratio(last_bal.get("total_liabilities"), last_bal.get("equity")),
              "current_ratio": ratio(last_bal.get("current_assets"), last_bal.get("current_liabilities")),
              "fcf_margin": ratio(fcf, t["revenue"])}
    filings = sorted({(r.get("accn"), r.get("filed"), r.get("form")) for _, pts in
                      [_pick_tag(facts, DURATION["revenue"]), _pick_tag(facts, DURATION["net_income"])]
                      for r in pts if r.get("accn")}, key=lambda x: x[1] or "", reverse=True)[:8]
    return {"ticker": ticker.upper(), "cik": ent["cik"], "name": facts.get("entityName") or ent["name"],
            "annual": [{"period_end": e, **ann[e]} for e in sorted(ann)],
            "quarterly": [{"period_end": e, **qtr[e]} for e in sorted(qtr)],
            "ttm": {**t, "free_cash_flow": fcf, "as_of": latest_q[-1] if latest_q else None},
            "ratios": ratios, "shares_outstanding": sh[-1] if sh else None, "tags": tags, "labels": LABELS,
            "balance": {k: v for k, v in last_bal.items() if k in INSTANT}, "balance_as_of": sorted(qtr)[-1] if qtr else None,
            "filings": [{"accession": a, "filed": f, "form": fm,
                         "url": f"https://www.sec.gov/Archives/edgar/data/{ent['cik']}/{a.replace('-', '')}/"} for a, f, fm in filings],
            "source": "SEC EDGAR XBRL (as filed)"}


# ── Point-in-time daily series (for the Quant Lab) ───────────────────────────
PIT_FIELDS = ("eps_ttm", "sales_ttm", "net_income_ttm", "gross_profit_ttm", "fcf_ttm", "equity", "total_assets",
              "total_liabilities", "shares")
STALE_DAYS = 400                     # no new filing for > 400 days → stop carrying the value


def pit_events(ticker: str) -> Dict[str, List[Tuple[str, float]]]:
    """{field: [(filed_date, value), ...]} — each value as first reported, dated when filed.
    Cached per ticker (small) for FACTS_TTL."""
    path = CACHE / "pit" / f"{ticker.upper().replace('/', '_')}.json"
    try:
        if time.time() - path.stat().st_mtime < FACTS_TTL:
            return {k: [tuple(x) for x in v] for k, v in json.loads(path.read_text()).items()}
    except Exception:
        pass
    out = _pit_events(ticker)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out))
    return out


def _pit_events(ticker: str) -> Dict[str, List[Tuple[str, float]]]:
    ent = resolve(ticker)
    if not ent:
        return {}
    facts = company_facts(ent["cik"])
    if not facts:
        return {}
    out: Dict[str, List[Tuple[str, float]]] = {}

    def dur_ttm(name):
        _, pts = _pick_tag(facts, DURATION[name])
        return ttm(quarterly(pts)) if pts else []
    for field, name in (("eps_ttm", "eps_diluted"), ("sales_ttm", "revenue"), ("net_income_ttm", "net_income")):
        out[field] = [(r["filed"], r["val"]) for r in dur_ttm(name)]
    out["gross_profit_ttm"] = [(r["filed"], r["val"]) for r in ttm(gross_profit_quarters(facts))]
    ocf = {r["end"]: r for r in dur_ttm("operating_cash_flow")}
    cap = {r["end"]: r for r in dur_ttm("capex")}
    out["fcf_ttm"] = [(max(ocf[e]["filed"], cap[e]["filed"]), ocf[e]["val"] - cap[e]["val"]) for e in sorted(ocf) if e in cap]
    for field in ("equity", "total_assets"):
        _, pts = _pick_tag(facts, INSTANT[field])
        out[field] = [(r["filed"], r["val"]) for r in instants(pts)]
    out["total_liabilities"] = [(r["filed"], r["val"]) for r in liabilities_instants(facts)]
    out["shares"] = [(r["filed"], r["val"]) for r in shares_series(facts)]
    return {k: sorted(v) for k, v in out.items() if v}


def pit_frame(tickers: List[str], index) -> Dict[str, "Any"]:
    """{field: DataFrame(dates × tickers)} of point-in-time values on `index` (a
    DatetimeIndex). Values appear the trading day AFTER filing (filings land during or after
    the session) and lapse after STALE_DAYS without a new filing."""
    import numpy as np
    import pandas as pd
    frames = {f: pd.DataFrame(np.nan, index=index, columns=tickers) for f in PIT_FIELDS}
    for t in tickers:
        try:
            ev = pit_events(t)
        except EdgarError:
            raise
        except Exception as e:
            logger.info("[sec] no fundamentals for %s: %s", t, e)
            continue
        for f, pts in ev.items():
            if f not in frames or not pts:
                continue
            s = pd.Series({pd.Timestamp(d) + pd.Timedelta(days=1): v for d, v in pts}).sort_index()
            s = s[~s.index.duplicated(keep="last")]
            daily = s.reindex(index.union(s.index)).ffill()
            last_filed = pd.Series(s.index, index=s.index).reindex(index.union(s.index)).ffill()
            age = (daily.index.to_series() - last_filed).dt.days
            daily[age > STALE_DAYS] = np.nan
            frames[f][t] = daily.reindex(index).to_numpy()
    return frames
