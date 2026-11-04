"""
Validation for the options research: chronological segments with a protected holdout, walk-forward selection,
overfitting statistics, uncertainty, leakage and survivorship checks, and the option model's error against CBOE's
observed strategy indices.

Segments (fixed before any experiment; never tuned):
  development   2016-01-01 … 2021-12-31   grids are searched here only
  validation    2022-01-01 … 2023-12-31   the development choice is evaluated here (once per experiment)
  holdout       2024-01-01 … last data     sealed: computed only when explicitly requested, and every reveal is logged
                                           in the registry (tuning after a reveal is no longer out of sample)

Survival criteria for a hypothesis (pre-declared): on validation AND walk-forward out-of-sample returns, net of modelled
costs — Sharpe > 0, 90% block-bootstrap Sharpe interval above 0 for the walk-forward series (excess returns), positive
return at 1.5× option spreads, positive return with every implied volatility 10% lower (added after the CBOE CNDR
replication showed the model over-earns CBOE's iron condor by ~2.3% a year out of sample — before any stage 3/4 run),
deflated Sharpe ≥ 0.90 (excess returns) for the number of configurations tried, and PBO < 0.5 where a grid was searched.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional, Sequence

import numpy as np
import pandas as pd

DEV = ("2016-01-01", "2021-12-31")
VAL = ("2022-01-01", "2023-12-31")
HOLDOUT_START = "2024-01-01"
WF_FIRST_YEAR = 2018                     # walk-forward test years 2018…2023 (two years of history before the first)
CRITERIA = {"sharpe_min": 0.0, "boot_p05_min": 0.0, "stress_spread": 1.5, "stress_iv": 0.9, "dsr_min": 0.90, "pbo_max": 0.5}


def pos(dates: pd.DatetimeIndex, d: str) -> int:
    """Index of the first date on or after `d`."""
    return int(dates.searchsorted(pd.Timestamp(d)))


def walk_forward(series: Dict[str, np.ndarray], dates: pd.DatetimeIndex, rf: np.ndarray, first_year: int = WF_FIRST_YEAR,
                 last: str = VAL[1], min_days: int = 250) -> Dict[str, Any]:
    """Each January from first_year, pick the configuration with the best Sharpe on all history before that date;
    stitch its returns for the year. series: {config key: daily returns on `dates`}. Returns the stitched returns and
    the choices. (Each configuration is its own account; switching at a year boundary ignores positions carried
    across it — documented approximation.)"""
    keys = list(series)
    M = np.column_stack([np.nan_to_num(series[k]) for k in keys])
    ex = M - (rf / 252)[:, None]
    stitched = np.zeros(len(dates))
    choices = []
    end = pd.Timestamp(last)
    for y in range(first_year, end.year + 1):
        a = pos(dates, f"{y}-01-01")
        b = min(pos(dates, f"{y + 1}-01-01"), pos(dates, last) + 1)
        if a < min_days or a >= b:
            continue
        hist = ex[:a]
        active = np.abs(M[:a]).sum(axis=0) > 0
        sd = hist.std(axis=0, ddof=1)
        sh = np.where(active & (sd > 0), hist.mean(axis=0) / np.where(sd > 0, sd, 1) * math.sqrt(252), -np.inf)
        k = int(np.argmax(sh))
        stitched[a:b] = M[a:b, k]
        choices.append({"year": y, "config": keys[k], "trailing_sharpe": round(float(sh[k]), 3) if np.isfinite(sh[k]) else None})
    lo = pos(dates, f"{first_year}-01-01")
    hi = pos(dates, last) + 1
    return {"returns": stitched[lo:hi], "start": lo, "end": hi, "choices": choices}


def bootstrap(r: np.ndarray, n: int = 1000, block: int = 21) -> Dict[str, Any]:
    """Block bootstrap of a return series."""
    from api.quant import robust
    return robust.block_bootstrap(np.asarray(r, float), n=n, block=block)


def trade_bootstrap(rs: np.ndarray, n: int = 2000, seed: int = 7) -> Dict[str, Any]:
    """90% interval of the mean R-multiple (trades resampled with replacement)."""
    rs = np.asarray(rs, float)
    rs = rs[np.isfinite(rs)]
    if rs.size < 20:
        return {}
    rng = np.random.default_rng(seed)
    m = rs[rng.integers(0, rs.size, (n, rs.size))].mean(axis=1)
    return {"mean_r": round(float(rs.mean()), 4), "p05": round(float(np.percentile(m, 5)), 4),
            "p95": round(float(np.percentile(m, 95)), 4), "prob_negative": round(float((m < 0).mean()), 3)}


def overfitting(matrix: np.ndarray, chosen: np.ndarray, n_trials: int, trial_sharpes: Sequence[float]) -> Dict[str, Any]:
    """Overfitting diagnostics: probability of backtest overfitting (CSCV) and the deflated Sharpe ratio for the trials
    run.
    """
    from api.quant import robust
    out: Dict[str, Any] = {"trials": int(n_trials)}
    if matrix.shape[1] >= 2:
        out["pbo"] = robust.pbo_cscv(matrix, s=8)
    per_period = [s / math.sqrt(252) for s in trial_sharpes if s is not None and np.isfinite(s)]
    out["deflated_sharpe"] = robust.deflated_sharpe(np.asarray(chosen, float), n_trials, per_period)
    return out


def survived(val: Dict[str, Any], wf: Dict[str, Any], boot: Dict[str, Any], stress: Dict[str, Any],
             of: Dict[str, Any], iv_stress: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Apply the pre-declared criteria. Every test is listed with its value, so a failure is explained."""
    tests = []

    def add(name, value, ok, need):
        tests.append({"test": name, "value": value, "passed": bool(ok), "needs": need})
    add("validation Sharpe", val.get("sharpe"), (val.get("sharpe") or -1) > CRITERIA["sharpe_min"], "> 0")
    add("walk-forward Sharpe", wf.get("sharpe"), (wf.get("sharpe") or -1) > CRITERIA["sharpe_min"], "> 0")
    add("walk-forward bootstrap Sharpe 5th pct", boot.get("sharpe_p05"), (boot.get("sharpe_p05") or -1) > CRITERIA["boot_p05_min"], "> 0")
    add(f"return at {CRITERIA['stress_spread']}× option spreads", stress.get("cagr"), (stress.get("cagr") or -1) > 0, "> 0")
    if iv_stress is not None:
        add("excess return with implied vols 10% lower (model-risk stress)", iv_stress.get("excess_cagr"),
            (iv_stress.get("excess_cagr") or -1) > 0, "> 0")
    dsr = (of.get("deflated_sharpe") or {}).get("dsr")
    add("deflated Sharpe (trials-adjusted)", None if dsr is None else round(dsr, 3), (dsr or 0) >= CRITERIA["dsr_min"], "≥ 0.90")
    pbo = (of.get("pbo") or {}).get("pbo")
    if pbo is not None:
        add("probability of backtest overfitting", pbo, pbo < CRITERIA["pbo_max"], "< 0.5")
    return {"survived": all(t["passed"] for t in tests), "tests": tests}


