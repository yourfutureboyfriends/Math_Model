"""
Market statistics for the dashboard's derived panels — pure, tested.

Every function takes observed series (closes, dated values) and returns a statistic of
them, or None when there isn't enough data. Nothing here substitutes a default value;
callers turn None into an explicit "unavailable" marker. No I/O.
"""
from __future__ import annotations

from bisect import bisect_right
from datetime import date, timedelta
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

TRADING_DAYS_1M = 21
TRADING_DAYS_3M = 63
TRADING_DAYS_12M = 252


def align_dated(series: Mapping[str, Mapping[str, float]]) -> Tuple[List[str], Dict[str, List[float]]]:
    """Restrict several {date: close} maps to their common dates (sorted).

    Different markets have different holidays, so returns must be computed on the
    intersection or they compare different days.
    """
    common = None
    for d in series.values():
        common = set(d) if common is None else common & set(d)
    dates = sorted(common or [])
    return dates, {k: [float(v[d]) for d in dates] for k, v in series.items()}


def closes_of(dated: Mapping[str, float]) -> List[float]:
    return [float(dated[d]) for d in sorted(dated)]


def period_return(closes: Sequence[float], lookback: int, skip: int = 0) -> Optional[float]:
    """Fractional return from `lookback` to `skip` trading days ago."""
    if lookback <= skip or len(closes) <= lookback:
        return None
    start, end = closes[-1 - lookback], closes[-1 - skip]
    if not start:
        return None
    return float(end / start - 1.0)


def momentum_12_1(closes: Sequence[float]) -> Optional[Dict[str, float]]:
    """12-month return, 1-month return and 12-1 momentum (12m excluding the last month)."""
    r12 = period_return(closes, TRADING_DAYS_12M)
    r1 = period_return(closes, TRADING_DAYS_1M)
    m = period_return(closes, TRADING_DAYS_12M, skip=TRADING_DAYS_1M)
    if None in (r12, r1, m):
        return None
    return {"return12m": r12, "return1m": r1, "momentum12_1": m}


def daily_returns(closes: Sequence[float]) -> np.ndarray:
    c = np.asarray(closes, dtype=float)
    if c.size < 2:
        return np.array([])
    return c[1:] / c[:-1] - 1.0


def trailing_correlation(a_closes: Sequence[float], b_closes: Sequence[float],
                         window: int = 60) -> Optional[float]:
    """Pearson correlation of the last `window` daily returns of two ALIGNED close series."""
    a, b = daily_returns(a_closes), daily_returns(b_closes)
    n = min(a.size, b.size)
    if n < window:
        return None
    a, b = a[-window:], b[-window:]
    if a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def mean_pairwise_correlation(closes_by_key: Mapping[str, Sequence[float]],
                              window: int = 60) -> Optional[float]:
    """Average pairwise return correlation across aligned series (a synchronisation gauge)."""
    keys = list(closes_by_key)
    vals = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            c = trailing_correlation(closes_by_key[keys[i]], closes_by_key[keys[j]], window)
            if c is not None:
                vals.append(c)
    return float(np.mean(vals)) if vals else None


def ols_decomposition(y: Sequence[float], factors: Mapping[str, Sequence[float]],
                      min_obs: int = 60) -> Optional[Dict]:
    """OLS of y on factors (with intercept): betas, t-stats, R² and each factor's share of
    the variance of y (Euler split of R²: beta_i·cov(x_i, y)/var(y), summing to R²)."""
    names = list(factors)
    yv = np.asarray(y, dtype=float)
    cols = [np.asarray(factors[k], dtype=float) for k in names]
    n = min([yv.size] + [c.size for c in cols]) if names else 0
    k = len(names)
    if n < max(min_obs, k + 2):
        return None
    yv = yv[-n:]
    X = np.column_stack([c[-n:] for c in cols] + [np.ones(n)])
    try:
        beta, *_ = np.linalg.lstsq(X, yv, rcond=None)
        resid = yv - X @ beta
        sigma2 = float(resid @ resid) / (n - (k + 1))
        cov = sigma2 * np.linalg.inv(X.T @ X)
    except np.linalg.LinAlgError:
        return None
    se = np.sqrt(np.clip(np.diag(cov), 0, None))
    var_y = float(yv.var(ddof=1))
    if var_y == 0:
        return None
    out = []
    for i, name in enumerate(names):
        share = float(beta[i] * np.cov(X[:, i], yv, ddof=1)[0, 1] / var_y)
        out.append({"factor": name, "beta": float(beta[i]),
                    "tStat": float(beta[i] / se[i]) if se[i] > 0 else None,
                    "varianceShare": share})
    return {"factors": out, "rSquared": 1.0 - float(resid.var(ddof=1)) / var_y, "observations": n}


def relative_strength_score(asset: Sequence[float], bench: Sequence[float],
                            lookback: int = TRADING_DAYS_3M,
                            history: int = TRADING_DAYS_12M) -> Optional[Dict[str, float]]:
    """Current `lookback`-day return of asset minus bench (aligned closes), and its
    percentile (0-1) within the trailing `history` days of that rolling relative return."""
    a, b = np.asarray(asset, dtype=float), np.asarray(bench, dtype=float)
    n = min(a.size, b.size)
    a, b = a[-n:], b[-n:]
    if n <= lookback + 20:
        return None
    rel = (a[lookback:] / a[:-lookback]) - (b[lookback:] / b[:-lookback])
    window = rel[-history:]
    current = float(window[-1])
    return {"relativeReturn": current, "percentile": float((window[:-1] < current).mean())}


