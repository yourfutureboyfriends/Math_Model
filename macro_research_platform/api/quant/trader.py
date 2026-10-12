"""
Quant Trader — a PAPER book that runs the systematic strategies deployed from the Quant Lab.

Each deployment freezes the strategy's spec and the date it went live. Its live record is
the strategy's point-in-time simulation (weights from data known at each close, traded at
the next bar, costs charged) restricted to days AFTER deployment — so nothing in it was
fitted with hindsight. The live return is compared with the range the pre-deployment
backtest implies for the same horizon (block bootstrap), which flags early when a
strategy behaves out of character.

The book is the deployments' capital combined; positions are today's target weights × the
deployment's current capital. Never places real orders.
"""
from __future__ import annotations

import logging
import math
import re
import threading
import time
from typing import Any, Dict, List, Optional

import numpy as np

from api.calculations import auto_backtest as ab
from api.quant import backtest, engine, robust, store

logger = logging.getLogger(__name__)
_cache: Dict[str, Any] = {}                 # per book: {"ts", "key", "data"}
_lock = threading.Lock()
TTL = 1800


# ── Two books, never mixed ───────────────────────────────────────────────────
# macro       — asset-class strategies: ETFs of indices, bonds, credit, commodities, currencies, sectors, countries
# fundamental — single-stock strategies, and anything that reads company fundamentals (value, quality …)
BOOKS = ("macro", "fundamental")
MACRO_PRESETS = {"cross_asset", "us_sectors", "country_etfs", "bonds_credit", "real_assets", "factor_etfs", "gem", "gtaa5"}
FUNDAMENTAL_PRESETS = {"us_megacaps"}


def classify(spec: Dict[str, Any]) -> str:
    """Which trader a strategy belongs to — decided by what it trades and what it reads."""
    from api.quant.expr import FUNDAMENTALS
    text = " ".join(str(spec.get(k) or "") for k in ("signal", "filter", "weighting", "exit"))
    if any(re.search(rf"\b{re.escape(f)}\b", text) for f in FUNDAMENTALS):
        return "fundamental"
    uni = spec.get("universe") or {}
    preset = uni.get("preset")
    if preset in FUNDAMENTAL_PRESETS:
        return "fundamental"
    if preset in MACRO_PRESETS:
        return "macro"
    syms = [str(s).upper() for s in (uni.get("symbols") or [])]
    if not syms:
        return "macro"
    stocks = 0
    for sym in syms[:40]:
        if any(ch in sym for ch in "^=") or sym.endswith("-USD"):
            continue                                            # index, FX, future, crypto
        try:
            from api.marketdata.core import _info
            if (_info(sym).get("quoteType") or "").upper() == "EQUITY":
                stocks += 1
        except Exception:
            continue
    return "fundamental" if stocks > len(syms[:40]) / 2 else "macro"


def book_of(dep: Dict[str, Any]) -> str:
    return dep.get("book") if dep.get("book") in BOOKS else classify(dep.get("spec") or {})


def deploy(owner: str, spec_in: Dict[str, Any], capital: float, strategy_id: Optional[int] = None,
           book: Optional[str] = None) -> Dict[str, Any]:
    if not 1_000 <= capital <= 1_000_000_000:
        raise engine.SpecError("Capital must be between $1,000 and $1bn.")
    res = backtest.run(spec_in, light=True)
    spec = res["spec"]
    m = res["metrics"]
    summary = {k: m.get(k) for k in ("cagr", "vol", "sharpe", "max_drawdown")}
    summary["period"] = res["period"]
    natural = classify(spec)
    if book and book != natural:                                # the two traders are kept strictly apart
        raise engine.SpecError(f"This strategy trades {'single stocks / company fundamentals' if natural == 'fundamental' else 'asset classes'}, "
                               f"so it belongs in the {'Fundamental' if natural == 'fundamental' else 'Macro'} Quant Trader.")
    # Live from the next session after the latest close in the data.
    d = store.deploy(owner, spec["name"], spec, res["period"]["last_close"], float(capital), strategy_id, summary, natural)
    invalidate()
    return d


def invalidate() -> None:
    with _lock:
        _cache.clear()


