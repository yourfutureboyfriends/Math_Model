"""
Stock-level portfolio optimisation (long-only, fully invested, per-name cap).

Methods
  * Equal weight (1/N) — the benchmark; DeMiguel, Garlappi & Uppal (2009) show estimated
    optimisers often fail to beat it out of sample, so every method is compared against it.
  * Minimum variance — on a Ledoit-Wolf (2004) shrunk covariance; with a weight cap this is a
    norm-constrained portfolio (DeMiguel, Garlappi, Nogales & Uppal, 2009).
  * Equal risk contribution — each name contributes the same share of risk, correlations
    included (Maillard, Roncalli & Teiletche, 2010).
  * Hierarchical risk parity — clusters the correlation matrix, no matrix inversion
    (López de Prado, 2016).
  * Maximum diversification — maximises weighted average volatility / portfolio volatility
    (Choueifaty & Coignard, 2008).
  * Black-Litterman — equilibrium returns implied by a prior (market-cap or equal) weight,
    blended with the entry model's views; view confidence per Idzorek (2005); then the
    maximum-Sharpe portfolio under the same constraints (Black & Litterman, 1992).

Pure functions: arrays in, arrays out. Returns are daily simple returns, annualised by 252.
"""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

PERIODS = 252
METHODS = ("equal_weight", "min_variance", "erc", "hrp", "max_diversification", "black_litterman")
LABELS = {
    "equal_weight": "Equal weight (1/N)",
    "min_variance": "Minimum variance",
    "erc": "Equal risk contribution",
    "hrp": "Hierarchical risk parity",
    "max_diversification": "Maximum diversification",
    "black_litterman": "Black-Litterman (model views)",
}
CITATIONS = {
    "equal_weight": "DeMiguel, Garlappi & Uppal (2009), Review of Financial Studies",
    "min_variance": "Ledoit & Wolf (2004) shrinkage; DeMiguel et al. (2009), Management Science",
    "erc": "Maillard, Roncalli & Teiletche (2010), Journal of Portfolio Management",
    "hrp": "López de Prado (2016), Journal of Portfolio Management",
    "max_diversification": "Choueifaty & Coignard (2008), Journal of Portfolio Management",
    "black_litterman": "Black & Litterman (1992); Idzorek (2005) view confidence",
}


# ── Estimation ───────────────────────────────────────────────────────────────
def shrunk_cov(returns: np.ndarray) -> np.ndarray:
    """Annualised Ledoit-Wolf shrinkage covariance (sample covariance pulled toward a scaled
    identity by the optimal intensity) — far better conditioned than the sample estimate."""
    from sklearn.covariance import LedoitWolf
    r = np.asarray(returns, dtype=float)
    return LedoitWolf().fit(r).covariance_ * PERIODS


def cap_weights(w: np.ndarray, max_w: float) -> np.ndarray:
    """Project onto {w ≥ 0, Σw = 1, w ≤ max_w}: clip and redistribute the excess pro rata."""
    w = np.clip(np.asarray(w, dtype=float), 0, None)
    n = w.size
    if n == 0:
        return w
    if w.sum() <= 0:
        w = np.ones(n)
    w = w / w.sum()
    cap = max(max_w, 1.0 / n)                 # infeasible caps relax to equal weight
    for _ in range(100):
        over = w > cap + 1e-12
        if not over.any():
            break
        excess = float((w[over] - cap).sum())
        w[over] = cap
        free = ~over & (w < cap - 1e-12)
        if not free.any():
            break
        w[free] += excess * w[free] / w[free].sum() if w[free].sum() > 0 else excess / free.sum()
    return w / w.sum()


def _solve(objective: Callable[[np.ndarray], float], n: int, max_w: float, x0: Optional[np.ndarray] = None) -> np.ndarray:
    from scipy.optimize import minimize
    cap = max(max_w, 1.0 / n)
    x0 = np.ones(n) / n if x0 is None else x0
    res = minimize(objective, x0, method="SLSQP", bounds=[(0.0, cap)] * n,
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1.0}],
                   options={"maxiter": 500, "ftol": 1e-12})
    w = res.x if res.success or np.isfinite(res.x).all() else x0
    return cap_weights(w, cap)


# ── Methods ──────────────────────────────────────────────────────────────────
def equal_weight(n: int) -> np.ndarray:
    return np.ones(n) / n


def min_variance(cov: np.ndarray, max_w: float) -> np.ndarray:
    return _solve(lambda w: float(w @ cov @ w), cov.shape[0], max_w)


def erc(cov: np.ndarray, max_w: float) -> np.ndarray:
    from api.calculations.rebalance import risk_budget_weights
    return cap_weights(risk_budget_weights(cov, np.ones(cov.shape[0])), max_w)


def hrp(returns: np.ndarray, max_w: float) -> np.ndarray:
    from api.calculations.risk_parity import hrp_weights
    return cap_weights(hrp_weights(np.asarray(returns, dtype=float)), max_w)


def diversification_ratio(w: np.ndarray, cov: np.ndarray) -> float:
    vol = float(np.sqrt(max(w @ cov @ w, 1e-18)))
    return float(w @ np.sqrt(np.diag(cov))) / vol


def max_diversification(cov: np.ndarray, max_w: float) -> np.ndarray:
    return _solve(lambda w: -diversification_ratio(w, cov), cov.shape[0], max_w)