def trend_signal(closes: Sequence[float], lookback: int) -> Optional[Dict[str, float]]:
    """Time-series momentum over `lookback` days: direction, return, and a t-stat-like
    strength (return / (daily vol · √lookback))."""
    ret = period_return(closes, lookback)
    if ret is None:
        return None
    r = daily_returns(closes)[-lookback:]
    vol = float(r.std(ddof=1)) if r.size > 1 else 0.0
    return {"direction": "LONG" if ret > 0 else "SHORT" if ret < 0 else "FLAT",
            "return": ret, "tStat": ret / (vol * np.sqrt(lookback)) if vol > 0 else None}


def inverse_vol_weights(closes_by_key: Mapping[str, Sequence[float]],
                        window: int = 60) -> Optional[Dict[str, float]]:
    """Naive risk-parity weights (∝ 1/σ of the last `window` daily returns)."""
    vols = {}
    for k, c in closes_by_key.items():
        r = daily_returns(c)
        if r.size < window:
            return None
        s = float(r[-window:].std(ddof=1))
        if s <= 0:
            return None
        vols[k] = s
    tot = sum(1.0 / v for v in vols.values())
    return {k: (1.0 / v) / tot for k, v in vols.items()}


def annualized_vol(closes: Sequence[float], window: int = 60) -> Optional[float]:
    r = daily_returns(closes)
    if r.size < window:
        return None
    return float(r[-window:].std(ddof=1) * np.sqrt(252))


def value_asof(dates: Sequence[str], values: Sequence[float], d: str,
               max_age_days: Optional[int] = None) -> Optional[float]:
    """Last value on or before ISO date `d` (optionally no older than max_age_days)."""
    i = bisect_right(list(dates), d) - 1
    if i < 0:
        return None
    if max_age_days is not None:
        age = (date.fromisoformat(d[:10]) - date.fromisoformat(dates[i][:10])).days
        if age > max_age_days:
            return None
    return float(values[i])


def credit_impulse(dates: Sequence[str], credit: Sequence[float],
                   nominal_gdp: Optional[float]) -> Optional[float]:
    """Credit impulse in % of GDP: (credit flow over the last 12m − flow over the prior
    12m) / nominal GDP. Credit and GDP must be in the same units (e.g. $bn, GDP SAAR)."""
    if not dates or not nominal_gdp:
        return None
    d0 = date.fromisoformat(dates[-1][:10])
    c_now = float(credit[-1])
    c_1y = value_asof(dates, credit, (d0 - timedelta(days=365)).isoformat(), max_age_days=14)
    c_2y = value_asof(dates, credit, (d0 - timedelta(days=730)).isoformat(), max_age_days=14)
    if c_1y is None or c_2y is None:
        return None
    return float(((c_now - c_1y) - (c_1y - c_2y)) / nominal_gdp * 100.0)


def zscore_and_percentile(current: float, history: Sequence[float]
                          ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """(mean, z-score, percentile 0-100) of `current` vs `history`; Nones if < 20 obs."""
    h = np.asarray([v for v in history if v is not None], dtype=float)
    if h.size < 20:
        return None, None, None
    sd = float(h.std(ddof=1))
    mean = float(h.mean())
    return mean, ((current - mean) / sd if sd > 0 else None), float((h < current).mean() * 100.0)


def change_zscore(values: Sequence[float], lookback: int, history: int = TRADING_DAYS_12M,
                  pct: bool = True) -> Optional[Dict[str, float]]:
    """Latest `lookback`-period change (pct or absolute) and its z-score vs the trailing
    `history` observations of the same rolling change."""
    v = np.asarray(values, dtype=float)
    if v.size <= lookback + 20:
        return None
    ch = (v[lookback:] / v[:-lookback] - 1.0) if pct else (v[lookback:] - v[:-lookback])
    window = ch[-history:]
    ref = window[:-1]
    sd = float(ref.std(ddof=1))
    if sd == 0:
        return None
    current = float(window[-1])
    return {"change": current, "z": (current - float(ref.mean())) / sd,
            "percentile": float((ref < current).mean())}


def conditional_return_stats(monthly_closes: Mapping[str, float],
                             labels: Mapping[str, str], label: str,
                             label_lag: int = 2) -> Optional[Dict[str, float]]:
    """Annualized mean / vol / return-to-vol and 95% CI of an asset's monthly returns in
    months whose regime label (read `label_lag` months earlier, so it was published
    before the month began) equals `label`. Keys are 'YYYY-MM' month strings."""
    months = sorted(monthly_closes)
    rets = []
    for i in range(1, len(months)):
        if i - label_lag < 0:
            continue
        lab = labels.get(months[i - label_lag])
        prev, cur = monthly_closes[months[i - 1]], monthly_closes[months[i]]
        if lab == label and prev:
            rets.append(cur / prev - 1.0)
    if len(rets) < 12:
        return None
    r = np.asarray(rets)
    mean_a, vol_a = float(r.mean() * 12), float(r.std(ddof=1) * np.sqrt(12))
    half = 1.96 * float(r.std(ddof=1)) / np.sqrt(r.size) * 12
    return {"annualReturn": mean_a, "annualVol": vol_a,
            "returnToVol": mean_a / vol_a if vol_a > 0 else None,
            "ci95": (mean_a - half, mean_a + half), "months": int(r.size)}
