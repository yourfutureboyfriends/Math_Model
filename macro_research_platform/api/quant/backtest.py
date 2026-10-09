"""
Full Quant Lab backtest report for one strategy spec: performance (net and gross of costs),
benchmark comparison, monthly table, curves, today's target positions, robustness tests,
warnings and a plain-English verdict. Also parameter sweeps (with PBO) and combinations of
several strategies.
"""
from __future__ import annotations

import itertools
import json
import math
import re
import time
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from api.quant import engine, robust

MAX_POINTS = 700
MAX_SWEEP = 36


def _thin(n: int) -> List[int]:
    step = max(1, math.ceil(n / MAX_POINTS))
    idx = list(range(0, n, step))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    return idx


def _r(x, d=4):
    return None if x is None or not np.isfinite(x) else round(float(x), d)


def run(spec_in: Dict[str, Any], n_trials: int = 1, trial_sharpes: Optional[Sequence[float]] = None,
        light: bool = False) -> Dict[str, Any]:
    """`light` skips the slower robustness reruns (used inside sweeps/combinations)."""
    t0 = time.time()
    spec = engine.normalize(spec_in)
    prep = engine.prepare(spec)
    sim = engine.simulate(spec, prep)
    dates, net, gross, cost = sim["dates"], sim["net"], sim["gross"], sim["cost"]
    # Start the record at the first day the strategy held anything (assets may list later).
    live = np.flatnonzero(sim["gross_exp"] > 1e-9)
    if live.size == 0:
        raise engine.SpecError("The strategy never took a position — check the signal, filter and selection rules.")
    a = int(live[0])
    sl = slice(a, len(dates))
    dates, net, gross, cost = dates[a:], net[sl], gross[sl], cost[sl]
    if len(dates) < 60:
        raise engine.SpecError("Less than 3 months of history — choose an earlier start or a longer-listed universe.")
    bench = engine.benchmark_returns(prep, spec["benchmark"], dates)
    m_net = robust.metrics(net, dates)
    m_gross = robust.metrics(gross, dates)
    m_bench = robust.metrics(bench, dates)
    mt = robust.monthly_table(net, dates)
    mb = robust.monthly_table(bench, dates)
    years = m_net["years"]
    out: Dict[str, Any] = {
        "spec": spec, "hash": engine.spec_hash(spec),
        "period": {"start": dates[0], "end": dates[-1], "years": years, "last_close": sim["last_close_date"]},
        "metrics": m_net, "metrics_gross": m_gross, "benchmark": {"symbol": spec["benchmark"], "metrics": m_bench},
        "vs_benchmark": robust.vs_benchmark(net, bench, mt["monthly"], mb["monthly"]),
        "trading": {"turnover_annual": _r(sim["turnover_total"] / years, 2),
                    "cost_drag_annual": _r(m_gross["cagr"] - m_net["cagr"]),
                    "avg_gross_exposure": _r(float(np.mean(sim["gross_exp"][sl])), 3),
                    "avg_net_exposure": _r(float(np.mean(sim["net_exp"][sl])), 3),
                    "avg_holdings": _r(float(np.mean(sim["holdings"][sl])), 1),
                    "time_in_market": _r(float(np.mean(sim["gross_exp"][sl] > 0.01)), 3),
                    "rebalances_logged": len(sim["log"])},
        "monthly": {"months": mt["months"], "years": mt["years"], "best_month": mt["best_month"],
                    "worst_month": mt["worst_month"], "pct_positive_months": mt["pct_positive_months"],
                    "pct_positive_years": mt["pct_positive_years"], "benchmark_years": mb["years"]},
        "missing_symbols": prep["missing"],
    }
    eq = np.cumprod(1 + net)
    eqb = np.cumprod(1 + bench)
    dd = eq / np.maximum.accumulate(eq) - 1
    roll = []
    if len(net) > 300:
        c = np.concatenate([[0.0], np.cumsum(net)])
        c2 = np.concatenate([[0.0], np.cumsum(net ** 2)])
        for i in range(252, len(net) + 1):
            mu = (c[i] - c[i - 252]) / 252
            var = (c2[i] - c2[i - 252]) / 252 - mu ** 2
            roll.append(mu / math.sqrt(var) * math.sqrt(252) if var > 1e-14 else None)
    out["curve"] = [{"date": dates[i], "strategy": round(float(eq[i]), 4), "benchmark": round(float(eqb[i]), 4),
                     "drawdown": round(float(dd[i]), 4),
                     "rolling_sharpe": (None if i < 251 or roll[i - 251] is None else round(roll[i - 251], 2)),
                     "exposure": round(float(sim["gross_exp"][a + i]), 3)} for i in _thin(len(dates))]
    out["rebalance_log"] = sim["log"][-25:][::-1]
    out["positions"] = _positions(spec, prep, sim)
    if light:
        out["daily_returns"] = net
        out["daily_dates"] = dates
        return out
    rb: Dict[str, Any] = {"psr": _r(robust.psr(net), 3)}
    trials = list(trial_sharpes or [])
    dsr = robust.deflated_sharpe(net, n_trials, [s / math.sqrt(252) for s in trials if s is not None])
    rb["deflated_sharpe"] = {"dsr": _r(dsr.get("dsr"), 3), "trials": dsr.get("trials", n_trials),
                             "sr0_annual": dsr.get("sr0_annual")}
    rb["is_oos"] = robust.is_oos(net, dates)
    rb["bootstrap"] = robust.block_bootstrap(net)
    rb["cost_sensitivity"] = []
    for k in (0, 1, 2, 3):
        rk = gross - k * cost if k != 1 else net
        rb["cost_sensitivity"].append({"multiple": k, "bps": spec["costs"]["bps"] * k, "sharpe": _r(robust.sharpe(rk), 3),
                                       "cagr": robust.metrics(rk, dates)["cagr"]})
    lag = engine.simulate(spec, prep, extra_lag=1)
    lr = lag["net"][-len(net):]
    rb["one_day_delay"] = {"sharpe": _r(robust.sharpe(lr), 3), "cagr": robust.metrics(lr, dates)["cagr"]}
    if spec["risk"]["vol_target"] is not None:
        nv = engine.simulate(spec, prep, vol_target_off=True)["net"][-len(net):]
        rb["without_vol_target"] = {"sharpe": _r(robust.sharpe(nv), 3), "cagr": robust.metrics(nv, dates)["cagr"],
                                    "max_drawdown": robust.metrics(nv, dates)["max_drawdown"]}
    out["robustness"] = rb
    out["warnings"] = _warnings(spec, prep, out)
    out["verdict"] = robust.verdict(out)
    out["build_seconds"] = round(time.time() - t0, 2)
    return out


