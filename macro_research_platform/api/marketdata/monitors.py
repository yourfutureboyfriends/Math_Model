"""
Global monitors for the Markets mode (Bloomberg mnemonics in brackets):

  earnings_calendar(...)  [EVTS]   company earnings dates with EPS estimate / actual / surprise
  fx_matrix()             [WCRS]   cross rates between major currencies + 1-day change
  money_markets()         [BTMM]   policy, bill, coupon, curve-spread, credit and mortgage rates (FRED)
  heatmap(country)        [IMAP]   a country's largest stocks by sector, sized by cap, coloured by move
  crypto()                [CRYPTO] top coins by market cap (CoinGecko, free; Yahoo fallback)
  futures_curve(root)     [CMDTY]  a commodity's futures term structure (contango/backwardation)
  news_hub(q)             [N/TOP]  markets headlines from major outlets with sentiment and search
"""
from __future__ import annotations

import logging
import math
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from api.marketdata.core import NotFound, Upstream, _cached, _f

logger = logging.getLogger(__name__)


# ── EVTS ─────────────────────────────────────────────────────────────────────
def earnings_calendar(start: Optional[str] = None, days: int = 7, min_cap_bn: float = 0.0, offset: int = 0,
                      limit: int = 100) -> Dict[str, Any]:
    s = date.fromisoformat(start) if start else date.today()
    e = s + timedelta(days=max(1, min(days, 31)))

    def fetch():
        import yfinance as yf
        try:
            df = yf.Calendars().get_earnings_calendar(market_cap=(min_cap_bn * 1e9) if min_cap_bn else None, filter_most_active=False,
                                                      start=s.isoformat(), end=e.isoformat(), limit=min(limit, 250), offset=offset)
        except Exception as ex:
            raise Upstream(f"Earnings calendar unavailable: {ex}")
        rows = []
        if df is not None and not df.empty:
            for sym, r in df.iterrows():
                t = r.get("Event Start Date")
                rows.append({"symbol": sym, "company": r.get("Company"), "market_cap": _f(r.get("Marketcap")),
                             "event": r.get("Event Name"), "datetime": t.isoformat() if hasattr(t, "isoformat") else str(t),
                             "timing": {"BMO": "Before open", "AMC": "After close", "TAS": "During session", "TNS": "Time not set"}.get(str(r.get("Timing")), r.get("Timing")),
                             "eps_estimate": _f(r.get("EPS Estimate")), "eps_reported": _f(r.get("Reported EPS")),
                             "surprise_pct": _f(r.get("Surprise(%)"))})
        rows.sort(key=lambda x: (x["datetime"] or "", -(x["market_cap"] or 0)))
        return {"start": s.isoformat(), "end": e.isoformat(), "rows": rows, "offset": offset,
                "source": "Yahoo Finance earnings calendar"}
    return _cached(f"evts:{s}:{e}:{min_cap_bn}:{offset}:{limit}", 1800, fetch)


# ── WCRS ─────────────────────────────────────────────────────────────────────
CCYS = ["USD", "EUR", "JPY", "GBP", "CHF", "CAD", "AUD", "NZD", "CNY", "HKD", "SGD", "INR", "KRW", "MXN", "BRL", "ZAR", "SEK", "NOK"]


def fx_matrix(ccys: Optional[List[str]] = None) -> Dict[str, Any]:
    cs = [c for c in (ccys or CCYS) if c in CCYS] or CCYS

    def fetch():
        import yfinance as yf
        pairs = {c: f"{c}USD=X" for c in cs if c != "USD"}           # USD per 1 unit of c
        try:
            df = yf.download(list(pairs.values()), period="10d", interval="1d", auto_adjust=False, group_by="ticker", progress=False, threads=True)
        except Exception as ex:
            raise Upstream(f"FX rates unavailable: {ex}")
        last, prev, asof = {"USD": 1.0}, {"USD": 1.0}, None
        for c, p in pairs.items():
            try:
                cl = df[p]["Close"].dropna()
                cl = cl[cl.index.dayofweek < 5]          # weekend prints are stale/junk: compare trading days
                last[c], prev[c] = float(cl.iloc[-1]), float(cl.iloc[-2])
                asof = max(asof or cl.index[-1], cl.index[-1])
            except Exception:
                continue
        have = [c for c in cs if c in last]
        # matrix[base][quote] = units of `quote` per 1 `base`
        mat = {b: {q: last[b] / last[q] for q in have} for b in have}
        chg = {b: {q: (last[b] / last[q]) / (prev[b] / prev[q]) - 1 for q in have} for b in have}
        vs_usd = sorted([{"ccy": c, "usd_change_1d": last[c] / prev[c] - 1} for c in have if c != "USD"], key=lambda x: -x["usd_change_1d"])
        return {"currencies": have, "matrix": mat, "change_1d": chg, "strength_vs_usd": vs_usd,
                "as_of": asof.strftime("%Y-%m-%d") if asof is not None else None,
                "note": "Row currency → column currency: units of the column currency per 1 unit of the row currency.",
                "source": "Yahoo Finance FX (daily)"}
    return _cached(f"wcrs:{','.join(cs)}", 300, fetch)


