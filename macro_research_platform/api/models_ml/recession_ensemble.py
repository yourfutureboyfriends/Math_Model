"""
US recession probability: term spread + credit ensemble, with its own out-of-sample record.

Target: an NBER recession in any of the next 12 months (the Federal Reserve staff definition).

Model: the average of four probits, each fitted on monthly data since 1973
    P1 = Φ(a + b·TS + c·EBP)              TS   = 10-year minus 3-month zero-coupon yield (GSW curve)
    P2 = Φ(a + b·NTFS + c·EBP)            NTFS = near-term forward spread (Engstrom & Sharpe, 2019)
    P3 = Φ(a + b·TS + c·EBP + d·PAY6)     EBP  = Gilchrist–Zakrajšek excess bond premium (Fed monthly file)
    P4 = Φ(a + b·NTFS + c·EBP + d·PAY6)   PAY6 = nonfarm payrolls, annualised 6-month growth, as published in
                                                 each month (ALFRED vintages of PAYEMS — real-time, not revised)
as two pairs — curve + credit (P1, P2) and the same with payrolls (P3, P4) — each pair averaged and Platt-recalibrated
on its own past forecasts (below), then the two averaged. Without payrolls it falls back to the first pair.

Why: in Fed staff tests (Pike & Vazquez-Grande, FEDS Notes 2019) probits pairing a term spread with the EBP were the
most robust out of sample; the EBP carries credit-market stress the curve misses. Our own pseudo-out-of-sample test
(refit every January on months whose 12-month window — plus a 12-month NBER announcement lag — had closed) from 1985:
the ensemble had AUROC 0.88 and a Brier skill of +0.28 vs the base rate; the previous headline (10Y–3M + policy rate,
fitted in-sample) had AUROC 0.65 and +0.14, and since 2005 it was worse than the base rate (−0.24) where the ensemble
stayed positive. The record is recomputed live here (`evaluation`) rather than quoted.

Recalibration: raw readings of 70%+ were followed by a recession only 46% of the time (the 2022–24 inverted curve,
no recession). The published probability is Platt-recalibrated — a logistic map of the raw probability's log-odds,
learned each year only from earlier out-of-sample forecasts whose outcomes were known (`learned_platt`). Out of
sample 1985–2025 it raised the Brier skill from +0.28 to +0.31 (since 2005: +0.09 to +0.12) and cut log loss from
0.410 to 0.380; ranking dipped (AUROC 0.88 → 0.85) because the map is re-learned each year — within a year it keeps
the order. A hard ceiling was tested too and rejected: it flattened every high reading to one value. Readings of 70%+
remain over-confident (about half were followed by recession). The raw reading is kept alongside.

Labour market: the 2022–24 false alarm had an inverted curve and strong hiring. Adding payroll momentum alone
improved ranking and Brier but blew up log loss after the COVID trough (payrolls had collapsed, the recession had
already ended); averaging the curve+credit probits with their payroll versions improved every measure, 1985–2025 out of
sample and recalibrated: AUROC 0.850 → 0.865 (since 2005: 0.821 → 0.844), Brier 0.127 → 0.117 (0.141 → 0.127), log
loss 0.380 → 0.345 (0.413 → 0.363), and readings of 70%+ were followed by recession 61% of the time instead of 48%
(since 2005: 69% vs 50%). Sahm-rule, unemployment-change and jobless-claims variants were tested and scored worse.

Point in time: trained and scored on payrolls as they were known each month (FRED/ALFRED vintages). With revised
payrolls the record looked better (Brier skill +0.37, since 2005 +0.21); as known at the time it is +0.32 / +0.16 —
the record shown is the real-time one. The EBP has no vintages, so a fully real-time variant (Moody's Baa – 10Y spread,
never revised, in place of the EBP) is scored alongside as a lower bound (`robustness`): about +0.32 / +0.13.

Tested and not adopted: a multi-country model (yield curve and GDP-based 'technical recessions' pooled across seven
economies on FRED) ranked US recessions poorly (AUROC 0.64; 0.50 since 2005) — free cross-country data has no credit
premium or payroll equivalent, which carry most of the skill — and blending it in did not help consistently.

Caveats carried with the result: the EBP history is re-estimated by the Fed (not a real-time vintage — see the Baa
variant); NBER dates are final, not as first announced.
Data: free Federal Reserve files; payrolls from FRED (the platform's key).
"""
from __future__ import annotations

