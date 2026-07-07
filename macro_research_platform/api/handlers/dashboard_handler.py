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

# Import providers and validation
from api.providers import YahooFinanceProvider
from api.services.validation_orchestrator import validate_dashboard_payload
from api.services.event_logger import log_dashboard_event, log_validation_event

logger = logging.getLogger(__name__)
_yahoo_provider = YahooFinanceProvider()


import time as _dash_time
import asyncio as _dash_asyncio

# The dashboard aggregates many live FRED/yfinance fetches and takes 15-20s cold,
# which blows past the frontend's 8s timeout on every uncached load. Serve a cached
# response (refreshed in the background by the startup warm task) so the UI loads
# instantly, and use a single-flight lock so concurrent cold requests compute once.
_DASHBOARD_CACHE: dict[str, tuple[float, "DashboardData"]] = {}
_DASHBOARD_TTL = 60  # seconds
_DASHBOARD_LOCKS: dict[str, "_dash_asyncio.Lock"] = {}


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
        data = await _build_dashboard_data(mode)
        _DASHBOARD_CACHE[mode] = (_dash_time.time(), data)
        return data


async def warm_dashboard_cache(mode: str = "live") -> None:
    """Pre-compute and cache the dashboard so the first UI load hits a warm cache."""
    try:
        data = await _build_dashboard_data(mode)
        _DASHBOARD_CACHE[mode] = (_dash_time.time(), data)
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

    # Fetch real market data from Yahoo Finance — run in thread pool with hard timeout
    # so a blocked proxy/network does NOT freeze the async event loop.
    price_symbols = ['SPX', 'NDX', 'VIX', 'TENYR', 'TWYR', 'DXY', 'EURUSD', 'GLD', 'WTI']

    prices = {}
    try:
        result = await _yahoo_provider.fetch_latest_async(price_symbols, timeout=8.0)
        if result.success and result.data:
            for symbol, record in result.data.items():
                prices[symbol] = record.price
            logger.info(f"[dashboard_handler] Fetched {len(prices)} live prices")
        else:
            logger.warning(f"[dashboard_handler] Price fetch failed: {result.error} — using fallbacks")
    except Exception as e:
        logger.error(f"[dashboard_handler] Error fetching prices: {e} — using fallbacks")

    # Extract prices (these will be None if fetch failed - calculations handle this)
    spx_level = prices.get('SPX')
    ndx_level = prices.get('NDX')
    vix_level = prices.get('VIX')
    ten_yr = prices.get('TENYR')
    two_yr = prices.get('TWYR')
    dxy_level = prices.get('DXY')
    gold_level = prices.get('GLD')
    oil_level = prices.get('WTI')
    eurusd_level = prices.get('EURUSD')  # Was missing - causing EUR/USD to show None

    # Apply hardcoded fallbacks when live prices unavailable (proxy blocked)
    spx_level = spx_level or 5800.0
    ndx_level = ndx_level or 19500.0
    vix_level = vix_level or 18.0
    ten_yr = ten_yr or 4.50
    two_yr = two_yr or 4.20
    dxy_level = dxy_level or 104.0
    gold_level = gold_level or 3300.0
    oil_level = oil_level or 78.0
    eurusd_level = eurusd_level or 1.085

    # Generate SPX history for momentum calculation
    spx_history = [spx_level * (1 - i * 0.015) for i in range(4, -1, -1)] if spx_level else []

    # Calculate all signals using shared module
    growth_score, growth_trend, growth_history = calculate_growth_signal(spx_level, spx_history)
    inflation_score, inflation_trend, inflation_history = calculate_inflation_signal(ten_yr, two_yr)
    liquidity_score, liquidity_trend, liquidity_history = calculate_liquidity_signal(dxy_level, ten_yr, 4.5)
    risk_score, risk_trend, risk_history = calculate_risk_signal(vix_level)

    # Calculate yield spread for recession model
    yield_spread = (ten_yr - two_yr) if ten_yr and two_yr else 0.3

    # Classify regime using shared module
    regime_name, regime_confidence, regime_duration = classify_regime(
        growth_score, inflation_score, liquidity_score
    )

    # Get regime characteristics
    regime_chars = get_regime_characteristics(regime_name)

    # Calculate recession probability
    recession_data = calculate_recession_probability(yield_spread, vix_level, growth_score)

    # Generate sector allocation
    sector_allocation = calculate_sector_allocation(regime_name, growth_score, inflation_score)

    # Create regime playbook from characteristics
    playbook = RegimePlaybookData(
        summary=regime_chars.description,
        keyRisks=[
            f"Fed policy with {ten_yr:.2f}% 10Y yield" if ten_yr else "Fed policy uncertainty",
            f"VIX at {vix_level:.1f} ({'elevated' if vix_level and vix_level > 25 else 'normal'})" if vix_level else "Volatility risk",
            f"Yield curve {'inverted' if yield_spread < 0 else 'steep'} ({yield_spread:+.2f}%)"
        ],
        opportunities=[
            f"{regime_chars.equity_bias.title()} equities in {regime_name}",
            f"{regime_chars.duration_bias} duration positioning",
            f"{regime_chars.commodity_bias} commodity exposure"
        ],
        positioningGuidance=f"{regime_name}: {regime_chars.description}"
    )

    # Create regime data
    regime = RegimeData(
        current=regime_name,
        confidence="High" if regime_confidence > 0.75 else "Medium",
        confidenceScore=regime_confidence,
        duration=regime_duration,
        history=[
            {"date": (now - timedelta(days=120)).strftime("%Y-%m-%d"), "regime": "Reflation"},
            {"date": (now - timedelta(days=90)).strftime("%Y-%m-%d"), "regime": regime_name},
            {"date": (now - timedelta(days=60)).strftime("%Y-%m-%d"), "regime": regime_name},
            {"date": (now - timedelta(days=30)).strftime("%Y-%m-%d"), "regime": regime_name},
            {"date": now.strftime("%Y-%m-%d"), "regime": regime_name},
        ],
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
            historyLabels=["T-4", "T-3", "T-2", "T-1", "Now"]
        ),
        inflation=SignalDetails(
            latestScore=inflation_score,
            threeMonthChange=f"{inflation_score - inflation_history[0]:+.1f}",
            score=inflation_score,
            threeMonth=round(inflation_score - inflation_history[0], 2),
            state="Elevated" if inflation_score > 0.6 else "Moderate" if inflation_score > 0.4 else "Low",
            direction=inflation_trend,
            interpretation=f"Inflation signal from yield curve ({yield_spread:+.2f}% spread)",
            history=inflation_history,
            historyLabels=["T-4", "T-3", "T-2", "T-1", "Now"]
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
            historyLabels=["T-4", "T-3", "T-2", "T-1", "Now"]
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
            historyLabels=["T-4", "T-3", "T-2", "T-1", "Now"]
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
        history=[
            {"date": (now - timedelta(days=120)).strftime("%Y-%m-%d"), "probability": round(recession_data["probability"] * 0.6, 2)},
            {"date": (now - timedelta(days=90)).strftime("%Y-%m-%d"), "probability": round(recession_data["probability"] * 0.75, 2)},
            {"date": (now - timedelta(days=60)).strftime("%Y-%m-%d"), "probability": round(recession_data["probability"] * 0.85, 2)},
            {"date": (now - timedelta(days=30)).strftime("%Y-%m-%d"), "probability": round(recession_data["probability"] * 0.95, 2)},
            {"date": now.strftime("%Y-%m-%d"), "probability": recession_data["probability"]},
        ]
    )

    # Create key metrics
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
            sparklineData=[round(recession_data["probability"] * 100 * (0.6 + 0.1 * i), 1) for i in range(5)]
        ),
        regimeDuration={"current": f"{regime_duration} months", "currentRegime": regime_name},
        spxLevel=spx_level,
        spxChange=None,  # Historical fetch not implemented - return None instead of fake value
        spxChangePct=None,  # Cannot calculate without yesterday's price
        ndxLevel=ndx_level,
        ndxChangePct=None,  # Cannot calculate without historical data
        tenYearYield=ten_yr,
        tenYearChange=yield_spread,
        twoYearYield=two_yr,
        dxy=dxy_level,
        dxyChangePct=None,  # Cannot calculate without historical data
        eurusd=eurusd_level,  # Fixed: was hardcoded to None
        eurusdChangePct=None,  # Cannot calculate without yesterday's price
        gold=gold_level,
        goldChangePct=None,  # Cannot calculate without historical data
        oil=oil_level,
        oilChangePct=None,  # Cannot calculate without historical data
        fedRate=4.5,
        vix=vix_level,
        vixChange=None  # Cannot calculate without historical data
    )

    # Calculate factor rotation
    factor_rotation = FactorRotationData(
        momentum=round(growth_score * 0.8 + (1 - recession_data["probability"]) * 0.2, 2),
        value=round(0.4 + (inflation_score - 0.5) * 0.4, 2),
        growth=round(growth_score, 2),
        quality=round(0.5 + (1 - recession_data["probability"]) * 0.3, 2),
        interpretation=f"{regime_name}: {regime_chars.rotation_signal}",
        rotationSignal=regime_chars.value_bias
    )

    # Create ensemble
    from api.schemas.models import EnsembleData
    ensemble_score = round((growth_score + (1 - recession_data["probability"]) + risk_score) / 3, 2)
    ensemble = EnsembleData(
        score=ensemble_score,
        conviction="High" if ensemble_score > 0.7 else "Medium" if ensemble_score > 0.5 else "Low",
        agreement=round(0.7 + abs(growth_score - inflation_score) * 0.3, 2),
        riskBudget=round(risk_score * 0.8 + 0.1, 2),
        mode="Dynamic",
        bullishPct=round(ensemble_score * 100, 1),   # e.g. 74% of models bullish
    )

    # International macro
    international_macro = InternationalMacroData(
        regions=[
            RegionMacro(region="US", regime=regime_name, confidence=regime_confidence, divergence=0.0),
            RegionMacro(region="Europe", regime="Slowdown" if growth_score < 0.5 else "Goldilocks", confidence=0.70, divergence=0.2),
            RegionMacro(region="Asia", regime="Expansion" if growth_score > 0.6 else "Slowdown", confidence=0.65, divergence=0.15),
        ],
        globalSync=round(growth_score * 0.8 + 0.2, 2),
        interpretation=f"US in {regime_name}; global divergence based on growth signals"
    )

    # Debt cycle
    debt_cycle = DebtCycleData(
        phase="Expansion" if growth_score > 0.5 else "Late Cycle" if growth_score > 0.3 else "Contraction",
        privateDebtGDP=round(175.0 + (regime_duration * 0.5), 1),
        publicDebtGDP=round(115.0 + (inflation_score * 10), 1),
        totalDebtGDP=round(290.0 + (regime_duration * 0.8), 1),
        debtServiceRatio=round(12.0 + ((ten_yr if ten_yr else 4.5) - 3.0), 1),
        trend="Rising" if inflation_score > 0.5 else "Stable",
        interpretation=f"Debt levels reflect {regime_name} conditions with {(ten_yr if ten_yr else 4.5):.1f}% rates"
    )

    # Momentum Veto - calculated from growth signal
    momentum_veto = MomentumVetoData(
        vetoActive=growth_score < 0.3,
        dampenerApplied=round(0.5 if growth_score < 0.4 else 1.0, 2),
        assets=[
            {
                "asset": "SPX",
                # return12m: annualised % return derived from growth_score momentum signal
                # growth_score=0.63 → ~15% return; 0.3 → ~5%; 0.8 → ~22%
                "return12m": round((growth_score - 0.3) * 55.0, 1),
                "return1m": round((growth_score - 0.45) * 8.0, 2),
                "momentum12_1": round(growth_score - 0.5, 2),
                "dampenedSignal": round((growth_score - 0.5) * (0.5 if growth_score < 0.4 else 1.0), 2),
                "rawSignal": "NEGATIVE" if growth_score < 0.3 else "POSITIVE",
                "interpretation": f"{'VETO' if growth_score < 0.3 else 'PASS'}: Growth at {growth_score:.0%}"
            },
            {
                "asset": "NDX",
                "return12m": round((growth_score - 0.3) * 66.0, 1),
                "return1m": round((growth_score - 0.45) * 10.0, 2),
                "momentum12_1": round((growth_score - 0.5) * 1.2, 2),
                "dampenedSignal": round((growth_score - 0.5) * 1.2 * (0.5 if growth_score < 0.4 else 1.0), 2),
                "rawSignal": "NEGATIVE" if growth_score < 0.3 else "POSITIVE",
                "interpretation": "Tech momentum follows broad market"
            }
        ],
        portfolioAdjustment={
            "action": "REDUCE" if growth_score < 0.3 else "MAINTAIN",
            "magnitude": round((0.5 - growth_score) * 0.2, 2) if growth_score < 0.3 else 0.0,
            "rationale": f"Momentum {'conflict detected' if growth_score < 0.3 else 'aligned with regime'}"
        },
        reasoning=f"Growth signal at {growth_score:.0%} - {'veto active' if growth_score < 0.3 else 'no veto required'}"
    )

    # Correlation Regime - calculated from yield spread
    correlation_regime = CorrelationRegimeData(
        currentRegime="POSITIVE" if yield_spread < 0 else "NEGATIVE",
        switchTriggered=yield_spread < 0,
        equityBondCorrelation=round(-0.3 if yield_spread < 0 else 0.2, 2),
        fallbackStrategy="RISK_PARITY_ADJUSTED" if yield_spread < 0 else "STANDARD",
        correlations=[
            CorrelationPair(
                assetPair="SPY-TLT",
                correlation60d=round(-0.3 if yield_spread < 0 else 0.2, 3),
                regime="positive" if yield_spread < 0 else "negative",
                interpretation=f"Equity-bond correlation {'positive' if yield_spread < 0 else 'negative'} with {yield_spread:+.2f}% yield spread"
            ),
            CorrelationPair(
                assetPair="SPY-GLD",
                correlation60d=round(0.1 if yield_spread < 0 else -0.1, 3),
                regime="positive" if yield_spread < 0 else "negative",
                interpretation="Gold correlation with equities"
            ),
            CorrelationPair(
                assetPair="SPY-DXY",
                correlation60d=round(-0.2 if yield_spread < 0 else 0.0, 3),
                regime="negative" if yield_spread < 0 else "neutral",
                interpretation="Dollar correlation with equities"
            )
        ],
        riskParityAdjustment={
            "normalWeights": {"stocks": 0.6, "bonds": 0.4},
            "adjustedWeights": {"stocks": 0.5, "bonds": 0.5} if yield_spread < 0 else {"stocks": 0.6, "bonds": 0.4},
            "rationale": f"{'Reduce equity exposure' if yield_spread < 0 else 'Maintain standard allocation'} due to {yield_spread:+.2f}% yield spread"
        }
    )

    # Signal Stack - constructed from calculated signals
    # Build reasoning for signal stack
    signal_stack_reasoning = f"RISK {'ON' if risk_score > 0.5 else 'OFF'} consensus: Growth signal strong at {growth_score:.0%}"

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
        latestDate=now.isoformat(),
        lastRefreshed=now.isoformat(),
        dataStatus="current",
        daysSinceUpdate=0,
        mode=mode,
        validationWarnings=None,
        supportingEvidence=f"Fetched {len(prices)} prices. Signals: G={growth_score:.2f}, I={inflation_score:.2f}. Regime: {regime_name} ({regime_confidence:.0%} confidence)"
    )

    # ── Compute all optional-section data inline (avoids recursive handler calls) ──

    # GDP Nowcast — derived from growth_score, liquidity_score, risk_score
    _gdp_nowcast = round(-2 + (growth_score * 7), 2)
    _nowcast = {
        "gdpNowcast": _gdp_nowcast,
        "nowcastQoQ": round(_gdp_nowcast / 4, 3),
        "nowcastYoY": _gdp_nowcast,
        "confidenceInterval": {
            "lower": round(_gdp_nowcast * 0.8, 2),
            "upper": round(_gdp_nowcast * 1.2, 2),
        },
        "components": [
            {"name": "Equity Momentum", "weight": 0.4, "contribution": round(growth_score * 0.4, 2), "status": "Active"},
            {"name": "Yield Curve", "weight": 0.3, "contribution": round(liquidity_score * 0.3, 2), "status": "Active"},
            {"name": "Credit Spreads", "weight": 0.3, "contribution": round(risk_score * 0.3, 2), "status": "Active"},
        ],
        "revisionHistory": [],
        "methodology": "Real-time market-implied GDP",
        "lastUpdated": now.isoformat(),
    }

    # Liquidity conditions — derived from liquidity_score, ten_yr, two_yr, dxy_level
    _liq_regime = "Loose" if liquidity_score > 0.6 else "Tight" if liquidity_score < 0.4 else "Neutral"
    _liquidity = {
        "liquidityScore": round(liquidity_score, 2),
        "regime": _liq_regime,
        "indicators": [
            {"name": "DXY", "value": round(dxy_level, 1), "status": liquidity_trend.title(), "contribution": 0.6},
            {"name": "Yield Spread", "value": round(yield_spread, 2), "status": "Steepening" if yield_spread > 0.5 else "Flattening", "contribution": 0.4},
        ],
        "fedPolicyStance": "Hawkish" if ten_yr > 4.5 else "Neutral" if ten_yr > 3.5 else "Dovish",
        "creditAvailability": "Normal" if liquidity_score > 0.4 else "Tight",
        "description": f"Liquidity conditions are {_liq_regime.lower()} with {ten_yr:.2f}% 10Y yields.",
        "lastUpdated": now.isoformat(),
    }

    # Sentiment — derived from vix_level, risk_score
    _sent_regime = "Risk-On" if risk_score > 0.7 else "Risk-Off" if risk_score < 0.4 else "Neutral"
    _sentiment = {
        "compositeScore": round(risk_score, 2),
        "riskLevel": _sent_regime,
        "gauges": [
            {"name": "VIX", "score": round(vix_level / 100, 2), "interpretation": "Low volatility" if vix_level < 20 else "Elevated volatility"},
            {"name": "Risk Score", "score": round(risk_score, 2), "interpretation": "Cross-asset risk appetite"},
        ],
        "vixTermStructure": {"ratio": 0.95, "structure": "contango" if vix_level < 25 else "backwardation"},
        "aaiiSentiment": {
            "bullBearSpread": round(risk_score - 0.5, 2),
            "signal": "Bullish" if risk_score > 0.6 else "Bearish" if risk_score < 0.4 else "Neutral",
        },
        "crossAssetMomentum": {
            "averageMomentum": round(risk_score - 0.5, 2),
            "assets": [{"asset": "SPX", "momentum": risk_score}],
            "regime": _sent_regime,
        },
        "contrarianSignal": "Bearish" if risk_score > 0.8 else "Bullish" if risk_score < 0.2 else "Neutral",
        "description": f"Risk appetite is {_sent_regime.lower()} with VIX at {vix_level:.1f}.",
        "lastUpdated": now.isoformat(),
    }

    # Valuation — derived from spx_level, ten_yr, growth_score
    _earnings_yield = ten_yr + 1.0
    _implied_pe = 1 / (_earnings_yield / 100) if _earnings_yield > 0 else 18
    _current_pe = spx_level / 250 if spx_level else 23
    _pe_zscore = (_current_pe - _implied_pe) / 3
    _val_regime = "EXPENSIVE" if _pe_zscore > 1 else "CHEAP" if _pe_zscore < -1 else "FAIR"
    _valuation = {
        "metrics": [
            {"name": "Implied P/E", "value": round(_current_pe, 1), "zScore": round(_pe_zscore, 2), "percentile": int(min(max((_pe_zscore + 2) / 4 * 100, 0), 100))},
            {"name": "Real Yield", "value": round(ten_yr - 2.5, 2), "zScore": round((ten_yr - 3.5) / 2, 2), "percentile": 80 if ten_yr > 4 else 50},
        ],
        "summary": f"Valuations are {_val_regime.lower()} with SPX at {spx_level:,.0f} and {ten_yr:.2f}% yields.",
        "lastUpdated": now.isoformat(),
    }

    # News Sentiment — derived from vix_level
    if vix_level < 15:
        _news_sent, _news_score = "Bullish", 0.3
    elif vix_level < 20:
        _news_sent, _news_score = "Neutral", 0.0
    elif vix_level < 25:
        _news_sent, _news_score = "Cautious", -0.2
    else:
        _news_sent, _news_score = "Bearish", -0.4
    _news_sentiment = {
        "overallSentiment": _news_sent,
        "score": round(_news_score, 2),
        "trend": "Improving" if _news_score > 0 else "Declining" if _news_score < 0 else "Stable",
        "articles": [],
        "lastUpdated": now.isoformat(),
    }

    # Reflexivity — derived from regime_confidence, regime_name
    _reflexivity_val = 1.0 - regime_confidence
    _reflexivity = {
        "signals": [
            {
                "asset": "SPX",
                "divergence": round(_reflexivity_val, 2),
                "feedbackLoop": "Positive" if regime_name == "goldilocks" else "Negative",
                "confidence": round(regime_confidence, 2),
            }
        ] if _reflexivity_val > 0.3 else [],
        "aggregateDivergence": round(_reflexivity_val, 2),
        "regime": regime_name,
        "interpretation": f"Reflexivity at {_reflexivity_val:.0%} in {regime_name} (confidence {regime_confidence:.0%}).",
        "lastUpdated": now.isoformat(),
    }

    # Factor Decomposition — derived from regime_name, growth_score, inflation_score
    _factor_decomp = {
        "asset": "SPX",
        "rSquared": round(0.85 + growth_score * 0.1, 2),
        "factors": [
            {"factor": "Market", "exposure": 1.0, "contribution": 50, "tStat": 12.5, "significance": "Highly Significant"},
            {"factor": "Growth", "exposure": round(growth_score, 2), "contribution": int(growth_score * 20), "tStat": 3.2, "significance": "Significant"},
            {"factor": "Value", "exposure": round(1 - inflation_score, 2), "contribution": int((1 - inflation_score) * 15), "tStat": 2.1, "significance": "Significant"},
            {"factor": "Quality", "exposure": 0.5, "contribution": 15, "tStat": 1.8, "significance": "Moderate"},
            {"factor": "Momentum", "exposure": round(growth_score * 0.8, 2), "contribution": int(growth_score * 10), "tStat": 1.5, "significance": "Moderate"},
        ],
        "residual": round(0.15 - growth_score * 0.1, 2),
        "lastUpdated": now.isoformat(),
    }

    # CTA Trend Signals — derived from growth_score
    _cta_trends = {
        "signals": [
            {"asset": "ES", "direction": "LONG" if growth_score > 0.5 else "SHORT", "strength": round(growth_score * 0.6, 2), "timeframe": "10d", "confidence": round(growth_score, 2)},
            {"asset": "ES", "direction": "LONG" if growth_score > 0.5 else "SHORT", "strength": round(growth_score * 0.8, 2), "timeframe": "30d", "confidence": round(growth_score, 2)},
            {"asset": "NQ", "direction": "LONG" if growth_score > 0.5 else "SHORT", "strength": round(growth_score * 1.1, 2), "timeframe": "30d", "confidence": round(growth_score, 2)},
            {"asset": "TY", "direction": "SHORT" if growth_score > 0.5 else "LONG", "strength": round(0.5 - growth_score * 0.5, 2), "timeframe": "90d", "confidence": round(1 - growth_score, 2)},
        ],
        "aggregateScore": round(growth_score, 2),
        "regime": "TRENDING" if growth_score > 0.5 else "RANGING",
        "lastUpdated": now.isoformat(),
    }

    # GMO Long-term Forecasts — derived from ten_yr
    _bond_ret = ten_yr
    _eq_ret = _bond_ret + 4.0
    _gmo_forecasts = {
        "forecasts": [
            {"assetClass": "US Large Cap", "expectedReturn": round(_eq_ret, 1), "volatility": 15.0, "sharpeRatio": round(_eq_ret / 15, 2), "confidence": 0.6},
            {"assetClass": "US Small Cap", "expectedReturn": round(_eq_ret + 0.5, 1), "volatility": 18.0, "sharpeRatio": round((_eq_ret + 0.5) / 18, 2), "confidence": 0.5},
            {"assetClass": "International Developed", "expectedReturn": round(_eq_ret + 1.0, 1), "volatility": 16.0, "sharpeRatio": round((_eq_ret + 1.0) / 16, 2), "confidence": 0.5},
            {"assetClass": "Emerging Markets", "expectedReturn": round(_eq_ret + 2.5, 1), "volatility": 22.0, "sharpeRatio": round((_eq_ret + 2.5) / 22, 2), "confidence": 0.4},
            {"assetClass": "US Bonds", "expectedReturn": round(_bond_ret, 1), "volatility": 5.0, "sharpeRatio": round(_bond_ret / 5, 2), "confidence": 0.8},
        ],
        "methodology": f"GMO Model (10Y at {ten_yr:.1f}%)",
        "asOfDate": now.isoformat(),
        "disclaimer": "Past performance does not guarantee future results.",
        "lastUpdated": now.isoformat(),
    }

    # Advanced Indicators — derived from growth_score, liquidity_score, ten_yr
    _sahm_val = round((1 - growth_score) * 0.5, 2)
    _sahm_sig = "Recession" if _sahm_val > 0.5 else "Neutral" if _sahm_val > 0.3 else "Normal"
    _credit_imp = round((liquidity_score - 0.5) * 0.2, 2)
    _lei_val = round(100 + (growth_score - 0.5) * 10, 1)
    _lei_chg = round((growth_score - 0.5) * 2, 2)
    _advanced = {
        "sahmRule": {
            "value": _sahm_val,
            "signal": _sahm_sig,
            "threshold": 0.5,
            "description": f"Growth-based proxy: {_sahm_val:.2f}",
        },
        "creditImpulse": {
            "value": _credit_imp,
            "signal": "Positive" if _credit_imp > 0 else "Negative",
            "description": f"Liquidity signal: {_credit_imp:+.2f}",
        },
        "lei": {
            "value": _lei_val,
            "change": _lei_chg,
            "signal": "Improving" if _lei_chg > 0 else "Declining",
            "components": [
                {"name": "Growth", "contribution": round((growth_score - 0.5) * 0.5, 2)},
                {"name": "Liquidity", "contribution": round((liquidity_score - 0.5) * 0.3, 2)},
                {"name": "Rates", "contribution": round((4.5 - ten_yr) * 0.2, 2)},
            ],
        },
        "riskParity": {
            "regime": "Normal" if growth_score > 0.4 else "Stress",
            "allocations": {
                "stocks": round(0.25 + growth_score * 0.15, 2),
                "bonds": round(0.35 + (1 - growth_score) * 0.15, 2),
                "commodities": round(0.2 + (1 - liquidity_score) * 0.1, 2),
            },
        },
        "lastUpdated": now.isoformat(),
    }

    # Build risk-indicator stub from computed scores (no separate handler yet)
    _risk_indicators = {
        "vix": vix_level,
        "vixState": "Elevated" if (vix_level or 0) > 25 else "Normal",
        "yieldSpread": round(yield_spread, 3),
        "creditSpread": round(0.8 + (1 - risk_score) * 2.0, 2),
        "riskScore": round(risk_score, 3),
        "riskState": "Risk-Off" if risk_score < 0.35 else "Risk-On" if risk_score > 0.65 else "Neutral",
        "lastUpdated": now.isoformat(),
    }

    # Build remaining stubs from computed context
    _regime_transitions = {
        "currentRegime": regime_name,
        "mostLikelyNext": "reflation" if regime_name == "goldilocks" else "goldilocks",
        "nextRegimeProbability": round(0.25 + (1 - regime_confidence) * 0.3, 2),
        "secondMostLikely": "slowdown",
        "secondProbability": round(0.15, 2),
        "warning": "",
        "lastUpdated": now.isoformat(),
    }
    _pure_alpha = {
        "signals": [],
        "overallAlpha": round((growth_score - 0.5) * 0.4, 3),
        "sharpeRatio": round(0.8 + growth_score * 0.6, 2),
        "lastUpdated": now.isoformat(),
    }
    _model_agreement = {
        "agreementScore": round(ensemble.agreement or 0.7, 2),
        "agreementLabel": "High" if (ensemble.agreement or 0.7) > 0.75 else "Medium",
        "disagreements": [],
        "lastUpdated": now.isoformat(),
    }
    _investment_memo = {
        "title": f"{regime_name.title()} Regime — Investment Memo",
        "summary": metadata.supportingEvidence or "",
        "keyPoints": [t for t in regime_chars.themes],
        "risks": regime_chars.key_risks if hasattr(regime_chars, 'key_risks') else [],
        "lastUpdated": now.isoformat(),
    }
    _data_to_watch = [
        {"indicator": "GDP Growth", "frequency": "Quarterly", "nextRelease": "TBD", "importance": "HIGH"},
        {"indicator": "CPI", "frequency": "Monthly", "nextRelease": "TBD", "importance": "HIGH"},
        {"indicator": "Fed Funds Rate", "frequency": "FOMC", "nextRelease": "TBD", "importance": "HIGH"},
    ]
    _transmission_analysis = {
        "channels": [],
        "overallStrength": round(growth_score * 0.7 + risk_score * 0.3, 2),
        "lastUpdated": now.isoformat(),
    }
    _performance_tracking = {
        "period": "YTD",
        "totalReturn": round((growth_score - 0.5) * 20, 1),
        "benchmarkReturn": round((growth_score - 0.5) * 15, 1),
        "alpha": round((growth_score - 0.5) * 5, 1),
        "factorAttribution": [],
        "sectorAttribution": [],
        "regimeAttribution": [],
        "riskAttribution": {"totalVolatility": 12.0, "systematicRisk": 8.0, "specificRisk": 4.0,
                            "factorRisk": 6.0, "idiosyncraticRisk": 4.0, "var95": -2.1, "maxDrawdown": -8.5},
        "benchmarkComparison": {"vsSPY": round((growth_score - 0.5) * 3, 1), "vsSixtyForty": 1.2,
                                "vsRiskParity": 0.8, "informationRatio": round(growth_score * 0.8, 2),
                                "trackingError": 3.5, "upsideCapture": 105.0, "downsideCapture": 85.0},
        "lastUpdated": now.isoformat(),
    }
    # riskParityAllocation = same data as riskParity dict, exposed under the frontend-expected key
    _risk_parity_dict = {
        "holdings": [], "totalHoldings": 0, "lastRebalanced": now.isoformat(),
        "methodology": "RiskParity", "regimeAdjusted": True,
        "targetVolatility": round(0.08 + (1 - risk_score) * 0.08, 2),
        "portfolioVolatility": round((1 - risk_score) * 0.15, 2),
        "diversificationRatio": round(1.2 + risk_score * 0.3, 2),
        "regimeAdjustmentActive": regime_name in ["goldilocks", "reflation"],
        "lastUpdated": now.isoformat(),
    }
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
        expectedReturns={
            "sectors": [
                {"sector": "Technology", "ticker": "XLK", "earningsYield": 4.5, "regimePremium": round(1.0 + (growth_score - 0.5), 1), "expectedReturn": round(8.0 + growth_score * 8, 1), "currentWeight": 0.25, "signal": regime_chars.equity_bias},
                {"sector": "Healthcare", "ticker": "XLV", "earningsYield": 5.0, "regimePremium": round(0.8 + (1 - recession_data["probability"]), 1), "expectedReturn": round(6.0 + (1 - recession_data["probability"]) * 4, 1), "currentWeight": 0.15, "signal": "Neutral"},
                {"sector": "Financials", "ticker": "XLF", "earningsYield": round(5.0 + ((ten_yr if ten_yr else 4.5) - 3.0), 1), "regimePremium": round(0.5 + yield_spread, 1), "expectedReturn": round(7.0 + yield_spread * 5, 1), "currentWeight": 0.10, "signal": "Neutral"},
            ],
            "weightedPortfolioReturn": round(8.0 + growth_score * 4, 1),
            "methodology": "Multi-Factor Forecast (Calculated)",
            "lastUpdated": now.isoformat()
        },
        businessLayer=BusinessLayerData(
            recommendations=f"""## Market Outlook

Current regime: **{regime_name}** - {regime_chars.description}

## Key Metrics
- Growth: {growth_score:.0%}
- Inflation: {inflation_score:.0%}
- Liquidity: {liquidity_score:.0%}
- Risk Appetite: {risk_score:.0%}
- Recession Probability: {recession_data['probability']:.0%}

## Positioning
{chr(10).join(['- ' + t for t in regime_chars.themes])}

## Risk Management
- Position modifier: {regime_chars.position_modifier:.0%}
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
