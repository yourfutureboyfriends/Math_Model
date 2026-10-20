"""
Cycle & systemic-risk indicators from published research (see api/calculations/systemic_risk.py
for the methods and references).

Data (all free, official or exchange-traded; none depends on FRED):
  * Federal Reserve — Gürkaynak–Sack–Wright zero-coupon curve parameters (feds200628.csv,
    daily since 1961) for the near-term forward spread.
  * Federal Reserve — Gilchrist–Zakrajšek excess bond premium (ebp_csv.csv, monthly), with
    the Fed's own model-implied 12-month recession probability.
  * Yahoo — daily closes of liquid ETFs for turbulence (multi-asset) and the absorption ratio
    (US sector SPDRs).
Downloads are cached on disk for a day; on failure the last good copy is used.
"""
from __future__ import annotations

import asyncio
import io
import logging
import time
from datetime import date
from typing import Any, Dict, List, Optional

import numpy as np

from api.calculations import systemic_risk as sr

logger = logging.getLogger(__name__)

GSW_URL = "https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv"
EBP_URL = "https://www.federalreserve.gov/econres/notes/feds-notes/ebp_csv.csv"
_UA = {"User-Agent": "Mozilla/5.0 (macro research terminal)"}
_DAY = 24 * 3600

TURBULENCE_UNIVERSE = {"SPY": "US equity", "EFA": "Developed ex-US equity", "EEM": "EM equity",
                       "TLT": "Long Treasuries", "IEF": "7-10Y Treasuries", "LQD": "IG credit",
                       "HYG": "HY credit", "GLD": "Gold", "DBC": "Commodities", "UUP": "US dollar"}
SECTOR_UNIVERSE = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLP", "XLY", "XLU", "XLB"]
# Proxies for the environmental-balance reference portfolio.
ENV_PROXIES = {"Equity": "SPY", "Corporate credit": "LQD", "Nominal bonds": "TLT",
               "Inflation-linked bonds": "TIP", "Commodities": "DBC", "Gold": "GLD"}
SYMBOL_CLASS = {"TLT": "Nominal bonds", "IEF": "Nominal bonds", "SHY": "Nominal bonds", "BND": "Nominal bonds",
                "AGG": "Nominal bonds", "GOVT": "Nominal bonds", "TIP": "Inflation-linked bonds",
                "SCHP": "Inflation-linked bonds", "GLD": "Gold", "IAU": "Gold", "DBC": "Commodities",
                "USO": "Commodities", "GSG": "Commodities", "PDBC": "Commodities", "HYG": "Corporate credit",
                "LQD": "Corporate credit", "JNK": "Corporate credit"}


def _cached(name: str, fetch, ttl: float = _DAY):
    from api.handlers.macro_inputs import _disk_load, _disk_save
    fresh = _disk_load(f"ri_{name}", max_age=ttl)
    if fresh is not None:
        return fresh["data"], "ok"
    try:
        data = fetch()
        _disk_save(f"ri_{name}", {"data": data})
        return data, "ok"
    except Exception as e:
        logger.warning("[research] %s fetch failed: %s", name, e)
        stale = _disk_load(f"ri_{name}")
        return (stale["data"], "stale-cache") if stale else (None, "unavailable")


# ── Near-term forward spread (GSW curve) ────────────────────────────────────
def _fetch_ntfs() -> Dict[str, Any]:
    import pandas as pd
    import requests
    r = requests.get(GSW_URL, headers=_UA, timeout=120)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), skiprows=9,
                     usecols=lambda c: c in ("Date", "BETA0", "BETA1", "BETA2", "BETA3", "TAU1", "TAU2", "SVENY01"))
    df = df.dropna(subset=["BETA0", "BETA1", "BETA2", "TAU1"])
    df["Date"] = pd.to_datetime(df["Date"])
    vals = [sr.near_term_forward_spread((b0, b1, b2, b3, t1, t2)) for b0, b1, b2, b3, t1, t2 in
            zip(df.BETA0, df.BETA1, df.BETA2, df.BETA3.fillna(0.0), df.TAU1, df.TAU2.fillna(1.0))]
    df["ntfs"] = vals
    daily = df[["Date", "ntfs"]].dropna()
    monthly = daily.set_index("Date")["ntfs"].resample("MS").mean().dropna()
    return {"monthly": {d.strftime("%Y-%m"): round(float(v), 4) for d, v in monthly.items()},
            "daily_tail": [(d.strftime("%Y-%m-%d"), round(float(v), 4)) for d, v in daily.tail(260).values],
            "as_of": daily["Date"].iloc[-1].strftime("%Y-%m-%d")}


