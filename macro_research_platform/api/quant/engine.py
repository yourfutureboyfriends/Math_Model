"""
Portfolio backtest engine for Quant Lab strategies.

A strategy spec (validated by `normalize`) is:
    universe   {preset} or {symbols}
    signal     formula (api/quant/expr) — higher = more attractive
    filter     optional formula; an asset is eligible only where it is > 0
    selection  {mode: top_n | top_pct | threshold | sign | long_short, n, pct, min_score, long_only}
    weighting  equal | inverse_vol | signal | equal_universe
    risk       {vol_target, max_weight, max_gross, vol_lookback}
    rebalance  daily | weekly | monthly
    execution  next_open | next_close
    costs      {bps (per side, on traded notional), borrow_bps (annual, on shorts)}
    fallback   optional symbol held when nothing is selected (e.g. IEF)
    benchmark  symbol (default SPY);  start / end dates

Timing (no look-ahead): weights are computed from data up to the close of day t and traded
at the open (or close) of day t+1. Between rebalances positions drift with prices; each
rebalance pays costs on the actual traded notional.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from api.quant import data as qdata
from api.quant import expr

SELECTION_MODES = ("top_n", "top_pct", "threshold", "sign", "long_short")
WEIGHTINGS = ("equal", "inverse_vol", "signal", "equal_universe")
REBALANCE = ("daily", "weekly", "monthly")
EXECUTION = ("next_open", "next_close")


class SpecError(ValueError):
    pass


def normalize(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Validated spec with defaults filled; raises SpecError with a user-facing message."""
    s = dict(spec or {})
    out: Dict[str, Any] = {"name": str(s.get("name") or "Untitled strategy")[:80],
                           "description": str(s.get("description") or "")[:1000]}
    out["universe"] = s.get("universe") or {"preset": "cross_asset"}
    try:
        qdata.resolve_universe(out["universe"])
    except ValueError as e:
        raise SpecError(str(e))
    for k in ("signal", "filter"):
        v = (s.get(k) or "").strip()
        if k == "signal" and not v:
            raise SpecError("A signal formula is required.")
        if v:
            try:
                expr.parse(v)
            except expr.ExprError as e:
                raise SpecError(f"{k.title()}: {e}")
        out[k] = v or None
    sel = dict(s.get("selection") or {})
    mode = sel.get("mode", "top_n")
    if mode not in SELECTION_MODES:
        raise SpecError(f"Selection mode must be one of {', '.join(SELECTION_MODES)}")
    out["selection"] = {"mode": mode, "n": int(sel.get("n") or 3), "pct": float(sel.get("pct") or 0.2),
                        "min_score": None if sel.get("min_score") in (None, "") else float(sel["min_score"]),
                        "long_only": bool(sel.get("long_only", mode != "long_short"))}
    if out["selection"]["n"] < 1 or out["selection"]["n"] > 200:
        raise SpecError("Number of holdings must be 1–200.")
    if not 0 < out["selection"]["pct"] <= 1:
        raise SpecError("Top % must be between 0 and 100%.")
    w = s.get("weighting", "equal")
    if w not in WEIGHTINGS:
        raise SpecError(f"Weighting must be one of {', '.join(WEIGHTINGS)}")
    out["weighting"] = w
    risk = dict(s.get("risk") or {})
    vt = risk.get("vol_target")
    out["risk"] = {"vol_target": None if vt in (None, "", 0) else float(vt),
                   "max_weight": float(risk.get("max_weight") or 1.0),
                   "max_gross": float(risk.get("max_gross") or 1.0),
                   "vol_lookback": int(risk.get("vol_lookback") or 63)}
    r = out["risk"]
    if r["vol_target"] is not None and not 0.01 <= r["vol_target"] <= 0.5:
        raise SpecError("Volatility target must be 1%–50%.")
    if not 0.01 <= r["max_weight"] <= 1.0:
        raise SpecError("Max weight per position must be 1%–100%.")
    if not 0.1 <= r["max_gross"] <= 4.0:
        raise SpecError("Max gross exposure (leverage) must be 0.1×–4×.")
    if not 20 <= r["vol_lookback"] <= 504:
        raise SpecError("Volatility lookback must be 20–504 days.")
    out["rebalance"] = s.get("rebalance", "monthly")
    if out["rebalance"] not in REBALANCE:
        raise SpecError(f"Rebalance must be one of {', '.join(REBALANCE)}")
    out["execution"] = s.get("execution", "next_open")
    if out["execution"] not in EXECUTION:
        raise SpecError("Execution must be next_open or next_close.")
    c = dict(s.get("costs") or {})
    out["costs"] = {"bps": float(c.get("bps", 5.0)), "borrow_bps": float(c.get("borrow_bps", 50.0))}
    if not 0 <= out["costs"]["bps"] <= 200 or not 0 <= out["costs"]["borrow_bps"] <= 2000:
        raise SpecError("Costs out of range (0–200 bp per trade, 0–2000 bp/yr borrow).")
    fb = (s.get("fallback") or "").strip().upper() or None
    if fb and not qdata.clean_symbols([fb])[0]:
        raise SpecError("Invalid fallback ticker.")
    out["fallback"] = fb
    bm = (s.get("benchmark") or "SPY").strip().upper()
    if not qdata.clean_symbols([bm])[0]:
        raise SpecError("Invalid benchmark ticker.")
    out["benchmark"] = bm
    out["start"] = (s.get("start") or "2005-01-01")[:10]
    out["end"] = (s.get("end") or None) and str(s["end"])[:10]
    return out


