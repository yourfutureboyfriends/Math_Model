"""Accuracy audit: compare what the platform shows with independent sources.

    ../.venv/bin/python scripts/audit_accuracy.py [--base http://localhost:8000] [--out data/processed/audit]

Each check fetches one output from the running API (or the dashboard snapshot) and a reference value from a source the
platform does not use for that number (FRED, ECB, NY Fed, CoinGecko, the Massive daily-bars store, Yahoo for SEC-based
figures), then records PASS / WARN / FAIL with the difference. Checks that have no outside reference test internal
consistency instead (a probability distribution sums to 1, a spread equals its legs' difference, …).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
import time
import traceback
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASE = "http://localhost:8000"
UA = {"User-Agent": "Mozilla/5.0 (MacroTerminal accuracy audit)"}
RESULTS: List[Dict[str, Any]] = []


# ── fetch helpers ────────────────────────────────────────────────────────────
def api(path: str, timeout: int = 300) -> Any:
    req = urllib.request.Request(BASE + path, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def http(url: str, timeout: int = 40) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


_FRED: Dict[str, Dict[str, float]] = {}


def fred(sid: str, days: int = 60) -> Dict[str, float]:
    if sid not in _FRED:
        txt = http(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={(date.today() - timedelta(days=days)).isoformat()}")
        out = {}
        for row in list(csv.reader(io.StringIO(txt)))[1:]:
            try:
                out[row[0]] = float(row[1])
            except (ValueError, IndexError):
                pass
        _FRED[sid] = out
    return _FRED[sid]


def fred_last(sid: str, on: Optional[str] = None) -> tuple:
    s = fred(sid, 400)
    keys = sorted(k for k in s if on is None or k <= on)
    return (keys[-1], s[keys[-1]]) if keys else (None, None)


def ecb_rates() -> Dict[str, Any]:
    txt = http("https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml")
    import re
    day = re.search(r"time='([\d-]+)'", txt).group(1)
    return {"date": day, **{c: float(r) for c, r in re.findall(r"currency='(\w+)' rate='([\d.]+)'", txt)}}


# ── recording ────────────────────────────────────────────────────────────────
def record(area: str, item: str, ours: Any, ref: Any, source: str, tol: Optional[float] = None, rel: bool = False,
           note: str = "", status: Optional[str] = None) -> None:
    diff = None
    if status is None:
        if ours is None:
            status = "FAIL"
            note = (note + " — the platform returned no value").strip(" —")
        elif ref is None or tol is None:
            status = "INFO"
        else:
            diff = (ours / ref - 1) if rel and ref else (ours - ref)
            status = "PASS" if abs(diff) <= tol else ("WARN" if abs(diff) <= 2 * tol else "FAIL")
    elif isinstance(ours, (int, float)) and isinstance(ref, (int, float)):
        diff = (ours / ref - 1) if rel and ref else ours - ref
    RESULTS.append({"area": area, "item": item, "ours": ours, "ref": ref, "diff": diff, "tolerance": tol, "relative": rel,
                    "source": source, "status": status, "note": note})
    flag = {"PASS": "  ok ", "WARN": " WARN", "FAIL": " FAIL", "INFO": " info", "ERROR": "  ERR"}[status]
    d = "" if diff is None else (f" diff {diff:+.2%}" if rel else f" diff {diff:+.4g}")
    print(f"{flag} {area:<14} {item:<44} ours={_fmt(ours)} ref={_fmt(ref)}{d}  {note}")


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)[:40]


def check(area: str, name: str):
    def deco(fn: Callable[[], None]):
        def run():
            try:
                fn()
            except Exception as e:                              # noqa: BLE001 — one broken check must not stop the audit
                RESULTS.append({"area": area, "item": name, "status": "ERROR", "note": f"{type(e).__name__}: {e}"[:300],
                                "trace": traceback.format_exc()[-800:]})
                print(f"  ERR {area:<14} {name:<44} {type(e).__name__}: {str(e)[:160]}")
        run.__name__ = fn.__name__
        CHECKS.append(run)
        return run
    return deco


CHECKS: List[Callable[[], None]] = []


# ── markets ──────────────────────────────────────────────────────────────────
def ours_on(sym: str, day: str) -> Optional[float]:
    """Our close for a symbol on a given date (price-history screen), so comparisons use the same day."""
    h = api(f"/api/v1/mkt/hp/{urllib.request.quote(sym)}")
    row = next((r for r in h["rows"] if r["date"] == day), None)
    return row["close"] if row else None


@check("Markets", "WEI index and FX levels vs FRED")
def _wei():
    ov = api("/api/v1/mkt/overview")
    rows = {r["symbol"]: r for g in ov["groups"] for r in g["rows"]}
    for sym, sid, label, tol in (("^GSPC", "SP500", "S&P 500", 0.002), ("^DJI", "DJIA", "Dow Jones", 0.002),
                                 ("^IXIC", "NASDAQCOM", "Nasdaq Composite", 0.002), ("^N225", "NIKKEI225", "Nikkei 225", 0.003),
                                 ("^VIX", "VIXCLS", "VIX", 0.02), ("CL=F", "DCOILWTICO", "WTI crude (front future vs spot)", 0.05)):
        fd, fv = fred_last(sid)
        ours = ours_on(sym, fd) if fd else None
        record("Markets", f"{label} close on {fd}", ours, fv, f"FRED {sid}", tol, rel=True,
               note="ours from the price-history screen on the same date")
        r = rows.get(sym)
        if sym != "^IXIC" and sym != "^N225" and not r:
            record("Markets", f"{label} row in WEI", None, None, "completeness", note="row missing")
    r = rows.get("EURUSD=X")
    e = ecb_rates()
    record("Markets", f"EUR/USD vs ECB reference ({e['date']})", r and r.get("price"), e.get("USD"), "ECB euro reference rate", 0.004, rel=True,
           note="ECB fixes at 14:15 CET; a small gap is timing")
    fd, fv = fred_last("DEXJPUS")
    record("Markets", f"USD/JPY on {fd}", ours_on("JPY=X", fd), fv, "FRED DEXJPUS (noon NY buying rate)", 0.006, rel=True)


@check("Markets", "Quote vs the local daily-bars store")
def _quotes():
    from api.providers import massive
    day = massive.stored_days()[-1]
    df = massive.read_day(day).set_index("ticker")
    for sym in ("AAPL", "MSFT", "JPM", "XOM", "NVDA"):
        q = api(f"/api/v1/mkt/quote/{sym}")
        ref = float(df.loc[sym, "c"]) if sym in df.index else None
        record("Markets", f"{sym} last price vs Massive close {day}", q.get("price"), ref, "Massive (Polygon) grouped daily bars", 0.002, rel=True,
               note="differs legitimately if a session has traded since the stored close")
        for k in ("market_cap", "trailing_pe", "eps_ttm", "dividend_yield"):
            if q.get(k) is None:
                record("Markets", f"{sym} quote field '{k}'", None, None, "completeness", note="missing on DES quote")


@check("Markets", "Crypto vs CoinGecko")
def _crypto():
    c = api("/api/v1/mkt/crypto")
    ref = json.loads(http("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd"))
    rows = {r["symbol"]: r for r in c["rows"]}
    record("Markets", "Bitcoin price", rows["BTC-USD"]["price"], ref["bitcoin"]["usd"], "CoinGecko", 0.01, rel=True)
    record("Markets", "Ether price", rows["ETH-USD"]["price"], ref["ethereum"]["usd"], "CoinGecko", 0.01, rel=True)
    g = json.loads(http("https://api.coingecko.com/api/v3/global"))["data"]["market_cap_percentage"]["btc"] / 100
    dom = c.get("btc_dominance") or c.get("dominance")
    record("Markets", "Bitcoin dominance", dom, g, "CoinGecko global", 0.02,
           note="our dominance is of the top-100 coins' market cap; CoinGecko's is of all coins")


@check("Markets", "FX cross rates vs ECB")
def _wcrs():
    w = api("/api/v1/mkt/wcrs")
    e = ecb_rates()
    m = w["matrix"]["USD"]
    for ccy in ("EUR", "JPY", "GBP", "CHF", "CAD", "AUD", "CNY", "INR"):
        if ccy == "EUR":
            ref = 1 / e["USD"]
        elif ccy in e:
            ref = e[ccy] / e["USD"]
        else:
            continue
        record("Markets", f"USD→{ccy} (ECB {e['date']})", m.get(ccy), ref, "ECB reference rates (cross via EUR)", 0.006, rel=True)


@check("Markets", "Index movers: members explain the index")
def _imov():
    for code in ("SPX", "INDU"):
        d = api(f"/api/v1/mkt/imov/{code}")
        record("Markets", f"IMOV {code}: implied vs actual move (bp)", d["implied_bps"], d["change_bps"], "internal consistency", 10.0)


@check("Markets", "Member returns: index return vs SPY and FRED")
def _mrr():
    d = api("/api/v1/mkt/mrr/SPX?period=1D")
    from api.providers import massive
    p = massive.panel(["SPY"], days=5)["SPY"].dropna()
    record("Markets", f"S&P 500 1-day return vs SPY ({d['as_of']})", d["index_return"], float(p.iloc[-1] / p.iloc[-2] - 1),
           "Massive SPY closes (ETF tracks the index)", 0.0015)
    fd, fv = fred_last("SP500")
    s_ = fred("SP500", 20)
    ks = sorted(s_)
    hp = {r["date"]: r["close"] for r in api("/api/v1/mkt/hp/%5EGSPC")["rows"]}
    if len(ks) > 1 and ks[-2] in hp and ks[-1] in hp:
        record("Markets", f"S&P 500 1-day return on {ks[-1]}", hp[ks[-1]] / hp[ks[-2]] - 1, s_[ks[-1]] / s_[ks[-2]] - 1, "FRED SP500", 0.0005)


# ── rates ────────────────────────────────────────────────────────────────────
@check("Rates", "Treasury curve vs FRED")
def _gc():
    from api.marketdata.curves import _us
    hist = _us()
    for t, sid in ((0.25, "DGS3MO"), (2.0, "DGS2"), (10.0, "DGS10"), (30.0, "DGS30")):
        fd, fv = fred_last(sid)
        ours = (hist.get(fd) or {}).get(t)
        record("Rates", f"US {t:g}Y par yield on {fd}", ours, fv, f"FRED {sid}", 0.011, note="same date")
    g = api("/api/v1/mkt/gc")
    us = g["curves"]["US"]
    record("Rates", "GC shows the latest Treasury curve date", us["date"], max(hist), "Treasury feed", status="PASS" if us["date"] == max(hist) else "FAIL")


@check("Rates", "World bonds and breakevens vs FRED")
def _wb():
    w = api("/api/v1/mkt/wb")
    us = next(r for r in w["rows"] if r["iso"] == "US")
    fd, fv = fred_last("DGS10")
    record("Rates", f"WB US 10Y ({us['date']})", us["yield_10y"], fv, f"FRED DGS10 {fd}", 0.08,
           note="ours is ^TNX intraday/latest; FRED is the prior close")
    fd, fv = fred_last("DFII10")
    record("Rates", "WB US 10Y TIPS", (w.get("us_tips_10y") or {}).get("yield"), fv, f"FRED DFII10 {fd}", 0.011)
    il = api("/api/v1/mkt/ilbe")
    ser = {s["id"]: s for s in il["series"]}
    for sid in ("T5YIE", "T10YIE"):
        fd, fv = fred_last(sid, ser[sid]["date"])
        record("Rates", f"ILBE {sid} ({ser[sid]['date']})", ser[sid]["last"], fv, f"FRED {sid}", 0.011)


@check("Rates", "Money markets vs FRED / NY Fed")
def _btmm():
    b = api("/api/v1/mkt/btmm")
    rows = {r["series"]: r for g in b["groups"] for r in g["rows"]}
    sofr = json.loads(http("https://markets.newyorkfed.org/api/rates/secured/sofr/last/1.json"))["refRates"][0]
    eff = json.loads(http("https://markets.newyorkfed.org/api/rates/unsecured/effr/last/1.json"))["refRates"][0]
    if "DFF" in rows:
        record("Rates", f"Fed funds effective ({rows['DFF']['date']})", rows["DFF"]["value"], eff["percentRate"], f"NY Fed EFFR {eff['effectiveDate']}", 0.011)
    if "SOFR" in rows:
        record("Rates", f"SOFR ({rows['SOFR']['date']})", rows["SOFR"]["value"], sofr["percentRate"], f"NY Fed SOFR {sofr['effectiveDate']}", 0.021,
               note="" if rows["SOFR"]["date"] == sofr["effectiveDate"] else "different days")
    else:
        record("Rates", "SOFR in BTMM", None, sofr["percentRate"], "NY Fed", note="row missing")


@check("Rates", "Policy rates vs official")
def _cbrt():
    c = api("/api/v1/mkt/cbrt")
    banks = {b["code"]: b for b in c["banks"]}
    fu = fred_last("DFEDTARU")[1]
    fl = fred_last("DFEDTARL")[1]
    record("Rates", "Fed policy rate (BIS = range midpoint)", banks["US"]["rate"], (fu + fl) / 2 if fu else None, "FRED DFEDTARU/L", 0.001)
    try:
        ecb = http("https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.DFR.LEV?lastNObservations=1&format=csvdata")
        dfr = float(list(csv.DictReader(io.StringIO(ecb)))[-1]["OBS_VALUE"])
        record("Rates", "ECB deposit rate (euro area)", banks["XM"]["rate"], dfr, "ECB data portal (DFR)", 0.001)
    except Exception as e:                                      # noqa: BLE001
        record("Rates", "ECB deposit rate", banks.get("XM", {}).get("rate"), None, "ECB data portal", note=f"reference unavailable: {e}")
    w = api("/api/v1/mkt/wirp")
    record("Rates", "WIRP target range", w["target_upper"], fu, "FRED DFEDTARU", 0.001)
    f = api("/api/v1/mkt/fomc")
    record("Rates", "FOMC portal target range upper", f["target_upper"], fu, "FRED DFEDTARU", 0.001)


@check("Rates", "Credit spreads vs FRED")
def _cred():
    c = api("/api/v1/mkt/cred")
    rows = c.get("rows") or c.get("series") or []
    if not rows:
        record("Rates", "CRED rows", None, None, "completeness", note=f"no rows; keys {list(c)[:8]}")
        return
    by = {(r.get("id") or r.get("series")): r for r in rows}
    for sid in ("BAMLC0A0CM", "BAMLH0A0HYM2"):
        r = by.get(sid)
        if not r:
            record("Rates", f"CRED {sid}", None, None, "completeness", note="series missing")
            continue
        ours = r.get("value", r.get("last", r.get("level")))
        fd, fv = fred_last(sid, r.get("date"))
        record("Rates", f"CRED {sid} ({r.get('date')})", ours, fv, f"FRED {sid}", 0.011)


@check("Rates", "Swap curve sanity (no free independent reference)")
def _swap():
    s = api("/api/v1/mkt/swap?days=3")
    for x in s["us_swap_spreads"]:
        if x["tenor"] in (2, 5, 10, 30):
            record("Rates", f"USD SOFR swap spread {x['tenor']}Y (bp)", x["spread_bp"], None, "range check: −90…+20bp",
                   status="PASS" if -90 <= x["spread_bp"] <= 20 else "FAIL")
    usd = next(c for c in s["curves"] if c["code"] == "USD")
    p1 = next((p for p in usd["points"] if p["tenor"] == 1), None)
    sofr = json.loads(http("https://markets.newyorkfed.org/api/rates/secured/sofr/last/1.json"))["refRates"][0]["percentRate"]
    if p1:
        record("Rates", "1Y SOFR swap vs overnight SOFR (pp)", p1["rate"], sofr, "NY Fed SOFR — should be within ~0.75pp", 0.75)


# ── macro ────────────────────────────────────────────────────────────────────
@check("Macro", "Dashboard snapshot vs FRED")
def _dash():
    snap = json.loads((ROOT / "data/processed/live/dashboard_live.json").read_text())
    km = snap["data"]["keyMetrics"]
    age_h = (time.time() - snap.get("ts", 0)) / 3600
    record("Macro", "Dashboard snapshot age (hours)", round(age_h, 1), None, "freshness ≤ 24h",
           status="PASS" if age_h <= 24 else "WARN")
    fd, fv = fred_last("DGS10")
    record("Macro", "Dashboard 10Y yield", km.get("tenYearYield"), fv, f"FRED DGS10 {fd}", 0.08)
    hp = api("/api/v1/mkt/hp/%5EGSPC")["rows"][0]
    record("Macro", f"Dashboard S&P 500 level vs latest close ({hp['date']})", km.get("spxLevel"), hp["close"], "price history (same session)", 0.002, rel=True)
    rec = snap["data"].get("recession") or {}
    record("Macro", "Recession probability shown (%)", km.get("recession", {}).get("value"), None, "range 0–100",
           status="PASS" if 0 <= (km.get("recession", {}).get("value") or -1) <= 100 else "FAIL")
    dash_regime = (km.get("regimeDuration") or {}).get("currentRegime") or (snap["data"].get("regime") or {}).get("current")
    record("Macro", "Dashboard regime (Macro desk)", dash_regime, None, "see model check", status="INFO")


@check("Macro", "Economic calendar actuals vs FRED")
def _eco():
    e = api("/api/v1/mkt/eco/global")
    ev = e.get("events") or []
    record("Macro", "ECO events returned (default view)", len(ev), None, "completeness", status="PASS" if ev else "FAIL",
           note="" if ev else "default call returns no events")
    s = api("/api/v1/mkt/ecst")
    record("Macro", "ECST latest surprise index", s.get("latest"), None, "range −3…+3", status="PASS" if s.get("latest") is not None and abs(s["latest"]) < 3 else "FAIL")


@check("Macro", "CPI and unemployment shown vs FRED")
def _cpi():
    w = api("/api/v1/mkt/wb")
    us = next(r for r in w["rows"] if r["iso"] == "US")
    cpi = fred("CPIAUCSL", 500)
    ks = sorted(cpi)
    last = ks[-1]
    prev = next(k for k in ks if k.startswith(str(int(last[:4]) - 1) + last[4:7]))
    yoy = (cpi[last] / cpi[prev] - 1) * 100
    record("Macro", f"US CPI y/y used for real yield ({us.get('inflation_source')})", us.get("inflation"), yoy, f"FRED CPIAUCSL {last[:7]}", 0.15,
           note="BIS publishes the same BLS index; small gaps are seasonal adjustment (FRED SA vs BIS NSA)")
    e = api("/api/v1/mkt/ecfc")
    usr = next(r for r in e["rows"] if r["iso"] == "US")
    fd, fv = fred_last("UNRATE")
    record("Macro", "ECFC US unemployment (IMF year estimate) vs latest", usr["unemployment"], fv, f"FRED UNRATE {fd}", 0.6,
           note="IMF full-year forecast vs latest monthly print — should be close, not equal")


@check("Macro", "Macro model regime vs dashboard regime")
def _regime():
    snap = json.loads((ROOT / "data/processed/live/dashboard_live.json").read_text())
    d = snap["data"]
    dash = ((d.get("keyMetrics") or {}).get("regimeDuration") or {}).get("currentRegime") or (d.get("regime") or {}).get("current")
    model = None
    for p in ("/api/v1/model/backtest", "/api/v1/model/macro", "/api/v1/model"):
        try:
            m = api(p, timeout=120)
            tl = m.get("timeline") or (m.get("backtest") or {}).get("timeline")
            if tl:
                model = tl[-1]["top"]
                break
        except Exception:                                       # noqa: BLE001
            continue
    norm = lambda s: (s or "").lower().replace("deflationary slowdown", "deflation").replace("slowdown", "deflation").strip()
    record("Macro", "Regime: dashboard vs macro model", dash, model, "the two models should agree or explain why",
           status="INFO" if model is None else ("PASS" if norm(dash) == norm(model) else "WARN"))


# ── equities ─────────────────────────────────────────────────────────────────
@check("Equities", "Fundamentals: SEC-based vs Yahoo")
def _fund():
    import yfinance as yf
    for sym in ("AAPL", "MSFT", "JPM"):
        info = yf.Ticker(sym).info
        ge = api(f"/api/v1/mkt/ge/{sym}")
        record("Equities", f"{sym} trailing EPS (GE)", ge.get("eps_ttm"), info.get("trailingEps"), "Yahoo trailingEps", 0.03, rel=True)
        record("Equities", f"{sym} trailing P/E (GE)", ge.get("pe"), info.get("trailingPE"), "Yahoo trailingPE", 0.04, rel=True)
        em = api(f"/api/v1/mkt/em/{sym}")
        record("Equities", f"{sym} TTM revenue (EM)", em.get("ttm_revenue"), info.get("totalRevenue"), "Yahoo totalRevenue", 0.03 if sym != "JPM" else 0.06, rel=True,
               note="banks: SEC 'Revenues' is total net revenue as reported; Yahoo uses its own definition" if sym == "JPM" else "")
        q = api(f"/api/v1/mkt/quote/{sym}")
        record("Equities", f"{sym} market cap (DES)", q.get("market_cap"), info.get("marketCap"), "Yahoo marketCap", 0.02, rel=True)


@check("Equities", "Option chain: IV and Greeks recomputed")
def _omon():
    from scipy.stats import norm
    o = api("/api/v1/mkt/omon/AAPL")
    S = o["underlying"] if isinstance(o["underlying"], (int, float)) else o["underlying"].get("price")
    T = max(o["days"], 1) / 365
    r, q = o.get("rate") or 0.04, o.get("dividend_yield") or 0
    bad = 0
    n = 0
    for c in o["calls"]:
        if not (c.get("iv") and c.get("delta") is not None) or abs(c["strike"] / S - 1) > 0.15:
            continue
        v = c["iv"]
        d1 = (math.log(S / c["strike"]) + (r - q + v * v / 2) * T) / (v * math.sqrt(T))
        n += 1
        bad += abs(math.exp(-q * T) * norm.cdf(d1) - c["delta"]) > 0.02
    record("Equities", f"AAPL call deltas consistent with their IV ({n} strikes)", bad, 0, "Black–Scholes recomputation", 0)
    if o.get("atm_iv"):
        record("Equities", "AAPL ATM IV in a sane range", o["atm_iv"], None, "0.05–1.5", status="PASS" if 0.05 < o["atm_iv"] < 1.5 else "FAIL")


@check("Equities", "Probability lab internal consistency")
def _prob():
    p = api("/api/v1/mkt/prob/AAPL")
    for lv in p["levels"]:
        record("Equities", f"PROB P(above)+P(below) at {lv['level']}", lv["p_above"] + lv["p_below"], 1.0, "must sum to 1", 0.002)
    pc = p["percentiles"]
    record("Equities", "PROB percentiles increase", 1 if pc["5"] < pc["25"] < pc["50"] < pc["75"] < pc["95"] else 0, 1, "monotonic", 0)



@check("Markets", "ETF premium: core US funds near NAV")
def _etfa():
    e = api("/api/v1/mkt/etfarb")
    rows = {r["symbol"]: r for r in e["rows"]}
    for sym in ("SPY", "IVV", "VOO", "QQQ", "SMH"):
        r = rows.get(sym)
        record("Markets", f"{sym} premium to NAV (bp, {r and r.get('close_basis')})", r and r["premium_bp"], 0.0,
               "arbitrage keeps core US equity ETFs within ~15bp", 15.0)


@check("Markets", "FX forwards follow covered interest parity")
def _frd():
    f = api("/api/v1/mkt/frd")
    S, rb, rq = f["spot"], f["rates"]["EUR"]["rate"], f["rates"]["USD"]["rate"]
    for t in f["tenors"]:
        ref = S * (1 + rq * t["days"] / 360) / (1 + rb * t["days"] / 360)
        record("Markets", f"EUR/USD {t['tenor']} forward", t["forward"], ref, "S x (1 + r_USD d/360) / (1 + r_EUR d/360)", 0.0005, rel=True,
               note="day-count convention can differ by a pip")


@check("Equities", "Dividend yield = trailing dividends / price")
def _dvd():
    for sym in ("AAPL", "JPM", "XOM"):
        d = api(f"/api/v1/mkt/dvd/{sym}")
        q = api(f"/api/v1/mkt/quote/{sym}")
        ref = d["ttm_dividends"] / q["price"] if d.get("ttm_dividends") and q.get("price") else None
        record("Equities", f"{sym} dividend yield", d.get("dividend_yield"), ref, "trailing 12-month payments / last price", 0.0008)


@check("Equities", "DCF outputs in a sane range")
def _dcf():
    for sym in ("AAPL", "MSFT", "KO"):
        d = api(f"/api/v1/mkt/dcf/{sym}")
        v = d.get("valuation") or d
        w = v.get("wacc")
        wacc = w.get("wacc") if isinstance(w, dict) else w
        ps = v.get("per_share")
        record("Equities", f"{sym} DCF WACC", wacc, None, "4%-14%", status="PASS" if wacc and 0.04 <= wacc <= 0.14 else "FAIL",
               note="" if wacc else f"keys {list(v)[:10]}")
        record("Equities", f"{sym} DCF value per share", ps, None, "positive", status="PASS" if ps and ps > 0 else "FAIL")
        ts, ex = v.get("terminal_share"), v.get("implied_ev_ebit_exit")
        record("Equities", f"{sym} DCF terminal value share / exit EV/EBIT", ts, ex, "typical 50-85% and 10-25x", status="INFO"
               if ts is None else ("PASS" if 0.4 <= ts <= 0.9 else "WARN"), note=f"value {ps and round(ps, 2)} vs price {v.get('price')}")


@check("Macro", "Recession probability vs the NY Fed's own model")
def _nyfed():
    import pandas as pd
    snap = json.loads((ROOT / "data/processed/live/dashboard_live.json").read_text())
    ours = (snap["data"]["keyMetrics"].get("recession") or {}).get("value")
    try:
        raw = urllib.request.urlopen(urllib.request.Request(
            "https://www.newyorkfed.org/medialibrary/media/research/capital_markets/allmonth.xls", headers=UA), timeout=40).read()
        df = pd.read_excel(io.BytesIO(raw))
        col = [c for c in df.columns if "rec" in str(c).lower() and "prob" in str(c).lower()]
        v = float(df[col[0]].dropna().iloc[-1])
        ref = v * 100 if v <= 1 else v
        record("Macro", "Recession probability, 12 months ahead (%)", ours, ref, f"NY Fed yield-curve model ({col[0]})", 10.0,
               note="the dashboard model adds the policy rate to the term spread; a few points apart is method")
    except Exception as e:                                      # noqa: BLE001
        record("Macro", "Recession probability (%)", ours, None, "NY Fed model", note=f"reference unavailable: {str(e)[:80]}")


@check("Macro", "Economic calendar: US CPI actual vs FRED")
def _eco_cpi():
    e = api("/api/v1/mkt/eco/global")
    ev = [x for x in e["events"] if (x.get("country") in ("US", "United States")) and "cpi" in str(x.get("event", "")).lower()
          and x.get("actual") is not None]
    if not ev:
        record("Macro", "US CPI release in calendar", None, None, "completeness", status="INFO", note="no US CPI with an actual in the window")
        return
    for x in ev[-3:]:
        record("Macro", f"{x.get('event')} ({str(x.get('date', ''))[:10]}) actual", x.get("actual"), None,
               "listed for manual check against BLS", status="INFO", note=json.dumps({k: x.get(k) for k in ('previous', 'consensus', 'unit')})[:120])


@check("Equities", "Breadth vs recomputation from the store")
def _breadth():
    b = api("/api/v1/mkt/ins/breadth")
    from api.providers import massive
    from api.marketdata import funds
    syms = [str(m["symbol"]).replace(".", "-") for m in funds.index_members("SPX")["members"]]
    p = massive.panel(syms, days=260)
    above = (p.iloc[-1] > p.iloc[-200:].mean()).sum() / p.iloc[-1].notna().sum()
    flat = {}
    def walk(o, pre=""):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, f"{pre}.{k}" if pre else k)
        elif isinstance(o, (int, float)):
            flat[pre] = o
    walk({k: v for k, v in b.items() if not isinstance(v, list)})
    key = next((k for k in flat if "200" in k and ("above" in k or "pct" in k)), None)
    ours = flat.get(key) if key else None
    if ours is not None and ours > 1:
        ours = ours / 100
    record("Equities", f"S&P 500 members above 200-day average ({key})", ours, float(above), "recomputed from Massive closes", 0.03)



@check("Macro", "Dashboard panels vs FRED (same dates)")
def _dash_panels():
    d = json.loads((ROOT / "data/processed/live/dashboard_live.json").read_text())["data"]
    ri, liq, now, rec = d.get("riskIndicators") or {}, d.get("liquidity") or {}, d.get("nowcast") or {}, d.get("recession") or {}
    t10, t2, t3m = fred("DGS10", 30), fred("DGS2", 30), fred("DGS3MO", 30)
    day = max(set(t10) & set(t2) & set(t3m))
    record("Macro", f"10Y-2Y spread ({day})", ri.get("yieldSpread"), round(t10[day] - t2[day], 2), "FRED DGS10 - DGS2", 0.03)
    comp = {c["name"]: c["value"] for c in rec.get("components", [])}
    record("Macro", f"10Y-3M spread used for recession odds ({day})", comp.get("10Y-3M Spread"), round(t10[day] - t3m[day], 2), "FRED DGS10 - DGS3MO", 0.03)
    fd, fv = fred_last("BAMLH0A0HYM2")
    record("Macro", f"High-yield OAS ({fd})", ri.get("creditSpread"), fv, "FRED BAMLH0A0HYM2", 0.02)
    nf = next((x["value"] for x in liq.get("indicators", []) if "NFCI" in x["name"]), None)
    fd, fv = fred_last("NFCI", None)
    record("Macro", f"Chicago Fed NFCI ({fd})", nf, fv, "FRED NFCI", 0.02)
    g = next((m for m in now.get("models", []) if "GDPNow" in m["model"]), None)
    fd, fv = fred_last("GDPNOW")
    record("Macro", f"GDPNow ({g and g.get('quarter')})", g and g["value"], fv, f"FRED GDPNOW (quarter starting {fd})", 0.01)
    hp = {r["date"]: r["close"] for r in api("/api/v1/mkt/hp/%5EVIX")["rows"]}
    last = max(hp)
    record("Macro", f"VIX on the dashboard vs latest close ({last})", ri.get("vix"), hp[last], "price history (same session)", 0.01, rel=True)


# ── run ──────────────────────────────────────────────────────────────────────
def main() -> int:
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--out", default=str(ROOT / "data/processed/audit"))
    a = ap.parse_args()
    BASE = a.base
    t0 = time.time()
    for c in CHECKS:
        c()
    counts = {s: sum(1 for r in RESULTS if r["status"] == s) for s in ("PASS", "WARN", "FAIL", "ERROR", "INFO")}
    print(f"\n{counts}  in {time.time() - t0:.0f}s")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"accuracy_{datetime.now():%Y%m%d_%H%M}.json"
    path.write_text(json.dumps({"run": datetime.now().isoformat(), "counts": counts, "results": RESULTS}, indent=1, default=str))
    print("report:", path)
    return 0 if counts["FAIL"] == counts["ERROR"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
