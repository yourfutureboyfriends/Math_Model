"""
Composite (ensemble) signal history: the four score inputs — growth, 1 − recession probability, risk appetite,
liquidity — re-evaluated weekly with the data available at each date (same functions as the live dashboard), and
the composite with today's evidence weights, alongside the S&P 500's forward 1-month return where it is known.

Weights are today's (from the out-of-sample evidence); the inputs at each date use only data up to that date.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict

from api.utils.cache import ttl_cache

logger = logging.getLogger(__name__)


@ttl_cache(3600, offload=True)
async def composite_history(weeks: int = 104) -> Dict[str, Any]:
    """Weekly history of the composite signal and its four inputs (growth, inflation, liquidity, risk) over `weeks`,
    rebuilt point-in-time: each week uses only data published by then (CPI by release date). Cached for an hour.
    """
    from api.handlers.macro_inputs import load_monthly_macro, cpi_release_series
    from api.calculations.signals import (calculate_growth_signal, calculate_inflation_signal,
                                          calculate_liquidity_signal, calculate_risk_signal)
    from api.calculations.models import estrella_mishkin_recession_prob
    from api.calculations.signal_governance import evidence_weights, evidence_for

    from api.handlers.macro_inputs import DatedSeries, load_fred_series
    from api.market_bars import bars

    def yahoo(t):
        b = bars(t, "1d", "5y")
        return DatedSeries.from_mapping(t, {x["t"]: x["c"] for x in b["bars"]})
    spx_s, vix_s, dxy_s = await asyncio.gather(*[asyncio.to_thread(yahoo, t) for t in ("^GSPC", "^VIX", "DX-Y.NYB")])
    fred = await load_fred_series(["DGS10", "DGS3MO", "DFF", "T10YIE"], days=1500)
    dgs10, dgs3mo, dff, be_s = (fred[k] for k in ("DGS10", "DGS3MO", "DFF", "T10YIE"))
    cpi_s = cpi_release_series(await asyncio.to_thread(load_monthly_macro))
    probit = None
    try:
        from api.models_ml.recession_probit import get_recession_probit
        p = await asyncio.wait_for(asyncio.to_thread(get_recession_probit), timeout=60)
        probit = p if p.fitted else None
    except Exception as e:
        logger.info("[composite] probit unavailable: %s", e)

    def rec_at(spread, ff):
        if spread is None:
            return None
        if probit is not None and ff is not None:
            return probit.predict(spread, ff)["probability"]
        try:
            return estrella_mishkin_recession_prob(spread)
        except ValueError:
            return None

    cards = {}
    try:
        from api.handlers.governance import signal_backtests
        bt = await asyncio.wait_for(signal_backtests(21), timeout=30)
        cards = {c["id"]: c for c in (bt or {}).get("signals") or []}
    except Exception as e:
        logger.info("[composite] evidence unavailable: %s", e)
    names = ["Growth signal", "1 − recession probability", "Risk-appetite signal", "Liquidity signal"]
    w = {r["name"]: r["weight"] for r in evidence_weights([(n, 0.0) for n in names],
                                                          evidence_for(cards))}
    closes, dates = spx_s.values, spx_s.dates
    pts = []
    n = len(closes)
    for off in range(min(weeks, (n - 260) // 5) * 5, -1, -5):
        i = n - 1 - off
        d = dates[i]
        g = calculate_growth_signal(None, closes[:i + 1])[0]
        liq = calculate_liquidity_signal(dxy_s.asof(d), dgs10.asof(d), dff.asof(d))[0]
        rsk = calculate_risk_signal(vix_s.asof(d))[0]
        ten, three = dgs10.asof(d), dgs3mo.asof(d)
        rec = rec_at((ten - three) if None not in (ten, three) else None, dff.asof(d))
        inf = calculate_inflation_signal(cpi_s.asof(d), be_s.asof(d))[0]
        comps = {"Growth signal": g, "1 − recession probability": (1 - rec) if rec is not None else None,
                 "Risk-appetite signal": rsk, "Liquidity signal": liq}
        avail = {k: v for k, v in comps.items() if v is not None}
        from api.handlers.governance import weights_as_of
        wd = weights_as_of(d) or w            # point-in-time weights; today's only before 3 years of evidence
        wsum = sum(wd[k] for k in avail)
        score = sum(wd[k] * v for k, v in avail.items()) / wsum if wsum else None
        fwd = closes[i + 21] / closes[i] - 1 if i + 21 < n else None
        pts.append({"date": d, "composite": round(score, 3) if score is not None else None,
                    "weights": {k: wd[k] for k in wd},
                    "growth": g, "inflation": inf, "liquidity": liq, "risk": rsk,
                    "recession": round(rec, 4) if rec is not None else None,
                    "spx": round(closes[i], 2), "spx_fwd_1m": round(fwd, 4) if fwd is not None else None})
    known = [p for p in pts if p["composite"] is not None and p["spx_fwd_1m"] is not None]
    hi = [p["spx_fwd_1m"] for p in known if p["composite"] > 0.6]
    lo = [p["spx_fwd_1m"] for p in known if p["composite"] < 0.4]
    mean = lambda x: round(sum(x) / len(x), 4) if x else None
    return {"available": bool(pts), "points": pts, "weights": w,
            "forward_return_by_state": {"composite > 0.6": {"weeks": len(hi), "avg_spx_1m": mean(hi)},
                                        "composite < 0.4": {"weeks": len(lo), "avg_spx_1m": mean(lo)},
                                        "all": {"weeks": len(known), "avg_spx_1m": mean([p["spx_fwd_1m"] for p in known])}},
            "method": ("Weekly re-evaluation of the composite's inputs with data as of each date, weighted by the "
                       "evidence available before that date (walk-forward tests since 2000, refreshed monthly). "
                       "Overlapping 1-month forward returns (weekly sampling) — descriptive, not a test."),
            "computed_at": datetime.now().isoformat(timespec="seconds")}