def _positions(spec, prep, sim) -> List[Dict[str, Any]]:
    cols, today = sim["cols"], sim["today"]
    rows = []
    for j, s in enumerate(cols):
        in_uni = j < len(prep["uni"])
        sc = float(sim["score_today"][j]) if in_uni and np.isfinite(sim["score_today"][j]) else None
        f = None
        if in_uni and sim["filter_today"] is not None:
            fv = sim["filter_today"][j]
            f = bool(np.isfinite(fv) and fv > 0)
        rows.append({"symbol": s, "signal": _r(sc), "passes_filter": f, "target_weight": _r(float(today[j])),
                     "vol": _r(float(sim["vol_today"][j])) if in_uni else None, "fallback": not in_uni})
    rows.sort(key=lambda r: (-(abs(r["target_weight"] or 0)), -(r["signal"] if r["signal"] is not None else -1e9)))
    return rows


def _warnings(spec, prep, out) -> List[str]:
    w = []
    if prep["survivorship"]:
        w.append("Survivorship bias: the universe is today's large caps, so firms that failed are missing — expect live results below this backtest.")
    if prep["missing"]:
        w.append(f"No data for {', '.join(prep['missing'][:8])} — excluded.")
    y = out["period"]["years"]
    if y < 8:
        w.append(f"Only {y:.0f} years tested — less than a full market cycle.")
    t = out["trading"]
    if (t["turnover_annual"] or 0) > 12 and spec["costs"]["bps"] < 5:
        w.append(f"High turnover ({t['turnover_annual']:.0f}× a year) with low assumed costs ({spec['costs']['bps']} bp) — real slippage may be higher.")
    if (t["cost_drag_annual"] or 0) > 0.02:
        w.append(f"Costs eat {t['cost_drag_annual']:.1%} a year — the edge depends on cheap execution.")
    if len(prep["uni"]) < 4 and spec["selection"]["mode"] in ("top_n", "top_pct", "long_short"):
        w.append("Very small universe — ranking across a handful of assets is noisy.")
    if (spec["risk"]["max_gross"] or 1) > 1.5:
        w.append(f"Leverage up to {spec['risk']['max_gross']}× — financing costs are not modelled beyond short borrow.")
    rb = out.get("robustness") or {}
    wv = rb.get("without_vol_target")
    if wv and wv.get("sharpe") is not None and out["metrics"].get("sharpe") is not None and wv["sharpe"] >= out["metrics"]["sharpe"]:
        w.append("The volatility target does not improve the Sharpe here — consistent with Cederburg et al. (2020); consider dropping it.")
    return w


