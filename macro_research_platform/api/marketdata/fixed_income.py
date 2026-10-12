"""
Fixed income and FX on free official data:

  breakevens()        ILBE — TIPS breakevens, 5y5y forward, real yields, survey and model expectations
  treasuries()        TSY  — every marketable Treasury with its end-of-day price (TreasuryDirect FedInvest),
                             yield to maturity, duration, convexity and DV01, plus the curve built from them
  bond_calc(...)      YAS  — price ↔ yield, accrued interest, durations, convexity, DV01 for any fixed coupon bond
  fx_carry()          FXCA — carry vs the dollar from central-bank policy rates, carry-to-risk, implied forwards
"""
from __future__ import annotations

import logging
import math
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from api.marketdata.core import NotFound, Upstream, _cached

logger = logging.getLogger(__name__)


# ── ILBE ─────────────────────────────────────────────────────────────────────
ILBE_SERIES = [("T5YIE", "5-year breakeven", "market"), ("T10YIE", "10-year breakeven", "market"), ("T5YIFR", "5y5y forward inflation", "market"),
               ("DFII5", "5-year real yield (TIPS)", "real"), ("DFII10", "10-year real yield (TIPS)", "real"), ("DFII30", "30-year real yield (TIPS)", "real"),
               ("DGS10", "10-year nominal yield", "nominal"), ("EXPINF1YR", "1-year expected inflation (Cleveland Fed model)", "model"),
               ("EXPINF10YR", "10-year expected inflation (Cleveland Fed model)", "model"), ("MICH", "1-year expected inflation (UMich survey)", "survey"),
               ("CPIAUCSL", "CPI (index)", "actual")]


def breakevens() -> Dict[str, Any]:
    from api.marketdata.insights import _fred
    import concurrent.futures as cf

    def build():
        def one(row):
            try:
                return row[0], _fred(row[0], years=12)
            except Exception as e:
                logger.info("[ilbe] %s: %s", row[0], e)
                return row[0], {}
        with cf.ThreadPoolExecutor(4) as ex:
            raw = dict(ex.map(one, ILBE_SERIES))
        frames = {}
        for sid, _, _ in ILBE_SERIES:
            d = raw.get(sid) or {}
            if d:
                s = pd.Series(d, dtype=float)
                s.index = pd.to_datetime(s.index)
                frames[sid] = s.sort_index().dropna()
        if "T10YIE" not in frames:
            raise Upstream("FRED didn't return the breakeven series — try again shortly.")
        if "CPIAUCSL" in frames:
            cpi = frames.pop("CPIAUCSL")
            yoy = (cpi / cpi.shift(12) - 1) * 100
            frames["CPI_YOY"] = yoy.dropna()
        rows = []
        names = {sid: n for sid, n, _ in ILBE_SERIES} | {"CPI_YOY": "CPI inflation, actual (y/y %)"}
        kinds = {sid: k for sid, _, k in ILBE_SERIES} | {"CPI_YOY": "actual"}
        for sid, s in frames.items():
            last = float(s.iloc[-1])

            def chg(days):
                p = s[s.index <= s.index[-1] - pd.Timedelta(days=days)]
                return (last - float(p.iloc[-1])) * 100 if len(p) else None
            w = s[s.index >= s.index[-1] - pd.Timedelta(days=365 * 10)]
            rows.append({"id": sid, "name": names.get(sid, sid), "kind": kinds.get(sid), "last": last, "date": s.index[-1].strftime("%Y-%m-%d"),
                         "chg_1m_bp": chg(30), "chg_1y_bp": chg(365), "percentile_10y": float((w < last).mean()), "min_10y": float(w.min()), "max_10y": float(w.max())})
        df = pd.DataFrame(frames).ffill(limit=40)
        wk = df.resample("W-FRI").last()
        wk = wk[wk.index >= wk.index[-1] - pd.Timedelta(days=365 * 10)]
        hist = [{"date": d.strftime("%Y-%m-%d"), **{k: (round(float(v), 3) if pd.notna(v) else None) for k, v in r.items()}} for d, r in wk.iterrows()]
        get = {r["id"]: r["last"] for r in rows}
        signals = []
        if "T5YIFR" in get:
            signals.append(f"The market prices {get['T5YIFR']:.2f}% inflation for the five years starting in five years — "
                           + ("above" if get["T5YIFR"] > 2.5 else "close to" if get["T5YIFR"] >= 2.0 else "below") + " the Fed's 2% PCE goal (≈2.3–2.5% on CPI).")
        if "T5YIE" in get and "CPI_YOY" in get:
            signals.append(f"Five-year breakeven {get['T5YIE']:.2f}% vs actual CPI inflation {get['CPI_YOY']:.2f}%: the market expects inflation to "
                           + ("rise" if get["T5YIE"] > get["CPI_YOY"] + 0.2 else "fall" if get["T5YIE"] < get["CPI_YOY"] - 0.2 else "stay roughly here") + ".")
        if "DFII10" in get:
            signals.append(f"10-year real yield {get['DFII10']:.2f}% — " + ("restrictive territory (above ~1.5%)" if get["DFII10"] > 1.5 else "accommodative (below ~0.5%)" if get["DFII10"] < 0.5 else "neutral range") + ".")
        return {"series": rows, "history": hist, "signals": signals,
                "note": "Breakeven = nominal Treasury yield − TIPS real yield: the inflation rate at which the two pay the same (it also carries a small "
                        "liquidity and risk premium). 5y5y = average expected inflation from five to ten years out — the Fed's favourite gauge of anchoring.",
                "source": "FRED: Treasury/TIPS (H.15), Cleveland Fed inflation expectations, University of Michigan survey, BLS CPI"}
    return _cached("ilbe", 3 * 3600, build)


