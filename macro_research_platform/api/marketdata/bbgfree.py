"""Data the platform previously listed as "paid only", from free public sources:

    SWAP  swap curves      — USD SOFR, EUR €STR / Euribor, GBP SONIA, JPY TONA, CAD CORRA par swap rates from the day's
                             reported trades (DTCC public swap tape, CFTC Part 43), with US swap spreads to Treasuries
    CDSX  credit indices   — CDX IG / HY / EM and iTraxx Main / Crossover / financials from the same tape, with history
    CDSA  single-name CDS  — which companies' and countries' default swaps traded most (SEC security-based swap tape)
    EXTH  extended hours   — pre-market and after-hours movers (Benzinga, with the platform's key)
    TRAN  call transcripts — earnings-call transcripts by speaker (defeatbeta open dataset on Hugging Face, ODC-BY)

DTCC's public data is for internal use: shown here, not redistributed.
"""
from __future__ import annotations

import io
import json
import logging
import re
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from api.marketdata.core import NotFound, Upstream, _cached, _f

logger = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (MacroTerminal research)"}
DTCC = "https://kgc0418-tdw-data-0.s3.amazonaws.com/{regime}/eod/{regime_u}_CUMULATIVE_{kind}_{d:%Y_%m_%d}.zip"
STORE = Path(__file__).resolve().parents[2] / "data" / "processed" / "dtcc"


# ── DTCC public tape ─────────────────────────────────────────────────────────
def _notional(v: Any) -> Optional[float]:
    """'250,000,000+' (capped block size) → 250e6; DTCC's 99,999… placeholder → None."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    s = str(v).replace(",", "").rstrip("+").strip()
    try:
        x = float(s)
    except ValueError:
        return None
    return x if 0 < x < 1e17 else None


def _tape(kind: str, d: date, regime: str = "cftc") -> Optional[pd.DataFrame]:
    """One day's cumulative report (RATES or CREDITS), kept on disk once the day is over."""
    STORE.mkdir(parents=True, exist_ok=True)
    path = STORE / f"{regime}_{kind}_{d:%Y%m%d}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    import requests
    url = DTCC.format(regime=regime, regime_u=regime.upper(), kind=kind, d=d)
    r = requests.get(url, headers=UA, timeout=90)
    if r.status_code in (403, 404):
        return None
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        df = pd.read_csv(z.open(name), low_memory=False, dtype=str)
    keep = ["Action type", "Event type", "Execution Timestamp", "Effective Date", "Expiration Date", "Fixed rate-Leg 1",
            "Fixed rate-Leg 2", "Notional amount-Leg 1", "Notional currency-Leg 1", "Spread-Leg 1", "Spread notation-Leg 1",
            "Price", "Price notation", "Package indicator", "Cleared", "Platform identifier", "Underlier ID-Leg 1",
            "UPI Underlier Name", "UPI FISN", "Index factor"]
    df = df[[c for c in keep if c in df.columns]]
    if d < date.today():                                       # a finished day never changes: keep it
        try:
            df.to_parquet(path)
        except Exception as e:                                 # noqa: BLE001 — still usable in memory
            logger.info("dtcc store: %s", e)
    return df


def _latest_tapes(kind: str, n: int, regime: str = "cftc") -> List[Tuple[date, pd.DataFrame]]:
    """The last n published business days, newest first (DTCC posts each weekday's file that evening)."""
    out: List[Tuple[date, pd.DataFrame]] = []
    d = date.today()
    tries = 0
    while len(out) < n and tries < n * 2 + 6:
        tries += 1
        if d.weekday() < 5:
            try:
                df = _tape(kind, d, regime)
                if df is not None and len(df):
                    out.append((d, df))
            except Exception as e:                             # noqa: BLE001 — skip a missing day
                logger.info("dtcc %s %s: %s", kind, d, e)
        d -= timedelta(days=1)
    return out


