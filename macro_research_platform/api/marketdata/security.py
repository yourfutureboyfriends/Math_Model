"""
Single-security functions for the Markets mode (Bloomberg mnemonics in brackets):

  earnings(s)    [ERN/EE]  reported vs estimated EPS history, upcoming date, consensus
                           EPS/revenue by period, estimate revisions and trend
  analysts(s)    [ANR]     rating distribution over time, price targets, rating changes
  holders(s)     [HDS]     ownership split, top institutions and funds, insider trades
  dividends(s)   [DVD]     payments, annual totals, growth, yield, payout, splits
  options(s, e)  [OMON]    chain with Black–Scholes Greeks, IV smile, term structure,
                           put/call ratios, max pain
  comps(s)       [RV]      same-industry peers across the main markets, multiples in USD
  history(s)     [HP]      OHLCV table
  compare(ss)    [COMP]    total-return comparison, stats and correlations
  beta(s, b)     [BETA]    regression beta / alpha / R², rolling beta, scatter
  (DCF lives in api/marketdata/dcf.py)

Sources: Yahoo Finance (prices, estimates, holders, options); SEC EDGAR for US free cash
flow when available. Missing data stays missing.
"""
from __future__ import annotations

import concurrent.futures as cf
import math
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from api.marketdata.core import (MAIN_EXCHANGES, NotFound, Upstream, _cached, _f, _info, _norm, div_yield, to_usd, usd_to_local)


def _tk(symbol: str):
    import yfinance as yf
    return yf.Ticker(symbol.strip().upper())


def _df_records(df: Optional[pd.DataFrame], index_name: str = "index", limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return []
    d = df.copy()
    if limit:
        d = d.head(limit)
    out = []
    for idx, row in d.iterrows():
        rec = {index_name: idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)}
        for k, v in row.items():
            if isinstance(v, (pd.Timestamp, datetime, date)):
                rec[str(k)] = v.strftime("%Y-%m-%d")
            elif isinstance(v, (int, float, np.floating, np.integer)):
                rec[str(k)] = _f(v)
            else:
                rec[str(k)] = None if v is None or (isinstance(v, float) and math.isnan(v)) else str(v)
        out.append(rec)
    return out


# ── ERN / EE ─────────────────────────────────────────────────────────────────
def earnings(symbol: str) -> Dict[str, Any]:
    s = symbol.strip().upper()

    def fetch():
        t = _tk(s)
        try:
            dates = t.earnings_dates
        except Exception:
            dates = None
        hist = []
        upcoming = []
        if dates is not None and not dates.empty:
            for idx, r in dates.iterrows():
                rec = {"date": idx.strftime("%Y-%m-%d"), "eps_estimate": _f(r.get("EPS Estimate")),
                       "eps_reported": _f(r.get("Reported EPS")), "surprise_pct": _f(r.get("Surprise(%)"))}
                (hist if rec["eps_reported"] is not None else upcoming).append(rec)
        est = {}
        for key, attr in (("eps", "earnings_estimate"), ("revenue", "revenue_estimate"), ("eps_trend", "eps_trend"),
                          ("eps_revisions", "eps_revisions"), ("growth", "growth_estimates")):
            try:
                est[key] = _df_records(getattr(t, attr), "period")
            except Exception:
                est[key] = []
        beats = [h for h in hist if h["surprise_pct"] is not None]
        return {"symbol": s, "history": hist[:16], "upcoming": sorted(upcoming, key=lambda x: x["date"])[:2],
                "estimates": est, "beat_rate": round(sum(1 for h in beats if h["surprise_pct"] > 0) / len(beats), 3) if beats else None,
                "avg_surprise_pct": round(float(np.mean([h["surprise_pct"] for h in beats])), 2) if beats else None,
                "currency": _info(s).get("financialCurrency") or _info(s).get("currency"), "source": "Yahoo Finance (analyst consensus)"}
    out = _cached(f"ern:{s}", 3600, fetch)
    if not out["history"] and not out["estimates"].get("eps"):
        raise NotFound(f"No earnings data for {s} (not a covered company).")
    return out