import io
import logging
import threading
import time
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

TTL = 12 * 3600
EVAL_START = 1985
_lock = threading.Lock()
_mem: Dict[str, Any] = {"ts": 0.0, "data": None}


# ── data ──────────────────────────────────────────────────────────────────────
def _fetch_curve() -> Dict[str, Any]:
    """Monthly-average TS and NTFS from the GSW curve parameters, plus the latest daily values."""
    import pandas as pd
    import requests
    from api import research_indicators as ri
    from api.calculations import systemic_risk as sr
    r = requests.get(ri.GSW_URL, headers=ri._UA, timeout=180)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), skiprows=9,
                     usecols=lambda c: c in ("Date", "BETA0", "BETA1", "BETA2", "BETA3", "TAU1", "TAU2"))
    df = df.dropna(subset=["BETA0", "BETA1", "BETA2", "TAU1"])
    df["Date"] = pd.to_datetime(df["Date"])
    df = df[df["Date"] >= "1972-01-01"]
    p = list(zip(df.BETA0, df.BETA1, df.BETA2, df.BETA3.fillna(0.0), df.TAU1, df.TAU2.fillna(1.0)))
    df["ts"] = [sr.svensson_zero_yield(10, *x) - sr.svensson_zero_yield(0.25, *x) for x in p]
    df["ntfs"] = [sr.near_term_forward_spread(x) for x in p]
    daily = df[["Date", "ts", "ntfs"]].dropna()
    mon = daily.set_index("Date")[["ts", "ntfs"]].resample("MS").mean().dropna()
    last = daily.iloc[-1]
    return {"monthly": {d.strftime("%Y-%m"): [round(float(a), 4), round(float(b), 4)] for d, (a, b) in mon.iterrows()},
            "latest": {"date": last["Date"].strftime("%Y-%m-%d"), "ts": round(float(last["ts"]), 4),
                       "ntfs": round(float(last["ntfs"]), 4)}}


def _fred():
    from api.config import FRED_API_KEY
    from fredapi import Fred
    if not FRED_API_KEY:
        raise ValueError("FRED_API_KEY not set")
    return Fred(api_key=FRED_API_KEY)


def _fetch_payrolls() -> Dict[str, Any]:
    """Nonfarm payrolls: the latest levels, and the 6-month growth as it was known in each month (ALFRED vintages)."""
    import pandas as pd
    f = _fred()
    s = f.get_series("PAYEMS", observation_start="1970-01-01").dropna()
    rel = f.get_series_all_releases("PAYEMS")
    rel["date"] = pd.to_datetime(rel["date"])
    rel["realtime_start"] = pd.to_datetime(rel["realtime_start"])
    rel = rel.dropna(subset=["value"]).sort_values("realtime_start")
    known: Dict[pd.Timestamp, float] = {}
    rt: Dict[str, float] = {}
    recs = list(zip(rel["realtime_start"], rel["date"], rel["value"].astype(float)))
    i = 0
    for month in pd.date_range("1972-01-01", pd.Timestamp.today().normalize(), freq="MS"):
        asof = month + pd.Timedelta(days=14)                    # the release in the first week of the month is in
        while i < len(recs) and recs[i][0] <= asof:
            known[recs[i][1]] = recs[i][2]
            i += 1
        a, b = month - pd.DateOffset(months=1), month - pd.DateOffset(months=7)
        if a in known and b in known and known[b] > 0:
            rt[month.strftime("%Y-%m")] = float(np.log(known[a] / known[b]) * 200)
    return {"monthly": {d.strftime("%Y-%m"): float(v) for d, v in s.items()}, "pay6_real_time": rt}


def _fetch_baa() -> Dict[str, float]:
    """Moody's Baa corporate yield minus the 10-year Treasury, monthly (never revised)."""
    f = _fred()
    spr = (f.get_series("BAA") - f.get_series("GS10")).dropna()
    return {d.strftime("%Y-%m"): float(v) for d, v in spr.items()}


def _pay6(level: Dict[str, float], month: str) -> Optional[float]:
    """Annualised 6-month payroll growth (%) known at `month`: the previous month's release vs six months before it."""
    y, m = map(int, month.split("-"))
    k = y * 12 + m - 1
    a, b = f"{(k - 1) // 12}-{(k - 1) % 12 + 1:02d}", f"{(k - 7) // 12}-{(k - 7) % 12 + 1:02d}"
    if a not in level or b not in level or level[b] <= 0:
        return None
    return float(np.log(level[a] / level[b]) * 200)


