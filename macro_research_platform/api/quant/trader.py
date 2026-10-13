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

Speed: each deployment is evaluated in a light mode (returns and today's targets only), its result is cached on
disk per spec and engine version (survives restarts), and a book is served at once from the latest results while
stale deployments refresh in the background (several in parallel).
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from api.calculations import auto_backtest as ab
from api.quant import backtest, engine, robust, store

logger = logging.getLogger(__name__)
_cache: Dict[str, Any] = {}                 # per book: {"ts", "key", "data"}
_lock = threading.Lock()
TTL = 1800
DISK = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "quant" / "trader"
DEP_TTL = 6 * 3600                           # a deployment's result is refreshed at most every 6 hours (daily data)
WORKERS = 3                                  # deployments evaluated in parallel (sandbox runs are separate processes)
SHOW_POSITIONS = 12                          # per algo in the book payload; the rest are summarised
SHOW_EXPOSURE = 25
_refreshing: set = set()


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
    """Tickers of a code or library strategy, read from its literal header (never by running it). A
    TRADABLE_UNIVERSE strategy trades the stocks of that universe, not just its literal UNIVERSE list."""
    from api.quant import library, sandbox
    if spec.get("kind") == "library":
        entry = library.get(spec["library"])
        if not entry.get("code"):                            # portfolios and 13F strategies are server-computed
            return []
        head = sandbox.check(entry["code"])
    else:
        head = sandbox.check(spec.get("code") or "")
    return head["universe"] + (["__TRADABLE__"] if head.get("tradable") else [])


def eval_code_spec(spec: Dict[str, Any], light: bool = False) -> Dict[str, Any]:
    """Daily out-of-sample returns of a code strategy: library code runs in-process (trusted), user code
    only inside the sandbox. `light`: returns and today's targets only (what a paper book needs)."""
    from api.quant import codeserver, library, sandbox
    if spec.get("kind") == "library":
        entry = library.get(spec["library"])
        if not entry.get("code"):                            # portfolios and 13F strategies: the server's own result
            return library.result(spec["library"])
        return codeserver.evaluate_code(entry["code"], spec.get("costs"), trusted=True, light=light)
    return sandbox.run(spec["code"], spec.get("costs"), light=light)


# ── Per-deployment results: light, cached on disk, refreshed in the background ──
def _dep_key(dep: Dict[str, Any]) -> str:
    from api.quant.codelab import ENGINE_VERSION
    body = json.dumps({"spec": dep["spec"], "engine": ENGINE_VERSION}, sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()[:20]


def _compute(dep: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate one deployment (light) and store the result on disk."""
    spec = dep["spec"]
    if spec.get("kind") in ("code", "library"):
        raw = _raw_from_code(eval_code_spec(spec, light=True))
    else:
        res = backtest.run(spec, light=True)
        raw = {"daily_dates": res["daily_dates"], "daily_returns": list(map(float, res["daily_returns"])),
               "positions": [{"symbol": p["symbol"], "target_weight": p["target_weight"], "signal": p.get("signal")}
                             for p in res["positions"]], "currency": "USD"}
    _save_raw(dep, raw)
    return raw


def _raw_from_code(cres: Dict[str, Any]) -> Dict[str, Any]:
    return {"daily_dates": cres["dates"], "daily_returns": cres["returns"], "daily_benchmark": cres.get("benchmark"),
            "positions": [{"symbol": k, "target_weight": v, "signal": None} for k, v in (cres.get("weights_last") or {}).items()],
            "currency": ((cres.get("provenance") or {}).get("account_currency") or "USD").upper()}


def _save_raw(dep: Dict[str, Any], raw: Dict[str, Any]) -> None:
    try:
        DISK.mkdir(parents=True, exist_ok=True)
        f = DISK / f"{dep['id']}.json"
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps({"key": _dep_key(dep), "ts": time.time(), "raw": raw}, default=float))
        tmp.replace(f)
    except Exception as e:                                       # noqa: BLE001 — caching must never break the book
        logger.info("[quant-trader] could not cache deployment %s: %s", dep["id"], e)


def _cached(dep: Dict[str, Any]) -> Optional[Tuple[Dict[str, Any], float]]:
    """(raw result, age in seconds) from disk. A result computed by an older engine counts as stale (age = ∞) — still
    shown while the new one is computed, never thrown away first."""
    try:
        d = json.loads((DISK / f"{dep['id']}.json").read_text())
        age = time.time() - float(d["ts"]) if d.get("key") == _dep_key(dep) else float("inf")
        return d["raw"], age
    except (OSError, ValueError, KeyError):
        return None


def deployment_result(dep: Dict[str, Any], allow_stale: bool = True) -> Tuple[Dict[str, Any], bool]:
    """(raw result, stale?) — cached when possible; computed now only if nothing usable exists."""
    hit = _cached(dep)
    if hit and (allow_stale or hit[1] < DEP_TTL):
        return hit[0], hit[1] >= DEP_TTL
    return _compute(dep), False


def classify(spec: Dict[str, Any]) -> str:
    """Which trader a strategy belongs to — decided by what it reads and what it trades."""
    from api.quant.expr import FUNDAMENTALS
    if spec.get("kind") in ("code", "library"):
        from api.quant import library
        if spec.get("kind") == "library":
            entry = library.get(spec["library"])
            if entry.get("kind") == "13f":
                return "fundamental"                        # stock picks from institutions' disclosed holdings
            if not entry.get("code"):
                return "macro"                              # multi-strategy / multi-manager portfolios
        syms = code_universe(spec)
        if "__TRADABLE__" in syms:
            return "technical"                              # a stock universe chosen by the strategy from price/volume
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
    if spec_in.get("kind") in ("code", "library"):
        return _deploy_code(owner, spec_in, capital, strategy_id, book)       # capital is in the account currency
    if not 1_000 <= capital <= 1_000_000_000:
        raise engine.SpecError("Capital must be between $1,000 and $1bn.")
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
    ccy = ((res.get("provenance") or {}).get("account_currency") or "USD").upper()
    from api.quant import codeserver
    cap_usd = capital * float(codeserver.usd_per(ccy, [res["dates"][-1]]).iloc[-1])
    if not 1_000 <= cap_usd <= 1_000_000_000:
        raise engine.SpecError(f"Capital must be worth between $1,000 and $1bn (the account is in {ccy}: "
                               f"{capital:,.0f} {ccy} ≈ ${cap_usd:,.0f}).")
    m = res.get("metrics") or {}
    summary = {k: m.get(k) for k in ("cagr", "vol", "sharpe", "max_drawdown")}
    summary["period"] = {"start": res["dates"][0], "end": res["dates"][-1], "last_close": res["dates"][-1]}
    summary["currency"] = ccy
    natural = classify(spec)
    if book and book != natural:
        raise engine.SpecError(f"This strategy trades {BOOK_TRADES[natural]}, so it belongs in the {BOOK_LABEL[natural]} Quant Trader.")
    d = store.deploy(owner, spec["name"], spec, res["dates"][-1], float(capital), strategy_id, summary, natural)
    if d and res.get("returns"):
        _save_raw(d, _raw_from_code(res))                       # the trader page opens instantly with it
    invalidate()
    return d


def forget(deployment_id: int) -> None:
    """Drop a stopped deployment's cached result (the append-only daily record is kept as its history)."""
    try:
        (DISK / f"{int(deployment_id)}.json").unlink(missing_ok=True)
    except OSError:
        pass


def invalidate() -> None:
    with _lock:
        _cache.clear()


def _one(dep: Dict[str, Any], res: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    spec = dep["spec"]
    if res is None:
        res, _ = deployment_result(dep)
    ccy = res.get("currency") or "USD"
    dates, r = res["daily_dates"], np.asarray(res["daily_returns"], float)
    # The deployment's NAV is kept in its own account currency; the book adds deployments up in USD at as-of FX.
    if ccy != "USD":
        from api.quant import codeserver
        usd = codeserver.usd_per(ccy, dates).to_numpy(float)
        r_usd = (1 + r) * np.r_[1.0, usd[1:] / usd[:-1]] - 1
        k = int(np.searchsorted(np.asarray(dates), dep["deployed_at"], side="right")) - 1
        cap_usd = dep["capital"] * float(usd[max(k, 0)])            # capital converted at the deployment date
    else:
        r_usd, cap_usd = r, dep["capital"]
    live_mask = np.array([d > dep["deployed_at"] for d in dates])
    pre = r[~live_mask]
    live_dates, live, live_usd, revised, provisional = _frozen_live(dep, dates, r, r_usd, live_mask)
    cum = float(np.prod(1 + live) - 1) if live.size else 0.0
    nav = dep["capital"] * (1 + cum)
    nav_usd = cap_usd * float(np.prod(1 + live_usd)) if live_usd.size else cap_usd
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
    positions = sorted(({"symbol": p["symbol"], "weight": p["target_weight"], "usd": round(nav_usd * p["target_weight"], 2),
                         "signal": p["signal"]} for p in res["positions"] if p["target_weight"]),
                       key=lambda p: -abs(p["weight"]))
    return {"id": dep["id"], "name": dep["name"], "strategy_id": dep["strategy_id"], "owner": dep["owner"],
            "deployed_at": dep["deployed_at"], "capital": dep["capital"], "nav": round(nav, 2), "currency": ccy,
            "capital_usd": round(cap_usd, 2), "nav_usd": round(nav_usd, 2),
            "live_days": int(live.size), "live_return": round(cum, 4),
            "record": {"frozen_days": int(live.size) - (1 if provisional else 0), "provisional": provisional,
                       "revised_days": revised},
            "live_max_drawdown": round(float((eq / peak - 1).min()), 4) if eq.size else None,
            "live_sharpe": robust.sharpe(live, live_dates) if live.size >= 20 else None,
            "expected_range": band, "status": status, "backtest": dep.get("backtest"),
            "rebalance": spec.get("rebalance"), "universe": spec.get("universe"), "book": book_of(dep),
            "positions": positions, "curve": [{"date": d, "nav": round(dep["capital"] * float(v), 2)}
                                               for d, v in zip(live_dates, eq)][-500:],
            "_live": dict(zip(live_dates, live_usd.tolist()))}


FREEZE = True


def _frozen_live(dep: Dict[str, Any], dates: List[str], r: np.ndarray, r_usd: np.ndarray, live_mask: np.ndarray):
    """The live record is append-only: every session after deployment except the latest (which the data source can
    still revise) is written once and from then on read back, never recomputed — so a data revision or an engine
    change cannot rewrite past paper results. Returns (dates, returns, USD returns, revised days, provisional date)."""
    idx = np.where(live_mask)[0]
    if not FREEZE or not len(idx):
        return [dates[i] for i in idx], r[idx], r_usd[idx], 0, None
    frozen = store.live_returns(dep["id"])
    final = idx[:-1]                                             # the last session stays provisional
    new = [(dates[i], float(r[i]), float(r_usd[i])) for i in final if dates[i] not in frozen]
    if new:
        store.append_live(dep["id"], new)
        frozen.update({d: (a, b) for d, a, b in new})
    revised = sum(1 for i in final if dates[i] in frozen and abs(frozen[dates[i]][0] - float(r[i])) > 1e-6)
    out_d = sorted(frozen)
    out_r = [frozen[d][0] for d in out_d]
    out_u = [frozen[d][1] for d in out_d]
    prov = dates[idx[-1]] if dates[idx[-1]] not in frozen else None
    if prov:
        out_d.append(prov)
        out_r.append(float(r[idx[-1]]))
        out_u.append(float(r_usd[idx[-1]]))
    return out_d, np.asarray(out_r, float), np.asarray(out_u, float), revised, prov


def _alerts(rows: List[Dict[str, Any]], errors: List[Dict[str, Any]], which: str) -> None:
    """Paper-trading alerts into the platform's alert panel (once per algo, kind and day)."""
    for x in rows:
        if x["status"] == "below range":
            store.raise_alert(x["id"], "below_range", "High",
                              f"{BOOK_LABEL[which]} algo “{x['name']}” is below its expected range: {x['live_return']:+.1%} "
                              f"after {x['live_days']} sessions, worse than 95% of its backtest paths — review it.")
    for e in errors:
        store.raise_alert(e["id"], "failed", "Medium", f"{BOOK_LABEL[which]} algo “{e['name']}” could not be updated: {e['error'][:200]}")


def _sector_of(symbols: List[str]) -> Dict[str, str]:
    """Sector from the tradable universe (no network); funds and options get their own buckets."""
    from api.quant import instruments
    rows = instruments._universe_rows()
    out = {}
    for sym in symbols:
        r = rows.get(sym) or rows.get(sym.replace("-", "."))
        if r and r.get("sector"):
            out[sym] = r["sector"]
        elif re.match(r"^[A-Z]{1,5}_[PC]", sym):
            out[sym] = "Options"
        else:
            out[sym] = "Funds & other"
    return out


def _refresh(which: str, deps: List[Dict[str, Any]]) -> None:
    """Background: recompute stale deployments (in parallel), then rebuild the book."""
    try:
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            list(ex.map(lambda d: _safe(_compute, d), deps))
        _build(which)
    finally:
        with _lock:
            _refreshing.discard(which)


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception as e:                                       # noqa: BLE001
        logger.warning("[quant-trader] %s failed: %s", getattr(fn, "__name__", "job"), e)
        return None


def book(force: bool = False, which: Optional[str] = None) -> Dict[str, Any]:
    """One trader's book: the macro, fundamental or technical deployments (never mixed). Served at once from the latest
    results; stale deployments refresh in the background (`refreshing` says so, the page polls)."""
    if which not in BOOKS:
        raise engine.SpecError("Choose the macro, fundamental or technical trader.")
    deps = [d for d in store.list_deployments(active_only=True) if book_of(d) == which]
    key = (which,) + tuple((d["id"], d["deployed_at"]) for d in deps)
    with _lock:
        hit = _cache.get(which)
        if not force and hit and hit["key"] == key and time.time() - hit["ts"] < TTL:
            return {**hit["data"], "refreshing": which in _refreshing}
    ages = {d["id"]: (_cached(d) or (None, None))[1] for d in deps}
    todo = [d for d in deps if ages[d["id"]] is None or ages[d["id"]] >= DEP_TTL or force]
    ready = [d for d in deps if ages[d["id"]] is not None]
    out = _build(which, ready, key if len(ready) == len(deps) else None)
    # algos never computed yet are prepared in the background too: the page never waits for a full re-run
    out["pending"] = [{"id": d["id"], "name": d["name"]} for d in deps if ages[d["id"]] is None]
    if todo:
        with _lock:
            start = which not in _refreshing
            _refreshing.add(which)
        if start:
            threading.Thread(target=_refresh, args=(which, todo), daemon=True, name=f"trader-{which}").start()
    return {**out, "refreshing": bool(todo)}


def _build(which: str, deps: Optional[List[Dict[str, Any]]] = None, key: Optional[tuple] = None) -> Dict[str, Any]:
    if deps is None:
        deps = [d for d in store.list_deployments(active_only=True) if book_of(d) == which]
        key = (which,) + tuple((d["id"], d["deployed_at"]) for d in deps)
    rows, errors = [], []
    for d in deps:
        try:
            hit = _cached(d)
            rows.append(_one(d, hit[0] if hit else None))
        except Exception as e:                                   # one broken strategy must not hide the book
            logger.warning("[quant-trader] deployment %s failed: %s", d["id"], e)
            errors.append({"id": d["id"], "name": d["name"], "error": str(e)[:200]})
    try:
        _alerts(rows, errors, which)
    except Exception as e:                                       # noqa: BLE001 — alerts never break the book
        logger.info("[quant-trader] alerts: %s", e)
    capital = sum(r["capital_usd"] for r in rows)                # in USD: deployments may keep other currencies
    nav = sum(r["nav_usd"] for r in rows)
    # Book NAV series: each deployment's NAV carried flat before it went live.
    all_dates = sorted({d for r in rows for d in r["_live"]})
    curve = []
    if all_dates:
        navs = {r["id"]: r["capital_usd"] for r in rows}
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
        # the page shows each algo's largest holdings; the rest are summarised (count and weight)
        r["positions_count"] = len(r["positions"])
        rest = r["positions"][SHOW_POSITIONS:]
        r["positions_other"] = {"count": len(rest), "weight": round(sum(p["weight"] for p in rest), 4)} if rest else None
        r["positions"] = r["positions"][:SHOW_POSITIONS]
    gross = sum(abs(v) for v in exposure.values())
    ranked = sorted(((k, v) for k, v in exposure.items() if abs(v) > 0.5), key=lambda x: -abs(x[1]))
    sectors = _sector_of([k for k, _ in ranked])
    by_sector: Dict[str, float] = {}
    for k, v in ranked:
        by_sector[sectors[k]] = by_sector.get(sectors[k], 0.0) + v
    w = (lambda v: round(v / nav, 4) if nav else None)
    rest = ranked[SHOW_EXPOSURE:]
    out = {"deployments": rows, "errors": errors, "capital": round(capital, 2), "nav": round(nav, 2),
           "return": round(nav / capital - 1, 4) if capital else None, "curve": curve[-750:],
           "exposure": [{"symbol": k, "usd": round(v, 2), "weight": w(v), "sector": sectors[k]} for k, v in ranked[:SHOW_EXPOSURE]],
           "exposure_other": {"count": len(rest), "usd": round(sum(v for _, v in rest), 2), "weight": w(sum(v for _, v in rest))} if rest else None,
           "positions_total": len(ranked),
           "by_sector": [{"sector": k, "usd": round(v, 2), "weight": w(v)} for k, v in sorted(by_sector.items(), key=lambda x: -abs(x[1]))],
           "gross_exposure": round(gross / nav, 3) if nav else None,
           "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "book": which}
    if key is not None:                                        # cache only a complete book
        with _lock:
            _cache[which] = {"ts": time.time(), "key": key, "data": out}
    return out
