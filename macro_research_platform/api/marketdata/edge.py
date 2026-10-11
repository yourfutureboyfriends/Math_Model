"""
Edge data — sources that lead the official numbers or show who is positioned where (free):

  cot()          CFTC Commitments of Traders: hedge-fund (leveraged funds) and asset-manager
                 positioning in financial futures, managed money in commodities; net position,
                 3-year percentile and z-score, 1- and 4-week change. Weekly (Tuesday data, Friday release).
  predictions()  Real-money prediction markets (Polymarket, Kalshi): probabilities for Fed
                 decisions, inflation prints, recession, geopolitics — and how they moved in a day.
  nowcasts()     Atlanta Fed GDPNow, Cleveland Fed inflation nowcast (CPI / core / PCE / core PCE),
                 NY Fed Weekly Economic Index, Chicago Fed financial conditions.
  trade()        IMF PortWatch: daily world trade from satellite AIS (port calls, tonnes imported
                 and exported) and monthly trade nowcasts by country, weeks before customs data.
  ports_trade()  Daily cargo through the world's biggest ports vs a year ago.
  board()        The most unusual readings across all of the above, ranked.
"""
from __future__ import annotations

import csv
import io
import logging
import math
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from api.marketdata.core import Upstream, _cached

logger = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (macro research terminal)"}
CFTC = "https://publicreporting.cftc.gov/resource"
PW = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"


def _get(url: str, **kw):
    import requests
    r = requests.get(url, headers={**UA, **kw.pop("headers", {})}, timeout=kw.pop("timeout", 40), **kw)
    r.raise_for_status()
    return r


def pct(v: Optional[float]) -> str:
    return "—" if v is None else f"{v * 100:+.0f}%"


def _f(x) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ── COT ─────────────────────────────────────────────────────────────────────
# code → (label, group, report): "tff" = financial futures (leveraged funds / asset managers),
# "dis" = commodities (managed money)
COT_MARKETS = {
    "13874A": ("S&P 500 (E-mini)", "Equities", "tff"), "209742": ("Nasdaq 100 (mini)", "Equities", "tff"), "239742": ("Russell 2000 (E-mini)", "Equities", "tff"),
    "1170E1": ("VIX", "Equities", "tff"),
    "042601": ("2Y Treasury", "Rates", "tff"), "044601": ("5Y Treasury", "Rates", "tff"), "043602": ("10Y Treasury", "Rates", "tff"),
    "020601": ("Treasury bond", "Rates", "tff"), "020604": ("Ultra bond", "Rates", "tff"), "134741": ("SOFR 3M", "Rates", "tff"), "045601": ("Fed funds", "Rates", "tff"),
    "098662": ("US dollar index", "FX", "tff"), "099741": ("Euro", "FX", "tff"), "097741": ("Japanese yen", "FX", "tff"), "096742": ("British pound", "FX", "tff"),
    "090741": ("Canadian dollar", "FX", "tff"), "232741": ("Australian dollar", "FX", "tff"), "092741": ("Swiss franc", "FX", "tff"),
    "095741": ("Mexican peso", "FX", "tff"), "102741": ("Brazilian real", "FX", "tff"), "133741": ("Bitcoin", "Crypto", "tff"),
    "067651": ("WTI crude", "Energy", "dis"), "023651": ("Natural gas", "Energy", "dis"),
    "088691": ("Gold", "Metals", "dis"), "084691": ("Silver", "Metals", "dis"), "085692": ("Copper", "Metals", "dis"),
    "002602": ("Corn", "Agriculture", "dis"), "005602": ("Soybeans", "Agriculture", "dis"), "001602": ("Wheat (SRW)", "Agriculture", "dis"),
}


def _cot_rows(dataset: str, codes: List[str], fields: str) -> List[Dict[str, Any]]:
    since = (date.today() - timedelta(days=3 * 365 + 30)).isoformat()
    where = f"cftc_contract_market_code in ({','.join(repr(c) for c in codes)}) AND report_date_as_yyyy_mm_dd >= '{since}'"
    return _get(f"{CFTC}/{dataset}.json", params={"$select": f"cftc_contract_market_code,report_date_as_yyyy_mm_dd,open_interest_all,{fields}",
                                                  "$where": where, "$limit": 20000, "$order": "report_date_as_yyyy_mm_dd"}, timeout=60).json()


