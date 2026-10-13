"""
FLOW — where money is moving, from official and market data (free sources):

  tic()         US Treasury TIC: foreigners' net purchases of US Treasuries, agency bonds,
                corporate bonds and stocks by country (money into the US), and US residents' net
                purchases of foreign bonds and stocks by country (money out). Monthly, ~6 weeks late.
  bis()         BIS locational banking statistics: change in cross-border bank claims on each
                country (exchange-rate adjusted flows), quarterly.
  etf()         US-listed country, asset-class and sector ETFs: creations / redemptions (daily
                change in shares outstanding × price, from our own daily snapshots) and a
                price × volume money-flow indicator over 1 week and 1 month.
  crypto()      Stablecoin supply by blockchain (DefiLlama): dollars moving on-chain.
  liquidity()   Fed net liquidity: balance sheet − Treasury General Account − reverse repo (FRED).
"""
from __future__ import annotations

import csv
import io
import json
import logging
import math
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from api.marketdata.core import Upstream, _cached

logger = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (macro research terminal)"}
TIC = "https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents"
SNAP = Path(__file__).resolve().parents[2] / "data" / "processed" / "etf_shares.json"

TIC_NAMES = {"China, Mainland": "CN", "Korea, South": "KR", "Russia": "RU", "Taiwan": "TW", "Turkey": "TR", "United Kingdom": "GB",
             "Czech Republic": "CZ", "British Virgin Islands": "VG", "Cayman Islands": "KY", "Curacao": "CW", "Saint Kitts and Nevis": "KN",
             "Syria": "SY", "Venezuela": "VE", "Hong Kong": "HK", "Bahamas": "BS", "Guernsey": "GG", "Jersey": "JE", "Anguilla": "AI",
             "Aruba": "AW", "Bermuda": "BM", "Monaco": "MC", "United Arab Emirates": "AE", "Trinidad and Tobago": "TT", "Iran": "IR",
             "Vietnam": "VN", "Bolivia": "BO", "Tanzania": "TZ", "Moldova": "MD", "Macedonia": "MK", "Laos": "LA", "Brunei": "BN"}


def _get(url: str, **kw):
    import requests
    r = requests.get(url, headers=UA, timeout=kw.pop("timeout", 40), **kw)
    r.raise_for_status()
    return r


def _iso_of(name: str) -> Optional[str]:
    from api.marketdata.countries import COUNTRIES
    n = name.strip()
    if n in TIC_NAMES:
        return TIC_NAMES[n]
    low = n.lower()
    for c in COUNTRIES:
        if c["name"].lower() == low:
            return c["iso2"]
    return None


def _num(x: str) -> Optional[float]:
    try:
        return float(x.replace(",", ""))
    except (ValueError, AttributeError):
        return None


# ── TIC ─────────────────────────────────────────────────────────────────────
def _tic_table(n: int) -> List[Dict[str, Any]]:
    """Rows of SLT table n (machine field names from the header row)."""
    def fetch():
        txt = _get(f"{TIC}/slt_table{n}.txt").text
        lines = txt.splitlines()
        hi = next(i for i, l in enumerate(lines) if l.startswith("country\tcountry_code\tdate"))
        cols = lines[hi].split("\t")
        out = []
        for l in lines[hi + 1:]:
            p = l.split("\t")
            if len(p) < 4 or not p[2][:4].isdigit():
                continue
            row = {"name": p[0].strip(), "code": p[1].strip(), "date": p[2].strip()}
            for c, v in zip(cols[3:], p[3:]):
                row[c] = _num(v)
            out.append(row)
        return out
    return _cached(f"tic:t{n}", 12 * 3600, fetch)


INFLOW = {"total": "for_lt_total_net", "treasuries": "for_lt_treas_net", "agency": "for_lt_agcy_net", "corp_bonds": "for_lt_corp_net", "stocks": "for_lt_eqty_net"}
OUTFLOW = {"total": "us_lt_total_net", "govt_bonds": "us_lt_govt_bond_net", "corp_bonds": "us_lt_corp_bond_net", "stocks": "us_lt_eqty_net"}