# ── ANR ──────────────────────────────────────────────────────────────────────
def analysts(symbol: str) -> Dict[str, Any]:
    s = symbol.strip().upper()

    def fetch():
        t = _tk(s)
        try:
            summ = _df_records(t.recommendations_summary, "row")
        except Exception:
            summ = []
        try:
            targets = {k: _f(v) for k, v in (t.analyst_price_targets or {}).items()}
        except Exception:
            targets = {}
        try:
            ud = t.upgrades_downgrades
            changes = _df_records(ud.sort_index(ascending=False), "date", limit=40) if ud is not None else []
        except Exception:
            changes = []
        return {"symbol": s, "summary": summ, "targets": targets, "changes": changes,
                "recommendation": _info(s).get("recommendationKey"), "analysts": _info(s).get("numberOfAnalystOpinions"),
                # Yahoo's consensus mean on a 1 (strong buy) … 5 (strong sell) scale — a fallback when
                # the rating breakdown endpoint fails (it intermittently returns 401).
                "recommendation_mean": _f(_info(s).get("recommendationMean")),
                "currency": _info(s).get("currency"), "source": "Yahoo Finance"}
    out = _cached(f"anr:{s}", 3600, fetch)
    if not out["summary"] and not out["changes"]:            # partial failure: retry soon, don't keep it for an hour
        from api.marketdata.core import _cache, _lock
        with _lock:
            ts, val = _cache.get(f"anr:{s}", (0, None))
            _cache[f"anr:{s}"] = (ts - 3600 + 120, val)
    if not out["summary"] and not out["targets"] and not out["changes"]:
        raise NotFound(f"No analyst coverage data for {s}.")
    return out


# ── HDS ──────────────────────────────────────────────────────────────────────
def holders(symbol: str) -> Dict[str, Any]:
    s = symbol.strip().upper()

    def fetch():
        t = _tk(s)
        major = {}
        try:
            mh = t.major_holders
            if mh is not None and not mh.empty:
                major = {str(k): _f(v) for k, v in mh["Value"].items()}
        except Exception:
            pass

        def holders_table(attr):
            try:
                return _df_records(getattr(t, attr), "row")
            except Exception:
                return []
        try:
            ins = t.insider_transactions
            insiders = _df_records(ins.head(30), "row") if ins is not None else []
        except Exception:
            insiders = []
        return {"symbol": s, "breakdown": major, "institutions": holders_table("institutional_holders"),
                "funds": holders_table("mutualfund_holders"), "insiders": insiders, "source": "Yahoo Finance (13F / Form 4)"}
    out = _cached(f"hds:{s}", 6 * 3600, fetch)
    if not out["breakdown"] and not out["institutions"]:
        raise NotFound(f"No ownership data for {s}.")
    return out


