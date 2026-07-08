"""
Value-at-Risk and stress-test math — pure, tested (Phase 3).

Works in dollar-P&L space: given each position's market value and aligned daily return
series, build the portfolio P&L distribution and compute VaR three ways, plus scenario
and reverse-stress P&L from dollar factor exposures. No I/O — price/return fetching
lives in the API layer.

VaR is reported as a POSITIVE dollar loss number (the amount you could lose).
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Optional, Tuple
import numpy as np

# One-sided normal quantiles for parametric VaR.
Z = {0.95: 1.6448536269514722, 0.99: 2.3263478740408408}


def portfolio_pnl_series(market_values: Sequence[float], return_matrix: np.ndarray) -> np.ndarray:
    """Daily portfolio P&L ($) = Σ_i market_value_i * return_i,t.

    market_values: length n (signed; shorts negative).
    return_matrix: shape (T, n) of daily returns aligned across positions.
    Returns length-T array of dollar P&L.
    """
    mv = np.asarray(market_values, dtype=float)
    R = np.asarray(return_matrix, dtype=float)
    if R.ndim != 2 or R.shape[1] != mv.size or R.shape[0] == 0:
        return np.array([])
    return R @ mv


def historical_var(pnl_series: Sequence[float], conf: float = 0.95) -> float:
    """Historical (empirical) VaR: the loss at the (1-conf) percentile of P&L.

    Returns a positive dollar loss. E.g. conf=0.95 -> 5th percentile of P&L, negated.
    """
    p = np.asarray(pnl_series, dtype=float)
    if p.size == 0:
        return 0.0
    q = np.percentile(p, (1.0 - conf) * 100.0)
    return round(max(0.0, -float(q)), 2)


def parametric_var(pnl_series: Sequence[float], conf: float = 0.95) -> float:
    """Variance-covariance VaR: z(conf) * σ(P&L), assuming normality.

    The std of the aggregated portfolio P&L already embeds position covariances.
    """
    p = np.asarray(pnl_series, dtype=float)
    if p.size < 2:
        return 0.0
    sigma = float(np.std(p, ddof=1))
    z = Z.get(round(conf, 2), 1.6448536269514722)
    return round(max(0.0, z * sigma), 2)


def monte_carlo_var(
    market_values: Sequence[float],
    return_matrix: np.ndarray,
    conf: float = 0.95,
    n_sims: int = 20000,
    seed: int = 42,
) -> float:
    """Monte Carlo VaR: simulate correlated position returns from the estimated
    covariance (multivariate normal) and take the (1-conf) percentile of simulated P&L.
    """
    mv = np.asarray(market_values, dtype=float)
    R = np.asarray(return_matrix, dtype=float)
    if R.ndim != 2 or R.shape[0] < 2 or R.shape[1] != mv.size:
        return 0.0
    mu = R.mean(axis=0)
    cov = np.cov(R, rowvar=False)
    cov = np.atleast_2d(cov)
    rng = np.random.default_rng(seed)
    sims = rng.multivariate_normal(mu, cov, size=n_sims)  # (n_sims, n)
    pnl = sims @ mv
    q = np.percentile(pnl, (1.0 - conf) * 100.0)
    return round(max(0.0, -float(q)), 2)


def scale_horizon(var_1d: float, days: int) -> float:
    """Scale a 1-day VaR to an h-day horizon by the square-root-of-time rule."""
    return round(var_1d * (days ** 0.5), 2)


def component_var_by_position(
    symbols: Sequence[str],
    market_values: Sequence[float],
    return_matrix: np.ndarray,
    total_var: float,
) -> List[Dict[str, float]]:
    """Euler/marginal allocation of total VaR to each position.

    component_i = total_var * (mv_i * cov(r_i, r_p)) / var(r_p_pnl). Components sum to
    total_var (up to numerical error). Positive = adds risk, negative = hedges.
    """
    mv = np.asarray(market_values, dtype=float)
    R = np.asarray(return_matrix, dtype=float)
    if R.ndim != 2 or R.shape[0] < 2 or R.shape[1] != mv.size:
        return []
    pnl = R @ mv
    var_pnl = float(np.var(pnl, ddof=1))
    if var_pnl <= 0:
        return []
    out = []
    for i, sym in enumerate(symbols):
        cov_i = float(np.cov(R[:, i], pnl, ddof=1)[0, 1])  # cov(r_i, pnl$)
        # marginal contribution of position i to portfolio P&L variance is mv_i*cov(r_i,pnl)
        contrib_frac = (mv[i] * cov_i) / var_pnl if var_pnl else 0.0
        out.append({"symbol": sym, "component_var": round(total_var * contrib_frac, 2),
                    "pct_of_var": round(contrib_frac, 4)})
    return out


def scenario_pnl(dollar_exposures: Dict[str, float], shocks: Dict[str, float]) -> Dict[str, float]:
    """Estimated portfolio P&L under a factor shock.

    dollar_exposures[f] = Σ_i mv_i * beta_i,f  ($ P&L per 1.0 factor return).
    shocks[f] = factor return in the scenario (e.g. -0.35 for equities -35%).
    P&L = Σ_f dollar_exposures[f] * shocks[f].
    """
    by_factor = {f: round(dollar_exposures.get(f, 0.0) * s, 2) for f, s in shocks.items()}
    total = round(sum(by_factor.values()), 2)
    return {"total_pnl": total, "by_factor": by_factor}


# ─────────────────────────────────────────────────────────────────────────────
# Predefined historical stress scenarios — representative factor RETURNS during the
# crisis window (equity/size/value/growth/momentum/rates/credit/commodity/usd/vol).
# Rates = TLT return (long Treasury: positive when yields fall), Credit = HYG return.
# These are approximate, representative moves for what-if analysis, not exact replays.
# ─────────────────────────────────────────────────────────────────────────────
STRESS_SCENARIOS: Dict[str, Dict[str, Dict[str, float]]] = {
    "gfc_2008": {
        "label": "2008 Global Financial Crisis (Sep-Nov)",
        "shocks": {"equity": -0.42, "size": -0.45, "value": -0.44, "growth": -0.40,
                   "momentum": -0.30, "rates": 0.14, "credit": -0.30, "commodity": -0.50,
                   "usd": 0.12, "volatility": 2.5},
    },
    "covid_2020": {
        "label": "2020 COVID Crash (Feb-Mar)",
        "shocks": {"equity": -0.34, "size": -0.41, "value": -0.38, "growth": -0.30,
                   "momentum": -0.20, "rates": 0.14, "credit": -0.20, "commodity": -0.55,
                   "usd": 0.03, "volatility": 3.0},
    },
    "taper_2013": {
        "label": "2013 Taper Tantrum",
        "shocks": {"equity": -0.05, "size": -0.06, "value": -0.04, "growth": -0.05,
                   "momentum": -0.03, "rates": -0.12, "credit": -0.05, "commodity": -0.08,
                   "usd": 0.04, "volatility": 0.5},
    },
    "rate_shock_2022": {
        "label": "2022 Rate Shock",
        "shocks": {"equity": -0.20, "size": -0.25, "value": -0.08, "growth": -0.30,
                   "momentum": -0.10, "rates": -0.30, "credit": -0.12, "commodity": 0.20,
                   "usd": 0.15, "volatility": 0.8},
    },
    "bond_1994": {
        "label": "1994 Bond Massacre",
        "shocks": {"equity": -0.03, "size": -0.04, "value": -0.02, "growth": -0.03,
                   "momentum": -0.02, "rates": -0.14, "credit": -0.04, "commodity": 0.05,
                   "usd": 0.06, "volatility": 0.4},
    },
}


def concentration(positions: List[Dict], limit_pct: float = 0.20) -> Dict:
    """Single-name and top-5 concentration on a gross-weight basis, with limit breaches.

    positions: enriched rows with symbol, market_value, book. limit_pct: single-name
    soft limit (default 20%). Returns largest, top5, HHI, and any breaches.
    """
    valued = [p for p in positions if isinstance(p.get("market_value"), (int, float))]
    total_gross = sum(abs(p["market_value"]) for p in valued)
    if total_gross <= 0:
        return {"available": False, "reason": "No priced positions."}
    rows = sorted(
        ({"symbol": p["symbol"], "book": p.get("book"),
          "gross_weight": abs(p["market_value"]) / total_gross} for p in valued),
        key=lambda r: r["gross_weight"], reverse=True,
    )
    for r in rows:
        r["gross_weight"] = round(r["gross_weight"], 4)
    top5 = round(sum(r["gross_weight"] for r in rows[:5]), 4)
    hhi = round(sum(r["gross_weight"] ** 2 for r in rows), 4)  # Herfindahl index
    breaches = [{"symbol": r["symbol"], "gross_weight": r["gross_weight"], "limit": limit_pct}
                for r in rows if r["gross_weight"] > limit_pct]

    def _group(key: str):
        agg: Dict[str, float] = {}
        for p in valued:
            agg[p.get(key) or "Unassigned"] = agg.get(p.get(key) or "Unassigned", 0.0) + abs(p["market_value"])
        return sorted(({"name": k, "gross_weight": round(v / total_gross, 4)} for k, v in agg.items()),
                      key=lambda r: r["gross_weight"], reverse=True)

    return {
        "available": True,
        "largest_name": rows[0]["symbol"], "largest_weight": rows[0]["gross_weight"],
        "top5_concentration": top5, "hhi": hhi, "single_name_limit": limit_pct,
        "breaches": breaches, "positions": rows,
        "by_asset_class": _group("asset_class"),
        "by_book": _group("book"),
    }


def days_to_liquidate(quantity: float, avg_daily_volume: Optional[float],
                      participation: float = 0.20) -> Optional[float]:
    """Days to exit a position = |shares| / (participation * ADV). None if ADV unknown.

    participation = max % of daily volume you'll trade (default 20%).
    """
    if not avg_daily_volume or avg_daily_volume <= 0:
        return None
    return round(abs(quantity) / (participation * avg_daily_volume), 2)


def reverse_stress(dollar_exposures: Dict[str, float], target_loss: float) -> List[Dict[str, float]]:
    """For a target LOSS (positive $), the single-factor shock that alone causes it.

    shock_f = -target_loss / dollar_exposure_f. Smaller |shock| = more dangerous factor.
    Skips factors with ~zero exposure. Returned sorted by smallest |shock| first.
    """
    rows = []
    for f, dexp in dollar_exposures.items():
        if abs(dexp) < 1e-6:
            continue
        shock = -target_loss / dexp
        rows.append({"factor": f, "required_shock": round(shock, 4), "dollar_exposure": round(dexp, 2)})
    rows.sort(key=lambda r: abs(r["required_shock"]))
    return rows