# ── BTMM ─────────────────────────────────────────────────────────────────────
BTMM_SERIES = [
    ("Policy & funding", [("DFF", "Fed funds effective"), ("SOFR", "SOFR"), ("IORB", "Interest on reserve balances")]),
    ("Treasury bills", [("DTB4WK", "4-week bill"), ("DTB3", "3-month bill"), ("DTB6", "6-month bill"), ("DTB1YR", "1-year bill")]),
    ("Treasury coupons", [("DGS2", "2-year"), ("DGS5", "5-year"), ("DGS10", "10-year"), ("DGS30", "30-year"),
                          ("DFII10", "10-year TIPS (real)"), ("T10YIE", "10-year breakeven inflation")]),
    ("Curve", [("T10Y2Y", "10y − 2y"), ("T10Y3M", "10y − 3m")]),
    ("Credit & mortgages", [("BAMLC0A0CM", "IG corporate OAS"), ("BAMLH0A0HYM2", "High-yield OAS"), ("MORTGAGE30US", "30-year mortgage")]),
]


def money_markets() -> Dict[str, Any]:
    def fetch():
        from api.providers.fred_provider import FREDProvider
        try:
            from api import fred_guard
            if fred_guard.is_open():
                raise Upstream("FRED is rate-limiting requests right now — try again shortly.")
        except ImportError:
            pass
        fp = FREDProvider()
        start = (date.today() - timedelta(days=400)).isoformat()
        groups = []
        import concurrent.futures as cf

        def one(sid):
            try:
                res = fp.fetch_series(sid, start_date=start)
                obs = [(o.date, o.value) for o in (res.data or []) if o.value is not None and math.isfinite(o.value)]
                return sid, obs
            except Exception:
                return sid, []
        ids = [sid for _, items in BTMM_SERIES for sid, _ in items]
        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            data = dict(ex.map(one, ids))
        for g, items in BTMM_SERIES:
            rows = []
            for sid, label in items:
                obs = data.get(sid) or []
                if not obs:
                    rows.append({"series": sid, "name": label, "value": None})
                    continue
                d, v = obs[-1]

                def back(days):
                    cutoff = (date.fromisoformat(d) - timedelta(days=days)).isoformat()
                    prior = [x for x in obs if x[0] <= cutoff]
                    return (v - prior[-1][1]) * 100 if prior else None
                rows.append({"series": sid, "name": label, "value": v, "date": d, "change_1w_bp": back(7), "change_1m_bp": back(30),
                             "change_1y_bp": back(365), "spark": [round(x[1], 4) for x in obs[-90:]]})
            groups.append({"group": g, "rows": rows})
        return {"groups": groups, "units": "percent; changes in basis points", "source": "FRED (St. Louis Fed)"}
    return _cached("btmm", 3600, fetch)


