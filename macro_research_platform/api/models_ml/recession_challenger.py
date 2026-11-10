"""
Recession challenger: a bagged neural network that runs in shadow mode beside the headline model, retrains every
month, logs its forecasts and builds a live record — and replaces nothing until it has earned it.

How the best-run firms use machine learning, and what that means here
  * beat a simple baseline out of sample, under conservative validation (Puglia & Tucker, Federal Reserve 2020: the
    apparent edge of neural networks and trees over probit reversed under stricter cross-validation)
  * compare a discovery with what noise and the number of trials would produce (Man AHL on overfitting; Bailey &
    López de Prado, deflated Sharpe ratio) — so the gain is bootstrapped and the variants tried are counted
  * ensembles over single models (Gu, Kelly & Xiu 2020); gains are evolutionary, not revolutionary (AQR 2024)
  * machines forecast, humans keep control of risk and of promotion (Bridgewater AIA)
  * champion / challenger with live monitoring before a model is relied on (Fed SR 11-7 model-risk guidance)
  * explain each forecast by its inputs (Bank of England, Shapley-style attribution)

Model (fixed in advance, not tuned on the test period): ten one-hidden-layer networks (8 tanh units, L2 alpha 1.0)
on standardised inputs — the headline's four (10Y–3M, near-term forward spread, EBP, payroll growth) plus the
6-month change in the spread, the 3-month change in the EBP and the 6-month S&P 500 return — averaged, then
Platt-recalibrated on its own earlier out-of-sample forecasts, like the headline.

Evidence so far (pseudo-out-of-sample 1985–2025, refit every January on months whose label and NBER lag had closed):
blended half-and-half with the headline it improved the Brier score 1985–99 and 2000–12 but was worse 2013–25; the
overall gain was not significant (year-block bootstrap: P(no gain) ≈ 0.10, before allowing for ~10 variants tried).
Alone, the networks, gradient boosting and random forests all scored worse than the headline. So it is a challenger.

Promotion (never automatic): eligible only when the backtest gain is significant at 5% after a Bonferroni allowance
for the variants tried AND it has beaten the headline on at least 24 live-scored months; then a person approves it.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

FEATURES = ["ts", "ntfs", "ebp", "pay6", "ts_d6", "ebp_d3", "spx6"]
N_NETS = 10
VARIANTS_TRIED = 10                 # model / feature variants examined before choosing this one (for the allowance)
ALPHA = 0.05
MIN_LIVE_MONTHS = 24
BACKTEST_TTL = 30 * 24 * 3600       # the expensive walk-forward record is rebuilt monthly
_lock = threading.Lock()
_mem: Dict[str, Any] = {"month": None, "data": None}
_ready = False


# ── data ──────────────────────────────────────────────────────────────────────
def _spx6() -> Dict[str, float]:
    """6-month log return of the S&P 500 (monthly average closes), known at month m from m−1's data."""
    import pandas as pd
    from api.marketdata.core import yahoo_download
    df = yahoo_download("^GSPC", period="max", interval="1d", auto_adjust=True)
    c = df["Close"]
    if isinstance(c, pd.DataFrame):
        c = c.iloc[:, 0]
    c.index = pd.to_datetime(c.index).tz_localize(None)
    m = np.log(c.resample("MS").mean()).diff(6).shift(1) * 100
    return {d.strftime("%Y-%m"): float(v) for d, v in m.dropna().items()}


def build_rows(rows: List[Dict[str, Any]], spx6: Dict[str, float]) -> List[Dict[str, Any]]:
    """The headline's monthly rows plus the challenger's extra inputs (each known at that month)."""
    out = [dict(r) for r in rows]
    for i, r in enumerate(out):
        r["ts_d6"] = r["ts"] - out[i - 6]["ts"] if i >= 6 else None
        r["ebp_d3"] = r["ebp"] - out[i - 3]["ebp"] if i >= 3 else None
        r["spx6"] = spx6.get(r["month"])
    return out


def features() -> List[str]:
    """The base inputs plus any indicator a person approved from the knowledge scanner."""
    try:
        from api.models_ml.knowledge_scanner import approved
        return FEATURES + [f"x_{a['series']}" for a in approved()]
    except Exception:                                                    # noqa: BLE001 — base inputs if the store is unavailable
        return list(FEATURES)