def _stats(series: List[float]) -> Dict[str, Any]:
    last = series[-1]
    pct = sum(1 for v in series if v <= last) / len(series)
    sd = statistics.pstdev(series) or 1.0
    return {"net": last, "pct_3y": round(pct, 3), "z_3y": round((last - statistics.fmean(series)) / sd, 2),
            "chg_1w": last - series[-2] if len(series) > 1 else None, "chg_4w": last - series[-5] if len(series) > 4 else None,
            "max_3y": max(series), "min_3y": min(series)}


def cot() -> Dict[str, Any]:
    def build():
        tff = [c for c, v in COT_MARKETS.items() if v[2] == "tff"]
        dis = [c for c, v in COT_MARKETS.items() if v[2] == "dis"]
        with ThreadPoolExecutor(2) as ex:
            f1 = ex.submit(_cot_rows, "gpe5-46if", tff, "lev_money_positions_long,lev_money_positions_short,asset_mgr_positions_long,asset_mgr_positions_short")
            f2 = ex.submit(_cot_rows, "72hh-3qpy", dis, "m_money_positions_long_all,m_money_positions_short_all,prod_merc_positions_long,prod_merc_positions_short")
            r1, r2 = f1.result(), f2.result()
        by: Dict[str, List[Dict[str, Any]]] = {}
        for r in r1 + r2:
            by.setdefault(r["cftc_contract_market_code"], []).append(r)
        out = []
        for code, rows in by.items():
            label, group, rep = COT_MARKETS[code]
            rows.sort(key=lambda r: r["report_date_as_yyyy_mm_dd"])
            if rep == "tff":
                spec = [(_f(r.get("lev_money_positions_long")) or 0) - (_f(r.get("lev_money_positions_short")) or 0) for r in rows]
                other = [(_f(r.get("asset_mgr_positions_long")) or 0) - (_f(r.get("asset_mgr_positions_short")) or 0) for r in rows]
                names = ("Hedge funds (leveraged)", "Asset managers")
            else:
                spec = [(_f(r.get("m_money_positions_long_all")) or 0) - (_f(r.get("m_money_positions_short_all")) or 0) for r in rows]
                other = [(_f(r.get("prod_merc_positions_long")) or 0) - (_f(r.get("prod_merc_positions_short")) or 0) for r in rows]
                names = ("Managed money", "Producers / merchants")
            oi = _f(rows[-1].get("open_interest_all")) or 0
            s = _stats(spec)
            out.append({"code": code, "market": label, "group": group, "date": rows[-1]["report_date_as_yyyy_mm_dd"][:10],
                        "spec_name": names[0], "other_name": names[1], **s, "pct_oi": round(s["net"] / oi, 4) if oi else None,
                        "other": _stats(other), "open_interest": oi,
                        "history": [{"date": r["report_date_as_yyyy_mm_dd"][:10], "spec": a, "other": b} for r, a, b in zip(rows, spec, other)][-156:],
                        "crowded": "long" if s["pct_3y"] >= 0.9 else "short" if s["pct_3y"] <= 0.1 else None})
        order = list(COT_MARKETS)
        out.sort(key=lambda r: order.index(r["code"]))
        return {"markets": out, "source": "CFTC Commitments of Traders (Traders in Financial Futures; Disaggregated), futures only",
                "note": "Net = longs − shorts in contracts. Percentile and z-score against the last three years. A reading in the top or "
                        "bottom decile is a crowded position: the trade most exposed to a reversal."}
    return _cached("edge:cot", 6 * 3600, build)


# ── Prediction markets ──────────────────────────────────────────────────────
POLY_TAGS = ["economy", "fed", "finance", "inflation", "business", "geopolitics", "crypto"]