# ── SWAP ─────────────────────────────────────────────────────────────────────
SWAP_INDICES = {
    "USD": ("USD SOFR OIS", ["USD-SOFR-OIS Compound", "USD-SOFR-COMPOUND", "USD-SOFR"]),
    "EUR": ("EUR €STR OIS", ["EUR-EuroSTR-OIS Compound", "EUR-EuroSTR-COMPOUND"]),
    "EURIBOR": ("EUR 6M Euribor", ["EUR-EURIBOR", "EUR-EURIBOR-Reuters"]),
    "GBP": ("GBP SONIA OIS", ["GBP-SONIA-OIS Compound", "GBP-SONIA-COMPOUND"]),
    "JPY": ("JPY TONA OIS", ["JPY-TONA-OIS Compound", "JPY-TONA-OIS-COMPOUND"]),
    "CAD": ("CAD CORRA OIS", ["CAD-CORRA-OIS-COMPOUND"]),
}
TENORS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 20, 25, 30, 40, 50]


def _wmedian(v: np.ndarray, w: np.ndarray) -> float:
    o = np.argsort(v)
    v, w = v[o], w[o]
    c = np.cumsum(w)
    return float(v[np.searchsorted(c, c[-1] / 2)])


def swap_curve_from_tape(df: pd.DataFrame) -> Dict[str, Dict[int, Dict[str, float]]]:
    """Par swap rates by currency and tenor: new, spot-starting, outright (not package) trades on a whole-year tenor,
    notional-weighted median of the fixed rate."""
    x = df[(df["Action type"] == "NEWT") & (df["Event type"].fillna("TRAD") == "TRAD")].copy()
    if "Package indicator" in x:
        x = x[x["Package indicator"].astype(str).str.lower() != "true"]
    exe = pd.to_datetime(x["Execution Timestamp"], errors="coerce", utc=True).dt.tz_localize(None).dt.normalize()
    eff = pd.to_datetime(x["Effective Date"], errors="coerce")
    exp = pd.to_datetime(x["Expiration Date"], errors="coerce")
    x = x[(eff - exe).dt.days.between(-1, 7)]                   # spot-starting: excludes forwards and IMM starts
    years = ((exp - eff).dt.days / 365.25).reindex(x.index)
    rate = pd.to_numeric(x["Fixed rate-Leg 1"], errors="coerce").fillna(pd.to_numeric(x["Fixed rate-Leg 2"], errors="coerce"))
    x = x.assign(years=years, rate=rate * 100, notional=x["Notional amount-Leg 1"].map(_notional))
    x = x[x["rate"].between(-2, 30)]
    out: Dict[str, Dict[int, Dict[str, float]]] = {}
    for ccy, (_, names) in SWAP_INDICES.items():
        y = x[x["UPI Underlier Name"].isin(names)]
        curve = {}
        for t in TENORS:
            z = y[(y["years"] - t).abs() <= 20 / 365.25]
            if len(z) < 2:
                continue
            r = z["rate"].to_numpy(float)
            med = float(np.median(r))
            z = z[(z["rate"] - med).abs() <= 0.5]               # drop off-market prints (non-standard terms)
            if len(z) < 2:
                continue
            w = z["notional"].fillna(z["notional"].median() if z["notional"].notna().any() else 1.0).to_numpy(float)
            curve[t] = {"rate": _wmedian(z["rate"].to_numpy(float), w), "trades": int(len(z)), "notional": float(np.nansum(w)),
                        "low": float(z["rate"].min()), "high": float(z["rate"].max())}
        if curve:
            out[ccy] = curve
    return out