def _complete(r: Dict[str, Any], feats: Optional[List[str]] = None) -> bool:
    return all(r.get(k) is not None for k in (feats or FEATURES))


def add_approved(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach approved indicators (as known each month) to the rows."""
    from api import research_indicators as ri
    from api.models_ml.knowledge_scanner import _monthly_known, approved
    for a in approved():
        vals, _ = ri._cached(f"kn_{a['series']}_{a['transform']}", lambda a=a: _monthly_known(a["series"], a["transform"]))
        for r in rows:
            r[f"x_{a['series']}"] = (vals or {}).get(r["month"])
    return rows


# ── model ─────────────────────────────────────────────────────────────────────
class BaggedNet:
    """Ten small networks on standardised inputs, averaged."""

    def __init__(self, n: int = N_NETS):
        self.n = n

    def fit(self, X: np.ndarray, y: np.ndarray) -> "BaggedNet":
        from sklearn.neural_network import MLPClassifier
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        Z = (X - self.mu) / self.sd
        self.nets = [MLPClassifier(hidden_layer_sizes=(8,), activation="tanh", alpha=1.0, max_iter=3000,
                                   random_state=s).fit(Z, y) for s in range(self.n)]
        return self

    def predict_each(self, X: np.ndarray) -> np.ndarray:
        """Each network's probability, shape (networks, rows) — their disagreement is the uncertainty (deep ensembles,
        Lakshminarayanan et al.)."""
        Z = (np.atleast_2d(X) - self.mu) / self.sd
        return np.array([m.predict_proba(Z)[:, 1] for m in self.nets])

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.predict_each(X).mean(0)

    def export(self) -> Dict[str, Any]:
        """Everything a browser needs to run the networks itself (tanh hidden layer, logistic output)."""
        r = lambda a: np.round(np.asarray(a, float), 5).tolist()        # noqa: E731
        return {"mu": r(self.mu), "sd": r(self.sd), "activation": "tanh", "output": "logistic",
                "nets": [{"W1": r(m.coefs_[0]), "b1": r(m.intercepts_[0]), "W2": r(m.coefs_[1][:, 0]),
                          "b2": float(m.intercepts_[1][0])} for m in self.nets]}


def data_checks(X_train: np.ndarray, X_recent: np.ndarray, x_now: np.ndarray, names: List[str]) -> Dict[str, Any]:
    """Validation gate on the inputs (as in Google's TFX data validation): today's value against the training range
    (a network extrapolates badly), and drift — the population stability index of the last 12 months against the
    training distribution (PSI > 0.25 is the usual 'significant shift' line)."""
    out, flags = {}, []
    for i, k in enumerate(names):
        col = X_train[:, i]
        lo, hi = float(np.min(col)), float(np.max(col))
        z = float((x_now[i] - col.mean()) / (col.std() + 1e-9))
        edges = np.quantile(col, np.linspace(0, 1, 11))
        edges[0], edges[-1] = -np.inf, np.inf
        e = np.histogram(col, edges)[0] / len(col) + 1e-4
        a = np.histogram(X_recent[:, i], edges)[0] / max(1, len(X_recent)) + 1e-4
        psi = float(np.sum((a - e) * np.log(a / e)))
        outside = bool(x_now[i] < lo or x_now[i] > hi)
        out[k] = {"value": round(float(x_now[i]), 3), "z": round(z, 2), "train_min": round(lo, 3), "train_max": round(hi, 3),
                  "outside_training_range": outside, "psi_12m": round(psi, 3)}
        if outside:
            flags.append(f"{k} outside the training range")
        elif psi > 0.25:
            flags.append(f"{k} has shifted (PSI {psi:.2f})")
    return {"inputs": out, "flags": flags, "ok": not flags}


def contributions(model: BaggedNet, x: np.ndarray, baseline: np.ndarray, names: Optional[List[str]] = None) -> Dict[str, float]:
    """Each input's push on today's raw probability: the forecast minus the forecast with that input set to its
    training average (an occlusion approximation of a Shapley attribution)."""
    p = float(model.predict(x)[0])
    out = {}
    for i, k in enumerate(names or FEATURES):
        z = x.copy()
        z[i] = baseline[i]
        out[k] = round(p - float(model.predict(z)[0]), 4)
    return out


def _cutoff(year: int, lag: int = 12) -> str:
    cy, cm = divmod(year * 12 - (12 + lag), 12)
    return f"{cy}-{cm + 1:02d}"


def walk_forward(rows: List[Dict[str, Any]], start_year: int = 1985) -> Dict[str, Any]:
    """Pseudo-out-of-sample: the challenger and the headline (same protocol, same months), each Platt-recalibrated on
    its own earlier forecasts; the blend; and a year-block bootstrap of the blend's Brier improvement."""
    from api.models_ml import recession_ensemble as R
    use = [r for r in rows if _complete(r)]
    by = {r["month"]: r for r in use}
    months = sorted(by)
    ch, hd, ys, tm = [], [], [], []
    for yr in range(start_year, int(months[-1][:4]) + 1):
        cut = _cutoff(yr)
        tr = [by[m] for m in months if m < cut and by[m]["y"] is not None]
        te = [by[m] for m in months if m[:4] == str(yr) and by[m]["y"] is not None]
        if not te or sum(r["y"] for r in tr) < 3:
            continue
        y = np.array([r["y"] for r in tr])
        net = BaggedNet().fit(np.array([[r[k] for k in FEATURES] for r in tr]), y)
        fits = {k: R.probit_fit(R._design(tr, c), y.astype(float)) for g in R.GROUPS_LABOUR.values() for k, c in g.items()}
        ch += list(net.predict(np.array([[r[k] for k in FEATURES] for r in te])))
        hd += [float(np.mean([R.ensemble_prob(fits, r, sp) for sp in R.GROUPS_LABOUR.values()])) for r in te]
        ys += [r["y"] for r in te]
        tm += [r["month"] for r in te]

    def calibrate(raw: List[float]) -> np.ndarray:
        out = []
        for i, m in enumerate(tm):
            known = [j for j in range(i) if tm[j] < _cutoff(int(m[:4]))]
            cal = R.learned_platt([raw[j] for j in known], [ys[j] for j in known]) if known else None
            out.append(R.platt_apply(cal, raw[i]))
        return np.array(out)
    y = np.array(ys)
    c_cal, h_cal = calibrate(ch), calibrate(hd)
    blend = (c_cal + h_cal) / 2
    d = (h_cal - y) ** 2 - (blend - y) ** 2                      # > 0: the blend scored better
    years = sorted({m[:4] for m in tm})
    idx = {yy: [i for i, m in enumerate(tm) if m[:4] == yy] for yy in years}
    rng = np.random.default_rng(0)
    boot = []
    for _ in range(4000):                                          # moving blocks of three years (episodes span months)
        pick: List[str] = []
        while len(pick) < len(years):
            s0 = int(rng.integers(0, len(years) - 2))
            pick += years[s0:s0 + 3]
        boot.append(float(d[[i for yy in pick[:len(years)] for i in idx[yy]]].mean()))
    p_no_gain = float((np.array(boot) <= 0).mean())

    def score(p: np.ndarray, mask: np.ndarray) -> Dict[str, Any]:
        pp, yy = np.clip(p[mask], 1e-6, 1 - 1e-6), y[mask]
        return {"auroc": round(R._auc(pp, yy), 3), "brier": round(float(np.mean((pp - yy) ** 2)), 4),
                "log_loss": round(float(-np.mean(yy * np.log(pp) + (1 - yy) * np.log(1 - pp))), 4)}
    eras = {"1985–1999": ("1985", "1999"), "2000–2012": ("2000", "2012"), "2013–now": ("2013", "2100")}
    by_era = {}
    for name, (a, b) in eras.items():
        mk = np.array([a <= m[:4] <= b for m in tm])
        if mk.any():
            by_era[name] = {"headline": score(h_cal, mk), "challenger": score(c_cal, mk), "blend": score(blend, mk),
                            "blend_brier_gain": round(float(d[mk].mean()), 5)}
    allm = np.ones(len(tm), bool)
    return {"from": tm[0], "to": tm[-1], "forecasts": len(tm),
            "overall": {"headline": score(h_cal, allm), "challenger": score(c_cal, allm), "blend": score(blend, allm)},
            "by_era": by_era, "blend_brier_gain": round(float(d.mean()), 5),
            "p_no_gain": round(p_no_gain, 3), "variants_tried": VARIANTS_TRIED,
            "significant_after_allowance": p_no_gain < ALPHA / VARIANTS_TRIED,
            "challenger_history": {"months": tm, "raw": [round(float(v), 5) for v in ch], "y": ys}}


# ── live shadow record ───────────────────────────────────────────────────────
def _conn() -> sqlite3.Connection:
    from api.core.app_db import app_db_path
    c = sqlite3.connect(app_db_path(), timeout=10)
    c.row_factory = sqlite3.Row
    return c


def _init() -> None:
    global _ready
    if _ready:
        return
    with _conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS model_shadow_forecasts (model TEXT NOT NULL, month TEXT NOT NULL, "
                  "probability REAL NOT NULL, headline REAL, logged_at TEXT NOT NULL, PRIMARY KEY (model, month))")
        c.execute("CREATE TABLE IF NOT EXISTS model_retrain_log (model TEXT NOT NULL, month TEXT NOT NULL, trained_at TEXT NOT NULL, "
                  "training_months INTEGER, features TEXT, settings TEXT, data_ok INTEGER, PRIMARY KEY (model, month))")
    _ready = True


def log_forecast(model: str, month: str, p: float, headline: Optional[float]) -> None:
    """One forecast per model per month, kept as first made (never overwritten — a live record is not revisable)."""
    _init()
    with _conn() as c:
        c.execute("INSERT OR IGNORE INTO model_shadow_forecasts (model, month, probability, headline, logged_at) "
                  "VALUES (?,?,?,?,?)", (model, month, p, headline, datetime.now(timezone.utc).isoformat(timespec="seconds")))


def log_retrain(model: str, month: str, n: int, feats: List[str], settings: Dict[str, Any], data_ok: bool) -> None:
    _init()
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO model_retrain_log (model, month, trained_at, training_months, features, settings, data_ok) "
                  "VALUES (?,?,?,?,?,?,?)", (model, month, datetime.now(timezone.utc).isoformat(timespec="seconds"), n,
                                             json.dumps(feats), json.dumps(settings), int(data_ok)))


