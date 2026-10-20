"""
Systemic-risk and cycle indicators from the published literature. Pure numpy functions.

* Financial turbulence — Kritzman & Li (2010), "Skulls, Financial Turbulence, and Risk
  Management", Financial Analysts Journal 66(5). d_t = (r_t − μ)' Σ⁻¹ (r_t − μ): the
  Mahalanobis distance of a day's cross-asset returns from their history. Captures extreme
  moves, decoupling of correlated assets and convergence of uncorrelated ones. The paper
  defines turbulent days as those above the 75th percentile.

* Absorption ratio — Kritzman, Li, Page & Rigobon (2011), "Principal Components as a Measure
  of Systemic Risk", Journal of Portfolio Management. Fraction of total variance explained by
  the first fifth of the eigenvectors; a high ratio means markets are tightly coupled and
  shocks propagate. The standardized shift compares the 15-day average with the 1-year
  average, in 1-year standard deviations.

* Near-term forward spread — Engstrom & Sharpe (2018/2019), "The Near-Term Forward Yield
  Spread as a Leading Indicator", Federal Reserve FEDS / Financial Analysts Journal: the
  forward rate on a 3-month bill six quarters ahead minus the current 3-month yield. A negative
  spread means markets price policy easing — historically a recession signal.

* Environmental balance — Bridgewater (Prince): reliable balance comes from equal risk across
  economic environments (rising/falling growth × rising/falling inflation), not equal risk
  across assets.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np


# ── Turbulence ───────────────────────────────────────────────────────────────
def turbulence_series(returns: np.ndarray, window: int = 756, min_window: int = 252) -> np.ndarray:
    """Turbulence for each day t, using the mean/covariance of the preceding `window` days
    (excluding t, so the reading is out-of-sample). NaN before `min_window` days."""
    T, n = returns.shape
    out = np.full(T, np.nan)
    for t in range(min_window, T):
        hist = returns[max(0, t - window):t]
        mu = hist.mean(axis=0)
        cov = np.cov(hist, rowvar=False)
        inv = np.linalg.pinv(cov)                       # robust to near-singular covariances
        d = returns[t] - mu
        out[t] = float(d @ inv @ d)
    return out


def percentile_of_last(series: np.ndarray) -> Optional[float]:
    """Percentile of the latest value among the PRIOR values (so a new high reads 100)."""
    s = series[~np.isnan(series)]
    if len(s) < 20:
        return None
    return round(float((s[:-1] <= s[-1]).mean() * 100), 1)


# ── Absorption ratio ─────────────────────────────────────────────────────────
def absorption_ratio(returns: np.ndarray, top_frac: float = 0.2, half_life: Optional[float] = 250) -> Optional[float]:
    """Share of total variance explained by the top ceil(top_frac * n) eigenvectors of the
    (exponentially weighted) covariance matrix of `returns` (T x n)."""
    T, n = returns.shape
    if T < n + 2:
        return None
    if half_life:
        w = 0.5 ** (np.arange(T)[::-1] / half_life)
        w = w / w.sum()
        mu = (w[:, None] * returns).sum(axis=0)
        x = returns - mu
        cov = (w[:, None] * x).T @ x
    else:
        cov = np.cov(returns, rowvar=False)
    eig = np.sort(np.linalg.eigvalsh(cov))[::-1]
    k = max(1, math.ceil(top_frac * n))
    total = eig.sum()
    return float(eig[:k].sum() / total) if total > 0 else None


def absorption_ratio_series(returns: np.ndarray, window: int = 500, step: int = 1, **kw) -> np.ndarray:
    T = returns.shape[0]
    out = np.full(T, np.nan)
    for t in range(window, T + 1, step):
        v = absorption_ratio(returns[t - window:t], **kw)
        out[t - 1] = np.nan if v is None else v
    return out


def standardized_shift(ar: np.ndarray, short: int = 15, long: int = 252) -> Optional[float]:
    """(short-window mean − long-window mean) / long-window std of the absorption ratio."""
    s = ar[~np.isnan(ar)]
    if len(s) < long:
        return None
    lo = s[-long:]
    sd = lo.std()
    return round(float((s[-short:].mean() - lo.mean()) / sd), 2) if sd > 0 else None


# ── Svensson curve and the near-term forward spread ──────────────────────────
def svensson_zero_yield(n_years: float, b0: float, b1: float, b2: float, b3: float,
                        tau1: float, tau2: float) -> float:
    """Continuously-compounded zero-coupon yield (percent) at maturity n (years) from the
    Svensson parameters published with the Gürkaynak–Sack–Wright curve."""
    x1, x2 = n_years / tau1, n_years / tau2
    f1 = (1 - math.exp(-x1)) / x1
    f2 = f1 - math.exp(-x1)
    f3 = (1 - math.exp(-x2)) / x2 - math.exp(-x2) if tau2 and not math.isnan(tau2) and not math.isnan(b3) else 0.0
    return b0 + b1 * f1 + b2 * f2 + (b3 * f3 if f3 else 0.0)


def near_term_forward_spread(params: Tuple[float, ...]) -> Optional[float]:
    """Engstrom–Sharpe: forward 3-month rate starting in 18 months minus the current 3-month
    zero yield, in percentage points (continuous compounding)."""
    try:
        y = lambda n: svensson_zero_yield(n, *params)   # noqa: E731
        fwd = (y(1.75) * 1.75 - y(1.5) * 1.5) / 0.25
        return fwd - y(0.25)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def fit_recession_probit(x: Sequence[float], y: Sequence[int]) -> Optional[Dict[str, float]]:
    """Probit P(y=1) = Φ(a + b·x) by Newton–Raphson (no statsmodels dependency)."""
    from statistics import NormalDist
    X = np.column_stack([np.ones(len(x)), np.asarray(x, float)])
    Y = np.asarray(y, float)
    if Y.sum() < 3 or (1 - Y).sum() < 3:
        return None
    beta = np.zeros(2)
    nd = NormalDist()
    for _ in range(50):
        z = X @ beta
        p = np.clip(np.array([nd.cdf(v) for v in z]), 1e-9, 1 - 1e-9)
        phi = np.array([nd.pdf(v) for v in z])
        grad = X.T @ (phi * (Y - p) / (p * (1 - p)))
        w = phi ** 2 / (p * (1 - p))
        hess = -(X * w[:, None]).T @ X
        step = np.linalg.solve(hess, grad)
        beta = beta - step
        if np.abs(step).max() < 1e-8:
            break
    return {"intercept": float(beta[0]), "slope": float(beta[1])}


def probit_prob(model: Dict[str, float], x: float) -> float:
    from statistics import NormalDist
    return NormalDist().cdf(model["intercept"] + model["slope"] * x)


# ── Environmental balance ────────────────────────────────────────────────────
# Which environments each asset class tends to do well in (two each), per the four-box
# growth × inflation framework.
ENVIRONMENTS = ("Rising growth", "Falling growth", "Rising inflation", "Falling inflation")
ASSET_ENVIRONMENTS: Dict[str, Tuple[str, str]] = {
    "Equity": ("Rising growth", "Falling inflation"),
    "Corporate credit": ("Rising growth", "Falling inflation"),
    "Nominal bonds": ("Falling growth", "Falling inflation"),
    "Inflation-linked bonds": ("Falling growth", "Rising inflation"),
    "Commodities": ("Rising growth", "Rising inflation"),
    "Gold": ("Falling growth", "Rising inflation"),
}


def environment_risk_split(risk_by_asset_class: Dict[str, float]) -> Dict[str, float]:
    """Share of portfolio risk exposed to each environment: each asset class's risk is split
    equally between its two environments. Shares sum to 2 (each unit counts twice), so they
    are normalised to sum to 1."""
    env = {e: 0.0 for e in ENVIRONMENTS}
    for ac, risk in risk_by_asset_class.items():
        envs = ASSET_ENVIRONMENTS.get(ac)
        if not envs or risk <= 0:
            continue
        for e in envs:
            env[e] += risk / 2
    total = sum(env.values())
    return {e: round(v / total, 4) for e, v in env.items()} if total > 0 else env


def balance_score(split: Dict[str, float]) -> Optional[float]:
    """1 = perfectly balanced across the four environments, 0 = all in one."""
    vals = [v for v in split.values()]
    if not vals or sum(vals) <= 0:
        return None
    dev = sum(abs(v - 0.25) for v in vals)          # max 1.5 (all risk in one box)
    return round(1 - dev / 1.5, 3)


def environment_balanced_weights(vols: Dict[str, float]) -> Dict[str, float]:
    """Asset-class weights giving each environment equal risk: each environment's 25% risk
    budget is split equally among its asset classes; an asset's risk budget is the sum over
    its environments, and weight ∝ budget / volatility (ignoring correlations, as in the
    simple four-box construction)."""
    members = {e: [ac for ac, envs in ASSET_ENVIRONMENTS.items() if e in envs and vols.get(ac)] for e in ENVIRONMENTS}
    budget: Dict[str, float] = {}
    for e, acs in members.items():
        for ac in acs:
            budget[ac] = budget.get(ac, 0.0) + 0.25 / len(acs)
    raw = {ac: b / vols[ac] for ac, b in budget.items() if vols.get(ac)}
    tot = sum(raw.values())
    return {ac: round(v / tot, 4) for ac, v in raw.items()} if tot > 0 else {}
