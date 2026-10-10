"""
SPLC — supply-chain and competitor links from SEC filings (free).

US rules (ASC 280) require a company to disclose customers above 10% of revenue, and many
also name key customers and competitors in their 10-K text. SEC full-text search finds
annual reports that say e.g. "sales to Walmart" or "Apple accounted for", so:

  · Suppliers of X  = filers that name X as a customer
  · Competitors of X = filers that name X as a competitor

Coverage is partial by nature (US filers, last ~2 years of 10-Ks, explicit wording only) —
the paid feeds add analyst-curated links and revenue shares.
"""
from __future__ import annotations

import concurrent.futures as cf
import logging
import re
import urllib.parse
from datetime import date, timedelta
from typing import Any, Dict, List

from api.marketdata.core import NotFound, _cached, _info

logger = logging.getLogger(__name__)
FTS = "https://efts.sec.gov/LATEST/search-index"
SUFFIX = re.compile(r"(,?\s+(inc\.?|incorporated|corporation|corp\.?|company|co\.?|ltd\.?|limited|plc|s\.a\.|n\.v\.|ag|se|holdings?|group|the))+\s*$", re.I)
# How companies are usually named in other firms' filings, where it differs from the legal name
ALIASES = {"ALPHABET": ["Google"], "META": ["Meta", "Facebook"], "AMAZON.COM": ["Amazon"], "INTERNATIONAL BUSINESS MACHINES": ["IBM"],
           "THE HOME DEPOT": ["Home Depot"], "THE PROCTER & GAMBLE": ["Procter & Gamble"], "THE COCA-COLA": ["Coca-Cola"],
           "TAIWAN SEMICONDUCTOR MANUFACTURING": ["TSMC"], "WAL-MART": ["Walmart"], "WALMART": ["Walmart", "Wal-Mart"]}

CUSTOMER = ['"sales to {x}"', '"{x} accounted for"', '"{x} represented"', '"{x}, our largest customer"', '"{x} was our largest customer"',
            '"revenue from {x}"', '"revenues from {x}"', '"customer, {x}"', '"customers, {x}"', '"customers include {x}"',
            '"customers including {x}"', '"net sales to {x}"']
COMPETITOR = ['"compete with {x}"', '"competitors include {x}"', '"competitors such as {x}"', '"competitors, including {x}"',
              '"competing with {x}"', '"competitors, {x}"']


def _names(symbol: str) -> List[str]:
    i = _info(symbol)
    raw = (i.get("longName") or i.get("shortName") or symbol).strip()
    base = SUFFIX.sub("", raw).strip().rstrip(",")
    key = base.upper()
    out = ALIASES.get(key) or [base.replace(".com", "")]
    return [n for n in dict.fromkeys(out) if len(n) >= 3]


def _search(phrase: str) -> List[Dict[str, Any]]:
    import requests
    from api.providers.sec_edgar import USER_AGENT as ua           # SEC fair-access User-Agent
    start = (date.today() - timedelta(days=730)).isoformat()
    url = f"{FTS}?q={urllib.parse.quote(phrase)}&forms=10-K&dateRange=custom&startdt={start}&enddt={date.today()}"
    for _ in range(2):                                   # EDGAR search occasionally 500s; retry once
        try:
            r = requests.get(url, headers={"User-Agent": ua}, timeout=30)
            if r.status_code == 200:
                return r.json().get("hits", {}).get("hits", [])
        except Exception as e:
            logger.debug("[splc] %s: %s", phrase, e)
    return []


def _collect(names: List[str], templates: List[str], self_cik: str) -> List[Dict[str, Any]]:
    phrases = [t.format(x=n) for n in names for t in templates]
    with cf.ThreadPoolExecutor(4) as ex:                 # SEC allows 10 requests a second
        results = list(ex.map(_search, phrases))
    firms: Dict[str, Dict[str, Any]] = {}
    for phrase, hits in zip(phrases, results):
        for h in hits:
            src = h.get("_source", {})
            disp = (src.get("display_names") or [""])[0]
            cik = (src.get("ciks") or [""])[0]
            if not cik or cik.lstrip("0") == self_cik.lstrip("0"):
                continue
            m = re.match(r"(.+?)\s+\(([A-Z0-9.\-, ]+)\)\s+\(CIK", disp)
            name = (m.group(1) if m else disp.split("  (")[0]).strip()
            ticker = m.group(2).split(",")[0].strip() if m else None
            f = firms.setdefault(cik, {"name": name, "ticker": ticker, "cik": cik, "phrases": set(), "filings": set(), "latest": ""})
            f["phrases"].add(phrase.strip('"'))
            f["filings"].add(src.get("adsh") or h.get("_id", "").split(":")[0])
            f["latest"] = max(f["latest"], src.get("file_date") or "")
    rows = []
    for f in firms.values():
        adsh = sorted(f["filings"])[-1] if f["filings"] else None
        link = (f"https://www.sec.gov/Archives/edgar/data/{int(f['cik'])}/{adsh.replace('-', '')}/" if adsh else None)
        rows.append({"name": f["name"], "ticker": f["ticker"], "cik": f["cik"], "evidence": sorted(f["phrases"]),
                     "strength": len(f["phrases"]), "latest_10k": f["latest"], "filing_url": link})
    rows.sort(key=lambda r: r["latest_10k"], reverse=True)       # newest first …
    rows.sort(key=lambda r: -r["strength"])                       # … within the strongest evidence first
    return rows


def supply_chain(symbol: str) -> Dict[str, Any]:
    s = symbol.strip().upper()

    def fetch():
        names = _names(s)
        try:
            from api.providers import sec_edgar
            self_cik = str(sec_edgar.resolve(s) or "")
        except Exception:
            self_cik = ""
        def not_self(r):        # a company's own 10-K naturally mentions itself
            n = r["name"].lower()
            return not (any(x.lower() in n for x in names) or (r["ticker"] and r["ticker"][:4] == s.split(".")[0][:4]))
        suppliers = [r for r in _collect(names, CUSTOMER, self_cik) if not_self(r)]
        competitors = [r for r in _collect(names, COMPETITOR, self_cik) if not_self(r)]
        if not suppliers and not competitors:
            raise NotFound(f"No SEC filings name {names[0]} as a customer or competitor in the last two years "
                           "(coverage is US 10-K filers using explicit wording).")
        return {"symbol": s, "searched_as": names, "suppliers": suppliers, "competitors": competitors,
                "method": "SEC full-text search of 10-K annual reports filed in the last two years. Suppliers: filings that name "
                          f"{names[0]} as a customer (\"sales to …\", \"… accounted for\", \"customers include …\"); competitors: "
                          "filings that name it as a competitor. Evidence = the phrases found; open the filing to read the context.",
                "source": "SEC EDGAR full-text search"}
    return _cached(f"splc:{s}", 86400, fetch)