def swap_curves(days: int = 10) -> Dict[str, Any]:
    """Today's swap curves and how 2-, 5-, 10- and 30-year rates moved over recent sessions; USD swap spreads."""
    def build():
        tapes = _latest_tapes("RATES", max(1, days))
        if not tapes:
            raise Upstream("DTCC's public swap tape is unavailable right now.")
        per_day = [(d, swap_curve_from_tape(df)) for d, df in tapes]
        d0, today = per_day[0]
        prev = next((c for d, c in per_day[1:] if c), {})
        curves = []
        for ccy, (label, _) in SWAP_INDICES.items():
            c = today.get(ccy)
            if not c:
                continue
            pts = [{"tenor": t, **v, "change_bp": (v["rate"] - prev[ccy][t]["rate"]) * 100 if ccy in prev and t in prev[ccy] else None}
                   for t, v in sorted(c.items())]
            hist = [{"date": str(d), **{f"y{t}": cc.get(ccy, {}).get(t, {}).get("rate") for t in (2, 5, 10, 30)}} for d, cc in reversed(per_day)]
            curves.append({"code": ccy, "name": label, "points": pts, "history": hist})
        spreads = []
        try:                                                    # swap spread: SOFR swap minus the Treasury par yield
            from api.marketdata.curves import curves as gov
            us = {p["tenor"]: p["yield"] for p in gov()["curves"]["US"]["points"]}
            for t, v in sorted((today.get("USD") or {}).items()):
                if float(t) in us:
                    spreads.append({"tenor": t, "swap": v["rate"], "treasury": us[float(t)], "spread_bp": (v["rate"] - us[float(t)]) * 100})
        except Exception as e:                                  # noqa: BLE001
            logger.info("swap spreads: %s", e)
        return {"date": str(d0), "curves": curves, "us_swap_spreads": spreads,
                "note": "Par rates from that day's reported trades: new, spot-starting, outright swaps at whole-year maturities, "
                        "notional-weighted median of the fixed rate (off-market prints dropped). Swap spread = SOFR swap minus "
                        "Treasury par yield (negative spreads are normal in USD).",
                "source": "DTCC public swap data (CFTC Part 43 real-time reports), internal use; Treasury curve US Treasury."}
    return _cached(f"swap:{days}", 3 * 3600, build)


# ── CDSX ─────────────────────────────────────────────────────────────────────
CDS_INDICES = [("CDX.NA.IG", "CDX North America IG", "spread"), ("CDX.NA.HY", "CDX North America HY", "price"),
               ("ITRAXX EUROPE", "iTraxx Europe Main", "spread"), ("ITRAXX EUROPE CROSSOVER", "iTraxx Europe Crossover", "spread"),
               ("ITRAXX EUROPE SENIOR FINANCIALS", "iTraxx Senior Financials", "spread"),
               ("ITRAXX EUROPE SUB FINANCIALS", "iTraxx Subordinated Financials", "spread"), ("CDX.EM", "CDX Emerging Markets", "price")]


