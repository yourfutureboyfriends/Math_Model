"""
Signal governance inputs — the out-of-sample evidence the dashboard weights its ensemble by.

Both are cached for 6 hours (they use years of daily history; the verdicts move slowly), shared by
their /api/v1 endpoints and the dashboard build.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from api.utils.cache import ttl_cache

logger = logging.getLogger(__name__)


@ttl_cache(6 * 3600, offload=True)
async def signal_backtests(horizon: int = 21):
    import asyncio as _aio
    from api.calculations.backtest import (
        momentum_signal, trend_signal, vol_regime_signal, backtest_signal,
    )

    def _closes(ticker):
        try:
            import yfinance as yf
            from api.market_dates import align_frame
            h = align_frame(ticker, yf.Ticker(ticker).history(period="5y", interval="1d"))
            if h is None or h.empty:
                return [], []
            dates = [str(d)[:10] for d in h.index]
            closes = [float(x) for x in h["Close"].tolist()]
            return dates, closes
        except Exception as e:
            logger.warning("[backtest] fetch failed for %s: %s", ticker, e)
            return [], []

    spx_dates, spx = await _aio.to_thread(_closes, "^GSPC")
    vix_dates, vix = await _aio.to_thread(_closes, "^VIX")
    if len(spx) < 300:
        return {"available": False, "reason": "Insufficient S&P 500 history for backtest.",
                "signals": []}

    scorecards = []
    for name, label, sig in [
        ("momentum_12_1", "Price Momentum (12-1m)", momentum_signal(spx)),
        ("trend_200d", "Trend (200-day MA)", trend_signal(spx)),
    ]:
        bt = backtest_signal(spx, sig, horizon)
        if bt.get("available"):
            scorecards.append({"id": name, "label": label, **bt})
    if len(vix) >= 300:
        # Align on common dates. VIX prints on some NYSE holidays (e.g. Memorial Day), so
        # trimming both series to the same length from the end shifted VIX ahead of the S&P
        # returns it was "predicting" — look-ahead that showed +613% / Sharpe 2.6.
        vmap = dict(zip(vix_dates, vix))
        common = [(v, c) for d, c in zip(spx_dates, spx) if (v := vmap.get(d)) is not None]
        vsig = vol_regime_signal([v for v, _ in common])
        bt = backtest_signal([c for _, c in common], vsig, horizon)
        if bt.get("available"):
            scorecards.append({"id": "vol_regime", "label": "VIX Vol-Regime", **bt})

    from api.calculations.signal_governance import evidence_status
    for sc in scorecards:
        sc["governance_status"], sc["governance_reason"] = evidence_status(sc)
    return {
        "available": True,
        "universe": "S&P 500 (^GSPC)",
        "period_days": len(spx),
        "horizon_days": horizon,
        "methodology": "Walk-forward: signal at date t uses only data <= t; evaluated "
                       "against the strictly-forward return over the next `horizon` days. "
                       "`hit_rate` uses overlapping windows; `hit_rate_independent` (with its "
                       "binomial p-value vs 50%) uses every horizon-th date only.",
        "signals": scorecards,
        "computed_at": datetime.now().isoformat(),
    }

@ttl_cache(6 * 3600, offload=True)
async def factor_validation():
    import numpy as _np
    from api.handlers.market_handler import _fetch_dated_closes_literal
    from api.calculations.factor_model import returns_from_closes
    from api.calculations.factor_validation import validate_factors

    # Factor proxies (long/short ETF spreads) explaining SPX excess behaviour.
    asset_t = "^GSPC"
    factor_defs = {
        "Value (VLUE)": "VLUE", "Momentum (MTUM)": "MTUM", "Quality (QUAL)": "QUAL",
        "Size (IWM−SPY)": ("IWM", "SPY"), "LowVol (USMV)": "USMV",
    }
    need = {asset_t}
    for v in factor_defs.values():
        need.update(v if isinstance(v, tuple) else (v,))
    dated = await asyncio.gather(*[_fetch_dated_closes_literal(t) for t in need])
    dmap = {t: d for t, d in zip(need, dated) if d}
    if asset_t not in dmap:
        return {"available": False, "reason": "Benchmark history unavailable."}

    def _series(t):
        d = dmap.get(t)
        return d if d else None

    # common dates across everything we actually got
    have = [t for t in need if t in dmap]
    common = None
    for t in have:
        common = set(dmap[t]) if common is None else (common & set(dmap[t]))
    common = sorted(common or [])
    if len(common) < 60:
        return {"available": False, "reason": "Insufficient overlapping history for OOS split."}

    asset_ret = returns_from_closes([dmap[asset_t][dt] for dt in common])
    factors = {}
    for name, spec in factor_defs.items():
        if isinstance(spec, tuple):
            a, b = spec
            if a in dmap and b in dmap:
                ra = _np.asarray(returns_from_closes([dmap[a][dt] for dt in common]))
                rb = _np.asarray(returns_from_closes([dmap[b][dt] for dt in common]))
                factors[name] = (ra - rb).tolist()
        elif spec in dmap:
            factors[name] = returns_from_closes([dmap[spec][dt] for dt in common])

    if not factors:
        return {"available": False, "reason": "No factor proxy history available."}

    out = validate_factors(factors, asset_ret)
    out["available"] = True
    out["benchmark"] = "S&P 500 (^GSPC) daily returns"
    out["observations"] = len(common)
    out["method"] = "Fit exposure on first-half (in-sample); measure R² on held-out second-half (out-of-sample)."
    out["citation"] = "Harvey, Liu & Zhu (2016), '...and the Cross-Section of Expected Returns', Review of Financial Studies"
    out["as_of"] = datetime.now().isoformat()
    return out
