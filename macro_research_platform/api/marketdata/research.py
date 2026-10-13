"""
Research functions built on free official data:

  filings(symbol)        CF    — a company's SEC filings (10-K, 10-Q, 8-K, 6-K, proxy, S-1 …) with 8-K
                                 items decoded and flagged, and the stock's reaction on each filing day
  filing_text(url)       CF    — the filing (and an 8-K's press release) as plain text, read in the terminal
  credit()               CRED  — ICE BofA option-adjusted spreads by rating and region, percentiles, signals
  factor_exposure(sym)   FAC   — Fama–French 5 + momentum loadings, full period and rolling one-year
  portfolio_risk(rows)   PORT  — exposures, volatility, VaR / ES, drawdown, risk contributions,
                                 correlations, factor loadings, and stress tests (factor shocks and
                                 historical replays)
"""
from __future__ import annotations

import concurrent.futures as cf
import logging
import math
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

from api.marketdata.core import MINOR_UNITS, NotFound, Upstream, _cached, _f, _info, to_usd

logger = logging.getLogger(__name__)
NY = ZoneInfo("America/New_York")


# ── CF: company filings ──────────────────────────────────────────────────────
ITEMS_8K = {
    "1.01": "Material agreement signed", "1.02": "Material agreement terminated", "1.03": "Bankruptcy or receivership",
    "1.04": "Mine safety", "1.05": "Cybersecurity incident", "2.01": "Acquisition or disposal completed", "2.02": "Results (earnings)",
    "2.03": "New debt or obligation", "2.04": "Debt acceleration / triggering event", "2.05": "Exit or restructuring costs",
    "2.06": "Impairment", "3.01": "Delisting notice / listing failure", "3.02": "Unregistered share sale", "3.03": "Shareholder rights changed",
    "4.01": "Auditor changed", "4.02": "Past financials no longer reliable (restatement)", "5.01": "Change in control",
    "5.02": "Director or officer change", "5.03": "Charter or bylaw amendment", "5.04": "Pension blackout", "5.05": "Code of ethics change",
    "5.07": "Shareholder vote results", "5.08": "Director nominations", "6.01": "ABS information", "7.01": "Regulation FD disclosure",
    "8.01": "Other events", "9.01": "Financial statements and exhibits",
}
RED_ITEMS = {"1.03", "1.05", "2.04", "2.06", "3.01", "4.01", "4.02", "2.05"}
AMBER_ITEMS = {"1.02", "2.03", "3.02", "5.01", "5.02", "3.03"}
FORM_LABEL = {"10-K": "Annual report", "10-Q": "Quarterly report", "8-K": "Current report", "6-K": "Foreign issuer report",
              "20-F": "Foreign annual report", "40-F": "Canadian annual report", "DEF 14A": "Proxy statement", "S-1": "Registration (IPO)",
              "S-3": "Shelf registration", "S-4": "Merger registration", "424B5": "Prospectus supplement", "SC 13D": "Activist stake (>5%)",
              "SC 13G": "Passive stake (>5%)", "SC 13D/A": "Activist stake amended", "SC 13G/A": "Passive stake amended",
              "4": "Insider trade", "144": "Planned insider sale", "11-K": "Employee plan report", "SD": "Conflict minerals"}
MATERIAL = {"10-K", "10-Q", "8-K", "6-K", "20-F", "40-F", "DEF 14A", "S-1", "S-3", "S-4", "424B5", "SC 13D", "SC 13D/A", "10-K/A", "10-Q/A", "8-K/A"}


def _daily_closes(symbols: List[str], start: str) -> pd.DataFrame:
    from api.marketdata.core import yahoo_download
    df = yahoo_download(symbols, start=start, auto_adjust=True, group_by="ticker", threads=True)
    out = {}
    for s in symbols:
        try:
            c = (df[s] if isinstance(df.columns, pd.MultiIndex) else df)["Close"].dropna()
            if len(c):
                c.index = pd.to_datetime(c.index).tz_localize(None).normalize()
                out[s] = c
        except Exception:
            continue
    return pd.DataFrame(out)