# ── IMAP ─────────────────────────────────────────────────────────────────────
def heatmap(country: str = "US", max_names: int = 300) -> Dict[str, Any]:
    country = country.upper()

    def fetch():
        import yfinance as yf
        from api import global_universe as gu
        u = gu.load(rebuild_if_stale=False)
        items = u if isinstance(u, list) else (u.get("stocks") or [])
        names = sorted([x for x in items if str(x.get("country")) == country and x.get("listing_country", country) == country],
                       key=lambda x: -(x.get("mcap_usd") or 0))[:max_names]
        if not names:
            raise NotFound(f"No stock universe for country '{country}'.")
        syms = [x["symbol"] for x in names]
        try:
            df = yf.download(syms, period="5d", interval="1d", auto_adjust=False, group_by="ticker", progress=False, threads=True)
        except Exception as ex:
            raise Upstream(f"Prices unavailable: {ex}")
        rows = []
        for x in names:
            try:
                c = df[x["symbol"]]["Close"].dropna()
                chg = float(c.iloc[-1] / c.iloc[-2] - 1) if len(c) >= 2 else None
                wk = float(c.iloc[-1] / c.iloc[0] - 1) if len(c) >= 2 else None
                px = float(c.iloc[-1])
            except Exception:
                chg = wk = px = None
            rows.append({"symbol": x["symbol"], "name": x.get("name"), "sector": x.get("sector") or "Other",
                         "market_cap_usd": x.get("mcap_usd"), "price": px, "change_1d": chg, "change_5d": wk})
        sectors: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            s = sectors.setdefault(r["sector"], {"sector": r["sector"], "cap": 0.0, "wsum": 0.0, "w": 0.0, "n": 0})
            s["cap"] += r["market_cap_usd"] or 0
            s["n"] += 1
            if r["change_1d"] is not None and r["market_cap_usd"]:
                s["wsum"] += r["change_1d"] * r["market_cap_usd"]
                s["w"] += r["market_cap_usd"]
        sec = [{"sector": v["sector"], "market_cap_usd": v["cap"], "count": v["n"],
                "change_1d": v["wsum"] / v["w"] if v["w"] else None} for v in sectors.values()]
        sec.sort(key=lambda x: -x["market_cap_usd"])
        return {"country": country, "rows": rows, "sectors": sec,
                "countries": sorted({str(x.get("country")) for x in items if x.get("country")}),
                "note": "Largest companies by market cap; sector moves are cap-weighted.", "source": "Yahoo Finance"}
    return _cached(f"imap:{country}:{max_names}", 300, fetch)


# ── CRYPTO ───────────────────────────────────────────────────────────────────
def crypto(limit: int = 100) -> Dict[str, Any]:
    def fetch():
        import requests
        try:
            r = requests.get("https://api.coingecko.com/api/v3/coins/markets",
                             params={"vs_currency": "usd", "order": "market_cap_desc", "per_page": min(limit, 250), "page": 1,
                                     "price_change_percentage": "1h,24h,7d,30d", "sparkline": "true"}, timeout=20)
            r.raise_for_status()
            coins = r.json()
        except Exception as ex:
            raise Upstream(f"CoinGecko unavailable: {ex}")
        rows = [{"symbol": f"{str(c.get('symbol', '')).upper()}-USD", "coin": str(c.get("symbol", "")).upper(), "name": c.get("name"),
                 "rank": c.get("market_cap_rank"), "price": _f(c.get("current_price")), "market_cap": _f(c.get("market_cap")),
                 "volume_24h": _f(c.get("total_volume")),
                 "change_1h": (_f(c.get("price_change_percentage_1h_in_currency")) or 0) / 100 if c.get("price_change_percentage_1h_in_currency") is not None else None,
                 "change_24h": (_f(c.get("price_change_percentage_24h_in_currency")) or 0) / 100 if c.get("price_change_percentage_24h_in_currency") is not None else None,
                 "change_7d": (_f(c.get("price_change_percentage_7d_in_currency")) or 0) / 100 if c.get("price_change_percentage_7d_in_currency") is not None else None,
                 "change_30d": (_f(c.get("price_change_percentage_30d_in_currency")) or 0) / 100 if c.get("price_change_percentage_30d_in_currency") is not None else None,
                 "ath_change": (_f(c.get("ath_change_percentage")) or 0) / 100 if c.get("ath_change_percentage") is not None else None,
                 "spark": [round(float(x), 8) for x in ((c.get("sparkline_in_7d") or {}).get("price") or [])[::6]]}
                for c in coins]
        total = sum(r["market_cap"] or 0 for r in rows)
        btc = next((r for r in rows if r["coin"] == "BTC"), None)
        return {"rows": rows, "total_market_cap": total, "btc_dominance": (btc["market_cap"] / total) if btc and total else None,
                "source": "CoinGecko (free API)"}
    return _cached(f"crypto:{limit}", 180, fetch)


