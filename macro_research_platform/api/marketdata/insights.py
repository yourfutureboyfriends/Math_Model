"""
Market internals and risk (free data):

  vol()             volatility complex: VIX term structure (9-day to 1-year), VVIX, SKEW, MOVE,
                    oil / gold / Nasdaq vol, realised vs implied S&P 500 volatility
  breadth()         S&P 500 breadth: share of members above their 50- and 200-day averages,
                    advance/decline line, new 52-week highs and lows, McClellan oscillator, by sector
  implied_moves()   upcoming earnings: the move the options market prices (at-the-money straddle
                    through the report) vs the stock's average post-earnings move
  uoa()             unusual options activity across the most traded US names: contracts trading
                    far above open interest, the biggest premiums, call/put skew
  risk()            regime gauge: recession probability from the yield curve (NY Fed model),
                    credit spreads, volatility, financial conditions, curve, dollar, copper/gold,
                    breadth — each as a z-score, combined into a risk-on / risk-off reading
"""
from __future__ import annotations
from api.market_dates import weekly_last

import csv
import io
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from api.marketdata.core import Upstream, _cached

logger = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (macro research terminal)"}


def _num(x) -> Optional[float]:
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _pctile(series: List[float], v: float) -> Optional[float]:
    xs = [x for x in series if x is not None]
    return round(sum(1 for x in xs if x <= v) / len(xs), 3) if xs else None


# ── Volatility ──────────────────────────────────────────────────────────────
VOL_IDX = {"^VIX9D": "VIX 9-day", "^VIX": "VIX (30-day)", "^VIX3M": "VIX 3-month", "^VIX6M": "VIX 6-month", "^VIX1Y": "VIX 1-year",
           "^VVIX": "VVIX (vol of VIX)", "^SKEW": "SKEW (tail risk)", "^MOVE": "MOVE (Treasury vol)", "^OVX": "Oil vol (OVX)",
           "^GVZ": "Gold vol (GVZ)", "^VXN": "Nasdaq vol (VXN)", "^VXEEM": "EM vol (VXEEM)"}
TERM = [("9D", 9, "^VIX9D"), ("1M", 30, "^VIX"), ("3M", 93, "^VIX3M"), ("6M", 183, "^VIX6M"), ("1Y", 365, "^VIX1Y")]


def vol() -> Dict[str, Any]:
    """Volatility dashboard: VIX family term structure, realised vs implied, and percentiles over 3 years."""
    def build():
        import yfinance as yf
        df = yf.download(list(VOL_IDX) + ["^GSPC"], period="3y", interval="1d", auto_adjust=False, progress=False, threads=True)["Close"]
        spx = df["^GSPC"].dropna()
        rets = spx.pct_change().dropna()
        rv = {n: float(rets.iloc[-n:].std() * math.sqrt(252) * 100) for n in (10, 21, 63)}
        rv21_series = (rets.rolling(21).std() * math.sqrt(252) * 100).dropna()
        idx = []
        for sym, name in VOL_IDX.items():
            s = df[sym].dropna() if sym in df else None
            if s is None or s.empty:
                continue
            last = float(s.iloc[-1])
            hist = [float(x) for x in s.iloc[-756:]]
            idx.append({"symbol": sym, "name": name, "last": round(last, 2), "chg_1d": round(last - float(s.iloc[-2]), 2) if len(s) > 1 else None,
                        "chg_1w": round(last - float(s.iloc[-6]), 2) if len(s) > 5 else None, "pct_3y": _pctile(hist, last) if len(hist) > 50 else None,
                        "spark": [round(float(x), 2) for x in s.iloc[-63:]]})

        def term_at(back: int):
            pts = []
            for label, days, sym in TERM:
                s = df[sym].dropna() if sym in df else None
                if s is not None and len(s) > back:
                    pts.append({"tenor": label, "days": days, "value": round(float(s.iloc[-1 - back]), 2)})
            return pts
        vix, vix3m = df["^VIX"].dropna(), df["^VIX3M"].dropna()
        joined = vix.to_frame("vix").join(vix3m.to_frame("vix3m"), how="inner").join(rv21_series.to_frame("rv21"), how="left")
        rows = [{"date": str(d.date()), "vix": round(float(r.vix), 2), "vix3m": round(float(r.vix3m), 2),
                 "rv21": round(float(r.rv21), 2) if r.rv21 == r.rv21 else None, "ratio": round(float(r.vix / r.vix3m), 3)} for d, r in joined.iloc[-756:].iterrows()]
        ratio = rows[-1]["ratio"]
        vrp = round(float(vix.iloc[-1]) - rv[21], 2)
        return {"indices": idx, "term": {"now": term_at(0), "week_ago": term_at(5), "month_ago": term_at(21)}, "history": rows,
                "realised": {k: round(v, 2) for k, v in rv.items()}, "vix": round(float(vix.iloc[-1]), 2), "ratio_vix_vix3m": ratio,
                "ratio_pct_3y": _pctile([r["ratio"] for r in rows], ratio), "variance_premium": vrp,
                "regime": "backwardation (stress)" if ratio > 1 else "steep contango (complacent)" if ratio < 0.85 else "contango (normal)",
                "source": "Cboe indices via Yahoo Finance; realised vol from S&P 500 daily returns",
                "note": "Term structure in contango (short-dated vol below long-dated) is the calm norm; backwardation (VIX above VIX3M) "
                        "marks stress. Variance premium = VIX − 21-day realised vol: options are usually priced above what the index delivers."}
    return _cached("ins:vol", 900, build)


