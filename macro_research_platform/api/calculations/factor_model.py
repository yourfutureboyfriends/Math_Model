"""
Multi-factor risk model — pure, tested regression math (Phase 2).

Estimates each position's sensitivity (beta) to a set of systematic factors by OLS
regression of the position's daily returns on the factor daily returns, then aggregates
loadings to the portfolio level weighted by position weight. No I/O — factor and
position return series are passed in; price fetching lives in the API layer.

Factors (daily returns; style/credit factors are LONG-SHORT spreads):
  equity      SPY            broad equity market beta
  size        IWM − SPY      small-cap minus market
  value       IWD − IWF      value minus growth
  momentum    MTUM − SPY     momentum minus market
  rates       TLT            long-duration Treasury (rate sensitivity, inverse of yields)
  credit      HYG − IEF      high yield minus duration-similar Treasuries
  commodity   DBC            broad commodity beta
  usd         UUP            US dollar beta
  volatility  ^VIX           equity volatility beta

Why spreads: SPY/IWM/IWD/IWF/MTUM are all long-only equity and ~0.6-0.9 correlated,
so regressing on them together split market beta arbitrarily (a utilities ETF came out
with a NEGATIVE market beta, and betas swung 1.5 -> 0.5 between half-years). Spreads
remove the shared market component so each style loading is identifiable.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple
import numpy as np

# factor -> (long ticker, short ticker or None)
FACTOR_DEFINITIONS: Dict[str, Tuple[str, Optional[str]]] = {
    "equity": ("SPY", None),
    "size": ("IWM", "SPY"),
    "value": ("IWD", "IWF"),
    "momentum": ("MTUM", "SPY"),
    "rates": ("TLT", None),
    "credit": ("HYG", "IEF"),
    "commodity": ("DBC", None),
    "usd": ("UUP", None),
    "volatility": ("^VIX", None),
}

# Display proxy per factor (e.g. "IWM-SPY").
FACTOR_PROXIES: Dict[str, str] = {
    f: (long if short is None else f"{long}-{short}") for f, (long, short) in FACTOR_DEFINITIONS.items()
}

# Every ticker that must be fetched to build the factors.
FACTOR_TICKERS: List[str] = sorted({t for pair in FACTOR_DEFINITIONS.values() for t in pair if t})

FACTOR_LABELS: Dict[str, str] = {
    "equity": "Equity Beta", "size": "Size (Small−Mkt)", "value": "Value (Val−Gro)",
    "momentum": "Momentum (Mom−Mkt)", "rates": "Rates Duration", "credit": "Credit (HY−Tsy)",
    "commodity": "Commodity", "usd": "USD", "volatility": "Volatility",
}


def build_factor_returns(ticker_returns: Dict[str, Sequence[float]]) -> Dict[str, np.ndarray]:
    """Factor return series from aligned per-ticker daily returns (long − short).
    Factors whose tickers are missing are omitted."""
    out: Dict[str, np.ndarray] = {}
    for f, (long, short) in FACTOR_DEFINITIONS.items():
        if long not in ticker_returns or (short and short not in ticker_returns):
            continue
        r = np.asarray(ticker_returns[long], dtype=float)
        if short:
            r = r - np.asarray(ticker_returns[short], dtype=float)
        out[f] = r
    return orthogonalize_factors(out)


CORE_FACTORS = ("equity", "rates")


def orthogonalize_factors(factors: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    """Residualize every non-core factor on the core ones (equity, rates).

    The credit spread (HYG−IEF) is ~0.4 correlated with equity and ~−0.6 with rates, the USD
    and commodity factors also load on both — so one regression split the market and duration
    betas arbitrarily between them (gold came out with equity 0.93 / credit −2.46 / rates
    −0.46). With the others orthogonalized, the equity and rates loadings are each position's
    TOTAL market and duration betas, and the rest measure exposure beyond them."""
    core = [k for k in CORE_FACTORS if k in factors]
    if not core:
        return factors
    n = min(len(factors[k]) for k in factors)
    out = {k: np.asarray(v, dtype=float)[-n:] for k, v in factors.items()}
    Xc = np.column_stack([out[k] - out[k].mean() for k in core])   # demeaned core factors
    betas: Dict[str, Dict[str, float]] = {}
    for k in factors:
        if k in core:
            continue
        y = out[k]
        b, *_ = np.linalg.lstsq(Xc, y - y.mean(), rcond=None)
        out[k] = y - Xc @ b                    # residual keeps the factor's own mean
        betas[k] = {c: float(b[i]) for i, c in enumerate(core)}
    ORTHO_BETAS.clear()
    ORTHO_BETAS.update(betas)
    return out


# Coefficients of the latest orthogonalization (non-core factor on the core factors), so a
# scenario expressed in raw factor moves can be mapped into the same orthogonal space.
ORTHO_BETAS: Dict[str, Dict[str, float]] = {}


def orthogonal_shocks(shocks: Dict[str, float], betas: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[str, float]:
    """Raw factor shocks -> shocks of the orthogonalized factors: each non-core shock minus
    the part implied by the equity and rates shocks."""
    betas = ORTHO_BETAS if betas is None else betas
    out = dict(shocks)
    for k, b in betas.items():
        if k in out:
            out[k] = round(out[k] - sum(coef * shocks.get(c, 0.0) for c, coef in b.items()), 4)
    return out


def factor_period_return(ticker_period_returns: Dict[str, float], factor: str) -> Optional[float]:
    """A factor's return over a window from its tickers' cumulative returns (long − short)."""
    long, short = FACTOR_DEFINITIONS[factor]
    if long not in ticker_period_returns or (short and short not in ticker_period_returns):
        return None
    return ticker_period_returns[long] - (ticker_period_returns[short] if short else 0.0)


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
    factor_returns: Dict[str, Sequence[float]],
) -> Dict[str, float]:
    """Euler decomposition of systematic variance across factors, using the full factor
    covariance: contribution_f = b_f · (Σ b)_f / (bᵀ Σ b).

    Contributions sum to 1. A negative value means the factor is hedging (offsetting
    other exposures through correlation). `factor_returns` are aligned daily series.
    """
    names = [f for f in portfolio_loadings if f in factor_returns and len(factor_returns[f]) > 1]
    if not names:
        return {f: 0.0 for f in portfolio_loadings}
    n = min(len(factor_returns[f]) for f in names)
    R = np.column_stack([np.asarray(factor_returns[f], dtype=float)[-n:] for f in names])
    cov = np.atleast_2d(np.cov(R, rowvar=False))
    b = np.array([portfolio_loadings[f] for f in names])
    total = float(b @ cov @ b)
    out = {f: 0.0 for f in portfolio_loadings}
    if total <= 0:
        return out
    mrc = cov @ b
    for i, f in enumerate(names):
        out[f] = round(float(b[i] * mrc[i] / total), 4)
    return out