def spec_hash(spec: Dict[str, Any]) -> str:
    core = {k: v for k, v in spec.items() if k not in ("name", "description")}
    return hashlib.sha1(json.dumps(core, sort_keys=True).encode()).hexdigest()[:16]


def _rebalance_mask(idx: pd.DatetimeIndex, freq: str) -> np.ndarray:
    n = len(idx)
    if freq == "daily":
        return np.ones(n, bool)
    key = idx.to_period("W" if freq == "weekly" else "M")
    m = np.zeros(n, bool)
    m[:-1] = key[:-1] != key[1:]
    m[-1] = True
    return m


def _cov_vol(rets: np.ndarray, w: np.ndarray) -> Optional[float]:
    """Annualised portfolio vol of weights w from a window of daily returns (pairwise-complete,
    10% shrinkage toward the diagonal)."""
    act = np.flatnonzero(w != 0)
    if act.size == 0:
        return None
    sub = rets[:, act]
    ok = np.isfinite(sub).all(axis=1)
    if ok.sum() < 20:
        return None
    c = np.cov(sub[ok], rowvar=False)
    c = np.atleast_2d(c)
    c = 0.9 * c + 0.1 * np.diag(np.diag(c))
    v = float(w[act] @ c @ w[act])
    return math.sqrt(v * 252) if v > 0 else None