# ── Bond maths ───────────────────────────────────────────────────────────────
def _add_months(d: date, m: int) -> date:
    y, mo = divmod(d.month - 1 + m, 12)
    y += d.year
    mo += 1
    import calendar
    return date(y, mo, min(d.day, calendar.monthrange(y, mo)[1]))


def _schedule(settle: date, maturity: date, freq: int) -> Tuple[date, List[date]]:
    """Previous coupon date and the remaining coupon dates (stepping back from maturity)."""
    step = 12 // freq
    dates = [maturity]
    while dates[-1] > settle:
        dates.append(_add_months(maturity, -step * len(dates)))
    prev = dates[-1]
    nxt = sorted(d for d in dates if d > settle)
    return prev, nxt


def bond_measures(coupon: float, maturity: date, settle: date, freq: int = 2, price: Optional[float] = None,
                  ytm: Optional[float] = None, face: float = 100.0) -> Dict[str, Any]:
    """Street-convention fixed-coupon bond: actual/actual accrual, yield compounded `freq` times a year.
    Give either a clean price (per 100) or a yield (decimal)."""
    if maturity <= settle:
        raise NotFound("The bond has matured.")
    prev, cfs = _schedule(settle, maturity, freq)
    period_days = (cfs[0] - prev).days or 1
    w = (cfs[0] - settle).days / period_days                    # fraction of a period to the next coupon
    c = coupon * face / freq
    accrued = c * (1 - w)
    flows = [(w + k, c + (face if i == len(cfs) - 1 else 0.0)) for k, i in zip(range(len(cfs)), range(len(cfs)))]

    def dirty_at(y):
        return sum(cf / (1 + y / freq) ** t for t, cf in flows)
    if ytm is None:
        if price is None:
            raise NotFound("Give a price or a yield.")
        target = price + accrued
        lo, hi = -0.05, 1.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if dirty_at(mid) > target:
                lo = mid
            else:
                hi = mid
        ytm = (lo + hi) / 2
    dirty = dirty_at(ytm)
    clean = dirty - accrued
    v = 1 + ytm / freq
    mac = sum(t * cf / v ** t for t, cf in flows) / dirty / freq
    mod = mac / v
    conv = sum(t * (t + 1) * cf / v ** (t + 2) for t, cf in flows) / dirty / freq ** 2
    dv01 = mod * dirty / 10000
    return {"ytm": ytm, "clean": clean, "dirty": dirty, "accrued": accrued, "macaulay": mac, "modified": mod, "convexity": conv,
            "dv01": dv01, "next_coupon": cfs[0].isoformat(), "previous_coupon": prev.isoformat(), "coupons_left": len(cfs),
            "current_yield": coupon * face / clean if clean else None, "years": (maturity - settle).days / 365.25}