def filings(symbol: str, limit: int = 120) -> Dict[str, Any]:
    from api.marketdata.extras import _company_only, _sec_get
    s = symbol.strip().upper()
    _company_only(s, "SEC filings")

    def fetch():
        from api.providers import sec_edgar
        res = sec_edgar.resolve(s)
        cik = res.get("cik") if isinstance(res, dict) else res
        if not cik:
            raise NotFound(f"{s} doesn't file with the SEC (mostly US-listed companies and ADRs do).")
        sub = _sec_get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json").json()
        r = sub["filings"]["recent"]
        n = len(r["form"])
        rows = []
        for i in range(n):
            form = r["form"][i]
            if form in ("4", "4/A", "3", "5", "144") and len(rows) > limit // 2:
                continue
            acc = r["accessionNumber"][i]
            doc = r["primaryDocument"][i]
            items = [x.strip() for x in (r.get("items", [""] * n)[i] or "").split(",") if x.strip()]
            acc_t = r.get("acceptanceDateTime", [""] * n)[i] or ""
            et = None
            try:      # acceptance is stamped in UTC; the market reacts on New York time
                et = datetime.fromisoformat(acc_t.replace("Z", "+00:00")).astimezone(NY)
            except Exception:
                pass
            rows.append({"form": form, "label": FORM_LABEL.get(form.replace("/A", ""), r.get("primaryDocDescription", [""] * n)[i] or form),
                         "filed": r["filingDate"][i], "accepted": et.strftime("%Y-%m-%d %H:%M ET") if et else None,
                         "accepted_date": et.strftime("%Y-%m-%d") if et else r["filingDate"][i], "after_close": bool(et and et.hour >= 16),
                         "period": r.get("reportDate", [""] * n)[i] or None, "items": [{"code": x, "label": ITEMS_8K.get(x, x),
                         "severity": "red" if x in RED_ITEMS else "amber" if x in AMBER_ITEMS else None} for x in items],
                         "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{doc}",
                         "index": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/", "acc": acc,
                         "size": r.get("size", [None] * n)[i], "material": form in MATERIAL})
            if len(rows) >= limit:
                break
        # The feed's acceptanceDateTime is not reliable (Apple's runs 8–10 hours ahead while Microsoft's is
        # true UTC), so material filings take the acceptance time printed on EDGAR's own index page (ET).
        def accepted_et(x):
            try:
                html = _sec_get(f"{x['index']}{x['acc']}-index.htm", timeout=20).text
                m = re.search(r"Accepted</div>\s*<div class=\"info\">([^<]+)", html)
                return x, datetime.strptime(m.group(1).strip(), "%Y-%m-%d %H:%M:%S") if m else None
            except Exception:
                return x, None
        with cf.ThreadPoolExecutor(3) as ex:
            for x, et in ex.map(accepted_et, [x for x in rows if x["material"]][:80]):
                if et:
                    x["accepted"], x["accepted_date"], x["after_close"] = et.strftime("%Y-%m-%d %H:%M ET"), et.strftime("%Y-%m-%d"), et.hour >= 16
        # price reaction on each material filing (vs the market)
        try:
            first = min(x["accepted_date"] for x in rows)
            px = _daily_closes([s, "^GSPC"], (date.fromisoformat(first) - timedelta(days=10)).isoformat())
        except Exception:
            px = pd.DataFrame()
        if s in px and "^GSPC" in px:
            idx = px.index
            for x in rows:
                if not x["material"]:
                    continue
                d = pd.Timestamp(x["accepted_date"])
                k = idx.searchsorted(d)                       # first trading day on/after the filing date
                if k < len(idx) and idx[k] == d and x["after_close"]:
                    k += 1
                if k < 1 or k >= len(idx):
                    continue
                p0, p1 = px[s].iloc[k - 1], px[s].iloc[k]
                m0, m1 = px["^GSPC"].iloc[k - 1], px["^GSPC"].iloc[k]
                x["reaction_day"] = idx[k].strftime("%Y-%m-%d")
                x["reaction"] = float(p1 / p0 - 1)
                x["abnormal"] = float(p1 / p0 - m1 / m0)
                k5 = min(len(idx) - 1, k + 4)
                x["reaction_5d"] = float(px[s].iloc[k5] / p0 - 1) if k5 > k else None
        earn = [abs(x["abnormal"]) for x in rows if x.get("abnormal") is not None and any(it["code"] == "2.02" for it in x["items"])]
        flags = [x for x in rows if any(it["severity"] == "red" for it in x["items"])]
        return {"symbol": s, "cik": int(cik), "name": sub.get("name"), "sic": sub.get("sicDescription"), "fiscal_year_end": sub.get("fiscalYearEnd"),
                "filings": rows, "typical_earnings_move": float(np.median(earn)) if earn else None, "earnings_events": len(earn),
                "red_flags": len(flags), "source": "SEC EDGAR submissions feed; reactions from Yahoo closes (abnormal = minus the S&P 500)."}
    return _cached(f"cf3:{s}", 3600, fetch)


