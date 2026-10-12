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


# ── Three books, never mixed ─────────────────────────────────────────────────
# macro       — asset-class strategies: ETFs of indices, bonds, credit, commodities, currencies, sectors, countries
#               (trend, momentum and breakout rules on those are still macro: what is traded decides)
# fundamental — single-stock strategies that read company fundamentals (value, quality, profitability …)
# technical   — single-stock strategies driven only by price and volume (momentum, reversal, breakouts, low vol)
BOOKS = ("macro", "fundamental", "technical")
BOOK_LABEL = {"macro": "Macro", "fundamental": "Fundamental", "technical": "Technical"}
BOOK_TRADES = {"macro": "asset classes", "fundamental": "stocks using company fundamentals",
               "technical": "stocks using price and volume only"}
MACRO_PRESETS = {"cross_asset", "us_sectors", "country_etfs", "bonds_credit", "real_assets", "factor_etfs", "gem", "gtaa5"}
STOCK_PRESETS = {"us_megacaps"}


def _trades_stocks(spec: Dict[str, Any]) -> bool:
    uni = spec.get("universe") or {}
    preset = uni.get("preset")
    if preset in STOCK_PRESETS:
        return True
    if preset in MACRO_PRESETS:
        return False
    syms = [str(s).upper() for s in (uni.get("symbols") or [])][:40]
    if not syms:
        return False
    stocks = 0
    for sym in syms:
        if any(ch in sym for ch in "^=") or sym.endswith("-USD"):
            continue                                            # index, FX, future, crypto
        try:
            from api.marketdata.core import _info
            if (_info(sym).get("quoteType") or "").upper() == "EQUITY":
                stocks += 1
        except Exception:
            continue
    return stocks > len(syms) / 2


def code_universe(spec: Dict[str, Any]) -> List[str]:
    """Tickers of a code or library strategy, read from its literal UNIVERSE (never by running it)."""
    from api.quant import library, sandbox
    if spec.get("kind") == "library":
        if spec.get("library") == library.PORTFOLIO["id"]:
            return []
        return sandbox.check(library.get(spec["library"])["code"])["universe"]
    return sandbox.check(spec.get("code") or "")["universe"]


def eval_code_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Daily out-of-sample returns of a code strategy: library code runs in-process (trusted), user code
    only inside the sandbox."""
    from api.quant import codeserver, library, sandbox
    if spec.get("kind") == "library":
        if spec["library"] == library.PORTFOLIO["id"]:
            return library.result(spec["library"])
        return codeserver.evaluate_code(library.get(spec["library"])["code"], spec.get("costs"), trusted=True)
    return sandbox.run(spec["code"], spec.get("costs"))


def classify(spec: Dict[str, Any]) -> str:
    """Which trader a strategy belongs to — decided by what it reads and what it trades."""
    from api.quant.expr import FUNDAMENTALS
    if spec.get("kind") in ("code", "library"):
        syms = code_universe(spec)
        return "technical" if syms and _trades_stocks({"universe": {"symbols": syms}}) else "macro"
    text = " ".join(str(spec.get(k) or "") for k in ("signal", "filter", "weighting", "exit"))
    if any(re.search(rf"\b{re.escape(f)}\b", text) for f in FUNDAMENTALS):
        return "fundamental"
    return "technical" if _trades_stocks(spec) else "macro"


def book_of(dep: Dict[str, Any]) -> str:
    # always re-derived from the frozen spec, so deployments made before a book existed land in the right one
    return classify(dep.get("spec") or {})


def deploy(owner: str, spec_in: Dict[str, Any], capital: float, strategy_id: Optional[int] = None,
           book: Optional[str] = None) -> Dict[str, Any]:
    if not 1_000 <= capital <= 1_000_000_000:
        raise engine.SpecError("Capital must be between $1,000 and $1bn.")
    if spec_in.get("kind") in ("code", "library"):
        return _deploy_code(owner, spec_in, capital, strategy_id, book)
    res = backtest.run(spec_in, light=True)
    spec = res["spec"]
    m = res["metrics"]
    summary = {k: m.get(k) for k in ("cagr", "vol", "sharpe", "max_drawdown")}
    summary["period"] = res["period"]
    natural = classify(spec)
    if book and book != natural:                                # the traders are kept strictly apart
        raise engine.SpecError(f"This strategy trades {BOOK_TRADES[natural]}, so it belongs in the {BOOK_LABEL[natural]} Quant Trader.")
    # Live from the next session after the latest close in the data.
    d = store.deploy(owner, spec["name"], spec, res["period"]["last_close"], float(capital), strategy_id, summary, natural)
    invalidate()
    return d


def _deploy_code(owner: str, spec_in: Dict[str, Any], capital: float, strategy_id: Optional[int],
                 book: Optional[str]) -> Dict[str, Any]:
    from api.quant import library, sandbox
    kind = spec_in.get("kind")
    spec = {"kind": kind, "name": str(spec_in.get("name") or "Code strategy")[:80]}
    if kind == "library":
        lib = library.get(str(spec_in.get("library")))
        spec.update(library=lib["id"], name=str(spec_in.get("name") or lib["name"])[:80])
    else:
        try:
            sandbox.check(spec_in.get("code") or "")
        except sandbox.SandboxError as e:
            raise engine.SpecError(str(e))
        spec["code"] = spec_in["code"]
    if isinstance(spec_in.get("costs"), dict):
        spec["costs"] = {k: float(v) for k, v in spec_in["costs"].items() if isinstance(v, (int, float))}
    try:
        res = eval_code_spec(spec)
    except sandbox.SandboxError as e:
        raise engine.SpecError(str(e))
    m = res.get("metrics") or {}
    summary = {k: m.get(k) for k in ("cagr", "vol", "sharpe", "max_drawdown")}
    summary["period"] = {"start": res["dates"][0], "end": res["dates"][-1], "last_close": res["dates"][-1]}
    natural = classify(spec)
    if book and book != natural:
        raise engine.SpecError(f"This strategy trades {BOOK_TRADES[natural]}, so it belongs in the {BOOK_LABEL[natural]} Quant Trader.")
    d = store.deploy(owner, spec["name"], spec, res["dates"][-1], float(capital), strategy_id, summary, natural)
    invalidate()
    return d


def invalidate() -> None:
    with _lock:
        _cache.clear()


def _one(dep: Dict[str, Any]) -> Dict[str, Any]:
    spec = dep["spec"]
    if spec.get("kind") in ("code", "library"):
        cres = eval_code_spec(spec)
        res = {"daily_dates": cres["dates"], "daily_returns": cres["returns"],
               "positions": [{"symbol": k, "target_weight": v, "signal": None} for k, v in (cres.get("weights_last") or {}).items()]}
    else:
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
            "live_sharpe": robust.sharpe(live, live_dates) if live.size >= 20 else None,
            "expected_range": band, "status": status, "backtest": dep.get("backtest"),
            "rebalance": spec.get("rebalance"), "universe": spec.get("universe"), "book": book_of(dep),
            "positions": positions, "curve": [{"date": d, "nav": round(dep["capital"] * float(v), 2)}
                                               for d, v in zip(live_dates, eq)][-500:],
            "_live": dict(zip(live_dates, live.tolist()))}


def book(force: bool = False, which: Optional[str] = None) -> Dict[str, Any]:
    """One trader's book: the macro, fundamental or technical deployments (never mixed)."""
    if which not in BOOKS:
        raise engine.SpecError("Choose the macro, fundamental or technical trader.")
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
