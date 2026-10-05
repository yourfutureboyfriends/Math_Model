"""Dashboard data handler using shared calculations module."""
from api.schemas.models import (
    DashboardData, RegimeData, KeyMetrics, RecessionData, SignalsData,
    SignalDetails, Scores, DataMetadata, RegimePlaybookData,
    BusinessLayerData, FactorRotationData, InternationalMacroData,
    RegionMacro, DebtCycleData, MetricWithSparkline,
    MomentumVetoData, CorrelationRegimeData, CorrelationPair,
    SignalStackData, SignalStackLayer
)
from datetime import datetime, timedelta
import logging

# Import shared calculations
from api.calculations import (
    classify_regime,
    get_regime_characteristics,
    calculate_growth_signal,
    calculate_inflation_signal,
    calculate_liquidity_signal,
    calculate_risk_signal,
    calculate_recession_probability,
    calculate_sector_allocation
)
from api.calculations.models import estrella_mishkin_recession_prob
from api.handlers.dashboard_sections import (
    load_section_inputs, build_momentum_veto, build_correlation_regime, build_debt_cycle,
    build_international_macro, build_factor_rotation, build_nowcast,
    build_factor_decomposition, build_trend_signals, build_sentiment, build_valuation,
    build_advanced_indicators, build_reflexivity, build_pure_alpha, build_regime_transitions,
    build_expected_returns, build_risk_parity, build_performance_tracking,
    build_sector_stats, build_cma,
)

# Import providers and validation
from api.providers import YahooFinanceProvider
from api.services.validation_orchestrator import validate_dashboard_payload
from api.services.event_logger import log_dashboard_event, log_validation_event

logger = logging.getLogger(__name__)
_yahoo_provider = YahooFinanceProvider()


import time as _dash_time
import asyncio as _dash_asyncio


class DashboardDataUnavailable(RuntimeError):
    """Core live inputs are missing, so the dashboard can't be computed from real data."""

# The dashboard aggregates many live FRED/yfinance fetches and takes 15-20s cold,
# which blows past the frontend's 8s timeout on every uncached load. Serve a cached
# response (refreshed in the background by the startup warm task) so the UI loads
# instantly, and use a single-flight lock so concurrent cold requests compute once.
_DASHBOARD_CACHE: dict[str, tuple[float, "DashboardData"]] = {}
_DASHBOARD_TTL = 60  # seconds
_DASHBOARD_LOCKS: dict[str, "_dash_asyncio.Lock"] = {}

# Real headline sentiment (RSS fetch is slow + news moves slowly → cache 10 min).
_NEWS_CACHE: dict = {"articles": None, "ts": 0.0}


def _r2(v):
    return round(v, 2) if v is not None else None


def _label100(s: float) -> str:
    if s > 20:
        return "Bullish"
    if s > 5:
        return "Slightly Bullish"
    if s > -5:
        return "Neutral"
    if s > -20:
        return "Slightly Bearish"
    return "Bearish"


def _build_news_sentiment(regime_name: str, now) -> dict:
    """Real headline-level sentiment from live RSS markets news (see NewsProvider), scored with a
    finance lexicon. Builds the shape the News Sentiment panel reads: overall, per-theme
    (inflation/growth/fed), and top bullish/bearish headlines. Falls back to an honest empty
    shape (never fabricated) if the feeds are unreachable."""
    import time as _t
    from api.calculations.news_sentiment import aggregate_sentiment

    if _NEWS_CACHE["articles"] is None or _t.time() - _NEWS_CACHE["ts"] > 600:
        try:
            from api.providers.news_provider import NewsProvider
            res = NewsProvider().fetch_all()
            arts = ([{"title": a.title, "source": a.source, "url": a.url}
                     for a in (res.articles or []) if a.title] if res.success else [])
        except Exception as e:
            logger.warning("[news] feed fetch failed: %s", e)
            arts = []
        _NEWS_CACHE["articles"] = arts
        _NEWS_CACHE["ts"] = _t.time()

    agg = aggregate_sentiment(_NEWS_CACHE["articles"])   # sentiment in [-1, +1]
    scored = agg["articles"]
    overall_score = round(agg["score"] * 100, 1)         # UI uses a -100..100 scale

    themes = {"inflation": ["inflation", "cpi", "price", "prices", "pce"],
              "growth": ["growth", "gdp", "jobs", "employment", "payroll", "recession", "economy"],
              "fed": ["fed", "federal reserve", "powell", "rate", "rates", "fomc", "central bank"]}
    by_theme = {}
    for t, keys in themes.items():
        sub = [a for a in scored if any(k in (a.get("title", "").lower()) for k in keys)]
        if sub:
            s = round(sum(x["sentiment"] for x in sub) / len(sub) * 100, 1)
            by_theme[t] = {"score": s, "label": _label100(s), "articleCount": len(sub)}

    def _hl(a):
        return {"headline": a["title"], "source": a.get("source", "News"), "score": round(a["sentiment"] * 100, 1)}
    bearish = [_hl(a) for a in scored if a["sentiment"] < -0.15][:5]
    bullish = [_hl(a) for a in scored if a["sentiment"] > 0.15][:5]

    bullish_regime = (regime_name or "").lower() in ("goldilocks", "expansion", "reflation", "recovery")
    regime_consistent = (overall_score >= 0) == bullish_regime if scored else None

    return {
        "overall": {"score": overall_score, "label": agg["overall"], "momentum": 0,
                    "momentumLabel": agg["trend"], "articleCount": len(scored)},
        "byTheme": by_theme,
        "topBearishHeadlines": bearish,
        "topBullishHeadlines": bullish,
        "regimeConsistent": regime_consistent,
        # legacy fields kept so both response shapes remain valid:
        "overallSentiment": agg["overall"], "score": overall_score, "trend": agg["trend"],
        "articles": [{"title": a["title"], "source": a.get("source"), "sentiment": a["sentiment"]} for a in scored[:12]],
        "source": "RSS ({}) + finance-lexicon NLP".format(
            ", ".join(sorted({a.get("source") for a in scored if a.get("source")})) or "no feeds reachable"),
        "lastUpdated": now.isoformat(),
    }