def filing_text(url: str) -> Dict[str, Any]:
    """A filing as readable text. For an 8-K the press release (exhibit 99) is attached when there is one."""
    from api.marketdata.extras import _sec_get
    if not re.match(r"^https://www\.sec\.gov/Archives/edgar/data/\d+/\d+/[\w.\-]+$", url):
        raise NotFound("Only SEC EDGAR archive documents can be opened here.")

    def fetch():
        import warnings
        from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

        def text_of(u: str) -> str:
            r = _sec_get(u, timeout=40)
            raw = r.content[:6_000_000]
            soup = BeautifulSoup(raw, "lxml")
            for t in soup(["script", "style", "ix:header"]):
                t.decompose()
            txt = soup.get_text("\n")
            txt = re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t\xa0]+", " ", txt))
            return txt.strip()
        main = text_of(url)
        exhibits = []
        base = url.rsplit("/", 1)[0] + "/"
        try:
            idx = _sec_get(base + "index.json", timeout=20).json()
            for it in idx.get("directory", {}).get("item", []):
                nm = it.get("name", "")
                if re.search(r"ex-?99|ex99|exhibit99|press", nm, re.I) and nm.lower().endswith((".htm", ".html", ".txt")):
                    exhibits.append({"name": nm, "text": text_of(base + nm)[:120_000]})
                    if len(exhibits) >= 2:
                        break
        except Exception:
            pass
        return {"url": url, "text": main[:200_000], "truncated": len(main) > 200_000, "exhibits": exhibits}
    return _cached(f"cftext:{url}", 86400, fetch)


# ── CRED: credit spreads ─────────────────────────────────────────────────────
CREDIT_SERIES = [
    ("BAMLC0A0CM", "US investment grade", "IG"), ("BAMLC0A4CBBB", "US BBB", "IG"), ("BAMLH0A0HYM2", "US high yield", "HY"),
    ("BAMLH0A1HYBB", "US BB", "HY"), ("BAMLH0A2HYB", "US single-B", "HY"), ("BAMLH0A3HYC", "US CCC & lower", "HY"),
    ("BAMLHE00EHYIOAS", "Euro high yield", "Regions"), ("BAMLEMCBPIOAS", "EM corporates", "Regions"),
    ("BAMLEMHBHYCRPIOAS", "EM high yield corporates", "Regions"), ("BAMLH0A0HYM2EY", "US high yield — effective yield", "Yield"),
]


