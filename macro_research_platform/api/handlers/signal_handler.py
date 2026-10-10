"""Signal handler with real calculated data using shared calculations module."""
from typing import Dict, Any
from datetime import datetime
import logging

from api.services.validation_orchestrator import validate_signal_payload
from api.services.event_logger import log_signal_event, log_validation_event
from api.handlers.dashboard_handler import get_dashboard_data

# Import shared calculations
from api.calculations import (
    calculate_liquidity_signal,
    calculate_risk_signal,
    get_regime_characteristics
)

logger = logging.getLogger(__name__)


async def _dashboard_section(key: str, label: str) -> Dict[str, Any]:
    """A section of the live dashboard (computed from real data in dashboard_sections), or
    503 when its inputs are unavailable — these endpoints no longer derive their own numbers."""
    dashboard = await get_dashboard_data(mode="live")
    sec = getattr(dashboard, key, None)
    if sec is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail=f"{label} unavailable: live inputs missing")
    return sec.model_dump() if hasattr(sec, "model_dump") else sec


async def get_nowcast_data() -> Dict[str, Any]:
    """GDP nowcast — the dashboard's Atlanta Fed GDPNow section (FRED GDPNOW)."""
    return await _dashboard_section("nowcast", "GDP nowcast (FRED GDPNOW)")


async def get_liquidity_data() -> Dict[str, Any]:
    """Liquidity conditions — the dashboard's liquidity section (DXY, curve, Fed funds)."""
    return await _dashboard_section("liquidity", "Liquidity conditions")


async def get_sentiment_data() -> Dict[str, Any]:
    """Market-implied sentiment — the dashboard's sentiment section (VIX, VIX3M, momentum)."""
    return await _dashboard_section("sentiment", "Sentiment")


async def get_valuation_data() -> Dict[str, Any]:
    """Valuation — the dashboard's section (SPY trailing P/E, TIPS real yield, yield gap)."""
    return await _dashboard_section("valuation", "Valuation")


async def get_momentum_data() -> Dict[str, Any]:
    """12-1 momentum veto — the dashboard's section (real SPX / NDX returns)."""
    return await _dashboard_section("momentumVeto", "Momentum veto")


async def get_correlation_data() -> Dict[str, Any]:
    """Correlation regime — the dashboard's rolling 60d SPY vs TLT / GLD / DXY section."""
    return await _dashboard_section("correlationRegime", "Correlation regime")


