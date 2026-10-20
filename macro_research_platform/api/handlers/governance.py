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
# Evidence window: since 2000 — three recessions (2001, 2008, 2020) and the 2022–24 inversion without one. Five years
# held ~60 independent months, too few to retire or keep an input on.
HISTORY_START = "2000-01-01"
_SERIES: dict = {}            # the last run's daily input votes (for point-in-time weights)
_WEIGHTS_CACHE: dict = {}


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
            h = align_frame(ticker, yf.Ticker(ticker).history(start=HISTORY_START, interval="1d"))
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
    votes_series = {}
    for name, label, sig in [
        ("momentum_12_1", "Price Momentum (12-1m)", momentum_signal(spx)),
        ("trend_200d", "Trend (200-day MA)", trend_signal(spx)),
    ]:
        bt = backtest_signal(spx, sig, horizon)
        votes_series[name] = sig
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

    # The composite's four inputs exactly as they vote (score > 0.5 = bullish), rebuilt day by day from data
    # known at each date. Recession uses Estrella–Mishkin's published coefficients: the platform's probit is refitted
    # on the whole history, so testing it here would leak the future into the past.
    try:
        cards, sigs = await _input_scorecards(spx_dates, spx, dict(zip(vix_dates, vix)), horizon)
        scorecards += cards
        votes_series.update(sigs)
    except Exception as e:
        logger.warning("[backtest] composite input tests failed: %s", e)
    import numpy as _np
    from api.calculations.backtest import sharpe as _sharpe
    bh = _sharpe(_np.diff(_np.asarray(spx)) / _np.asarray(spx)[:-1])
    from api.calculations.signal_governance import evidence_status
    for sc in scorecards:
        sc["buy_hold_sharpe"] = bh
        sc["governance_status"], sc["governance_reason"] = evidence_status(sc)
    _SERIES.update(dates=spx_dates, spx=spx, votes={k: v for k, v in votes_series.items() if k.startswith("input_")},
                   horizon=horizon)
    # How independent the composite's votes really are: day-by-day correlation of their positions since 2000
    clusters = None
    try:
        from api.calculations.backtest import _POS
        from api.calculations.signal_governance import cluster_votes
        keep = ("input_growth", "input_risk", "input_liquidity", "input_recession", "momentum_12_1", "trend_200d")
        clusters = cluster_votes({k: [_POS.get(x, 0) for x in votes_series[k]] for k in keep if k in votes_series})
    except Exception as e:
        logger.info("[backtest] vote clustering failed: %s", e)
    return {
        "available": True,
        "vote_clusters": clusters,
        "universe": "S&P 500 (^GSPC)",
        "history_start": spx_dates[0] if spx_dates else None,
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


async def _input_scorecards(spx_dates, spx, vix_by_date, horizon):
    import asyncio as _aio
    from api.calculations.backtest import backtest_signal, BULLISH, BEARISH, NEUTRAL
    from api.calculations.signals import (calculate_growth_signal, calculate_liquidity_signal,
                                          calculate_risk_signal)
    from api.calculations.models import estrella_mishkin_recession_prob
    from api.handlers.macro_inputs import DatedSeries

    def dxy_hist():
        from api.market_bars import bars
        b = bars("DX-Y.NYB", "1d", "max")
        return DatedSeries.from_mapping("dxy", {x["t"]: x["c"] for x in b["bars"]})
    dxy = await _aio.to_thread(dxy_hist)
    from datetime import date as _d
    from api.handlers.macro_inputs import _fetch_fred_history_sync
    days = (_d.today() - _d.fromisoformat(HISTORY_START)).days + 400
    dgs10, dgs3mo, dff = await _aio.gather(*[_aio.to_thread(_fetch_fred_history_sync, sid, days)
                                             for sid in ("DGS10", "DGS3MO", "DFF")])
    if min(len(dgs10.values), len(dgs3mo.values), len(dff.values)) < 1000:
        raise RuntimeError("FRED history too short for the input tests")

    def vote(x):
        return NEUTRAL if x is None else BULLISH if x > 0.5 else BEARISH

    sig = {"input_growth": [], "input_risk": [], "input_liquidity": [], "input_recession": []}
    for i, d in enumerate(spx_dates):
        sig["input_growth"].append(vote(calculate_growth_signal(None, spx[:i + 1])[0]))
        v = vix_by_date.get(d)
        sig["input_risk"].append(vote(calculate_risk_signal(v)[0] if v else None))
        sig["input_liquidity"].append(vote(calculate_liquidity_signal(dxy.asof(d), dgs10.asof(d), dff.asof(d))[0]))
        t, m = dgs10.asof(d), dgs3mo.asof(d)
        rec = estrella_mishkin_recession_prob(t - m) if None not in (t, m) else None
        sig["input_recession"].append(vote(1 - rec if rec is not None else None))
    labels = {"input_growth": "Composite input: growth signal", "input_risk": "Composite input: risk appetite (VIX level)",
              "input_liquidity": "Composite input: liquidity (DXY, Fed − 10Y)",
              "input_recession": "Composite input: 1 − recession probability (Estrella–Mishkin)"}
    out = []
    for k, sg in sig.items():
        bt = backtest_signal(spx, sg, horizon)
        if bt.get("available"):
            share = sum(1 for x in sg if x == BULLISH) / max(1, sum(1 for x in sg if x != NEUTRAL))
            out.append({"id": k, "label": labels[k], "bullish_share": round(share, 3), **bt})
    return out, sig


def weights_as_of(day: str, min_years: float = 3.0):
    """Composite weights using only evidence available before `day`: each input's walk-forward test on
    HISTORY_START → day − horizon (so every forward return was already known), recomputed monthly.
    None when the input series are not loaded yet or there are under `min_years` of history."""
    import numpy as np
    from bisect import bisect_left
    from api.calculations.backtest import backtest_signal, sharpe
    from api.calculations.signal_governance import evidence_weights, INPUT_EVIDENCE
    if not _SERIES.get("dates"):
        return None
    month = day[:7]
    if month in _WEIGHTS_CACHE:
        return _WEIGHTS_CACHE[month]
    dates, spx, h = _SERIES["dates"], _SERIES["spx"], _SERIES["horizon"]
    end = bisect_left(dates, month + "-01") - h          # forward windows that closed before the month began
    if end < int(252 * min_years):
        _WEIGHTS_CACHE[month] = None
        return None
    c = np.asarray(spx[:end], float)
    bh = sharpe(np.diff(c) / c[:-1])
    cards = {}
    for name, cid in INPUT_EVIDENCE.items():
        v = _SERIES["votes"].get(cid)
        if v:
            bt = backtest_signal(spx[:end], v[:end], h)
            cards[name] = {**bt, "buy_hold_sharpe": bh} if bt.get("available") else None
    rows = evidence_weights([(n, 0.0) for n in INPUT_EVIDENCE], cards)
    w = {r["name"]: r["weight"] for r in rows}
    _WEIGHTS_CACHE[month] = w
    return w