def credit() -> Dict[str, Any]:
    from api.marketdata.insights import _fred

    def fetch():
        def one(row):
            sid = row[0]
            try:
                return sid, _fred(sid, years=4)
            except Exception as e:
                logger.info("[cred] %s: %s", sid, e)
                return sid, {}
        with cf.ThreadPoolExecutor(4) as ex:
            data = dict(ex.map(one, CREDIT_SERIES))
        if not any(data.values()):
            raise Upstream("FRED didn't return the ICE BofA spread series — try again shortly.")
        out, frames = [], {}
        for sid, name, group in CREDIT_SERIES:
            d = data.get(sid) or {}
            if not d:
                continue
            s = pd.Series(d, dtype=float)
            s.index = pd.to_datetime(s.index)
            s = s.sort_index().dropna()
            frames[sid] = s
            last = float(s.iloc[-1])

            def chg(days):
                past = s[s.index <= s.index[-1] - pd.Timedelta(days=days)]
                return (last - float(past.iloc[-1])) * 100 if len(past) else None
            pct = float((s < last).mean())
            z = float((last - s.mean()) / s.std()) if s.std() > 0 else None
            out.append({"id": sid, "name": name, "group": group, "last": last, "date": s.index[-1].strftime("%Y-%m-%d"),
                        "chg_1w_bp": chg(7), "chg_1m_bp": chg(30), "chg_3m_bp": chg(91), "chg_1y_bp": chg(365),
                        "percentile": pct, "z": z, "min": float(s.min()), "max": float(s.max()), "start": s.index[0].strftime("%Y-%m-%d"),
                        "unit": "%" if sid.endswith("EY") else "% (spread)"})
        df = pd.DataFrame(frames).ffill()
        wk = df.resample("W-FRI").last().dropna(how="all")
        hist = [{"date": d.strftime("%Y-%m-%d"), **{k: (round(float(v), 3) if v == v else None) for k, v in r.items()}} for d, r in wk.iterrows()]
        derived = {}
        if {"BAMLH0A0HYM2", "BAMLC0A0CM"} <= set(df):
            r = (df["BAMLH0A0HYM2"] / df["BAMLC0A0CM"]).dropna()
            derived["hy_ig_ratio"] = {"last": float(r.iloc[-1]), "percentile": float((r < r.iloc[-1]).mean()), "label": "HY ÷ IG spread"}
        if {"BAMLH0A3HYC", "BAMLH0A1HYBB"} <= set(df):
            r = (df["BAMLH0A3HYC"] - df["BAMLH0A1HYBB"]).dropna()
            derived["ccc_bb"] = {"last": float(r.iloc[-1]), "percentile": float((r < r.iloc[-1]).mean()),
                                 "label": "CCC − BB (distress premium)"}
        signals = []
        hy = next((x for x in out if x["id"] == "BAMLH0A0HYM2"), None)
        if hy:
            if hy["percentile"] <= 0.15:
                signals.append(f"US high-yield spreads are tight — {hy['last']:.2f}%, lower than {1 - hy['percentile']:.0%} of the last {hy['start'][:4]}–today range: little cushion for bad news.")
            elif hy["percentile"] >= 0.85:
                signals.append(f"US high-yield spreads are wide — {hy['last']:.2f}%, in the top {1 - hy['percentile']:.0%} of the range: credit is pricing stress.")
            if (hy.get("chg_1m_bp") or 0) >= 50:
                signals.append(f"High-yield spreads widened {hy['chg_1m_bp']:.0f}bp in a month — a risk-off move worth watching against equities.")
            if (hy.get("chg_1m_bp") or 0) <= -40:
                signals.append(f"High-yield spreads tightened {-hy['chg_1m_bp']:.0f}bp in a month — risk appetite is improving.")
        cb = derived.get("ccc_bb")
        if cb and cb["percentile"] >= 0.8:
            signals.append("CCC bonds trade far wider than BB — the weakest borrowers are being shut out (an early default warning).")
        return {"series": out, "history": hist, "derived": derived, "signals": signals,
                "note": "Option-adjusted spreads over Treasuries (ICE BofA indices via FRED). FRED serves about three years of these "
                        "series, so percentiles are three-year percentiles.", "source": "ICE BofA via FRED (St. Louis Fed)"}
    return _cached("cred", 3 * 3600, fetch)