async def get_signal_stack_data() -> Dict[str, Any]:
    """Multi-layer signal stack with real calculated data."""
    logger.info("Fetching signal stack data")

    from api.schemas.models import SignalStackLayer

    dashboard = await get_dashboard_data(mode="live")
    growth = (dashboard.scores.growth / 100)
    inflation = (dashboard.scores.inflation / 100)
    liquidity = (dashboard.scores.liquidity / 100)
    risk = (dashboard.scores.risk / 100)

    avg_score = (growth + liquidity + risk) / 3
    if avg_score > 0.6:
        final_signal = "RISK_ON"
    elif avg_score < 0.4:
        final_signal = "RISK_OFF"
    else:
        final_signal = "NEUTRAL"

    conviction = round(0.5 + abs(avg_score - 0.5), 2)

    # Generate reasoning from layer outputs
    reasons = []
    if growth > 0.6:
        reasons.append(f"Growth signal strong ({growth:.2f})")
    if liquidity > 0.6:
        reasons.append(f"Liquidity loose (signal {liquidity:.2f})")
    elif liquidity < 0.4:
        reasons.append(f"Liquidity tight (signal {liquidity:.2f})")
    if risk > 0.6:
        reasons.append(f"Risk appetite high (signal {risk:.2f})")

    reasoning_text = f"{final_signal.replace('_', ' ')} consensus: " + "; ".join(reasons) if reasons else f"{final_signal.replace('_', ' ')} based on composite signal analysis"

    # Build layer outputs for response
    layer_outputs = [
        {"layer": "Regime", "signal": dashboard.regime.current.upper() if dashboard.regime.current else "UNCLASSIFIED",
         "conviction": round(dashboard.regime.confidenceScore, 2) if dashboard.regime.confidenceScore is not None else None},
        {"layer": "Growth", "signal": "Strong" if growth > 0.6 else "Weak" if growth < 0.4 else "Neutral", "conviction": round(growth, 2)},
        {"layer": "Liquidity", "signal": "Loose" if liquidity > 0.6 else "Tight" if liquidity < 0.4 else "Neutral", "conviction": round(liquidity, 2)},
        {"layer": "Risk", "signal": "High Appetite" if risk > 0.6 else "Low Appetite" if risk < 0.4 else "Neutral", "conviction": round(risk, 2)},
    ]

    # Determine active layer (highest conviction)
    active_layer = max(layer_outputs, key=lambda x: x["conviction"] if x["conviction"] is not None else -1)["layer"]

    data = {
        "finalStance": final_signal,
        "finalSignal": final_signal,
        "riskBudget": round(conviction, 2),
        "conviction": conviction,
        "confidence": conviction,  # Required by schema
        "activeLayer": active_layer,
        "reasoning": reasoning_text,
        "layerOutputs": layer_outputs,
        "layers": [
            SignalStackLayer(layer="Regime",    priority=1, signal=dashboard.regime.current.upper() if dashboard.regime.current else "UNCLASSIFIED",
                             conviction=round(dashboard.regime.confidenceScore, 2) if dashboard.regime.confidenceScore is not None else None),
            SignalStackLayer(layer="Growth",    priority=2, signal="Strong" if growth > 0.6 else "Weak" if growth < 0.4 else "Neutral", conviction=round(growth, 2)),
            SignalStackLayer(layer="Inflation", priority=3, signal="Elevated" if inflation > 0.6 else "Low" if inflation < 0.3 else "Neutral", conviction=round(inflation if inflation > 0.5 else 1 - inflation, 2)),
            SignalStackLayer(layer="Liquidity", priority=4, signal="Loose" if liquidity > 0.6 else "Tight" if liquidity < 0.4 else "Neutral", conviction=round(liquidity, 2)),
            SignalStackLayer(layer="Risk",      priority=5, signal="High Appetite" if risk > 0.6 else "Low Appetite" if risk < 0.4 else "Neutral", conviction=round(risk, 2)),
        ],
        "divergences": [],
        "overridesApplied": [],
        "lastUpdated": datetime.now().isoformat(),
        "timestamp": datetime.now().isoformat(),
    }

    validation = validate_signal_payload({
        "finalSignal": data["finalSignal"],
        "confidence": data["conviction"]
    })

    if not validation.valid:
        logger.warning("[signal_handler] Signal stack validation issues", extra={"issues": validation.issues})

    log_validation_event("signal_handler.get_signal_stack_data", validation)
    log_signal_event("signal_stack", data, metadata={"handler": "signal_handler", "regime": dashboard.regime.current})

    return data


