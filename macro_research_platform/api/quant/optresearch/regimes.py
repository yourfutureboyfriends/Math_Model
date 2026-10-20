"""
Market-regime research: causal features, a rules baseline, and learned classifiers (logistic regression, random forest,
gradient-boosted trees, a Gaussian hidden Markov model), compared out of sample.

Features (S&P 500 via SPY, each from data up to that close): distance from the 50/200-day averages, 1/3/6/12-month
momentum, 21/63-day realised volatility, implied volatility (VIX), its 1-year percentile, the volatility risk premium
(VIX − realised), VIX term slope (3-month ÷ 1-month), ADX trend strength, drawdown from the 1-year high, and breadth
(share of point-in-time S&P 500 members above their 200-day average, and with positive 12-1 momentum).

Target: the next 21 sessions' S&P return relative to the implied move m = VIX·√(21/252): bull (> +0.5m),
bear (< −0.5m), range (otherwise).

Walk-forward: models are refitted each January on everything up to 21 sessions earlier (an embargo, so no training
label overlaps the test period) and predict that year. The HMM is fitted unsupervised on the 5-day return and log realised
vol; its states are named by their training-set majority label; predictions use the forward (filtering) probabilities
only — never the smoothed or Viterbi path, which would look ahead.

Gating (pre-declared, not optimised): bull → bull put, bull call, half-size condor; range → condor, bull put;
bear → bear put; stress (rules model only: VIX ≥ 30 or inverted term structure) → bear put at half size.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

CLASSES = ["bull", "range", "bear"]
GATES: Dict[str, Dict[str, float]] = {
    "bull": {"bull_put": 1.0, "bull_call": 1.0, "bear_put": 0.0, "iron_condor": 0.5},
    "range": {"bull_put": 1.0, "bull_call": 0.0, "bear_put": 0.0, "iron_condor": 1.0},
    "bear": {"bull_put": 0.0, "bull_call": 0.0, "bear_put": 1.0, "iron_condor": 0.0},
    "stress": {"bull_put": 0.0, "bull_call": 0.0, "bear_put": 0.5, "iron_condor": 0.0},
}
HORIZON = 21
FEATURES = ["dist50", "dist200", "mom1", "mom3", "mom6", "mom12", "rv21", "rv63", "vix", "vix_pct", "vrp", "term",
            "adx", "dd", "breadth200", "breadth_mom"]


def features(panel, surf: Dict[str, Any], breadth_panel=None) -> pd.DataFrame:
    """breadth_panel: the full research panel (breadth needs every point-in-time member, not a stage's subset)."""
    from api.quant.optresearch.strategies import _adx
    c = panel.frame("close")
    bp = breadth_panel if breadth_panel is not None else panel
    cb = bp.frame("close").reindex(c.index)
    s = c["SPY"]
    lr = np.log(s / s.shift(1))
    vix = pd.Series(surf["vix"], index=c.index)
    P = surf["P"]
    term = pd.Series(P[:, 2] / np.where(P[:, 1] > 0, P[:, 1], np.nan), index=c.index)
    sma200_all = cb.rolling(200, min_periods=180).mean()
    mem = pd.DataFrame(bp.a["members"], index=bp.dates, columns=bp.tickers).reindex(c.index).fillna(False).astype(bool)
    stocks = mem.any(axis=0)
    above = (cb > sma200_all).where(mem)
    mom12_all = cb.shift(21) / cb.shift(252) - 1
    f = pd.DataFrame({
        "dist50": s / s.rolling(50).mean() - 1, "dist200": s / s.rolling(200).mean() - 1,
        "mom1": s / s.shift(21) - 1, "mom3": s / s.shift(63) - 1, "mom6": s / s.shift(126) - 1,
        "mom12": s.shift(21) / s.shift(252) - 1,
        "rv21": lr.rolling(21).std() * np.sqrt(252), "rv63": lr.rolling(63).std() * np.sqrt(252),
        "vix": vix, "vix_pct": vix.rolling(252, min_periods=120).rank(pct=True),
        "vrp": vix - lr.rolling(21).std() * np.sqrt(252), "term": term,
        "adx": _adx(panel.frame("high")[["SPY"]], panel.frame("low")[["SPY"]], c[["SPY"]])["SPY"],
        "dd": s / s.rolling(252, min_periods=60).max() - 1,
        "breadth200": above.loc[:, stocks].mean(axis=1),
        "breadth_mom": (mom12_all > 0).where(mem).loc[:, stocks].mean(axis=1),
        "ret5": s / s.shift(5) - 1,                                    # HMM observation (with log rv21)
    })
    return f


def labels(panel, surf: Dict[str, Any]) -> pd.Series:
    """Forward 21-session class (NaN where the window runs past the data). Known only HORIZON sessions later."""
    s = panel.frame("close")["SPY"]
    fwd = s.shift(-HORIZON) / s - 1
    m = pd.Series(surf["vix"], index=s.index) * np.sqrt(HORIZON / 252)
    y = pd.Series(np.where(fwd > 0.5 * m, 0, np.where(fwd < -0.5 * m, 2, 1)), index=s.index, dtype=float)
    return y.where(fwd.notna())


def rules(f: pd.DataFrame) -> pd.Series:
    """Baseline: stress (VIX ≥ 30 or term inverted) > bear (below the 200-day with negative 6-month momentum, or a
    10% drawdown) > range (ADX < 20 and within 3% of the 50-day) > bull."""
    stress = (f["vix"] >= 0.30) | (f["term"] < 0.97)
    bear = ((f["dist200"] < 0) & (f["mom6"] < 0)) | (f["dd"] < -0.10)
    rng = (f["adx"] < 20) & (f["dist50"].abs() < 0.03)
    out = np.where(stress, "stress", np.where(bear, "bear", np.where(rng, "range", "bull")))
    return pd.Series(out, index=f.index).where(f[["dist200", "vix", "adx"]].notna().all(axis=1))


def _model(kind: str):
    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    if kind == "logistic":
        return make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=2000))
    if kind == "random_forest":
        return RandomForestClassifier(n_estimators=300, max_depth=4, min_samples_leaf=60, random_state=7, n_jobs=4)
    if kind == "gbdt":
        return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=60,
                                              l2_regularization=1.0, random_state=7)
    raise ValueError(kind)