def _inputs():
    from api import research_indicators as ri
    curve, c_status = ri._cached("gsw_ts_ntfs", _fetch_curve)
    ebp_rows, e_status = ri._cached("ebp", ri._fetch_ebp)
    pay, p_status = ri._cached("payems_rt", _fetch_payrolls)
    baa, _ = ri._cached("baa_spread", _fetch_baa)
    if not curve or not ebp_rows:
        return None, {"curve": c_status, "ebp": e_status, "payrolls": p_status}
    ebp = {r[0]: float(r[2]) for r in ebp_rows}
    level = (pay or {}).get("monthly") or {}
    rt = (pay or {}).get("pay6_real_time") or {}
    baa = baa or {}
    months = sorted(m for m in curve["monthly"] if m in ebp)
    labels = ri._recession_ahead(months, 12)
    rows = [{"month": m, "ts": curve["monthly"][m][0], "ntfs": curve["monthly"][m][1], "ebp": ebp[m],
             "pay6": rt.get(m), "baa": baa.get(m), "y": labels[m]} for m in months]
    pay_now = None
    if level:
        last = max(level)
        y_, m_ = map(int, last.split("-"))
        nxt = f"{y_ + m_ // 12}-{m_ % 12 + 1:02d}"           # the month after the latest release: uses it
        pay_now = {"pay6": _pay6(level, nxt), "as_of": last}
    return {"rows": rows, "latest_curve": curve["latest"], "ebp_as_of": max(ebp), "ebp_latest": ebp[max(ebp)],
            "payrolls_now": pay_now}, {"curve": c_status, "ebp": e_status, "payrolls": p_status}


# ── estimation ────────────────────────────────────────────────────────────────
def probit_fit(X: np.ndarray, y: np.ndarray) -> Optional[np.ndarray]:
    """Probit by Newton–Raphson; X includes the constant column. None if it does not converge."""
    from scipy.stats import norm
    beta = np.zeros(X.shape[1])
    for _ in range(100):
        z = X @ beta
        p = np.clip(norm.cdf(z), 1e-10, 1 - 1e-10)
        phi = norm.pdf(z)
        grad = X.T @ (phi * (y - p) / (p * (1 - p)))
        hess = -(X * (phi ** 2 / (p * (1 - p)))[:, None]).T @ X
        try:
            step = np.linalg.solve(hess, grad)
        except np.linalg.LinAlgError:
            return None
        beta = beta - step
        if not np.all(np.isfinite(beta)):
            return None
        if np.abs(step).max() < 1e-9:
            return beta
    return beta


def probit_prob(beta: np.ndarray, x: List[float]) -> float:
    from scipy.stats import norm
    return float(norm.cdf(beta[0] + float(np.dot(beta[1:], x))))


SPECS = {"ts_ebp": ["ts", "ebp"], "ntfs_ebp": ["ntfs", "ebp"]}
SPECS_PAY = {"ts_ebp_pay": ["ts", "ebp", "pay6"], "ntfs_ebp_pay": ["ntfs", "ebp", "pay6"]}
SPECS_LABOUR = {**SPECS, **SPECS_PAY}
GROUPS_BASE = {"curve_credit": SPECS}
GROUPS_LABOUR = {"curve_credit": SPECS, "with_payrolls": SPECS_PAY}
GROUPS_REAL_TIME = {"curve_credit": {"ts_baa": ["ts", "baa"], "ntfs_baa": ["ntfs", "baa"]},
                    "with_payrolls": {"ts_baa_pay": ["ts", "baa", "pay6"], "ntfs_baa_pay": ["ntfs", "baa", "pay6"]}}
# the previous headline's shape, for the comparison: term spread + the short rate (3-month yield ≈ policy rate)
BENCH = {"ts_only": ["ts"]}


def _design(rows, cols):
    return np.column_stack([np.ones(len(rows))] + [np.array([r[c] for r in rows], float) for c in cols])


def ensemble_prob(fits: Dict[str, np.ndarray], x: Dict[str, float], specs: Optional[Dict[str, List[str]]] = None) -> float:
    specs = specs or SPECS
    return float(np.mean([probit_prob(fits[k], [x[c] for c in cols]) for k, cols in specs.items()]))