# ── DVD ──────────────────────────────────────────────────────────────────────
def dividends(symbol: str) -> Dict[str, Any]:
    s = symbol.strip().upper()

    def fetch():
        t = _tk(s)
        try:
            dv = t.dividends
        except Exception as e:
            raise Upstream(f"Dividend data unavailable: {e}")
        try:
            sp = t.splits
        except Exception:
            sp = pd.Series(dtype=float)
        i = _info(s)
        pays = [{"date": d.strftime("%Y-%m-%d"), "amount": _f(v)} for d, v in dv.items()][::-1] if dv is not None else []
        annual = {}
        if dv is not None and len(dv):
            yearly = dv.groupby(dv.index.year).sum()
            this_year = datetime.now().year
            annual = {int(y): round(float(v), 6) for y, v in yearly.items() if y < this_year}
        ys = sorted(annual)
        growth = {}
        for n in (1, 3, 5, 10):
            if len(ys) > n and annual[ys[-1 - n]] > 0:
                growth[f"{n}y"] = round((annual[ys[-1]] / annual[ys[-1 - n]]) ** (1 / n) - 1, 4)
        # Consecutive increases judged on each year's MEDIAN payment: robust to payment timing
        # (an extra or missing payment) and to one bad or special payment in the record.
        streak = 0
        if dv is not None and len(dv):
            peak = dv.groupby(dv.index.year).median()
            py = [y for y in sorted(peak.index) if y < datetime.now().year]
            for a, b in zip(py[::-1][1:], py[::-1][:-1]):
                if peak[b] > peak[a] * 1.0001:
                    streak += 1
                else:
                    break
        dy = div_yield(i)
        return {"symbol": s, "payments": pays[:40], "annual": [{"year": y, "total": annual[y]} for y in ys[-20:]],
                "growth": growth, "consecutive_increases": streak, "currency": i.get("currency"),
                "dividend_yield": dy,
                "payout_ratio": _f(i.get("payoutRatio")), "ex_dividend_date": i.get("exDividendDate"),
                "forward_rate": _f(i.get("dividendRate")),
                "splits": [{"date": d.strftime("%Y-%m-%d"), "ratio": _f(v)} for d, v in sp.items()][::-1] if sp is not None else [],
                "source": "Yahoo Finance"}
    return _cached(f"dvd:{s}", 6 * 3600, fetch)


# ── OMON ─────────────────────────────────────────────────────────────────────
def _norm_cdf(x):
    return 0.5 * (1 + np.vectorize(math.erf)(x / math.sqrt(2)))


def bs_greeks(S: float, K: np.ndarray, T: float, r: float, q: float, iv: np.ndarray, call: bool) -> Dict[str, np.ndarray]:
    """Black–Scholes–Merton Greeks with continuous dividend yield q. Theta per calendar day,
    vega per 1 vol point, rho per 1% rate move."""
    K = np.asarray(K, float)
    iv = np.asarray(iv, float)
    T = max(T, 1 / 365)
    with np.errstate(all="ignore"):
        d1 = (np.log(S / K) + (r - q + 0.5 * iv ** 2) * T) / (iv * math.sqrt(T))
        d2 = d1 - iv * math.sqrt(T)
        pdf = np.exp(-0.5 * d1 ** 2) / math.sqrt(2 * math.pi)
        Nd1, Nd2 = _norm_cdf(d1), _norm_cdf(d2)
        if call:
            delta = math.exp(-q * T) * Nd1
            theta = (-S * math.exp(-q * T) * pdf * iv / (2 * math.sqrt(T)) - r * K * math.exp(-r * T) * Nd2
                     + q * S * math.exp(-q * T) * Nd1) / 365
            rho = K * T * math.exp(-r * T) * Nd2 / 100
        else:
            delta = -math.exp(-q * T) * _norm_cdf(-d1)
            theta = (-S * math.exp(-q * T) * pdf * iv / (2 * math.sqrt(T)) + r * K * math.exp(-r * T) * _norm_cdf(-d2)
                     - q * S * math.exp(-q * T) * _norm_cdf(-d1)) / 365
            rho = -K * T * math.exp(-r * T) * _norm_cdf(-d2) / 100
        gamma = math.exp(-q * T) * pdf / (S * iv * math.sqrt(T))
        vega = S * math.exp(-q * T) * pdf * math.sqrt(T) / 100
    clean = lambda a: np.where(np.isfinite(a) & (iv > 0), a, np.nan)
    return {"delta": clean(delta), "gamma": clean(gamma), "theta": clean(theta), "vega": clean(vega), "rho": clean(rho)}


def bs_price(S, K, T, r, q, iv, call):
    K = np.asarray(K, float)
    iv = np.asarray(iv, float)
    with np.errstate(all="ignore"):
        d1 = (np.log(S / K) + (r - q + 0.5 * iv ** 2) * T) / (iv * math.sqrt(T))
        d2 = d1 - iv * math.sqrt(T)
        if call:
            return S * math.exp(-q * T) * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
        return K * math.exp(-r * T) * _norm_cdf(-d2) - S * math.exp(-q * T) * _norm_cdf(-d1)