def predictions() -> Dict[str, Any]:
    def build():
        import json as _json
        seen, out = set(), []
        for tag in POLY_TAGS:
            try:
                evs = _get("https://gamma-api.polymarket.com/events", params={"closed": "false", "limit": 40, "order": "volume24hr", "ascending": "false", "tag_slug": tag}).json()
            except Exception as e:
                logger.info("[pred] polymarket %s: %s", tag, e)
                continue
            for e in evs:
                if e.get("id") in seen:
                    continue
                seen.add(e.get("id"))
                mkts = []
                for m in e.get("markets") or []:
                    if m.get("closed"):
                        continue
                    try:
                        prices = [float(x) for x in _json.loads(m.get("outcomePrices") or "[]")]
                    except Exception:
                        continue
                    if not prices:
                        continue
                    mkts.append({"question": m.get("groupItemTitle") or m.get("question"), "yes": prices[0], "chg_1d": _f(m.get("oneDayPriceChange")),
                                 "chg_1w": _f(m.get("oneWeekPriceChange")), "volume_24h": _f(m.get("volume24hr")), "end": (m.get("endDate") or "")[:10]})
                if not mkts:
                    continue
                mkts.sort(key=lambda m: -m["yes"])
                out.append({"source": "Polymarket", "title": e.get("title"), "category": tag, "volume_24h": _f(e.get("volume24hr")) or 0,
                            "liquidity": _f(e.get("liquidity")), "end": (e.get("endDate") or "")[:10], "markets": mkts[:8]})
        # Kalshi (CFTC-regulated): Fed, CPI, GDP, recession series
        for series in ("KXFED", "KXCPIYOY", "KXGDP", "KXRECSSNBER", "KXPAYROLLS"):
            try:
                j = _get("https://api.elections.kalshi.com/trade-api/v2/events", params={"status": "open", "limit": 3, "series_ticker": series, "with_nested_markets": "true"}).json()
            except Exception as e:
                logger.info("[pred] kalshi %s: %s", series, e)
                continue
            for e in j.get("events") or []:
                mkts = []
                for m in e.get("markets") or []:
                    p = _f(m.get("last_price_dollars"))
                    prev = _f(m.get("previous_price_dollars"))
                    if p is None:
                        continue
                    mkts.append({"question": m.get("yes_sub_title") or m.get("subtitle") or m.get("ticker"), "yes": p, "chg_1d": (p - prev) if prev is not None else None,
                                 "volume_24h": _f(m.get("volume_24h")), "end": (m.get("close_time") or "")[:10]})
                if mkts:
                    mkts.sort(key=lambda m: -m["yes"])
                    out.append({"source": "Kalshi", "title": e.get("title"), "category": "economy", "volume_24h": sum(m["volume_24h"] or 0 for m in mkts),
                                "end": mkts[0]["end"], "markets": mkts[:8]})
        out.sort(key=lambda e: -(e["volume_24h"] or 0))
        return {"events": out, "source": "Polymarket (gamma API), Kalshi (public market data)",
                "note": "Prices are the market's probability (0–1) that the outcome happens. Moves of 10+ points in a day mean new information."}
    return _cached("edge:pred", 600, build)


# ── Nowcasts ────────────────────────────────────────────────────────────────
def _fred(sid: str, years: int = 3) -> List[Dict[str, Any]]:
    txt = _get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": sid, "cosd": (date.today() - timedelta(days=365 * years)).isoformat()}).text
    out = []
    for row in list(csv.reader(io.StringIO(txt)))[1:]:
        v = _f(row[1]) if len(row) > 1 else None
        if v is not None:
            out.append({"date": row[0], "value": v})
    return out


def _cleveland(kind: str) -> Dict[str, Any]:
    j = _get(f"https://www.clevelandfed.org/-/media/files/webcharts/inflationnowcasting/nowcast_{kind}.json?sc_lang=en").json()
    out = {}
    for block in j if isinstance(j, list) else [j]:
        period = (block.get("chart") or {}).get("subcaption")
        cats = [c.get("label") for c in ((block.get("categories") or [{}])[0].get("category") or [])]
        series = {}
        for ds in block.get("dataset") or []:
            name = ds.get("seriesname") or ""
            vals = [_f(d.get("value")) for d in ds.get("data") or []]
            pts = [(c, v) for c, v in zip(cats, vals) if v is not None]
            if pts:
                series[name] = {"latest": pts[-1][1], "as_of": pts[-1][0], "first": pts[0][1], "points": len(pts)}
        if period and series:
            out[period] = series
    return out


