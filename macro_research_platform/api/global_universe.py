"""
Global equity universe: the largest stocks in every market the platform covers
(api/markets.COUNTRIES), each classified by MSCI market class, region, country, exchange
and currency — built from Yahoo's equity screener and cached for a week.

Per country, the primary exchange(s) are screened by market cap. Clean-up:
  * only ordinary equity; depositary receipts (Brazil BDRs, Thai DRs, Canadian CDRs) and
    names flagged as such are dropped;
  * one listing per company worldwide — duplicates (same company name: cross-listings,
    NSE/BSE twins, preferred share classes) keep the listing with the highest traded value,
    which is the home listing (NVIDIA on Nasdaq, not Xetra; BHP in Sydney, not Johannesburg);
  * market cap and traded value converted to USD (minor-unit quotes such as pence handled).
Then the largest N per country (COUNTRIES[c]["n"]) by USD market cap.
"""
from __future__ import annotations

import json
import logging
import math
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from api.markets import COUNTRIES, classify, fx_ticker, minor_unit_factor

logger = logging.getLogger(__name__)

DATA = Path(__file__).resolve().parent.parent / "data" / "processed"
FILE = DATA / "global_universe.json"
MAX_AGE_DAYS = 7
_DR = re.compile(r"\b(DRN|BDR|CDR|DR|NVDR|ADR|GDR|ETF|ETN|FUND|TRUST UNITS?)\b", re.I)
_SUFFIX_WORDS = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|ag|se|sa|nv|n\.v|"
                           r"spa|s\.p\.a|ab|asa|a/s|oyj|holdings?|group|the|tbk|bhd|berhad|pcl|kgaa|sab de cv|"
                           r"de cv|s\.a|class [a-z]|cl [a-z])\b\.?", re.I)


_FOREIGN_FORM = re.compile(r"\b(plc|n\.?v\.?|s\.?a\.?|ag|se|asa|a/s|oyj|ab|limited|ltd\.?|s\.?p\.?a\.?|kgaa|tbk|berhad|bhd|pcl)\b\.?\s*$", re.I)


# ── Pure helpers (tested) ────────────────────────────────────────────────────
def _fold(s: str) -> str:
    """Lower-case and strip accents (Nestlé → nestle)."""
    import unicodedata
    return "".join(ch for ch in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(ch)).lower()


def name_key(name: str) -> str:
    n = _fold(name or "")
    n = re.sub(r"\(.*?\)", " ", n)
    n = _SUFFIX_WORDS.sub(" ", n)
    n = re.sub(r"[^a-z0-9]+", "", n)
    return n


def is_depositary(q: Dict[str, Any]) -> bool:
    sym = str(q.get("symbol") or "")
    name = f"{q.get('shortName') or ''} {q.get('longName') or ''}"
    if q.get("quoteType") not in (None, "EQUITY"):
        return True
    if re.search(r"3[2-5]\.SA$", sym) or re.search(r"\d{2}\.BK$", sym) or sym.endswith(".NE"):
        return True
    return bool(_DR.search(name))


def usd(value: Optional[float], quote_ccy: Optional[str], fx: Dict[str, float], already_major: bool = False) -> Optional[float]:
    """Convert an amount in `quote_ccy` (minor unit unless `already_major`) to USD."""
    if value is None:
        return None
    major, div = minor_unit_factor(quote_ccy)
    v = value if already_major else value / div
    rate = 1.0 if major == "USD" else fx.get(major)
    return v / rate if rate else None


def dedupe_and_rank(quotes: List[Dict[str, Any]], fx: Dict[str, float]) -> List[Dict[str, Any]]:
    """One listing per company (highest USD traded value), then largest N per country."""
    rows = []
    for q in quotes:
        if is_depositary(q):
            continue
        ccy = q.get("currency")
        mcap = usd(q.get("marketCap"), ccy, fx, already_major=True)
        px = q.get("regularMarketPrice")
        vol = q.get("averageDailyVolume3Month") or 0
        traded = usd((px or 0) * vol, ccy, fx) or 0.0
        if not mcap:
            continue
        rows.append({"symbol": q["symbol"], "name": q.get("longName") or q.get("shortName") or q["symbol"],
                     "country": q["_country"], "exchange": q.get("exchange"), "currency": ccy,
                     "mcap_usd": mcap, "traded_usd": traded, "_fin": q.get("financialCurrency")})
    # A US listing of a foreign company (ADR) can out-trade its home listing (TSMC); within a
    # duplicate group the home listing wins over a US one that reports in another currency or
    # carries a non-US corporate form (plc, N.V., AG, Limited, ...).
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault(name_key(r["name"]), []).append(r)
    for g in groups.values():
        if len(g) > 1 and any(r["country"] != "US" for r in g):
            for r in g:
                if r["country"] == "US" and (r["_fin"] not in (None, "USD") or _FOREIGN_FORM.search(r["name"])):
                    r["traded_usd"] = -1.0
    rows.sort(key=lambda r: -r["traded_usd"])
    seen_name, seen_size, kept = set(), set(), []
    for r in rows:
        nk = name_key(r["name"])
        # Second key catches a listing whose name is abbreviated differently: the same first
        # 12 letters AND the same USD market cap (to ~0.6%, as one company's listings are).
        # A looser key (6 letters, ~6% cap band) merged different banks — Bank of Montreal
        # with Bank of Nova Scotia, China Construction Bank with another "China…" bank.
        sk = (nk[:12], round(math.log10(r["mcap_usd"]) * 400)) if r["mcap_usd"] > 0 and len(nk) >= 12 else None
        if (nk and nk in seen_name) or (sk and sk in seen_size):
            continue
        seen_name.add(nk)
        if sk:
            seen_size.add(sk)
        kept.append(r)
    from api.markets import home_country
    for r in kept:                     # MSCI home market (H-shares → China, PDD → China, …)
        r["listing_country"] = r["country"]
        r["country"] = home_country(r["country"], r.get("_fin"))
    out = []
    for c, meta in COUNTRIES.items():
        mine = sorted([r for r in kept if r["country"] == c], key=lambda r: -r["mcap_usd"])[: meta["n"]]
        for r in mine:
            r.update(classify(r["symbol"], c))
            r["mcap_usd"] = round(r["mcap_usd"])
            r["traded_usd"] = round(max(r["traded_usd"], 0))
            r.pop("_fin", None)
        out.extend(mine)
    return out