def bond_calc(coupon: float, maturity: str, price: Optional[float] = None, ytm: Optional[float] = None,
              settle: Optional[str] = None, freq: int = 2, shock_bp: float = 100) -> Dict[str, Any]:
    st = date.fromisoformat(settle) if settle else date.today()
    mat = date.fromisoformat(maturity)
    base = bond_measures(coupon, mat, st, freq, price=price, ytm=ytm)
    up = bond_measures(coupon, mat, st, freq, ytm=base["ytm"] + shock_bp / 1e4)
    dn = bond_measures(coupon, mat, st, freq, ytm=max(-0.049, base["ytm"] - shock_bp / 1e4))
    grid = []
    for bp in (-200, -100, -50, -25, 0, 25, 50, 100, 200):
        m = bond_measures(coupon, mat, st, freq, ytm=max(-0.049, base["ytm"] + bp / 1e4))
        approx = base["clean"] * (1 - base["modified"] * bp / 1e4 + 0.5 * base["convexity"] * (bp / 1e4) ** 2)
        grid.append({"shift_bp": bp, "yield": m["ytm"], "price": m["clean"], "change": m["clean"] / base["clean"] - 1, "duration_convexity_estimate": approx})
    return {**base, "settle": st.isoformat(), "maturity": mat.isoformat(), "coupon": coupon, "frequency": freq,
            "price_up": up["clean"], "price_down": dn["clean"], "shock_bp": shock_bp, "grid": grid,
            "note": "Street convention: actual/actual accrual, yield compounded with the coupon frequency, clean prices per 100 face."}


# ── TSY: the Treasury market from FedInvest end-of-day prices ────────────────
def _fedinvest(day: date) -> List[List[str]]:
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (macro research terminal)"
    g = s.get("https://www.treasurydirect.gov/GA-FI/FedInvest/selectSecurityPriceDate", timeout=40)
    m = re.search(r'name="_csrf" value="([^"]+)"', g.text)
    if not m:
        raise Upstream("TreasuryDirect FedInvest form unavailable.")
    r = s.post("https://www.treasurydirect.gov/GA-FI/FedInvest/selectSecurityPriceDate",
               data={"priceDate": day.isoformat(), "submit": "Show Prices", "_csrf": m.group(1)}, timeout=60)
    rows = [re.findall(r"<td[^>]*>(.*?)</td>", x, re.S) for x in re.findall(r"<tr>(.*?)</tr>", r.text, re.S)]
    return [[re.sub(r"<[^>]+>", "", c).strip() for c in x] for x in rows if len(x) >= 8]


def treasuries() -> Dict[str, Any]:
    def build():
        rows, day = [], date.today()
        for _ in range(8):                                      # latest business day with prices
            day -= timedelta(days=1)
            if day.weekday() >= 5:
                continue
            try:
                rows = _fedinvest(day)
            except Exception as e:
                logger.info("[tsy] %s: %s", day, e)
                rows = []
            if rows:
                break
        if not rows:
            raise Upstream("TreasuryDirect end-of-day prices are unavailable right now.")
        settle = day + timedelta(days=1)
        while settle.weekday() >= 5:
            settle += timedelta(days=1)
        out = []
        for cusip, kind, rate, mat, _call, buy, sell, eod in rows[:600]:
            try:
                m = datetime.strptime(mat, "%m/%d/%Y").date()
                cpn = float(rate.rstrip("%")) / 100
                px = float(eod) or float(sell) or float(buy)
            except ValueError:
                continue
            if px <= 0 or (m - settle).days < 7:                 # a few days from maturity the yield is meaningless
                continue
            k = kind.replace("MARKET BASED ", "").title()
            rec = {"cusip": cusip, "type": k, "coupon": cpn, "maturity": m.isoformat(), "price": px, "years": (m - settle).days / 365.25}
            if k == "Bill":
                days = (m - settle).days
                rec["ytm"] = (100 - px) / px * 365 / days                       # bond-equivalent yield
                rec["modified"] = days / 365 / (1 + rec["ytm"] * days / 365)
                rec["dv01"] = rec["modified"] * px / 10000
            elif k in ("Note", "Bond", "Tips"):
                try:
                    bm = bond_measures(cpn, m, settle, 2, price=px)
                    rec.update({"ytm": bm["ytm"], "modified": bm["modified"], "convexity": bm["convexity"], "dv01": bm["dv01"], "accrued": bm["accrued"]})
                except Exception:
                    pass
            out.append(rec)
        out.sort(key=lambda r: r["maturity"])
        curve = {}
        for kind in ("nominal", "real"):
            pts = [r for r in out if r.get("ytm") is not None and ((r["type"] == "Tips") == (kind == "real")) and r["type"] != "Frn"]
            buckets = {}
            for r in pts:
                b = round(r["years"] * 2) / 2
                buckets.setdefault(b, []).append(r["ytm"])
            curve[kind] = [{"years": b, "ytm": float(np.median(v))} for b, v in sorted(buckets.items()) if b > 0]
        return {"price_date": day.isoformat(), "settle": settle.isoformat(), "securities": out, "curve": curve,
                "counts": {k: sum(1 for r in out if r["type"] == k) for k in ("Bill", "Note", "Bond", "Tips", "Frn")},
                "note": "End-of-day prices from the Treasury's FedInvest service; yields computed here (street convention; bills as bond-equivalent yield). "
                        "TIPS yields are real yields. Prices are indicative end-of-day values, not executable quotes.",
                "source": "TreasuryDirect FedInvest (U.S. Treasury)"}
    return _cached("tsy", 6 * 3600, build)