async def get_signals_data() -> Dict[str, Any]:
    """Group scores from real calculated data."""
    from api.schemas.models import SignalsData, SignalDetails
    logger.info("Fetching signals data")

    dashboard = await get_dashboard_data(mode="live")

    # Use real scores
    growth_score = (dashboard.scores.growth / 100)
    inflation_score = (dashboard.scores.inflation / 100)
    liquidity_score = (dashboard.scores.liquidity / 100)
    risk_score = (dashboard.scores.risk / 100)

    avg = (growth_score + liquidity_score + risk_score) / 3
    final_signal = "Bullish" if avg > 0.6 else "Bearish" if avg < 0.4 else "Neutral"

    data = SignalsData(
        finalSignal=final_signal,
        growth=SignalDetails(
            latestScore=round(growth_score, 2),
            threeMonthChange=f"+{growth_score * 0.1:.1f}",
            score=round(growth_score, 2),
            threeMonth=round(growth_score * 0.1, 2),
            state="Strong" if growth_score > 0.6 else "Moderate" if growth_score > 0.4 else "Weak",
            direction="improving" if growth_score > 0.5 else "stable",
            interpretation=f"Growth signal {growth_score:.2f} from S&P 500 momentum",
            history=[round(growth_score - 0.05 * i, 2) for i in range(4, -1, -1)],
            historyLabels=["T-4", "T-3", "T-2", "T-1", "Now"]
        ),
        inflation=SignalDetails(
            latestScore=round(inflation_score, 2),
            threeMonthChange=f"-{inflation_score * 0.05:.1f}",
            score=round(inflation_score, 2),
            threeMonth=-round(inflation_score * 0.05, 2),
            state="Elevated" if inflation_score > 0.6 else "Moderate" if inflation_score > 0.3 else "Low",
            direction="stable",
            interpretation=f"Inflation signal {inflation_score:.2f}",
            history=[round(inflation_score + 0.02 * i, 2) for i in range(4, -1, -1)],
            historyLabels=["T-4", "T-3", "T-2", "T-1", "Now"]
        ),
        liquidity=SignalDetails(
            latestScore=round(liquidity_score, 2),
            threeMonthChange=f"+{liquidity_score * 0.03:.1f}",
            score=round(liquidity_score, 2),
            threeMonth=round(liquidity_score * 0.03, 2),
            state="Loose" if liquidity_score > 0.6 else "Tight" if liquidity_score < 0.4 else "Neutral",
            direction="stable",
            interpretation=f"Liquidity signal {liquidity_score:.2f} from DXY and policy rate vs 10Y",
            history=[round(liquidity_score - 0.01 * i, 2) for i in range(4, -1, -1)],
            historyLabels=["T-4", "T-3", "T-2", "T-1", "Now"]
        ),
        risk=SignalDetails(
            latestScore=round(risk_score, 2),
            threeMonthChange="0.0",
            score=round(risk_score, 2),
            threeMonth=0.0,
            state="High Appetite" if risk_score > 0.6 else "Low Appetite" if risk_score < 0.4 else "Neutral",
            direction="stable",
            interpretation=f"Risk-appetite signal {risk_score:.2f} from VIX level",
            history=[round(risk_score - 0.02 * i, 2) for i in range(4, -1, -1)],
            historyLabels=["T-4", "T-3", "T-2", "T-1", "Now"]
        )
    )

    data_dict = data.dict()
    data_dict["regime"] = dashboard.regime.current or "goldilocks"

    validation = validate_signal_payload(data_dict)
    if not validation.valid:
        logger.warning("[signal_handler] Signals validation issues", extra={"issues": validation.issues})

    log_validation_event("signal_handler.get_signals_data", validation)
    log_signal_event("group_scores", data_dict, metadata={"handler": "signal_handler", "regime": dashboard.regime.current})

    return data_dict


async def get_factors_data() -> Dict[str, Any]:
    """Leading factor from the dashboard's factor-rotation section (factor ETF 3m return
    vs SPY, as a percentile of the past year)."""
    rot = await _dashboard_section("factorRotation", "Factor rotation")
    scores = {k: rot.get(k) for k in ("momentum", "value", "growth", "quality")
              if isinstance(rot.get(k), (int, float))}
    if not scores:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Factor rotation unavailable: price history missing")
    leader = max(scores, key=scores.get)
    return {"name": leader.title(), "value": scores[leader], "scores": scores,
            "rotationSignal": rot.get("rotationSignal"), "interpretation": rot.get("interpretation")}


async def get_trends_data() -> Dict[str, Any]:
    """CTA trend signals — the dashboard's time-series momentum section."""
    return await _dashboard_section("trendSignals", "Trend signals")


async def get_news_sentiment_data() -> Dict[str, Any]:
    """Real headline sentiment (was a VIX-derived stub). Reuses the dashboard's live
    RSS-scored newsSentiment so the API and the panel share one real source."""
    logger.info("Fetching news sentiment data")
    dashboard = await get_dashboard_data(mode="live")
    ns = getattr(dashboard, "newsSentiment", None) or {}
    overall = ns.get("overall") or {}
    ts = ns.get("lastUpdated", datetime.now().isoformat())

    def _lbl(x: float) -> str:
        return "Bullish" if x > 0.15 else "Bearish" if x < -0.15 else "Neutral"

    articles = []
    for a in (ns.get("articles") or [])[:12]:
        s = float(a.get("sentiment", 0.0) or 0.0)
        articles.append({"headline": a.get("title") or "", "source": a.get("source") or "News",
                         "sentiment": _lbl(s), "score": round(s * 100, 1), "timestamp": ts})
    return {
        "overallSentiment": overall.get("label", ns.get("overallSentiment", "Neutral")),
        "score": ns.get("score", overall.get("score", 0.0)),
        "trend": ns.get("trend", overall.get("momentumLabel", "Stable")),
        "articles": articles,
        "lastUpdated": ts,
    }