# ── Parameter sweep ──────────────────────────────────────────────────────────
_PH = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


def sweep(spec_in: Dict[str, Any], params: Dict[str, Sequence[Any]], n_prior_trials: int = 0) -> Dict[str, Any]:
    """Run every combination of `params` (placeholders like {n} anywhere in the spec), then
    report each variant, the PBO of picking the best, and the best variant's Deflated Sharpe
    counting all variants as trials."""
    keys = [k for k in params if _PH.fullmatch("{" + k + "}")]
    if not keys:
        raise engine.SpecError("Add parameters, e.g. n = 126, 189, 252, and use {n} in the formula.")
    grids = [list(params[k])[:12] for k in keys]
    combos = list(itertools.product(*grids))
    if len(combos) > MAX_SWEEP:
        raise engine.SpecError(f"{len(combos)} combinations — at most {MAX_SWEEP} per sweep.")
    raw = json.dumps(spec_in)
    used = set(_PH.findall(raw))
    missing = [k for k in keys if k not in used]
    if missing:
        raise engine.SpecError(f"Parameter(s) {', '.join(missing)} are not used — write {{{missing[0]}}} in the formula or a setting.")
    rows, series = [], []
    for combo in combos:
        txt = raw
        for k, v in zip(keys, combo):
            num = float(v)
            lit = str(int(num)) if num.is_integer() else str(num)
            txt = txt.replace('"{' + k + '}"', lit).replace("{" + k + "}", lit)
        res = run(json.loads(txt), light=True)
        rows.append({"params": dict(zip(keys, combo)), "sharpe": res["metrics"]["sharpe"], "cagr": res["metrics"]["cagr"],
                     "max_drawdown": res["metrics"]["max_drawdown"], "turnover": res["trading"]["turnover_annual"]})
        series.append((res["daily_dates"], res["daily_returns"]))
    common = sorted(set.intersection(*(set(d) for d, _ in series)))
    maps = [dict(zip(d, r)) for d, r in series]
    mat = np.column_stack([np.array([mp[x] for x in common]) for mp in maps])
    sh = [r["sharpe"] for r in rows]
    best = int(np.nanargmax([s if s is not None else -9 for s in sh]))
    n_tr = len(rows) + n_prior_trials
    dsr = robust.deflated_sharpe(mat[:, best], n_tr, [s / math.sqrt(252) for s in sh if s is not None])
    pbo = robust.pbo_cscv(mat)
    valid = [x for x in sh if x is not None]
    spread = (max(valid) - min(valid)) if valid else 0
    if pbo.get("pbo") is None:
        note = "Too little overlapping history to estimate the probability of overfitting."
    elif pbo["pbo"] > 0.5 and spread < 0.25:
        note = (f"The variants perform alike (Sharpe {min(valid):.2f}–{max(valid):.2f}), so the 'best' setting is mostly luck "
                f"(PBO {pbo['pbo']:.0%}). Good news: the idea is robust to its parameters — pick a middle value, not the top one.")
    elif pbo["pbo"] > 0.5:
        note = (f"PBO {pbo['pbo']:.0%}: the in-sample best usually lands in the bottom half out of sample — the best "
                "variant is likely overfit. Prefer a simpler or middle setting.")
    else:
        note = (f"PBO {pbo['pbo']:.0%}: the in-sample best tends to stay above the median out of sample — the "
                "parameter choice carries real information.")
    return {"keys": keys, "rows": rows, "best": rows[best], "pbo": pbo, "interpretation": note,
            "deflated_sharpe_best": {"dsr": _r(dsr.get("dsr"), 3), "trials": n_tr, "sr0_annual": dsr.get("sr0_annual")},
            "sharpe_spread": {"min": _r(np.nanmin([s for s in sh if s is not None]), 3), "max": _r(np.nanmax([s for s in sh if s is not None]), 3),
                              "median": _r(float(np.nanmedian([s for s in sh if s is not None])), 3)},
            "window": {"start": common[0], "end": common[-1]}}


