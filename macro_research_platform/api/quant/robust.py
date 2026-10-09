"""
Performance statistics and robustness tests for Quant Lab backtests.

Why each test exists (the ways backtests mislead):
  * Multiple testing — trying many variants and keeping the best inflates the Sharpe.
    Deflated Sharpe Ratio (Bailey & López de Prado 2014) and the t > 3 hurdle of Harvey,
    Liu & Zhu (2016) correct for it; PBO via combinatorially symmetric cross-validation
    (Bailey, Borwein, López de Prado & Zhu 2017) measures it directly for a parameter sweep.
  * Overfitting to one period — in-sample vs out-of-sample split and year-by-year
    consistency.
  * Estimation noise — stationary block-bootstrap confidence intervals (Politis & Romano 1994).
  * Implementation — cost sensitivity (short-term strategies often die after costs:
    reversal profits largely vanish net of trading costs), execution delay, and whether a
    volatility target actually helps out of sample (Cederburg et al. 2020 found vol-managed
    versions underperform in 72 of 103 equity strategies).
"""
from __future__ import annotations

import math
from itertools import combinations
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

PPY = 252


def _years(dates: Sequence[str]) -> float:
    from datetime import date
    return max((date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days / 365.25, 1 / 365.25)


def sharpe(r: np.ndarray) -> Optional[float]:
    r = r[np.isfinite(r)]
    if r.size < 20 or r.std(ddof=1) == 0:
        return None
    return float(r.mean() / r.std(ddof=1) * math.sqrt(PPY))


def metrics(r: np.ndarray, dates: Sequence[str]) -> Dict[str, Any]:
    r = np.nan_to_num(np.asarray(r, float))
    eq = np.cumprod(1 + r)
    yrs = _years(dates)
    cagr = float(eq[-1] ** (1 / yrs) - 1) if eq[-1] > 0 else -1.0
    vol = float(r.std(ddof=1) * math.sqrt(PPY)) if r.size > 2 else 0.0
    peak = np.maximum.accumulate(np.concatenate([[1.0], eq]))[1:]
    dd = eq / peak - 1
    # longest time under water (days)
    under, longest, cur = dd < 0, 0, 0
    for u in under:
        cur = cur + 1 if u else 0
        longest = max(longest, cur)
    down = r[r < 0]
    sortino = float(r.mean() * PPY / (down.std(ddof=1) * math.sqrt(PPY))) if down.size > 2 and down.std() > 0 else None
    mdd = float(dd.min()) if dd.size else 0.0
    t_stat = float(r.mean() / (r.std(ddof=1) / math.sqrt(r.size))) if r.size > 2 and r.std() > 0 else None
    return {"total_return": round(float(eq[-1] - 1), 4), "cagr": round(cagr, 4), "vol": round(vol, 4),
            "sharpe": None if vol == 0 else round(float(r.mean() * PPY / vol), 3),
            "sortino": round(sortino, 3) if sortino is not None else None,
            "max_drawdown": round(mdd, 4), "calmar": round(cagr / abs(mdd), 3) if mdd < 0 else None,
            "longest_underwater_days": int(longest), "hit_rate_days": round(float((r[r != 0] > 0).mean()), 3) if (r != 0).any() else None,
            "t_stat": round(t_stat, 2) if t_stat is not None else None, "years": round(yrs, 1),
            "skew": round(float(_skew(r)), 2), "worst_day": round(float(r.min()), 4), "best_day": round(float(r.max()), 4)}


def _skew(r):
    s = r.std()
    return float(((r - r.mean()) ** 3).mean() / s ** 3) if s > 0 else 0.0


def _kurt(r):
    s = r.std()
    return float(((r - r.mean()) ** 4).mean() / s ** 4) if s > 0 else 3.0


def monthly_table(r: np.ndarray, dates: Sequence[str]) -> Dict[str, Any]:
    by: Dict[str, Dict[str, float]] = {}
    keys = [d[:7] for d in dates]
    out_m: Dict[str, float] = {}
    i = 0
    while i < len(keys):
        j = i
        while j < len(keys) and keys[j] == keys[i]:
            j += 1
        out_m[keys[i]] = float(np.prod(1 + r[i:j]) - 1)
        i = j
    for k, v in out_m.items():
        by.setdefault(k[:4], {})[k[5:]] = round(v, 4)
    years = {y: round(float(np.prod([1 + v for v in m.values()]) - 1), 4) for y, m in by.items()}
    vals = np.array(list(out_m.values()))
    return {"months": by, "years": years,
            "best_month": round(float(vals.max()), 4) if vals.size else None,
            "worst_month": round(float(vals.min()), 4) if vals.size else None,
            "pct_positive_months": round(float((vals > 0).mean()), 3) if vals.size else None,
            "pct_positive_years": round(float(np.mean([v > 0 for v in years.values()])), 3) if years else None,
            "monthly": out_m}


def vs_benchmark(r: np.ndarray, b: np.ndarray, monthly_r: Dict[str, float], monthly_b: Dict[str, float]) -> Dict[str, Any]:
    ok = np.isfinite(r) & np.isfinite(b)
    r, b = r[ok], b[ok]
    if r.size < 60 or b.std() == 0:
        return {}
    beta = float(np.cov(r, b)[0, 1] / b.var(ddof=1))
    alpha = float((r.mean() - beta * b.mean()) * PPY)
    active = r - b
    te = float(active.std(ddof=1) * math.sqrt(PPY))
    ks = [k for k in monthly_r if k in monthly_b]
    mr, mb = np.array([monthly_r[k] for k in ks]), np.array([monthly_b[k] for k in ks])
    up, dn = mb > 0, mb < 0
    return {"beta": round(beta, 3), "alpha_annual": round(alpha, 4), "correlation": round(float(np.corrcoef(r, b)[0, 1]), 3),
            "tracking_error": round(te, 4), "information_ratio": round(float(active.mean() * PPY / te), 3) if te > 0 else None,
            "up_capture": round(float(mr[up].mean() / mb[up].mean()), 3) if up.any() and mb[up].mean() != 0 else None,
            "down_capture": round(float(mr[dn].mean() / mb[dn].mean()), 3) if dn.any() and mb[dn].mean() != 0 else None,
            "return_in_benchmark_down_months": round(float(mr[dn].mean()), 4) if dn.any() else None}


def psr(r: np.ndarray, sr_benchmark: float = 0.0) -> Optional[float]:
    """Probabilistic Sharpe Ratio: P(true per-period Sharpe > benchmark), skew/kurtosis-adjusted."""
    from scipy.stats import norm
    r = r[np.isfinite(r)]
    n = r.size
    if n < 30 or r.std(ddof=1) == 0:
        return None
    sr = r.mean() / r.std(ddof=1)
    den = math.sqrt(max(1e-12, 1 - _skew(r) * sr + (_kurt(r) - 1) / 4 * sr ** 2))
    return float(norm.cdf((sr - sr_benchmark) * math.sqrt(n - 1) / den))


def deflated_sharpe(r: np.ndarray, n_trials: int, trial_sharpes: Optional[Sequence[float]] = None) -> Dict[str, Any]:
    """DSR: PSR against the expected maximum Sharpe of `n_trials` (Bailey & López de Prado 2014).
    The variance of trial Sharpes is taken from `trial_sharpes` (per-period) when ≥ 2 are known,
    else from the sampling error of a Sharpe estimate."""
    r = r[np.isfinite(r)]
    n = r.size
    if n < 30 or r.std(ddof=1) == 0:
        return {}
    n_trials = max(1, int(n_trials))
    if n_trials == 1:
        return {"dsr": psr(r, 0.0), "trials": 1, "sr0_annual": 0.0}
    from scipy.stats import norm
    ts = np.array([x for x in (trial_sharpes or []) if x is not None and np.isfinite(x)], float)
    var = float(ts.var(ddof=1)) if ts.size >= 2 else 1.0 / (n - 1)
    g = 0.5772156649
    e_max = math.sqrt(var) * ((1 - g) * norm.ppf(1 - 1 / n_trials) + g * norm.ppf(1 - 1 / (n_trials * math.e)))
    return {"dsr": psr(r, e_max), "trials": n_trials, "sr0_annual": round(e_max * math.sqrt(PPY), 3)}


def block_bootstrap(r: np.ndarray, n: int = 600, block: int = 21, seed: int = 7) -> Dict[str, Any]:
    """Stationary block bootstrap (Politis & Romano 1994): 5–95% ranges of Sharpe and CAGR.
    Vectorised: each path restarts at a random day with probability 1/block, else continues."""
    r = np.nan_to_num(np.asarray(r, float))
    T = r.size
    if T < 120:
        return {}
    rng = np.random.default_rng(seed)
    sh, cg = [], []
    ar = np.arange(T)
    for chunk in range(0, n, 100):                         # bounded memory: 100 paths at a time
        k = min(100, n - chunk)
        restart = rng.random((k, T)) < 1.0 / block
        restart[:, 0] = True
        starts = rng.integers(0, T, size=(k, T))
        last = np.maximum.accumulate(np.where(restart, ar, 0), axis=1)
        idx = (np.take_along_axis(starts, last, axis=1) + (ar - last)) % T
        x = r[idx]
        s = x.std(axis=1, ddof=1)
        sh.append(np.where(s > 0, x.mean(axis=1) / np.where(s > 0, s, 1) * math.sqrt(PPY), 0.0))
        g = np.exp(np.log1p(np.clip(x, -0.999999, None)).sum(axis=1))
        cg.append(np.where(g > 0, g ** (PPY / T) - 1, -1.0))
    sh, cg = np.concatenate(sh), np.concatenate(cg)
    return {"sharpe_p05": round(float(np.percentile(sh, 5)), 3), "sharpe_p95": round(float(np.percentile(sh, 95)), 3),
            "cagr_p05": round(float(np.percentile(cg, 5)), 4), "cagr_p95": round(float(np.percentile(cg, 95)), 4),
            "prob_sharpe_negative": round(float((sh < 0).mean()), 3), "samples": n, "block_days": block}


def is_oos(r: np.ndarray, dates: Sequence[str], split: float = 0.7) -> Dict[str, Any]:
    k = int(len(r) * split)
    if k < 250 or len(r) - k < 120:
        return {}
    a, b = sharpe(r[:k]), sharpe(r[k:])
    return {"split_date": dates[k], "is_sharpe": round(a, 3) if a is not None else None,
            "oos_sharpe": round(b, 3) if b is not None else None,
            "decay": round(1 - b / a, 3) if a and b is not None and a > 0 else None}


def pbo_cscv(matrix: np.ndarray, s: int = 10) -> Dict[str, Any]:
    """Probability of Backtest Overfitting via CSCV. `matrix` is T × N (daily returns of N
    variants). Split time into S blocks; for every half/half split, take the in-sample best
    variant and see where it ranks out of sample. PBO = share of splits where it lands in
    the bottom half (logit ≤ 0)."""
    T, N = matrix.shape
    if N < 2 or T < s * 40:
        return {}
    blocks = np.array_split(np.arange(T), s)
    lambdas = []
    oos_of_best = []
    for comb in combinations(range(s), s // 2):
        is_idx = np.concatenate([blocks[i] for i in comb])
        oos_idx = np.concatenate([blocks[i] for i in range(s) if i not in comb])
        def sr(m):
            sd = m.std(axis=0, ddof=1)
            return np.where(sd > 0, m.mean(axis=0) / np.where(sd > 0, sd, 1), -np.inf)
        s_is, s_oos = sr(matrix[is_idx]), sr(matrix[oos_idx])
        best = int(np.argmax(s_is))
        rank = float((s_oos < s_oos[best]).sum() + 1) / (N + 1)        # relative rank in (0,1)
        rank = min(max(rank, 1e-6), 1 - 1e-6)
        lambdas.append(math.log(rank / (1 - rank)))
        oos_of_best.append(float(s_oos[best] * math.sqrt(PPY)))
    lam = np.array(lambdas)
    return {"pbo": round(float((lam <= 0).mean()), 3), "splits": int(lam.size), "blocks": s,
            "median_oos_sharpe_of_is_best": round(float(np.median(oos_of_best)), 3)}


def verdict(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Plain-English grade from the robustness evidence (not a promise of future returns)."""
    reasons, score = [], 0
    m = stats.get("metrics") or {}
    rb = stats.get("robustness") or {}
    dsr = (rb.get("deflated_sharpe") or {}).get("dsr")
    t = m.get("t_stat")
    oos = rb.get("is_oos") or {}
    boot = rb.get("bootstrap") or {}
    cost2 = next((c for c in rb.get("cost_sensitivity") or [] if c["multiple"] == 2), None)
    if t is not None:
        if t >= 3:
            score += 2; reasons.append(f"t-stat {t:.1f} clears the t > 3 hurdle for new strategies (Harvey, Liu & Zhu 2016).")
        elif t >= 2:
            score += 1; reasons.append(f"t-stat {t:.1f}: significant by classic standards but below the t > 3 hurdle that accounts for data mining.")
        else:
            score -= 1; reasons.append(f"t-stat {t:.1f}: the average return is not distinguishable from zero.")
    if dsr is not None:
        if dsr >= 0.95:
            score += 2; reasons.append(f"Deflated Sharpe {dsr:.0%} after {rb['deflated_sharpe']['trials']} variant(s) tried — survives the multiple-testing correction.")
        elif dsr >= 0.5:
            reasons.append(f"Deflated Sharpe {dsr:.0%} after {rb['deflated_sharpe']['trials']} variant(s): more likely real than not, but not conclusive.")
        else:
            score -= 2; reasons.append(f"Deflated Sharpe {dsr:.0%} after {rb['deflated_sharpe']['trials']} variant(s): the result is plausibly luck from trying variants.")
    if oos.get("oos_sharpe") is not None and oos.get("is_sharpe"):
        if oos["oos_sharpe"] <= 0:
            score -= 2; reasons.append(f"Out of sample (after {oos['split_date']}) the Sharpe is {oos['oos_sharpe']:.2f} — the edge did not persist.")
        elif oos.get("decay") is not None and oos["decay"] > 0.5:
            score -= 1; reasons.append(f"Sharpe fell {oos['decay']:.0%} out of sample — typical of overfitting or a fading anomaly (McLean & Pontiff 2016 find ~ -58% after publication).")
        else:
            score += 1; reasons.append(f"Out-of-sample Sharpe {oos['oos_sharpe']:.2f} vs {oos['is_sharpe']:.2f} in sample — holds up.")
    if boot.get("sharpe_p05") is not None:
        if boot["sharpe_p05"] > 0:
            score += 1; reasons.append(f"90% bootstrap range of Sharpe {boot['sharpe_p05']:.2f} to {boot['sharpe_p95']:.2f} excludes zero.")
        else:
            reasons.append(f"90% bootstrap range of Sharpe {boot['sharpe_p05']:.2f} to {boot['sharpe_p95']:.2f} includes zero.")
    if cost2 and cost2.get("sharpe") is not None and m.get("sharpe"):
        if cost2["sharpe"] < 0.5 * m["sharpe"]:
            score -= 1; reasons.append(f"Doubling costs cuts the Sharpe to {cost2['sharpe']:.2f} — fragile to execution.")
    fa = rb.get("factor_attribution") or {}
    if fa.get("available") and fa.get("r2") is not None and fa["r2"] > 0.5:
        if fa.get("alpha_t") is not None and fa["alpha_t"] < 2:
            score -= 1
            top = max(fa["loadings"], key=lambda x: abs(x["t"]) if x["factor"] != "Mkt-RF" else 0)
            reasons.append(f"Mostly known factor exposure: alpha after Fama–French 5 + momentum is {fa['alpha_annual']:+.1%}/yr "
                           f"(t = {fa['alpha_t']:.1f}); the biggest tilt is {top['name'].lower()} (β {top['beta']:+.2f}). "
                           "You could get most of this from cheap factor ETFs.")
        elif fa.get("alpha_t") is not None and fa["alpha_t"] >= 3:
            score += 1
            reasons.append(f"Alpha survives the factor model: {fa['alpha_annual']:+.1%}/yr after Fama–French 5 + momentum (t = {fa['alpha_t']:.1f}).")
    if m.get("years") is not None and m["years"] < 5:
        score -= 1; reasons.append(f"Only {m['years']:.0f} years of history — too short to judge.")
    grade = "promising" if score >= 4 else "mixed" if score >= 1 else "weak"
    if grade == "promising" and t is not None and t < 3:
        grade = "mixed"                      # HLZ: below t = 3 the evidence is not conclusive
        reasons.append("Capped at 'mixed' because the t-stat is below 3 — a longer record or a stronger edge is needed.")
    label = {"promising": "Promising — robust on the tests run",
             "mixed": "Mixed — some evidence, not conclusive",
             "weak": "Weak — likely noise or overfit"}[grade]
    return {"grade": grade, "label": label, "score": score, "reasons": reasons}