# ── CMDTY futures curves ─────────────────────────────────────────────────────
MONTH_CODES = "FGHJKMNQUVXZ"
FUTURES = {
    "CL": ("WTI crude oil", "NYM", list(range(1, 13))), "BZ": ("Brent crude", "NYM", list(range(1, 13))),
    "NG": ("Natural gas", "NYM", list(range(1, 13))), "HO": ("Heating oil", "NYM", list(range(1, 13))),
    "RB": ("RBOB gasoline", "NYM", list(range(1, 13))), "GC": ("Gold", "CMX", [2, 4, 6, 8, 10, 12]),
    "SI": ("Silver", "CMX", [3, 5, 7, 9, 12]), "HG": ("Copper", "CMX", [3, 5, 7, 9, 12]),
    "ZC": ("Corn", "CBT", [3, 5, 7, 9, 12]), "ZW": ("Wheat", "CBT", [3, 5, 7, 9, 12]), "ZS": ("Soybeans", "CBT", [1, 3, 5, 7, 8, 9, 11]),
    "KC": ("Coffee", "NYB", [3, 5, 7, 9, 12]), "LE": ("Live cattle", "CME", [2, 4, 6, 8, 10, 12]),
    "PL": ("Platinum", "NYM", [1, 4, 7, 10]), "PA": ("Palladium", "NYM", [3, 6, 9, 12]),
    "HE": ("Lean hogs", "CME", [2, 4, 5, 6, 7, 8, 10, 12]), "CT": ("Cotton", "NYB", [3, 5, 7, 10, 12]),
    "SB": ("Sugar No. 11", "NYB", [3, 5, 7, 10]),
    # financial futures (quarterly)
    "ES": ("E-mini S&P 500", "CME", [3, 6, 9, 12]), "NQ": ("E-mini Nasdaq-100", "CME", [3, 6, 9, 12]),
    "YM": ("E-mini Dow", "CBT", [3, 6, 9, 12]), "RTY": ("E-mini Russell 2000", "CME", [3, 6, 9, 12]),
    "ZT": ("2-year T-note", "CBT", [3, 6, 9, 12]), "ZF": ("5-year T-note", "CBT", [3, 6, 9, 12]),
    "ZN": ("10-year T-note", "CBT", [3, 6, 9, 12]), "ZB": ("30-year T-bond", "CBT", [3, 6, 9, 12]),
    "6E": ("Euro FX", "CME", [3, 6, 9, 12]), "6J": ("Japanese yen", "CME", [3, 6, 9, 12]),
}


def futures_curve(root: str, n: int = 10) -> Dict[str, Any]:
    root = root.upper()
    if root not in FUTURES:
        raise NotFound(f"Unknown futures root '{root}'. Try one of: {', '.join(FUTURES)}")
    name, exch, months = FUTURES[root]

    def fetch():
        import yfinance as yf
        today = date.today()
        contracts = []
        y, m = today.year, today.month
        for k in range(36):
            mm = (m - 1 + k) % 12 + 1
            yy = y + (m - 1 + k) // 12
            if mm in months:
                contracts.append((f"{root}{MONTH_CODES[mm - 1]}{str(yy)[-2:]}.{exch}", f"{yy}-{mm:02d}"))
            if len(contracts) >= n + 2:
                break
        syms = [c for c, _ in contracts]
        try:
            df = yf.download(syms + [f"{root}=F"], period="5d", interval="1d", auto_adjust=False, group_by="ticker", progress=False, threads=True)
        except Exception as ex:
            raise Upstream(f"Futures prices unavailable: {ex}")
        pts = []
        for sym, month in contracts:
            try:
                c = df[sym]["Close"].dropna()
                if len(c):
                    pts.append({"contract": sym, "month": month, "price": float(c.iloc[-1]),
                                "change_1d": float(c.iloc[-1] / c.iloc[-2] - 1) if len(c) > 1 else None})
            except Exception:
                continue
        pts = pts[:n]
        if len(pts) < 2:
            raise NotFound(f"Not enough listed contracts priced for {name}.")
        slope = pts[-1]["price"] / pts[0]["price"] - 1
        span_m = max(1, (int(pts[-1]["month"][:4]) - int(pts[0]["month"][:4])) * 12 + int(pts[-1]["month"][5:]) - int(pts[0]["month"][5:]))
        return {"root": root, "name": name, "exchange": exch, "points": pts, "front": pts[0], "slope": slope,
                "annualised_roll_yield": -((1 + slope) ** (12 / span_m) - 1),
                "shape": "contango (later months dearer)" if slope > 0.005 else "backwardation (later months cheaper)" if slope < -0.005 else "flat",
                "note": "Positive roll yield (backwardation) pays a long futures holder as contracts converge to spot.",
                "source": "Yahoo Finance futures (delayed)"}
    return _cached(f"fut:{root}:{n}", 600, fetch)