async def get_dashboard_data(mode: str = "live") -> DashboardData:
    """Return dashboard data, served from a short-TTL cache when fresh."""
    now_ts = _dash_time.time()
    cached = _DASHBOARD_CACHE.get(mode)
    if cached and now_ts - cached[0] < _DASHBOARD_TTL:
        return cached[1]

    lock = _DASHBOARD_LOCKS.setdefault(mode, _dash_asyncio.Lock())
    async with lock:
        # Another request may have refreshed the cache while we waited for the lock.
        cached = _DASHBOARD_CACHE.get(mode)
        if cached and _dash_time.time() - cached[0] < _DASHBOARD_TTL:
            return cached[1]
        try:
            data = await _build_dashboard_data(mode)
        except DashboardDataUnavailable as e:
            if cached:
                # Serve the last dashboard built from real data, flagged as stale.
                logger.warning(f"[dashboard_handler] {e} — serving last good dashboard")
                stale = cached[1].model_copy(deep=True)
                stale.metadata.dataStatus = "stale"
                stale.metadata.validationWarnings = str(e)
                return stale
            from fastapi import HTTPException
            raise HTTPException(status_code=503, detail=str(e))
        _DASHBOARD_CACHE[mode] = (_cache_stamp(data), data)
        return data


def _cache_stamp(data) -> float:
    """Cache timestamp. A build that fell back from the fitted recession model is stamped so
    it expires in ~30s: the next request retries instead of serving the fallback headline
    (which differs from the fitted model's) for the full TTL."""
    degraded = getattr(getattr(data, "recession", None), "logisticProb", 0) is None
    return _dash_time.time() - (max(0, _DASHBOARD_TTL - 30) if degraded else 0)


async def warm_dashboard_cache(mode: str = "live") -> None:
    """Pre-compute and cache the dashboard so the first UI load hits a warm cache."""
    try:
        data = await _build_dashboard_data(mode)
        _DASHBOARD_CACHE[mode] = (_cache_stamp(data), data)
        logger.info("[dashboard_handler] Cache warmed for mode=%s", mode)
    except Exception as e:
        logger.warning("[dashboard_handler] Cache warm failed: %s", e)