def _recession_ahead(months: List[str], horizon: int = 12) -> Dict[str, Optional[int]]:
    """1 if any month in (t, t+horizon] is an NBER recession month; None where the window is
    not yet complete."""
    from api.models_ml.recession_probit import NBER_RECESSIONS
    import pandas as pd
    rec = set()
    for start, end in NBER_RECESSIONS:
        for d in pd.date_range(start, end, freq="MS"):
            rec.add(d.strftime("%Y-%m"))
    last_known = max(months)
    out = {}
    for m in months:
        y, mo = map(int, m.split("-"))
        window = [f"{y + (mo - 1 + k) // 12}-{(mo - 1 + k) % 12 + 1:02d}" for k in range(1, horizon + 1)]
        out[m] = None if window[-1] > last_known else int(any(w in rec for w in window))
    return out


def ntfs_block() -> Dict[str, Any]:
    data, status = _cached("ntfs", _fetch_ntfs)
    if not data:
        return {"available": False, "reason": "Federal Reserve yield-curve file unavailable", "source_status": status}
    monthly = data["monthly"]
    months = sorted(monthly)
    labels = _recession_ahead(months)
    train = [(monthly[m], labels[m]) for m in months if labels[m] is not None and m >= "1972-01"]
    model = sr.fit_recession_probit([x for x, _ in train], [y for _, y in train]) if train else None
    latest_daily = data["daily_tail"][-1]
    cur = latest_daily[1]
    hist = np.array([monthly[m] for m in months])
    return {
        "available": True, "value_pp": round(cur, 3), "as_of": latest_daily[0],
        "percentile": round(float((hist < cur).mean() * 100), 1),
        "signal": "Easing priced (recession risk)" if cur < 0 else "No easing priced",
        "recession_probability_12m": round(sr.probit_prob(model, cur), 4) if model else None,
        "model": ({**{k: round(v, 4) for k, v in model.items()}, "training_months": len(train),
                   "target": "NBER recession in the next 12 months"} if model else None),
        "history": [{"date": m, "value": monthly[m]} for m in months[-120:]],
        "source": "Federal Reserve GSW zero-coupon curve (feds200628)", "source_status": status,
        "method": "Forward 3-month rate 18 months ahead minus the current 3-month zero yield "
                  "(Engstrom & Sharpe, 2019); probit fitted on monthly data since 1972.",
    }


# ── Excess bond premium ──────────────────────────────────────────────────────
def _fetch_ebp() -> List[List]:
    import requests
    r = requests.get(EBP_URL, headers=_UA, timeout=60)
    r.raise_for_status()
    rows = []
    for line in r.text.strip().splitlines()[1:]:
        d, gz, ebp, prob = line.split(",")[:4]
        m, _, y = d.split("/")
        rows.append([f"{y}-{int(m):02d}", float(gz), float(ebp), float(prob)])
    return rows


def ebp_block() -> Dict[str, Any]:
    rows, status = _cached("ebp", _fetch_ebp)
    if not rows:
        return {"available": False, "reason": "Federal Reserve EBP file unavailable", "source_status": status}
    rows.sort()
    m, gz, ebp, prob = rows[-1]
    hist = np.array([r[2] for r in rows])
    prev12 = next((r for r in rows if r[0] == f"{int(m[:4]) - 1}{m[4:]}"), None)
    return {
        "available": True, "as_of": m, "ebp_pp": round(ebp, 3), "gz_spread_pp": round(gz, 3),
        "fed_recession_probability_12m": round(prob, 4),
        "ebp_percentile": round(float((hist < ebp).mean() * 100), 1),
        "ebp_change_12m_pp": round(ebp - prev12[2], 3) if prev12 else None,
        "signal": ("Elevated — credit risk appetite weak" if ebp > 0.5 else
                   "Below average — strong credit risk appetite" if ebp < 0 else "Near average"),
        "history": [{"date": r[0], "ebp": round(r[2], 3), "probability": round(r[3], 4)} for r in rows[-120:]],
        "source": "Federal Reserve (Gilchrist & Zakrajšek, 2012; monthly update)", "source_status": status,
    }


# ── Turbulence and absorption ratio ──────────────────────────────────────────
async def _returns_matrix(tickers: List[str], period: str = "10y"):
    from api.handlers.market_handler import _fetch_dated_closes_literal
    closes = await asyncio.gather(*[_fetch_dated_closes_literal(t, period) for t in tickers])
    ok = [(t, c) for t, c in zip(tickers, closes) if c and len(c) > 300]
    if len(ok) < 3:
        return None, [], []
    common = sorted(set.intersection(*[set(c) for _, c in ok]))
    px = np.array([[c[d] for _, c in ok] for d in common])
    rets = np.diff(np.log(px), axis=0)
    return rets, [t for t, _ in ok], common[1:]