def implied_vol(price: np.ndarray, S: float, K: np.ndarray, T: float, r: float, q: float, call: bool) -> np.ndarray:
    """Vectorised bisection on Black–Scholes–Merton (60 steps, 0.1%–500% vol). NaN where the
    price is below intrinsic value or missing."""
    price, K = np.asarray(price, float), np.asarray(K, float)
    lo, hi = np.full(K.shape, 0.001), np.full(K.shape, 5.0)
    intrinsic = np.maximum(0, (S * math.exp(-q * T) - K * math.exp(-r * T)) if call else (K * math.exp(-r * T) - S * math.exp(-q * T)))
    ok = np.isfinite(price) & (price > intrinsic + 1e-6) & (price < (S if call else K))
    for _ in range(60):
        mid = (lo + hi) / 2
        p = bs_price(S, K, T, r, q, mid, call)
        hi = np.where(p > price, mid, hi)
        lo = np.where(p > price, lo, mid)
    return np.where(ok, (lo + hi) / 2, np.nan)


def _risk_free() -> float:
    try:
        from api.marketdata.core import quote
        y = quote("^IRX")["price"]
        return y / 100 if y else 0.04
    except Exception:
        return 0.04


def options(symbol: str, expiry: Optional[str] = None) -> Dict[str, Any]:
    s = symbol.strip().upper()
    t = _tk(s)
    try:
        exps = list(t.options or [])
    except Exception as e:
        raise Upstream(f"Options unavailable: {e}")
    if not exps:
        raise NotFound(f"No listed options for {s} on Yahoo (options are mainly US-listed).")
    if expiry in exps:
        exp = expiry
    else:                       # default to the first expiry at least 5 days out (0-DTE IVs are unusable)
        today = pd.Timestamp.now().normalize()
        exp = next((e for e in exps if (pd.Timestamp(e) - today).days >= 5), exps[-1])

    def fetch():
        i = _info(s)
        S = _f(i.get("regularMarketPrice")) or _f(i.get("previousClose"))
        if S is None:
            raise NotFound(f"No underlying price for {s}.")
        q = div_yield(i) or 0.0                 # continuous dividend yield for Black-Scholes-Merton
        r = _risk_free()
        try:
            ch = t.option_chain(exp)
        except Exception as e:
            raise Upstream(f"Option chain unavailable: {e}")
        T = max((pd.Timestamp(exp) - pd.Timestamp.now().normalize()).days, 0) / 365 + 1 / 365
        sides = {}
        for name, df, call in (("calls", ch.calls, True), ("puts", ch.puts, False)):
            if df is None or df.empty:
                sides[name] = []
                continue
            # Our own IV from the bid/ask mid (last trade if no two-sided quote): Yahoo's IV field is
            # stale or a ~1e-5 placeholder outside US hours.
            bid, ask, last = (df[c].astype(float).to_numpy() for c in ("bid", "ask", "lastPrice"))
            mid = np.where((bid > 0) & (ask > 0) & (ask >= bid), (bid + ask) / 2, last)
            ivs = implied_vol(mid, S, df["strike"].to_numpy(), T, r, q, call)
            g = bs_greeks(S, df["strike"].to_numpy(), T, r, q, np.nan_to_num(ivs), call)
            rows = []
            for j, (_, x) in enumerate(df.iterrows()):
                rows.append({"contract": x.get("contractSymbol"), "strike": _f(x.get("strike")), "last": _f(x.get("lastPrice")),
                             "bid": _f(x.get("bid")), "ask": _f(x.get("ask")), "change_pct": _f(x.get("percentChange")),
                             "volume": _f(x.get("volume")), "open_interest": _f(x.get("openInterest")),
                             "iv": _f(ivs[j]), "itm": bool(x.get("inTheMoney")),
                             **{k: _f(v[j]) for k, v in g.items()}})
            sides[name] = rows
        all_rows = sides["calls"] + sides["puts"]
        two_sided = sum(1 for r in all_rows if (r["bid"] or 0) > 0 and (r["ask"] or 0) > 0)
        stale = bool(all_rows) and two_sided < 0.3 * len(all_rows)
        oi_c = sum(r["open_interest"] or 0 for r in sides["calls"])
        oi_p = sum(r["open_interest"] or 0 for r in sides["puts"])
        vol_c = sum(r["volume"] or 0 for r in sides["calls"])
        vol_p = sum(r["volume"] or 0 for r in sides["puts"])
        strikes = sorted({r["strike"] for r in sides["calls"] + sides["puts"] if r["strike"] is not None})
        pain = None
        if strikes:
            def payout(k):
                return (sum(max(0.0, k - c["strike"]) * (c["open_interest"] or 0) for c in sides["calls"])
                        + sum(max(0.0, p["strike"] - k) * (p["open_interest"] or 0) for p in sides["puts"]))
            pain = min(strikes, key=payout)
        # IV smile (OTM side at each strike) and ATM IV
        smile = []
        for k in strikes:
            side = "puts" if k < S else "calls"
            row = next((x for x in sides[side] if x["strike"] == k), None)
            if row and row["iv"] and 0.01 < row["iv"] < 5:
                smile.append({"strike": k, "iv": row["iv"], "moneyness": round(k / S, 4)})
        atm = min(smile, key=lambda x: abs(x["strike"] - S)) if smile else None
        return {"symbol": s, "underlying": S, "currency": i.get("currency"), "expiry": exp, "expirations": exps,
                "days": int(round(T * 365)), "rate": r, "dividend_yield": q, "calls": sides["calls"], "puts": sides["puts"],
                "put_call_oi": round(oi_p / oi_c, 3) if oi_c else None, "put_call_volume": round(vol_p / vol_c, 3) if vol_c else None,
                "max_pain": pain, "atm_iv": atm["iv"] if atm else None, "smile": smile,
                "quotes_stale": stale,
                "warning": ("No live two-sided quotes (US options market closed): implied vols and Greeks use the last "
                            "trades, which may be out of line with the current underlying price.") if stale else None,
                "expected_move": round(S * atm["iv"] * math.sqrt(T), 4) if atm else None,
                "source": "Yahoo Finance options (15-min delayed). IV solved from the bid/ask mid and Greeks via "
                          "Black–Scholes–Merton (European approximation for US-style options)."}
    return _cached(f"opt:{s}:{exp}", 300, fetch)