def tic() -> Dict[str, Any]:
    def build():
        t1, t2 = _tic_table(1), _tic_table(2)
        months = sorted({r["date"] for r in t1}, reverse=True)
        latest = months[0]
        last3, last12 = set(months[:3]), set(months[:12])

        def agg(rows, fields, posf):
            out: Dict[str, Dict[str, Any]] = {}
            for r in rows:
                iso = _iso_of(r["name"])
                if not iso:
                    continue
                c = out.setdefault(iso, {"iso2": iso, "name": r["name"], "m1": {}, "m3": {}, "m12": {}, "holdings": None})
                for k, f in fields.items():
                    v = r.get(f)
                    if v is None:
                        continue
                    if r["date"] == latest:
                        c["m1"][k] = v
                    if r["date"] in last3:
                        c["m3"][k] = c["m3"].get(k, 0) + v
                    if r["date"] in last12:
                        c["m12"][k] = c["m12"].get(k, 0) + v
                if r["date"] == latest:
                    c["holdings"] = r.get(posf)
            return out
        inflow = agg(t1, INFLOW, "for_lt_total_pos")
        outflow = agg(t2, OUTFLOW, "us_lt_total_pos")
        world_in = next((r for r in t1 if r["name"].startswith("Grand Total") and r["date"] == latest), None)
        world_out = next((r for r in t2 if r["name"].startswith("Grand Total") and r["date"] == latest), None)
        return {"latest": latest, "months": months[:24], "into_us": list(inflow.values()), "out_of_us": list(outflow.values()),
                "total_into_us": {k: world_in.get(f) for k, f in INFLOW.items()} if world_in else None,
                "total_out_of_us": {k: world_out.get(f) for k, f in OUTFLOW.items()} if world_out else None,
                "units": "USD millions", "source": "US Treasury TIC (SLT tables 1 and 2), monthly",
                "note": "Into the US: foreign residents' net purchases of US long-term securities, by the country of the buyer's custodian "
                        "(financial centres such as the UK, Cayman, Luxembourg and Belgium stand in for investors elsewhere). "
                        "Out of the US: US residents' net purchases of that country's securities."}
    return _cached("tic:summary", 12 * 3600, build)


def tic_country(iso: str) -> Dict[str, Any]:
    iso = iso.upper()
    t1, t2 = _tic_table(1), _tic_table(2)
    rows: Dict[str, Dict[str, Any]] = {}
    name = None
    for r in t1:
        if _iso_of(r["name"]) == iso:
            name = r["name"]
            d = rows.setdefault(r["date"], {"date": r["date"]})
            for k, f in INFLOW.items():
                d[f"in_{k}"] = r.get(f)
            d["holdings_us_securities"] = r.get("for_lt_total_pos")
            d["holdings_treasuries"] = r.get("for_lt_treas_pos")
    for r in t2:
        if _iso_of(r["name"]) == iso:
            d = rows.setdefault(r["date"], {"date": r["date"]})
            for k, f in OUTFLOW.items():
                d[f"out_{k}"] = r.get(f)
            d["us_holdings_there"] = r.get("us_lt_total_pos")
    if not rows:
        raise Upstream(f"No TIC data for {iso}.")
    return {"iso2": iso, "name": name, "rows": [rows[k] for k in sorted(rows)][-60:], "units": "USD millions", "source": "US Treasury TIC"}