def _one(dep: Dict[str, Any]) -> Dict[str, Any]:
    spec = dep["spec"]
    res = backtest.run(spec, light=True)
    dates, r = res["daily_dates"], np.asarray(res["daily_returns"], float)
    live_mask = np.array([d > dep["deployed_at"] for d in dates])
    pre, live = r[~live_mask], r[live_mask]
    live_dates = [d for d, k in zip(dates, live_mask) if k]
    cum = float(np.prod(1 + live) - 1) if live.size else 0.0
    nav = dep["capital"] * (1 + cum)
    band = ab.bootstrap_range(pre, int(live.size)) if live.size >= 5 else {}
    status = "on track"
    if band and live.size >= 20:
        if cum < band.get("p5", -1):
            status = "below range"
        elif cum > band.get("p95", 1):
            status = "above range"
    elif live.size < 20:
        status = "too early"
    eq = np.cumprod(1 + live) if live.size else np.array([])
    peak = np.maximum.accumulate(eq) if eq.size else eq
    positions = [{"symbol": p["symbol"], "weight": p["target_weight"], "usd": round(nav * p["target_weight"], 2),
                  "signal": p["signal"]} for p in res["positions"] if p["target_weight"]]
    return {"id": dep["id"], "name": dep["name"], "strategy_id": dep["strategy_id"], "owner": dep["owner"],
            "deployed_at": dep["deployed_at"], "capital": dep["capital"], "nav": round(nav, 2),
            "live_days": int(live.size), "live_return": round(cum, 4),
            "live_max_drawdown": round(float((eq / peak - 1).min()), 4) if eq.size else None,
            "live_sharpe": robust.sharpe(live) if live.size >= 20 else None,
            "expected_range": band, "status": status, "backtest": dep.get("backtest"),
            "rebalance": spec.get("rebalance"), "universe": spec.get("universe"), "book": book_of(dep),
            "positions": positions, "curve": [{"date": d, "nav": round(dep["capital"] * float(v), 2)}
                                               for d, v in zip(live_dates, eq)][-500:],
            "_live": dict(zip(live_dates, live.tolist()))}


def book(force: bool = False, which: Optional[str] = None) -> Dict[str, Any]:
    """One trader's book: the macro or the fundamental deployments (never both together)."""
    if which not in BOOKS:
        raise engine.SpecError("Choose the macro or the fundamental trader.")
    deps = [d for d in store.list_deployments(active_only=True) if book_of(d) == which]
    key = (which,) + tuple((d["id"], d["deployed_at"]) for d in deps)
    with _lock:
        hit = _cache.get(which)
        if not force and hit and hit["key"] == key and time.time() - hit["ts"] < TTL:
            return hit["data"]
    rows, errors = [], []
    for d in deps:
        try:
            rows.append(_one(d))
        except Exception as e:                                   # one broken strategy must not hide the book
            logger.warning("[quant-trader] deployment %s failed: %s", d["id"], e)
            errors.append({"id": d["id"], "name": d["name"], "error": str(e)[:200]})
    capital = sum(r["capital"] for r in rows)
    nav = sum(r["nav"] for r in rows)
    # Book NAV series: each deployment's NAV carried flat before it went live.
    all_dates = sorted({d for r in rows for d in r["_live"]})
    curve = []
    if all_dates:
        navs = {r["id"]: r["capital"] for r in rows}
        for d in all_dates:
            for r in rows:
                x = r["_live"].get(d)
                if x is not None:
                    navs[r["id"]] *= (1 + x)
            curve.append({"date": d, "nav": round(sum(navs.values()), 2)})
    exposure: Dict[str, float] = {}
    for r in rows:
        for p in r["positions"]:
            exposure[p["symbol"]] = exposure.get(p["symbol"], 0.0) + p["usd"]
        r.pop("_live", None)
    gross = sum(abs(v) for v in exposure.values())
    out = {"deployments": rows, "errors": errors, "capital": round(capital, 2), "nav": round(nav, 2),
           "return": round(nav / capital - 1, 4) if capital else None, "curve": curve[-750:],
           "exposure": sorted([{"symbol": k, "usd": round(v, 2), "weight": round(v / nav, 4) if nav else None}
                               for k, v in exposure.items() if abs(v) > 0.5], key=lambda x: -abs(x["usd"])),
           "gross_exposure": round(gross / nav, 3) if nav else None,
           "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "book": which}
    with _lock:
        _cache[which] = {"ts": time.time(), "key": key, "data": out}
    return out
