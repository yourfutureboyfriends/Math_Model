"""Screens that fill the gaps against Bloomberg, IBKR and Futu with free public data:

    BORROW  short borrow       — IBKR's published stock-loan fee, rebate and shares available (18 markets, several times a day)
    DARK    off-exchange volume — FINRA's weekly dark-pool (ATS) and wholesaler (OTC) volume per stock, by venue
    PROB    probability lab    — the price distribution an option expiry implies (Breeden–Litzenberger), as IBKR's Probability Lab
    CRPR    credit profile     — synthetic rating from interest coverage (Damodaran), Altman Z, Piotroski F, leverage, liquidity
    LEAG    M&A adviser league — banks named as financial adviser in merger proxies and registrations (SEC full-text search)
    SPF     economist consensus — Philadelphia Fed Survey of Professional Forecasters medians (US growth, CPI, jobs, 10-year)
"""
from __future__ import annotations

import io
import logging
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from api.marketdata.core import NotFound, Upstream, _cached, _f

logger = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (MacroTerminal research)"}


# ── BORROW ───────────────────────────────────────────────────────────────────
IBKR_FTP = "ftp://shortstock:@ftp2.interactivebrokers.com/{}"
BORROW_FILES = {"": "usa.txt", "L": "british.txt", "HK": "hongkong.txt", "T": "japan.txt", "TO": "canada.txt", "V": "canada.txt",
                "AX": "australia.txt", "DE": "germany.txt", "F": "germany.txt", "PA": "france.txt", "AS": "dutch.txt", "MI": "italy.txt",
                "MC": "spain.txt", "ST": "swedish.txt", "SW": "swiss.txt", "SI": "singapore.txt", "NS": "india.txt", "BO": "india.txt",
                "MX": "mexico.txt", "BR": "belgium.txt", "VI": "austria.txt"}