# ── BIS cross-border bank lending ───────────────────────────────────────────
def bis() -> Dict[str, Any]:
    def build():
        url = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_LBS_D_PUB/1.0/Q.{m}.C.A.TO1.A.5J.A.5A.A..N"
        flows = _get(url.format(m="F"), params={"lastNObservations": 4, "format": "csv"}, timeout=60).text
        stocks = _get(url.format(m="S"), params={"lastNObservations": 1, "format": "csv"}, timeout=60).text
        by: Dict[str, Dict[str, Any]] = {}
        for r in csv.DictReader(io.StringIO(flows)):
            cc = r.get("L_CP_COUNTRY") or ""
            v = _num(r.get("OBS_VALUE") or "")
            if len(cc) != 2 or not cc.isalpha() or v is None:
                continue
            by.setdefault(cc, {"iso2": cc, "q": {}})["q"][r["TIME_PERIOD"]] = v
        for r in csv.DictReader(io.StringIO(stocks)):
            cc = r.get("L_CP_COUNTRY") or ""
            if cc in by:
                by[cc]["claims"] = _num(r.get("OBS_VALUE") or "")
        quarters = sorted({q for c in by.values() for q in c["q"]})
        last = quarters[-1] if quarters else None
        out = []
        for c in by.values():
            qv = [c["q"].get(q) for q in quarters[-4:]]
            out.append({"iso2": c["iso2"], "last_q": c["q"].get(last), "four_q": sum(v for v in qv if v is not None) if any(v is not None for v in qv) else None,
                        "claims": c.get("claims"), "pct_of_claims": round(c["q"][last] / c["claims"] * 100, 2) if c.get("claims") and c["q"].get(last) is not None else None})
        return {"quarter": last, "quarters": quarters, "countries": out, "units": "USD millions",
                "source": "BIS locational banking statistics (all reporting banks' cross-border claims, exchange-rate adjusted change)",
                "note": "Positive: banks abroad lent more to (or bought more claims on) that country this quarter. Quarterly, ~4 months late."}
    return _cached("bis:lbs", 24 * 3600, build)


# ── ETFs: creations / redemptions and money flow ────────────────────────────
ASSET_ETFS = {
    "SPY": "US large caps", "QQQ": "Nasdaq 100", "IWM": "US small caps", "EFA": "Developed ex-US", "EEM": "Emerging markets", "ACWI": "World stocks",
    "TLT": "20y+ Treasuries", "IEF": "7–10y Treasuries", "SHY": "1–3y Treasuries", "BIL": "T-bills (cash)", "TIP": "TIPS", "AGG": "US aggregate bonds",
    "LQD": "IG corporate bonds", "HYG": "High-yield bonds", "EMB": "EM dollar bonds", "MUB": "Municipal bonds",
    "GLD": "Gold", "SLV": "Silver", "USO": "Crude oil", "UNG": "Natural gas", "DBC": "Commodities", "VNQ": "US real estate",
    "IBIT": "Bitcoin", "ETHA": "Ether", "UUP": "US dollar", "FXE": "Euro", "FXY": "Yen",
}
SECTOR_ETFS = {"XLK": "Technology", "XLF": "Financials", "XLE": "Energy", "XLV": "Health care", "XLI": "Industrials", "XLY": "Consumer discretionary",
               "XLP": "Consumer staples", "XLU": "Utilities", "XLB": "Materials", "XLRE": "Real estate", "XLC": "Communication", "SMH": "Semiconductors",
               "KRE": "Regional banks", "XBI": "Biotech", "ITA": "Defence", "KWEB": "China internet"}


def _universe() -> Dict[str, Dict[str, str]]:
    from api.marketdata.monitors import COUNTRY_ETFS
    u = {sym: {"group": "country", "label": label, "iso2": iso} for iso, (sym, label) in COUNTRY_ETFS.items()}
    u.update({s: {"group": "asset", "label": l} for s, l in ASSET_ETFS.items()})
    u.update({s: {"group": "sector", "label": l} for s, l in SECTOR_ETFS.items()})
    return u


_snap_lock = threading.Lock()


def _snap_load() -> Dict[str, Dict[str, list]]:
    try:
        return json.loads(SNAP.read_text())
    except Exception:
        return {}