def iv_term_structure(symbol: str, n: int = 8) -> List[Dict[str, Any]]:
    s = symbol.strip().upper()

    def fetch():
        exps = list(_tk(s).options or [])[:n]
        out = []
        for e in exps:
            try:
                o = options(s, e)
                if o["atm_iv"]:
                    out.append({"expiry": e, "days": o["days"], "atm_iv": o["atm_iv"]})
            except Exception:
                continue
        return out
    return _cached(f"ivts:{s}", 900, fetch)


# ── RV (comps) ───────────────────────────────────────────────────────────────
HOME_REGIONS = {"CN": ["cn", "hk"], "HK": ["hk"], "GB": ["gb"], "US": ["us"], "NL": ["nl", "fr", "it"], "IE": ["us", "gb"]}


def _screen_industry(name: Optional[str]) -> Optional[str]:
    """Company-profile industry → the screener's label ('Software - Application' →
    'Software—Application'); fuzzy match as a fallback."""
    if not name:
        return None
    import difflib
    from yfinance.const import EQUITY_SCREENER_EQ_MAP
    valid = set()
    for v in EQUITY_SCREENER_EQ_MAP["industry"].values():
        valid |= set(v) if isinstance(v, (set, list, tuple)) else {v}
    key = lambda x: x.lower().replace(" - ", "—").replace("-", "—").replace(" ", "")
    by_key = {key(v): v for v in valid}
    if key(name) in by_key:
        return by_key[key(name)]
    m = difflib.get_close_matches(key(name), list(by_key), n=1, cutoff=0.8)
    return by_key[m[0]] if m else None