async def turbulence_block() -> Dict[str, Any]:
    rets, names, dates = await _returns_matrix(list(TURBULENCE_UNIVERSE))
    if rets is None or len(rets) < 300:
        return {"available": False, "reason": "insufficient price history"}
    turb = await asyncio.to_thread(sr.turbulence_series, rets)
    valid = turb[~np.isnan(turb)]
    thr75 = float(np.percentile(valid, 75))
    last20 = valid[-20:]
    return {
        "available": True, "as_of": dates[-1], "assets": [TURBULENCE_UNIVERSE[t] for t in names],
        "value": round(float(valid[-1]), 2), "avg_20d": round(float(last20.mean()), 2),
        "percentile": sr.percentile_of_last(turb),
        "percentile_20d_avg": round(float((valid < last20.mean()).mean() * 100), 1),
        "threshold_75th": round(thr75, 2), "turbulent": bool(last20.mean() > thr75),
        "turbulent_days_last_20": int((last20 > thr75).sum()),
        "history": [{"date": d, "value": round(float(v), 2)} for d, v in zip(dates[-250:], turb[-250:]) if v == v],
        "method": "Mahalanobis distance of daily returns vs the prior 3-year mean/covariance "
                  "(Kritzman & Li, 2010); turbulent = above the 75th percentile.",
    }


async def absorption_block() -> Dict[str, Any]:
    rets, names, dates = await _returns_matrix(SECTOR_UNIVERSE)
    if rets is None or len(rets) < 760:
        return {"available": False, "reason": "insufficient price history"}
    ar = await asyncio.to_thread(sr.absorption_ratio_series, rets[-1100:], 500)
    valid = ar[~np.isnan(ar)]
    shift = sr.standardized_shift(ar)
    return {
        "available": True, "as_of": dates[-1], "assets": names, "eigenvectors": max(1, int(np.ceil(0.2 * len(names)))),
        "value": round(float(valid[-1]), 4), "percentile": sr.percentile_of_last(ar),
        "standardized_shift": shift,
        "signal": ("Fragile — markets tightly coupled" if shift is not None and shift >= 1 else
                   "Decoupling" if shift is not None and shift <= -1 else "Normal"),
        "history": [{"date": d, "value": round(float(v), 4)} for d, v in zip(dates[-1100:][-250:], ar[-250:]) if v == v],
        "method": "Variance share of the top fifth of eigenvectors of US sector returns, 500-day "
                  "window, 250-day half-life; shift = (15-day − 1-year mean) / 1-year σ "
                  "(Kritzman, Li, Page & Rigobon, 2011).",
    }


# ── Environmental balance ────────────────────────────────────────────────────
async def environment_block() -> Dict[str, Any]:
    from api import portfolio_store
    from api.handlers.market_handler import _fetch_dated_closes_literal

    async def vol(t):
        c = await _fetch_dated_closes_literal(t)
        days = sorted(c or {})
        if len(days) < 60:
            return None
        px = np.array([c[d] for d in days])
        return float(np.diff(np.log(px)).std() * np.sqrt(252))

    proxy_vols = dict(zip(ENV_PROXIES, await asyncio.gather(*[vol(t) for t in ENV_PROXIES.values()])))
    balanced = sr.environment_balanced_weights({k: v for k, v in proxy_vols.items() if v})

    book = None
    positions = await asyncio.to_thread(portfolio_store.list_positions, None)
    if positions:
        syms = sorted({str(p["symbol"]).upper() for p in positions})
        vols = dict(zip(syms, await asyncio.gather(*[vol(s) for s in syms])))
        risk: Dict[str, float] = {}
        for p in positions:
            s = str(p["symbol"]).upper()
            mv = abs(float(p["quantity"]) * float(p.get("avg_cost") or 0))
            ac = SYMBOL_CLASS.get(s, "Equity")
            if vols.get(s):
                risk[ac] = risk.get(ac, 0.0) + mv * vols[s]
        split = sr.environment_risk_split(risk)
        book = {"risk_by_environment": split, "balance_score": sr.balance_score(split),
                "risk_by_asset_class": {k: round(v / sum(risk.values()), 4) for k, v in risk.items()} if risk else {}}
    return {
        "available": True,
        "environments": list(sr.ENVIRONMENTS),
        "asset_environments": {k: list(v) for k, v in sr.ASSET_ENVIRONMENTS.items()},
        "balanced_weights": balanced, "proxies": ENV_PROXIES,
        "proxy_volatility": {k: round(v, 4) for k, v in proxy_vols.items() if v},
        "book": book,
        "method": "Each asset class's standalone risk (|value| × volatility) is split between the two "
                  "growth/inflation environments it tends to do well in; balanced weights give each "
                  "environment 25% of risk (correlations ignored). Principle: balance across economic "
                  "environments rather than across assets (Bridgewater, Prince).",
    }


async def build_cycle_risk() -> Dict[str, Any]:
    t0 = time.time()
    ntfs, ebp = await asyncio.gather(asyncio.to_thread(ntfs_block), asyncio.to_thread(ebp_block))
    turb, ar, env = await asyncio.gather(turbulence_block(), absorption_block(), environment_block())
    return {"near_term_forward_spread": ntfs, "excess_bond_premium": ebp, "turbulence": turb,
            "absorption_ratio": ar, "environmental_balance": env,
            "as_of": date.today().isoformat(), "compute_seconds": round(time.time() - t0, 1)}