def snapshot_shares() -> int:
    """Record today's shares outstanding and price for every ETF in the universe (weekdays)."""
    import yfinance as yf
    today = date.today()
    if today.weekday() >= 5:
        return 0
    key = today.isoformat()
    with _snap_lock:
        snaps = _snap_load()
        if key in snaps and len(snaps[key]) > 0.8 * len(_universe()):
            return 0
    day: Dict[str, list] = {}
    for sym in _universe():
        try:
            info = yf.Ticker(sym).info
            sh = info.get("sharesOutstanding")
            px = info.get("navPrice") or info.get("regularMarketPrice") or info.get("previousClose")
            if sh and px:
                day[sym] = [float(sh), float(px)]
        except Exception as e:
            logger.debug("[flow] %s: %s", sym, e)
        time.sleep(0.2)
    with _snap_lock:
        snaps = _snap_load()
        snaps[key] = day
        keep = dict(sorted(snaps.items())[-400:])
        SNAP.parent.mkdir(parents=True, exist_ok=True)
        SNAP.write_text(json.dumps(keep, separators=(",", ":")))
    logger.info("[flow] ETF share snapshot: %d funds", len(day))
    return len(day)


def snapshots_start() -> None:
    def loop():
        while True:
            try:
                now = datetime.now(timezone.utc)
                if now.hour >= 21 or now.hour < 12:          # after the US close: the day's creations are in
                    snapshot_shares()
            except Exception as e:
                logger.warning("[flow] snapshot failed: %s", e)
            time.sleep(1800)
    threading.Thread(target=loop, name="etf-shares", daemon=True).start()


def etf() -> Dict[str, Any]:
    def build():
        import yfinance as yf
        uni = _universe()
        syms = list(uni)
        px = yf.download(syms, period="3mo", interval="1d", auto_adjust=False, progress=False, threads=True, group_by="ticker")
        snaps = _snap_load()
        days = sorted(snaps)
        rows = []
        for s in syms:
            try:
                d = px[s].dropna(subset=["Close", "Volume"])
            except Exception:
                continue
            if len(d) < 25:
                continue
            tp = (d["High"] + d["Low"] + d["Close"]) / 3
            dv = tp * d["Volume"]
            sign = (tp.diff() > 0).astype(float) - (tp.diff() < 0).astype(float)
            # cash-like funds accrue a little every day: an up/down volume split means nothing there
            calm = float(d["Close"].pct_change().iloc[-21:].std() or 0) < 0.0008

            def mf(n):
                if calm:
                    return None
                w = (dv * sign).iloc[-n:]
                tot = dv.iloc[-n:].sum()
                return float(w.sum() / tot) if tot else None
            avg_dv = float(dv.iloc[-21:].mean())
            # creations / redemptions from our share snapshots
            flows = {}
            series = [(k, snaps[k][s]) for k in days if s in snaps[k]]
            if len(series) >= 2:
                (d0, a), (d1, b) = series[-2], series[-1]
                flows["last_usd"] = (b[0] - a[0]) * b[1]
                flows["last_dates"] = [d0, d1]
                first = next(((k, v) for k, v in series if (date.fromisoformat(series[-1][0]) - date.fromisoformat(k)).days <= 7), None)
                if first and first[0] != series[-1][0]:
                    flows["week_usd"] = (b[0] - first[1][0]) * b[1]
                flows["since"] = series[0][0]
                flows["total_usd"] = (b[0] - series[0][1][0]) * b[1]
                flows["aum_usd"] = b[0] * b[1]
            rows.append({"symbol": s, **uni[s], "price": float(d["Close"].iloc[-1]),
                         "chg_1w": float(d["Close"].iloc[-1] / d["Close"].iloc[-6] - 1), "chg_1m": float(d["Close"].iloc[-1] / d["Close"].iloc[-22] - 1),
                         "mf_1w": mf(5), "mf_1m": mf(21), "dollar_volume": avg_dv,
                         "volume_surge": float(dv.iloc[-5:].mean() / avg_dv) if avg_dv else None, **({"flows": flows} if flows else {})})
        return {"rows": rows, "snapshots": len(days), "first_snapshot": days[0] if days else None,
                "source": "Yahoo Finance prices and shares outstanding (daily snapshots kept by this terminal)",
                "note": "Flows = change in shares outstanding × price (fund creations minus redemptions), from daily snapshots this terminal "
                        "records after each US close. Money-flow indicator: share of the period's dollar volume traded on up days minus down "
                        "days (−1 to +1) — a pressure gauge, not a fund-flow figure."}
    return _cached("flow:etf", 1800, build)