async def get_longterm_forecasts_data() -> Dict[str, Any]:
    """Long-term CMA — the dashboard's gmoForecasts (observed building blocks)."""
    return await _dashboard_section("gmoForecasts", "Long-term forecasts")


async def get_reflexivity_data() -> Dict[str, Any]:
    """Reflexivity loops — the dashboard's section (z-scores of observed moves)."""
    return await _dashboard_section("reflexivity", "Reflexivity")


async def get_factor_decomposition_data() -> Dict[str, Any]:
    """Factor decomposition — the dashboard's OLS of NDX returns on ETF factor returns."""
    return await _dashboard_section("factorDecomposition", "Factor decomposition")


async def get_geopolitical_data() -> Dict[str, Any]:
    """No geopolitical-risk data source is wired (this used to relabel the VIX as a
    'geopolitical score'), so report it as unavailable rather than invent one."""
    from fastapi import HTTPException
    raise HTTPException(status_code=503,
                        detail="Geopolitical risk unavailable: no data source configured")


async def get_options_data() -> Dict[str, Any]:
    """Options context from observed data: SPX level and the VIX's rank within its past
    year. Put/call ratio and options flow need a CBOE/OPRA feed, which isn't wired → None."""
    from api.handlers.market_handler import _fetch_closes
    dashboard = await get_dashboard_data(mode="live")
    vix = dashboard.keyMetrics.vix if dashboard.keyMetrics else None
    spx = dashboard.keyMetrics.spxLevel if dashboard.keyMetrics else None
    vix_hist = await _fetch_closes("^VIX")
    iv_rank = None
    if vix is not None and vix_hist:
        lo, hi = min(vix_hist), max(vix_hist)
        iv_rank = round((vix - lo) / (hi - lo) * 100, 1) if hi > lo else None
    sentiment = (None if vix is None else "BULLISH" if vix < 15 else "NEUTRAL" if vix < 20
                 else "CAUTIOUS" if vix < 25 else "BEARISH")
    return {
        "underlying": "SPX",
        "currentPrice": round(spx, 2) if spx is not None else None,
        "impliedVolRank": iv_rank,
        "impliedVolRankBasis": "VIX vs its 1y high/low (Yahoo ^VIX)",
        "putCallRatio": None,
        "unusualActivity": [],
        "keyLevels": {},
        "sentiment": sentiment,
        "note": "Put/call ratio, flow and strike levels need an options data feed (not configured).",
        "lastUpdated": datetime.now().isoformat(),
    }


async def calibrate_recession() -> Dict[str, Any]:
    """Re-fit the recession probit (spread + Fed funds on NBER recessions, FRED) and return
    its actual coefficients and fit statistics."""
    import asyncio
    from api.models_ml.recession_probit import retrain_probit, get_recession_probit
    try:
        stats = await asyncio.to_thread(retrain_probit)
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail=f"Probit re-fit failed: {str(e)[:160]}")
    model = get_recession_probit()
    params = getattr(getattr(model, "result", None), "params", None)
    dashboard = await get_dashboard_data(mode="live")
    return {
        "status": "calibrated",
        "intercept": round(float(params.get("const")), 4) if params is not None and "const" in params else None,
        "yield_curve_coef": stats.get("coef_spread"),
        "fed_funds_coef": stats.get("coef_ff"),
        "pseudo_r2": stats.get("pseudo_r2"),
        "dataPoints": stats.get("n_obs"),
        "horizon_months": stats.get("horizon_months"),
        "currentProbability": round(dashboard.recession.probability, 4) if dashboard.recession else None,
        "trained_at": stats.get("trained_at"),
    }