def nowcasts() -> Dict[str, Any]:
    def build():
        res: Dict[str, Any] = {}
        with ThreadPoolExecutor(5) as ex:
            futs = {"gdpnow": ex.submit(_fred, "GDPNOW", 3), "wei": ex.submit(_fred, "WEI", 3), "nfci": ex.submit(_fred, "NFCI", 3),
                    "infl_q": ex.submit(_cleveland, "quarter"), "infl_m": ex.submit(_cleveland, "month")}
            for k, f in futs.items():
                try:
                    res[k] = f.result()
                except Exception as e:
                    logger.info("[nowcast] %s: %s", k, e)
                    res[k] = None
        return {**res, "source": "Atlanta Fed GDPNow, NY Fed Weekly Economic Index, Chicago Fed NFCI (FRED); Cleveland Fed inflation nowcasting",
                "note": "GDPNow: real GDP growth (q/q annualised) for the quarter being tracked. WEI: weekly real activity scaled to "
                        "4-quarter GDP growth. NFCI: financial conditions, positive = tighter than average. Inflation nowcasts update daily."}
    return _cached("edge:nowcasts", 3 * 3600, build)


# ── Trade (IMF PortWatch) ───────────────────────────────────────────────────
def _pw(service: str, where: str, fields: str, order: str, n: int = 2000) -> List[Dict[str, Any]]:
    out, offset = [], 0
    while True:
        j = _get(f"{PW}/{service}/FeatureServer/0/query", params={"where": where, "outFields": fields, "orderByFields": order,
                                                                  "resultOffset": offset, "resultRecordCount": n, "f": "json"}, timeout=60).json()
        feats = [f["attributes"] for f in j.get("features") or []]
        out += feats
        if not j.get("exceededTransferLimit") or not feats:
            return out
        offset += len(feats)