def retrain_log(model: str = "recession_nn_challenger", limit: int = 24) -> List[Dict[str, Any]]:
    _init()
    with _conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM model_retrain_log WHERE model = ? ORDER BY month DESC LIMIT ?", (model, limit))]
    for r in rows:
        r["features"], r["settings"] = json.loads(r["features"] or "[]"), json.loads(r["settings"] or "{}")
    return rows


def live_record(model: str = "recession_nn_challenger") -> Dict[str, Any]:
    """Score logged forecasts whose 12-month window has closed (NBER dates as recorded in the code)."""
    from api import research_indicators as ri
    _init()
    with _conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM model_shadow_forecasts WHERE model = ? ORDER BY month", (model,))]
    if not rows:
        return {"logged": 0, "scored": 0}
    months = [r["month"] for r in rows]
    today = datetime.now(timezone.utc).strftime("%Y-%m")
    lab = ri._recession_ahead(sorted(set(months) | {today}), 12)
    scored = [(r, lab.get(r["month"])) for r in rows if lab.get(r["month"]) is not None and r["headline"] is not None]
    out = {"logged": len(rows), "first": months[0], "scored": len(scored)}
    if scored:
        ch = np.mean([(r["probability"] - y) ** 2 for r, y in scored])
        hd = np.mean([(r["headline"] - y) ** 2 for r, y in scored])
        out.update(challenger_brier=round(float(ch), 4), headline_brier=round(float(hd), 4), beats_headline=bool(ch < hd))
    return out