def cds_levels_from_tape(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    """The on-the-run 5-year level of each index: median traded spread (bp) or price, from the most traded maturity."""
    x = df[(df["Action type"] == "NEWT")].copy()
    out = {}
    for name, label, quote in CDS_INDICES:
        y = x[x["UPI Underlier Name"] == name]
        if y.empty:
            continue
        mat = y["Expiration Date"].value_counts().index[0]
        y = y[y["Expiration Date"] == mat]
        sp = pd.to_numeric(y["Spread-Leg 1"], errors="coerce")
        nota = pd.to_numeric(y["Spread notation-Leg 1"], errors="coerce")
        if quote == "spread":
            v = sp[(nota == 3) & sp.between(0.0001, 0.5)] * 1e4
        else:
            v = sp[(nota == 1) & sp.between(50, 150)]
        if len(v) < 2:
            continue
        coupon = _f(pd.to_numeric(y["Fixed rate-Leg 1"], errors="coerce").mode().iloc[0]) if pd.to_numeric(y["Fixed rate-Leg 1"], errors="coerce").notna().any() else None
        rec = {"name": label, "maturity": mat, "quote": quote, "level": float(np.median(v)), "trades": int(len(y)),
               "notional": float(np.nansum(y["Notional amount-Leg 1"].map(_notional).to_numpy(dtype=float))), "coupon_bp": coupon * 1e4 if coupon else None}
        if quote == "price" and coupon:                         # rough spread from price: coupon − upfront ÷ risky duration (~4.3y)
            rec["spread_equiv_bp"] = coupon * 1e4 - (rec["level"] - 100) / 4.3 * 100
        out[name] = rec
    return out


def credit_indices(days: int = 22) -> Dict[str, Any]:
    """CDX and iTraxx index levels today, the change over the last session and month, and their recent history."""
    def build():
        tapes = _latest_tapes("CREDITS", max(2, days))
        if not tapes:
            raise Upstream("DTCC's public credit tape is unavailable right now.")
        per_day = [(d, cds_levels_from_tape(df)) for d, df in tapes]
        d0, today = per_day[0]
        rows = []
        for name, label, quote in CDS_INDICES:
            t = today.get(name)
            if not t:
                continue
            series = [(d, lv[name]["level"]) for d, lv in per_day if name in lv]
            prev = series[1][1] if len(series) > 1 else None
            first = series[-1][1] if len(series) > 1 else None
            sign = -1 if quote == "price" else 1                # a falling price is wider credit
            rows.append({**t, "index": name, "change_1d": (t["level"] - prev) if prev is not None else None,
                         "change_period": (t["level"] - first) if first is not None else None, "since": str(series[-1][0]),
                         "widening": None if prev is None else (sign * (t["level"] - prev) > 0),
                         "history": [{"date": str(d), "level": v} for d, v in reversed(series)]})
        if not rows:
            raise Upstream("No index trades on the latest tape.")
        return {"date": str(d0), "rows": rows,
                "note": "IG, iTraxx Main and Crossover trade as spreads (bp); CDX HY and EM trade as prices (100 = par, lower = "
                        "wider). Levels are the median of that day's reported trades in the most-traded (on-the-run 5-year) "
                        "maturity. The HY spread is approximate (coupon minus upfront ÷ ~4.3 years of risky duration).",
                "source": "DTCC public swap data (CFTC Part 43), internal use."}
    return _cached(f"cdsx:{days}", 3 * 3600, build)


# ── CDSA ─────────────────────────────────────────────────────────────────────
def _figi_names(isins: List[str]) -> Dict[str, Dict[str, str]]:
    """Issuer names for ISINs from OpenFIGI (free; ≤10 identifiers per request without a key), cached on disk."""
    import requests
    path = STORE / "figi_names.json"
    try:
        known = json.loads(path.read_text())
    except Exception:
        known = {}
    todo = [i for i in isins if i not in known][:250]
    for k in range(0, len(todo), 10):
        batch = todo[k:k + 10]
        try:
            r = requests.post("https://api.openfigi.com/v3/mapping", json=[{"idType": "ID_ISIN", "idValue": i} for i in batch],
                              headers={"Content-Type": "application/json"}, timeout=30)
            if r.status_code == 429:
                break
            r.raise_for_status()
            for i, res in zip(batch, r.json()):
                d = (res.get("data") or [{}])[0]
                known[i] = {"name": d.get("name") or "", "ticker": d.get("ticker") or "", "type": d.get("securityType2") or ""}
        except Exception as e:                                  # noqa: BLE001 — unnamed rows still show the ISIN
            logger.info("openfigi: %s", e)
            break
    try:
        STORE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(known))
    except Exception:
        pass
    return known


GENERIC_NAMES = {"NO NAME OBTAINABLE", "NT", "SR NT", "BD", "GLOBAL BD", "GLOBAL NT", "SR NT 144A", "GTD SR NT", "SUB NT 144A", "NAN"}


def _valid_isin(s: Any) -> bool:
    """ISIN with a correct check digit — and not the standard-reference-obligation placeholder shared by many names."""
    s = str(s or "")
    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", s) or s.startswith("XSSNRREF"):
        return False
    digits = "".join(str(int(c, 36)) for c in s[:11])
    total = 0
    for k, ch in enumerate(reversed(digits)):
        d = int(ch) * (2 if k % 2 == 0 else 1)
        total += d // 10 + d % 10
    return (10 - total % 10) % 10 == int(s[11])


def _entity_key(underlier: Any, name: Any) -> Optional[str]:
    """One key per reference entity: the issuer part of a real ISIN (country + 6-character issuer code), else the entity
    name the tape gives (placeholder ISINs and Markit RED codes carry it), else the RED entity code."""
    u, n = str(underlier or "").strip(), str(name or "").strip().upper()
    if _valid_isin(u):
        return u[:8]
    if n and n not in GENERIC_NAMES and not re.search(r"\d|%|NOTE|BOND|\bNT\b|\bBD\b", n):
        return "NAME:" + n
    if re.fullmatch(r"[A-Z0-9]{6}([A-Z0-9]{3})?", u):
        return "RED:" + u[:6]
    return None