def _hmm_filter(model, X: np.ndarray) -> np.ndarray:
    """Forward-filtered state probabilities P(state_t | x_1..x_t) — causal, unlike predict()/predict_proba()."""
    from scipy.stats import multivariate_normal
    K = model.n_components
    logB = np.column_stack([multivariate_normal(model.means_[k], model.covars_[k], allow_singular=True).logpdf(X)
                            for k in range(K)])
    A = model.transmat_
    out = np.zeros((len(X), K))
    a = model.startprob_ * np.exp(logB[0] - logB[0].max())
    a /= a.sum()
    out[0] = a
    for t in range(1, len(X)):
        a = (a @ A) * np.exp(logB[t] - logB[t].max())
        s = a.sum()
        a = a / s if s > 0 else np.full(K, 1 / K)
        out[t] = a
    return out


def walk_forward(f: pd.DataFrame, y: pd.Series, first_year: int, last_date: Optional[pd.Timestamp] = None,
                 kinds=("logistic", "random_forest", "gbdt", "hmm")) -> Dict[str, pd.Series]:
    """Out-of-sample class predictions (strings) per model, refitted each January with a 21-session embargo."""
    X = f[FEATURES]
    ok_x = X.notna().all(axis=1)
    idx = f.index
    years = sorted({d.year for d in idx if d.year >= first_year and (last_date is None or d <= last_date)})
    preds = {k: pd.Series(np.nan, index=idx, dtype=object) for k in kinds}
    for yr in years:
        test = (idx.year == yr) & ok_x.to_numpy()
        if last_date is not None:
            test &= idx <= last_date
        if not test.any():
            continue
        first_test = np.nonzero(idx.year == yr)[0][0]
        cut = first_test - HORIZON                                    # labels of training rows end before the test year
        train = np.zeros(len(idx), bool)
        train[:max(cut, 0)] = True
        train &= ok_x.to_numpy() & y.notna().to_numpy()
        if train.sum() < 500:
            continue
        Xtr, ytr = X[train].to_numpy(), y[train].to_numpy().astype(int)
        for k in kinds:
            if k == "hmm":
                from hmmlearn.hmm import GaussianHMM
                obs = np.column_stack([f["ret5"].to_numpy(), np.log(f["rv21"].to_numpy())])
                okh = np.isfinite(obs).all(axis=1)
                tr_h = train & okh
                m = GaussianHMM(n_components=3, covariance_type="full", n_iter=200, random_state=7)
                m.fit(obs[tr_h])
                # filter from the start of usable data through the test year (causal at every step)
                upto = np.nonzero(okh & (np.arange(len(idx)) <= np.nonzero(test)[0][-1]))[0]
                probs = _hmm_filter(m, obs[upto])
                st = probs.argmax(axis=1)
                st_full = pd.Series(st, index=idx[upto])
                tr_states = st_full.reindex(idx[tr_h]).to_numpy()
                ytr_h = y[tr_h].to_numpy().astype(int)
                name = {}
                for s_ in range(3):
                    lab = ytr_h[tr_states == s_]
                    name[s_] = CLASSES[int(np.bincount(lab, minlength=3).argmax())] if len(lab) else "range"
                pt = st_full.reindex(idx[test])
                preds[k][test] = [name[int(v)] if np.isfinite(v) else np.nan for v in pt.to_numpy()]
            else:
                m = _model(k)
                m.fit(Xtr, ytr)
                preds[k][test] = [CLASSES[int(v)] for v in m.predict(X[test].to_numpy())]
    return preds


def scores(pred: pd.Series, y: pd.Series, base: Optional[str] = None) -> Dict[str, Any]:
    """Accuracy and balanced accuracy where both prediction and outcome exist (stress counts as bear)."""
    p = pred.replace({"stress": "bear"})
    ok = p.notna() & y.notna()
    if ok.sum() < 50:
        return {"days": int(ok.sum())}
    yt = y[ok].astype(int).map(lambda v: CLASSES[v])
    pp = p[ok]
    acc = float((yt == pp).mean())
    bal = float(np.mean([(pp[yt == c] == c).mean() for c in CLASSES if (yt == c).any()]))
    maj = yt.value_counts().idxmax()
    return {"days": int(ok.sum()), "accuracy": round(acc, 3), "balanced_accuracy": round(bal, 3),
            "majority_class": maj, "majority_accuracy": round(float((yt == maj).mean()), 3),
            "predicted_mix": {c: round(float((pp == c).mean()), 3) for c in CLASSES}}


def gates(pred: pd.Series, n: int) -> Dict[str, np.ndarray]:
    """Per-strategy risk multipliers per session from regime predictions (no prediction → nothing new opens)."""
    out = {}
    for s in ("bull_put", "bull_call", "bear_put", "iron_condor"):
        out[s] = np.array([GATES[v][s] if isinstance(v, str) and v in GATES else 0.0 for v in pred.to_numpy()])[:n]
    return out
