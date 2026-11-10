"""
ML engine: one disciplined pipeline for every forecasting task on the platform (api/ml/tasks.py), with a roster of
models from simple to data-rich, each scored the same way.

Inputs
  core        each task's few economically chosen inputs (api/ml/features.py)
  panel       ~70 FRED-MD-style series across output, labour, housing, orders, money & credit, rates & spreads, FX and
              prices (api/ml/panel.py), each stationary and as known at the time

Roster (fixed settings chosen from the literature, not tuned on the test period)
  champion        L2 logistic regression on the core inputs — the baseline every ML model must beat (Two Sigma's
                  reported practice; Puglia & Tucker, Fed 2020)
  network         ten one-hidden-layer networks on the core inputs, averaged (deep ensembles, DeepMind)
  factor_logit    logistic on core + 8 principal-component factors of the panel (Stock & Watson diffusion indexes;
                  the best regulariser in Goulet Coulombe et al., J. Applied Econometrics 2022)
  factor_network  networks on core + factors — non-linearity with factor regularisation (Goulet Coulombe et al.)
  forest          random forest on core + the whole panel (Medeiros et al., JBES 2021)
  boosting        gradient-boosted trees (LightGBM) on core + the whole panel (Vrontos et al., IJF 2021)
  regime_switch   a two-state Markov-switching model of an activity composite (production, payrolls, real income,
                  real consumption) — the hidden 'recession state' probability, filtered in real time (Hamilton 1989;
                  Chauvet & Piger, the St. Louis Fed's smoothed recession probabilities) — mapped to each task
  deep_sequence   a GRU that reads the last 24 months of every input and answers all tasks at once (api/ml/deep.py)
  average         the equal-weight average of all of them, recalibrated — the classic robust combination
Tuning: the network and boosting models choose their size and regularisation at every refit from a chronological
validation slice of the training window (with a gap equal to the answer delay), so no setting is picked on the test
period. Text & news (newspaper uncertainty and sentiment indices) feed the trees and the deep network.
Factors and scalers are re-estimated inside every training window, so no future data reaches a forecast.

Validation: walk-forward, refit each January only on months whose answer was known by then (`known_after`); each model
Platt-recalibrated on its own earlier forecasts; scored by era against the base rate.
Gate: a model serves a task only if its gain over the champion is significant after a Bonferroni allowance for every
task × model compared (year-block bootstrap), it is not worse since 2013, it has beaten the champion over 24 live-scored
months — and a person approves (SR 11-7 champion/challenger; Bridgewater's human control).
Live: retrains monthly, logs one forecast per model per month that cannot be rewritten, scores them as answers arrive,
checks inputs for extrapolation and drift, and explains forecasts (occlusion attribution for the core models,
importance by series and group for the data-rich ones).
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from api.ml.tasks import TASKS, Task

logger = logging.getLogger(__name__)

N_NETS = 10
N_FACTORS = 8
PANEL_START_BY = "1975-12"              # panel series used must exist from here (complete rows over the walk-forward)
FFILL_MONTHS = 3                         # the latest months may carry a series' last value forward (ragged release edge)
ALPHA = 0.05
MIN_LIVE_MONTHS = 24
BACKTEST_TTL = 30 * 24 * 3600
ROSTER = ["champion", "network", "factor_logit", "factor_network", "forest", "boosting", "regime_switch", "deep_sequence", "sections"]
LOCAL = [k for k in ROSTER if k not in ("deep_sequence", "sections")]   # fitted per task here; deep and sections bring their own refits
CANDIDATES = ROSTER[1:] + ["average"]
MODEL_INFO = {
    "autonomous_tft": ("Autonomous TFT / GAT", "Gated prospective deployment with domain experts, graph context and multi-horizon forecasting."),
    "champion": ("Logistic (core inputs)", "Regularised logistic regression on the task's few chosen inputs — the baseline."),
    "network": ("Neural network (core, tuned)", "Ten one-hidden-layer networks on the core inputs, averaged; size and regularisation chosen each refit."),
    "factor_logit": ("Factor model", "Logistic on the core inputs plus 8 factors extracted from the ~70-series panel."),
    "factor_network": ("Factor neural network", "Ten networks on the core inputs plus the panel's 8 factors."),
    "forest": ("Random forest (all data)", "300 trees on the core inputs, every panel series and the text block."),
    "boosting": ("Gradient boosting (all data, tuned)", "LightGBM on the core inputs, every panel series and the text block; size chosen each refit."),
    "regime_switch": ("Regime-switching model", "Two-state Markov-switching model of an activity composite; the hidden recession-state probability, mapped to the task."),
    "deep_sequence": ("Deep sequence network", "Specialist input encoders, learned routing, 24-month recurrent memory and separate task heads (PyTorch; shared reference profile available)."),
    "sections": ("Section experts + situation gate", "One expert per economic section (rates, credit, financial conditions, labour, activity, housing, inflation, money, markets, sentiment) on every input incl. newer series; a gate weights them by the situation (curve, credit stress, inflation, labour, volatility)."),
    "autonomous_tft": ("Autonomous TFT / GAT", "Temporal fusion transformer with a graph-attention layer, trained by the autonomous pipeline; serves automatically once its prospective evidence gates pass, without a PM/risk sign-off."),
    "average": ("Average of all models", "Equal-weight average of every model, recalibrated."),
}
_locks: Dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_training: Dict[str, float] = {}
_mem: Dict[str, Dict[str, Any]] = {}
_ready = False


def _lock_for(name: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(name, threading.Lock())


# ── models ────────────────────────────────────────────────────────────────────
class Logit:
    def fit(self, X: np.ndarray, y: np.ndarray) -> "Logit":
        from sklearn.linear_model import LogisticRegression
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        self.m = LogisticRegression(C=1.0, max_iter=3000).fit((X - self.mu) / self.sd, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.m.predict_proba((np.atleast_2d(X) - self.mu) / self.sd)[:, 1]

    def coefficients(self, names: List[str]) -> Dict[str, float]:
        return {k: round(float(c), 4) for k, c in zip(names, self.m.coef_[0])}


class BaggedNet:
    def __init__(self, n: int = N_NETS, max_iter: int = 3000):
        self.n, self.max_iter = n, max_iter

    def fit(self, X: np.ndarray, y: np.ndarray) -> "BaggedNet":
        from sklearn.neural_network import MLPClassifier
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        Z = (X - self.mu) / self.sd
        self.nets = [MLPClassifier(hidden_layer_sizes=(8,), activation="tanh", alpha=1.0, max_iter=self.max_iter, random_state=s).fit(Z, y)
                     for s in range(self.n)]
        return self

    def predict_each(self, X: np.ndarray) -> np.ndarray:
        Z = (np.atleast_2d(X) - self.mu) / self.sd
        return np.array([m.predict_proba(Z)[:, 1] for m in self.nets])

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.predict_each(X).mean(0)

    def export(self) -> Dict[str, Any]:
        r = lambda a: np.asarray(a, float).tolist()        # noqa: E731
        return {"mu": r(self.mu), "sd": r(self.sd), "activation": "tanh", "output": "logistic",
                "nets": [{"W1": r(m.coefs_[0]), "b1": r(m.intercepts_[0]), "W2": r(m.coefs_[1][:, 0]),
                          "b2": float(m.intercepts_[1][0])} for m in self.nets]}


class Factors:
    """Principal-component factors of the standardised panel, estimated on the training window only."""

    def fit(self, P: np.ndarray, k: int = N_FACTORS) -> "Factors":
        self.mu, self.sd = P.mean(0), P.std(0) + 1e-9
        Z = (P - self.mu) / self.sd
        _, s, vt = np.linalg.svd(Z, full_matrices=False)
        self.V = vt[:k].T
        self.share = (s[:k] ** 2 / np.sum(s ** 2)).tolist()
        return self

    def transform(self, P: np.ndarray) -> np.ndarray:
        return ((np.atleast_2d(P) - self.mu) / self.sd) @ self.V


NET_GRID = [(4, 1.0), (8, 1.0), (8, 3.0), (16, 3.0)]          # (hidden units, L2 alpha)
BOOST_GRID = [(3, 200), (7, 300), (15, 400)]                    # (leaves, trees)


def _logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _boost(leaves: int, trees: int):
    import lightgbm as lgb
    return lgb.LGBMClassifier(n_estimators=trees, learning_rate=0.03, num_leaves=leaves, min_child_samples=20, subsample=0.8,
                              subsample_freq=1, colsample_bytree=0.5, reg_lambda=1.0, random_state=0, verbose=-1)


class TunedNet(BaggedNet):
    def __init__(self, hidden: int, alpha: float, n: int = N_NETS):
        super().__init__(n)
        self.hidden, self.alpha = hidden, alpha

    def fit(self, X: np.ndarray, y: np.ndarray) -> "TunedNet":
        from sklearn.neural_network import MLPClassifier
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        Z = (X - self.mu) / self.sd
        self.nets = [MLPClassifier(hidden_layer_sizes=(self.hidden,), activation="tanh", alpha=self.alpha, max_iter=3000,
                                   random_state=s).fit(Z, y) for s in range(self.n)]
        return self


def _inner_split(n: int, gap: int) -> Optional[Tuple[slice, slice]]:
    """Chronological tuning split of a training window: the last 20% validates, separated by the answer delay so no
    validation answer overlaps a training one."""
    v0 = int(n * 0.8)
    if v0 - gap < 120 or n - v0 < 36:
        return None
    return slice(0, v0 - gap), slice(v0, n)


class Model:
    """One roster member over (core, panel, text) inputs."""

    def __init__(self, kind: str, gap: int = 12):
        self.kind, self.gap, self.settings = kind, gap, None

    def _x(self, C: np.ndarray, P: np.ndarray, T: Optional[np.ndarray] = None) -> np.ndarray:
        if self.kind in ("champion", "network"):
            return C
        if self.kind in ("factor_logit", "factor_network"):
            return np.hstack([C, self.fac.transform(P)])
        if T is not None and T.size:
            return np.hstack([C, P, T])
        return np.hstack([C, P])

    def _tune(self, X: np.ndarray, y: np.ndarray, grid, build):
        sp = _inner_split(len(y), self.gap)
        if sp is None or y[sp[1]].sum() == 0 or y[sp[0]].sum() < 5:
            return grid[len(grid) // 2]
        tr, va = sp
        scores = {}
        for g in grid:
            try:
                m = build(g, small=True).fit(X[tr], y[tr])
                p = m.predict(X[va]) if isinstance(m, BaggedNet) else m.predict_proba(X[va])[:, 1]
                scores[g] = _logloss(p, y[va])
            except Exception:                                   # noqa: BLE001 — a failed setting is just not chosen
                continue
        return min(scores, key=scores.get) if scores else grid[len(grid) // 2]

    def fit(self, C: np.ndarray, P: np.ndarray, y: np.ndarray, T: Optional[np.ndarray] = None) -> "Model":
        if self.kind in ("factor_logit", "factor_network"):
            self.fac = Factors().fit(P)
        X = self._x(C, P, T)
        if self.kind in ("champion", "factor_logit"):
            self.m = Logit().fit(X, y)
        elif self.kind == "network":
            h, a = self._tune(X, y, NET_GRID, lambda g, small=False: TunedNet(g[0], g[1], 2 if small else N_NETS))
            self.settings = {"hidden_units": h, "l2_alpha": a}
            self.m = TunedNet(h, a).fit(X, y)
        elif self.kind == "factor_network":
            self.m = BaggedNet(5).fit(X, y)
        elif self.kind == "forest":
            from sklearn.ensemble import RandomForestClassifier
            self.m = RandomForestClassifier(n_estimators=300, min_samples_leaf=10, max_features="sqrt", random_state=0,
                                            n_jobs=-1).fit(X, y)
        elif self.kind == "boosting":
            lv, nt = self._tune(X, y, BOOST_GRID, lambda g, small=False: _boost(*g))
            self.settings = {"leaves": lv, "trees": nt}
            self.m = _boost(lv, nt).fit(X, y)
        return self

    def predict(self, C: np.ndarray, P: np.ndarray, T: Optional[np.ndarray] = None) -> np.ndarray:
        X = self._x(np.atleast_2d(C), np.atleast_2d(P), None if T is None else np.atleast_2d(T))
        if self.kind in ("forest", "boosting"):
            return self.m.predict_proba(X)[:, 1]
        return self.m.predict(X)

    def importance(self, names: List[str]) -> Optional[Dict[str, float]]:
        if self.kind not in ("forest", "boosting"):
            return None
        imp = np.asarray(self.m.feature_importances_ if self.kind == "forest" else self.m.booster_.feature_importance("gain"), float)
        imp = imp / (imp.sum() or 1)
        return {k: round(float(v), 4) for k, v in zip(names, imp)}


# ── regime switching ──────────────────────────────────────────────────────────
ACTIVITY = ["p_INDPRO", "p_PAYEMS", "p_W875RX1", "p_DPCERA3M086SBEA"]


def activity_composite(P: np.ndarray, pk: List[str], train_end: int) -> Optional[np.ndarray]:
    """Average of the standardised growth rates of production, payrolls, real income and real consumption (scalers
    from the training months only) — the coincident index a Markov-switching model reads."""
    cols = [pk.index(k) for k in ACTIVITY if k in pk]
    if len(cols) < 2:
        return None
    A = P[:, cols]
    mu, sd = A[:train_end].mean(0), A[:train_end].std(0) + 1e-9
    return ((A - mu) / sd).mean(1)


def regime_probabilities(series: np.ndarray, train_end: int) -> Optional[np.ndarray]:
    """Real-time (filtered) probability of the low-growth state at every month: a two-state Markov-switching model
    with switching mean and variance, fitted on months [0, train_end), then run forward over the whole series with
    those parameters — each month's probability uses data up to that month only."""
    import warnings
    from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = MarkovRegression(series[:train_end], k_regimes=2, trend="c", switching_variance=True).fit(disp=False, search_reps=8)
            params = np.asarray(res.params)
            names = list(res.model.param_names)
            consts = [params[names.index(f"const[{i}]")] for i in range(2)]
            low = int(np.argmin(consts))
            full = MarkovRegression(series, k_regimes=2, trend="c", switching_variance=True).filter(params)
        return np.asarray(full.filtered_marginal_probabilities)[:, low]
    except Exception as e:                                       # noqa: BLE001 — the model is then skipped
        logger.warning("[ml] regime-switching fit failed: %s", e)
        return None