# ── N / TOP ──────────────────────────────────────────────────────────────────
# Regional business feeds (keyless, checked 2026-10) — tagged with their home region
REGIONAL_FEEDS = {
    "Nikkei Asia": ("https://asia.nikkei.com/rss/feed/nar", "apac"), "SCMP Business": ("https://www.scmp.com/rss/92/feed", "apac"),
    "Economic Times": ("https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", "apac"),
    "BusinessLine": ("https://www.thehindubusinessline.com/markets/feeder/default.rss", "apac"),
    "CNA Business": ("https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6936", "apac"),
    "ABC Australia": ("https://www.abc.net.au/news/feed/51892/rss.xml", "apac"),
    "BBC Business": ("https://feeds.bbci.co.uk/news/business/rss.xml", "europe"), "Guardian Business": ("https://www.theguardian.com/uk/business/rss", "europe"),
    "DW Business": ("https://rss.dw.com/rdf/rss-en-bus", "europe"), "Euronews Business": ("https://www.euronews.com/rss?level=vertical&name=business", "europe"),
    "Africanews": ("https://www.africanews.com/feed/rss?themes=business", "mea"),
    "Moneyweb": ("https://www.moneyweb.co.za/feed/", "mea"),
    "CBC Business": ("https://www.cbc.ca/webfeed/rss/rss-business", "americas"), "Financial Post": ("https://financialpost.com/feed", "americas"),
    "MercoPress": ("https://en.mercopress.com/rss/", "americas"), "Buenos Aires Times": ("https://www.batimes.com.ar/feed", "americas"),
    "Mexico News Daily": ("https://mexiconewsdaily.com/feed/", "americas"),
}


