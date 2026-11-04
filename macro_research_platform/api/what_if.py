"""
What-if scenarios: drag intuitive market moves and see what they do to the fund's book and to the macro models'
portfolios, using the same factor model as VaR & Stress (api/calculations/factor_model.py).

Sliders → factor shocks (the factor model's daily-regression factors, applied to a one-off move):

    equity_pct        S&P 500 move                    equity      = equity_pct
    rates_bp          10-year Treasury yield change    rates       = TLT return ≈ −16.5 × Δy (TLT's modified duration)
    credit_bp         high-yield spread change         credit      = HYG − IEF return ≈ −3.5 × Δspread (HY spread duration)
    commodities_pct   broad commodities (DBC)          commodity   = commodities_pct
    usd_pct           US dollar (DXY / UUP)            usd         = usd_pct
    vix_pts           VIX change in points             volatility  = vix_pts / current VIX

Size, value and momentum are left unshocked. The raw shocks are mapped into the model's orthogonalised factor space
(the part of each non-core shock not already implied by the equity and rates shocks) before being applied, as the
stress tests do.

Book: P&L = Σ_f dollar exposure_f × shock_f (positions' regression betas × market value).
Model portfolios: each model's tactical and strategic weights on its instruments, with each instrument's betas
estimated the same way over ten years of daily returns, give the portfolio return under the scenario — available even when the book is empty.

Linear, first-order estimates from historical betas: they ignore convexity, option positions, correlation breaks and
liquidity, so read them as a sense of size and direction, not a forecast.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

TLT_DURATION = 16.5
HY_SPREAD_DURATION = 3.5
LIMITS = {"equity_pct": (-0.6, 0.4), "rates_bp": (-300, 300), "credit_bp": (-300, 800), "commodities_pct": (-0.6, 0.6),
          "usd_pct": (-0.25, 0.25), "vix_pts": (-20, 60)}
_LOAD_CACHE: Dict[str, Any] = {"at": 0.0, "loadings": {}, "ortho": {}}
_LOAD_TTL = 6 * 3600
# Scenario betas come from ten years of daily returns (the 2020 crash and the 2022 rate shock included): one calm
# year made gold look like an equity (beta 0.8) and turned a −40% crash into a −52% gold move.
WINDOW = "10y"


def slider_shocks(s: Dict[str, float], vix_level: Optional[float]) -> Dict[str, float]:
    """Raw factor shocks for slider values (clamped to their ranges).

    Args:
        s: Slider values: equity_pct, commodities_pct, usd_pct as fractions (−0.2 = −20%); rates_bp, credit_bp in
            basis points; vix_pts in VIX points.
        vix_level: Current VIX, to turn points into the volatility factor's return.

    Returns:
        Factor returns for the factor model (equity, rates, credit, commodity, usd, volatility).
    """
    v = {k: min(max(float(s.get(k) or 0.0), lo), hi) for k, (lo, hi) in LIMITS.items()}
    out = {"equity": v["equity_pct"], "rates": -TLT_DURATION * v["rates_bp"] / 1e4,
           "credit": -HY_SPREAD_DURATION * v["credit_bp"] / 1e4, "commodity": v["commodities_pct"], "usd": v["usd_pct"]}
    out["volatility"] = v["vix_pts"] / vix_level if vix_level else 0.0
    return {k: round(x, 6) for k, x in out.items()}


async def ticker_loadings(tickers: List[str]) -> Tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, float]]]:
    """Factor betas of each ticker (OLS of daily returns on the orthogonalised factor returns, up to ten years),
    cached for six hours, with the orthogonalisation coefficients of that fit (to map raw shocks consistently).

    Returns:
        (loadings by ticker, orthogonalisation betas).
    """
    from api.calculations import factor_model as fm
    from api.calculations.factor_model import FACTOR_TICKERS, build_factor_returns, estimate_factor_loadings, returns_from_closes
    from api.handlers.market_handler import _fetch_dated_closes_literal
    fresh = time.time() - _LOAD_CACHE["at"] < _LOAD_TTL
    have = _LOAD_CACHE["loadings"] if fresh else {}
    todo = [t for t in dict.fromkeys(tickers) if t not in have]
    if todo:
        fac = {t: await _fetch_dated_closes_literal(t, WINDOW) for t in FACTOR_TICKERS}
        common = None
        for d in fac.values():
            common = set(d) if common is None else common & set(d)
        common = sorted(common or [])
        window = common[-2521:]
        if len(window) >= 61:                      # the canonical fit whose coefficients map the scenario's shocks
            build_factor_returns({ft: returns_from_closes([fac[ft][d] for d in window]) for ft in FACTOR_TICKERS})
            _LOAD_CACHE["ortho"] = {k: dict(v) for k, v in fm.ORTHO_BETAS.items()}
        for t in todo:
            closes = await _fetch_dated_closes_literal(t, WINDOW)
            dates = [d for d in common if d in closes][-2520:]           # up to ten years of daily returns
            if len(dates) < 61:
                have[t] = {}
                continue
            r = returns_from_closes([closes[d] for d in dates])
            f = build_factor_returns({ft: returns_from_closes([fac[ft][d] for d in dates]) for ft in FACTOR_TICKERS})
            have[t] = estimate_factor_loadings(r, f) or {}
        _LOAD_CACHE.update(at=time.time() if not fresh else _LOAD_CACHE["at"], loadings=have)
    return {t: have.get(t, {}) for t in tickers}, _LOAD_CACHE["ortho"]


def _portfolio_move(weights: Dict[str, float], instruments: Dict[str, str], loads: Dict[str, Dict[str, float]],
                    shocks: Dict[str, float]) -> Dict[str, Any]:
    by_asset, missing = [], []
    total = 0.0
    for asset, w in weights.items():
        if not w:
            continue
        b = loads.get(instruments.get(asset, ""), {})
        if not b:
            missing.append(asset)
            continue
        r = sum(b.get(f, 0.0) * s for f, s in shocks.items())
        total += w * r
        by_asset.append({"asset": asset, "instrument": instruments.get(asset), "weight": round(w, 4),
                         "move": round(r, 4), "contribution": round(w * r, 4)})
    by_asset.sort(key=lambda x: x["contribution"])
    return {"return": round(total, 4), "by_asset": by_asset, "not_estimated": missing}


async def run(sliders: Dict[str, float]) -> Dict[str, Any]:
    """The scenario's effect on the fund's book and on each macro model's tactical and strategic portfolios."""
    from api.calculations import factor_model as fm
    from api.calculations.factor_model import FACTOR_LABELS, orthogonal_shocks
    from api.handlers.market_handler import _fetch_dated_closes_literal
    vix = await _fetch_dated_closes_literal("^VIX")
    vix_level = vix[max(vix)] if vix else None
    raw = slider_shocks(sliders, vix_level)

    # Book: exposures to the factors orthogonalised in that same fit, so its coefficients map the shocks
    from api.routers.book import _dollar_factor_exposures
    book: Dict[str, Any]
    try:
        dexp, reason = await _dollar_factor_exposures(None)
    except Exception as e:                                                     # noqa: BLE001 — shown as unavailable
        dexp, reason = None, str(e)[:160]
    shocks = orthogonal_shocks(raw, {k: dict(v) for k, v in fm.ORTHO_BETAS.items()})
    if dexp is None:
        book = {"available": False, "reason": reason or "No positions in this fund's book."}
    else:
        from api import fund_store
        from api.calculations.var_model import scenario_pnl
        res = scenario_pnl(dexp, shocks)
        capital = float((await asyncio.to_thread(fund_store.get_settings)).get("capital") or 0) or None
        book = {"available": True, "pnl": res["total_pnl"], "pnl_pct_capital": round(res["total_pnl"] / capital, 4) if capital else None,
                "capital": capital, "by_factor": [{"factor": f, "label": FACTOR_LABELS.get(f, f), "pnl": v}
                                                  for f, v in sorted(res["by_factor"].items(), key=lambda kv: kv[1]) if v]}

    # Macro model portfolios (served from each model's cache or snapshot)
    from api.model.engine import run_model
    from api.model.economies import ECONOMIES
    results = await asyncio.gather(*[run_model(None, persist=False, economy=e) for e in ECONOMIES], return_exceptions=True)
    instruments = {}
    for r in results:
        if isinstance(r, dict) and r.get("available"):
            for k in ("tactical", "strategic"):
                instruments.update({a: t for a, t in r["portfolios"][k]["etfs"].items()})
    loads, ortho = await ticker_loadings(sorted(set(instruments.values())))
    shocks = orthogonal_shocks(raw, ortho)
    models = []
    for eid, r in zip(ECONOMIES, results):
        if not isinstance(r, dict) or not r.get("available"):
            models.append({"economy": eid, "name": ECONOMIES[eid].name, "available": False})
            continue
        m = {"economy": eid, "name": r["economy"]["name"], "currency": r["economy"]["currency"], "available": True}
        for k in ("tactical", "strategic"):
            port = r["portfolios"][k]
            m[k] = _portfolio_move(port["weights"], port["etfs"], loads, shocks)
        models.append(m)

    return {"sliders": {k: sliders.get(k, 0) for k in LIMITS}, "vix_level": vix_level, "factor_shocks": raw,
            "model_shocks": shocks, "book": book, "models": models,
            "method": "Linear factor-model estimate (historical betas, daily regressions over up to ten years); "
                      f"rates via TLT duration {TLT_DURATION}, credit via HY spread duration {HY_SPREAD_DURATION}. "
                      "Ignores convexity, options, correlation breaks and liquidity."}
