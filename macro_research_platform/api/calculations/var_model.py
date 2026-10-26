"""
Value-at-Risk and stress-test math — pure, tested (Phase 3).

Works in dollar-P&L space: given each position's market value and aligned daily return
series, build the portfolio P&L distribution and compute VaR three ways, plus scenario
and reverse-stress P&L from dollar factor exposures. No I/O — price/return fetching
lives in the API layer.

VaR is reported as a POSITIVE dollar loss number (the amount you could lose).
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Optional
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
# crisis window, as PROXY returns: equity=SPY, size=IWM, value=IWD, growth=IWF,
# momentum=MTUM (convert with to_factor_shocks() before applying to factor exposures).
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


# IEF (7-10y) has roughly 0.45x the duration of TLT (20y+); used to express the HYG−IEF
# credit factor from the scenarios' TLT ("rates") move.
_IEF_TO_TLT_DURATION = 0.45


def to_factor_shocks(proxy_shocks: Dict[str, float]) -> Dict[str, float]:
    """Translate scenario proxy returns (SPY, IWM, IWD, IWF, MTUM, TLT, HYG, ... as in
    STRESS_SCENARIOS) into the factor model's long-short factor returns:
    size = IWM−SPY, value = IWD−IWF, momentum = MTUM−SPY, credit = HYG−IEF."""
    s = proxy_shocks
    eq = s.get("equity", 0.0)
    out = {"equity": eq}
    if "size" in s:
        out["size"] = round(s["size"] - eq, 4)
    if "value" in s and "growth" in s:
        out["value"] = round(s["value"] - s["growth"], 4)
    if "momentum" in s:
        out["momentum"] = round(s["momentum"] - eq, 4)
    if "rates" in s:
        out["rates"] = s["rates"]
    if "credit" in s:
        out["credit"] = round(s["credit"] - _IEF_TO_TLT_DURATION * s.get("rates", 0.0), 4)
    for k in ("commodity", "usd", "volatility"):
        if k in s:
            out[k] = s[k]
    return out


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


def suggest_size_for_var(daily_vol: float, price: float, var_limit: float,
                         conf: float = 0.95, horizon: int = 1) -> Dict[str, float]:
    """Suggest a position size whose standalone VaR stays within `var_limit` ($).

    Standalone VaR of a notional N ≈ N × z(conf) × daily_vol × √horizon. Solve for the
    max notional, then shares = notional / price. A conservative (ignores diversification)
    vol-targeted / VaR-capped size. Returns {max_notional, suggested_shares, daily_vol}.
    """
    z = Z.get(round(conf, 2), 1.6448536269514722)
    denom = z * max(daily_vol, 1e-9) * (horizon ** 0.5)
    max_notional = var_limit / denom if denom > 0 else 0.0
    shares = (max_notional / price) if price and price > 0 else 0.0
    return {"max_notional": round(max_notional, 2),
            "suggested_shares": int(max(0, shares)),
            "daily_vol": round(daily_vol, 5)}


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


# ─────────────────────────────────────────────────────────────────────────────
# Tail risk beyond plain VaR, volatility-responsive VaR, and VaR backtesting.
#   Expected Shortfall: the mean loss beyond VaR — the Basel FRTB measure (97.5%), coherent where VaR is not
#     (Artzner et al. 1999; Acerbi & Tasche 2002).
#   Cornish–Fisher (modified) VaR: the normal quantile corrected for the P&L's skew and excess kurtosis
#     (Favre & Galeano 2002) — fat left tails raise it.
#   EWMA VaR: RiskMetrics (1996) exponentially weighted volatility, λ = 0.94 — reacts to volatility clustering.
#   Filtered historical simulation: past P&L standardised by its own EWMA volatility then rescaled to today's
#     (Barone-Adesi, Giannopoulos & Vosper 1999; Hull & White 1998) — empirical tails, today's volatility.
#   Backtests: Kupiec (1995) proportion-of-failures, Christoffersen (1998) independence and conditional coverage,
#     and the Basel traffic light (binomial zones).
# ─────────────────────────────────────────────────────────────────────────────
import math as _math


def _z_lower(conf: float) -> float:
    from statistics import NormalDist
    return NormalDist().inv_cdf(1.0 - conf)                     # e.g. −1.645 at 95%


def expected_shortfall_hist(pnl_series: Sequence[float], conf: float = 0.975) -> float:
    """Historical ES: the average P&L in the worst (1−conf) tail, as a positive loss."""
    p = np.sort(np.asarray(pnl_series, dtype=float))
    if p.size == 0:
        return 0.0
    k = max(1, int(_math.floor(p.size * (1.0 - conf))))
    return round(max(0.0, -float(p[:k].mean())), 2)


def expected_shortfall_normal(pnl_series: Sequence[float], conf: float = 0.975) -> float:
    """Normal ES (zero mean, like parametric_var): σ·φ(z)/(1−conf)."""
    p = np.asarray(pnl_series, dtype=float)
    if p.size < 2:
        return 0.0
    z = -_z_lower(conf)
    phi = _math.exp(-0.5 * z * z) / _math.sqrt(2 * _math.pi)
    return round(float(np.std(p, ddof=1)) * phi / (1.0 - conf), 2)


def moments(pnl_series: Sequence[float]) -> Dict[str, float]:
    p = np.asarray(pnl_series, dtype=float)
    if p.size < 4:
        return {"skew": 0.0, "excess_kurtosis": 0.0}
    m, s = p.mean(), p.std(ddof=0)
    if s <= 0:
        return {"skew": 0.0, "excess_kurtosis": 0.0}
    return {"skew": float(((p - m) ** 3).mean() / s ** 3), "excess_kurtosis": float(((p - m) ** 4).mean() / s ** 4 - 3.0)}


def cornish_fisher_var(pnl_series: Sequence[float], conf: float = 0.95) -> float:
    """Modified VaR: σ × the Cornish–Fisher-adjusted lower quantile (zero mean)."""
    p = np.asarray(pnl_series, dtype=float)
    if p.size < 4:
        return parametric_var(p, conf)
    mo = moments(p)
    S, K, z = mo["skew"], mo["excess_kurtosis"], _z_lower(conf)
    zcf = z + (z * z - 1) * S / 6 + (z ** 3 - 3 * z) * K / 24 - (2 * z ** 3 - 5 * z) * S * S / 36
    return round(max(0.0, -zcf * float(np.std(p, ddof=1))), 2)


def ewma_sigma_path(pnl_series: Sequence[float], lam: float = 0.94) -> np.ndarray:
    """σ_t of each day from information up to the day before (σ_0 = sample σ of the first 20 days)."""
    p = np.asarray(pnl_series, dtype=float)
    out = np.empty(p.size + 1)
    seed = p[: min(20, p.size)]
    out[0] = float(np.sqrt(np.mean(seed ** 2))) if seed.size else 0.0
    for t in range(p.size):
        out[t + 1] = _math.sqrt(lam * out[t] ** 2 + (1 - lam) * p[t] ** 2)
    return out                                                  # out[t] = forecast for day t; out[-1] = tomorrow


def ewma_var(pnl_series: Sequence[float], conf: float = 0.95, lam: float = 0.94) -> float:
    p = np.asarray(pnl_series, dtype=float)
    if p.size < 20:
        return parametric_var(p, conf)
    return round(max(0.0, -_z_lower(conf) * float(ewma_sigma_path(p, lam)[-1])), 2)


def filtered_hs(pnl_series: Sequence[float], conf: float = 0.95, lam: float = 0.94) -> Dict[str, float]:
    """Filtered historical simulation: VaR and ES from standardised residuals rescaled to tomorrow's EWMA σ."""
    p = np.asarray(pnl_series, dtype=float)
    if p.size < 60:
        return {"var": historical_var(p, conf), "es": expected_shortfall_hist(p, 0.975)}
    sig = ewma_sigma_path(p, lam)
    ok = sig[:-1] > 0
    resid = p[ok] / sig[:-1][ok]
    scen = resid * sig[-1]
    return {"var": historical_var(scen, conf), "es": expected_shortfall_hist(scen, 0.975)}


