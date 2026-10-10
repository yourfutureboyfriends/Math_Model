"""
Systematic macro model — orchestration, persistence and order generation.

run_model(params) produces one reproducible model run: the current economic state (factors,
regime probabilities, recession probability), expected returns, the strategic and tactical
portfolios with risk contributions, and the walk-forward backtest. Every run is stored
(model_runs) with its parameters, so any allocation can be traced back to the exact model
state that produced it.

Orders: the model manages its own sleeve (its ten ETFs, book "Macro Model"); other holdings
are never touched.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from api.model.core import ModelParams, decide, risk_contributions
from api.model.data import ASSETS, MACRO_SERIES, load_model_data

logger = logging.getLogger(__name__)

MODEL_VERSION = "1.0"
MODEL_BOOK = "Macro Model"
_CACHE: Dict[str, tuple] = {}
_TTL = 6 * 3600
# A cold run takes minutes (FRED + Yahoo history, then the fit and the backtest). The model
# is monthly, so the last result on disk is served at once after a restart (flagged) while
# one background task recomputes it.
_SNAPSHOT_DIR = __import__("pathlib").Path(__file__).resolve().parents[2] / "data" / "processed" / "live"
_SNAPSHOT_MAX_AGE = 3 * 86400
_REFRESHING: Dict[str, "asyncio.Task"] = {}


def _snapshot_path(key: str):
    return _SNAPSHOT_DIR / f"model_{key}.json"


def _save_snapshot(key: str, result: Dict[str, Any]) -> None:
    try:
        _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _snapshot_path(key).with_suffix(".tmp")
        tmp.write_text(json.dumps({"ts": time.time(), "result": result}, default=str))
        tmp.replace(_snapshot_path(key))
    except Exception as e:
        logger.debug("[model] snapshot save failed: %s", e)


def _load_snapshot(key: str) -> Optional[Dict[str, Any]]:
    try:
        raw = json.loads(_snapshot_path(key).read_text())
    except Exception:
        return None
    if time.time() - float(raw.get("ts", 0)) > _SNAPSHOT_MAX_AGE:
        return None
    out = dict(raw["result"])
    out["snapshot"] = {"saved_at": datetime.fromtimestamp(raw["ts"], timezone.utc).strftime("%Y-%m-%dT%H:%M+00:00"),
                       "note": "Last computed run, served while the model recomputes after a restart."}
    return out


def _blocks() -> Dict[str, str]:
    return {k: v[0] for k, v in MACRO_SERIES.items()}


def _env() -> Dict[str, str]:
    return {k: v[2] for k, v in ASSETS.items()}


def params_hash(p: ModelParams) -> str:
    return hashlib.sha256(json.dumps(p.__dict__, sort_keys=True).encode()).hexdigest()[:12]


# ── Persistence ──────────────────────────────────────────────────────────────
def _conn():
    from api.portfolio_store import _conn as pconn
    c = pconn()
    c.execute("""CREATE TABLE IF NOT EXISTS model_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, version TEXT, params_hash TEXT,
        params TEXT, as_of TEXT, regime_probs TEXT, strategic TEXT, tactical TEXT,
        backtest_summary TEXT, user TEXT)""")
    return c


def save_run(result: Dict[str, Any], user: str) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO model_runs (ts, version, params_hash, params, as_of, regime_probs, strategic, tactical, "
            "backtest_summary, user) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (result["run_at"], MODEL_VERSION, result["params_hash"], json.dumps(result["params"]),
             result["as_of"], json.dumps(result["regime"]["probabilities"]),
             json.dumps(result["portfolios"]["strategic"]["weights"]), json.dumps(result["portfolios"]["tactical"]["weights"]),
             json.dumps({k: result["backtest"].get(k) for k in ("start", "end", "stats", "tactical_vs_strategic")}), user))
        c.commit()
        return int(cur.lastrowid)


def list_runs(limit: int = 50):
    with _conn() as c:
        rows = c.execute("SELECT id, ts, version, params_hash, as_of, regime_probs, strategic, tactical, user "
                         "FROM model_runs ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("regime_probs", "strategic", "tactical"):
            d[k] = json.loads(d[k]) if d[k] else None
        out.append(d)
    return out


# ── Run ──────────────────────────────────────────────────────────────────────
def _portfolio_block(assets, w, cov, mu_annual) -> Dict[str, Any]:
    rc = risk_contributions(w, cov)
    vol = math.sqrt(max(w @ cov @ w, 0)) * math.sqrt(12)
    return {
        "weights": {a: round(float(x), 4) for a, x in zip(assets, w)},
        "cash": round(float(1 - w.sum()), 4), "gross": round(float(w.sum()), 4),
        "expected_vol": round(vol, 4),
        "expected_excess_return": round(float(w @ mu_annual), 4),
        "risk_contributions": {a: round(float(x), 4) for a, x in zip(assets, rc)},
        "etfs": {a: ASSETS[a][1] for a in assets},
    }


async def run_model(params: Optional[Dict] = None, user: str = "system", persist: bool = True,
                    force: bool = False) -> Dict[str, Any]:
    p = ModelParams.from_dict(params)
    key = params_hash(p)
    hit = _CACHE.get(key)
    if not hit and not force:
        snap = _load_snapshot(key)
        if snap:
            t = _REFRESHING.get(key)
            if t is None or t.done():
                _REFRESHING[key] = asyncio.get_running_loop().create_task(
                    run_model(params, user=user, persist=persist, force=True))
            return snap
    if hit and not force and time.time() - hit[0] < _TTL:
        cached = hit[1]
        if persist and cached.get("available") and not cached.get("run_id"):
            try:   # computed by a preview without saving: record it before anything cites it
                cached["run_id"] = await asyncio.to_thread(save_run, cached, user)
            except Exception as e:
                logger.warning("[model] could not persist run: %s", e)
        return cached

    panel, rets = await load_model_data()
    as_of = rets.index[-1]
    d = await asyncio.to_thread(decide, panel, rets, _blocks(), _env(), as_of, p)
    if d is None:
        return {"available": False, "reason": "insufficient data to run the model"}
    from api.model.backtest import run_backtest
    bt = await asyncio.to_thread(run_backtest, panel, rets, _blocks(), _env(), p)

    # Markov-switching recession probability on the growth factor (Hamilton, 1989) — a
    # diagnostic shown alongside, not an input to the allocation.
    ms = await asyncio.to_thread(_markov_switching, d.growth)
    mu_ann = d.exp_bl * 12
    g, i = d.growth.dropna(), d.inflation.dropna()
    result = {
        "available": True, "version": MODEL_VERSION,
        "run_at": datetime.now(timezone.utc).isoformat(), "as_of": as_of.strftime("%Y-%m"),
        "params": p.__dict__, "params_hash": key,
        "state": {
            "growth_factor": round(float(g.iloc[-1]), 3), "growth_change_3m": round(float(g.iloc[-1] - g.iloc[-4]), 3),
            "inflation_factor": round(float(i.iloc[-1]), 3), "inflation_change_3m": round(float(i.iloc[-1] - i.iloc[-4]), 3),
            "factor_as_of": g.index[-1].strftime("%Y-%m"),
            "loadings": d.loadings,
            "history": [{"month": m.strftime("%Y-%m"), "growth": round(float(a), 3), "inflation": round(float(b), 3)}
                        for m, a, b in zip(g.index[-120:], g.iloc[-120:], i.reindex(g.index).iloc[-120:])],
        },
        "regime": {
            "probabilities": {k: round(v, 4) for k, v in d.regime_probs.items()},
            "most_likely": max(d.regime_probs, key=d.regime_probs.get),
            "p_growth_rising": round(d.p_growth_up["probability"], 4),
            "p_inflation_rising": round(d.p_inflation_up["probability"], 4),
            "base_rates": {"growth_rising": round(d.p_growth_up["base_rate"], 3),
                           "inflation_rising": round(d.p_inflation_up["base_rate"], 3)},
            "independence_assumption": True,
            "markov_switching": ms,
            "observations_per_regime": d.regime_counts,
        },
        "expected_returns": {
            a: {"model": round(float(m) * 12, 4), "posterior": round(float(b) * 12, 4),
                "prior_implied": round(float(pr) * 12, 4),
                "by_regime": {q: round(float(d.cond_means.loc[a, q]) * 12, 4) for q in d.cond_means.columns}}
            for a, m, b, pr in zip(d.assets, d.exp_model, d.exp_bl,
                                   p.risk_aversion * d.cov @ d.prior)
        },
        "portfolios": {
            "strategic": _portfolio_block(d.assets, d.strategic, d.cov, mu_ann),
            "tactical": _portfolio_block(d.assets, d.weights, d.cov, mu_ann),
        },
        "backtest": bt,
        "methodology": {
            "factors": "Diffusion-index growth and inflation factors (Stock & Watson, 2002): first principal "
                       "component of 9 growth and 8 inflation series, each lagged to its publication date.",
            "regimes": "Logistic models of next month's 3-month factor direction; four growth × inflation regime "
                       "probabilities as their product. Markov-switching model (Hamilton, 1989) shown as a diagnostic.",
            "expected_returns": "Asset excess returns by realised regime since 1985, shrunk toward each asset's mean, "
                                "weighted by the regime probabilities.",
            "portfolio": "Black–Litterman (prior = environment-balanced portfolio, views = regime-conditional expected "
                         "returns), mean–variance with a volatility target, long-only, per-asset cap. The strategic "
                         "portfolio is the prior alone, scaled to the target.",
            "limitations": ["FRED serves revised data, not first-release vintages (mild look-ahead in the macro inputs).",
                            "Regime probabilities assume growth and inflation directions are independent.",
                            "Estimation uses mutual-fund proxies; trading uses ETFs with shorter histories.",
                            "Gold history starts in 2000 and commodities in 2002."],
        },
    }
    _CACHE[key] = (time.time(), result)
    if result.get("available"):
        await asyncio.to_thread(_save_snapshot, key, result)
    if persist:
        try:
            result["run_id"] = await asyncio.to_thread(save_run, result, user)
        except Exception as e:
            logger.warning("[model] could not persist run: %s", e)
    return result


def _markov_switching(growth: pd.Series) -> Dict[str, Any]:
    try:
        import warnings
        from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression
        y = growth.dropna().iloc[-480:].reset_index(drop=True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = MarkovRegression(y, k_regimes=2, switching_variance=True).fit(disp=False)
        means = [float(res.params[f"const[{k}]"]) for k in range(2)]
        low = int(np.argmin(means))
        filt = np.asarray(res.filtered_marginal_probabilities)
        p_low = float(filt[-1, low])
        trans = np.asarray(res.regime_transition)
        stay_low = float(trans[low, low, 0]) if trans.ndim == 3 else float(trans[low, low])
        return {"p_contraction_regime": round(p_low, 4), "regime_means": [round(m, 3) for m in means],
                "expected_duration_months": round(1 / (1 - stay_low), 1) if stay_low and stay_low < 1 else None,
                "method": "2-state Markov-switching mean/variance on the growth factor (filtered probability)"}
    except Exception as e:
        return {"available": False, "reason": str(e)[:120]}


# ── Orders ───────────────────────────────────────────────────────────────────
async def model_orders(result: Dict[str, Any], which: str, sleeve_capital: Optional[float]) -> Dict[str, Any]:
    """Orders that move the model sleeve (its ETFs only) to the chosen portfolio."""
    from api import fund_store, portfolio_store
    from api.calculations.rebalance import rebalance_orders
    from api.handlers.market_handler import _fetch_dated_closes_literal
    port = result["portfolios"][which]
    etf_w: Dict[str, float] = {}
    for a, w in port["weights"].items():
        if w > 0:
            etf_w[port["etfs"][a]] = etf_w.get(port["etfs"][a], 0.0) + w
    universe = {v[1] for v in ASSETS.values()}
    positions = await asyncio.to_thread(portfolio_store.list_positions, None)
    syms = sorted(universe | {str(p["symbol"]).upper() for p in positions})
    closes = await asyncio.gather(*[_fetch_dated_closes_literal(s) for s in syms])
    prices = {s: c[max(c)] for s, c in zip(syms, closes) if c}
    # The sleeve is the "Macro Model" book only: the same ETF held in another (discretionary)
    # book is not the model's to trade.
    current: Dict[str, float] = {}
    other_mv = 0.0
    other_by_sym: Dict[str, float] = {}
    for pos in positions:
        s = str(pos["symbol"]).upper()
        if pos.get("book") == MODEL_BOOK:
            current[s] = current.get(s, 0.0) + float(pos["quantity"])
        else:
            mv = abs(float(pos["quantity"]) * float(prices.get(s) or pos.get("avg_cost") or 0))
            other_mv += mv
            other_by_sym[s] = other_by_sym.get(s, 0.0) + mv
    settings = await asyncio.to_thread(fund_store.get_settings)
    nav = float(settings.get("capital") or 0)
    basis = "given"
    if sleeve_capital is None:
        # Default: fund NAV not already deployed in other books.
        sleeve_capital = max(0.0, nav - other_mv)
        basis = "fund capital less holdings in other books"
    # Respect the fund's hard single-name limit (pre-trade compliance would BLOCK above it):
    # the position in each ETF across ALL books stays below it; the excess is held as cash.
    from api.calculations.limits import merge_limits
    limits = merge_limits(await asyncio.to_thread(fund_store.get_limit_overrides))
    hard = float(limits["single_name"]["hard"])
    clipped: Dict[str, Dict[str, float]] = {}
    if nav > 0 and sleeve_capital > 0:
        for sym, w in list(etf_w.items()):
            cap = max(0.0, (hard * 0.98 * nav - other_by_sym.get(sym, 0.0)) / sleeve_capital)
            if w > cap:
                clipped[sym] = {"model_weight": round(w, 4), "capped_weight": round(cap, 4)}
                etf_w[sym] = cap
    plan = rebalance_orders(etf_w, sleeve_capital, prices, current)
    holdings = []
    for sym in sorted(universe | set(current)):
        qty = current.get(sym, 0.0)
        px = prices.get(sym)
        val = qty * px if px else None
        holdings.append({"symbol": sym, "quantity": qty, "price": round(px, 2) if px else None,
                         "market_value": round(val, 2) if val is not None else None,
                         "weight": round(val / sleeve_capital, 4) if val is not None and sleeve_capital else None,
                         "target_weight": round(etf_w.get(sym, 0.0), 4)})
    return {**plan, "holdings": holdings, "portfolio": which, "sleeve_capital": round(sleeve_capital, 2), "sleeve_capital_basis": basis,
            "other_books_market_value": round(other_mv, 2), "book": MODEL_BOOK,
            "single_name_limit": hard, "clipped_by_limits": clipped,
            "target_weights": etf_w, "run_id": result.get("run_id"), "as_of": result["as_of"]}