def single_name_cds(days: int = 5) -> Dict[str, Any]:
    """Single-name CDS trading over recent sessions, by reference entity: trades and notional, corporate vs sovereign.
    Single-name prices are rarely disseminated, so this ranks hedging activity, not spreads."""
    def build():
        tapes = _latest_tapes("CREDITS", max(1, days), regime="sec")
        for d, df in tapes:
            df["day"] = str(d)
        if not tapes:
            raise Upstream("DTCC's security-based swap tape is unavailable right now.")
        frames = []
        for d, df in tapes:
            x = df[(df["Action type"] == "NEWT") & df["UPI FISN"].fillna("").str.contains("SN")]
            frames.append(x)
        x = pd.concat(frames)
        x = x.assign(issuer=[_entity_key(i, n) for i, n in zip(x["Underlier ID-Leg 1"], x["UPI Underlier Name"])])
        x = x[x["issuer"].notna()]
        # spreads, where the tape carries one (about one trade in eight): decimal notation, 1bp–50%, CDS not total-return swaps
        sp = pd.to_numeric(x["Spread-Leg 1"], errors="coerce")
        nota = pd.to_numeric(x["Spread notation-Leg 1"], errors="coerce")
        exp = pd.to_datetime(x["Expiration Date"], errors="coerce")
        tenor = (exp - pd.to_datetime(x["day"])).dt.days / 365.25
        # some reporters submit the spread 100× too small (Egypt at 3bp): a traded CDS is never under ~5bp, so those go
        x = x.assign(spread_bp=(sp * 1e4).where((nota == 3) & sp.between(0.0005, 0.5) & x["UPI FISN"].str.contains("CDS")),
                     tenor=tenor)
        x = x.assign(notional=x["Notional amount-Leg 1"].map(_notional),
                     sovereign=x["UPI FISN"].str.contains("Sov"))
        g = x.groupby("issuer").agg(trades=("issuer", "size"), notional=("notional", "sum"), isin=("Underlier ID-Leg 1", "first"),
                                    sovereign=("sovereign", "max"), bond=("UPI Underlier Name", "first"),
                                    days=("day", "nunique")).reset_index().sort_values(["trades", "notional"], ascending=False)
        top = g.head(60)
        names = _figi_names([i for i in top["isin"].tolist() if _valid_isin(i)])
        five = x[x["spread_bp"].notna() & x["tenor"].between(4.0, 5.9)]          # the 5-year point, as quoted
        n5 = five.groupby("issuer").size()
        spread5 = five.groupby("issuer")["spread_bp"].median()[n5 >= 3]           # one or two prints aren't a market
        last_day = five.groupby(["issuer", "day"])["spread_bp"].median()
        rows = []
        for _, r in top.iterrows():
            nm = names.get(r["isin"], {})
            hist = last_day.get(r["issuer"]) if r["issuer"] in last_day.index.get_level_values(0) else None
            rows.append({"issuer_code": r["issuer"], "isin": r["isin"] if _valid_isin(r["isin"]) else None,
                         "name": nm.get("name") or (r["issuer"][5:] if r["issuer"].startswith("NAME:") else None),
                         "ticker": nm.get("ticker"), "sovereign": bool(r["sovereign"]), "trades": int(r["trades"]),
                         "notional": float(r["notional"]) if pd.notna(r["notional"]) else None, "days_traded": int(r["days"]),
                         "spread_5y_bp": float(spread5[r["issuer"]]) if r["issuer"] in spread5.index else None,
                         "spread_prints": int(n5.get(r["issuer"], 0)),
                         "spread_history": [{"date": d, "spread_bp": float(v)} for d, v in sorted(hist.items())]
                         if hist is not None and r["issuer"] in spread5.index else []})
        # the same company reached through bond ISINs and through its name: one row
        def norm(nm):
            w = re.sub(r"[^A-Z0-9 ]", " ", (nm or "").upper()).split()
            return " ".join(t for t in w if t not in {"INC", "CORP", "CORPORATION", "CO", "LTD", "PLC", "SA", "SPA", "AG", "NV", "THE", "LLC", "COMPANY"})
        merged: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            k = norm(r["name"]) or r["issuer_code"]
            m = merged.get(k)
            if m is None:
                merged[k] = r
                continue
            m["trades"] += r["trades"]
            m["notional"] = (m["notional"] or 0) + (r["notional"] or 0)
            m["days_traded"] = max(m["days_traded"], r["days_traded"])
            if r["spread_prints"] > m["spread_prints"]:
                m["spread_5y_bp"], m["spread_history"] = r["spread_5y_bp"], r["spread_history"]
            m["spread_prints"] += r["spread_prints"]
            m["isin"] = m["isin"] or r["isin"]
            m["ticker"] = m["ticker"] or r["ticker"]
        for r in merged.values():
            if not r["name"] and r["issuer_code"].startswith("RED:"):
                r["name"] = f"RED {r['issuer_code'][4:]} (unnamed: Markit RED codes are licensed)"
        rows = sorted(merged.values(), key=lambda r: -r["trades"])
        return {"from": tapes[-1][0].isoformat(), "to": tapes[0][0].isoformat(), "sessions": len(tapes), "rows": rows,
                "total_trades": int(len(x)), "entities": int(len(g)),
                "with_spreads": int(sum(1 for r in merged.values() if r["spread_5y_bp"] is not None)),
                "note": "Counts new single-name CDS trades by reference entity (grouped by the issuer part of the reference bond's ISIN). "
                        "The 5-year spread is the median of the trades that disseminated one (the public tape omits it for most "
                        "single-name trades), so it shows only for names with at least three such trades; prints under 5bp are "
                        "dropped as mis-scaled. "
                        "Notional is capped in the public tape for large trades, so it understates block size. Busy names are "
                        "where credit protection is being bought or sold — often around earnings, downgrades or M&A.",
                "source": "DTCC public security-based swap data (SEC Regulation SBSR), internal use; names OpenFIGI."}
    return _cached(f"cdsa3:{days}", 6 * 3600, build)