def _foreign_line(symbol: str) -> bool:
    """Exchange lines that list foreign shares: Borsa Italiana's '1xxx.MI', London's '0xxx.L'."""
    base, _, suf = symbol.partition(".")
    return (suf == "MI" and base[:1] == "1" and not base.isdigit()) or (suf == "L" and len(base) == 4 and base[0] == "0")


def _home_countries() -> Dict[str, str]:
    """Normalised company name → headquarters country, from the global universe."""
    def build():
        try:
            from api import global_universe as gu
            u = gu.load(rebuild_if_stale=False)
            items = u if isinstance(u, list) else (u.get("stocks") or [])
            return {_norm(x.get("name")): str(x.get("country")) for x in items if x.get("name") and x.get("country")}
        except Exception:
            return {}
    return _cached("home_countries", 86400, build)


PEER_REGIONS = ["us", "jp", "gb", "de", "fr", "nl", "ch", "kr", "tw", "cn", "hk", "in", "ca", "au", "se", "it", "es"]


def comps(symbol: str, max_peers: int = 12) -> Dict[str, Any]:
    s = symbol.strip().upper()
    i = _info(s)
    industry = _screen_industry(i.get("industry"))
    if not industry:
        raise NotFound(f"{s} has no industry classification the screener knows — comps need a company.")

    def fetch():
        import yfinance as yf
        from yfinance import EquityQuery as Q

        def region(rg):
            fx = usd_to_local(rg)
            q = Q("and", [Q("eq", ["region", rg]), Q("is-in", ["exchange", *MAIN_EXCHANGES[rg]]),
                          Q("eq", ["industry", industry]), Q("gt", ["intradaymarketcap", 1e9 * fx])])
            for attempt in range(2):                      # Yahoo rate-limits bursts: retry once
                try:
                    res = yf.screen(q, sortField="intradaymarketcap", sortAsc=False, size=25)
                    return [(rg, x, to_usd(_f(x.get("marketCap")), x.get("currency")) or 0) for x in res.get("quotes") or []
                            if not _foreign_line(x.get("symbol", ""))]
                except Exception:
                    time.sleep(1.0)
            return []
        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            found = [r for rows in ex.map(region, PEER_REGIONS) for r in rows]
        home = _home_countries()
        groups: Dict[str, List] = {}
        for rg, x, mcap_usd in found:
            n = _norm(x.get("longName") or x.get("shortName"))
            if n:
                groups.setdefault(n, []).append((rg, x, mcap_usd))
        subject = _norm(i.get("longName") or i.get("shortName"))
        peers = []
        for n, cands in groups.items():
            if n == subject:                                   # the subject's other listings
                continue
            hq = home.get(n)
            pref = [c for c in cands if hq and c[0] in HOME_REGIONS.get(hq, [hq.lower()])]
            rg, x, mcap_usd = max(pref or cands, key=lambda c: c[2])
            peers.append((x["symbol"], max(c[2] for c in cands)))
        peers.sort(key=lambda p: -p[1])
        syms = [s] + [p for p, _ in peers if p != s][:max_peers]

        def row(sym):
            try:
                ii = _info(sym)
            except Exception:
                return None
            ccy = ii.get("currency")
            mcap = _f(ii.get("marketCap"))
            dy = div_yield(ii)
            return {"symbol": sym, "name": ii.get("longName") or ii.get("shortName"), "country": ii.get("country"),
                    "currency": ccy, "market_cap_usd": to_usd(mcap, ccy),
                    "pe": _f(ii.get("trailingPE")), "forward_pe": _f(ii.get("forwardPE")), "ev_ebitda": _f(ii.get("enterpriseToEbitda")),
                    "price_to_book": _f(ii.get("priceToBook")), "price_to_sales": _f(ii.get("priceToSalesTrailing12Months")),
                    "gross_margin": _f(ii.get("grossMargins")), "operating_margin": _f(ii.get("operatingMargins")),
                    "roe": _f(ii.get("returnOnEquity")), "revenue_growth": _f(ii.get("revenueGrowth")),
                    "dividend_yield": dy, "beta": _f(ii.get("beta")),
                    "subject": sym == s}
        with cf.ThreadPoolExecutor(max_workers=8) as ex:
            rows = [r for r in ex.map(row, syms) if r]
        med = {}
        for k in ("pe", "forward_pe", "ev_ebitda", "price_to_book", "price_to_sales", "gross_margin", "operating_margin", "roe",
                  "revenue_growth", "dividend_yield"):
            vals = [r[k] for r in rows if not r["subject"] and r[k] is not None and (k not in ("pe", "forward_pe", "ev_ebitda") or 0 < r[k] < 500)]
            med[k] = float(np.median(vals)) if vals else None
        return {"symbol": s, "industry": industry, "sector": i.get("sector"), "rows": rows, "peer_median": med,
                "source": "Yahoo Finance — largest same-industry companies on each market's main exchange (≥ $1bn)"}
    return _cached(f"rv:{s}", 6 * 3600, fetch)