def regime_features(prob: np.ndarray) -> np.ndarray:
    """[probability of the low-growth state, its 3-month change]."""
    d3 = np.concatenate([np.zeros(3), prob[3:] - prob[:-3]])
    return np.column_stack([prob, d3])


# ── data ──────────────────────────────────────────────────────────────────────
def panel_keys(panel: Dict[str, Dict[str, float]]) -> List[str]:
    return sorted(k for k, v in panel.items() if v and min(v) <= PANEL_START_BY)


def _carry(series: Dict[str, float], months: List[str]) -> Dict[str, float]:
    """The series with its last value carried forward up to FFILL_MONTHS past its end (the ragged release edge)."""
    out = dict(series)
    last = max(series) if series else None
    for m in months:
        if last and m > last and m not in out:
            y, mo = map(int, m.split("-"))
            ly, lm = map(int, last.split("-"))
            if (y - ly) * 12 + mo - lm <= FFILL_MONTHS:
                out[m] = series[last]
    return out


def dataset(task: Task, feats: Dict[str, Dict[str, float]], panel: Dict[str, Dict[str, float]],
            text: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[str, Any]:
    missing = [k for k in task.features if k not in feats or not feats[k]]
    if missing:
        return {"rows": [], "missing": missing, "panel_keys": [], "text_keys": []}
    text = text or {}
    tk = sorted(text)
    target = task.target()
    months = sorted(set.intersection(*[set(feats[k]) for k in task.features]))
    pk = panel_keys(panel)
    filled = {k: _carry(panel[k], months[-FFILL_MONTHS - 1:]) for k in pk}
    rows = []
    for m in months:
        p = [filled[k].get(m) for k in pk]
        if any(v is None for v in p):
            continue
        rows.append({"month": m, "c": [feats[k][m] for k in task.features], "p": p,
                     "t": [text[k].get(m, np.nan) for k in tk], "y": target.get(m)})
    return {"rows": rows, "missing": [], "panel_keys": pk, "text_keys": tk}


def cutoff(year: int, known_after: int) -> str:
    """Training months for a January `year` refit: answers known by then."""
    k = year * 12 - known_after                      # months since year 0; January of `year` is year·12
    return f"{k // 12}-{k % 12 + 1:02d}"


def _platt_series(raw: List[float], ys: List[int], tm: List[str], known_after: int) -> np.ndarray:
    from api.models_ml import recession_ensemble as R
    out = []
    for i, m in enumerate(tm):
        cut = cutoff(int(m[:4]), known_after)
        known = [j for j in range(i) if tm[j] < cut]
        coef = R.learned_platt([raw[j] for j in known], [ys[j] for j in known]) if known else None
        out.append(R.platt_apply(coef, raw[i]))
    return np.array(out)


def _block_p(d: np.ndarray, tm: List[str], n: int = 2000) -> float:
    from api.models_ml.knowledge_scanner import block_bootstrap_p
    return block_bootstrap_p(d, tm, n=n)


def _arrays(rows: List[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    return (np.array([r["c"] for r in rows], float), np.array([r["p"] for r in rows], float),
            np.array([r["y"] for r in rows]) if rows and rows[0]["y"] is not None else np.array([]),
            np.array([r.get("t", []) for r in rows], float))


def walk_forward(task: Task, rows: List[Dict[str, Any]], roster: Optional[List[str]] = None,
                 panel_keys_: Optional[List[str]] = None, deep: Optional[Dict[str, float]] = None,
                 sections: Optional[Dict[str, float]] = None) -> Optional[Dict[str, Any]]:
    from api.models_ml import recession_ensemble as R
    pre = {"deep_sequence": deep, "sections": sections}                    # models that bring their own refits: month → raw
    roster = [k for k in (roster or ROSTER) if k not in pre or pre[k]]
    lab = [r for r in rows if r["y"] is not None]
    pos = {r["month"]: i for i, r in enumerate(rows)}
    P_all = np.array([r["p"] for r in rows], float)
    if len(lab) < 240:
        return None
    months = [r["month"] for r in lab]
    raw: Dict[str, List[float]] = {k: [] for k in roster}
    ys: List[int] = []
    tm: List[str] = []
    for yr in range(max(task.start_year, int(months[0][:4]) + 12), int(months[-1][:4]) + 1):
        cut = cutoff(yr, task.known_after)
        tr = [r for r in lab if r["month"] < cut]
        te = [r for r in lab if r["month"][:4] == str(yr)]
        y_tr = np.array([r["y"] for r in tr])
        if not te or len(tr) < 120 or y_tr.sum() < 10 or (1 - y_tr).sum() < 10:
            continue
        Ctr, Ptr, _, Ttr = _arrays(tr)
        Cte, Pte, _, Tte = _arrays(te)
        for k in roster:
            if k in pre:
                raw[k] += [pre[k].get(r["month"], np.nan) for r in te]
            elif k == "regime_switch":
                end = pos[tr[-1]["month"]] + 1
                comp = activity_composite(P_all, panel_keys_ or [], end) if panel_keys_ else None
                prob = regime_probabilities(comp[:pos[te[-1]["month"]] + 1], end) if comp is not None else None
                if prob is None:
                    raw[k] += [float(y_tr.mean())] * len(te)
                    continue
                F = regime_features(prob)
                m = Logit().fit(F[[pos[r["month"]] for r in tr]], y_tr)
                raw[k] += list(m.predict(F[[pos[r["month"]] for r in te]]))
            else:
                raw[k] += list(Model(k, task.known_after).fit(Ctr, Ptr, y_tr, Ttr).predict(Cte, Pte, Tte))
        ys += [r["y"] for r in te]
        tm += [r["month"] for r in te]
    if len(tm) < 60:
        return None
    y = np.array(ys)
    for k in pre:                                                 # months a precomputed model did not cover: the champion's
        if k in raw:
            raw[k] = [c if not np.isfinite(d) else d for d, c in zip(raw[k], raw["champion"])]
    cal = {k: _platt_series(raw[k], ys, tm, task.known_after) for k in roster}
    cal["average"] = np.mean([cal[k] for k in roster], axis=0)
    base = []
    for i, m in enumerate(tm):
        cut = cutoff(int(m[:4]), task.known_after)
        known = [ys[j] for j in range(i) if tm[j] < cut]
        base.append(float(np.mean(known)) if known else float(np.mean(ys[:12])))
    base = np.array(base)

    def score(p: np.ndarray, mask: np.ndarray) -> Dict[str, Any]:
        pp, yy = np.clip(p[mask], 1e-6, 1 - 1e-6), y[mask]
        bs, bb = float(np.mean((pp - yy) ** 2)), float(np.mean((base[mask] - yy) ** 2))
        return {"auroc": round(R._auc(pp, yy), 3) if 0 < yy.sum() < len(yy) else None, "brier": round(bs, 4),
                "skill_vs_base_rate": round(1 - bs / bb, 3) if bb else None,
                "hit_rate": round(float(np.mean((pp > 0.5) == (yy == 1))), 3)}
    allm = np.ones(len(tm), bool)
    eras = {}
    for name, (a, b) in {"1985–1999": ("1985", "1999"), "2000–2012": ("2000", "2012"), "2013–now": ("2013", "2100")}.items():
        mk = np.array([a <= m[:4] <= b for m in tm])
        if mk.sum() >= 24:
            eras[name] = {k: score(v, mk) for k, v in cal.items()}
    gains = {}
    for k in cal:
        if k == "champion":
            continue
        d = (cal["champion"] - y) ** 2 - (cal[k] - y) ** 2
        gains[k] = {"brier": round(float(d.mean()), 5), "p_no_gain": round(_block_p(d, tm), 3)}
    return {"from": tm[0], "to": tm[-1], "forecasts": len(tm), "positive_share": round(float(y.mean()), 3),
            "overall": {k: score(v, allm) for k, v in cal.items()}, "by_era": eras, "gains": gains,
            "history": {"months": tm, "y": ys, "raw": {k: [round(float(v), 5) for v in raw[k]] for k in roster}}}


# ── live record ───────────────────────────────────────────────────────────────
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
        c.execute("CREATE TABLE IF NOT EXISTS ml_forecasts (task TEXT NOT NULL, model TEXT NOT NULL, month TEXT NOT NULL, "
                  "probability REAL NOT NULL, logged_at TEXT NOT NULL, PRIMARY KEY (task, model, month))")
        c.execute("CREATE TABLE IF NOT EXISTS ml_retrains (task TEXT NOT NULL, month TEXT NOT NULL, trained_at TEXT NOT NULL, "
                  "training_months INTEGER, data_ok INTEGER, flags TEXT, PRIMARY KEY (task, month))")
        c.execute("CREATE TABLE IF NOT EXISTS ml_promotions (task TEXT PRIMARY KEY, model TEXT NOT NULL, approved_by TEXT NOT NULL, "
                  "approved_at TEXT NOT NULL, note TEXT)")
        columns={r[1] for r in c.execute("PRAGMA table_info(ml_promotions)")}
        if 'model_version' not in columns:c.execute('ALTER TABLE ml_promotions ADD COLUMN model_version TEXT')
    _ready = True


def log_forecast(task: str, model: str, month: str, p: float) -> None:
    _init()
    if model in ('deep_sequence','average'):
        from api.ml.deep_config import fingerprint
        model=model+'__'+fingerprint()
    with _conn() as c:
        c.execute("INSERT OR IGNORE INTO ml_forecasts (task, model, month, probability, logged_at) VALUES (?,?,?,?,?)",
                  (task, model, month, p, datetime.now(timezone.utc).isoformat(timespec="seconds")))


def live_record(task: Task, target: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """Per model: logged months, scored months and Brier on the scored ones; whether each is ahead of the champion."""
    _init()
    with _conn() as c:
        rows = [dict(r) for r in c.execute("SELECT model, month, probability FROM ml_forecasts WHERE task = ?", (task.name,))]
    if not rows:
        return {"logged_months": 0, "scored_months": 0, "models": {}}
    target = target if target is not None else task.target()
    by: Dict[str, Dict[str, float]] = {}
    from api.ml.deep_config import model_key
    deep_key=model_key()
    month_index=datetime.now(timezone.utc).year*12+datetime.now(timezone.utc).month-1-task.known_after
    known_before=f"{month_index//12}-{month_index%12+1:02d}"
    for r in rows:
        for versioned in ('deep_sequence','average'):
            if r['model']==versioned or r['model'].startswith(versioned+'__'):
                if r['model']!=versioned+'__'+deep_key.split('__',1)[1]:r['model']='obsolete_version'
                else:r['model']=versioned
        if r['model']=='obsolete_version':continue
        by.setdefault(r["month"], {})[r["model"]] = r["probability"]
    scored = {m: v for m, v in by.items() if m in target and m<known_before and "champion" in v}
    out: Dict[str, Any] = {"logged_months": len(by), "first": min(by), "scored_months": len(scored), "models": {}}
    if scored:
        champ = float(np.mean([(v["champion"] - target[m]) ** 2 for m, v in scored.items()]))
        for k in {mm for v in scored.values() for mm in v}:
            pairs = [(v[k],target[m],v['champion']) for m,v in scored.items() if k in v]
            b=float(np.mean([(p-y_)**2 for p,y_,_ in pairs]))
            paired_champion=float(np.mean([(c-y_)**2 for _,y_,c in pairs]))
            out["models"][k] = {"scored":len(pairs),"brier":round(b,4),"paired_champion_brier":round(paired_champion,4),"ahead_of_champion":b<paired_champion if k!='champion' else None}
        # backward-compatible summary for the network
        if "network" in out["models"]:
            out["champion_brier"] = round(champ, 4)
            out["network_brier"] = out["models"]["network"]["brier"]
            out["network_ahead"] = out["models"]["network"]["ahead_of_champion"]
    return out


def promoted(task: str) -> Optional[Dict[str, Any]]:
    _init()
    with _conn() as c:
        r = c.execute("SELECT * FROM ml_promotions WHERE task = ?", (task,)).fetchone()
    result=dict(r) if r else None
    if result and result['model'] in ('deep_sequence','average'):
        from api.ml.deep_config import fingerprint
        if result.get('model_version')!=fingerprint():return None
    return result


def promote(task_name: str, user: str, model: Optional[str] = None, note: str = "") -> Dict[str, Any]:
    """A person promotes a model for a task — only one the gate lists as eligible (the strongest if none is named)."""
    res = run(task_name)
    if not res.get("available"):
        raise LookupError(res.get("reason") or "task unavailable")
    eligible = res["promotion"]["eligible_models"]
    if not eligible:
        raise ValueError("Not eligible: " + res["promotion"]["status"])
    model = model or eligible[0]
    if model not in eligible:
        raise ValueError(f"{model} is not eligible ({', '.join(eligible)} are)")
    _init()
    with _conn() as c:
        from api.ml.deep_config import fingerprint
        c.execute("INSERT OR REPLACE INTO ml_promotions (task,model,approved_by,approved_at,note,model_version) VALUES (?,?,?,?,?,?)",
                  (task_name,model,user,datetime.now(timezone.utc).isoformat(timespec="seconds"),note[:500],fingerprint() if model in ('deep_sequence','average') else None))
    _mem.pop(task_name, None)
    return {"task": task_name, "promoted": model, "by": user}


def demote(task_name: str) -> Dict[str, Any]:
    _init()
    with _conn() as c:
        n = c.execute("DELETE FROM ml_promotions WHERE task = ?", (task_name,)).rowcount
    _mem.pop(task_name, None)
    if not n:
        raise LookupError(f"{task_name} has no promoted model")
    return {"task": task_name, "promoted": None}


# ── checks and explanations ───────────────────────────────────────────────────
def data_checks(X_train: np.ndarray, X_recent: np.ndarray, x_now: np.ndarray, names: List[str]) -> Dict[str, Any]:
    """Today's inputs against the training range (networks extrapolate badly) and drift: the last 12 months' average
    against the training distribution, in training standard deviations (flagged beyond 1.5). The population stability
    index is reported too, smoothed — with only 12 recent months it is too noisy to alarm on by itself."""
    out, flags = {}, []
    bins = 5
    for i, k in enumerate(names):
        col = X_train[:, i]
        lo, hi = float(col.min()), float(col.max())
        edges = np.quantile(col, np.linspace(0, 1, bins + 1))
        edges[0], edges[-1] = -np.inf, np.inf
        e = np.histogram(col, edges)[0] / len(col) + 1e-4
        a = (np.histogram(X_recent[:, i], edges)[0] + 0.5) / (len(X_recent) + 0.5 * bins)
        psi = float(np.sum((a - e) * np.log(a / e)))
        shift = float((X_recent[:, i].mean() - col.mean()) / (col.std() + 1e-9))
        outside = bool(x_now[i] < lo or x_now[i] > hi)
        out[k] = {"value": round(float(x_now[i]), 3), "train_min": round(lo, 3), "train_max": round(hi, 3),
                  "z": round(float((x_now[i] - col.mean()) / (col.std() + 1e-9)), 2), "outside_training_range": outside,
                  "shift_12m_sd": round(shift, 2), "psi_12m": round(psi, 3)}
        if outside:
            flags.append(f"{k} is outside the range the model was trained on")
        elif abs(shift) > 1.5:
            flags.append(f"{k} has shifted: the last 12 months average {shift:+.1f} standard deviations from its training norm")
    return {"inputs": out, "flags": flags, "ok": not flags}


def attributions(predict, x: np.ndarray, baseline: np.ndarray, names: List[str]) -> Dict[str, float]:
    """Each input's push on the raw probability: the forecast minus the forecast with that input at its average."""
    p = float(predict(x)[0])
    out = {}
    for i, k in enumerate(names):
        z = x.copy()
        z[i] = baseline[i]
        out[k] = round(p - float(predict(z)[0]), 4)
    return out


# ── run a task ────────────────────────────────────────────────────────────────
def compute(task: Task) -> Dict[str, Any]:
    from api import research_indicators as ri
    from api.ml import features as F
    from api.ml import panel as PN
    from api.models_ml import recession_ensemble as R
    from api.ml import deep as D
    feats, panel, text = F.load(), PN.load(), F.load_text()
    ds = dataset(task, feats, panel, text)
    if ds["missing"]:
        return {"available": False, "task": task.name, "reason": f"inputs unavailable: {', '.join(ds['missing'])}"}
    rows, pk, tk = ds["rows"], ds["panel_keys"], ds["text_keys"]
    try:
        joint = D.peek(start=True)                                      # the deep model's joint record and today's readings
    except Exception as e:                                     # noqa: BLE001 — the deep model is optional
        logger.warning("[ml] deep model unavailable: %s", e)
        joint = None
    deep_bt = ((joint or {}).get("backtest") or {}).get(task.name)
    lab = [r for r in rows if r["y"] is not None]
    if len(lab) < 240:
        return {"available": False, "task": task.name, "reason": "not enough history with known answers"}
    from api.ml import sections as SX
    sx_data, sx_sec, sx_lab = SX.inputs()
    months_all = [r["month"] for r in rows]
    y_of = {r["month"]: r["y"] for r in rows}
    sx_wf, _ = ri._cached(f"ml_{SX.VERSION}_{task.name}", lambda: SX.walk_forward(task, months_all, y_of, sx_data, sx_sec), ttl=BACKTEST_TTL)
    # one key for the walk-forward record: any change to the deep model, its data or the section engine invalidates it,
    # and history() reads exactly this key (stored on the result) rather than rebuilding its own
    bt_key = f"ml_bt6_{D.fingerprint()}_{(joint or {}).get('data_digest','no_deep')[:16]}_{SX.VERSION}_{task.name}"
    bt, bt_status = ri._cached(bt_key, lambda: walk_forward(task, rows, panel_keys_=pk, deep=deep_bt,
                                                                             sections=(sx_wf or {}).get("prob")), ttl=BACKTEST_TTL)
    C, P, y, T = _arrays(lab)
    now = rows[-1]
    c_now, p_now, t_now = np.array(now["c"], float), np.array(now["p"], float), np.array(now["t"], float)
    models = {k: Model(k, task.known_after).fit(C, P, y, T) for k in LOCAL if k != "regime_switch"}
    hist = (bt or {}).get("history") or {}
    raws: Dict[str, float] = {k: float(m.predict(c_now, p_now, t_now)[0]) for k, m in models.items()}
    regime_now = None
    comp = activity_composite(np.array([r["p"] for r in rows], float), pk, len(rows))
    if comp is not None:
        prob = regime_probabilities(comp, len(rows))
        if prob is not None:
            pos = {r["month"]: i for i, r in enumerate(rows)}
            Fr = regime_features(prob)
            raws["regime_switch"] = float(Logit().fit(Fr[[pos[r["month"]] for r in lab]], y).predict(Fr[[len(rows) - 1]])[0])
            regime_now = {"low_growth_state_probability": round(float(prob[-1]), 4),
                          "history": [{"month": rows[i]["month"], "p": round(float(prob[i]), 4)} for i in range(max(0, len(rows) - 120), len(rows))]}
    sections_now = None
    if sx_wf and sx_wf.get("prob"):
        try:
            sections_now = SX.live(task, months_all, y_of, sx_data, sx_sec, sx_wf, sx_lab)
            raws["sections"] = sections_now["probability_raw"]
        except Exception as e:                                 # noqa: BLE001 — the sections model is optional
            logger.warning("[ml] sections model unavailable: %s", e)
    if joint and task.name in (joint.get("now") or {}):
        raws["deep_sequence"] = float(joint["now"][task.name])
    probs: Dict[str, float] = {}
    for k, raw in raws.items():
        coef = R.learned_platt(hist.get("raw", {}).get(k, []), hist.get("y", [])) if hist else None
        probs[k] = R.platt_apply(coef, raw)
    probs["average"] = float(np.mean([probs[k] for k in raws]))
    net: BaggedNet = models["network"].m
    each = net.predict_each(c_now)[:, 0]
    net_cal = R.learned_platt(hist.get("raw", {}).get("network", []), hist.get("y", [])) if hist else None
    per_net = [R.platt_apply(net_cal, float(v)) for v in each]
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    for k, p in probs.items():
        log_forecast(task.name, k, month, p)
    checks = data_checks(C, np.array([r["c"] for r in rows[-12:]]), c_now, task.features)
    _init()
    with _conn() as cx:
        cx.execute("INSERT OR REPLACE INTO ml_retrains (task, month, trained_at, training_months, data_ok, flags) VALUES (?,?,?,?,?,?)",
                   (task.name, month, datetime.now(timezone.utc).isoformat(timespec="seconds"), len(lab), int(checks["ok"]),
                    json.dumps(checks["flags"])))
    live = live_record(task)
    # gate
    n_tests = len(TASKS) * len(CANDIDATES)
    bar = ALPHA / n_tests
    gains = (bt or {}).get("gains") or {}
    recent = ((bt or {}).get("by_era") or {}).get("2013–now") or {}
    eligible, why = [], {}
    for k in CANDIDATES:
        g = gains.get(k) or {}
        sig = g.get("brier", 0) > 0 and g.get("p_no_gain", 1) < bar
        rec_ok = bool(recent.get(k) and recent.get("champion") and recent[k]["brier"] <= recent["champion"]["brier"])
        lm = (live.get("models") or {}).get(k) or {}
        live_ok = lm.get("scored", 0) >= MIN_LIVE_MONTHS and lm.get("ahead_of_champion") is True
        reasons = []
        if not sig:
            reasons.append(f"gain not significant (P(luck) {g.get('p_no_gain', 1):.2f} vs bar {bar:.4f})" if g else "no record")
        if not rec_ok:
            reasons.append("worse than the champion since 2013")
        if not live_ok:
            reasons.append(f"live {lm.get('scored', 0)}/{MIN_LIVE_MONTHS} months")
        why[k] = "; ".join(reasons) or "eligible"
        if sig and rec_ok and live_ok:
            eligible.append(k)
    eligible.sort(key=lambda k: -(gains.get(k) or {}).get("brier", 0))
    prom = promoted(task.name)
    serving = prom["model"] if prom and prom["model"] in probs else "champion"
    overall = (bt or {}).get("overall") or {}
    skill = (overall.get(serving) or {}).get("skill_vs_base_rate")
    best = max(overall, key=lambda k: (overall[k].get("skill_vs_base_rate") or -9)) if overall else None
    names_all = task.features + pk + tk
    labels = {**{k: F.FEATURES.get(k, (k,))[0] for k in task.features}, **{k: PN.LABEL_OF.get(k, k) for k in pk},
              **{k: F.TEXT.get(k, (k,))[0] for k in tk}}
    group_of = {**{k: "Core inputs" for k in task.features}, **{k: PN.GROUP_OF.get(k, "Other") for k in pk},
                **{k: "Text & news" for k in tk}}
    importance = {}
    for k in ("forest", "boosting"):
        imp = models[k].importance(names_all) or {}
        top = sorted(imp.items(), key=lambda kv: -kv[1])[:15]
        by_group: Dict[str, float] = {}
        for name, v in imp.items():
            by_group[group_of[name]] = by_group.get(group_of[name], 0) + v
        importance[k] = {"top": [{"key": n, "label": labels.get(n, n), "group": group_of[n], "share": v} for n, v in top],
                         "by_group": {g: round(v, 4) for g, v in sorted(by_group.items(), key=lambda kv: -kv[1])}}
    fac: Factors = models["factor_logit"].fac
    return {
        "available": True, "task": task.name, "title": task.title, "question": task.question, "used_for": task.used_for,
        "backtest_key": bt_key,
        "notes": task.notes, "month": month, "as_of_inputs": now["month"],
        "signal": {"probability": round(probs[serving], 4), "model": serving, "skill_vs_base_rate": skill,
                   "useful": skill is not None and skill > 0},
        "models": {k: {"name": MODEL_INFO[k][0], "what": MODEL_INFO[k][1], "probability": round(p, 4),
                       "raw": round(raws.get(k, p), 4), "record": overall.get(k), "gain": gains.get(k), "gate": why.get(k)}
                   for k, p in probs.items()},
        "best_by_record": best,
        "champion": {"probability": round(probs["champion"], 4), "raw": round(raws["champion"], 4),
                     "coefficients": models["champion"].m.coefficients(task.features)},
        "network": {"probability": round(probs["network"], 4), "raw": round(raws["network"], 4),
                    "range": [round(min(per_net), 4), round(max(per_net), 4)], "spread": round(float(np.std(per_net)), 4),
                    "weights": net.export(), "calibration": net_cal},
        "features": [{"key": k, "label": F.FEATURES.get(k, (k,))[0], "unit": F.FEATURES.get(k, ("", ""))[1]} for k in task.features],
        "inputs": {k: round(float(v), 4) for k, v in zip(task.features, c_now)},
        "attributions": {"champion": attributions(lambda z: models["champion"].predict(z, p_now), c_now, C.mean(0), task.features),
                         "network": attributions(lambda z: models["network"].predict(z, p_now), c_now, C.mean(0), task.features)},
        "tuned_settings": {k: models[k].settings for k in ("network", "boosting") if models[k].settings},
        "regime": regime_now,
        "deep": ({"seeds": [round(float(R.platt_apply(R.learned_platt(hist.get("raw", {}).get("deep_sequence", []), hist.get("y", [])) if hist else None, v)), 4)
                            for v in (joint.get("seeds") or {}).get(task.name, [])],
                  "inputs_per_month": joint.get("inputs"), "sequence_months": joint.get("sequence_months"), "as_of": joint.get("as_of"),"configuration":joint.get("configuration"),"fingerprint":joint.get("fingerprint"),"training_reports":joint.get("training_reports"),"modules":joint.get("modules"),"routing":joint.get("routing")}
                 if joint else None),
        "importance": importance,
        "sections_detail": sections_now,
        "panel": {"series": len(pk), "groups": {**PN.groups(pk), **({"Text & news": len(tk)} if tk else {})},
                  "factor_variance_share": [round(v, 3) for v in fac.share]},
        "data_checks": checks, "training_months": len(lab), "positive_share": round(float(y.mean()), 3),
        "backtest": {k: v for k, v in (bt or {}).items() if k != "history"} or None, "backtest_status": bt_status,
        "live": live,
        "promotion": {"promoted": prom, "eligible": bool(eligible), "eligible_models": eligible, "requires_human_approval": True,
                      "bar": bar, "comparisons": n_tests,
                      "status": (f"{MODEL_INFO[serving][0]} promoted" if prom else
                                 f"Eligible for review: {', '.join(MODEL_INFO[k][0] for k in eligible)}" if eligible else
                                 "No challenger eligible — the champion serves. " + " · ".join(f"{MODEL_INFO[k][0]}: {why[k]}" for k in CANDIDATES[:3]))},
    }


def _autonomous_result(data):
    from api.ml.autonomous import decorate
    return decorate(data)


def run(name: str, force: bool = False) -> Dict[str, Any]:
    """A task's result, retrained once a month (and after a restart). Never raises."""
    task = TASKS.get(name)
    if not task:
        return {"available": False, "task": name, "reason": "unknown task"}
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    hit = _mem.get(name)
    if not force and hit and hit["month"] == month:
        return _autonomous_result(hit["data"])
    with _lock_for(name):
        hit = _mem.get(name)
        if not force and hit and hit["month"] == month:
            return _autonomous_result(hit["data"])
        t = time.time()
        try:
            data = compute(task)
        except Exception as e:                                         # noqa: BLE001 — reported, not raised
            logger.warning("[ml] %s failed: %s", name, e)
            data = {"available": False, "task": name, "reason": f"{type(e).__name__}: {e}"}
        logger.info("[ml] %s: %s in %.0fs", name, "ok" if data.get("available") else data.get("reason"), time.time() - t)
        if data.get("available") or not hit:
            _mem[name] = {"month": month, "data": data}
        return _autonomous_result(_mem[name]["data"])


def request(name: str) -> Dict[str, Any]:
    """For the API: this month's result at once if ready; otherwise start training in the background (if it is not
    already) and say so — a page never waits minutes on a request."""
    if name not in TASKS:
        return {"available": False, "task": name, "reason": "unknown task"}
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    hit = _mem.get(name)
    if hit and hit["month"] == month:
        return _autonomous_result(hit["data"])
    if name not in _training:
        _training[name] = time.time()

        def work():
            try:
                run(name)
            finally:
                _training.pop(name, None)
        threading.Thread(target=work, name=f"ml-{name}", daemon=True).start()
    return {"available": False, "task": name, "training": True, "started_at": _training.get(name),
            "elapsed_s": round(time.time() - _training.get(name, time.time())),
            "reason": "training: fitting six models on ~80 inputs and building their walk-forward records"}


def cached(name: str) -> Optional[Dict[str, Any]]:
    """This month's result if already computed (never trains) — for the desk, the playbook and the assistant."""
    hit = _mem.get(name)
    return _autonomous_result(hit["data"]) if hit and hit["data"].get("available") else None


def evidence(name: str, phrase: str) -> Optional[str]:
    """A short line for the desk and playbook — only when the task's served model has beaten the base rate out of
    sample (a model without skill is not evidence). Uses this month's cached result; never trains."""
    d = cached(name)
    if not d or not d["signal"].get("useful"):
        return None
    s = d["signal"]
    sign = ", promoted automatically without sign-off" if s.get("model") == "autonomous_tft" else ""
    skill = s.get("skill_vs_base_rate")
    return (f"ML: {phrase} {s['probability']:.0%} ({MODEL_INFO.get(s['model'], (s['model'],))[0]}"
            f"{'' if skill is None else f', out-of-sample skill {skill:+.0%}'}{sign})")


def summary() -> List[Dict[str, Any]]:
    """Every task's signal and each model's reading, without the network weights."""
    out = []
    for name, task in TASKS.items():
        d = cached(name)
        if not d:
            out.append({"task": name, "title": task.title, "question": task.question, "used_for": task.used_for, "ready": False,
                        "training": name in _training})
            continue
        bt = d.get("backtest") or {}
        out.append({"task": name, "title": task.title, "question": task.question, "used_for": task.used_for, "ready": True,
                    "signal": d["signal"], "network_probability": d["network"]["probability"],
                    "network_range": d["network"]["range"], "champion_probability": d["champion"]["probability"],
                    "models": {k: {"name": v["name"], "probability": v["probability"],
                                   "skill": (v.get("record") or {}).get("skill_vs_base_rate")} for k, v in d["models"].items()},
                    "best_by_record": d.get("best_by_record"), "overall": bt.get("overall"),
                    "promotion": d["promotion"]["status"], "data_ok": d["data_checks"]["ok"], "flags": d["data_checks"]["flags"],
                    "month": d["month"]})
    return out


def run_all() -> Dict[str, Any]:
    return {name: bool(run(name).get("available")) for name in TASKS}


def input_history(name: str, months: int = 480) -> Optional[Dict[str, Any]]:
    """The task's core inputs month by month (as published, from the same caches the models train on) with the
    outcome where known — the network visualizer replays them through the exported weights in the browser."""
    from api.ml import features as F
    task = TASKS.get(name)
    if not task:
        return None
    feats = F.load()
    if any(k not in feats or not feats[k] for k in task.features):
        return None
    common = sorted(set.intersection(*[set(feats[k]) for k in task.features]))[-months:]
    target = task.target()
    return {"task": name, "features": task.features, "months": common,
            "values": [[round(float(feats[k][m]), 4) for k in task.features] for m in common],
            "outcome": [target.get(m) for m in common]}


def history(name: str) -> Optional[Dict[str, Any]]:
    """Every model's recalibrated walk-forward forecast by month, with the outcome — for the timeline, ROC and
    reliability charts. Uses this month's cached result (never trains)."""
    d = cached(name)
    task = TASKS.get(name)
    if not d or not task:
        return None
    from api.handlers.macro_inputs import _disk_load
    key = d.get("backtest_key")                                       # the record this result was built from
    bt = (_disk_load(f"ri_{key}") or {}).get("data") if key else None  # read only
    h = (bt or {}).get("history") or {}
    if not h:
        return None
    tm, ys = h["months"], h["y"]
    cal = {k: [round(float(v), 4) for v in _platt_series(raw, ys, tm, task.known_after)] for k, raw in h["raw"].items()}
    if cal:
        cal["average"] = [round(float(np.mean([cal[k][i] for k in h["raw"]])), 4) for i in range(len(tm))]
    return {"task": name, "months": tm, "outcome": ys, "models": cal,
            "names": {k: MODEL_INFO.get(k, (k,))[0] for k in cal}}


def registry() -> Dict[str, Any]:
    """Model registry and operations: each task's stages (production = serving, shadow = challengers), promotions,
    the retrain log and the latest logged forecasts."""
    _init()
    with _conn() as c:
        retrains = [dict(r) for r in c.execute("SELECT * FROM ml_retrains ORDER BY trained_at DESC LIMIT 60")]
        promos = [dict(r) for r in c.execute("SELECT * FROM ml_promotions ORDER BY approved_at DESC")]
        recent = [dict(r) for r in c.execute("SELECT task, model, month, probability, logged_at FROM ml_forecasts "
                                              "ORDER BY logged_at DESC, task, model LIMIT 200")]
        counts = {r["task"]: r["n"] for r in c.execute("SELECT task, COUNT(DISTINCT month) AS n FROM ml_forecasts GROUP BY task")}
    for r in retrains:
        r["flags"] = json.loads(r.get("flags") or "[]")
    from api.ml.deep_config import fingerprint
    version=fingerprint()
    for p in promos:p['active']=p['model'] not in ('deep_sequence','average') or p.get('model_version')==version
    model_counts={}
    with _conn() as c:cohorts=[dict(r) for r in c.execute('SELECT task,model,month FROM ml_forecasts')]
    for r in cohorts:
        key=r['model']
        for v in ('deep_sequence','average'):
            if key==v+'__'+version:key=v
        model_counts.setdefault((r['task'],key),set()).add(r['month'])
    stages = []
    for name, task in TASKS.items():
        prom = next((p for p in promos if p["task"] == name and p['active']), None)
        d = cached(name)
        # the autonomous model serves without a promotion record once its own gates pass; show it as production then
        auto = ((d or {}).get("signal") or {}).get("model") == "autonomous_tft"
        for k in ROSTER + (["autonomous_tft"] if auto else []) + ["average"]:
            stage = ("production" if k == "autonomous_tft" else "shadow") if auto else \
                    "production" if (prom and prom["model"] == k) or (not prom and k == "champion") else "shadow"
            rec = ((d or {}).get("models") or {}).get(k) or {}
            stages.append({"task": name, "task_title": task.title, "model": k, "model_name": MODEL_INFO.get(k, (k,))[0],
                           "stage": stage, "probability": rec.get("probability"),
                           "skill": (rec.get("record") or {}).get("skill_vs_base_rate"), "gate": rec.get("gate"),
                           "live_months":len(model_counts.get((name,k),set()))})
    return {"stages": stages, "promotions": promos, "retrains": retrains, "recent_forecasts": recent,
            "deep_sequence_training":__import__("api.ml.deep",fromlist=["status"]).status(),"training": sorted(_training), "models": {k: {"name": v[0], "what": v[1]} for k, v in MODEL_INFO.items()}}