# ── EXTH ─────────────────────────────────────────────────────────────────────
def extended_hours(session: str = "PRE_MARKET", min_cap: float = 5e8, min_price: float = 2.0) -> Dict[str, Any]:
    """Pre-market or after-hours gainers and losers, filtered to companies of a meaningful size."""
    from api.providers import benzinga
    session = session.upper()
    if session not in ("PRE_MARKET", "AFTER_MARKET", "REGULAR"):
        raise NotFound("Session must be PRE_MARKET, AFTER_MARKET or REGULAR.")
    if not benzinga.available():
        raise NotFound("Extended-hours movers need the Benzinga key in .env (BENZINGA_API_KEY).")
    params = {"maxResults": 100} | ({"session": session} if session != "REGULAR" else {})
    r = benzinga._get("/v1/market/movers", params, 120).get("result") or {}

    def clean(rows):
        out = []
        for m in rows or []:
            cap, px = _f(m.get("marketCap")), _f(m.get("price"))
            if (cap or 0) < min_cap or (px or 0) < min_price:
                continue
            vol, avg = _f(m.get("volume")), _f(m.get("averageVolume"))
            out.append({"symbol": m.get("symbol"), "name": m.get("companyName"), "price": px, "change": _f(m.get("change")),
                        "change_pct": (_f(m.get("changePercent")) or 0) / 100, "volume": vol, "avg_volume": avg,
                        "previous_close": _f(m.get("previousClose")), "market_cap": cap, "sector": m.get("gicsSectorName")})
        return out[:30]
    return {"session": session, "from": r.get("fromDate"), "to": r.get("toDate"), "gainers": clean(r.get("gainers")),
            "losers": clean(r.get("losers")), "min_market_cap": min_cap,
            "note": "Change is against the previous regular-session close. Extended-hours trading is thin: moves on small volume "
                    "can reverse at the open.",
            "source": "Benzinga market movers (session snapshot)."}


# ── TRAN ─────────────────────────────────────────────────────────────────────
TRANSCRIPTS = "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/resolve/main/data/US/stock_earning_call_transcripts.parquet"