# ── Leakage and survivorship ────────────────────────────────────────────────
def prefix_invariance(panel, surf_fn, feat_fn, cut_frac: float = 0.7) -> Dict[str, Any]:
    """Recompute features on data truncated at a cut date: every value on or before the cut must be identical — a
    feature that changes when later data are removed is using the future."""
    from api.quant.optresearch import market
    T = len(panel.dates)
    cut = int(T * cut_frac)
    full = feat_fn(panel, surf_fn(panel))
    short_panel = market.Panel(panel.dates[:cut], panel.tickers, {k: v[:cut] for k, v in panel.a.items()}, panel.rf[:cut],
                               panel.info, dict(panel.meta))
    short_panel.meta.pop("_qy", None)
    part = feat_fn(short_panel, surf_fn(short_panel))
    bad = {}
    for k, v in part.items():
        if not isinstance(v, np.ndarray) or v.ndim < 1:
            continue
        a, b = np.asarray(full[k])[:cut], np.asarray(v)
        same = (a == b) | (np.isnan(a.astype(float)) & np.isnan(b.astype(float))) if a.dtype.kind in "fc" else (a == b)
        if not np.all(same):
            bad[k] = int((~same).sum())
    return {"cut": str(panel.dates[cut - 1].date()), "passed": not bad, "differing_values": bad}


