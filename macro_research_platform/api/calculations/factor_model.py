"""
Multi-factor risk model — pure, tested regression math (Phase 2).

Estimates each position's sensitivity (beta) to a set of systematic factors by OLS
regression of the position's daily returns on the factor daily returns, then aggregates
loadings to the portfolio level weighted by position weight. No I/O — factor and
position return series are passed in; price fetching lives in the API layer.

Factors (proxied by liquid ETFs / indices, returns basis):
  equity      SPY      broad equity market beta
  size        IWM      small-cap tilt
  value       IWD      value tilt
  growth      IWF      growth tilt
  momentum    MTUM     cross-sectional momentum factor
  rates       TLT      long-duration Treasury (rate sensitivity, inverse of yields)
  credit      HYG      high-yield credit spread sensitivity
  commodity   DBC      broad commodity beta
  usd         UUP      US dollar beta
  volatility  ^VIX     equity volatility beta
"""
from __future__ import annotations

from typing import Dict, List, Sequence
import numpy as np

FACTOR_PROXIES: Dict[str, str] = {
    "equity": "SPY",
    "size": "IWM",
    "value": "IWD",
    "growth": "IWF",
    "momentum": "MTUM",
    "rates": "TLT",
    "credit": "HYG",
    "commodity": "DBC",
    "usd": "UUP",
    "volatility": "^VIX",
}

FACTOR_LABELS: Dict[str, str] = {
    "equity": "Equity Beta", "size": "Size", "value": "Value", "growth": "Growth",
    "momentum": "Momentum", "rates": "Rates Duration", "credit": "Credit Spread",
    "commodity": "Commodity", "usd": "USD", "volatility": "Volatility",
}


def returns_from_closes(closes: Sequence[float]) -> np.ndarray:
    """Simple daily returns from a close series. Length = len(closes) - 1."""
    c = np.asarray(closes, dtype=float)
    if c.size < 2:
        return np.array([])
    return c[1:] / c[:-1] - 1.0


def estimate_factor_loadings(
    position_returns: Sequence[float],
    factor_returns: Dict[str, Sequence[float]],
    min_obs: int = 60,
) -> Dict[str, float]:
    """OLS betas of position returns on factor returns (with an intercept).

    All series must be aligned (same dates, same length). Returns {factor: beta};
    empty dict if there is insufficient overlapping data. r_squared is not returned
    here (see regression_fit for that).
    """
    y = np.asarray(position_returns, dtype=float)
    names = list(factor_returns.keys())
    if y.size < min_obs or not names:
        return {}
    X_cols = [np.asarray(factor_returns[n], dtype=float) for n in names]
    n = min([y.size] + [c.size for c in X_cols])
    if n < min_obs:
        return {}
    y = y[-n:]
    X = np.column_stack([c[-n:] for c in X_cols] + [np.ones(n)])  # + intercept
    try:
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    except np.linalg.LinAlgError:
        return {}
    return {name: float(beta[i]) for i, name in enumerate(names)}


def regression_fit(
    position_returns: Sequence[float],
    factor_returns: Dict[str, Sequence[float]],
) -> float:
    """R-squared of the multi-factor fit; 0.0 if unavailable."""
    loadings = estimate_factor_loadings(position_returns, factor_returns, min_obs=2)
    if not loadings:
        return 0.0
    names = list(loadings.keys())
    y = np.asarray(position_returns, dtype=float)
    X_cols = [np.asarray(factor_returns[n], dtype=float) for n in names]
    n = min([y.size] + [c.size for c in X_cols])
    y = y[-n:]
    X = np.column_stack([c[-n:] for c in X_cols] + [np.ones(n)])
    beta = np.array([loadings[name] for name in names] + [float(np.mean(y - X[:, :-1] @ np.array([loadings[nm] for nm in names])))])
    resid = y - X @ beta
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return round(1.0 - ss_res / ss_tot, 4) if ss_tot > 0 else 0.0


def aggregate_portfolio_loadings(
    position_loadings: List[Dict[str, float]],
    weights: List[float],
) -> Dict[str, float]:
    """Portfolio factor loading = Σ weight_i × position_beta_i (net, signed weights).

    weights should be NET weights (market_value / gross) so a short position's loadings
    subtract. Missing per-position factors are treated as 0 beta.
    """
    factors = set()
    for pl in position_loadings:
        factors.update(pl.keys())
    out: Dict[str, float] = {}
    for f in factors:
        out[f] = round(sum(w * pl.get(f, 0.0) for pl, w in zip(position_loadings, weights)), 4)
    return out


def contribution_to_vol(
    portfolio_loadings: Dict[str, float],
    factor_vol: Dict[str, float],
) -> Dict[str, float]:
    """Rough per-factor contribution to portfolio volatility, assuming independent
    factors: contribution_f = (loading_f * factor_vol_f)^2, normalized to sum to 1.

    This is a first-order approximation (ignores factor correlations); a full
    covariance treatment is part of Phase 3 VaR.
    """
    raw = {f: (portfolio_loadings.get(f, 0.0) * factor_vol.get(f, 0.0)) ** 2 for f in portfolio_loadings}
    total = sum(raw.values())
    if total <= 0:
        return {f: 0.0 for f in raw}
    return {f: round(v / total, 4) for f, v in raw.items()}