def _auc(p: np.ndarray, y: np.ndarray) -> Optional[float]:
    pos, neg = p[y == 1], p[y == 0]
    if not len(pos) or not len(neg):
        return None
    return float(np.mean(pos[:, None] > neg[None, :]) + 0.5 * np.mean(pos[:, None] == neg[None, :]))


CAL_MIN_FORECASTS, CAL_MIN_POSITIVES = 120, 10


def _logit(p):
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def learned_platt(probs: List[float], outcomes: List[int]) -> Optional[List[float]]:
    """[a, b] of P = 1 / (1 + exp(−(a + b·logit(raw)))) fitted on past forecasts (lightly ridge-regularised toward
    the identity map a=0, b=1); None with too little history."""
    if len(probs) < CAL_MIN_FORECASTS or sum(outcomes) < CAL_MIN_POSITIVES:
        return None
    X = np.column_stack([np.ones(len(probs)), _logit(probs)])
    y = np.asarray(outcomes, float)
    prior, lam = np.array([0.0, 1.0]), 1e-2
    b = prior.copy()
    for _ in range(60):
        p = 1 / (1 + np.exp(-(X @ b)))
        grad = X.T @ (y - p) - lam * (b - prior)
        hess = -(X * (p * (1 - p))[:, None]).T @ X - lam * np.eye(2)
        step = np.linalg.solve(hess, grad)
        b = b - step
        if np.abs(step).max() < 1e-9:
            break
    return [float(b[0]), float(b[1])]


def platt_apply(coef: Optional[List[float]], p: float) -> float:
    if coef is None:
        return p
    return float(1 / (1 + np.exp(-(coef[0] + coef[1] * float(_logit(p))))))