def _chi2_sf(x: float, df: int) -> float:
    if x <= 0:
        return 1.0
    if df == 1:
        return _math.erfc(_math.sqrt(x / 2))
    if df == 2:
        return _math.exp(-x / 2)
    raise ValueError("df 1 or 2")


def _binom_cdf(k: int, n: int, p: float) -> float:
    return sum(_math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(0, k + 1))


def var_backtest(losses: Sequence[float], var_forecasts: Sequence[float], conf: float = 0.95) -> Dict:
    """Exceptions = days the realised loss exceeded the VaR forecast made the day before (both positive losses).
    Kupiec POF (unconditional coverage), Christoffersen independence and conditional coverage, Basel traffic
    light (green while the exception count is within the binomial 95% bound, red beyond 99.99%)."""
    L = np.asarray(losses, dtype=float)
    V = np.asarray(var_forecasts, dtype=float)
    n = int(min(L.size, V.size))
    if n < 20:
        return {"available": False, "reason": f"{n} days of recorded VaR and P&L — need at least 20"}
    hits = (L[:n] > V[:n]).astype(int)
    x, p = int(hits.sum()), 1.0 - conf
    ph = x / n

    def ll(prob, k, m):
        if prob <= 0 or prob >= 1:
            return 0.0 if (k == 0 and prob <= 0) or (k == m and prob >= 1) else -1e300
        return (m - k) * _math.log(1 - prob) + k * _math.log(prob)
    lr_pof = -2 * (ll(p, x, n) - ll(ph, x, n))
    n00 = n01 = n10 = n11 = 0
    for a, b in zip(hits[:-1], hits[1:]):
        n00 += (a == 0 and b == 0); n01 += (a == 0 and b == 1); n10 += (a == 1 and b == 0); n11 += (a == 1 and b == 1)
    pi0 = n01 / (n00 + n01) if (n00 + n01) else 0.0
    pi1 = n11 / (n10 + n11) if (n10 + n11) else 0.0
    pi = (n01 + n11) / (n00 + n01 + n10 + n11) if n > 1 else 0.0
    lr_ind = -2 * ((ll(pi, n01 + n11, n00 + n01 + n10 + n11)) - (ll(pi0, n01, n00 + n01) + ll(pi1, n11, n10 + n11)))
    lr_ind = max(lr_ind, 0.0)
    green = next(k for k in range(n + 1) if _binom_cdf(k, n, p) >= 0.95) - 1   # Basel: green while P(X ≤ k) < 95%
    red = next(k for k in range(n + 1) if _binom_cdf(k, n, p) >= 0.9999)
    zone = "green" if x <= green else "yellow" if x < red else "red"
    return {"available": True, "days": n, "exceptions": x, "expected": round(n * p, 1), "exception_rate": round(ph, 4),
            "kupiec_lr": round(lr_pof, 3), "kupiec_p": round(_chi2_sf(lr_pof, 1), 4),
            "christoffersen_ind_lr": round(lr_ind, 3), "christoffersen_ind_p": round(_chi2_sf(lr_ind, 1), 4),
            "conditional_coverage_p": round(_chi2_sf(lr_pof + lr_ind, 2), 4),
            "traffic_light": zone, "green_max": green, "red_from": red,
            "verdict": ("VaR is consistent with the realised losses" if zone == "green" and _chi2_sf(lr_pof, 1) > 0.05
                        else "VaR is under-forecasting losses — review the model" if ph > p
                        else "VaR is conservative (fewer breaches than expected)")}