# ── HP / COMP / BETA ─────────────────────────────────────────────────────────
def _closes(symbols: List[str], period: str = "5y", interval: str = "1d") -> pd.DataFrame:
    import yfinance as yf
    try:
        df = yf.download(symbols, period=period, interval=interval, auto_adjust=True, group_by="ticker", threads=True, progress=False)
    except Exception as e:
        raise Upstream(f"Price history unavailable: {e}")
    out = {}
    for sym in symbols:
        try:
            c = (df[sym] if isinstance(df.columns, pd.MultiIndex) else df)["Close"].dropna()
            if len(c) > 1:
                out[sym] = c
        except Exception:
            continue
    if not out:
        raise NotFound("No price history for those symbols.")
    return pd.DataFrame(out)


def history(symbol: str, period: str = "1y", interval: str = "1d") -> Dict[str, Any]:
    import yfinance as yf
    s = symbol.strip().upper()
    if interval not in ("1d", "1wk", "1mo") or period not in ("1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max"):
        raise NotFound("period 1mo…max, interval 1d/1wk/1mo")

    def fetch():
        try:
            df = yf.Ticker(s).history(period=period, interval=interval, auto_adjust=False)
        except Exception as e:
            raise Upstream(f"History unavailable: {e}")
        if df is None or df.empty:
            raise NotFound(f"No price history for {s}.")
        rows = [{"date": d.strftime("%Y-%m-%d"), "open": _f(r["Open"]), "high": _f(r["High"]), "low": _f(r["Low"]),
                 "close": _f(r["Close"]), "adj_close": None, "volume": _f(r["Volume"])} for d, r in df.iterrows()]
        for k in range(1, len(rows)):
            if rows[k]["close"] and rows[k - 1]["close"]:
                rows[k]["change_pct"] = rows[k]["close"] / rows[k - 1]["close"] - 1
        return {"symbol": s, "period": period, "interval": interval, "rows": rows[::-1], "currency": _info(s).get("currency"),
                "note": "Prices as traded (not adjusted for dividends); splits are applied.", "source": "Yahoo Finance"}
    return _cached(f"hp:{s}:{period}:{interval}", 900, fetch)