def black_litterman_returns(cov: np.ndarray, prior_w: np.ndarray, views: np.ndarray, confidence: np.ndarray,
                            delta: float = 2.5, tau: float = 0.05) -> np.ndarray:
    """Posterior expected excess returns. One absolute view per asset: `views[i]` its expected
    annual excess return, `confidence[i]` ∈ (0, 1) — Ω_ii = (1/c − 1)·τ·Σ_ii (Idzorek-style:
    c→1 trusts the view fully, c→0 ignores it)."""
    pi = delta * cov @ prior_w                           # reverse-optimised equilibrium returns
    c = np.clip(np.asarray(confidence, dtype=float), 0.01, 0.99)
    omega = np.diag((1 / c - 1) * tau * np.diag(cov))
    ts = tau * cov
    a = np.linalg.inv(np.linalg.inv(ts) + np.linalg.inv(omega))
    return a @ (np.linalg.inv(ts) @ pi + np.linalg.inv(omega) @ np.asarray(views, dtype=float))


def max_sharpe(mu: np.ndarray, cov: np.ndarray, max_w: float) -> np.ndarray:
    def neg_sharpe(w):
        vol = math.sqrt(max(float(w @ cov @ w), 1e-18))
        return -float(w @ mu) / vol
    return _solve(neg_sharpe, cov.shape[0], max_w)


def model_views(setup_scores: Sequence[Optional[float]], scale: float = 0.10) -> tuple:
    """Entry-model set-up score (−1..+1) → an absolute annual excess-return view
    (score × `scale`) with confidence |score| (bounded 0.05–0.8). A missing score is a
    no-information view (zero return, minimal confidence)."""
    s = np.array([0.0 if x is None or not np.isfinite(x) else float(x) for x in setup_scores])
    return s * scale, np.clip(np.abs(s), 0.05, 0.8)


def weights_for(method: str, returns: np.ndarray, cov: np.ndarray, max_w: float,
                prior_w: Optional[np.ndarray] = None, setup_scores: Optional[Sequence] = None) -> np.ndarray:
    n = cov.shape[0]
    if method == "equal_weight":
        return equal_weight(n)
    if method == "min_variance":
        return min_variance(cov, max_w)
    if method == "erc":
        return erc(cov, max_w)
    if method == "hrp":
        return hrp(returns, max_w)
    if method == "max_diversification":
        return max_diversification(cov, max_w)
    if method == "black_litterman":
        prior = equal_weight(n) if prior_w is None else np.asarray(prior_w, dtype=float) / np.sum(prior_w)
        q, conf = model_views(setup_scores if setup_scores is not None else [None] * n)
        return max_sharpe(black_litterman_returns(cov, prior, q, conf), cov, max_w)
    raise ValueError(method)


# ── Diagnostics ──────────────────────────────────────────────────────────────
def describe(w: np.ndarray, cov: np.ndarray) -> Dict[str, object]:
    from api.calculations.rebalance import risk_contributions
    rc = risk_contributions(cov, w)
    return {"vol": round(float(np.sqrt(max(w @ cov @ w, 0))), 4),
            "diversification_ratio": round(diversification_ratio(w, cov), 3),
            "effective_n": round(float(1 / np.sum(w ** 2)), 2),
            "max_weight": round(float(w.max()), 4),
            "risk_contributions": [round(float(x), 4) for x in rc]}


def walk_forward(returns: np.ndarray, method: str, max_w: float, lookback: int = 252, rebalance: int = 21,
                 cost_bps: float = 10.0, prior_w: Optional[np.ndarray] = None,
                 setup_fn: Optional[Callable[[int], Sequence]] = None) -> Dict[str, object]:
    """Out-of-sample test: re-estimate on the trailing `lookback` days every `rebalance` days,
    hold (weights drift) until the next rebalance; costs on turnover. `setup_fn(t)` supplies
    the model's set-up scores known at day t (Black-Litterman views)."""
    r = np.asarray(returns, dtype=float)
    T, n = r.shape
    if T < lookback + rebalance:
        return {}
    port, turnover = [], []
    w = np.zeros(n)
    for t in range(lookback, T):
        if (t - lookback) % rebalance == 0:
            win = r[t - lookback:t]
            target = weights_for(method, win, shrunk_cov(win), max_w, prior_w,
                                 setup_fn(t) if setup_fn else None)
            to = float(np.abs(target - w).sum())
            turnover.append(to)
            day = float(target @ r[t]) - to * cost_bps / 1e4
            w = target
        else:
            day = float(w @ r[t])
        port.append(day)
        grown = w * (1 + r[t])
        w = grown / grown.sum() if grown.sum() > 0 else w
    p = np.array(port)
    nav = np.cumprod(1 + p)
    yrs = p.size / PERIODS
    vol = float(p.std(ddof=1) * math.sqrt(PERIODS))
    return {"cagr": round(float(nav[-1] ** (1 / yrs) - 1), 4), "vol": round(vol, 4),
            "sharpe": round(float(p.mean() * PERIODS / vol), 2) if vol > 0 else None,
            "max_drawdown": round(float((nav / np.maximum.accumulate(nav) - 1).min()), 4),
            "turnover_annual": round(float(np.mean(turnover) * PERIODS / rebalance), 2) if turnover else None,
            "nav": nav}