# ── FAC: factor exposures of one stock ───────────────────────────────────────
def factor_exposure(symbol: str, years: int = 5) -> Dict[str, Any]:
    s = symbol.strip().upper()

    def fetch():
        from api.providers import factor_library as fl
        px = _daily_closes([s], (date.today() - timedelta(days=int(365.25 * years) + 10)).isoformat())
        if s not in px or len(px[s]) < 300:
            raise NotFound(f"Not enough price history for {s}.")
        r = px[s].pct_change().dropna()
        full = fl.attribution(r.values, [d.strftime("%Y-%m-%d") for d in r.index])
        if not full.get("available"):
            raise NotFound(full.get("reason") or "Factor data unavailable.")
        f = fl.factors()
        cols = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]
        df = f[cols + ["RF"]].join(r.rename("r"), how="inner").dropna()
        y = (df["r"] - df["RF"]).to_numpy()
        X = np.column_stack([np.ones(len(df)), df[cols].to_numpy()])
        roll = []
        for end in range(252, len(df) + 1, 21):                 # one-year windows, stepped monthly
            b, *_ = np.linalg.lstsq(X[end - 252:end], y[end - 252:end], rcond=None)
            roll.append({"date": df.index[end - 1].strftime("%Y-%m-%d"), **{c: round(float(b[i + 1]), 3) for i, c in enumerate(cols)},
                         "alpha": round(float(b[0] * 252), 4)})
        # variance decomposition: share of the stock's variance explained by each factor (full period)
        bvec = np.array([l["beta"] for l in full["loadings"]])
        F = df[cols].to_numpy()
        cov = np.cov(F.T)
        sys_var = float(bvec @ cov @ bvec)
        tot = float(np.var(y))
        contrib = {c: float(bvec[i] * (cov[i] @ bvec)) / tot for i, c in enumerate(cols)} if tot > 0 else {}
        us = not ("." in s and not s.endswith((".US",)))
        return {"symbol": s, **full, "rolling": roll, "variance_share": contrib, "idiosyncratic_share": max(0.0, 1 - sys_var / tot) if tot else None,
                "factor_names": fl.NAMES, "us_factors_note": None if us else
                "These are US factors; for a non-US stock the loadings describe how it co-moves with US styles (local-currency returns).",
                "source": "Kenneth French Data Library (daily US factors, ~1 month lag); prices Yahoo Finance"}
    return _cached(f"fac:{s}:{years}", 6 * 3600, fetch)


# ── PORT: portfolio risk ─────────────────────────────────────────────────────
SHOCK_PROXIES = {"^GSPC": "S&P 500", "^TNX": "US 10-year yield", "CL=F": "WTI crude", "DX-Y.NYB": "US dollar index"}
SCENARIOS = [("Equities −10%", "^GSPC", -0.10), ("Equities −20%", "^GSPC", -0.20), ("Rates +100bp", "^TNX", 1.0), ("Rates −100bp", "^TNX", -1.0),
             ("Oil +30%", "CL=F", 0.30), ("Oil −30%", "CL=F", -0.30), ("Dollar +5%", "DX-Y.NYB", 0.05), ("Dollar −5%", "DX-Y.NYB", -0.05)]
REPLAYS = [("Global financial crisis", "2008-09-12", "2009-03-09"), ("Euro debt crisis", "2011-07-22", "2011-10-03"),
           ("Taper tantrum", "2013-05-21", "2013-06-24"), ("China deval / oil crash", "2015-08-10", "2016-02-11"),
           ("Volmageddon", "2018-01-26", "2018-02-08"), ("Q4 2018 sell-off", "2018-09-20", "2018-12-24"),
           ("Covid crash", "2020-02-19", "2020-03-23"), ("2022 rate shock", "2022-01-03", "2022-10-12"),
           ("Yen carry unwind", "2024-07-16", "2024-08-05")]


def _usd_returns(closes: pd.DataFrame, ccy: Dict[str, str]) -> pd.DataFrame:
    """Daily returns in USD. Yahoo labels a daily FX bar one day after the New York session it belongs
    to, so FX is shifted back a day before it is combined with the asset's own return."""
    import yfinance as yf
    rets = closes.ffill(limit=3).pct_change(fill_method=None)
    pairs = {c for c in ccy.values() if c and c != "USD"}
    if not pairs:
        return rets
    fx = yf.download([f"{c}USD=X" for c in pairs], start=closes.index[0].strftime("%Y-%m-%d"), auto_adjust=True, progress=False,
                     group_by="ticker", threads=True)
    for sym, c in ccy.items():
        if c == "USD" or sym not in rets:
            continue
        try:
            f = (fx[f"{c}USD=X"] if isinstance(fx.columns, pd.MultiIndex) else fx)["Close"].dropna()
            f.index = pd.to_datetime(f.index).tz_localize(None).normalize()
            f = f.shift(-1).reindex(rets.index).ffill(limit=3)
            rets[sym] = (1 + rets[sym]) * (1 + f.pct_change(fill_method=None)) - 1
        except Exception:
            continue
    return rets