# ── FXCA: FX carry ───────────────────────────────────────────────────────────
CARRY_CCYS = {"EUR": "XM", "JPY": "JP", "GBP": "GB", "CHF": "CH", "CAD": "CA", "AUD": "AU", "NZD": "NZ", "SEK": "SE", "NOK": "NO",
              "MXN": "MX", "BRL": "BR", "ZAR": "ZA", "INR": "IN", "KRW": "KR", "TRY": "TR", "PLN": "PL", "HUF": "HU", "CZK": "CZ",
              "IDR": "ID", "CLP": "CL", "COP": "CO", "CNY": "CN", "THB": "TH", "ILS": "IL", "PHP": "PH"}


def fx_carry() -> Dict[str, Any]:
    from api.marketdata.core import yahoo_download
    from api.marketdata.toolkit import central_banks

    def build():
        cb = {b["code"]: b for b in central_banks()["banks"]}
        usd = cb.get("US", {}).get("rate")
        if usd is None:
            raise Upstream("No US policy rate from the BIS.")
        syms = {c: f"{c}USD=X" for c in CARRY_CCYS}
        df = yahoo_download(list(syms.values()), period="1y", auto_adjust=True, group_by="ticker", threads=True)
        rows = []
        for c, area in CARRY_CCYS.items():
            b = cb.get(area)
            try:
                px = (df[syms[c]] if isinstance(df.columns, pd.MultiIndex) else df)["Close"].dropna()
            except Exception:
                px = pd.Series(dtype=float)
            if b is None or len(px) < 60:
                continue
            r = np.log(px).diff().dropna()
            vol3m = float(r.iloc[-63:].std() * math.sqrt(252))
            carry = (b["rate"] - usd) / 100                          # long the currency, funded in dollars
            spot_1y = float(px.iloc[-1] / px.iloc[0] - 1)
            t = 0.25
            fwd = float(px.iloc[-1]) * (1 + usd / 100 * t) / (1 + b["rate"] / 100 * t)   # USD per unit, covered parity
            rows.append({"ccy": c, "country": b["country"], "policy_rate": b["rate"], "carry": carry, "vol_3m": vol3m,
                         "carry_to_vol": carry / vol3m if vol3m else None, "spot_usd": float(px.iloc[-1]), "spot_1y": spot_1y,
                         "carry_trade_1y": spot_1y + carry, "forward_3m": fwd, "forward_points_3m": (fwd - float(px.iloc[-1])) * 1e4,
                         "spot_3m": float(px.iloc[-1] / px.iloc[-64] - 1) if len(px) > 64 else None})
        rows.sort(key=lambda x: -(x["carry_to_vol"] or -9))
        top = [x for x in rows if x["carry"] > 0][:3]
        fund = sorted(rows, key=lambda x: x["carry"])[:3]
        basket = None
        if len(top) == 3 and len(fund) == 3:
            basket = {"long": [x["ccy"] for x in top], "short": [x["ccy"] for x in fund],
                      "carry": float(np.mean([x["carry"] for x in top]) - np.mean([x["carry"] for x in fund])),
                      "spot_1y": float(np.mean([x["spot_1y"] for x in top]) - np.mean([x["spot_1y"] for x in fund]))}
        return {"usd_rate": usd, "rows": rows, "basket": basket,
                "note": "Carry = the currency's policy rate minus the Fed's (what a long position funded in dollars earns a year if spot "
                        "doesn't move). Carry-to-vol divides it by 3-month realised volatility — the usual way to rank carry trades. "
                        "Policy rates stand in for 3-month deposit rates; the 3-month forward is from covered interest parity.",
                "source": "BIS policy rates; Yahoo Finance FX"}
    return _cached("fxca", 3 * 3600, build)
