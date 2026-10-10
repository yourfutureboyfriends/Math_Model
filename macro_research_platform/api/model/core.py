"""
Systematic macro model — the numerical core (pure functions; no I/O).

Pipeline, all evaluated with information available at the decision date:

1. FACTORS  Diffusion-index factors (Stock & Watson, 2002): the first principal component
   of a block of standardised, stationary series — one GROWTH factor, one INFLATION factor.
   Standardisation uses only data up to the decision date (expanding window).

2. REGIMES  The four growth/inflation regimes are defined by the DIRECTION of each factor over
   three months (rising / falling). For next month, P(growth rising) and P(inflation rising)
   come from logistic models on each factor's level and recent change, fitted on history only;
   regime probabilities are their product (independence assumption, reported).

3. EXPECTED RETURNS  Each asset's mean monthly excess return in each realised regime, shrunk
   toward its unconditional mean (weight n_q / (n_q + k)), weighted by next month's regime
   probabilities: E[r_a] = Σ_q P(q) · μ̂_{a,q}.

4. PORTFOLIO  Black–Litterman (Black & Litterman, 1992; He & Litterman, 1999): the prior is the
   environment-balanced portfolio (equal risk to each growth/inflation environment); the views
   are the model's expected returns. Then mean–variance with a volatility target, long-only,
   per-asset caps, residual in cash.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

QUADRANTS = ("Goldilocks", "Reflation", "Stagflation", "Deflationary slowdown")
# (growth rising?, inflation rising?) -> regime
QUADRANT_OF = {(True, False): "Goldilocks", (True, True): "Reflation",
               (False, True): "Stagflation", (False, False): "Deflationary slowdown"}


@dataclass
class ModelParams:
    vol_target: float = 0.10            # annualised portfolio volatility target
    max_weight: float = 0.35            # per-asset cap
    risk_aversion: float = 2.5          # δ in Black–Litterman and the optimiser
    tau: float = 0.05                   # BL prior uncertainty scale
    view_confidence: float = 1.0        # >1 trusts the model's views more
    shrinkage_months: int = 36          # k in the regime-mean shrinkage
    cov_months: int = 60                # covariance estimation window
    min_history_months: int = 120       # before an asset is admitted to estimation
    momentum_months: int = 3            # regime direction window
    cost_bps: float = 10.0              # one-way transaction cost in the backtest
    max_gross: float = 1.0              # 1.0 = no leverage; >1 lets the strategic portfolio reach the vol target

    @classmethod
    def from_dict(cls, d: Optional[Dict]) -> "ModelParams":
        p = cls()
        for k, v in (d or {}).items():
            if hasattr(p, k) and v is not None:
                setattr(p, k, type(getattr(p, k))(v))
        return p


# ── 1. Factors ───────────────────────────────────────────────────────────────
def diffusion_factor(block: pd.DataFrame, anchor: str) -> Tuple[pd.Series, Dict[str, float]]:
    """First principal component of a block (columns = series, index = month), standardised
    with the block's own history (call with data truncated at the decision date). Rows need at
    least half the series; missing values are set to the series mean (0 after standardising).
    Sign normalised so `anchor` loads positively."""
    b = block.dropna(how="all")
    b = b.loc[:, b.count() >= 36]
    if b.shape[1] < 2:
        return pd.Series(dtype=float), {}
    z = (b - b.mean()) / b.std(ddof=0)
    z = z[z.count(axis=1) >= max(2, b.shape[1] // 2)].fillna(0.0)
    if len(z) < 36:
        return pd.Series(dtype=float), {}
    _, _, vt = np.linalg.svd(z.values - z.values.mean(axis=0), full_matrices=False)
    load = vt[0]
    if anchor in z.columns and load[list(z.columns).index(anchor)] < 0:
        load = -load
    f = pd.Series(z.values @ load / np.sqrt((load ** 2).sum()), index=z.index)
    f = (f - f.mean()) / f.std(ddof=0)
    return f, {c: round(float(v), 3) for c, v in zip(z.columns, load)}


# ── 2. Regimes ───────────────────────────────────────────────────────────────
def direction_features(f: pd.Series, k: int) -> pd.DataFrame:
    return pd.DataFrame({"level": f, "change": f - f.shift(k)})


def direction_probability(f: pd.Series, k: int = 3, horizon: int = 1) -> Optional[Dict]:
    """P(the factor's k-month change, measured `horizon` months ahead, is positive), from a
    logistic regression on [level, k-month change] fitted on the factor's own history.
    The factor is indexed by publication month (the panel is lag-shifted), so horizon=1 is
    exactly the regime label of the month being allocated for."""
    from sklearn.linear_model import LogisticRegression
    X = direction_features(f, k)
    y = (f.shift(-horizon) - f.shift(-horizon + k) > 0).astype(float)
    y[f.shift(-horizon).isna()] = np.nan
    train = pd.concat([X, y.rename("y")], axis=1).dropna()
    if len(train) < 60 or train["y"].nunique() < 2:
        return None
    m = LogisticRegression(C=1.0).fit(train[["level", "change"]].values, train["y"].values)
    x_now = X.iloc[[-1]].values
    if np.isnan(x_now).any():
        return None
    p = float(m.predict_proba(x_now)[0, 1])
    base = float(train["y"].mean())
    return {"probability": p, "base_rate": base, "coef": [round(float(c), 3) for c in m.coef_[0]],
            "n": len(train)}


def quadrant_probabilities(p_growth_up: float, p_infl_up: float) -> Dict[str, float]:
    return {QUADRANT_OF[(g, i)]: (p_growth_up if g else 1 - p_growth_up) * (p_infl_up if i else 1 - p_infl_up)
            for g in (True, False) for i in (True, False)}


def realized_regimes(g: pd.Series, i: pd.Series, k: int = 3) -> pd.Series:
    dg, di = g - g.shift(k), i - i.shift(k)
    lab = pd.Series(index=g.index, dtype=object)
    ok = dg.notna() & di.notna()
    lab[ok] = [QUADRANT_OF[(a > 0, b > 0)] for a, b in zip(dg[ok], di[ok])]
    return lab


# ── 3. Expected returns ──────────────────────────────────────────────────────
def regime_conditional_means(rets: pd.DataFrame, labels: pd.Series, k: int) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """Mean monthly excess return per asset per regime, shrunk toward the asset's overall mean:
    μ̂ = (n_q · μ_q + k · μ) / (n_q + k)."""
    df = rets.join(labels.rename("_q"), how="inner").dropna(subset=["_q"])
    overall = df.drop(columns="_q").mean()
    out, counts = {}, {}
    for q in QUADRANTS:
        sub = df[df["_q"] == q].drop(columns="_q")
        n = sub.notna().sum()
        counts[q] = int(len(sub))
        mu_q = sub.mean().fillna(overall)
        out[q] = (n * mu_q + k * overall) / (n + k)
    return pd.DataFrame(out), counts


def expected_returns(cond: pd.DataFrame, probs: Dict[str, float]) -> pd.Series:
    return sum(cond[q] * probs.get(q, 0.0) for q in QUADRANTS)


def shrunk_covariance(rets: pd.DataFrame) -> np.ndarray:
    from sklearn.covariance import LedoitWolf
    x = rets.dropna().values
    return LedoitWolf().fit(x).covariance_


# ── 4. Portfolio ─────────────────────────────────────────────────────────────
def environment_prior(assets: Sequence[str], env_class: Dict[str, str], vols: np.ndarray) -> np.ndarray:
    """Equal risk to each growth/inflation environment (class level), split within a class by
    inverse volatility."""
    from api.calculations.systemic_risk import environment_balanced_weights
    cls_vol: Dict[str, List[float]] = {}
    for a, v in zip(assets, vols):
        cls_vol.setdefault(env_class[a], []).append(v)
    class_w = environment_balanced_weights({c: float(np.mean(v)) for c, v in cls_vol.items()})
    w = np.zeros(len(assets))
    for c, cw in class_w.items():
        idx = [j for j, a in enumerate(assets) if env_class[a] == c]
        inv = np.array([1 / vols[j] for j in idx])
        w[idx] = cw * inv / inv.sum()
    return w / w.sum() if w.sum() > 0 else np.full(len(assets), 1 / len(assets))


def black_litterman(cov: np.ndarray, w_prior: np.ndarray, views: np.ndarray, delta: float,
                    tau: float, confidence: float) -> Tuple[np.ndarray, np.ndarray]:
    """Posterior expected returns with absolute views on every asset (P = I):
    μ = [(τΣ)⁻¹ + Ω⁻¹]⁻¹ [(τΣ)⁻¹ π + Ω⁻¹ Q], π = δ Σ w_prior, Ω = diag(τΣ) / confidence."""
    pi = delta * cov @ w_prior
    ts = tau * cov
    omega = np.diag(np.diag(ts)) / max(confidence, 1e-6)
    a = np.linalg.inv(ts) + np.linalg.inv(omega)
    b = np.linalg.inv(ts) @ pi + np.linalg.inv(omega) @ views
    return np.linalg.solve(a, b), pi


def optimize(mu: np.ndarray, cov: np.ndarray, delta: float, max_w: float, vol_target_monthly: float) -> np.ndarray:
    """max w'μ − δ/2 w'Σw  s.t. 0 ≤ w ≤ max_w, Σw ≤ 1; then scaled down (into cash) if the
    portfolio's volatility exceeds the target. No leverage."""
    from scipy.optimize import minimize
    n = len(mu)
    obj = lambda w: -(w @ mu - 0.5 * delta * w @ cov @ w)          # noqa: E731
    jac = lambda w: -(mu - delta * cov @ w)                         # noqa: E731
    w0 = np.full(n, min(max_w, 1 / n))
    res = minimize(obj, w0, jac=jac, method="SLSQP", bounds=[(0, max_w)] * n,
                   constraints=[{"type": "ineq", "fun": lambda w: 1 - w.sum()}],
                   options={"maxiter": 500, "ftol": 1e-12})
    w = np.clip(res.x if res.success else w0, 0, max_w)
    vol = math.sqrt(max(w @ cov @ w, 0))
    if vol > vol_target_monthly > 0:
        w = w * vol_target_monthly / vol
    return w


def scale_to_target(w: np.ndarray, cov: np.ndarray, vol_target_monthly: float, max_gross: float) -> np.ndarray:
    """Scale a portfolio to the volatility target, within the gross-exposure limit."""
    vol = math.sqrt(max(w @ cov @ w, 0))
    if vol <= 0:
        return w
    k = min(vol_target_monthly / vol, max_gross / max(w.sum(), 1e-12))
    return w * k


def risk_contributions(w: np.ndarray, cov: np.ndarray) -> np.ndarray:
    total = w @ cov @ w
    return (w * (cov @ w)) / total if total > 0 else np.zeros_like(w)


# ── One decision ─────────────────────────────────────────────────────────────
@dataclass
class Decision:
    as_of: pd.Timestamp
    assets: List[str]
    weights: np.ndarray
    cash: float
    regime_probs: Dict[str, float]
    p_growth_up: Dict
    p_inflation_up: Dict
    exp_model: np.ndarray            # regime-conditional expected excess returns (monthly)
    exp_bl: np.ndarray               # Black-Litterman posterior (monthly)
    prior: np.ndarray
    strategic: np.ndarray            # environment-balanced, vol-targeted (no views)
    cov: np.ndarray
    cond_means: pd.DataFrame
    regime_counts: Dict[str, int]
    growth: pd.Series = field(default_factory=pd.Series)
    inflation: pd.Series = field(default_factory=pd.Series)
    loadings: Dict[str, Dict[str, float]] = field(default_factory=dict)


def decide(panel: pd.DataFrame, rets: pd.DataFrame, blocks: Dict[str, str], env_class: Dict[str, str],
           as_of: pd.Timestamp, p: ModelParams) -> Optional[Decision]:
    """The model's allocation for the month after `as_of`, using only data up to `as_of`."""
    pan = panel[panel.index <= as_of]
    g_cols = [c for c, b in blocks.items() if b == "growth" and c in pan]
    i_cols = [c for c, b in blocks.items() if b == "inflation" and c in pan]
    g, gl = diffusion_factor(pan[g_cols], "INDPRO")
    i, il = diffusion_factor(pan[i_cols], "CPIAUCSL")
    if g.empty or i.empty:
        return None
    pg = direction_probability(g, p.momentum_months)
    pi_ = direction_probability(i, p.momentum_months)
    if not pg or not pi_:
        return None
    probs = quadrant_probabilities(pg["probability"], pi_["probability"])

    r = rets[rets.index <= as_of]
    assets = [a for a in r.columns if r[a].count() >= p.min_history_months]
    if len(assets) < 3:
        return None
    labels = realized_regimes(g, i, p.momentum_months)
    cond, counts = regime_conditional_means(r[assets], labels, p.shrinkage_months)
    mu_model = expected_returns(cond, probs).values
    window = r[assets].tail(p.cov_months).dropna()
    if len(window) < 24:
        return None
    cov = shrunk_covariance(window)
    vols = np.sqrt(np.diag(cov))
    prior = environment_prior(assets, env_class, vols)
    mu_bl, _ = black_litterman(cov, prior, mu_model, p.risk_aversion, p.tau, p.view_confidence)
    target_m = p.vol_target / math.sqrt(12)
    w = optimize(mu_bl, cov, p.risk_aversion, p.max_weight, target_m)
    strategic = scale_to_target(prior, cov, target_m, p.max_gross)
    return Decision(as_of, assets, w, float(1 - w.sum()), probs, pg, pi_, mu_model, mu_bl, prior, strategic,
                    cov, cond, counts, g, i, {"growth": gl, "inflation": il})