# ── Combining strategies ─────────────────────────────────────────────────────
def combine(specs: List[Dict[str, Any]], method: str = "erc") -> Dict[str, Any]:
    """Several strategies as one book: equal weight, inverse volatility or equal risk
    contribution (walk-forward, trailing-year covariance), on their common dates."""
    from api.calculations import strategies as sg
    if not 2 <= len(specs) <= 8:
        raise engine.SpecError("Combine 2–8 strategies.")
    runs = [run(s, light=True) for s in specs]
    names = []
    for s, r in zip(specs, runs):
        nm = r["spec"]["name"]
        while nm in names:
            nm += "′"
        names.append(nm)
    common = sorted(set.intersection(*(set(r["daily_dates"]) for r in runs)))
    if len(common) < 400:
        raise engine.SpecError("The strategies overlap for less than ~1.5 years — not enough to combine.")
    al = {}
    for n, r in zip(names, runs):
        mp = dict(zip(r["daily_dates"], r["daily_returns"]))
        al[n] = np.array([mp[d] for d in common])
    if method == "equal":
        R = np.column_stack(list(al.values()))
        comb = R.mean(axis=1)
        weights = {n: round(1 / len(names), 4) for n in names}
        dates = common
    elif method == "inverse_vol":
        R = np.column_stack(list(al.values()))
        comb = np.zeros(len(common))
        for t in range(252, len(common)):
            v = R[t - 252:t].std(axis=0, ddof=1)
            w = np.where(v > 0, 1 / v, 0)
            w = w / w.sum() if w.sum() > 0 else np.full(len(names), 1 / len(names))
            comb[t] = R[t] @ w
        comb = comb[252:]
        dates = common[252:]
        weights = {n: round(float(x), 4) for n, x in zip(names, w)}
    else:
        c = sg.combine_erc(al)
        comb = c["returns"]
        dates = common[252:]
        weights = c["weights"]
    per = {n: robust.metrics(al[n][-len(dates):], dates) for n in names}
    corr = np.corrcoef(np.column_stack([al[n][-len(dates):] for n in names]), rowvar=False)
    eq = np.cumprod(1 + comb)
    eqs = {n: np.cumprod(1 + al[n][-len(dates):]) for n in names}
    curve = [{"date": dates[i], "combined": round(float(eq[i]), 4), **{n: round(float(eqs[n][i]), 4) for n in names}}
             for i in _thin(len(dates))]
    return {"method": method, "names": names, "weights": weights, "metrics": robust.metrics(comb, dates),
            "members": per, "correlation": {a: {b: round(float(corr[i, j]), 3) for j, b in enumerate(names)} for i, a in enumerate(names)},
            "curve": curve, "window": {"start": dates[0], "end": dates[-1]},
            "bootstrap": robust.block_bootstrap(comb)}