def evaluate(rows: List[Dict[str, Any]], start_year: int = EVAL_START, announce_lag: int = 12,
             groups: Optional[Dict[str, Dict[str, List[str]]]] = None, return_preds: bool = False) -> Optional[Dict[str, Any]]:
    """Pseudo-out-of-sample: each January refit on months whose label was known (12-month window + NBER lag),
    forecast that year's months. Scores the ensemble, the term spread alone and the base rate."""
    groups = groups or GROUPS_BASE
    specs = {k: c for g in groups.values() for k, c in g.items()}
    need = {c for cols in specs.values() for c in cols}
    graw: Dict[str, List[float]] = {g: [] for g in groups}
    by_month = {r["month"]: r for r in rows if all(r.get(c) is not None for c in need)}
    months = sorted(by_month)
    preds: Dict[str, List[float]] = {"ensemble": [], "ensemble_calibrated": [], "term_spread_only": [], "base_rate": []}
    ys: List[int] = []
    test_months: List[str] = []
    last_year = int(months[-1][:4])
    for yr in range(start_year, last_year + 1):
        cut_y, cut_m = divmod((yr * 12) - (12 + announce_lag), 12)
        cutoff = f"{cut_y}-{cut_m + 1:02d}"
        train = [by_month[m] for m in months if m < cutoff and by_month[m]["y"] is not None]
        test = [by_month[m] for m in months if m[:4] == str(yr) and by_month[m]["y"] is not None]
        if not test or sum(r["y"] for r in train) < 3:
            continue
        ytr = np.array([r["y"] for r in train], float)
        fits = {k: probit_fit(_design(train, c), ytr) for k, c in {**specs, **BENCH}.items()}
        if any(v is None for v in fits.values()):
            continue
        # recalibration per group, learned from its earlier forecasts whose outcome (window + lag) was known by now
        known = [i for i, m in enumerate(test_months) if m < cutoff]
        cals = {g: learned_platt([graw[g][i] for i in known], [ys[i] for i in known]) for g in groups}
        for r in test:
            ps = {g: ensemble_prob(fits, r, sp) for g, sp in groups.items()}
            for g, v in ps.items():
                graw[g].append(v)
            preds["ensemble"].append(float(np.mean(list(ps.values()))))
            preds["ensemble_calibrated"].append(float(np.mean([platt_apply(cals[g], v) for g, v in ps.items()])))
            preds["term_spread_only"].append(probit_prob(fits["ts_only"], [r["ts"]]))
            preds["base_rate"].append(float(ytr.mean()))
            ys.append(int(r["y"]))
            test_months.append(r["month"])
    if not ys:
        return None
    y = np.array(ys)
    base_bs = float(np.mean((np.array(preds["base_rate"]) - y) ** 2))
    out: Dict[str, Any] = {}
    for k, p in preds.items():
        p = np.clip(np.array(p), 1e-6, 1 - 1e-6)
        bs = float(np.mean((p - y) ** 2))
        out[k] = {"auroc": None if k == "base_rate" else round(_auc(p, y), 3), "brier": round(bs, 4),
                  "brier_skill_vs_base_rate": round(1 - bs / base_bs, 3) if base_bs else None,
                  "log_loss": round(float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))), 4)}
    p = np.array(preds["ensemble_calibrated"])
    # Four buckets, each with a Wilson 95% range: finer buckets held too few forecasts (and few separate recession
    # episodes) to read — e.g. a 50–70% bucket of 45 months swung on one episode. Months within an episode are not
    # independent, so even these ranges are on the narrow side.
    edges = [0, .1, .3, .7, 1.0001]
    calib = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        k = (p >= lo) & (p < hi)
        if k.any():
            n, f = int(k.sum()), float(y[k].mean())
            z = 1.96
            centre = (f + z * z / (2 * n)) / (1 + z * z / n)
            half = z * np.sqrt(f * (1 - f) / n + z * z / (4 * n * n)) / (1 + z * z / n)
            calib.append({"range": f"{lo:.0%}–{min(hi, 1):.0%}", "forecasts": n,
                          "mean_probability": round(float(p[k].mean()), 3), "recession_frequency": round(f, 3),
                          "frequency_95": [round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)]})
    since_2005 = np.array([m >= "2005-01" for m in test_months])
    sub = {}
    if since_2005.any():
        ys5, b5 = y[since_2005], np.mean((np.array(preds["base_rate"])[since_2005] - y[since_2005]) ** 2)
        for k in ("ensemble_calibrated", "ensemble", "term_spread_only"):
            pk = np.array(preds[k])[since_2005]
            sub[k] = {"auroc": round(_auc(pk, ys5), 3), "brier_skill_vs_base_rate": round(1 - float(np.mean((pk - ys5) ** 2)) / b5, 3)}
    labelled_now = [i for i, m in enumerate(test_months)]
    return {"forecasts": len(ys), "recession_months": int(y.sum()), "from": test_months[0], "to": test_months[-1],
            "models": out, "since_2005": sub, "calibration": calib,
            "calibration_now": {g: learned_platt([graw[g][i] for i in labelled_now], [ys[i] for i in labelled_now]) for g in groups},
            **({"preds": {"months": test_months, "y": ys, "calibrated": preds["ensemble_calibrated"]}} if return_preds else {}),
            "method": f"Refit every January from {start_year} on months whose 12-month window and a {announce_lag}-month "
                      "NBER announcement lag had closed; forecasts that year's months; scored against NBER recessions "
                      "within 12 months. Brier skill > 0 beats always forecasting the training base rate."}