def _articles(provider_feeds: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    from api.providers.news_provider import NewsProvider
    from api.calculations.news_sentiment import score_headline
    from api.marketdata.countries import countries_in
    p = NewsProvider()
    if provider_feeds is not None:
        p.feeds = provider_feeds
    res = p.fetch_all()
    if not res.success and not res.articles:
        return []
    out = []
    for a in res.articles or []:
        text = f"{a.title or ''} {a.summary or ''}"
        out.append({"title": a.title, "source": a.source, "url": a.url, "summary": (a.summary or "")[:280],
                    "time": a.published.replace(tzinfo=timezone.utc).isoformat() if a.published else None,
                    "sentiment": score_headline(a.title or ""), "countries": countries_in(text)})
    return out


def news_hub(q: Optional[str] = None, limit: int = 60, region: Optional[str] = None, country: Optional[str] = None) -> Dict[str, Any]:
    from api.marketdata.countries import region_of
    glob = _cached("newshub", 600, lambda: _articles())
    regional = _cached("newshub:regional", 900, lambda: _articles({k: v[0] for k, v in REGIONAL_FEEDS.items()}))
    feed_region = {k: v[1] for k, v in REGIONAL_FEEDS.items()}
    if not glob and not regional:
        raise Upstream("News feeds unreachable.")
    seen, items = set(), []
    for i in glob + regional:
        key = (i["title"] or "").strip().lower()[:90]
        if not key or key in seen:
            continue
        seen.add(key)
        items.append({**i, "region": feed_region.get(i["source"], "global"),
                      "regions": sorted({region_of(c) for c in i["countries"]} | ({feed_region[i["source"]]} if i["source"] in feed_region else set()))})
    items.sort(key=lambda i: i["time"] or "", reverse=True)
    if region and region != "global":
        items = [i for i in items if region in i["regions"]]
    if country:
        c = country.upper()
        items = [i for i in items if c in i["countries"]]
    if q:
        ql = q.lower()
        items = [i for i in items if ql in (i["title"] or "").lower() or ql in (i["summary"] or "").lower()]
    sources = sorted({i["source"] for i in items if i["source"]})
    return {"query": q, "region": region, "country": country, "items": items[:limit], "sources": sources, "count": len(items),
            "source": "RSS: " + ", ".join(sources) if sources else "RSS", "sentiment_note": "Finance word-list tone, −1 to +1.",
            "note": "Headlines are placed in a region by their outlet and by the countries they mention."}


# ── MAP: country equity markets via USD-listed MSCI country ETFs ─────────────
COUNTRY_ETFS = {
    "US": ("SPY", "S&P 500"), "CA": ("EWC", "MSCI Canada"), "MX": ("EWW", "MSCI Mexico"), "BR": ("EWZ", "MSCI Brazil"),
    "AR": ("ARGT", "MSCI Argentina"), "CL": ("ECH", "MSCI Chile"), "PE": ("EPU", "MSCI Peru"), "KW": ("KWT", "MSCI Kuwait"),      # GXG (Colombia) was delisted: Colombia uses ICOLCAP as its index
    "GB": ("EWU", "MSCI UK"), "DE": ("EWG", "MSCI Germany"), "FR": ("EWQ", "MSCI France"), "IT": ("EWI", "MSCI Italy"),
    "ES": ("EWP", "MSCI Spain"), "NL": ("EWN", "MSCI Netherlands"), "CH": ("EWL", "MSCI Switzerland"), "SE": ("EWD", "MSCI Sweden"),
    "NO": ("NORW", "MSCI Norway"), "DK": ("EDEN", "MSCI Denmark"), "FI": ("EFNL", "MSCI Finland"), "BE": ("EWK", "MSCI Belgium"),
    "AT": ("EWO", "MSCI Austria"), "IE": ("EIRL", "MSCI Ireland"), "PL": ("EPOL", "MSCI Poland"), "TR": ("TUR", "MSCI Turkey"),
    "IL": ("EIS", "MSCI Israel"), "SA": ("KSA", "MSCI Saudi Arabia"), "AE": ("UAE", "MSCI UAE"), "QA": ("QAT", "MSCI Qatar"),
    "ZA": ("EZA", "MSCI South Africa"), "IN": ("INDA", "MSCI India"),
    "CN": ("MCHI", "MSCI China"), "HK": ("EWH", "MSCI Hong Kong"), "TW": ("EWT", "MSCI Taiwan"), "KR": ("EWY", "MSCI Korea"),
    "JP": ("EWJ", "MSCI Japan"), "SG": ("EWS", "MSCI Singapore"), "MY": ("EWM", "MSCI Malaysia"), "TH": ("THD", "MSCI Thailand"),
    "ID": ("EIDO", "MSCI Indonesia"), "PH": ("EPHE", "MSCI Philippines"), "VN": ("VNM", "Vietnam"), "AU": ("EWA", "MSCI Australia"),
    "NZ": ("ENZL", "MSCI New Zealand"), "GR": ("GREK", "MSCI Greece"), "PT": ("PGAL", "Portugal"),
}


def world_map_markets() -> Dict[str, Any]:
    def fetch():
        import yfinance as yf
        syms = sorted({v[0] for v in COUNTRY_ETFS.values()})
        try:
            df = yf.download(syms, period="13mo", interval="1d", auto_adjust=True, group_by="ticker", progress=False, threads=True)
        except Exception as ex:
            raise Upstream(f"Country ETF prices unavailable: {ex}")
        out = {}
        for iso, (sym, label) in COUNTRY_ETFS.items():
            try:
                c = df[sym]["Close"].dropna()
            except Exception:
                continue
            if len(c) < 30:
                continue
            last = float(c.iloc[-1])
            prior_year = c[c.index.year < c.index[-1].year]
            out[iso] = {"etf": sym, "label": label, "price": last, "date": c.index[-1].strftime("%Y-%m-%d"),
                        "change_1d": last / float(c.iloc[-2]) - 1, "change_1m": last / float(c.iloc[-22]) - 1 if len(c) > 22 else None,
                        "change_ytd": last / float(prior_year.iloc[-1]) - 1 if len(prior_year) else None,
                        "change_1y": last / float(c.iloc[-253]) - 1 if len(c) > 253 else None}
        return {"countries": out, "source": "Yahoo Finance — USD-listed MSCI country ETFs (total return, in USD)"}
    return _cached("worldmap", 600, fetch)
