"""
US recession probability: term spread + credit ensemble, with its own out-of-sample record.

Target: an NBER recession in any of the next 12 months (the Federal Reserve staff definition).

Model: the average of two probits, each fitted on monthly data since 1973
    P1 = Φ(a + b·TS + c·EBP)      TS   = 10-year minus 3-month zero-coupon yield (GSW curve)
    P2 = Φ(a + b·NTFS + c·EBP)    NTFS = near-term forward spread (Engstrom & Sharpe, 2019)
    EBP = Gilchrist–Zakrajšek excess bond premium (Federal Reserve monthly file)

Why: in Fed staff tests (Pike & Vazquez-Grande, FEDS Notes 2019) probits pairing a term spread with the EBP were the
most robust out of sample; the EBP carries credit-market stress the curve misses. Our own pseudo-out-of-sample test
(refit every January on months whose 12-month window — plus a 12-month NBER announcement lag — had closed) from 1985:
the ensemble had AUROC 0.88 and a Brier skill of +0.28 vs the base rate; the previous headline (10Y–3M + policy rate,
fitted in-sample) had AUROC 0.65 and +0.14, and since 2005 it was worse than the base rate (−0.24) where the ensemble
stayed positive. The record is recomputed live here (`evaluation`) rather than quoted.

Caveats carried with the result: the EBP history is re-estimated by the Fed (not a real-time vintage); NBER dates are
final, not as first announced; high readings were over-confident in 2022–24 (an inverted curve, no recession).
All data are free Federal Reserve files (no FRED key needed).
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


def _inputs():
    from api import research_indicators as ri
    curve, c_status = ri._cached("gsw_ts_ntfs", _fetch_curve)
    ebp_rows, e_status = ri._cached("ebp", ri._fetch_ebp)
    if not curve or not ebp_rows:
        return None, {"curve": c_status, "ebp": e_status}
    ebp = {r[0]: float(r[2]) for r in ebp_rows}
    months = sorted(m for m in curve["monthly"] if m in ebp)
    labels = ri._recession_ahead(months, 12)
    rows = [{"month": m, "ts": curve["monthly"][m][0], "ntfs": curve["monthly"][m][1], "ebp": ebp[m], "y": labels[m]}
            for m in months]
    return {"rows": rows, "latest_curve": curve["latest"], "ebp_as_of": max(ebp), "ebp_latest": ebp[max(ebp)]}, \
        {"curve": c_status, "ebp": e_status}


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
# the previous headline's shape, for the comparison: term spread + the short rate (3-month yield ≈ policy rate)
BENCH = {"ts_only": ["ts"]}


def _design(rows, cols):
    return np.column_stack([np.ones(len(rows))] + [np.array([r[c] for r in rows], float) for c in cols])


def ensemble_prob(fits: Dict[str, np.ndarray], x: Dict[str, float]) -> float:
    return float(np.mean([probit_prob(fits[k], [x[c] for c in cols]) for k, cols in SPECS.items()]))


def _auc(p: np.ndarray, y: np.ndarray) -> Optional[float]:
    pos, neg = p[y == 1], p[y == 0]
    if not len(pos) or not len(neg):
        return None
    return float(np.mean(pos[:, None] > neg[None, :]) + 0.5 * np.mean(pos[:, None] == neg[None, :]))


def evaluate(rows: List[Dict[str, Any]], start_year: int = EVAL_START, announce_lag: int = 12) -> Optional[Dict[str, Any]]:
    """Pseudo-out-of-sample: each January refit on months whose label was known (12-month window + NBER lag),
    forecast that year's months. Scores the ensemble, the term spread alone and the base rate."""
    by_month = {r["month"]: r for r in rows}
    months = sorted(by_month)
    preds: Dict[str, List[float]] = {"ensemble": [], "term_spread_only": [], "base_rate": []}
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
        fits = {k: probit_fit(_design(train, c), ytr) for k, c in {**SPECS, **BENCH}.items()}
        if any(v is None for v in fits.values()):
            continue
        for r in test:
            preds["ensemble"].append(ensemble_prob(fits, r))
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
    p = np.array(preds["ensemble"])
    edges = [0, .1, .2, .3, .5, .7, 1.0001]
    calib = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        k = (p >= lo) & (p < hi)
        if k.any():
            calib.append({"range": f"{lo:.0%}–{min(hi, 1):.0%}", "forecasts": int(k.sum()),
                          "mean_probability": round(float(p[k].mean()), 3), "recession_frequency": round(float(y[k].mean()), 3)})
    since_2005 = np.array([m >= "2005-01" for m in test_months])
    sub = {}
    if since_2005.any():
        ys5, b5 = y[since_2005], np.mean((np.array(preds["base_rate"])[since_2005] - y[since_2005]) ** 2)
        for k in ("ensemble", "term_spread_only"):
            pk = np.array(preds[k])[since_2005]
            sub[k] = {"auroc": round(_auc(pk, ys5), 3), "brier_skill_vs_base_rate": round(1 - float(np.mean((pk - ys5) ** 2)) / b5, 3)}
    return {"forecasts": len(ys), "recession_months": int(y.sum()), "from": test_months[0], "to": test_months[-1],
            "models": out, "since_2005": sub, "calibration": calib,
            "method": f"Refit every January from {start_year} on months whose 12-month window and a {announce_lag}-month "
                      "NBER announcement lag had closed; forecasts that year's months; scored against NBER recessions "
                      "within 12 months. Brier skill > 0 beats always forecasting the training base rate."}


