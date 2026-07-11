"""
Risk-parity allocation methods + honest backtest — pure, tested (Phase 2).

Implements four allocation schemes and a 60/40 benchmark so they can be compared on the same
real asset returns, directly addressing the research:
- Traditional Risk Parity (inverse-vol) — the naive version the panel used to ship.
- Return-overlay RP — blends risk weights with a simple expected-return tilt, per
  "Risk Parity and its Discontents" (2025): pure risk weighting generally *underperforms*
  60/40 unless an expected-return model is added.
- Hierarchical Risk Parity (HRP) — López de Prado (2016): clusters the correlation matrix and
  allocates by recursive bisection; robust to covariance estimation error.
- CVaR Risk Parity — allocates by tail risk (Conditional VaR) rather than variance.

Backtest reports Sharpe, Sortino, max drawdown honestly (weights are full-sample static — a
comparison of weighting schemes, not a walk-forward; stated as a caveat).
"""
from __future__ import annotations

from typing import Dict, List, Sequence
import numpy as np


def _ann(mean_daily: float) -> float:
    return mean_daily * 252


def inverse_vol_weights(returns: np.ndarray) -> np.ndarray:
    """Traditional (naive) risk parity: weight inversely to volatility."""
    vol = returns.std(axis=0, ddof=1)
    vol = np.where(vol == 0, 1e-9, vol)
    w = 1.0 / vol
    return w / w.sum()


def cvar_weights(returns: np.ndarray, alpha: float = 0.05) -> np.ndarray:
    """CVaR risk parity: weight inversely to each asset's Conditional VaR (mean of worst
    `alpha` tail)."""
    n = returns.shape[1]
    cvar = np.zeros(n)
    for j in range(n):
        col = np.sort(returns[:, j])
        k = max(1, int(len(col) * alpha))
        cvar[j] = -col[:k].mean()          # positive tail-loss magnitude
    cvar = np.where(cvar <= 0, 1e-9, cvar)
    w = 1.0 / cvar
    return w / w.sum()


def _hrp_quasi_diag(link) -> List[int]:
    link = link.astype(int)
    n = link[-1, 3]
    order = [link[-1, 0], link[-1, 1]]
    while max(order) >= n:
        new = []
        for i in order:
            if i < n:
                new.append(i)
            else:
                a, b = link[i - n, 0], link[i - n, 1]
                new.extend([a, b])
        order = new
    return [int(i) for i in order]


def hrp_weights(returns: np.ndarray) -> np.ndarray:
    """Hierarchical Risk Parity (López de Prado 2016)."""
    from scipy.cluster.hierarchy import linkage
    from scipy.spatial.distance import squareform

    n = returns.shape[1]
    if n < 2:
        return np.ones(n) / max(n, 1)
    corr = np.corrcoef(returns, rowvar=False)
    corr = np.nan_to_num(corr, nan=0.0)
    dist = np.sqrt(np.clip((1.0 - corr) / 2.0, 0, 1))
    np.fill_diagonal(dist, 0.0)
    link = linkage(squareform(dist, checks=False), method="single")
    order = _hrp_quasi_diag(link)
    cov = np.cov(returns, rowvar=False)

    def cluster_var(idx):
        c = cov[np.ix_(idx, idx)]
        iv = 1.0 / np.diag(c)
        iv = iv / iv.sum()
        return float(iv @ c @ iv)

    w = np.ones(n)
    clusters = [order]
    while clusters:
        clusters = [c[j:k] for c in clusters for j, k in ((0, len(c) // 2), (len(c) // 2, len(c))) if len(c) > 1]
        for i in range(0, len(clusters), 2):
            left, right = clusters[i], clusters[i + 1]
            vl, vr = cluster_var(left), cluster_var(right)
            a = 1 - vl / (vl + vr)
            for idx in left:
                w[idx] *= a
            for idx in right:
                w[idx] *= (1 - a)
    return w / w.sum()


def return_overlay_weights(returns: np.ndarray, expected_returns: Sequence[float],
                           blend: float = 0.7) -> np.ndarray:
    """Blend risk-based (inverse-vol) weights with an expected-return tilt.
    `blend` = weight on the risk-based component (0.7 = 70% risk / 30% return)."""
    rp = inverse_vol_weights(returns)
    er = np.asarray(expected_returns, dtype=float)
    er = np.clip(er, 0, None)
    tilt = er / er.sum() if er.sum() > 0 else rp
    w = blend * rp + (1 - blend) * tilt
    return w / w.sum()


def sixty_forty(labels: Sequence[str]) -> np.ndarray:
    """60/40: 60% split across equity-like assets, 40% across bond-like assets."""
    eq = [i for i, l in enumerate(labels) if any(k in l.lower() for k in ("spx", "equity", "ndx", "stock", "spy", "qqq"))]
    bd = [i for i, l in enumerate(labels) if any(k in l.lower() for k in ("bond", "tlt", "ief", "10y", "treasury", "agg"))]
    w = np.zeros(len(labels))
    if eq:
        for i in eq:
            w[i] = 0.6 / len(eq)
    if bd:
        for i in bd:
            w[i] = 0.4 / len(bd)
    if w.sum() == 0:
        w = np.ones(len(labels))
    return w / w.sum()


def backtest(weights: np.ndarray, returns: np.ndarray) -> Dict:
    """Sharpe / Sortino / max drawdown of a static-weight portfolio on `returns`."""
    port = returns @ weights
    mean, std = port.mean(), port.std(ddof=1)
    downside = port[port < 0].std(ddof=1) if (port < 0).any() else 1e-9
    sharpe = round(float(_ann(mean) / (std * np.sqrt(252))), 2) if std > 0 else 0.0
    sortino = round(float(_ann(mean) / (downside * np.sqrt(252))), 2) if downside > 0 else 0.0
    equity = np.cumprod(1 + port)
    peak = np.maximum.accumulate(equity)
    max_dd = round(float(((equity - peak) / peak).min() * 100), 1)
    return {"ann_return_pct": round(float(_ann(mean) * 100), 1),
            "ann_vol_pct": round(float(std * np.sqrt(252) * 100), 1),
            "sharpe": sharpe, "sortino": sortino, "max_drawdown_pct": max_dd}