def trade() -> Dict[str, Any]:
    def build():
        since = (date.today() - timedelta(days=760)).isoformat()
        regions = ["World", "China", "Advanced Economies", "Emerging Market and Developing Economies", "European Union", "Emerging and Developing Asia",
                   "Latin America and the Caribbean", "Major Advanced Economies (G7)"]
        names = ",".join(f"'{r}'" for r in regions)
        reg = _pw("Daily_Trade_Data_REG", f"country IN ({names}) AND date >= '{since}'",
                  "country,date,portcalls,import,export,import_container,import_tanker,import_dry_bulk", "date")
        series: Dict[str, List[Dict[str, Any]]] = {}
        for r in reg:
            series.setdefault(r["country"], []).append(r)
        world = sorted(series.get("World", []), key=lambda r: r["date"])

        def roll(xs: List[Dict[str, Any]], key: str, days: int = 7) -> Dict[str, float]:
            xs = sorted(xs, key=lambda r: r["date"])
            out = {}
            for i, r in enumerate(xs):
                w = xs[max(0, i - days + 1): i + 1]
                out[str(r["date"])[:10]] = sum((x.get(key) or 0) for x in w) / len(w)
            return out
        regional = []
        for name in regions:
            xs = series.get(name) or []
            if not xs:
                continue
            imp, exp = roll(xs, "import", 28), roll(xs, "export", 28)
            last = max(imp)
            ly = (date.fromisoformat(last) - timedelta(days=364)).isoformat()
            regional.append({"region": name, "as_of": last, "imports_t_day": imp[last], "exports_t_day": exp[last],
                             "imports_yoy": imp[last] / imp[ly] - 1 if imp.get(ly) else None, "exports_yoy": exp[last] / exp[ly] - 1 if exp.get(ly) else None})
        rows = []
        for i, r in enumerate(world):
            win = world[max(0, i - 6): i + 1]
            rows.append({"date": str(r["date"])[:10], "trade_7d": sum((x["import"] or 0) + (x["export"] or 0) for x in win) / len(win) / 2 / 1e6,
                         "container_7d": sum(x["import_container"] or 0 for x in win) / len(win) / 1e6,
                         "tanker_7d": sum(x["import_tanker"] or 0 for x in win) / len(win) / 1e6,
                         "dry_bulk_7d": sum(x["import_dry_bulk"] or 0 for x in win) / len(win) / 1e6, "portcalls": r["portcalls"]})
        by_date = {r["date"]: r for r in rows}

        def yoy(r, k):
            d = (date.fromisoformat(r["date"]) - timedelta(days=364)).isoformat()
            p = by_date.get(d)
            return r[k] / p[k] - 1 if p and p[k] else None
        last = rows[-1] if rows else None
        latest = {k: yoy(last, k) for k in ("trade_7d", "container_7d", "tanker_7d", "dry_bulk_7d")} if last else {}
        monthly = _pw("Monthly_TradeNow", f"date >= '{(date.today() - timedelta(days=500)).isoformat()}'", "region,ISO3,date,trade_value,trade_volume,value_import_total,value_export_total", "date")
        by_c: Dict[str, List[Dict[str, Any]]] = {}
        for m in monthly:
            by_c.setdefault(m["ISO3"], []).append(m)
        countries = []
        for iso3, ms in by_c.items():
            ms.sort(key=lambda m: m["date"])
            cur = ms[-1]
            prev_y = next((m for m in ms if m["date"][:7] == f"{int(cur['date'][:4]) - 1}{cur['date'][4:7]}"), None)
            countries.append({"iso3": iso3, "name": cur["region"], "month": cur["date"][:7], "trade_value": cur["trade_value"], "trade_volume": cur["trade_volume"],
                              "exports": cur["value_export_total"], "imports": cur["value_import_total"],
                              "value_yoy": cur["trade_value"] / prev_y["trade_value"] - 1 if prev_y and prev_y["trade_value"] else None,
                              "exports_yoy": cur["value_export_total"] / prev_y["value_export_total"] - 1 if prev_y and prev_y["value_export_total"] else None,
                              "imports_yoy": cur["value_import_total"] / prev_y["value_import_total"] - 1 if prev_y and prev_y["value_import_total"] else None})
        return {"world": rows[-400:], "world_yoy": latest, "as_of": last["date"] if last else None, "countries": countries, "regions": regional,
                "source": "IMF PortWatch (satellite AIS: port calls and estimated cargo tonnes; monthly TradeNow nowcasts)",
                "note": "Daily world seaborne trade (million tonnes a day, 7-day average). TradeNow: each country's trade in the latest month, "
                        "an index nowcast from ship movements, published weeks before customs statistics."}
    return _cached("edge:trade", 12 * 3600, build)


# G20 and the larger emerging traders: the countries whose trade swings move markets
MAJOR_TRADERS = {"USA", "CHN", "JPN", "DEU", "KOR", "IND", "GBR", "FRA", "ITA", "NLD", "BEL", "ESP", "CAN", "MEX", "BRA", "ARG", "CHL", "PER", "COL",
                 "AUS", "IDN", "MYS", "SGP", "THA", "VNM", "PHL", "TWN", "HKG", "SAU", "ARE", "QAT", "KWT", "IRQ", "IRN", "TUR", "EGY", "ZAF",
                 "NGA", "RUS", "POL", "NOR", "SWE"}

BIG_PORTS = ["Shanghai", "Singapore", "Ningbo-Zhoushan", "Shenzhen", "Qingdao", "Guangzhou", "Busan", "Tianjin", "Rotterdam", "Port Klang",
             "Antwerp", "Xiamen", "Kaohsiung", "Los Angeles-Long Beach", "Hamburg", "Tanjung Pelepas", "Laem Chabang", "Jebel Ali", "Houston",
             "New York-New Jersey", "Santos", "Colombo", "Piraeus", "Port Hedland", "Ras Tanura", "Tubarao", "Valencia", "Algeciras", "Mundra", "Savannah"]