def portfolio_risk(holdings: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = []
    agg: Dict[str, float] = {}
    for h in holdings:
        sym = str(h.get("symbol") or "").strip().upper()
        q = _f(h.get("quantity"))
        if sym and q:
            agg[sym] = agg.get(sym, 0.0) + q
    if not agg:
        raise NotFound("Add some holdings (symbol and quantity).")
    if len(agg) > 60:
        raise NotFound("Up to 60 holdings.")

    def info(sym):
        try:
            return sym, _info(sym)
        except Exception:
            return sym, {}
    with cf.ThreadPoolExecutor(8) as ex:
        infos = dict(ex.map(info, list(agg)))
    ccy_of: Dict[str, str] = {}
    for sym, qty in agg.items():
        i = infos.get(sym) or {}
        px = _f(i.get("regularMarketPrice")) or _f(i.get("currentPrice")) or _f(i.get("previousClose"))
        c = i.get("currency") or "USD"
        major = MINOR_UNITS.get(c, c.upper())
        local = px * qty if px else None
        if local is not None and c in MINOR_UNITS:
            local /= 100                                   # pence → pounds
        usd = to_usd(local, major) if local is not None else None
        ccy_of[sym] = major
        prev = _f(i.get("regularMarketPreviousClose")) or _f(i.get("previousClose"))
        rows.append({"symbol": sym, "name": i.get("longName") or i.get("shortName") or sym, "quantity": qty, "price": px, "currency": c, "ccy": major,
                     "value_usd": usd, "day_change": (px / prev - 1) if px and prev else None,
                     "type": {"EQUITY": "Stock", "ETF": "ETF", "MUTUALFUND": "Fund", "CRYPTOCURRENCY": "Crypto", "FUTURE": "Future",
                              "INDEX": "Index", "CURRENCY": "FX"}.get((i.get("quoteType") or "").upper(), i.get("quoteType") or "—"),
                     "sector": i.get("sector") or ({"ETF": "Funds", "CRYPTOCURRENCY": "Crypto"}.get((i.get("quoteType") or "").upper(), "Other")),
                     "country": i.get("country") or ("—" if (i.get("quoteType") or "").upper() != "EQUITY" else "Unknown")})
    priced = [r for r in rows if r["value_usd"] is not None]
    if not priced:
        raise NotFound("None of the holdings could be priced.")
    gross = sum(abs(r["value_usd"]) for r in priced)
    net = sum(r["value_usd"] for r in priced)
    for r in priced:
        r["weight"] = r["value_usd"] / gross
    syms = [r["symbol"] for r in priced]
    w = np.array([r["weight"] for r in priced])

    def build():
        start = (date.today() - timedelta(days=3 * 365 + 10)).isoformat()
        closes = _daily_closes(syms + list(SHOCK_PROXIES), start)
        rets = _usd_returns(closes[[s for s in syms if s in closes]], {s: ccy_of[s] for s in syms}) if any(s in closes for s in syms) else pd.DataFrame()
        prox = closes[[p for p in SHOCK_PROXIES if p in closes]].ffill(limit=3)
        return closes, rets, prox
    closes, rets, prox = _cached(f"port:{','.join(sorted(syms))}", 1800, build)
    have = [s for s in syms if s in rets and rets[s].notna().sum() > 60]
    missing = [s for s in syms if s not in have]
    R = rets.reindex(columns=syms).fillna(0.0)
    R = R[(rets[have].notna().any(axis=1))] if have else R
    port = R.to_numpy() @ w                       # daily return per $1 gross, rebalanced to today's weights
    port_s = pd.Series(port, index=R.index).iloc[1:]
    if len(port_s) < 60:
        raise NotFound("Not enough price history for these holdings.")
    vol = float(port_s.std() * math.sqrt(252))
    lev = net / gross if gross else 1.0
    q95, q99 = np.quantile(port_s, 0.05), np.quantile(port_s, 0.01)
    es95 = float(port_s[port_s <= q95].mean())
    eq = (1 + port_s).cumprod()
    dd = float((eq / eq.cummax() - 1).min())
    yrs = len(port_s) / 252
    cagr = float(eq.iloc[-1] ** (1 / yrs) - 1) if yrs > 0 and eq.iloc[-1] > 0 else None
    # weekly returns for beta / correlation / risk contribution (robust to markets closing at different hours)
    Rw = (1 + R).resample("W-FRI").prod() - 1
    Rw = Rw.iloc[1:]
    pw = Rw.to_numpy() @ w
    cov = np.cov(Rw.to_numpy().T) * 52 if len(syms) > 1 else np.array([[float(np.var(Rw.iloc[:, 0])) * 52]])
    cov = np.atleast_2d(cov)
    pvar = float(w @ cov @ w)
    contrib = (w * (cov @ w)) / pvar if pvar > 0 else np.zeros_like(w)
    spx_w = None
    if "^GSPC" in prox:
        spx_w = prox["^GSPC"].resample("W-FRI").last().pct_change().reindex(Rw.index)
    beta = None
    if spx_w is not None:
        ok = spx_w.notna()
        if ok.sum() > 20:
            beta = float(np.cov(pw[ok.values], spx_w[ok].values)[0, 1] / np.var(spx_w[ok].values))
    for k, r in enumerate(priced):
        col = Rw[r["symbol"]]
        r["vol"] = float(R[r["symbol"]].std() * math.sqrt(252)) if r["symbol"] in have else None
        r["risk_share"] = float(contrib[k])
        if spx_w is not None and r["symbol"] in have:
            ok = spx_w.notna() & col.notna()
            r["beta"] = float(np.cov(col[ok], spx_w[ok])[0, 1] / np.var(spx_w[ok])) if ok.sum() > 20 else None
        r["return_1y"] = float((1 + R[r["symbol"]].iloc[-252:]).prod() - 1) if r["symbol"] in have else None
    # correlations (largest 20 holdings)
    top = sorted(priced, key=lambda r: -abs(r["weight"]))[:20]
    cm = Rw[[r["symbol"] for r in top]].corr().round(2)
    corr = {"symbols": list(cm.columns), "matrix": cm.fillna(0).values.tolist()}

    def group(key):
        g: Dict[str, float] = {}
        for r in priced:
            g[r[key]] = g.get(r[key], 0.0) + r["weight"]
        return sorted(({"name": k, "weight": v} for k, v in g.items()), key=lambda x: -abs(x["weight"]))
    # factor shocks: univariate weekly betas of each holding to each proxy (captures what usually moves with it)
    pxw = prox.resample("W-FRI").last()
    shocks = []
    betas: Dict[str, Dict[str, float]] = {}
    for p in SHOCK_PROXIES:
        if p not in pxw:
            continue
        f = (pxw[p].diff() if p == "^TNX" else pxw[p].pct_change()).reindex(Rw.index)
        for s in syms:
            ok = f.notna() & Rw[s].notna()
            if s in have and ok.sum() > 30 and np.var(f[ok]) > 0:
                betas.setdefault(s, {})[p] = float(np.cov(Rw[s][ok], f[ok])[0, 1] / np.var(f[ok]))
    for name, p, shock in SCENARIOS:
        per = []
        for r in priced:
            b = betas.get(r["symbol"], {}).get(p)
            if b is None:
                continue
            imp = max(-1.0, b * shock)
            per.append({"symbol": r["symbol"], "impact": imp, "pnl": imp * r["value_usd"]})
        if per:
            tot = sum(x["pnl"] for x in per)
            shocks.append({"scenario": name, "driver": SHOCK_PROXIES[p], "pnl": tot, "return": tot / gross,
                           "worst": sorted(per, key=lambda x: x["pnl"])[:3], "best": sorted(per, key=lambda x: -x["pnl"])[:2]})
    replays = _replays(priced, betas)
    # factor attribution (US factors, daily USD returns)
    factors = None
    try:
        from api.providers import factor_library as fl
        factors = fl.attribution(port_s.values, [d.strftime("%Y-%m-%d") for d in port_s.index])
    except Exception as e:
        logger.info("[port] factors: %s", e)
    curve_step = max(1, len(eq) // 400)
    curve = [{"date": d.strftime("%Y-%m-%d"), "value": round(float(v) * 100, 2)} for k, (d, v) in enumerate(eq.items()) if k % curve_step == 0 or k == len(eq) - 1]
    worst_days = [{"date": d.strftime("%Y-%m-%d"), "return": float(v), "pnl": float(v) * gross} for d, v in port_s.nsmallest(5).items()]
    eff_n = 1 / float(np.sum(w ** 2)) if len(w) else None
    return {"positions": sorted(rows, key=lambda r: -abs(r.get("value_usd") or 0)), "missing_history": missing,
            "summary": {"gross_usd": gross, "net_usd": net, "net_exposure": lev, "positions": len(priced),
                        "day_pnl": sum((r["value_usd"] or 0) * (r["day_change"] or 0) / (1 + (r["day_change"] or 0)) for r in priced),
                        "vol": vol, "beta": beta, "var95_1d": float(-q95 * gross), "var99_1d": float(-q99 * gross), "es95_1d": float(-es95 * gross),
                        "var95_pct": float(-q95), "max_drawdown": dd, "cagr": cagr, "sharpe_like": (cagr / vol) if cagr is not None and vol else None,
                        "effective_n": eff_n, "top5_weight": float(sum(sorted(np.abs(w), reverse=True)[:5])),
                        "history_from": port_s.index[0].strftime("%Y-%m-%d")},
            "exposure": {"sector": group("sector"), "country": group("country"), "currency": group("ccy"), "type": group("type")},
            "correlation": corr, "scenarios": shocks, "replays": replays, "factors": factors, "curve": curve, "worst_days": worst_days,
            "note": "Risk uses today's weights applied to three years of daily returns in USD (FX included). VaR/ES are historical, one day. "
                    "Betas, correlations and risk shares use weekly returns, so markets that close at different hours line up. "
                    "Shock scenarios scale each holding's weekly beta to the driver; replays apply each holding's actual return in the episode "
                    "(or its S&P 500 beta when it didn't trade yet).",
            "source": "Yahoo Finance prices and FX; Kenneth French factors"}


def _replays(priced: List[Dict[str, Any]], betas: Dict[str, Dict[str, float]]) -> List[Dict[str, Any]]:
    syms = [r["symbol"] for r in priced]

    def fetch():
        return _daily_closes(syms + ["^GSPC"], "2008-08-01")
    try:
        long = _cached(f"portlong:{','.join(sorted(syms))}", 6 * 3600, fetch)
    except Exception as e:
        logger.info("[port] replays: %s", e)
        return []
    gross = sum(abs(r["value_usd"]) for r in priced)
    out = []
    for name, a, b in REPLAYS:
        A, B = pd.Timestamp(a), pd.Timestamp(b)
        if "^GSPC" not in long:
            break
        spx = long["^GSPC"].dropna()
        try:
            m = float(spx[spx.index <= B].iloc[-1] / spx[spx.index <= A].iloc[-1] - 1)
        except IndexError:
            continue
        pnl, proxied, per = 0.0, [], []
        for r in priced:
            s = r["symbol"]
            c = long[s].dropna() if s in long else pd.Series(dtype=float)
            if len(c) and c.index[0] <= A:
                ret = float(c[c.index <= B].iloc[-1] / c[c.index <= A].iloc[-1] - 1)
            else:
                ret = max(-1.0, (betas.get(s, {}).get("^GSPC") or 1.0) * m)
                proxied.append(s)
            pnl += ret * r["value_usd"]
            per.append({"symbol": s, "return": ret, "pnl": ret * r["value_usd"]})
        out.append({"episode": name, "start": a, "end": b, "spx": m, "return": pnl / gross if gross else None, "pnl": pnl,
                    "proxied": proxied, "worst": sorted(per, key=lambda x: x["pnl"])[:3]})
    return out