class _RangeFile(io.RawIOBase):
    """A read-only file over HTTP range requests, so pyarrow reads only a parquet file's footer and the row groups it needs."""

    def __init__(self, url: str):
        import requests
        self.s = requests.Session()
        r = self.s.head(url, allow_redirects=True, timeout=30)
        r.raise_for_status()
        self.url, self.size, self.pos = r.url, int(r.headers["Content-Length"]), 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = offset if whence == 0 else self.pos + offset if whence == 1 else self.size + offset
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        if n == 0:
            return b""
        r = self.s.get(self.url, headers={"Range": f"bytes={self.pos}-{self.pos + n - 1}"}, timeout=90)
        r.raise_for_status()
        self.pos += len(r.content)
        return r.content

    def readinto(self, b):
        d = self.read(len(b))
        b[:len(d)] = d
        return len(d)


def _transcript_rows(symbol: str) -> pd.DataFrame:
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(_RangeFile(TRANSCRIPTS))
    md = pf.metadata
    groups = []
    for g in range(md.num_row_groups):
        st = md.row_group(g).column(0).statistics
        if st is not None and st.has_min_max and st.min <= symbol <= st.max:
            groups.append(g)
    if not groups:
        return pd.DataFrame()
    tab = pf.read_row_groups(groups)
    tab = tab.filter(pc.equal(tab["symbol"], symbol))
    return tab.to_pandas()


def _calls(symbol: str) -> List[Dict[str, Any]]:
    """Every call for a company, newest first, each as speaker turns (cached; ~3 s to read from the dataset)."""
    symbol = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z.\-]{0,6}", symbol):
        raise NotFound("Transcripts cover US-listed companies.")

    def build():
        df = _transcript_rows(symbol)
        if df.empty:
            raise NotFound(f"No earnings-call transcripts for {symbol} in the open dataset.")
        df = df.sort_values("report_date", ascending=False)
        num = lambda v: int(v) if v is not None and not pd.isna(v) else None
        return [{"id": num(r["transcripts_id"]), "date": r["report_date"], "fiscal_year": num(r["fiscal_year"]),
                 "fiscal_quarter": num(r["fiscal_quarter"]),
                 "paragraphs": [{"speaker": p["speaker"], "text": p["content"]} for p in (r["transcripts"] if r["transcripts"] is not None else [])]}
                for _, r in df.iterrows() if not pd.isna(r["transcripts_id"])]
    return _cached(f"tran:{symbol}", 12 * 3600, build)


def _speakers(c: Dict[str, Any]) -> List[Dict[str, Any]]:
    seen: Dict[str, int] = {}
    for p in c["paragraphs"]:
        seen[p["speaker"]] = seen.get(p["speaker"], 0) + len(p["text"])
    return [{"speaker": k, "chars": v} for k, v in sorted(seen.items(), key=lambda kv: -kv[1])]


def transcripts(symbol: str) -> Dict[str, Any]:
    """A company's earnings calls: the list, and the latest call as speaker turns."""
    calls = _calls(symbol)
    return {"symbol": symbol.strip().upper(),
            "calls": [{k: c[k] for k in ("id", "date", "fiscal_year", "fiscal_quarter")} | {"paragraphs": len(c["paragraphs"])} for c in calls],
            "latest": {**calls[0], "speakers": _speakers(calls[0])},
            "source": "defeatbeta/yahoo-finance-data on Hugging Face (ODC-BY licence), read by range request."}


def transcript(symbol: str, call_id: int) -> Dict[str, Any]:
    """One call's full text by speaker turn."""
    c = next((x for x in _calls(symbol) if x["id"] == int(call_id)), None)
    if not c:
        raise NotFound("That call isn't in the dataset.")
    return {"symbol": symbol.strip().upper(), **c, "speakers": _speakers(c)}