def _ftp_text(name: str) -> str:
    import urllib.request
    with urllib.request.urlopen(IBKR_FTP.format(name), timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def borrow_table(file: str = "usa.txt") -> Dict[str, Any]:
    """IBKR's stock-loan file for one market: {symbol: {fee, rebate, available, name, currency}} and its timestamp."""
    def fetch():
        txt = _ftp_text(file)
        stamp, rows = None, {}
        for line in txt.splitlines():
            if line.startswith("#BOF"):
                p = line.split("|")
                stamp = f"{p[1].replace('.', '-')} {p[2]}" if len(p) > 2 else None
                continue
            if line.startswith("#"):
                continue
            p = line.split("|")
            if len(p) < 8:
                continue
            avail = p[7].strip()
            rows[p[0].strip().upper()] = {"name": p[2].strip(), "currency": p[1].strip(), "rebate": _f(p[5]), "fee": _f(p[6]),
                                          "available": 10_000_000 if avail.startswith(">") else (int(float(avail)) if avail else 0),
                                          "available_label": avail or "0"}
        if not rows:
            raise Upstream("IBKR's stock-loan file came back empty.")
        return {"as_of": stamp, "rows": rows}
    return _cached(f"borrow:{file}", 3600, fetch)


def _borrow_key(symbol: str) -> Tuple[str, str]:
    s = symbol.strip().upper()
    base, _, suf = s.partition(".")
    if suf == "HK":
        base = base.lstrip("0") or "0"
    return BORROW_FILES.get(suf, ""), base.replace("-", " ") if suf == "" else base


def borrow(symbol: str) -> Dict[str, Any]:
    """The current cost and availability of borrowing a stock to sell short at IBKR."""
    file, key = _borrow_key(symbol)
    if not file:
        raise NotFound(f"IBKR publishes no stock-loan file for {symbol}'s market.")
    t = borrow_table(file)
    r = t["rows"].get(key) or t["rows"].get(key.replace(" ", "."))
    if not r:
        raise NotFound(f"{symbol} isn't in IBKR's stock-loan file (not borrowable there).")
    fee = r["fee"] or 0.0
    tier = "general collateral" if fee < 0.5 else "warm" if fee < 5 else "hard to borrow" if fee < 50 else "extremely hard to borrow"
    return {"symbol": symbol.upper(), **r, "tier": tier, "as_of": t["as_of"], "market_file": file,
            "note": "Fee is the annual rate IBKR charges to borrow the shares; rebate is what a short seller earns on the cash "
                    "(negative when the fee exceeds the benchmark rate). 'Available' is IBKR's own lendable inventory, capped "
                    "at 10 million in the file.",
            "source": "Interactive Brokers stock-loan file (public FTP, updated through the day)."}


def borrow_screen(min_dollar_volume: float = 5e6, limit: int = 60) -> Dict[str, Any]:
    """The most expensive US stocks to short among liquid names, and index members that are costly to borrow."""
    def build():
        t = borrow_table("usa.txt")
        liquid: Dict[str, float] = {}
        try:
            from api.providers import massive
            days = massive.stored_days()
            if days:
                df = massive.read_day(days[-1])
                if df is not None and not df.empty:
                    dv = (df.set_index("ticker")["c"] * df.set_index("ticker")["v"]).dropna()
                    liquid = {str(k).upper(): float(v) for k, v in dv.items() if v >= min_dollar_volume}
        except Exception as e:                                  # noqa: BLE001 — without volumes, members only
            logger.info("borrow liquidity: %s", e)
        members: Dict[str, Dict[str, Any]] = {}
        try:
            from api.marketdata import funds
            for code in ("SPX", "NDX"):
                for m in funds.index_members(code)["members"]:
                    members[str(m["symbol"]).upper()] = {"index": code, "name": m.get("name"), "sector": m.get("sector")}
        except Exception as e:                                  # noqa: BLE001
            logger.info("borrow members: %s", e)
        rows = []
        for sym, r in t["rows"].items():
            if not re.fullmatch(r"[A-Z][A-Z. ]{0,6}", sym) or r["fee"] is None:
                continue
            m = members.get(sym.replace(" ", "."))
            dv = liquid.get(sym.replace(" ", "."))
            if not m and dv is None:
                continue
            rows.append({"symbol": sym.replace(" ", "."), "name": (m or {}).get("name") or r["name"], "fee": r["fee"], "rebate": r["rebate"],
                         "available": r["available"], "available_label": r["available_label"], "dollar_volume": dv,
                         "index": (m or {}).get("index"), "sector": (m or {}).get("sector")})
        if not rows:
            raise Upstream("No liquid names matched IBKR's stock-loan file.")
        hard = sorted(rows, key=lambda r: -r["fee"])[:limit]
        idx = sorted([r for r in rows if r["index"]], key=lambda r: -r["fee"])[:30]
        fees = np.array([r["fee"] for r in rows])
        return {"as_of": t["as_of"], "universe": len(rows), "hard_to_borrow": int((fees >= 5).sum()), "median_fee": float(np.median(fees)),
                "hardest": hard, "index_members": idx,
                "note": f"Liquid = over ${min_dollar_volume / 1e6:.0f}M traded on the last session, or a member of the S&P 500 or "
                        "Nasdaq 100. A fee above ~5% a year usually means heavy short demand or scarce supply.",
                "source": "Interactive Brokers stock-loan file; dollar volume from the local daily-bars store (Massive)."}
    return _cached("borrow:screen", 3600, build)


# ── DARK ─────────────────────────────────────────────────────────────────────
FINRA_URL = "https://api.finra.org/data/group/otcMarket/name/weeklySummary"


def _finra_week(symbol: str, week: str, tier: str) -> List[Dict[str, Any]]:
    import requests
    body = {"limit": 500, "compareFilters": [{"compareType": "EQUAL", "fieldName": "issueSymbolIdentifier", "fieldValue": symbol},
                                             {"compareType": "EQUAL", "fieldName": "weekStartDate", "fieldValue": week},
                                             {"compareType": "EQUAL", "fieldName": "tierIdentifier", "fieldValue": tier}]}
    r = requests.post(FINRA_URL, json=body, headers={**UA, "Accept": "application/json"}, timeout=40)
    if r.status_code == 204 or not r.text.strip():
        return []
    r.raise_for_status()
    return r.json()


def dark_pool(symbol: str, weeks: int = 10) -> Dict[str, Any]:
    """Weekly off-exchange volume for a US stock: dark pools (ATS) and wholesalers/internalisers (other OTC), their share
    of all volume, and the venues that traded most. FINRA publishes each week two to four weeks later."""
    symbol = symbol.strip().upper()
    if "." in symbol and not re.fullmatch(r"[A-Z]+\.[A-Z]", symbol):
        raise NotFound("FINRA's off-exchange data covers US-listed stocks only.")
    weeks = max(4, min(int(weeks), 26))

    def build():
        import concurrent.futures as cf
        fsym = symbol.replace("-", " ").replace(".", " ")
        monday = date.today() - timedelta(days=date.today().weekday())
        candidates = [str(monday - timedelta(weeks=k)) for k in range(2, weeks + 5)]

        def one(w):
            try:
                rows = _finra_week(fsym, w, "T1") or _finra_week(fsym, w, "T2")
                return w, rows
            except Exception as e:                              # noqa: BLE001 — a missing week is skipped
                logger.info("dark %s %s: %s", symbol, w, e)
                return w, []
        with cf.ThreadPoolExecutor(4) as ex:
            got = dict(ex.map(one, candidates))
        published = [w for w in candidates if got.get(w)][:weeks]
        if not published:
            raise NotFound(f"FINRA has no off-exchange volume for {symbol} in recent weeks.")
        try:
            from api.marketdata.core import yahoo_download
            vdf = yahoo_download([symbol], period="6mo", auto_adjust=False)
            vol = (vdf["Volume"] if not isinstance(vdf.columns, pd.MultiIndex) else vdf["Volume"][symbol]).dropna()
            vol.index = pd.to_datetime(vol.index).tz_localize(None).normalize()
        except Exception as e:                                  # noqa: BLE001 — shares without a percentage
            logger.info("dark volume %s: %s", symbol, e)
            vol = pd.Series(dtype=float)
        series, venues = [], {}
        for w in sorted(published):
            rows = got[w]
            ats = sum(_f(r.get("totalWeeklyShareQuantity")) or 0 for r in rows if r.get("summaryTypeCode") == "ATS_W_SMBL")
            otc = sum(_f(r.get("totalWeeklyShareQuantity")) or 0 for r in rows if r.get("summaryTypeCode") == "OTC_W_SMBL")
            ws = pd.Timestamp(w)
            total = float(vol[(vol.index >= ws) & (vol.index < ws + timedelta(days=7))].sum()) if len(vol) else 0.0
            series.append({"week": w, "ats": ats, "otc": otc, "total": total or None,
                           "ats_share": ats / total if total else None, "off_exchange_share": (ats + otc) / total if total else None,
                           "ats_trades": sum(_f(r.get("totalWeeklyTradeCount")) or 0 for r in rows if r.get("summaryTypeCode") == "ATS_W_SMBL")})
            for r in rows:
                if r.get("summaryTypeCode") in ("ATS_W_SMBL_FIRM", "OTC_W_SMBL_FIRM"):
                    k = (r.get("marketParticipantName") or r.get("MPID") or "?").strip()
                    v = venues.setdefault(k, {"venue": k, "kind": "Dark pool (ATS)" if r["summaryTypeCode"].startswith("ATS") else "Wholesaler / OTC",
                                              "shares": 0.0, "trades": 0.0})
                    v["shares"] += _f(r.get("totalWeeklyShareQuantity")) or 0
                    v["trades"] += _f(r.get("totalWeeklyTradeCount")) or 0
        tot_v = sum(v["shares"] for v in venues.values()) or 1
        top = sorted(venues.values(), key=lambda v: -v["shares"])[:15]
        for v in top:
            v["share_of_off_exchange"] = v["shares"] / tot_v
            v["avg_trade"] = v["shares"] / v["trades"] if v["trades"] else None
        last = series[-1]
        shares = [s["off_exchange_share"] for s in series if s["off_exchange_share"] is not None]
        return {"symbol": symbol, "weeks": series, "venues": top, "latest_week": last["week"],
                "off_exchange_share": last["off_exchange_share"], "ats_share": last["ats_share"],
                "avg_off_exchange_share": float(np.mean(shares)) if shares else None,
                "note": "Off-exchange = dark pools (ATS) plus wholesalers and internalisers (mostly retail orders filled by firms such "
                        "as Citadel and Virtu). FINRA publishes Tier 1 stocks two weeks after the week ends, others four weeks after. "
                        "Share is of all shares traded that week (Yahoo consolidated volume).",
                "source": "FINRA OTC Transparency (weekly ATS and non-ATS summaries); volume Yahoo Finance."}
    return _cached(f"dark:{symbol}:{weeks}", 12 * 3600, build)


# ── PROB ─────────────────────────────────────────────────────────────────────
def _bs_call(S, K, T, r, q, v):
    from scipy.stats import norm
    v = np.maximum(v, 1e-4)
    d1 = (np.log(S / K) + (r - q + 0.5 * v * v) * T) / (v * np.sqrt(T))
    d2 = d1 - v * np.sqrt(T)
    return S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)