# ── The option model against CBOE's observed strategy indices ────────────────
def replicate_cboe(panel, surf: Dict[str, Any], atm_scales: Sequence[float] = (0.80, 0.84, 0.88, 0.92, 0.96),
                   put_slopes: Sequence[float] = (1.5, 2.0, 3.0, 4.0), calib_end: str = "2017-12-31") -> Dict[str, Any]:
    """Price CBOE's PutWrite (PUT: sell the monthly ATM put, collateral = strike in T-bills) and Iron Condor (CNDR:
    short ~20-delta put & call, long ~5-delta wings, monthly, held to expiry; collateral ≈ the index level — CNDR's
    published volatility of ~7% a year rules out collateral equal to the condor's maximum loss) on SPY with the
    OBSERVED VIX term structure, at mid prices, and compare monthly returns with CBOE's published series.

    Calibration on ≤ calib_end only: the VIX → at-the-money scale from PUT (an unambiguous contract), then the
    put-side smile slope from CNDR (the intercept of CBOE's excess return regressed on the model's — a scale-free
    measure of premium bias). 2018 onward is out of sample. SPX vs SPY, CBOE's exact strike/price rules and
    collateral conventions all add to the tracking error, which is reported, not hidden."""
    from api.quant.optresearch import pricing
    from api.quant.optresearch import vol as volmod
    j = panel.col("SPY")
    S = panel.a["px"][:, j].astype(float)
    dates = panel.dates
    day = dates.values.astype("datetime64[D]").astype(np.int64)
    rf = panel.rf
    exp_days, exp_pos = pricing.expiry_table(dates, False)
    q = 0.018
    rolls = [(int(p), int(exp_pos[i + 1]), int(exp_days[i + 1])) for i, p in enumerate(exp_pos[:-1])
             if 0 <= p < len(dates) - 1 and exp_pos[i + 1] < len(dates) and p >= pos(dates, "2011-01-01")]
    put_idx, cndr_idx = volmod.cboe("PUT"), volmod.cboe("CNDR")
    base_scale = volmod.ATM_SCALE["index"]

    def atm_at(t, T, scale):
        rat = volmod.term_ratio(surf["pillars"], surf["P"], np.array([t]), np.array([max(T, 9 / 365)]))[0]
        return float(surf["atm"][t, j] / base_scale * scale * (rat if np.isfinite(rat) else 1.0))

    def run(scale, slope, which):
        out = []
        for p0, p1, eday in rolls:
            T = (eday - day[p0]) / 365.0
            if T <= 0:
                continue
            a0, r0, S0, S1 = atm_at(p0, T, scale), float(rf[p0]), S[p0], S[p1]
            cash = float(np.sum(rf[p0:p1] / 252))
            val = lambda K_, c_: float(pricing.bsm(S0, K_, T, r0, q, pricing.smile_vol(a0, S0, K_, T, "index", slope, 1.0), c_)["value"])
            if which == "put":
                out.append((p0, p1, (val(S0, False) - max(S0 - S1, 0.0)) / S0 + cash, cash))
            else:
                ks = {nm: float(pricing.strike_for_delta(np.array([S0]), np.array([T]), np.array([r0]), np.array([q]),
                                                          np.array([a0]), dl, c, "index", put_slope=slope, call_slope=1.0)[0])
                      for nm, dl, c in (("ps", 0.20, False), ("pl", 0.05, False), ("cs", 0.20, True), ("cl", 0.05, True))}
                credit = val(ks["ps"], False) - val(ks["pl"], False) + val(ks["cs"], True) - val(ks["cl"], True)
                payoff = (max(ks["ps"] - S1, 0) - max(ks["pl"] - S1, 0)) + (max(S1 - ks["cs"], 0) - max(S1 - ks["cl"], 0))
                out.append((p0, p1, (credit - payoff) / S0 + cash, cash))
        return out

    def compare(model, idx_series, a, b):
        if idx_series is None or not model:
            return None
        full = idx_series.reindex(idx_series.index.union(dates)).ffill()
        rows = []
        for p0, p1, x, cash in model:
            if not (pd.Timestamp(a) <= dates[p1] <= pd.Timestamp(b)):
                continue
            o0, o1 = full.get(dates[p0]), full.get(dates[p1])
            if o0 and o1 and np.isfinite(o0) and np.isfinite(o1):
                rows.append((x - cash, o1 / o0 - 1 - cash))
        if len(rows) < 12:
            return None
        x, y = np.array(rows).T
        beta, alpha = np.polyfit(x, y, 1)
        return {"months": int(len(x)), "corr": round(float(np.corrcoef(x, y)[0, 1]), 3),
                "model_excess_annual": round(float(x.mean() * 12), 4), "cboe_excess_annual": round(float(y.mean() * 12), 4),
                "beta": round(float(beta), 3), "alpha_annual": round(float(alpha * 12), 4),
                "tracking_error_annual": round(float((x - y).std() * math.sqrt(12)), 4),
                "mean_gap_annual": round(float((x - y).mean() * 12), 4)}

    last = str(dates[-1].date())
    cal_put = []
    for sc in atm_scales:
        c = compare(run(sc, 3.0, "put"), put_idx, "2011-01-01", calib_end)
        if c:
            cal_put.append({"atm_scale": sc, **c})
    best_scale = min(cal_put, key=lambda c: abs(c["mean_gap_annual"]))["atm_scale"] if cal_put else base_scale
    cal_cndr = []
    for sl in put_slopes:
        c = compare(run(best_scale, sl, "cndr"), cndr_idx, "2011-01-01", calib_end)
        if c:
            cal_cndr.append({"put_slope": sl, **c})
    best_slope = min(cal_cndr, key=lambda c: abs(c["alpha_annual"]))["put_slope"] if cal_cndr else 3.0
    return {"note": "Model at mid prices (no costs) vs CBOE's published series; excess returns over T-bills. "
                    "PUT calibrates the ATM scale, CNDR the put-side smile slope, on 2011–2017 only.",
            "calibration_put": cal_put, "calibration_cndr": cal_cndr, "atm_scale": best_scale,
            "atm_scale_vs_default": round(best_scale / base_scale, 4), "chosen_put_slope": best_slope,
            "out_of_sample": {"put": compare(run(best_scale, best_slope, "put"), put_idx, "2018-01-01", last),
                              "cndr": compare(run(best_scale, best_slope, "cndr"), cndr_idx, "2018-01-01", last)},
            "before_calibration_out_of_sample": {
                "put": compare(run(base_scale, 3.0, "put"), put_idx, "2018-01-01", last),
                "cndr": compare(run(base_scale, 3.0, "cndr"), cndr_idx, "2018-01-01", last)}}
