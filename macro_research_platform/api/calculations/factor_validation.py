"""
Factor out-of-sample validation — pure, tested (Phase 4).

AQR's "Fact, Fiction, and Factor Investing" argues a factor is only credible if it survives
OUT of the sample it was fit on. This splits a factor's history in two, fits the exposure on the
in-sample half, measures R² on both halves, and flags a factor as UNSTABLE when its explanatory
power collapses out-of-sample (large in-sample vs out-of-sample R² gap) — the classic overfitting
signature. It also reports the factor's own max drawdown so a "good" factor's tail risk is visible.

Citation: Asness, Israelov, Liew et al. — AQR "Fact, Fiction, and Factor Investing."
"""
from __future__ import annotations

from typing import Dict, List, Sequence
import numpy as np


def _r2(y: np.ndarray, x: np.ndarray, beta: float, alpha: float) -> float:
    pred = alpha + beta * x
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0


def _max_dd(series: np.ndarray) -> float:
    equity = np.cumprod(1 + series)
    peak = np.maximum.accumulate(equity)
    return round(float(((equity - peak) / peak).min() * 100), 1)


def validate_factor(name: str, factor_returns: Sequence[float],
                    asset_returns: Sequence[float], unstable_gap: float = 0.25) -> Dict:
    """Fit exposure in-sample (first half), test R² out-of-sample (second half)."""
    f = np.asarray(factor_returns, dtype=float)
    a = np.asarray(asset_returns, dtype=float)
    n = min(len(f), len(a))
    f, a = f[:n], a[:n]
    if n < 20:
        return {"factor": name, "available": False,
                "reason": f"only {n} observations; need ≥20 for a split test"}

    half = n // 2
    fi, ai = f[:half], a[:half]                        # in-sample
    fo, ao = f[half:], a[half:]                        # out-of-sample

    # fit beta/alpha on in-sample
    beta = float(np.cov(ai, fi, ddof=1)[0, 1] / np.var(fi, ddof=1)) if np.var(fi, ddof=1) > 0 else 0.0
    alpha = float(ai.mean() - beta * fi.mean())

    r2_is = round(_r2(ai, fi, beta, alpha), 3)
    r2_oos = round(_r2(ao, fo, beta, alpha), 3)        # same betas, held-out data
    gap = round(r2_is - r2_oos, 3)
    unstable = gap >= unstable_gap or r2_oos < 0

    return {
        "factor": name,
        "available": True,
        "in_sample_r2": r2_is,
        "out_of_sample_r2": r2_oos,
        "r2_gap": gap,
        "beta": round(beta, 3),
        "unstable": bool(unstable),
        "factor_max_drawdown_pct": _max_dd(f),
        "n_obs": n,
        "verdict": ("UNSTABLE — explanatory power does not survive out-of-sample"
                    if unstable else "stable out-of-sample"),
    }


def validate_factors(factors: Dict[str, Sequence[float]],
                     asset_returns: Sequence[float]) -> Dict:
    """Validate several factors; summarise how many are stable vs flagged."""
    results: List[Dict] = [validate_factor(k, v, asset_returns) for k, v in factors.items()]
    tested = [r for r in results if r.get("available")]
    unstable = [r["factor"] for r in tested if r.get("unstable")]
    return {
        "factors": results,
        "n_tested": len(tested),
        "n_unstable": len(unstable),
        "unstable_factors": unstable,
        "note": ("All tested factors survive out-of-sample." if not unstable
                 else f"Flagged as unstable (in-sample R² does not hold up): {', '.join(unstable)}."),
    }