# ── Fetch ────────────────────────────────────────────────────────────────────
def fx_rates() -> Dict[str, float]:
    """Units of each currency per 1 USD."""
    import yfinance as yf
    ccys = sorted({m["ccy"] for m in COUNTRIES.values() if m["ccy"] != "USD"} | {"GBP", "ZAR", "ILS", "EUR", "JPY"})
    tick = [fx_ticker(c) for c in ccys]
    df = yf.download(tick, period="5d", progress=False, group_by="ticker", threads=True)
    out = {}
    for c, t in zip(ccys, tick):
        try:
            out[c] = float(df[t]["Close"].dropna().iloc[-1])
        except Exception:
            pass
    return out


def _screen_country(code: str, meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    import yfinance as yf
    from yfinance import EquityQuery as Q
    if not meta.get("yr") or not meta.get("exch") or not meta.get("n"):
        return []
    query = Q("and", [Q("eq", ["region", meta["yr"]]), Q("is-in", ["exchange", *meta["exch"]])])
    # Many exchanges list thousands of foreign companies (Xetra, Milan, Mexico's SIC, B3
    # BDRs) that rank above local names by market cap, so page until enough HOME-market
    # names (reporting in the local currency, or any currency for multi-currency markets)
    # are collected.
    want = int(meta["n"] * 1.5) + 10
    out, offset, home = [], 0, 0
    while home < want and offset < 6000:
        try:
            r = yf.screen(query, offset=offset, size=250, sortField="intradaymarketcap", sortAsc=False)
        except Exception as e:
            logger.warning("[universe] %s screen failed: %s", code, e)
            break
        qs = r.get("quotes") or []
        for q in qs:
            q["_country"] = code
            if not is_depositary(q) and (q.get("financialCurrency") in (meta["ccy"], None)
                                         or code in ("GB", "NL", "CH", "IE", "HK", "SG", "IL")):
                home += 1
        out.extend(qs)
        if len(qs) < 250:
            break
        offset += 250
        time.sleep(0.2)
    return out


def build() -> Dict[str, Any]:
    t0 = time.time()
    fx = fx_rates()
    quotes: List[Dict[str, Any]] = []
    for code, meta in COUNTRIES.items():
        quotes.extend(_screen_country(code, meta))
        time.sleep(0.15)
    stocks = dedupe_and_rank(quotes, fx)
    # GICS sectors for US names from the S&P 500 list (others get theirs from the full model).
    try:
        from api.stock_ideas import load_universe
        sp = load_universe()
        for s in stocks:
            if s["country"] == "US" and s["symbol"] in sp:
                s["sector"] = sp[s["symbol"]]
    except Exception:
        pass
    if len(stocks) < 500:                      # screener refused / partial: keep the last good universe
        raise RuntimeError(f"only {len(stocks)} stocks screened")
    out = {"saved_at": time.time(), "config": config_hash(), "built_seconds": round(time.time() - t0, 1), "fx": fx,
           "raw_quotes": len(quotes), "stocks": stocks}
    DATA.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(out))
    logger.info("[universe] %d stocks from %d quotes in %.0fs", len(stocks), len(quotes), time.time() - t0)
    return out


def config_hash() -> str:
    """Changes when the market list, exchanges or sizes change → universe is rebuilt."""
    import hashlib
    cfg = json.dumps({c: [m.get("yr"), m.get("exch"), m.get("n")] for c, m in COUNTRIES.items()}, sort_keys=True)
    return hashlib.sha1(cfg.encode()).hexdigest()[:10]


def load(max_age_days: int = MAX_AGE_DAYS, rebuild_if_stale: bool = True) -> Dict[str, Any]:
    try:
        cur = json.loads(FILE.read_text())
    except Exception:
        cur = None
    if cur and time.time() - cur.get("saved_at", 0) < max_age_days * 86400 \
            and (cur.get("config") == config_hash() or not rebuild_if_stale):
        return cur
    if rebuild_if_stale:
        try:
            return build()
        except Exception as e:
            logger.warning("[universe] rebuild failed: %s", e)
    return cur or {"stocks": [], "fx": {}}


def summary(u: Dict[str, Any]) -> Dict[str, Any]:
    by_class: Dict[str, int] = {}
    by_country: Dict[str, int] = {}
    for s in u.get("stocks", []):
        by_class[s["market_class"]] = by_class.get(s["market_class"], 0) + 1
        by_country[s["country"]] = by_country.get(s["country"], 0) + 1
    return {"stocks": len(u.get("stocks", [])), "by_class": by_class, "countries": len(by_country),
            "by_country": dict(sorted(by_country.items(), key=lambda kv: -kv[1]))}