def ports_trade() -> Dict[str, Any]:
    def build():
        # port complexes: every terminal whose name starts with the port's ("Shanghai" + "Shanghai (Yangshan)")
        like = " OR ".join("portname LIKE '" + p.replace("'", "''") + "%'" for p in BIG_PORTS)
        since = (date.today() - timedelta(days=420)).isoformat()
        rows = _pw("Daily_Ports_Data", f"({like}) AND date >= '{since}'", "date,portname,country,portcalls,import,export", "date")
        by: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for r in rows:
            base = next((p for p in sorted(BIG_PORTS, key=len, reverse=True) if r["portname"].startswith(p)), None)
            if not base:
                continue
            d = by.setdefault(base, {}).setdefault(str(r["date"])[:10], {"date": str(r["date"])[:10], "country": r["country"], "import": 0, "export": 0, "portcalls": 0})
            for k in ("import", "export", "portcalls"):
                d[k] += r.get(k) or 0
        out = []
        for name, days in by.items():
            rs = sorted(days.values(), key=lambda r: r["date"])
            last = date.fromisoformat(rs[-1]["date"][:10])

            def window(end: date, days: int = 28):
                xs = [r for r in rs if end - timedelta(days=days) < date.fromisoformat(r["date"][:10]) <= end]
                return sum((r["import"] or 0) + (r["export"] or 0) for r in xs) / max(1, len(xs)), sum(r["portcalls"] or 0 for r in xs) / max(1, len(xs))
            now_t, now_c = window(last)
            ly_t, ly_c = window(last - timedelta(days=364))
            pm_t, _ = window(last - timedelta(days=28))
            out.append({"port": name, "country": rs[-1]["country"], "as_of": str(last), "tonnes_day": now_t, "calls_day": now_c,
                        "yoy": now_t / ly_t - 1 if ly_t else None, "mom": now_t / pm_t - 1 if pm_t else None, "calls_yoy": now_c / ly_c - 1 if ly_c else None,
                        "spark": [round(((r["import"] or 0) + (r["export"] or 0)) / 1e3) for r in rs[-90:]]})
        out.sort(key=lambda r: -r["tonnes_day"])
        return {"ports": out, "source": "IMF PortWatch daily port activity (satellite AIS)",
                "note": "Cargo handled (imports + exports, tonnes a day, last 4 weeks) vs the same 4 weeks a year ago and the 4 weeks before."}
    return _cached("edge:ports", 12 * 3600, build)