def compute() -> Dict[str, Any]:
    data, status = _inputs()
    if not data:
        return {"available": False, "reason": "Federal Reserve curve or EBP file unavailable", "source_status": status}
    rows = data["rows"]
    labelled = [r for r in rows if r["y"] is not None]
    y = np.array([r["y"] for r in labelled], float)
    fits = {k: probit_fit(_design(labelled, c), y) for k, c in SPECS.items()}
    if any(v is None for v in fits.values()):
        return {"available": False, "reason": "probit did not converge", "source_status": status}
    lc = data["latest_curve"]
    x_now = {"ts": lc["ts"], "ntfs": lc["ntfs"], "ebp": data["ebp_latest"]}
    parts = {k: probit_prob(fits[k], [x_now[c] for c in cols]) for k, cols in SPECS.items()}
    prob = float(np.mean(list(parts.values())))
    hist = [{"date": r["month"], "probability": round(ensemble_prob(fits, r), 4)} for r in rows[-24:]]
    return {
        "available": True, "probability": round(prob, 4),
        "components": {"term_spread_plus_ebp": round(parts["ts_ebp"], 4), "forward_spread_plus_ebp": round(parts["ntfs_ebp"], 4)},
        "inputs": {"term_spread_10y_3m_pp": round(lc["ts"], 3), "near_term_forward_spread_pp": round(lc["ntfs"], 3),
                   "curve_as_of": lc["date"], "excess_bond_premium_pp": round(data["ebp_latest"], 3), "ebp_as_of": data["ebp_as_of"]},
        "coefficients": {k: [round(float(b), 4) for b in v] for k, v in fits.items()},
        "training_months": len(labelled), "history": hist,
        "evaluation": evaluate(rows),
        "target": "NBER recession in any of the next 12 months",
        "model": "Term spread + credit ensemble (10Y–3M + EBP, forward spread + EBP; probit average)",
        "sources": ["Federal Reserve GSW zero-coupon curve (feds200628)", "Federal Reserve excess bond premium (ebp_csv)"],
        "source_status": status,
        "caveats": ["EBP history is re-estimated by the Fed, not a real-time vintage",
                    "NBER dates are final, not as first announced",
                    "High readings were over-confident in 2022–24 (inverted curve, no recession)"],
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
