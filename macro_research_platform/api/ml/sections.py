"""
Section experts with situation gating — a mixture-of-experts layer over every input the platform has.

The inputs are split into economic sections (rates & curve, credit, financial conditions, labour, activity, housing,
inflation, money & liquidity, markets, sentiment & news). Each section has its own expert: an L2-regularised logistic
model on that section's standardised inputs, refit every January on the months whose answers were known
(pseudo-out-of-sample, as the rest of the engine). A section joins the walk-forward from the year it has enough history
— so series that start in the 1990s or 2000s (VIX, high-yield spreads, breakevens, job openings) can be used — and is
marked missing before that.

A gate then combines the experts. Its inputs are each expert's log-odds, a missing flag per expert, and each expert's
log-odds interacted with the current *situation*: curve inverted, credit stress, high inflation, labour market turning,
volatility spike — point-in-time rules, not fitted states. So the weight on, say, the credit expert can differ when credit
is stressed. The gate is trained only on the experts' own earlier out-of-sample forecasts (stacking in time), so nothing
it learns has seen the answer; with too little history it falls back to the average of the experts' log-odds.

This follows how blocks are used in nowcasting (the New York Fed Staff Nowcast groups its data in blocks), stacked
generalisation (Wolpert 1992; Breiman 1996) and mixtures of experts with a gating network (Jacobs, Jordan, Nowlan &
Hinton 1991) — here deliberately small and heavily regularised, because monthly macro samples are short.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

SECTIONS: Dict[str, str] = {
    "core": "Task's core inputs (anchor)", "rates_curve": "Rates & curve", "credit": "Credit", "fin_conditions": "Financial conditions", "labour": "Labour",
    "activity": "Activity & surveys", "housing": "Housing", "inflation": "Inflation", "money": "Money & liquidity",
    "markets": "Markets & global", "sentiment": "Sentiment & news",
}
# core features → section
CORE_SECTION = {"ts": "rates_curve", "ntfs": "rates_curve", "y10": "rates_curve", "y10_d3": "rates_curve", "ff": "rates_curve",
                "ebp": "credit", "baa": "credit", "pay6": "labour", "unemp_d6": "labour", "cpi_yoy": "inflation", "cpi_d3": "inflation",
                "spx6": "markets", "usd6": "markets", "oil6": "markets", "spx_vol3": "fin_conditions", "sent_d6": "sentiment"}
# FRED-MD-style panel groups → section
PANEL_SECTION = {"Output & income": "activity", "Consumption & orders": "activity", "Labour": "labour", "Housing": "housing",
                 "Money & credit": "money", "Rates & spreads": "rates_curve", "FX": "markets", "Prices": "inflation"}
SITUATIONS = {"curve_inverted": "Yield curve inverted", "credit_stress": "Credit stress", "high_inflation": "High inflation",
              "labour_turning": "Labour market turning", "vol_spike": "Volatility spike"}

MIN_TRAIN = 120             # labelled months an expert needs
MIN_POS = 8                 # and positive months
MIN_COVER = 0.6             # share of a section's inputs a month must have
GATE_MIN = 120              # out-of-sample months the gate needs before it replaces the plain average
C_EXPERT = 0.3
LAMBDA_W, LAMBDA_V, V_MAX = 0.01, 0.05, 1.5    # gate: shrink weights towards equal, situation shifts firmly
K_SHRINK = 36              # track gate: months of overall record a situation's record is shrunk towards
GATE_KIND = "track"        # 'track' (skill-weighted, default) or 'softmax' (fitted mixture of experts)
N_FACT = 3                  # factors per section


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def inputs() -> Tuple[Dict[str, Dict[str, float]], Dict[str, str], Dict[str, str]]:
    """Every input by key → {month: value}, its section and its label."""
    from api.ml import extended as X
    from api.ml import features as F
    from api.ml import panel as PN
    feats, panel, text = F.load(), PN.load(), F.load_text()
    data: Dict[str, Dict[str, float]] = {}
    sec: Dict[str, str] = {}
    lab: Dict[str, str] = {}
    for k, v in feats.items():
        if k in CORE_SECTION and v:
            data[k], sec[k], lab[k] = v, CORE_SECTION[k], F.FEATURES.get(k, (k,))[0]
    for k, v in panel.items():
        g = PN.GROUP_OF.get(k)
        if v and g in PANEL_SECTION:
            # corporate-bond spreads belong to credit, not to rates
            s_ = "credit" if k in ("p_BAA_FF", "p_AAA_FF", "p_BAA_AAA", "p_BAA", "p_AAA") else PANEL_SECTION[g]
            data[k], sec[k], lab[k] = v, s_, PN.LABEL_OF.get(k, k)
    for k, v in text.items():
        if v:
            data[k], sec[k], lab[k] = v, "sentiment", F.TEXT.get(k, (k,))[0]
    for k, v in X.load().items():
        if v and k in X.SECTION_OF:                                     # cached series no longer listed are skipped
            data[k], sec[k], lab[k] = v, X.SECTION_OF[k], X.LABEL_OF[k]
    return data, sec, lab


def situation(data: Dict[str, Dict[str, float]], m: str) -> Dict[str, float]:
    """Point-in-time situation flags for a month (0/1), from inputs known then."""
    g = lambda k: data.get(k, {}).get(m)
    vol = g("x_VIXCLS") if g("x_VIXCLS") is not None else g("spx_vol3")
    return {"curve_inverted": float((g("ts") or 0) < 0),
            "credit_stress": float((g("ebp") or 0) > 0.5 or (g("x_NFCICREDIT") or 0) > 0.5),
            "high_inflation": float((g("cpi_yoy") or 0) > 4),
            "labour_turning": float((g("unemp_d6") or 0) > 0.3 or (g("x_SAHMREALTIME") or 0) >= 0.5),
            "vol_spike": float((vol or 0) > 28)}


class Expert:
    """One section: its inputs standardised and compressed to at most N_FACT principal-component factors (fitted on the
    training months — the New York Fed nowcast's block-factor idea), then an L2 logistic on those factors. Months with
    too few of the section's inputs are 'missing'; gaps are filled with the training mean before projecting."""

    def __init__(self, keys: List[str], compress: bool = True):
        self.keys, self.compress = keys, compress

    def matrix(self, data, months: List[str]) -> Tuple[np.ndarray, np.ndarray]:
        X = np.array([[data.get(k, {}).get(m, np.nan) for k in self.keys] for m in months], float)   # a series gone today counts as missing
        ok = np.isfinite(X).mean(1) >= MIN_COVER if len(self.keys) else np.zeros(len(months), bool)
        return X, ok

    def _z(self, X: np.ndarray) -> np.ndarray:
        Z = (X - self.mu) / self.sd
        return np.where(np.isfinite(Z), Z, 0.0)

    def fit(self, data, months: List[str], y: np.ndarray) -> Optional["Expert"]:
        from sklearn.linear_model import LogisticRegression
        X, ok = self.matrix(data, months)
        if ok.sum() < MIN_TRAIN or y[ok].sum() < MIN_POS or (1 - y[ok]).sum() < MIN_POS:
            return None
        X = X[ok]
        with np.errstate(all="ignore"):
            self.mu, self.sd = np.nanmean(X, 0), np.nanstd(X, 0)
        self.mu[~np.isfinite(self.mu)] = 0
        self.sd[~np.isfinite(self.sd) | (self.sd == 0)] = 1
        Z = self._z(X)
        k = min(N_FACT, Z.shape[1])
        if self.compress and Z.shape[1] > k:
            _, sv, vt = np.linalg.svd(Z - Z.mean(0), full_matrices=False)
            self.load = vt[:k].T                                           # inputs × factors
            self.share = (sv[:k] ** 2 / (sv ** 2).sum()).round(3).tolist()
        else:
            self.load, self.share = np.eye(Z.shape[1]), None
        F_ = Z @ self.load
        self.fsd = F_.std(0); self.fsd[self.fsd == 0] = 1
        self.m = LogisticRegression(C=C_EXPERT, max_iter=2000).fit(F_ / self.fsd, y[ok])
        return self

    def predict(self, data, months: List[str]) -> np.ndarray:
        X, ok = self.matrix(data, months)
        p = self.m.predict_proba((self._z(X) @ self.load) / self.fsd)[:, 1]
        p[~ok] = np.nan
        return p

    def weights(self) -> Dict[str, float]:
        """Each input's effective weight: the logistic coefficients mapped back through the factor loadings."""
        w = self.load @ (self.m.coef_[0] / self.fsd)
        return {k: round(float(c), 4) for k, c in zip(self.keys, w)}


class Gate:
    """Mixture-of-experts gate (Jacobs, Jordan, Nowlan & Hinton 1991): the weights on the available experts are a
    softmax — positive and summing to one — whose logits shift with the situation; the forecast is a calibrated
    weighted average of the experts' log-odds, z = a + b·Σ wᵢ·Lᵢ (b ≥ 0). A situation can change whom to trust but
    cannot amplify the experts beyond what they say — the failure of free stacking weights on a few episodes. The
    weight and situation parameters are shrunk to zero (equal weights) by an L2 penalty."""

    def _w(self, th: np.ndarray, L: np.ndarray, S: np.ndarray) -> np.ndarray:
        n, J = L.shape[1], S.shape[1]
        u, v = th[2:2 + n], th[2 + n:].reshape(n, J)
        g = u[None, :] + S @ v.T                                   # months × experts
        g = np.where(np.isfinite(L), g, -np.inf)
        g = g - np.max(np.where(np.isfinite(g), g, -1e9), axis=1, keepdims=True)
        e = np.where(np.isfinite(g), np.exp(g), 0.0)
        return e / np.maximum(e.sum(1, keepdims=True), 1e-12)

    def _z(self, th, L, S):
        W = self._w(th, L, S)
        return th[0] + th[1] * np.sum(W * np.where(np.isfinite(L), L, 0.0), axis=1), W

    def fit(self, L: np.ndarray, S: np.ndarray, y: np.ndarray) -> "Gate":
        from scipy.optimize import minimize
        n, J = L.shape[1], S.shape[1]

        def loss(th):
            z, _ = self._z(th, L, S)
            p = 1 / (1 + np.exp(-np.clip(z, -30, 30)))
            ll = -np.mean(y * np.log(p + 1e-12) + (1 - y) * np.log(1 - p + 1e-12))
            return ll + LAMBDA_W * np.sum(th[2:2 + n] ** 2) + LAMBDA_V * np.sum(th[2 + n:] ** 2)
        th0 = np.concatenate([[0.0, 1.0], np.zeros(n), np.zeros(n * J)])
        bounds = [(None, None), (0, 3)] + [(-4, 4)] * n + [(-V_MAX, V_MAX)] * (n * J)
        self.theta = minimize(loss, th0, method="L-BFGS-B", bounds=bounds, options={"maxiter": 300}).x
        return self

    def predict(self, L: np.ndarray, S: np.ndarray) -> np.ndarray:
        z, _ = self._z(self.theta, L, S)
        return 1 / (1 + np.exp(-np.clip(z, -30, 30)))

    def weights(self, L: np.ndarray, S: np.ndarray) -> np.ndarray:
        return self._w(self.theta, L, S)


class TrackGate:
    """Track-record gate (forecast combination: simple, skill-weighted averages beat optimised weights in short samples
    — Timmermann 2006). Each expert's weight is its earlier out-of-sample Brier skill against the base rate (floored at
    zero), measured in the months that shared the current situation and shrunk towards its overall record when that
    situation is rare: skill_s = (n_s·skill_in_s + K·skill_all) / (n_s + K). No fitted coefficients to overfit."""

    def fit(self, L: np.ndarray, S: np.ndarray, y: np.ndarray, base: np.ndarray) -> "TrackGate":
        n, J = L.shape[1], S.shape[1]
        P = 1 / (1 + np.exp(-np.where(np.isfinite(L), L, 0.0)))
        self.all = np.zeros(n)
        self.sit = np.zeros((n, J))
        self.cnt = np.zeros((n, J))
        for i in range(n):
            ok = np.isfinite(L[:, i])
            self.all[i] = self._skill(P[ok, i], y[ok], base[ok])
            for j in range(J):
                mk = ok & (S[:, j] > 0)
                self.cnt[i, j] = mk.sum()
                self.sit[i, j] = self._skill(P[mk, i], y[mk], base[mk]) if mk.sum() >= 12 else self.all[i]
        return self

    @staticmethod
    def _skill(p, y, b) -> float:
        if len(y) < 12:
            return 0.0
        bb = float(np.mean((b - y) ** 2))
        return 1 - float(np.mean((p - y) ** 2)) / bb if bb > 0 else 0.0

    def weights(self, L: np.ndarray, S: np.ndarray) -> np.ndarray:
        W = np.zeros_like(L, dtype=float)
        for t in range(L.shape[0]):
            act = np.where(S[t] > 0)[0]
            sc = self.all.copy() if not len(act) else np.mean(
                [(self.cnt[:, j] * self.sit[:, j] + K_SHRINK * self.all) / (self.cnt[:, j] + K_SHRINK) for j in act], axis=0)
            w = np.where(np.isfinite(L[t]), np.maximum(sc, 0.0), 0.0)
            W[t] = w / w.sum() if w.sum() > 0 else np.where(np.arange(L.shape[1]) == 0, 1.0, 0.0)   # none skilful: the anchor
        return W

    def predict(self, L: np.ndarray, S: np.ndarray) -> np.ndarray:
        W = self.weights(L, S)
        z = np.sum(W * np.where(np.isfinite(L), L, 0.0), axis=1)
        return 1 / (1 + np.exp(-z))


def _fallback(L: np.ndarray, prior: float) -> np.ndarray:
    """Before the gate has history: the anchor (the task's core inputs) where available, else the average of the
    available experts' log-odds, else the prior."""
    out = np.full(L.shape[0], float(_logit(np.array([prior]))[0]))
    for i in range(L.shape[0]):
        if np.isfinite(L[i, 0]):
            out[i] = L[i, 0]
        else:
            v = L[i][np.isfinite(L[i])]
            if v.size:
                out[i] = v.mean()
    return 1 / (1 + np.exp(-out))


def _make_gate(L_tr, S_tr, gy, gm, lab, y_of, task):
    """The configured gate, fitted on earlier out-of-sample expert forecasts (months gm)."""
    if GATE_KIND == "softmax":
        return Gate().fit(L_tr, S_tr, gy)
    from api.ml.engine import cutoff
    # each month's base rate: the share of yes among answers known before it (what 'no skill' would have said)
    known = [(m, y_of[m]) for m in lab]
    base = np.array([np.mean([v for mm, v in known if mm < cutoff(int(m[:4]), task.known_after)] or [gy.mean()]) for m in gm])
    return TrackGate().fit(L_tr, S_tr, gy, base)


def walk_forward(task, months: List[str], y_of: Dict[str, Optional[int]], data, sec: Dict[str, str]) -> Dict[str, Any]:
    """Experts and gate refit every January on answers known then. Returns month → probability (the gate's
    out-of-sample forecast), each expert's out-of-sample probabilities, and the situations."""
    from api.ml.engine import cutoff
    keys = {s: ([k for k in task.features if k in data] if s == "core" else [k for k in data if sec[k] == s]) for s in SECTIONS}
    lab = [m for m in months if y_of.get(m) is not None]
    years = sorted({int(m[:4]) for m in months})
    S_all = {m: situation(data, m) for m in months}
    oos: Dict[str, Dict[str, float]] = {s: {} for s in SECTIONS}
    out: Dict[str, float] = {}
    gate_used: Dict[int, str] = {}
    for yr in years:
        cut = cutoff(yr, task.known_after)
        tr = [m for m in lab if m < cut]
        te = [m for m in months if m[:4] == str(yr)]
        if len(tr) < MIN_TRAIN or not te:
            continue
        ytr = np.array([y_of[m] for m in tr], float)
        for s, ks in keys.items():
            e = Expert(ks, compress=s != "core").fit(data, tr, ytr) if ks else None
            if e is not None:
                for m, p in zip(te, e.predict(data, te)):
                    if np.isfinite(p):
                        oos[s][m] = float(p)
        # gate: trained on earlier out-of-sample expert forecasts whose answers are known by the cutoff
        gm = [m for m in tr if any(m in oos[s] for s in SECTIONS)]
        L_te = np.array([[_logit(np.array([oos[s][m]]))[0] if m in oos[s] else np.nan for s in SECTIONS] for m in te])
        S_te = np.array([[S_all[m][k] for k in SITUATIONS] for m in te])
        gy = np.array([y_of[m] for m in gm], float)
        if len(gm) >= GATE_MIN and gy.sum() >= MIN_POS and (1 - gy).sum() >= MIN_POS:
            L_tr = np.array([[_logit(np.array([oos[s][m]]))[0] if m in oos[s] else np.nan for s in SECTIONS] for m in gm])
            S_tr = np.array([[S_all[m][k] for k in SITUATIONS] for m in gm])
            p = _make_gate(L_tr, S_tr, gy, gm, lab, y_of, task).predict(L_te, S_te)
            gate_used[yr] = "gate"
        else:
            p = _fallback(L_te, float(ytr.mean()))
            gate_used[yr] = "anchor"
        for m, v in zip(te, p):
            out[m] = float(v)
    return {"prob": out, "experts": oos, "situations": S_all, "gate_used": gate_used, "keys": keys}


def live(task, months: List[str], y_of: Dict[str, Optional[int]], data, sec: Dict[str, str], wf: Dict[str, Any],
         labels: Dict[str, str]) -> Dict[str, Any]:
    """Today's reading: experts fit on every known answer, the gate fit on every out-of-sample expert forecast; each
    section's probability, its contribution to the final log-odds, and the situation now."""
    # the walk-forward may be cached from a day a series was available that is not today; use today's inputs
    keys = {s: [k for k in ks if k in data] for s, ks in wf["keys"].items()}
    oos = wf["experts"]
    lab = [m for m in months if y_of.get(m) is not None]
    y = np.array([y_of[m] for m in lab], float)
    now = months[-1]
    experts: Dict[str, Optional[Expert]] = {s: (Expert(ks, compress=s != "core").fit(data, lab, y) if ks else None) for s, ks in keys.items()}
    L_now = np.array([[_logit(experts[s].predict(data, [now]))[0] if experts[s] is not None and np.isfinite(experts[s].predict(data, [now])[0]) else np.nan
                       for s in SECTIONS]])
    S_now_d = situation(data, now)                                    # always today's, never the cached record's
    S_now = np.array([[S_now_d[k] for k in SITUATIONS]])
    gm = [m for m in lab if any(m in oos[s] for s in SECTIONS)]
    gy = np.array([y_of[m] for m in gm], float)
    contrib: Dict[str, float] = {}
    if len(gm) >= GATE_MIN and gy.sum() >= MIN_POS:
        L_tr = np.array([[_logit(np.array([oos[s][m]]))[0] if m in oos[s] else np.nan for s in SECTIONS] for m in gm])
        S_tr = np.array([[(wf["situations"].get(m) or situation(data, m))[k] for k in SITUATIONS] for m in gm])
        g = _make_gate(L_tr, S_tr, gy, gm, lab, y_of, task)
        p_now = float(g.predict(L_now, S_now)[0])
        W = g.weights(L_now, S_now)[0]
        b_ = float(g.theta[1]) if isinstance(g, Gate) else 1.0
        weights_now = {s: round(float(W[i]), 3) for i, s in enumerate(SECTIONS)}
        contrib = {s: float(b_ * W[i] * (L_now[0][i] if np.isfinite(L_now[0][i]) else 0.0)) for i, s in enumerate(SECTIONS)}
        method = "gate"
    else:
        p_now = float(_fallback(L_now, float(y.mean()))[0])
        weights_now = {s: (1.0 if s == "core" else 0.0) for s in SECTIONS}
        contrib = {s: float(L_now[0][0]) if s == "core" and np.isfinite(L_now[0][0]) else 0.0 for s in SECTIONS}
        method = "anchor"

    def skill(s: str) -> Dict[str, Any]:
        ms = [m for m in oos[s] if y_of.get(m) is not None]
        if len(ms) < 60:
            return {"months": len(ms)}
        p = np.array([oos[s][m] for m in ms])
        yy = np.array([y_of[m] for m in ms], float)
        from api.models_ml import recession_ensemble as R
        b = float(np.mean((yy.mean() - yy) ** 2))
        return {"months": len(ms), "from": ms[0], "brier": round(float(np.mean((p - yy) ** 2)), 4),
                "skill_vs_base_rate": round(1 - float(np.mean((p - yy) ** 2)) / b, 3) if b else None,
                "auroc": round(R._auc(p, yy), 3) if 0 < yy.sum() < len(yy) else None}
    rows = []
    for i, s in enumerate(SECTIONS):
        e = experts[s]
        top = sorted(e.weights().items(), key=lambda kv: -abs(kv[1]))[:5] if e is not None else []
        rows.append({"section": s, "label": SECTIONS[s], "inputs": len(keys[s]), "available": bool(np.isfinite(L_now[0][i])),
                     "probability": None if not np.isfinite(L_now[0][i]) else round(float(1 / (1 + np.exp(-L_now[0][i]))), 4),
                     "weight_now": weights_now.get(s), "contribution": round(contrib.get(s, 0.0), 4), "record": skill(s),
                     "top_inputs": [{"key": k, "label": labels.get(k, k), "coef": c} for k, c in top]})
    return {"probability_raw": round(p_now, 4), "method": method, "as_of": now,
            "situation": [{"key": k, "label": SITUATIONS[k], "on": bool(S_now_d[k])} for k in SITUATIONS],
            "sections": rows, "inputs_total": sum(len(v) for v in keys.values())}