def probability(symbol: str, expiry: Optional[str] = None) -> Dict[str, Any]:
    """The distribution of the price at expiry that option prices imply: the smile (out-of-the-money quotes) is smoothed
    on a fine strike grid, priced as calls, and differentiated twice (Breeden–Litzenberger). Gives percentiles, the chance
    of finishing above or below any level, and how the market's distribution differs from a plain lognormal."""
    from api.marketdata import security
    symbol = symbol.strip().upper()

    def build():
        from scipy.stats import norm
        ch = security.options(symbol, expiry)
        exp = ch["expiry"]
        if not expiry:                                          # default: the first expiry at least ~3 weeks out
            later = [e for e in ch.get("expirations", []) if (date.fromisoformat(e) - date.today()).days >= 21]
            if later and later[0] != exp:
                ch, exp = security.options(symbol, later[0]), later[0]
        S = _f(ch.get("underlying"))
        if isinstance(ch.get("underlying"), dict):
            S = _f(ch["underlying"].get("price"))
        days = ch.get("days") or max((date.fromisoformat(exp) - date.today()).days, 1)
        T, r, q = days / 365.0, _f(ch.get("rate")) or 0.04, _f(ch.get("dividend_yield")) or 0.0
        if not S:
            raise Upstream("No underlying price for this chain.")
        pts = []
        for side, rows in (("call", ch.get("calls") or []), ("put", ch.get("puts") or [])):
            for o in rows:
                k, iv = _f(o.get("strike")), _f(o.get("iv"))
                if not k or not iv or not 0.01 < iv < 5:
                    continue
                if (side == "call" and k >= S) or (side == "put" and k <= S):   # out of the money: the liquid side
                    pts.append((k, iv))
        pts = sorted(dict(pts).items())
        if len(pts) < 6:
            raise NotFound(f"Too few usable option quotes for {symbol} {exp} to infer a distribution.")
        ks, ivs = np.array([p[0] for p in pts]), np.array([p[1] for p in pts])
        x = np.log(ks / S)
        # smooth the smile: a quadratic in log-moneyness, flat beyond the quoted strikes
        coef = np.polyfit(x, ivs, 2, w=np.exp(-np.abs(x) * 2))
        atm = float(np.polyval(coef, 0.0))
        sd = atm * np.sqrt(T)
        grid = S * np.exp(np.linspace(-5 * sd, 5 * sd, 801))
        gx = np.clip(np.log(grid / S), x.min(), x.max())
        vol = np.clip(np.polyval(coef, gx), 0.03, 4.0)
        C = _bs_call(S, grid, T, r, q, vol)
        dk = np.gradient(grid)
        cdf_above = np.clip(-np.exp(r * T) * np.gradient(C, grid), 0, 1)      # P(S_T > K)
        dens = np.clip(np.exp(r * T) * np.gradient(np.gradient(C, grid), grid), 0, None)
        mass = float((dens * dk).sum())
        if mass <= 0:
            raise Upstream("The option prices don't give a usable distribution.")
        dens = dens / mass
        cdf = np.clip(np.cumsum(dens * dk), 0, 1)
        pct = {p: float(np.interp(p / 100, cdf, grid)) for p in (5, 10, 25, 50, 75, 90, 95)}
        # a lognormal with the at-the-money vol, for comparison
        mu = np.log(S) + (r - q - 0.5 * atm * atm) * T
        logn = norm.pdf(np.log(grid), mu, sd) / grid
        logn_cdf = norm.cdf(np.log(grid), mu, sd)
        levels = [round(S * (1 + m), 2) for m in (-0.2, -0.1, -0.05, 0.05, 0.1, 0.2)]
        rows = [{"level": L, "move": L / S - 1, "p_above": float(np.interp(L, grid, 1 - cdf)), "p_below": float(np.interp(L, grid, cdf)),
                 "p_above_lognormal": float(1 - norm.cdf(np.log(L), mu, sd))} for L in levels]
        step = max(1, len(grid) // 160)
        return {"symbol": symbol, "expiry": exp, "days": days, "spot": S, "atm_iv": atm, "rate": r,
                "expected_move": S * atm * np.sqrt(T), "percentiles": pct,
                "p_up": float(np.interp(S, grid, 1 - cdf)), "levels": rows,
                "mean": float((grid * dens * dk).sum()),
                "left_tail_vs_lognormal": float(np.interp(S * 0.85, grid, cdf) / max(norm.cdf(np.log(S * 0.85), mu, sd), 1e-9)),
                "curve": [{"price": float(grid[i]), "density": float(dens[i]), "lognormal": float(logn[i]), "cdf": float(cdf[i]),
                           "lognormal_cdf": float(logn_cdf[i])} for i in range(0, len(grid), step)],
                "expirations": ch.get("expirations", []),
                "note": "Market-implied (risk-neutral) distribution: it prices in investors' demand for protection, so it tends to put "
                        "more weight on falls than history would. The lognormal uses the at-the-money volatility only.",
                "source": f"{ch.get('source', 'Option chain')}; smile fitted on out-of-the-money quotes, Breeden–Litzenberger density."}
    return _cached(f"prob:{symbol}:{expiry}", 900, build)


# ── CRPR ─────────────────────────────────────────────────────────────────────
# Damodaran's interest-coverage → rating → default spread table for large non-financial firms (January 2026 update)
SYNTHETIC = [(8.5, "AAA", 0.0059), (6.5, "AA", 0.0070), (5.5, "A+", 0.0092), (4.25, "A", 0.0107), (3.0, "A-", 0.0121),
             (2.5, "BBB", 0.0147), (2.25, "BB+", 0.0183), (2.0, "BB", 0.0220), (1.75, "B+", 0.0280), (1.5, "B", 0.0342),
             (1.25, "B-", 0.0433), (0.8, "CCC", 0.0735), (0.65, "CC", 0.0900), (0.2, "C", 0.1200), (float("-inf"), "D", 0.1600)]


def synthetic_rating(coverage: Optional[float]) -> Tuple[str, float]:
    if coverage is None:
        return "AAA", SYNTHETIC[0][2]                          # no interest expense: no debt burden to rate
    for floor, rating, spread in SYNTHETIC:
        if coverage > floor:
            return rating, spread
    return "D", SYNTHETIC[-1][2]


def credit_profile(symbol: str) -> Dict[str, Any]:
    """A credit view from filings: the rating interest coverage implies (and its default spread and cost of debt), Altman's
    Z-score, Piotroski's F-score, leverage and liquidity — a free stand-in for agency ratings."""
    from api.marketdata.core import _info
    from api.marketdata.extras import _company_only
    symbol = symbol.strip().upper()
    _company_only(symbol, "a credit profile")

    def build():
        from api.providers import sec_edgar as se
        ent = se.resolve(symbol)
        facts = se.company_facts(ent["cik"]) if ent else None
        if not facts:
            raise NotFound(f"{symbol} doesn't file US GAAP statements with the SEC.")
        info = _info(symbol)
        if (info.get("sector") or "") in ("Financial Services",) and any(w in (info.get("industry") or "") for w in ("Bank", "Insurance", "Capital Markets")):
            raise NotFound("Coverage-based credit scores aren't meaningful for banks and insurers (interest is their business).")

        def dur(name, tags=None):
            _, pts = se._pick_tag(facts, tags or se.DURATION[name])
            if not pts:
                return None, []
            t = se.ttm(se.quarterly(pts))
            return (t[-1]["val"] if t else None), se.annual(pts)

        def inst(name, tags=None):
            _, pts = se._pick_tag(facts, tags or se.INSTANT[name])
            return se.instants(pts) if pts else []
        ebit, ebit_a = dur("operating_income")
        interest, int_a = dur("interest_expense")
        rev, rev_a = dur("revenue")
        ni, ni_a = dur("net_income")
        cfo, cfo_a = dur("operating_cash_flow")
        dna, _ = dur("dna")
        gp, gp_a = dur("gross_profit")
        last = lambda rows: rows[-1]["val"] if rows else None
        ta_s, tl_s = inst("total_assets"), inst("total_liabilities")
        ca_s, cl_s = inst("current_assets"), inst("current_liabilities")
        ta, tl, ca, cl = last(ta_s), last(tl_s), last(ca_s), last(cl_s)
        eq, cash = last(inst("equity")), last(inst("cash"))
        debt = (last(inst("long_term_debt")) or 0) + (last(inst("short_term_debt")) or 0)
        re_ = last(inst("retained", ["RetainedEarningsAccumulatedDeficit"]))
        if tl is None and ta is not None and eq is not None:
            tl = ta - eq
        if not ta or ebit is None:
            raise NotFound(f"Not enough balance-sheet and income data in {symbol}'s filings.")
        cov = ebit / interest if interest and interest > 0 else None
        rating, spread = synthetic_rating(cov)
        mcap = _f(info.get("marketCap"))
        z = None
        if all(v is not None for v in (ca, cl, re_, tl, rev)) and tl:
            z = 1.2 * (ca - cl) / ta + 1.4 * re_ / ta + 3.3 * ebit / ta + 0.6 * ((mcap or eq or 0) / tl) + 1.0 * rev / ta
        # Piotroski F-score on the last two fiscal years
        f_items: List[Dict[str, Any]] = []

        def yr(rows, k=-1):
            return rows[k]["val"] if len(rows) >= -k else None

        def at_year(rows, end):
            v = [r["val"] for r in rows if r["end"] <= end]
            return v[-1] if v else None
        if len(ni_a) >= 2 and len(rev_a) >= 2:
            e1, e0 = ni_a[-1]["end"], ni_a[-2]["end"]
            A1, A0 = at_year(ta_s, e1), at_year(ta_s, e0)
            roa1 = ni_a[-1]["val"] / A1 if A1 else None
            roa0 = ni_a[-2]["val"] / A0 if A0 else None
            cfo1 = yr(cfo_a)
            lev1 = (at_year(inst("long_term_debt"), e1) or 0) / A1 if A1 else None
            lev0 = (at_year(inst("long_term_debt"), e0) or 0) / A0 if A0 else None
            cr1 = (at_year(ca_s, e1) or 0) / (at_year(cl_s, e1) or np.nan)
            cr0 = (at_year(ca_s, e0) or 0) / (at_year(cl_s, e0) or np.nan)
            sh = se.shares_series(facts)
            s1, s0 = at_year(sh, e1), at_year(sh, e0)
            gm1 = gp_a[-1]["val"] / rev_a[-1]["val"] if len(gp_a) >= 2 and rev_a[-1]["val"] else None
            gm0 = gp_a[-2]["val"] / rev_a[-2]["val"] if len(gp_a) >= 2 and rev_a[-2]["val"] else None
            at1 = rev_a[-1]["val"] / A1 if A1 else None
            at0 = rev_a[-2]["val"] / A0 if A0 else None
            tests = [("Profitable (ROA > 0)", roa1 is not None and roa1 > 0), ("Operating cash flow positive", cfo1 is not None and cfo1 > 0),
                     ("ROA improved", roa1 is not None and roa0 is not None and roa1 > roa0),
                     ("Cash flow exceeds earnings", cfo1 is not None and ni_a[-1]["val"] is not None and cfo1 > ni_a[-1]["val"]),
                     ("Long-term leverage fell", lev1 is not None and lev0 is not None and lev1 <= lev0),
                     ("Current ratio rose", bool(np.isfinite(cr1) and np.isfinite(cr0) and cr1 > cr0)),
                     ("No new shares issued", s1 is not None and s0 is not None and s1 <= s0 * 1.005),
                     ("Gross margin rose", gm1 is not None and gm0 is not None and gm1 > gm0),
                     ("Asset turnover rose", at1 is not None and at0 is not None and at1 > at0)]
            f_items = [{"test": t, "pass": bool(p)} for t, p in tests]
        ebitda = ebit + (dna or 0)
        y10 = None
        try:
            from api.marketdata.core import quote
            y10 = _f(quote("^TNX")["price"])
        except Exception:                                       # noqa: BLE001
            pass
        coverage_hist = []
        for a in ebit_a[-8:]:
            i = next((x["val"] for x in int_a if x["end"] == a["end"]), None)
            coverage_hist.append({"year_end": a["end"], "coverage": a["val"] / i if i and i > 0 else None,
                                  "rating": synthetic_rating(a["val"] / i if i and i > 0 else None)[0] if i else None})
        return {
            "symbol": symbol, "name": facts.get("entityName"), "synthetic_rating": rating, "default_spread": spread,
            "cost_of_debt": (y10 / 100 + spread) if y10 else None, "interest_coverage": cov, "ebit_ttm": ebit, "interest_ttm": interest,
            "total_debt": debt, "cash": cash, "net_debt": debt - (cash or 0), "ebitda_ttm": ebitda,
            "net_debt_to_ebitda": (debt - (cash or 0)) / ebitda if ebitda > 0 else None,
            "debt_to_equity": debt / eq if eq and eq > 0 else None, "current_ratio": ca / cl if ca and cl else None,
            "altman_z": z, "altman_zone": None if z is None else "safe" if z > 2.99 else "grey" if z > 1.81 else "distress",
            "piotroski": sum(x["pass"] for x in f_items) if f_items else None, "piotroski_tests": f_items,
            "coverage_history": coverage_hist, "scale": [{"rating": r_, "min_coverage": c if c != float("-inf") else None, "spread": s}
                                                         for c, r_, s in SYNTHETIC],
            "note": "Synthetic rating: the rating whose typical interest coverage (operating income ÷ interest, last four quarters) "
                    "matches this company's — Damodaran's method for large non-financial firms; not an agency rating. Altman Z is the "
                    "original public-manufacturer model (safe above 2.99, distress below 1.81); Piotroski F scores nine yes/no tests (8–9 strong, 0–2 weak).",
            "source": "SEC EDGAR XBRL; coverage→rating→spread table from Aswath Damodaran (NYU Stern); market cap Yahoo; 10-year Treasury yield.",
        }
    return _cached(f"crpr:{symbol}", 6 * 3600, build)


# ── LEAG ─────────────────────────────────────────────────────────────────────
ADVISERS = ["Goldman Sachs", "Morgan Stanley", "J.P. Morgan", "BofA Securities", "Citigroup", "Barclays", "Evercore", "Lazard",
            "Centerview", "Jefferies", "UBS", "Deutsche Bank", "Wells Fargo Securities", "RBC Capital Markets", "Guggenheim",
            "PJT Partners", "Moelis", "Houlihan Lokey", "Perella Weinberg", "Qatalyst", "Piper Sandler", "Raymond James", "Stifel",
            "Keefe, Bruyette", "Truist Securities", "BMO Capital Markets", "TD Cowen", "Allen & Company", "Lincoln International",
            "William Blair", "Kroll", "Duff & Phelps", "Needham", "Leerink", "Cantor Fitzgerald"]


def league_table(days: int = 365) -> Dict[str, Any]:
    """Banks ranked by the number of US public-company mergers in which they gave the fairness opinion (named under
    'Opinion of …' in a merger proxy or S-4 registration) over the period, with the companies."""
    days = max(90, min(int(days), 730))

    def build():
        import concurrent.futures as cf
        import requests
        from api.providers.sec_edgar import USER_AGENT
        end = date.today()
        start = end - timedelta(days=days)

        def one(bank):
            try:
                r = requests.get("https://efts.sec.gov/LATEST/search-index",
                                 params={"q": f'"Opinion of {bank}"', "forms": "DEFM14A,S-4,PREM14A,SC 14D9",
                                         "dateRange": "custom", "startdt": str(start), "enddt": str(end)},
                                 headers={"User-Agent": USER_AGENT}, timeout=40)
                r.raise_for_status()
                hits = r.json()["hits"]["hits"]
            except Exception as e:                              # noqa: BLE001 — one bank missing is shown as none
                logger.info("leag %s: %s", bank, e)
                return bank, None
            deals: Dict[str, Dict[str, Any]] = {}
            for h in hits:
                src = h["_source"]
                name = re.sub(r"\s+\(CIK.*$", "", (src.get("display_names") or ["?"])[0]).strip()
                cik = (src.get("ciks") or ["?"])[0]
                d = deals.setdefault(cik, {"company": name, "first_filed": src.get("file_date"), "forms": set()})
                d["forms"].add(src.get("form"))
                d["first_filed"] = min(d["first_filed"] or "9", src.get("file_date") or "9")
            return bank, [{"company": v["company"], "filed": v["first_filed"], "forms": sorted(f for f in v["forms"] if f)} for v in deals.values()]
        with cf.ThreadPoolExecutor(4) as ex:
            got = list(ex.map(one, ADVISERS))
        rows = [{"bank": b, "deals": len(d), "companies": sorted(d, key=lambda x: x["filed"] or "", reverse=True)}
                for b, d in got if d]
        if not rows:
            raise Upstream("SEC full-text search unavailable right now.")
        rows.sort(key=lambda r: -r["deals"])
        for i, r in enumerate(rows):
            r["rank"] = i + 1
        return {"from": str(start), "to": str(end), "rows": rows, "missing": [b for b, d in got if d is None],
                "note": "Counts companies whose merger proxy, S-4 or tender-offer response contains an 'Opinion of <bank>' section — "
                        "the bank that gave a fairness opinion to the board. Deal values aren't in the search index, so this ranks "
                        "by number of deals; both sides of a deal can each count when both are US-listed. Search covers the most "
                        "recent 100 matching documents per bank.",
                "source": "SEC EDGAR full-text search (efts.sec.gov)."}
    return _cached(f"leag:{days}", 12 * 3600, build)


# ── SPF ──────────────────────────────────────────────────────────────────────
SPF_URL = "https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/survey-of-professional-forecasters/data-files/files/{}"
SPF_VARS = {"gdp": ("Median_RGDP_Growth.xlsx", "DRGDP", "Real GDP growth (annualised q/q)"),
            "cpi": ("Median_CPI_Level.xlsx", "CPI", "CPI inflation (annualised q/q)"),
            "core_cpi": ("Median_CORECPI_Level.xlsx", "CORECPI", "Core CPI inflation (annualised q/q)"),
            "unemployment": ("Median_UNEMP_Level.xlsx", "UNEMP", "Unemployment rate"),
            "tbond": ("Median_TBOND_Level.xlsx", "TBOND", "10-year Treasury yield"),
            "tbill": ("Median_TBILL_Level.xlsx", "TBILL", "3-month T-bill rate")}


def spf_consensus() -> Dict[str, Any]:
    """The Philadelphia Fed's Survey of Professional Forecasters: median forecasts for the current quarter, the next four
    and the annual averages, with the change since the previous survey."""
    def build():
        import requests
        out, survey = {}, None
        for key, (file, stem, label) in SPF_VARS.items():
            try:
                r = requests.get(SPF_URL.format(file), headers=UA, timeout=40)
                r.raise_for_status()
                df = pd.read_excel(io.BytesIO(r.content))
            except Exception as e:                              # noqa: BLE001 — one series missing is left out
                logger.info("spf %s: %s", key, e)
                continue
            df = df.dropna(subset=["YEAR", "QUARTER"])
            now, prev = df.iloc[-1], df.iloc[-2]
            y, q = int(now["YEAR"]), int(now["QUARTER"])
            survey = survey or (y, q)
            quarters = []
            for i in range(2, 7):
                col = f"{stem}{i}"
                if col in df:
                    qi = q + i - 2
                    qy, qq = y + (qi - 1) // 4, (qi - 1) % 4 + 1
                    pv = _f(prev.get(f"{stem}{i + 1}"))                  # the same calendar quarter in the previous survey
                    quarters.append({"period": f"{qy} Q{qq}", "median": _f(now[col]), "previous_survey": pv})
            annual = [{"year": y + j, "median": _f(now.get(f"{stem}{c}")), "previous_survey": None}
                      for j, c in enumerate("ABC") if f"{stem}{c}" in df]
            for a in annual:                                     # last survey's view of the same year
                y0 = int(prev["YEAR"])
                off = a["year"] - y0
                if 0 <= off <= 2 and f"{stem}{'ABC'[off]}" in df:
                    a["previous_survey"] = _f(prev.get(f"{stem}{'ABC'[off]}"))
            out[key] = {"label": label, "quarters": quarters, "annual": annual}
        if not out:
            raise Upstream("The Survey of Professional Forecasters files are unavailable right now.")
        return {"survey": f"{survey[0]} Q{survey[1]}" if survey else None, "series": out,
                "note": "Median of about 35 professional forecasters, surveyed each quarter by the Federal Reserve Bank of Philadelphia "
                        "— the free equivalent of an economist consensus survey. 'Previous' is the last survey's forecast for the same period.",
                "source": "Federal Reserve Bank of Philadelphia, Survey of Professional Forecasters."}
    return _cached("spf:v1", 12 * 3600, build)