def compare(symbols: List[str], period: str = "5y") -> Dict[str, Any]:
    syms = [x.strip().upper() for x in symbols if x.strip()][:8]
    if len(syms) < 1:
        raise NotFound("Give at least one symbol.")

    def fetch():
        px = _closes(syms, period)
        px = px.dropna(how="all").ffill().dropna()
        if len(px) < 20:
            raise NotFound("Not enough overlapping history.")
        rets = px.pct_change().dropna()
        yrs = max((px.index[-1] - px.index[0]).days / 365.25, 1 / 365)
        stats = []
        for c in px.columns:
            eq = px[c] / px[c].iloc[0]
            dd = eq / eq.cummax() - 1
            vol = float(rets[c].std() * math.sqrt(252))
            cagr = float(eq.iloc[-1] ** (1 / yrs) - 1)
            stats.append({"symbol": c, "total_return": float(eq.iloc[-1] - 1), "cagr": cagr, "vol": vol,
                          "sharpe": cagr / vol if vol else None, "max_drawdown": float(dd.min())})
        step = max(1, len(px) // 600)
        curve = [{"date": d.strftime("%Y-%m-%d"), **{c: round(float(px[c].iloc[k] / px[c].iloc[0]), 4) for c in px.columns}}
                 for k, d in enumerate(px.index) if k % step == 0 or k == len(px) - 1]
        corr = rets.corr()
        return {"symbols": list(px.columns), "missing": [x for x in syms if x not in px.columns], "period": period,
                "start": px.index[0].strftime("%Y-%m-%d"), "curve": curve, "stats": stats,
                "correlation": {a: {b: round(float(corr.loc[a, b]), 3) for b in px.columns} for a in px.columns},
                "note": "Total return (dividends reinvested, adjusted closes), each rebased to 1 on the first common date; "
                        "returns in each instrument's own currency.", "source": "Yahoo Finance"}
    return _cached(f"comp:{','.join(syms)}:{period}", 900, fetch)


def beta(symbol: str, benchmark: str = "^GSPC", period: str = "2y", freq: str = "W") -> Dict[str, Any]:
    s, b = symbol.strip().upper(), benchmark.strip().upper()

    def fetch():
        px = _closes([s, b], period).dropna()
        if s not in px or b not in px:
            raise NotFound("Missing history for the security or benchmark.")
        px = px.resample({"D": "B", "W": "W-FRI", "M": "ME"}[freq]).last().dropna() if freq != "D" else px
        r = px.pct_change().dropna()
        if len(r) < 20:
            raise NotFound("Not enough overlapping history.")
        x, y = r[b].to_numpy(), r[s].to_numpy()
        X = np.column_stack([np.ones_like(x), x])
        coef, res, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ coef
        n = len(y)
        se = math.sqrt((resid @ resid) / (n - 2) / ((x - x.mean()) @ (x - x.mean())))
        r2 = 1 - resid.var() / y.var() if y.var() > 0 else None
        ppy = {"D": 252, "W": 52, "M": 12}[freq]
        win = {"D": 126, "W": 26, "M": 12}[freq]
        rb = (r[s].rolling(win).cov(r[b]) / r[b].rolling(win).var()).dropna()
        return {"symbol": s, "benchmark": b, "period": period, "frequency": freq, "observations": n,
                "beta": float(coef[1]), "beta_se": se, "alpha_annual": float(coef[0] * ppy), "r2": r2,
                "correlation": float(np.corrcoef(x, y)[0, 1]), "adjusted_beta": float(0.67 * coef[1] + 0.33),
                "scatter": [{"x": round(float(a), 5), "y": round(float(c), 5)} for a, c in zip(x[-260:], y[-260:])],
                "rolling": [{"date": d.strftime("%Y-%m-%d"), "beta": round(float(v), 3)} for d, v in rb.items()],
                "note": "OLS of the security's returns on the benchmark's. Adjusted beta = 0.67 × raw + 0.33 (Blume, as on Bloomberg).",
                "source": "Yahoo Finance"}
    return _cached(f"beta:{s}:{b}:{period}:{freq}", 3600, fetch)