# ── Stablecoins ─────────────────────────────────────────────────────────────
def crypto() -> Dict[str, Any]:
    def build():
        chains = _get("https://stablecoins.llama.fi/stablecoinchains").json()
        top = sorted(({"chain": c["name"], "usd": (c.get("totalCirculatingUSD") or {}).get("peggedUSD") or 0} for c in chains), key=lambda c: -c["usd"])[:15]
        hist = _get("https://stablecoins.llama.fi/stablecoincharts/all").json()
        tot = [(datetime.fromtimestamp(int(h["date"]), tz=timezone.utc).date().isoformat(), (h.get("totalCirculatingUSD") or {}).get("peggedUSD")) for h in hist]
        tot = [t for t in tot if t[1]]

        def chg(series, days):
            if len(series) <= days:
                return None
            return series[-1][1] - series[-1 - days][1]
        for c in top[:10]:
            try:
                h = _get(f"https://stablecoins.llama.fi/stablecoincharts/{c['chain']}").json()
                s = [(int(x["date"]), (x.get("totalCirculatingUSD") or {}).get("peggedUSD")) for x in h if (x.get("totalCirculatingUSD") or {}).get("peggedUSD")]
                c["chg_7d"], c["chg_30d"] = chg(s, 7), chg(s, 30)
            except Exception:
                pass
        return {"total": tot[-1][1] if tot else None, "chg_7d": chg(tot, 7), "chg_30d": chg(tot, 30), "chg_90d": chg(tot, 90),
                "history": [{"date": d, "usd": v} for d, v in tot[-730:]], "chains": top,
                "source": "DefiLlama (stablecoin supply, all dollar-pegged coins)",
                "note": "New stablecoins are minted when dollars come on-chain and burned when they leave: supply growth is money flowing into crypto."}
    return _cached("flow:crypto", 3600, build)


# ── Fed net liquidity ───────────────────────────────────────────────────────
def liquidity() -> Dict[str, Any]:
    def series(sid: str):
        txt = _get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": sid, "cosd": (date.today() - timedelta(days=3 * 365)).isoformat()}).text
        out = {}
        for row in list(csv.reader(io.StringIO(txt)))[1:]:
            v = _num(row[1]) if len(row) > 1 else None
            if v is not None:
                out[row[0]] = v
        return out

    def build():
        walcl, tga, rrp = series("WALCL"), series("WTREGEN"), series("RRPONTSYD")     # $mn, $mn (weekly), $bn (daily)
        rrp_days = sorted(rrp)
        rows = []
        for d in sorted(walcl):
            if d not in tga:
                continue
            r = next((rrp[x] for x in reversed(rrp_days) if x <= d), None)
            if r is None:
                continue
            net = walcl[d] / 1000 - tga[d] / 1000 - r            # $bn
            rows.append({"date": d, "net_liquidity": round(net, 1), "fed_balance_sheet": round(walcl[d] / 1000, 1),
                         "tga": round(tga[d] / 1000, 1), "reverse_repo": round(r, 1)})
        if not rows:
            raise Upstream("FRED liquidity series unavailable")
        last = rows[-1]
        prev4 = rows[-5] if len(rows) >= 5 else rows[0]
        return {"rows": rows, "latest": last, "chg_4w": round(last["net_liquidity"] - prev4["net_liquidity"], 1),
                "chg_13w": round(last["net_liquidity"] - (rows[-14] if len(rows) >= 14 else rows[0])["net_liquidity"], 1),
                "units": "USD billions", "source": "FRED: WALCL, WTREGEN, RRPONTSYD",
                "note": "Net liquidity = Fed balance sheet − Treasury's cash account (TGA) − overnight reverse repo: the dollars the Fed system leaves in markets."}
    return _cached("flow:liquidity", 6 * 3600, build)