def target_weights(spec: Dict[str, Any], score: np.ndarray, eligible: np.ndarray, vol: np.ndarray,
                   n_universe: int) -> np.ndarray:
    """Weights from one day's scores (NaN = no view), before risk scaling."""
    sel = spec["selection"]
    mode, long_only = sel["mode"], sel["long_only"]
    m = score.size
    ok = eligible & np.isfinite(score)
    if sel["min_score"] is not None and mode in ("top_n", "top_pct", "threshold"):
        ok &= score > sel["min_score"]
    w = np.zeros(m)
    idx = np.flatnonzero(ok)
    if idx.size == 0:
        return w
    order = idx[np.argsort(-score[idx], kind="stable")]
    side = np.zeros(m)
    if mode == "top_n":
        side[order[:sel["n"]]] = 1
    elif mode == "top_pct":
        side[order[:max(1, int(round(idx.size * sel["pct"])))]] = 1
    elif mode == "threshold":
        side[idx[score[idx] > (sel["min_score"] if sel["min_score"] is not None else 0.0)]] = 1
    elif mode == "sign":
        side[idx] = np.sign(score[idx])
        if long_only:
            side = np.clip(side, 0, None)
    elif mode == "long_short":
        k = min(sel["n"], idx.size // 2)
        if k >= 1:
            side[order[:k]] = 1
            if not long_only:
                side[order[-k:]] = -1
    act = np.flatnonzero(side != 0)
    if act.size == 0:
        return w
    wt = spec["weighting"]
    if wt == "inverse_vol":
        iv = np.where(np.isfinite(vol[act]) & (vol[act] > 0), 1 / vol[act], np.nan)
        base = np.where(np.isfinite(iv), iv, np.nanmean(iv) if np.isfinite(iv).any() else 1.0)
    elif wt == "signal":
        base = np.abs(score[act])
        if not (base > 0).any():
            base = np.ones(act.size)
    else:
        base = np.ones(act.size)
    w[act] = side[act] * base
    if wt == "equal_universe":
        w[act] = side[act] / max(n_universe, 1)            # unselected slots stay in cash
    else:
        longs, shorts = w > 0, w < 0
        if mode == "long_short" and shorts.any():
            w[longs] *= 0.5 / w[longs].sum()
            w[shorts] *= 0.5 / -w[shorts].sum()
        else:
            g = np.abs(w).sum()
            w = w / g if g > 0 else w
    return w


def apply_risk(spec: Dict[str, Any], w: np.ndarray, hist_rets: np.ndarray) -> np.ndarray:
    r = spec["risk"]
    w = np.clip(w, -r["max_weight"], r["max_weight"])
    if r["vol_target"] is not None:
        v = _cov_vol(hist_rets, w)
        if v and v > 0:
            w = w * (r["vol_target"] / v)
    g = np.abs(w).sum()
    if g > r["max_gross"]:
        w = w * (r["max_gross"] / g)
    return w


def prepare(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Load data and evaluate the formulas once (shared by the run and its robustness reruns)."""
    syms, survivorship = qdata.resolve_universe(spec["universe"])
    extra = [x for x in (spec["benchmark"], spec["fallback"]) if x and x not in syms]
    warm_start = (pd.Timestamp(spec["start"]) - pd.Timedelta(days=int(2520 * 1.5))).strftime("%Y-%m-%d")
    pan, missing = qdata.panel(syms + extra, start=warm_start, end=spec["end"])
    if not pan:
        raise SpecError("No price data could be loaded for this universe.")
    cols = list(pan["close"].columns)
    uni = [s for s in syms if s in cols]
    if not uni:
        raise SpecError(f"No price data for any of: {', '.join(syms[:8])}")
    if spec["benchmark"] not in cols:
        raise SpecError(f"No price data for the benchmark {spec['benchmark']}.")
    if spec["fallback"] and spec["fallback"] not in cols:
        raise SpecError(f"No price data for the fallback {spec['fallback']}.")
    close_u = pan["close"][uni]
    ctx = expr.Ctx(close_u, pan["open"][uni], pan["high"][uni], pan["low"][uni], pan["volume"][uni],
                   mkt=pan["close"][spec["benchmark"]])
    try:
        score = expr.evaluate(spec["signal"], ctx)
        filt = expr.evaluate(spec["filter"], ctx) if spec["filter"] else None
    except expr.ExprError as e:
        raise SpecError(str(e))
    lr = np.log(close_u / close_u.shift(1))
    vol = lr.rolling(63, min_periods=40).std() * math.sqrt(252)
    return {"pan": pan, "uni": uni, "missing": [m for m in missing if m in syms], "survivorship": survivorship,
            "score": score, "filter": filt, "vol": vol}


def simulate(spec: Dict[str, Any], prep: Dict[str, Any], extra_lag: int = 0, vol_target_off: bool = False
             ) -> Dict[str, Any]:
    """Run the strategy. Returns daily net/gross returns, costs, exposures and rebalance log."""
    if vol_target_off:
        spec = {**spec, "risk": {**spec["risk"], "vol_target": None}}
    pan, uni = prep["pan"], prep["uni"]
    cols = list(uni) + ([spec["fallback"]] if spec["fallback"] and spec["fallback"] not in uni else [])
    close = pan["close"][cols]
    open_ = pan["open"][cols]
    idx = close.index
    start_i = int(idx.searchsorted(pd.Timestamp(spec["start"])))
    C, O = close.to_numpy(float), open_.to_numpy(float)
    T, M = C.shape
    nu = len(uni)
    score = prep["score"].reindex(idx).to_numpy(float)
    filt = prep["filter"].reindex(idx).to_numpy(float) if prep["filter"] is not None else None
    vol = prep["vol"].reindex(idx).to_numpy(float)
    with np.errstate(all="ignore"):
        rcc = C[1:] / C[:-1] - 1
    rcc = np.vstack([np.full((1, M), np.nan), rcc])
    hist = rcc[:, :nu]
    reb = _rebalance_mask(idx, spec["rebalance"])
    fb_col = cols.index(spec["fallback"]) if spec["fallback"] else None
    bps, borrow = spec["costs"]["bps"] / 1e4, spec["costs"]["borrow_bps"] / 1e4 / 252
    next_open = spec["execution"] == "next_open"

    h = np.zeros(M)                      # current weights (fraction of NAV)
    pending: Optional[np.ndarray] = None
    pending_at = -1
    net = np.zeros(T)
    gross = np.zeros(T)
    cost = np.zeros(T)
    gross_exp = np.zeros(T)
    net_exp = np.zeros(T)
    nhold = np.zeros(T)
    turnover_total = 0.0
    log: List[Dict[str, Any]] = []
    last_target = None
    lb = spec["risk"]["vol_lookback"]

    def decide(t: int) -> np.ndarray:
        elig = np.isfinite(C[t, :nu])
        if filt is not None:
            elig &= np.nan_to_num(filt[t], nan=0.0) > 0
        n_live = int(np.isfinite(C[t, :nu]).sum())
        w_u = target_weights(spec, score[t], elig, vol[t], n_live)
        w_u = apply_risk(spec, w_u, hist[max(0, t - lb + 1):t + 1])
        w = np.zeros(M)
        w[:nu] = w_u
        if fb_col is not None:
            free = max(0.0, 1.0 - np.abs(w_u).sum()) if spec["weighting"] == "equal_universe" else (1.0 if not (w_u != 0).any() else 0.0)
            if free > 0 and np.isfinite(C[t, fb_col]):
                w[fb_col] += free
        return w

    for t in range(max(1, start_i - 1), T):
        # 1) mark to market from close t-1 (overnight + intraday, or close to close)
        if t >= start_i:
            g_cc = np.nan_to_num(rcc[t])
            trade_now = pending is not None and t >= pending_at
            if trade_now and next_open:
                with np.errstate(all="ignore"):
                    g1 = np.nan_to_num(np.where(np.isfinite(O[t]) & np.isfinite(C[t - 1]), O[t] / C[t - 1] - 1, g_cc))
                    g2 = np.nan_to_num(np.where(np.isfinite(O[t]) & np.isfinite(C[t]), C[t] / O[t] - 1, 0.0))
                R1 = float(h @ g1)
                h = h * (1 + g1) / (1 + R1) if 1 + R1 > 0 else h
                tw = pending
                to = float(np.abs(tw - h).sum())
                c = to * bps
                R2 = float(tw @ g2)
                day = (1 + R1) * (1 - c) * (1 + R2) - 1
                gross_day = (1 + R1) * (1 + R2) - 1
                h = tw * (1 + g2) / (1 + R2) if 1 + R2 > 0 else tw
                turnover_total += to
                cost[t] += c
                pending = None
            else:
                R = float(h @ g_cc)
                h = h * (1 + g_cc) / (1 + R) if 1 + R > 0 else h
                day = gross_day = R
                if trade_now:                                   # next_close: trade at today's close
                    to = float(np.abs(pending - h).sum())
                    c = to * bps
                    day = (1 + R) * (1 - c) - 1
                    turnover_total += to
                    cost[t] += c
                    h = pending.copy()
                    pending = None
            b = float(np.abs(np.clip(h, None, 0)).sum()) * borrow
            net[t] = (1 + day) * (1 - b) - 1
            gross[t] = gross_day
            cost[t] += b
            gross_exp[t] = float(np.abs(h).sum())
            net_exp[t] = float(h.sum())
            nhold[t] = int((np.abs(h) > 1e-6).sum())
        # 2) decide at today's close; trade at the next bar (+ any extra lag)
        if reb[t] and t >= start_i - 1 and t < T - 1:
            w = decide(t)
            prev = last_target
            pending, pending_at = w, t + 1 + extra_lag
            last_target = w
            if prev is None or (np.sign(prev) != np.sign(w)).any() or np.abs(prev - w).sum() > 0.05:
                ins = [cols[i] for i in np.flatnonzero((w != 0) & ((prev == 0) if prev is not None else True))]
                outs = [cols[i] for i in np.flatnonzero((w == 0) & (prev != 0))] if prev is not None else []
                log.append({"date": idx[t].strftime("%Y-%m-%d"), "in": ins[:12], "out": outs[:12],
                            "holdings": int((w != 0).sum()), "gross": round(float(np.abs(w).sum()), 3)})

    sl = slice(start_i, T)
    dates = [d.strftime("%Y-%m-%d") for d in idx[sl]]
    # Today's target if the strategy were rebalanced at the latest close.
    today = decide(T - 1)
    return {"dates": dates, "net": net[sl], "gross": gross[sl], "cost": cost[sl], "gross_exp": gross_exp[sl],
            "net_exp": net_exp[sl], "holdings": nhold[sl], "turnover_total": turnover_total,
            "log": log, "cols": cols, "today": today, "last_close_date": idx[-1].strftime("%Y-%m-%d"),
            "score_today": score[T - 1], "filter_today": (filt[T - 1] if filt is not None else None),
            "vol_today": vol[T - 1]}


def benchmark_returns(prep: Dict[str, Any], symbol: str, dates: List[str]) -> np.ndarray:
    c = prep["pan"]["close"][symbol]
    r = (c / c.shift(1) - 1).reindex(pd.DatetimeIndex(dates)).to_numpy(float)
    return np.nan_to_num(r)