# ── Breadth ─────────────────────────────────────────────────────────────────
def breadth() -> Dict[str, Any]:
    """Market breadth: share of stocks above moving averages, new highs / lows, advance-decline."""
    def build():
        import pandas as pd
        import yfinance as yf
        from api.stock_ideas import load_universe
        uni = load_universe()
        syms = list(uni)
        # The Massive store (every US stock's daily bar, split-adjusted) once it covers ~two years up to the latest session:
        # one local read instead of 500 Yahoo downloads. Price return only, which is what breadth measures.
        from api.providers import massive
        days = massive.stored_days()
        source = "S&P 500 members (Wikipedia list) with Yahoo Finance daily closes"
        raw = None
        if len(days) >= 300 and (date.today() - days[-1]).days <= 4:
            raw = massive.panel(syms, days=520)
            if raw.shape[1] >= 450:
                source = "S&P 500 members (Wikipedia list) with Massive (Polygon) daily closes, split-adjusted"
            else:
                raw = None
        if raw is None:
            raw = yf.download(syms, period="2y", interval="1d", auto_adjust=True, progress=False, threads=6)["Close"]   # gentle on Yahoo
        px = raw.dropna(axis=1, thresh=300).ffill(limit=3)
        if px.shape[1] < 300:
            raise Upstream("Not enough S&P 500 price history for breadth.")
        ma50, ma200 = px.rolling(50).mean(), px.rolling(200).mean()
        hi252, lo252 = px.rolling(252).max(), px.rolling(252).min()
        chg = px.diff()
        above50 = ((px > ma50) & ma50.notna()).sum(axis=1) / ma50.notna().sum(axis=1)
        above200 = ((px > ma200) & ma200.notna()).sum(axis=1) / ma200.notna().sum(axis=1)
        adv, dec = (chg > 0).sum(axis=1), (chg < 0).sum(axis=1)
        net = adv - dec
        ad_line = net.cumsum()
        new_hi = ((px >= hi252) & hi252.notna()).sum(axis=1)
        new_lo = ((px <= lo252) & lo252.notna()).sum(axis=1)
        mcc = net.ewm(span=19, adjust=False).mean() - net.ewm(span=39, adjust=False).mean()
        out = pd.DataFrame({"above50": above50 * 100, "above200": above200 * 100, "adv": adv, "dec": dec, "ad_line": ad_line,
                            "new_highs": new_hi, "new_lows": new_lo, "mcclellan": mcc}).iloc[252:]
        rows = [{"date": str(d.date()), **{k: (round(float(v), 2) if v == v else None) for k, v in r.items()}} for d, r in out.iterrows()]
        last = px.iloc[-1]
        sectors: Dict[str, Dict[str, Any]] = {}
        for sym in px.columns:
            sec = uni.get(sym, "Other")
            s = sectors.setdefault(sec, {"sector": sec, "n": 0, "a50": 0, "a200": 0, "hi": 0, "lo": 0, "ret_1m": []})
            if pd.isna(last[sym]):
                continue
            s["n"] += 1
            s["a50"] += int(last[sym] > ma50[sym].iloc[-1]) if not pd.isna(ma50[sym].iloc[-1]) else 0
            s["a200"] += int(last[sym] > ma200[sym].iloc[-1]) if not pd.isna(ma200[sym].iloc[-1]) else 0
            s["hi"] += int(last[sym] >= hi252[sym].iloc[-1]) if not pd.isna(hi252[sym].iloc[-1]) else 0
            s["lo"] += int(last[sym] <= lo252[sym].iloc[-1]) if not pd.isna(lo252[sym].iloc[-1]) else 0
            if len(px[sym].dropna()) > 22:
                s["ret_1m"].append(float(last[sym] / px[sym].iloc[-22] - 1))
        sec_rows = [{"sector": s["sector"], "members": s["n"], "above50": round(s["a50"] / s["n"] * 100, 1) if s["n"] else None,
                     "above200": round(s["a200"] / s["n"] * 100, 1) if s["n"] else None, "new_highs": s["hi"], "new_lows": s["lo"],
                     "median_1m": round(sorted(s["ret_1m"])[len(s["ret_1m"]) // 2], 4) if s["ret_1m"] else None} for s in sectors.values() if s["n"]]
        sec_rows.sort(key=lambda r: -(r["above50"] or 0))
        cur = rows[-1]
        return {"rows": rows, "latest": cur, "members": int(px.shape[1]), "sectors": sec_rows,
                "pct_3y": {"above50": _pctile([r["above50"] for r in rows], cur["above50"]), "above200": _pctile([r["above200"] for r in rows], cur["above200"])},
                "source": source,
                "note": "Breadth shows how many stocks take part in a move. An index rising while fewer members sit above their 200-day "
                        "average is a narrow, fragile advance; McClellan below −50 is oversold, above +50 overbought."}
    return _cached("ins:breadth", 6 * 3600, build)


# ── Earnings implied moves ──────────────────────────────────────────────────
def _hist_earnings_moves(t, timing_hint: Optional[str]) -> Dict[str, Any]:
    import pandas as pd
    try:
        ed = t.get_earnings_dates(limit=16)
    except Exception:
        return {}
    if ed is None or ed.empty:
        return {}
    past = [d for d in ed.index if d.tz_convert("America/New_York").date() < date.today()][:8]
    if not past:
        return {}
    h = t.history(period="3y", interval="1d", auto_adjust=True)
    if h.empty:
        return {}
    closes = h["Close"]
    closes.index = closes.index.tz_localize(None).normalize() if closes.index.tz is not None else closes.index.normalize()
    moves = []
    for d in past:
        local = d.tz_convert("America/New_York")
        day = pd.Timestamp(local.date())
        after_close = local.hour >= 12                           # reported after the close: reaction next day
        idx = closes.index.searchsorted(day)
        try:
            if after_close:
                before, after = closes.iloc[idx], closes.iloc[idx + 1]
                if closes.index[idx] != day:
                    before, after = closes.iloc[idx - 1], closes.iloc[idx]
            else:
                before, after = closes.iloc[idx - 1], closes.iloc[idx]
            moves.append(float(after / before - 1))
        except (IndexError, KeyError):
            continue
    if not moves:
        return {}
    return {"avg_abs_move": sum(abs(m) for m in moves) / len(moves), "max_abs_move": max(abs(m) for m in moves), "moves": [round(m, 4) for m in moves], "n": len(moves)}


def _implied_move(sym: str, when: str, timing: Optional[str]) -> Optional[Dict[str, Any]]:
    import yfinance as yf
    t = yf.Ticker(sym)
    try:
        exps = t.options
    except Exception:
        return None
    if not exps:
        return None
    d = date.fromisoformat(when[:10])
    amc = (timing or "").lower().startswith("after")
    exp = next((e for e in exps if date.fromisoformat(e) > d or (date.fromisoformat(e) == d and not amc)), None)
    if not exp:
        return None
    try:
        ch = t.option_chain(exp)
        spot = t.fast_info.get("lastPrice") or t.fast_info.get("previousClose")
    except Exception:
        return None
    if not spot:
        return None
    calls, puts = ch.calls, ch.puts
    if calls.empty or puts.empty:
        return None
    k = min(set(calls["strike"]) & set(puts["strike"]), key=lambda s: abs(s - spot), default=None)
    if k is None:
        return None

    def mid(df):
        r = df[df["strike"] == k].iloc[0]
        b, a, l = _num(r.get("bid")), _num(r.get("ask")), _num(r.get("lastPrice"))
        return (b + a) / 2 if b and a and a > 0 else l
    c, p = mid(calls), mid(puts)
    if not c or not p:
        return None
    straddle = c + p
    days = max(1, (date.fromisoformat(exp) - date.today()).days)
    out = {"symbol": sym, "expiry": exp, "days_to_expiry": days, "spot": round(float(spot), 2), "strike": float(k),
           "straddle": round(straddle, 2), "implied_move": round(straddle / spot, 4)}
    out.update(_hist_earnings_moves(t, timing))
    if out.get("avg_abs_move"):
        out["ratio"] = round(out["implied_move"] / out["avg_abs_move"], 2)
    return out


def implied_moves(days: int = 10, min_cap_bn: float = 10) -> Dict[str, Any]:
    """Option-implied earnings moves for upcoming reporters above `min_cap_bn` vs their history."""
    def build():
        from api.marketdata.monitors import earnings_calendar
        cal = earnings_calendar(days=days, min_cap_bn=min_cap_bn, limit=200)["rows"]
        cal = [r for r in cal if r.get("symbol") and "." not in r["symbol"] and (r.get("market_cap") or 0) >= min_cap_bn * 1e9
               and r.get("datetime") and r["datetime"][:10] >= date.today().isoformat()]
        cal.sort(key=lambda r: -(r.get("market_cap") or 0))
        cal = cal[:40]
        with ThreadPoolExecutor(4) as ex:
            res = list(ex.map(lambda r: (r, _implied_move(r["symbol"], r["datetime"], r.get("timing"))), cal))
        rows = []
        for r, m in res:
            if not m:
                continue
            rows.append({**m, "company": r.get("company"), "date": r["datetime"][:10], "timing": r.get("timing"),
                         "market_cap": r.get("market_cap"), "eps_estimate": r.get("eps_estimate")})
        rows.sort(key=lambda r: r["date"])
        return {"rows": rows, "source": "Yahoo Finance option chains and earnings dates",
                "note": "Implied move = at-the-money straddle for the first expiry after the report ÷ share price: the market's priced "
                        "move through earnings. Ratio > 1: options price a bigger move than the stock's average reaction over its last "
                        "8 reports (rich); < 1: cheap. Prices 15-minute delayed."}
    return _cached(f"ins:impm:{days}:{min_cap_bn}", 3 * 3600, build)


# ── Unusual options activity ────────────────────────────────────────────────
UOA_UNIVERSE = ["SPY", "QQQ", "IWM", "DIA", "TLT", "HYG", "GLD", "SLV", "USO", "XLF", "XLE", "XLK", "SMH", "KRE", "EEM", "FXI", "EWZ",
                "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AMD", "AVGO", "NFLX", "ORCL", "CRM", "ADBE", "INTC", "MU",
                "QCOM", "PLTR", "SMCI", "COIN", "MSTR", "HOOD", "UBER", "SHOP", "BABA", "PDD", "JD", "NIO", "JPM", "BAC", "C", "WFC",
                "GS", "MS", "XOM", "CVX", "OXY", "BA", "CAT", "DIS", "WMT", "COST", "NKE", "PFE", "LLY", "UNH", "MRNA", "RIVN", "SOFI", "ARM"]


def _uoa_one(sym: str) -> Dict[str, Any]:
    import yfinance as yf
    t = yf.Ticker(sym)
    try:
        exps = list(t.options)[:3]
        spot = t.fast_info.get("lastPrice") or t.fast_info.get("previousClose")
    except Exception:
        return {"symbol": sym, "hits": []}
    hits, cv, pv, cprem, pprem = [], 0, 0, 0.0, 0.0
    for e in exps:
        try:
            ch = t.option_chain(e)
        except Exception:
            continue
        for kind, df in (("call", ch.calls), ("put", ch.puts)):
            for _, r in df.iterrows():
                v, oi, last = _num(r.get("volume")) or 0, _num(r.get("openInterest")) or 0, _num(r.get("lastPrice")) or 0
                prem = v * last * 100
                if kind == "call":
                    cv += v; cprem += prem
                else:
                    pv += v; pprem += prem
                if v >= 1000 and prem >= 250_000 and (v >= 3 * oi or oi == 0):
                    k = float(r["strike"])
                    iv = _num(r.get("impliedVolatility")) or 0
                    itm = (k / spot - 1) if spot else 0
                    # deep in-the-money contracts (stock replacement, dividend plays) and stale quotes with absurd
                    # implied vol inflate "premium" without saying anything about speculative flow
                    if spot and ((kind == "call" and itm < -0.3) or (kind == "put" and itm > 0.3)) or iv > 2.5:
                        continue
                    hits.append({"symbol": sym, "kind": kind, "expiry": e, "strike": k, "volume": int(v), "open_interest": int(oi),
                                 "vol_oi": round(v / oi, 1) if oi else None, "last": last, "premium": round(prem),
                                 "iv": round(iv, 3), "spot": spot,
                                 "moneyness": round(k / spot - 1, 3) if spot else None})
    return {"symbol": sym, "hits": hits, "call_volume": int(cv), "put_volume": int(pv), "call_premium": round(cprem), "put_premium": round(pprem),
            "put_call": round(pv / cv, 2) if cv else None, "spot": spot}


def uoa() -> Dict[str, Any]:
    """Unusual options activity: large trades vs open interest across a liquid universe, by premium."""
    def build():
        with ThreadPoolExecutor(4) as ex:
            res = list(ex.map(_uoa_one, UOA_UNIVERSE))
        hits = sorted((h for r in res for h in r["hits"]), key=lambda h: -h["premium"])[:80]
        tickers = sorted(({k: v for k, v in r.items() if k != "hits"} | {"unusual": len(r["hits"])} for r in res if r.get("call_volume") is not None),
                         key=lambda r: -(r["call_premium"] + r["put_premium"]))
        return {"hits": hits, "tickers": tickers, "as_of": datetime.now(timezone.utc).isoformat(timespec="minutes"),
                "source": "Yahoo Finance option chains (first three expiries), 15-minute delayed",
                "note": "Unusual: at least 1,000 contracts and $250k of premium, trading at 3× or more the open interest — new positions, "
                        "not closing trades; deep in-the-money contracts (>30%) are left out. Premium = volume × last price × 100. Direction (bought or sold) isn't visible in free data."}
    return _cached("ins:uoa", 900, build)


# ── Risk regime ─────────────────────────────────────────────────────────────
def _fred(sid: str, years: int = 6) -> Dict[str, float]:
    import requests
    r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": sid, "cosd": (date.today() - timedelta(days=365 * years)).isoformat()},
                     headers=UA, timeout=40)
    r.raise_for_status()
    out = {}
    for row in list(csv.reader(io.StringIO(r.text)))[1:]:
        v = _num(row[1]) if len(row) > 1 else None
        if v is not None:
            out[row[0]] = v
    return out


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def risk() -> Dict[str, Any]:
    """Cross-asset risk gauges: curve slopes, high-yield spread, financial conditions and their percentiles."""
    def build():
        import pandas as pd
        import yfinance as yf
        with ThreadPoolExecutor(5) as ex:
            f = {k: ex.submit(_fred, k) for k in ("T10Y3M", "T10Y2Y", "BAMLH0A0HYM2", "NFCI")}
            fred = {k: v.result() for k, v in f.items()}
        mk = yf.download(["^VIX", "DX-Y.NYB", "HG=F", "GC=F", "^GSPC"], period="6y", interval="1d", auto_adjust=True, progress=False)["Close"]
        weekly = lambda s: weekly_last(s).dropna()
        ser = {
            "curve_3m10y": weekly(pd.Series(fred["T10Y3M"], dtype=float).set_axis(pd.to_datetime(list(fred["T10Y3M"])))),
            "curve_2s10s": weekly(pd.Series(fred["T10Y2Y"], dtype=float).set_axis(pd.to_datetime(list(fred["T10Y2Y"])))),
            "hy_oas": weekly(pd.Series(fred["BAMLH0A0HYM2"], dtype=float).set_axis(pd.to_datetime(list(fred["BAMLH0A0HYM2"])))),
            "nfci": weekly(pd.Series(fred["NFCI"], dtype=float).set_axis(pd.to_datetime(list(fred["NFCI"])))),
            "vix": weekly(mk["^VIX"].dropna()),
            "dollar_3m": weekly(mk["DX-Y.NYB"].dropna()).pct_change(13) * 100,
            "copper_gold_3m": weekly((mk["HG=F"] / mk["GC=F"]).dropna()).pct_change(13) * 100,
            "spx_trend": weekly((mk["^GSPC"] / mk["^GSPC"].rolling(200).mean() - 1).dropna()) * 100,
        }
        # sign: + means risk-on
        meta = {"curve_3m10y": ("Yield curve 10y − 3m", 1, "pp"), "curve_2s10s": ("Yield curve 10y − 2y", 1, "pp"),
                "hy_oas": ("High-yield credit spread", -1, "pp"), "nfci": ("Financial conditions (NFCI)", -1, ""),
                "vix": ("VIX", -1, ""), "dollar_3m": ("Dollar, 3-month change", -1, "%"), "copper_gold_3m": ("Copper/gold, 3-month change", 1, "%"),
                "spx_trend": ("S&P 500 vs 200-day average", 1, "%")}
        df = pd.DataFrame(ser).ffill(limit=2).dropna(how="all")
        z = pd.DataFrame({k: (df[k] - df[k].rolling(156, min_periods=52).mean()) / df[k].rolling(156, min_periods=52).std() * meta[k][1] for k in df})
        comp = z.mean(axis=1, skipna=True).clip(-3, 3)
        hist = [{"date": str(d.date()), "score": round(float(v), 2)} for d, v in comp.dropna().iloc[-260:].items()]
        last = df.iloc[-1]
        comps = []
        for k, (name, sign, unit) in meta.items():
            s = df[k].dropna()
            if s.empty:
                continue
            zz = z[k].dropna()
            comps.append({"key": k, "name": name, "value": round(float(s.iloc[-1]), 2), "unit": unit, "z": round(float(zz.iloc[-1]), 2) if not zz.empty else None,
                          "chg_4w": round(float(s.iloc[-1] - s.iloc[-5]), 2) if len(s) > 4 else None, "risk_on_when": "higher" if sign > 0 else "lower"})
        spread = sum(list(fred["T10Y3M"].values())[-22:]) / min(22, len(fred["T10Y3M"]))     # last month's average, like the NY Fed
        rec = _norm_cdf(-0.5333 - 0.6330 * spread)
        score = float(comp.dropna().iloc[-1])
        return {"score": round(score, 2), "regime": "Risk-on" if score > 0.5 else "Risk-off" if score < -0.5 else "Neutral",
                "components": comps, "history": hist, "recession_prob_12m": round(rec, 3), "curve_3m10y_avg": round(spread, 2),
                "as_of": str(df.index[-1].date()),
                "source": "FRED (Treasury curve, ICE BofA HY OAS, Chicago Fed NFCI); Yahoo Finance (VIX, dollar index, copper, gold, S&P 500)",
                "note": "Each input is a z-score against its last 3 years, signed so positive = risk-on, and the gauge is their average. "
                        "Recession probability: the New York Fed's probit on the 10-year minus 3-month Treasury spread (12 months ahead)."}
    return _cached("ins:risk", 3 * 3600, build)