def compute() -> Dict[str, Any]:
    data, status = _inputs()
    if not data:
        return {"available": False, "reason": "Federal Reserve curve or EBP file unavailable", "source_status": status}
    rows = data["rows"]
    pay_now = (data.get("payrolls_now") or {}).get("pay6")
    groups = GROUPS_LABOUR if pay_now is not None else GROUPS_BASE
    specs = {k: c for g in groups.values() for k, c in g.items()}
    need = {c for cols in specs.values() for c in cols}
    usable = [r for r in rows if all(r.get(c) is not None for c in need)]
    labelled = [r for r in usable if r["y"] is not None]
    y = np.array([r["y"] for r in labelled], float)
    fits = {k: probit_fit(_design(labelled, c), y) for k, c in specs.items()}
    if any(v is None for v in fits.values()):
        return {"available": False, "reason": "probit did not converge", "source_status": status}
    lc = data["latest_curve"]
    x_now = {"ts": lc["ts"], "ntfs": lc["ntfs"], "ebp": data["ebp_latest"], "pay6": pay_now}
    parts = {k: probit_prob(fits[k], [x_now[c] for c in cols]) for k, cols in specs.items()}
    ev = evaluate(rows, groups=groups)
    cal = (ev or {}).get("calibration_now") or {}
    robust = None
    if groups is GROUPS_LABOUR and sum(r.get("baa") is not None for r in rows) > 300:
        rv = evaluate(rows, groups=GROUPS_REAL_TIME)
        if rv:
            m_, s5 = rv["models"]["ensemble_calibrated"], rv["since_2005"].get("ensemble_calibrated") or {}
            robust = {"model": "Fully real-time variant: Moody's Baa – 10Y spread (never revised) in place of the EBP",
                      "auroc": m_["auroc"], "brier_skill_vs_base_rate": m_["brier_skill_vs_base_rate"],
                      "since_2005": s5, "from": rv["from"], "to": rv["to"]}

    def headline(x):                                    # each group averaged, recalibrated, then the groups averaged
        ps = {g: ensemble_prob(fits, x, sp) for g, sp in groups.items()}
        return float(np.mean(list(ps.values()))), float(np.mean([platt_apply(cal.get(g), v) for g, v in ps.items()]))
    raw, prob = headline(x_now)
    # carry for the duration call (regime.duration_tilt): today's 10Y–3M spread against its own 5-year norm
    hist_ts = [r["ts"] for r in rows[-61:-1]]
    carry = None
    if len(hist_ts) >= 24:
        mu, sd = float(np.mean(hist_ts)), float(np.std(hist_ts, ddof=1))
        if sd > 0:
            carry = {"z": round((lc["ts"] - mu) / sd, 3), "term_spread_pp": round(lc["ts"], 3),
                     "mean_5y_pp": round(mu, 3), "sd_5y_pp": round(sd, 3), "as_of": lc["date"]}
    hist = [{"date": r["month"], "probability": round(headline(r)[1], 4)} for r in usable[-24:]]
    return {
        "available": True, "probability": round(prob, 4), "raw_probability": round(raw, 4),
        "recalibration": {g: ([round(c, 4) for c in v] if v else None) for g, v in cal.items()},
        "components": {k: round(v, 4) for k, v in parts.items()},
        "inputs": {"term_spread_10y_3m_pp": round(lc["ts"], 3), "near_term_forward_spread_pp": round(lc["ntfs"], 3),
                   "curve_as_of": lc["date"], "excess_bond_premium_pp": round(data["ebp_latest"], 3), "ebp_as_of": data["ebp_as_of"],
                   "payroll_growth_6m_annualised_pct": round(pay_now, 2) if pay_now is not None else None,
                   "payrolls_as_of": (data.get("payrolls_now") or {}).get("as_of")},
        "coefficients": {k: [round(float(b), 4) for b in v] for k, v in fits.items()},
        "training_months": len(labelled), "history": hist,
        "evaluation": {**ev, "robustness": robust} if ev else ev,
        "duration_carry": carry,
        "target": "NBER recession in any of the next 12 months",
        "model": ("Term spread + credit + payrolls ensemble (four probits, recalibrated)" if groups is GROUPS_LABOUR else
                  "Term spread + credit ensemble (10Y–3M + EBP, forward spread + EBP; probit average)"),
        "sources": ["Federal Reserve GSW zero-coupon curve (feds200628)", "Federal Reserve excess bond premium (ebp_csv)"]
                   + (["FRED/ALFRED PAYEMS vintages (payrolls as first published)"] if groups is GROUPS_LABOUR else []),
        "source_status": status,
        "caveats": ["EBP history is re-estimated by the Fed, not a real-time vintage",
                    *(["Payrolls as known at the time (ALFRED vintages)"] if groups is GROUPS_LABOUR else
                      ["Payrolls unavailable: running without the labour-market probits"]),
                    "NBER dates are final, not as first announced",
                    "Platt-recalibrated on its own past out-of-sample forecasts" if any(cal.values()) else "Not recalibrated: too little history"],
    }


def get_recession_ensemble(force: bool = False) -> Dict[str, Any]:
    """Cached twice a day (the inputs are monthly / daily files); never raises."""
    if not force and _mem["data"] is not None and time.time() - _mem["ts"] < TTL:
        return _mem["data"]
    with _lock:
        if not force and _mem["data"] is not None and time.time() - _mem["ts"] < TTL:
            return _mem["data"]
        try:
            data = compute()
        except Exception as e:                                     # noqa: BLE001 — reported, not raised
            logger.warning("[recession-ensemble] unavailable: %s", e)
            data = {"available": False, "reason": f"{type(e).__name__}: {e}"}
        if data.get("available") or _mem["data"] is None:
            _mem.update(ts=time.time(), data=data)
        return _mem["data"]