def transcript_search(symbol: str, query: str, limit: int = 12) -> Dict[str, Any]:
    """The speaker turns, across all of a company's calls, that mention the query words — newest calls first."""
    from api.marketdata.bbgplus import _stem, _terms
    symbol = symbol.strip().upper()
    terms = [_stem(t) for t in _terms(query or "")]
    if not terms:
        raise NotFound("Type a few words to search the calls for.")
    calls = _calls(symbol)
    hits = []
    def chunks(text: str, size: int = 700) -> List[str]:
        """Long turns (prepared remarks are often one paragraph) as ~size-character runs of whole sentences."""
        if len(text) <= size * 1.3:
            return [text]
        out, buf = [], ""
        for sent in re.split(r"(?<=[.!?])\s+", text):
            if buf and len(buf) + len(sent) > size:
                out.append(buf)
                buf = ""
            buf = f"{buf} {sent}".strip()
        return out + ([buf] if buf else [])
    for k, c in enumerate(calls[:16]):                           # the last four years of calls, newer ones weighted up
        recency = 1 / (1 + 0.15 * k)
        for p in c["paragraphs"]:
            for piece in chunks(p["text"]):
                words = [_stem(w) for w in re.findall(r"[a-z0-9][a-z0-9\-&$%.]*[a-z0-9%]|[a-z0-9]", piece.lower())]
                n = sum(words.count(t) for t in terms)
                cov = sum(1 for t in terms if t in words) / len(terms)
                if n and cov >= 0.5:
                    hits.append({"date": c["date"], "quarter": f"FY{c['fiscal_year']} Q{c['fiscal_quarter']}" if c["fiscal_year"] else c["date"],
                                 "call_id": c["id"], "speaker": p["speaker"], "text": piece,
                                 "score": recency * cov * cov * n / np.sqrt(1 + len(words) / 80)})
    hits.sort(key=lambda h: -h["score"])
    return {"symbol": symbol, "query": query, "terms": terms, "hits": hits[:limit], "matches": len(hits)}


# ── BOND: corporate-bond market breadth (FINRA TRACE, free API account) ──────
def bond_market(days: int = 30) -> Dict[str, Any]:
    """US corporate-bond market breadth from TRACE: bonds advancing vs declining, 52-week highs and lows, trades and
    volume by investment grade / high yield / convertible, over recent sessions."""
    from api.providers import finra_api
    if not finra_api.available():
        raise NotFound("Corporate-bond breadth needs a free FINRA API account: create one at developer.finra.org, then add "
                       "FINRA_API_CLIENT_ID and FINRA_API_CLIENT_SECRET to .env and restart the backend.")

    def build():
        rows, d, tries = [], date.today(), 0
        while len({r["tradeReportDate"] for r in rows}) < days and tries < days * 2:
            tries += 1
            if d.weekday() < 5:
                got = finra_api.query("fixedIncomeMarket", "corporateMarketBreadth",
                                      {"compareFilters": [{"compareType": "EQUAL", "fieldName": "tradeReportDate", "fieldValue": str(d)}]})
                rows += got
            d -= timedelta(days=1)
        if not rows:
            raise Upstream("FINRA returned no corporate-bond breadth.")
        df = pd.DataFrame(rows)
        latest = df["tradeReportDate"].max()
        cats = []
        for cat, g in df.groupby("productCategory"):
            g = g.sort_values("tradeReportDate")
            last = g.iloc[-1]
            adv, dec = float(last.get("advances") or 0), float(last.get("declines") or 0)
            cats.append({"category": cat, "date": last["tradeReportDate"], "advances": adv, "declines": dec,
                         "unchanged": float(last.get("unchanged") or 0), "highs_52w": float(last.get("fiftyTwoWeekHigh") or 0),
                         "lows_52w": float(last.get("fiftyTwoWeekLow") or 0), "trades": float(last.get("totalTrades") or 0),
                         "volume": float(last.get("totalVolume") or 0), "ad_ratio": adv / dec if dec else None,
                         "history": [{"date": r["tradeReportDate"], "net_advances": float((r.get("advances") or 0) - (r.get("declines") or 0)),
                                      "highs_minus_lows": float((r.get("fiftyTwoWeekHigh") or 0) - (r.get("fiftyTwoWeekLow") or 0))}
                                     for _, r in g.iterrows()]})
        return {"date": latest, "categories": cats,
                "note": "Advances and declines count bonds whose last price rose or fell versus their previous trade day; "
                        "52-week highs and lows count bonds at new price extremes.",
                "source": "FINRA TRACE market breadth (FINRA Query API)."}
    return _cached(f"bondmkt:{days}", 3 * 3600, build)