async def _build_dashboard_data(mode: str = "live") -> DashboardData:
    """
    Build complete dashboard data from real market calculations.

    Uses shared calculations module - no hardcoded values.
    """
    logger.info(f"Building dashboard data (mode: {mode})")
    now = datetime.now()

    # Live quotes for display. A quote that can't be fetched stays None — the signal
    # inputs below fall back only to the latest REAL observation, never a made-up level.
    price_symbols = ['SPX', 'NDX', 'VIX', 'TENYR', 'DXY', 'EURUSD', 'GLD', 'WTI']

    prices = {}
    try:
        result = await _yahoo_provider.fetch_latest_async(price_symbols, timeout=8.0)
        if result.success and result.data:
            for symbol, record in result.data.items():
                prices[symbol] = record.price
            logger.info(f"[dashboard_handler] Fetched {len(prices)} live prices")
        else:
            logger.warning(f"[dashboard_handler] Live price fetch failed: {result.error}")
    except Exception as e:
        logger.error(f"[dashboard_handler] Error fetching prices: {e}")

    # Dated history (Yahoo + FRED) for every signal input — real values at each date.
    from api.handlers.macro_inputs import load_macro_inputs
    from api.calculations.signals import GROWTH_HISTORY_OFFSETS
    inputs = await load_macro_inputs()
    spx_s, vix_s, dxy_s = inputs["spx"], inputs["vix"], inputs["dxy"]
    dgs10, dgs2, dgs3mo, dff, sahm_s, be_s = (
        inputs[k] for k in ("dgs10", "dgs2", "dgs3mo", "dff", "sahm", "breakeven"))
    # CPI YoY keyed by release date (monthly FRED panel; cached on disk).
    from api.handlers.macro_inputs import load_monthly_macro, cpi_release_series
    cpi_s = cpi_release_series(await _dash_asyncio.to_thread(load_monthly_macro))

    spx_level = prices.get('SPX') or spx_s.latest
    vix_level = prices.get('VIX') or vix_s.latest
    dxy_level = prices.get('DXY') or dxy_s.latest
    ten_yr = prices.get('TENYR') or dgs10.latest
    ndx_level = prices.get('NDX')
    gold_level = prices.get('GLD')
    oil_level = prices.get('WTI')
    eurusd_level = prices.get('EURUSD')
    # 2Y from FRED DGS2: Yahoo has no 2-year index (^FVX, used before, is the 5-year).
    two_yr = dgs2.latest
    fed_rate = round(dff.latest, 2) if dff else None
    sahm_value = sahm_s.latest

    required = {
        "S&P 500 history": spx_s.values if len(spx_s.values) > 127 else None,
        "VIX": vix_level, "DXY": dxy_level,
        "10Y yield (FRED DGS10)": dgs10.latest, "2Y yield (FRED DGS2)": two_yr,
        "3M yield (FRED DGS3MO)": dgs3mo.latest, "Fed funds (FRED DFF)": fed_rate,
        "Inflation (CPI or 10Y breakeven)": cpi_s.latest if cpi_s else be_s.latest,
    }
    missing_inputs = [name for name, v in required.items() if v is None]
    if missing_inputs:
        raise DashboardDataUnavailable(
            "Live inputs unavailable: " + ", ".join(missing_inputs))

    # Price / FRED history for the derived panels, fetched while the core signals compute.
    _sections_task = _dash_asyncio.create_task(load_section_inputs())

    data_warnings = []
    if inputs.missing():
        data_warnings.append("Refresh failed, serving last good data for: " + ", ".join(inputs.missing()))
    if sahm_value is None:
        data_warnings.append("Sahm rule (FRED SAHMREALTIME) unavailable")
    if not cpi_s:
        data_warnings.append("CPI unavailable — inflation signal uses 10Y breakeven only")
    if not be_s:
        data_warnings.append("10Y breakeven (FRED T10YIE) unavailable — inflation signal uses CPI only")
    _stale_cutoff = (now - timedelta(days=6)).strftime("%Y-%m-%d")
    for _s in (spx_s, vix_s, dxy_s, dgs10, dgs2, dgs3mo, dff):
        if _s.latest_date and _s.latest_date < _stale_cutoff:
            data_warnings.append(f"{_s.name} last observation {_s.latest_date}")

    # Recession model: probit re-fitted on FRED history when available (fits once,
    # off the event loop), else the published Estrella-Mishkin coefficients.
    probit = None
    try:
        from api.models_ml.recession_probit import get_recession_probit
        _p = await _dash_asyncio.wait_for(_dash_asyncio.to_thread(get_recession_probit), timeout=60)
        probit = _p if _p.fitted else None
    except Exception as e:
        logger.warning(f"[dashboard_handler] fitted probit unavailable: {e}")

    def _recession_prob_at(spread_pp, ff):
        if spread_pp is None:
            return None
        if probit is not None and ff is not None:
            return probit.predict(spread_pp, ff)["probability"]
        try:
            return estrella_mishkin_recession_prob(spread_pp)
        except ValueError:
            return None

    # Evaluate every signal at T-4 … Now on S&P trading dates (~3 months span).
    spx_closes = spx_s.values[:-1] + [spx_level]
    labels = ["T-4", "T-3", "T-2", "T-1", "Now"]
    points = []
    for label, off in zip(labels, GROWTH_HISTORY_OFFSETS):
        i = len(spx_closes) - 1 - off
        if i < 0:
            continue
        d = spx_s.dates[i]
        is_now = off == 0
        ten_d, three_d = dgs10.asof(d), dgs3mo.asof(d)
        if is_now:
            ten_d, three_d = dgs10.latest, dgs3mo.latest
        ff_d = fed_rate if is_now else dff.asof(d)
        g = calculate_growth_signal(None, spx_closes[:i + 1])[0]
        inf = calculate_inflation_signal(cpi_s.asof(d), be_s.latest if is_now else be_s.asof(d))[0]
        liq = calculate_liquidity_signal(dxy_level if is_now else dxy_s.asof(d), ten_d, ff_d)[0]
        rsk = calculate_risk_signal(vix_level if is_now else vix_s.asof(d))[0]
        reg = classify_regime(g, inf, liq)[0] if None not in (g, inf, liq) else None
        spread_3m10y = (ten_d - three_d) if None not in (ten_d, three_d) else None
        points.append({"label": label, "date": now.strftime("%Y-%m-%d") if is_now else d,
                       "g": g, "i": inf, "l": liq, "r": rsk, "regime": reg,
                       "rec": _recession_prob_at(spread_3m10y, ff_d)})

    def _series(key):
        pts = [p for p in points if p[key] is not None]
        return [p[key] for p in pts], [p["label"] for p in pts]

    growth_score, growth_trend, _ = calculate_growth_signal(spx_level, spx_s.values[:-1])
    cpi_now = cpi_s.asof(now.strftime("%Y-%m-%d"))
    inflation_score, inflation_trend, _ = calculate_inflation_signal(cpi_now, be_s.latest)
    liquidity_score, liquidity_trend, _ = calculate_liquidity_signal(dxy_level, dgs10.latest, fed_rate)
    risk_score, risk_trend, _ = calculate_risk_signal(vix_level)
    growth_history, growth_labels = _series("g")
    inflation_history, inflation_labels = _series("i")
    liquidity_history, liquidity_labels = _series("l")
    risk_history, risk_labels = _series("r")

    # 10Y-2Y spread (both FRED, same date)
    # Same-date spreads (never one series' latest minus another's older print).
    _c2 = dgs10.last_common(dgs2)
    yield_spread = (_c2[1] - _c2[2]) if _c2 else dgs10.latest - two_yr

    # Classify regime using shared module
    regime_name, regime_confidence, _ = classify_regime(
        growth_score, inflation_score, liquidity_score
    )

    # Measured regime duration: step back through trading days (weekly), re-classifying
    # with each date's as-of inputs, until the regime differs. Replaces the old
    # "6 + confidence * 18 months" formula, which was not a measurement at all. If the
    # price/macro history runs out first, the duration is a lower bound ("N+ months").
    from datetime import date as _date
    run_start, duration_bounded = spx_s.dates[-1], False
    for i in range(len(spx_closes) - 1, -1, -5):
        d = spx_s.dates[i]
        g_d = calculate_growth_signal(None, spx_closes[:i + 1])[0]
        i_d = calculate_inflation_signal(cpi_s.asof(d), be_s.asof(d))[0]
        l_d = calculate_liquidity_signal(dxy_s.asof(d), dgs10.asof(d), dff.asof(d))[0]
        if None in (g_d, i_d, l_d):
            break                                   # history exhausted -> lower bound
        if classify_regime(g_d, i_d, l_d)[0] != regime_name:
            duration_bounded = True
            break
        run_start = d
    regime_duration = max(0, round((now.date() - _date.fromisoformat(run_start)).days / 30.44))
    regime_duration_label = f"{regime_duration}{'' if duration_bounded else '+'} months"

    # Get regime characteristics
    regime_chars = get_regime_characteristics(regime_name)

    # Recession probability from real models (headline = fitted probit, else E-M)
    _c3 = dgs10.last_common(dgs3mo)
    spread_3m10y_now = (_c3[1] - _c3[2]) if _c3 else dgs10.latest - dgs3mo.latest
    recession_data = calculate_recession_probability(
        spread_3m10y_now, fed_rate, sahm_value,
        _recession_prob_at(spread_3m10y_now, fed_rate) if probit is not None else None,
    )
    recession_history = [{"date": p["date"], "probability": round(p["rec"], 4)}
                         for p in points if p["rec"] is not None]

    # Record today's recession forecast for the validation diagnostics (one row per day —
    # the logger upserts). Best-effort: a logging failure never affects the dashboard.
    if recession_data["probability"] is not None:
        def _log_recession():
            try:
                from api.services.recession_validation import recession_validator
                recession_validator.log_recession_forecast(
                    date=now.strftime("%Y-%m-%d"), horizon="12M",
                    components={"logistic": recession_data["logisticProb"],
                                "probit": recession_data["emProbitProb"], "sahm": None},
                    blended_probability=recession_data["probability"],
                    metadata={"model": recession_data.get("model"),
                              "spread_3m10y_pp": round(spread_3m10y_now, 3),
                              "fed_funds": fed_rate, "sahm_value": sahm_value})
            except Exception as e:
                logger.debug(f"[dashboard_handler] recession forecast log failed: {e}")
        _dash_asyncio.get_running_loop().run_in_executor(None, _log_recession)

    # Generate sector allocation

    # Create regime playbook from characteristics
    playbook = RegimePlaybookData(
        summary=regime_chars.description,
        keyRisks=[
            f"Fed policy with {ten_yr:.2f}% 10Y yield" if ten_yr else "Fed policy uncertainty",
            f"VIX at {vix_level:.1f} ({'elevated' if vix_level and vix_level > 25 else 'normal'})" if vix_level else "Volatility risk",
            f"Yield curve (10Y–2Y) {'inverted' if yield_spread < 0 else 'flat' if yield_spread < 0.5 else 'normal' if yield_spread < 1.5 else 'steep'} ({yield_spread:+.2f}pp)"
        ],
        opportunities=[
            f"{regime_chars.equity_bias.title()} equities in {regime_name}",
            f"{regime_chars.duration_bias.capitalize()} duration positioning",
            f"{regime_chars.commodity_bias.capitalize()} commodity exposure"
        ],
        positioningGuidance=f"{regime_name}: {regime_chars.description}"
    )

    # Create regime data
    regime = RegimeData(
        current=regime_name,
        confidence="High" if regime_confidence > 0.75 else "Medium",
        confidenceScore=regime_confidence,
        duration=regime_duration,
        history=[{"date": p["date"], "regime": p["regime"]} for p in points if p["regime"]],
        interpretations=[
            {"factor": "Growth", "impact": "Positive" if growth_score > 0.5 else "Neutral", "color": "success" if growth_score > 0.5 else "neutral"},
            {"factor": "Inflation", "impact": "Stable" if 0.3 < inflation_score < 0.7 else "Elevated", "color": "info" if 0.3 < inflation_score < 0.7 else "warning"},
            {"factor": "Liquidity", "impact": "Adequate" if liquidity_score > 0.4 else "Tight", "color": "neutral" if liquidity_score > 0.4 else "warning"},
        ],
        playbook=playbook
    )

    # Create scores
    scores = Scores(
        growth=round(growth_score * 100, 1),
        inflation=round(inflation_score * 100, 1),
        liquidity=round(liquidity_score * 100, 1),
        risk=round(risk_score * 100, 1)
    )

    # Create signals
    final_signal_value = "Bullish" if risk_score > 0.6 and growth_score > 0.6 else "Bearish" if risk_score < 0.4 else "Neutral"
    signals = SignalsData(
        finalSignal=final_signal_value,
        growth=SignalDetails(
            latestScore=growth_score,
            threeMonthChange=f"{growth_score - growth_history[0]:+.1f}",
            score=growth_score,
            threeMonth=round(growth_score - growth_history[0], 2),
            state="Strong" if growth_score > 0.7 else "Moderate" if growth_score > 0.4 else "Weak",
            direction=growth_trend,
            interpretation=f"Growth signal from SPX momentum: {spx_level:,.0f}" if spx_level else "Growth signal from momentum",
            history=growth_history,
            historyLabels=growth_labels
        ),
        inflation=SignalDetails(
            latestScore=inflation_score,
            threeMonthChange=f"{inflation_score - inflation_history[0]:+.1f}",
            score=inflation_score,
            threeMonth=round(inflation_score - inflation_history[0], 2),
            state="Elevated" if inflation_score > 0.6 else "Moderate" if inflation_score > 0.4 else "Low",
            direction=inflation_trend,
            interpretation=("Inflation signal from "
                            + " and ".join(x for x in (
                                f"CPI {cpi_now:.1f}% YoY" if cpi_now is not None else None,
                                f"10Y breakeven {be_s.latest:.2f}%" if be_s.latest is not None else None) if x)),
            history=inflation_history,
            historyLabels=inflation_labels
        ),
        liquidity=SignalDetails(
            latestScore=liquidity_score,
            threeMonthChange=f"{liquidity_score - liquidity_history[0]:+.1f}",
            score=liquidity_score,
            threeMonth=round(liquidity_score - liquidity_history[0], 2),
            state="Loose" if liquidity_score > 0.6 else "Tight" if liquidity_score < 0.4 else "Neutral",
            direction=liquidity_trend,
            interpretation=f"Liquidity signal from DXY ({dxy_level:.1f}) and rates" if dxy_level else "Liquidity from rates",
            history=liquidity_history,
            historyLabels=liquidity_labels
        ),
        risk=SignalDetails(
            latestScore=risk_score,
            threeMonthChange=f"{risk_score - risk_history[0]:+.1f}",
            score=risk_score,
            threeMonth=round(risk_score - risk_history[0], 2),
            state="High Appetite" if risk_score > 0.7 else "Moderate" if risk_score > 0.4 else "Low Appetite",
            direction=risk_trend,
            interpretation=f"Risk signal from VIX level ({vix_level:.1f})" if vix_level else "Risk signal from volatility",
            history=risk_history,
            historyLabels=risk_labels
        )
    )

    # Create recession data
    recession = RecessionData(
        probability=recession_data["probability"],
        level=recession_data["level"],
        logisticProb=recession_data["logisticProb"],
        emProbitProb=recession_data["emProbitProb"],
        sahmValue=recession_data["sahmValue"],
        sahmSignal=recession_data["sahmSignal"],
        description=f"{recession_data['level']} probability ({recession_data['probability']:.0%})",
        components=recession_data["components"],
        history=recession_history,
    )

    # Create key metrics
    # Real daily % changes from cached daily history (reuses market_handler helpers,
    # so no extra network cost). Previously all *ChangePct fields were None -> the UI
    # showed +0.00% for FX/prices.
    from api.handlers.market_handler import _fetch_closes, _pct_change
    _chg_tickers = {
        'SPX': '^GSPC', 'NDX': '^NDX', 'VIX': '^VIX', 'DXY': 'DX-Y.NYB',
        'EURUSD': 'EURUSD=X', 'GLD': 'GC=F', 'WTI': 'CL=F',
    }
    # Store as FRACTIONS (0.0007 = 0.07%) to match the frontend's fmtChange convention.
    # Dated closes, so each change carries the session it belongs to: Yahoo's spot-FX bars
    # land a day later than equities/DXY (see api/market_dates.py), so on any given morning
    # EUR/USD's latest complete session can be a day behind the S&P's.
    from api.handlers.market_handler import _fetch_dated_closes_literal
    _chg, _chg_asof = {}, {}
    _spx_closes = None
    for _k, _t in _chg_tickers.items():
        _dated = await _fetch_dated_closes_literal(_t)
        _days = sorted(_dated)
        _closes = [_dated[d] for d in _days]
        if _k == 'SPX':
            _spx_closes = _closes
        _pc = _pct_change(_closes, 1) if _closes else None
        _chg[_k] = (_pc / 100.0) if _pc is not None else None
        _chg_asof[_k] = _days[-1] if _days else None
    # Yields move in basis points, not percent: the 10Y's daily change in bp from ^TNX.
    # (This field used to carry the 2s10s SPREAD, which the UI showed as the 10Y's change.)
    _tnx = await _fetch_closes('^TNX')
    ten_yr_change_bp = round((_tnx[-1] - _tnx[-2]) * 100, 1) if _tnx and len(_tnx) >= 2 else None
    spx_change_pts = (round(_spx_closes[-1] - _spx_closes[-2], 2)
                      if _spx_closes and len(_spx_closes) >= 2 else None)

    key_metrics = KeyMetrics(
        growth=MetricWithSparkline(
            value=round(growth_score * 100, 1),
            formatted=f"{growth_score * 100:.1f}%",
            direction="up" if growth_score > 0.6 else "stable" if growth_score > 0.4 else "down",
            sparklineData=[h * 100 for h in growth_history]
        ),
        inflation=MetricWithSparkline(
            value=round(inflation_score * 100, 1),
            formatted=f"{inflation_score * 100:.1f}%",
            direction="up" if inflation_score > 0.6 else "stable" if inflation_score > 0.4 else "down",
            sparklineData=[h * 100 for h in inflation_history]
        ),
        liquidity=MetricWithSparkline(
            value=round(liquidity_score, 2),
            formatted=f"{liquidity_score:.2f}",
            direction="up" if liquidity_score > 0.6 else "stable" if liquidity_score > 0.4 else "down",
            sparklineData=liquidity_history
        ),
        risk=MetricWithSparkline(
            value=round((1 - risk_score) * 100, 1),
            formatted=f"{(1 - risk_score) * 100:.1f}%",
            direction="up" if risk_score < 0.4 else "stable" if risk_score < 0.6 else "down",
            sparklineData=[(1 - h) * 100 for h in risk_history]
        ),
        recession=MetricWithSparkline(
            value=round(recession_data["probability"] * 100, 1),
            formatted=f"{recession_data['probability'] * 100:.1f}%",
            direction="up" if recession_data["probability"] > 0.3 else "stable",
            sparklineData=[round(h["probability"] * 100, 1) for h in recession_history]
        ),
        regimeDuration={"current": regime_duration_label, "currentRegime": regime_name,
                        "measured": "exact" if duration_bounded else "lower bound (history limit)"},
        spxLevel=spx_level,
        spxChange=spx_change_pts,
        spxChangePct=_chg.get('SPX'),
        ndxLevel=ndx_level,
        ndxChangePct=_chg.get('NDX'),
        tenYearYield=ten_yr,
        tenYearChange=ten_yr_change_bp,
        twoYearYield=two_yr,
        dxy=dxy_level,
        dxyChangePct=_chg.get('DXY'),
        eurusd=eurusd_level,  # Fixed: was hardcoded to None
        eurusdChangePct=_chg.get('EURUSD'),
        gold=gold_level,
        goldChangePct=_chg.get('GLD'),
        oil=oil_level,
        oilChangePct=_chg.get('WTI'),
        fedRate=fed_rate,
        vix=vix_level,
        vixChange=_chg.get('VIX'),
        changeAsOf=_chg_asof,
    )

    # Panels below are computed from observed price / FRED history (see
    # api/handlers/dashboard_sections.py); a missing input yields None, not a made-up value.
    _sections = await _sections_task

    # Sector allocation: regime playbook weights + observed sector relative strength.
    sector_allocation = calculate_sector_allocation(
        regime_name, growth_score, inflation_score,
        sector_stats=build_sector_stats(_sections), confidence=regime_confidence)

    factor_rotation = build_factor_rotation(_sections)
    momentum_veto = build_momentum_veto(_sections)
    correlation_regime = build_correlation_regime(_sections)
    debt_cycle = build_debt_cycle(_sections)
    international_macro = build_international_macro(
        _sections, regime_name, regime_confidence, growth_score)
    _cta_trends = build_trend_signals(_sections, now)

    # Ensemble — vote of the live models (each component is a real signal or model).
    from api.schemas.models import EnsembleData
    _votes = {
        "Growth (SPX momentum)": growth_score > 0.5,
        "Risk appetite (VIX)": risk_score > 0.5,
        "Liquidity (DXY/rates)": liquidity_score > 0.5,
        "Recession model": recession_data["probability"] < 0.5,
    }
    if momentum_veto is not None:
        _votes["12-1 momentum"] = not momentum_veto.vetoActive
    if _cta_trends is not None:
        _votes["CTA trend"] = _cta_trends["aggregateScore"] > 0
    _n_bull = sum(_votes.values())
    ensemble_score = round((growth_score + (1 - recession_data["probability"]) + risk_score
                            + liquidity_score) / 4, 2)
    _components = [("Growth signal", growth_score), ("1 − recession probability", 1 - recession_data["probability"]),
                   ("Risk-appetite signal", risk_score), ("Liquidity signal", liquidity_score)]
    ensemble = EnsembleData(
        score=ensemble_score,
        conviction="High" if ensemble_score > 0.7 else "Medium" if ensemble_score > 0.5 else "Low",
        agreement=round(max(_n_bull, len(_votes) - _n_bull) / len(_votes), 2),
        riskBudget=round(risk_score * 0.8 + 0.1, 2),
        mode="Equal-weight",   # fixed equal weights — nothing adapts (was labelled "Dynamic")
        bullishPct=round(_n_bull / len(_votes) * 100, 1),
        components=[{"name": n, "score": round(v, 2), "weight": 0.25, "contribution": round(v * 0.25, 3)}
                    for n, v in _components],
        votes=[{"model": k, "bullish": bool(v)} for k, v in _votes.items()],
    )

    # Signal Stack - constructed from calculated signals
    # Build reasoning for signal stack
    signal_stack_reasoning = f"RISK {'ON' if risk_score > 0.5 else 'OFF'} consensus: Growth signal strong ({growth_score:.2f})"

    signal_stack = SignalStackData(
        layers=[
            SignalStackLayer(
                layer="Growth",
                priority=1,
                signal="BULLISH" if growth_score > 0.6 else "BEARISH" if growth_score < 0.4 else "NEUTRAL",
                conviction=growth_score if growth_score > 0.5 else 1 - growth_score,
                override=None
            ),
            SignalStackLayer(
                layer="Inflation",
                priority=2,
                signal="OVERWEIGHT" if inflation_score > 0.6 else "UNDERWEIGHT" if inflation_score < 0.4 else "NEUTRAL",
                conviction=inflation_score if inflation_score > 0.5 else 1 - inflation_score,
                override=None
            ),
            SignalStackLayer(
                layer="Liquidity",
                priority=3,
                signal="RISK_ON" if liquidity_score > 0.6 else "RISK_OFF" if liquidity_score < 0.4 else "NEUTRAL",
                conviction=liquidity_score if liquidity_score > 0.5 else 1 - liquidity_score,
                override=None
            ),
            SignalStackLayer(
                layer="Risk",
                priority=4,
                signal="RISK_ON" if risk_score > 0.6 else "DEFENSIVE" if risk_score < 0.4 else "NEUTRAL",
                conviction=risk_score if risk_score > 0.5 else 1 - risk_score,
                override=None
            ),
            SignalStackLayer(
                layer="Regime",
                priority=5,
                signal=regime_name.upper() if regime_name else "NEUTRAL",
                conviction=regime_confidence,
                override=None
            ),
        ],
        finalSignal=final_signal_value.upper().replace(" ", "_"),
        confidence=round((growth_score + inflation_score + liquidity_score + risk_score) / 4, 2),
        reasoning=signal_stack_reasoning,
        timestamp=now.isoformat()
    )

    # Metadata
    metadata = DataMetadata(
        latestDate=spx_s.latest_date or now.isoformat(),
        lastRefreshed=now.isoformat(),
        dataStatus="degraded" if data_warnings else "current",
        daysSinceUpdate=0,
        mode=mode,
        validationWarnings="; ".join(data_warnings) or None,
        supportingEvidence=f"Fetched {len(prices)} prices. Signals: G={growth_score:.2f}, I={inflation_score:.2f}. Regime: {regime_name} ({regime_confidence:.0%} confidence)"
    )

    # ── Compute all optional-section data inline (avoids recursive handler calls) ──

    # GDP Nowcast — Atlanta Fed GDPNow via FRED.
    _nowcast = build_nowcast(_sections, now)

    # Liquidity / financial conditions. The model score (DXY 60%, Fed funds − 10Y 40%) is
    # shown next to the standard reference, the Chicago Fed NFCI; Fed stance comes from the
    # FOMC target's actual moves and credit availability from HY spreads (each was previously
    # inferred from the 10Y level or from the liquidity score itself).
    from api.calculations.global_macro import policy_stats as _policy_stats
    _liq_regime = "Loose" if liquidity_score > 0.6 else "Tight" if liquidity_score < 0.4 else "Neutral"
    _nfci = _sections.series("NFCI")
    _tgt = _sections.series("DFEDTARU")
    _fed = _policy_stats(list(zip(_tgt.dates, _tgt.values))) if _tgt else {"available": False}
    _fed_stance = ({"hiking": "Tightening", "cutting": "Easing"}.get(_fed.get("stance"), "On hold")
                   if _fed.get("available") else None)
    _hy = _sections.series("BAMLH0A0HYM2").latest
    _policy_minus_10y = (fed_rate - dgs10.latest) if (fed_rate is not None and dgs10.latest is not None) else None
    _dxy_state = "Supportive" if dxy_level < 100 else "Restrictive" if dxy_level > 108 else "Neutral"
    _nfci_desc = (f"Chicago Fed NFCI {_nfci.latest:+.2f} (week of {_nfci.latest_date}; < 0 = looser than average)"
                  if _nfci else "NFCI unavailable")
    _liquidity = {
        "liquidityScore": round(liquidity_score, 2),
        "regime": _liq_regime,
        "indicators": [
            {"name": "Chicago Fed NFCI", "value": round(_nfci.latest, 2) if _nfci else None,
             "status": (None if not _nfci else "Looser than average" if _nfci.latest < 0 else "Tighter than average"),
             "contribution": None},
            {"name": "US Dollar Index (DXY)", "value": round(dxy_level, 1), "status": _dxy_state, "contribution": 0.6},
            {"name": "Fed funds − 10Y (pp)", "value": round(_policy_minus_10y, 2) if _policy_minus_10y is not None else None,
             "status": None if _policy_minus_10y is None else ("Restrictive" if _policy_minus_10y > 0 else "Accommodative"),
             "contribution": 0.4},
        ],
        "fedPolicyStance": _fed_stance,
        "fedTargetUpper": _fed.get("rate"),
        "fedLastMove": _fed.get("last_move"),
        "creditAvailability": (None if _hy is None else "Ample" if _hy < 4.0 else "Normal" if _hy < 6.0 else "Tight"),
        "hyOas": round(_hy, 2) if _hy is not None else None,
        "description": (f"Model liquidity score {liquidity_score:.2f} ({_liq_regime.lower()}): DXY {dxy_level:.1f}, "
                        f"Fed funds − 10Y {_policy_minus_10y:+.2f}pp. {_nfci_desc}."
                        if _policy_minus_10y is not None else f"Model liquidity score {liquidity_score:.2f}. {_nfci_desc}."),
        "lastUpdated": now.isoformat(),
    }

    # Sentiment — VIX level / term structure (^VIX3M) / 1m change, cross-asset 3m momentum.
    _sentiment = build_sentiment(_sections, vix_level, risk_score, now)

    # Valuation — SPY trailing P/E, 10Y TIPS real yield (z-scored), equity yield gap.
    _valuation = build_valuation(_sections, now)

    # News Sentiment — REAL headline-level sentiment from live RSS news (was a VIX-derived stub).
    _news_sentiment = _build_news_sentiment(regime_name, now)

    # Reflexivity — feedback loops (equity↔credit, vol↔deleveraging, dollar↔conditions)
    # measured as z-scores of observed moves.
    _reflexivity = build_reflexivity(_sections, regime_name, now)

    # Factor Decomposition — OLS of Nasdaq-100 returns on ETF factor returns (1y daily).
    _factor_decomp = build_factor_decomposition(_sections, now)

    # Long-term Forecasts — building-block CMA from observed inputs (ETF earnings yields,
    # 10Y breakeven, 10Y yield, realized vol); shared by /api/forecasts/longterm and
    # /api/business/expected-returns.
    _gmo_forecasts = build_cma(_sections, ten_yr, dgs3mo.latest, be_s.latest, now)

    # Advanced Indicators — Sahm rule (FRED SAHMREALTIME), credit impulse (FRED bank
    # credit vs GDP), LEI (no source → unavailable), inverse-vol risk-parity weights.
    _advanced = build_advanced_indicators(_sections, sahm_s, now)

    # Build risk-indicator stub from computed scores (no separate handler yet)
    _risk_indicators = {
        "vix": vix_level,
        "vixState": "Elevated" if (vix_level or 0) > 25 else "Normal",
        "yieldSpread": round(yield_spread, 3),
        # ICE BofA US High Yield OAS (FRED BAMLH0A0HYM2, percent); None if unavailable.
        "creditSpread": _r2(_sections.series("BAMLH0A0HYM2").latest),
        "riskScore": round(risk_score, 3),
        "riskState": "Risk-Off" if risk_score < 0.35 else "Risk-On" if risk_score > 0.65 else "Neutral",
        "lastUpdated": now.isoformat(),
    }

    # Regime transitions — empirical quadrant transition matrix (FRED monthly, since 1985).
    _regime_transitions = build_regime_transitions(_sections, regime_name, now)
    # Pure alpha — cross-asset 3m momentum z-scores.
    _pure_alpha = build_pure_alpha(_sections, now)
    _model_agreement = {
        "agreementScore": round(ensemble.agreement, 2),
        "agreementLabel": "High" if ensemble.agreement > 0.75 else "Medium" if ensemble.agreement >= 0.6 else "Low",
        "disagreements": [],
        "lastUpdated": now.isoformat(),
    }
    _summary = (f"{regime_name.title()} regime ({regime_confidence:.0%} confidence, "
                f"{regime_duration_label}): {regime_chars.description.lower()}. Growth signal "
                f"{growth_score:.2f}, inflation signal {inflation_score:.2f}"
                + (f"; CPI {cpi_now:.1f}% y/y" if cpi_now is not None else "")
                + (f", 10Y {ten_yr:.2f}%" if ten_yr else "") + ".")
    _investment_memo = {
        "title": f"{regime_name.title()} Regime — Investment Memo",
        "regimeSummary": _summary,
        "summary": _summary,
        "keyPoints": [t for t in regime_chars.themes],
        "risks": list(playbook.keyRisks),
        "opportunities": list(playbook.opportunities),
        "lastUpdated": now.isoformat(),
    }
    # Upcoming releases from the release calendar (was a fixed list with every date "TBD").
    try:
        from api.data_freshness import get_live_freshness
        from api.release_calendar import upcoming_releases
        _fr = await _dash_asyncio.to_thread(get_live_freshness)
        _data_to_watch = upcoming_releases(_fr.get("series", []), now.date())
    except Exception as _e:
        logger.warning(f"[dashboard] release calendar unavailable: {_e}")
        _data_to_watch = []
    # Monetary-policy transmission channels — REAL status derived from live rates/curve/FX/risk
    # (was an empty-channels stub). Each channel: how freely policy is transmitting right now.
    _curve = yield_spread
    def _ch(name, restricted, active, desc):
        status = "Restricted" if restricted else "Active" if active else "Mixed"
        return {"channel": name, "status": status, "description": desc}
    _transmission_channels = [
        _ch("Interest Rate", fed_rate >= 4.5, fed_rate <= 2.5,
            f"Fed funds {fed_rate:.2f}% — {'restrictive policy' if fed_rate >= 4.5 else 'accommodative' if fed_rate <= 2.5 else 'neutral'} stance"),
        _ch("Yield Curve", _curve < 0, _curve > 1.0,
            f"10Y-2Y {_curve * 100:+.0f}bps — {'inverted (recession signal)' if _curve < 0 else 'steep (easing)' if _curve > 1.0 else 'flat'}"),
    ]
    # Credit channel from the ICE BofA US HY OAS (FRED), not the VIX-based risk score.
    _hy = _sections.series("BAMLH0A0HYM2").latest
    if _hy is not None:
        _transmission_channels.append(_ch("Credit", _hy >= 5.0, _hy <= 3.5,
            f"HY OAS {_hy:.2f}% — {'credit tightening' if _hy >= 5.0 else 'credit flowing' if _hy <= 3.5 else 'mixed'}"))
    _transmission_channels += [
        _ch("Exchange Rate", dxy_level >= 106, dxy_level <= 98,
            f"DXY {dxy_level:.1f} — {'strong USD tightens conditions' if dxy_level >= 106 else 'weak USD eases' if dxy_level <= 98 else 'neutral'}"),
        _ch("Asset Price", growth_score < 0.4, growth_score > 0.6,
            f"Equity momentum {growth_score:.2f} — {'wealth effect positive' if growth_score > 0.6 else 'negative' if growth_score < 0.4 else 'neutral'}"),
        _ch("Volatility", vix_level >= 25, vix_level <= 15,
            f"VIX {vix_level:.1f} — {'stress impedes transmission' if vix_level >= 25 else 'calm supports flow' if vix_level <= 15 else 'normal'}"),
    ]
    _active_n = sum(1 for c in _transmission_channels if c["status"] == "Active")
    _transmission_analysis = {
        "channels": _transmission_channels,
        "activeChannels": _active_n,
        "totalChannels": len(_transmission_channels),
        # Share of channels currently transmitting freely.
        "overallStrength": round(_active_n / len(_transmission_channels), 2),
        "source": "computed from live rates / curve / FX / risk",
        "lastUpdated": now.isoformat(),
    }
    # Performance tracking — accuracy of the persisted forecast log (database forecast_history).
    _performance_tracking = build_performance_tracking(_sections, now)
    # Risk parity — inverse-vol SPY/TLT/GLD/DBC with realized portfolio vol (also exposed
    # under the frontend-expected riskParityAllocation key).
    _risk_parity_dict = build_risk_parity(_sections, now)
    # ──────────────────────────────────────────────────────────────────────────

    # Build dashboard
    dashboard = DashboardData(
        regime=regime,
        keyMetrics=key_metrics,
        scores=scores,
        recession=recession,
        signals=signals,
        sectorAllocation=sector_allocation,
        riskParity=_risk_parity_dict,
        # Historical regime-conditional returns for the current growth×inflation quadrant.
        expectedReturns=build_expected_returns(_sections, _regime_transitions, now),
        businessLayer=BusinessLayerData(
            recommendations=f"""## Market Outlook

Current regime: **{regime_name}** - {regime_chars.description}

## Key Metrics
- Growth signal: {growth_score:.2f} (0–1)
- Inflation signal: {inflation_score:.2f}
- Liquidity signal: {liquidity_score:.2f}
- Risk-appetite signal: {risk_score:.2f}
- Recession Probability: {recession_data['probability']:.0%}

## Positioning
{chr(10).join(['- ' + t for t in regime_chars.themes])}

## Risk Management
- Regime baseline sizing: {regime_chars.position_modifier:.0%} of normal (composite risk budget: {round(risk_score * 0.8 + 0.1, 2):.2f}x)
- VIX Level: {f'{vix_level:.1f}' if vix_level else 'N/A'}
- Yield Curve: {yield_spread:+.2f}%
""",
            expectedReturns=[],
            positionSizing=[],
            signalScorecard=[],
            decisionLog=[]
        ),
        metadata=metadata,
        ensemble=ensemble,
        timestamp=now.isoformat(),
        mode=mode,
        factorRotation=factor_rotation,
        internationalMacro=international_macro,
        debtCycle=debt_cycle,
        momentumVeto=momentum_veto,
        correlationRegime=correlation_regime,
        signalStack=signal_stack,
        regime_confidence=regime_confidence,
        regimePlaybook=playbook,
        # Optional section data — all fetched above
        nowcast=_nowcast,
        liquidity=_liquidity,
        sentiment=_sentiment,
        valuation=_valuation,
        newsSentiment=_news_sentiment,
        reflexivity=_reflexivity,
        factorDecomposition=_factor_decomp,
        trendSignals=_cta_trends,
        gmoForecasts=_gmo_forecasts,
        advancedIndicators=_advanced,
        riskIndicators=_risk_indicators,
        regimeTransitions=_regime_transitions,
        pureAlpha=_pure_alpha,
        modelAgreement=_model_agreement,
        investmentMemo=_investment_memo,
        dataToWatch=_data_to_watch,
        transmissionAnalysis=_transmission_analysis,
        performanceTracking=_performance_tracking,
        riskParityAllocation=_risk_parity_dict,
    )

    # Validate
    dashboard_dict = dashboard.dict()
    validation = validate_dashboard_payload(dashboard_dict)

    if not validation.valid:
        logger.warning("[dashboard_handler] Validation issues", extra={"issues": validation.issues})

    log_validation_event("dashboard_handler", validation)
    log_dashboard_event(dashboard_dict, metadata={"mode": mode, "handler": "dashboard_handler", "calculated": True})

    logger.info(f"[dashboard_handler] Dashboard built: {regime_name} regime, scores G={growth_score:.2f} I={inflation_score:.2f}")

    return dashboard