# ── Signal board ────────────────────────────────────────────────────────────
def board() -> Dict[str, Any]:
    """The most unusual readings across positioning, prediction markets, trade, ports and fund flows."""
    def build():
        sig: List[Dict[str, Any]] = []

        def add(kind, title, detail, score, fn=None, symbol=None):
            sig.append({"kind": kind, "title": title, "detail": detail, "score": round(score, 2), "fn": fn, "symbol": symbol})
        try:
            for m in cot()["markets"]:
                if m["pct_3y"] >= 0.9 or m["pct_3y"] <= 0.1:
                    high = m["pct_3y"] >= 0.9
                    side = ("most long in 3 years" if m["net"] > 0 else "least short in 3 years") if high else ("most short in 3 years" if m["net"] < 0 else "least long in 3 years")
                    add("Positioning", f"{m['market']}: {m['spec_name'].lower()} {side}",
                        f"Net {m['net']:+,.0f} contracts, {m['pct_3y'] * 100:.0f}th percentile, z {m['z_3y']:+.1f}; 4-week change {m['chg_4w']:+,.0f}.",
                        min(4.5, 1.5 + abs(m["z_3y"]) + (0.5 if m["pct_3y"] in (0, 1) else 0)), "COT")
                elif m["chg_4w"] is not None and m["max_3y"] != m["min_3y"] and abs(m["chg_4w"]) / (m["max_3y"] - m["min_3y"]) > 0.35:
                    add("Positioning", f"Fast repositioning in {m['market']}", f"{m['spec_name']} moved {m['chg_4w']:+,.0f} contracts in 4 weeks "
                        f"({abs(m['chg_4w']) / (m['max_3y'] - m['min_3y']) * 100:.0f}% of the 3-year range).", 1.5 + abs(m["chg_4w"]) / (m["max_3y"] - m["min_3y"]), "COT")
        except Exception as e:
            logger.info("[board] cot: %s", e)
        try:
            import re as _re
            noise = _re.compile(r"(above|below|between) _+ on|up or down|price of .* on [A-Z][a-z]+ \d|daily|by \d{1,2}(am|pm)", _re.I)
            for e in predictions()["events"]:
                market_relevant = e["category"] in ("economy", "fed", "finance", "inflation") or (e["category"] in ("geopolitics", "business") and (e["volume_24h"] or 0) > 100_000)
                if not market_relevant or noise.search(e["title"] or ""):
                    continue
                for m in e["markets"]:
                    ch = m.get("chg_1d")
                    if ch is None or abs(ch) < 0.08 or (m.get("volume_24h") or 0) < 10_000 or not (0.03 <= m["yes"] <= 0.97 or abs(ch) >= 0.25):
                        continue
                    add("Prediction markets", f"{e['title']}: {m['question']}",
                        f"Now {m['yes'] * 100:.0f}% ({ch * 100:+.0f} pts in a day) on {e['source']}; 24h volume ${m['volume_24h']:,.0f}.",
                        min(4.0, abs(ch) * 8), "PRED")
        except Exception as e:
            logger.info("[board] pred: %s", e)
        try:
            for p in ports_trade()["ports"]:
                if p["yoy"] is not None and abs(p["yoy"]) >= 0.15:
                    add("Trade", f"{p['port']} cargo {p['yoy'] * 100:+.0f}% vs a year ago",
                        f"{p['tonnes_day'] / 1e3:,.0f}k tonnes a day over 4 weeks to {p['as_of']}; month-on-month {p['mom'] * 100:+.0f}%.", min(3.5, 1 + abs(p["yoy"]) * 5), "NOW")
            t = trade()
            for c in t["countries"]:
                if c["iso3"] not in MAJOR_TRADERS:
                    continue
                ex, im = c.get("exports_yoy"), c.get("imports_yoy")
                big = max(abs(ex or 0), abs(im or 0))
                if big >= 0.15:
                    add("Trade", f"{c['name']} trade nowcast: exports {pct(ex)}, imports {pct(im)} y/y ({c['month']})",
                        "IMF PortWatch TradeNow from ship movements — weeks ahead of customs data.", min(3.5, 1 + big * 5), "NOW")
            for r in t.get("regions") or []:
                ex, im = r.get("exports_yoy"), r.get("imports_yoy")
                big = max(abs(ex or 0), abs(im or 0))
                if big >= 0.08:
                    add("Trade", f"{r['region']} seaborne trade: exports {pct(ex)}, imports {pct(im)} vs a year ago",
                        f"Last 4 weeks to {r['as_of']} (IMF PortWatch, daily satellite AIS).", min(3.5, 1 + big * 10), "NOW")
        except Exception as e:
            logger.info("[board] trade: %s", e)
        try:
            from api.marketdata import flows
            for r in flows.etf()["rows"]:
                if (r.get("volume_surge") or 0) >= 1.8:
                    add("Fund flows", f"{r['symbol']} ({r['label']}) trading {r['volume_surge']:.1f}× its usual dollar volume",
                        f"Money-flow 1W {(r['mf_1w'] or 0) * 100:+.0f}, price 1W {r['chg_1w'] * 100:+.1f}%.", min(3.5, r["volume_surge"]), "FLOW", r["symbol"])
                if r.get("flows", {}).get("week_usd") is not None and r["flows"].get("aum_usd") and abs(r["flows"]["week_usd"]) / r["flows"]["aum_usd"] > 0.03:
                    w = r["flows"]["week_usd"]
                    add("Fund flows", f"{r['symbol']} {'creations' if w > 0 else 'redemptions'} of ${abs(w) / 1e6:,.0f}M this week",
                        f"{abs(w) / r['flows']['aum_usd'] * 100:.1f}% of assets.", 2 + abs(w) / r["flows"]["aum_usd"] * 20, "FLOW", r["symbol"])
        except Exception as e:
            logger.info("[board] etf: %s", e)
        try:
            from api.marketdata import insights
            v = insights.vol()
            if v["ratio_vix_vix3m"] > 1:
                add("Volatility", "VIX term structure inverted (backwardation)", f"VIX {v['vix']} above VIX3M: ratio {v['ratio_vix_vix3m']:.2f} — near-term stress priced.", 4.0, "VOL")
            elif (v.get("ratio_pct_3y") or 1) <= 0.05:
                add("Volatility", "VIX curve unusually steep — complacency", f"VIX/VIX3M {v['ratio_vix_vix3m']:.2f}, bottom 5% of 3 years; variance premium {v['variance_premium']:+.1f} pts.", 2.5, "VOL")
            for ix in v["indices"]:
                if ix.get("pct_3y") is not None and ix["pct_3y"] >= 0.95 and ix["symbol"] not in ("^VIX9D", "^VIX3M", "^VIX6M", "^VIX1Y"):
                    add("Volatility", f"{ix['name']} at a 3-year high zone ({ix['last']})", f"{ix['pct_3y'] * 100:.0f}th percentile of 3 years.", 2.8, "VOL")
            b = insights.breadth()
            lt = b["latest"]
            r = insights.risk()
            trend = next((c["value"] for c in r["components"] if c["key"] == "spx_trend"), None)
            if trend is not None and trend > 3 and lt["above50"] < 45:
                add("Breadth", f"Narrow market: index {trend:+.1f}% above its 200-day, only {lt['above50']:.0f}% of members above their 50-day",
                    f"{lt['above200']:.0f}% above the 200-day; McClellan {lt['mcclellan']:+.0f}. Leadership is concentrated.", 3.0, "BRDT")
            if abs(lt["mcclellan"] or 0) >= 60:
                add("Breadth", f"McClellan oscillator {lt['mcclellan']:+.0f} — {'overbought' if lt['mcclellan'] > 0 else 'oversold'}", "S&P 500 advance/decline momentum at an extreme.", 2.6, "BRDT")
            if r["recession_prob_12m"] >= 0.3:
                add("Macro", f"Yield-curve recession probability {r['recession_prob_12m'] * 100:.0f}% (12 months)", f"10y−3m spread {r['curve_3m10y_avg']:+.2f}pp (NY Fed model).", 3.2, "RISK")
            for m in insights.implied_moves()["rows"]:
                if m.get("ratio") and (m["ratio"] >= 1.8 or m["ratio"] <= 0.6) and m.get("n", 0) >= 4:
                    rich = m["ratio"] >= 1.8
                    add("Options", f"{m['symbol']} earnings {m['date']}: options price ±{m['implied_move'] * 100:.1f}% vs a typical ±{m['avg_abs_move'] * 100:.1f}%",
                        f"Implied move {m['ratio']:.1f}× its average over the last {m['n']} reports — options look {'rich' if rich else 'cheap'}.",
                        min(3.2, 1.5 + abs(math.log(m["ratio"])) * 2), "IMPM", m["symbol"])
            for h in insights.uoa()["hits"][:6]:
                add("Options", f"{h['symbol']} {h['expiry']} {h['strike']:g} {h['kind']}s: {h['volume']:,} contracts vs {h['open_interest']:,} open",
                    f"${h['premium'] / 1e6:,.1f}M premium{f', {h["vol_oi"]}× open interest' if h.get('vol_oi') else ''}.", min(3.0, 1.5 + h["premium"] / 2e7), "UOA", h["symbol"])
        except Exception as e:
            logger.info("[board] insights: %s", e)
        sig.sort(key=lambda s: -s["score"])
        # keep the board varied: at most 12 signals of any one kind
        per: Dict[str, int] = {}
        varied = []
        for x in sig:
            per[x["kind"]] = per.get(x["kind"], 0) + 1
            if per[x["kind"]] <= 12:
                varied.append(x)
        return {"signals": varied[:50], "generated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
                "note": "Ranked by how unusual each reading is (z-scores, percentile extremes, size of the move). Not advice — a list of where to look."}
    return _cached("edge:board", 1800, build)