# ── today's shadow forecast ───────────────────────────────────────────────────
def compute() -> Dict[str, Any]:
    from api import research_indicators as ri
    from api.models_ml import recession_ensemble as R
    data, status = R._inputs()
    if not data:
        return {"available": False, "reason": "headline inputs unavailable", "source_status": status}
    spx, _ = ri._cached("spx6_monthly", _spx6)
    rows = build_rows(data["rows"], spx or {})
    if sum(_complete(r) for r in rows) < 300:
        return {"available": False, "reason": "not enough complete history for the challenger"}
    bt, bt_status = ri._cached("recession_nn_backtest", lambda: walk_forward(rows), ttl=BACKTEST_TTL)
    labelled = [r for r in rows if _complete(r) and r["y"] is not None]
    X = np.array([[r[k] for k in FEATURES] for r in labelled])
    net = BaggedNet().fit(X, np.array([r["y"] for r in labelled]))
    # today's inputs: the headline's latest values, plus the latest month's derived inputs
    head = R.get_recession_ensemble()
    inp = (head or {}).get("inputs") or {}
    last = rows[-1]
    x_now = {"ts": inp.get("term_spread_10y_3m_pp", last["ts"]), "ntfs": inp.get("near_term_forward_spread_pp", last["ntfs"]),
             "ebp": inp.get("excess_bond_premium_pp", last["ebp"]), "pay6": inp.get("payroll_growth_6m_annualised_pct", last.get("pay6")),
             "ts_d6": last.get("ts_d6"), "ebp_d3": last.get("ebp_d3"), "spx6": last.get("spx6")}
    if any(v is None for v in x_now.values()):
        return {"available": False, "reason": "an input is missing today"}
    xv = np.array([x_now[k] for k in FEATURES], float)
    raw = float(net.predict(xv)[0])
    cal = None
    if bt and bt.get("challenger_history"):
        h = bt["challenger_history"]
        cal = R.learned_platt(h["raw"], h["y"])
    prob = R.platt_apply(cal, raw)
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    log_forecast("recession_nn_challenger", month, prob, (head or {}).get("probability"))
    live = live_record()
    eligible_backtest = bool(bt and bt.get("significant_after_allowance"))
    eligible_live = live.get("scored", 0) >= MIN_LIVE_MONTHS and live.get("beats_headline") is True
    reasons = []
    if not eligible_backtest:
        reasons.append(f"backtest gain not significant (P(no gain) {bt['p_no_gain']:.2f}; needs < {ALPHA / VARIANTS_TRIED:.3f} "
                       f"allowing for {VARIANTS_TRIED} variants tried)" if bt else "backtest record not built yet")
    if bt and (bt.get("by_era", {}).get("2013–now", {}).get("blend_brier_gain") or 0) < 0:
        reasons.append("the blend scored worse than the headline since 2013")
    if not eligible_live:
        reasons.append(f"live record {live.get('scored', 0)} of {MIN_LIVE_MONTHS} scored months")
    bt_public = {k: v for k, v in (bt or {}).items() if k != "challenger_history"} or None
    return {
        "available": True, "mode": "shadow", "month": month, "probability": round(prob, 4), "raw_probability": round(raw, 4),
        "headline_probability": (head or {}).get("probability"),
        "inputs": {k: round(float(v), 3) for k, v in x_now.items()},
        "contributions": contributions(net, xv, X.mean(0)),
        "training_months": len(labelled), "backtest": bt_public, "backtest_status": bt_status, "live": live,
        "promotion": {"eligible": eligible_backtest and eligible_live, "requires_human_approval": True,
                      "status": "Eligible for review" if eligible_backtest and eligible_live else "Not eligible: " + "; ".join(reasons)},
        "model": f"Bagged neural network ({N_NETS}× one hidden layer of 8 tanh units), retrained monthly; shadow challenger",
        "method": __doc__.strip().split("\n\n")[0],
    }


def get_challenger(force: bool = False) -> Dict[str, Any]:
    """Retrained once a month (and on restart); never raises."""
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    if not force and _mem["data"] is not None and _mem["month"] == month:
        return _mem["data"]
    with _lock:
        if not force and _mem["data"] is not None and _mem["month"] == month:
            return _mem["data"]
        t = time.time()
        try:
            data = compute()
        except Exception as e:                                     # noqa: BLE001 — reported, not raised
            logger.warning("[recession-challenger] unavailable: %s", e)
            data = {"available": False, "reason": f"{type(e).__name__}: {e}"}
        logger.info("[recession-challenger] %s in %.0fs", "ok" if data.get("available") else data.get("reason"), time.time() - t)
        if data.get("available") or _mem["data"] is None:
            _mem.update(month=month, data=data)
        return _mem["data"]
