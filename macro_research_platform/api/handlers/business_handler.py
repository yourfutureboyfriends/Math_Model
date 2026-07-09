"""Business handler - business logic for business layer endpoints."""
from typing import Dict, Any, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


async def get_trade_ideas_data() -> Dict[str, Any]:
    """Trade ideas endpoint with real calculated data from regime."""
    logger.info("Fetching trade ideas with calculated data")

    # Get real calculated dashboard data
    from api.handlers.dashboard_handler import get_dashboard_data
    dashboard = await get_dashboard_data(mode="live")

    regime = dashboard.regime.current or "goldilocks"
    spx_level = dashboard.keyMetrics.spxLevel if dashboard.keyMetrics else None

    # SPY ETF price is approximately SPX index / 10
    spy_price = round((spx_level / 10) if spx_level else 580.0, 2)

    # Generate trade ideas based on actual regime and prices
    if regime == "expansion":
        ideas = [
            {
                "asset": "SPY",
                "direction": "LONG",
                "entry": spy_price,
                "stop": round(spy_price * 0.95, 2),
                "target": round(spy_price * 1.05, 2),
                "conviction": "HIGH",
                "rationale": f"Expansion regime - overweight equities. SPX at {(spx_level or 5800):,.0f}, SPY at ${spy_price}."
            },
            {
                "asset": "XLF",
                "direction": "LONG",
                "entry": 42.0,
                "stop": 39.0,
                "target": 46.0,
                "conviction": "MEDIUM",
                "rationale": "Financials benefit from rising rates in expansion"
            }
        ]
    elif regime == "stagflation":
        ideas = [
            {
                "asset": "GLD",
                "direction": "LONG",
                "entry": 195.0,
                "stop": 188.0,
                "target": 205.0,
                "conviction": "HIGH",
                "rationale": "Stagflation hedge - Gold benefits from elevated inflation"
            },
            {
                "asset": "TLT",
                "direction": "SHORT",
                "entry": 92.0,
                "stop": 96.0,
                "target": 85.0,
                "conviction": "MEDIUM",
                "rationale": "Inflation pressure on bonds - real yields elevated"
            }
        ]
    else:
        # Default ideas for other regimes
        ideas = [
            {
                "asset": "SPY",
                "direction": "NEUTRAL",
                "entry": spy_price,
                "stop": round(spy_price * 0.93, 2),
                "target": round(spy_price * 1.05, 2),
                "conviction": "LOW",
                "rationale": f"Mixed signals in {regime} regime - await clarity"
            }
        ]

    return {
        "ideas": ideas,
        "count": len(ideas),
        "lastUpdated": datetime.now().isoformat(),
    }


async def get_morning_brief_data() -> Dict[str, Any]:
    """Morning brief endpoint with real calculated data from dashboard."""
    logger.info("Fetching morning brief with calculated data")
    now = datetime.now()

    # Get real calculated dashboard data
    from api.handlers.dashboard_handler import get_dashboard_data
    dashboard = await get_dashboard_data(mode="live")

    # Extract regime info
    regime = dashboard.regime.current or "goldilocks"
    confidence = dashboard.regime.confidenceScore or 0.75
    duration = dashboard.regime.duration or 1

    # Get scores
    growth = dashboard.scores.growth if dashboard.scores else 50
    inflation = dashboard.scores.inflation if dashboard.scores else 30
    risk = dashboard.scores.risk if dashboard.scores else 50

    # Get prices — SPX is the index level (~5800), SPY ETF is ~1/10th of SPX (~580)
    spx = (dashboard.keyMetrics.spxLevel or 5800) if dashboard.keyMetrics else 5800
    spy_price = round(spx / 10, 2)   # SPY ETF ≈ SPX / 10
    qqq_price = round(spx / 12, 2)   # QQQ ETF ≈ SPX / 12 (approx)
    vix = (dashboard.keyMetrics.vix or 18.0) if dashboard.keyMetrics else 18.0
    ten_yr = (dashboard.keyMetrics.tenYearYield or 4.5) if dashboard.keyMetrics else 4.5

    # Generate priorities based on actual market data
    priorities = []
    if ten_yr and ten_yr > 4.5:
        priorities.append("Monitor Treasury yields — elevated rates pressure valuations")
    if vix and vix > 20:
        priorities.append("Watch volatility — VIX elevated above 20")
    if growth < 40:
        priorities.append("Growth slowing — defensively position portfolios")
    if inflation > 60:
        priorities.append("Inflation pressure — watch Fed policy signals")

    # Always ensure at least 3 priorities with regime-specific content
    if len(priorities) < 3:
        regime_priorities = {
            "expansion": [
                f"{regime.title()} regime — overweight equities and cyclicals",
                "Monitor yield curve for late-cycle signals",
                "Track credit spreads for stress indicators",
            ],
            "goldilocks": [
                "Goldilocks conditions persist — maintain growth positioning",
                "Monitor yield curve for inversion signals",
                "Track credit spreads for stress indicators",
            ],
            "reflation": [
                "Reflation regime — favour commodities and TIPS",
                "Watch breakeven inflation for rate expectations",
                "Energy and materials outperformance likely",
            ],
            "stagflation": [
                "Stagflation risk — reduce duration and growth exposure",
                "Hard assets and short-duration bonds preferred",
                "Monitor Fed response to stagflation signals",
            ],
            "slowdown": [
                "Slowdown confirmed — shift to defensive positioning",
                "Flight-to-quality bonds favoured",
                "Reduce cyclical and high-beta exposure",
            ],
        }
        defaults = regime_priorities.get(regime, regime_priorities["expansion"])
        for p in defaults:
            if len(priorities) >= 3:
                break
            if p not in priorities:
                priorities.append(p)

    # Generate risks based on actual signals
    risks = []
    if inflation > 50:
        risks.append(f"Inflation elevated at {inflation:.0f}% signal")
    if risk < 40:
        risks.append(f"Risk appetite low — VIX at {vix:.1f}")
    if ten_yr and ten_yr > 4.5:
        risks.append(f"Rates at {ten_yr:.2f}% — duration risk elevated")

    if len(risks) < 3:
        risks.extend([
            "Geopolitical tensions — energy price volatility",
            "Credit stress — HY spreads near 400bps",
            "Dollar strength — EM pressure",
        ][:3 - len(risks)])

    # Generate conviction trades based on regime — use ETF prices not index levels
    trades = []
    if regime in ("goldilocks", "expansion"):
        trades.append({"ticker": "SPY", "direction": "LONG", "conviction": "HIGH",
                       "thesis": f"{regime.title()} regime — overweight equities",
                       "entry": spy_price, "stop": round(spy_price * 0.95, 2), "target": round(spy_price * 1.08, 2)})
        trades.append({"ticker": "QQQ", "direction": "LONG", "conviction": "MEDIUM",
                       "thesis": "Tech momentum in growth regime",
                       "entry": qqq_price, "stop": round(qqq_price * 0.94, 2), "target": round(qqq_price * 1.10, 2)})
    elif regime == "stagflation":
        trades.append({"ticker": "GLD", "direction": "LONG", "conviction": "HIGH",
                       "thesis": "Stagflation hedge via gold",
                       "entry": 330.0, "stop": 315.0, "target": 355.0})
        trades.append({"ticker": "TLT", "direction": "SHORT", "conviction": "MEDIUM",
                       "thesis": "Rates pressure bonds in stagflation",
                       "entry": 92.0, "stop": 97.0, "target": 85.0})
    elif regime == "slowdown":
        trades.append({"ticker": "TLT", "direction": "LONG", "conviction": "HIGH",
                       "thesis": "Flight to quality in slowdown",
                       "entry": 92.0, "stop": 89.0, "target": 100.0})
        trades.append({"ticker": "XLU", "direction": "LONG", "conviction": "MEDIUM",
                       "thesis": "Defensive utilities in slowdown",
                       "entry": 75.0, "stop": 72.0, "target": 82.0})
    elif regime == "reflation":
        trades.append({"ticker": "GLD", "direction": "LONG", "conviction": "HIGH",
                       "thesis": "Reflation — real assets outperform",
                       "entry": 330.0, "stop": 318.0, "target": 350.0})
        trades.append({"ticker": "SPY", "direction": "LONG", "conviction": "MEDIUM",
                       "thesis": "Equities benefit from nominal growth",
                       "entry": spy_price, "stop": round(spy_price * 0.95, 2), "target": round(spy_price * 1.06, 2)})
    else:
        trades.append({"ticker": "SPY", "direction": "LONG", "conviction": "MEDIUM",
                       "thesis": f"{regime.title()} regime — broad equity exposure",
                       "entry": spy_price, "stop": round(spy_price * 0.95, 2), "target": round(spy_price * 1.05, 2)})
        trades.append({"ticker": "GLD", "direction": "LONG", "conviction": "MEDIUM",
                       "thesis": "Diversification hedge",
                       "entry": 330.0, "stop": 318.0, "target": 348.0})

    # Calculate position modifier based on risk score
    position_modifier = risk / 100 if risk else 1.0
    model_caution = confidence < 0.6 or risk < 40

    # Generate summary based on real data
    summary = f"{regime.title()} regime with growth at {growth:.0f}%, inflation at {inflation:.0f}%."
    if spx:
        summary += f" SPX at {spx:,.0f}."
    if vix:
        summary += f" VIX {vix:.1f}."

    return {
        "date": now.strftime("%Y-%m-%d"),
        "summary": summary,
        "keyEvents": priorities[:3],
        "tradeIdeas": [
            {
                "asset": t["ticker"],
                "direction": t["direction"],
                "entry": t["entry"],
                "stop": t["stop"],
                "target": t["target"],
                "conviction": t["conviction"],
                "rationale": t["thesis"]
            } for t in trades
        ],
        # Legacy fields for backwards compatibility
        "regime": regime.title(),
        "duration_months": duration,
        "confidence": confidence,
        "headline": f"Macro regime: {regime.title()} - Growth {growth:.0f}%, Inflation {inflation:.0f}%",
        "priorities": [{"type": "signal", "priority": i+1, "title": p, "implication": "Action required"} for i, p in enumerate(priorities[:3])],
        "risks": [{"type": "market", "text": r, "severity": "WARNING" if i == 0 else "INFO"} for i, r in enumerate(risks[:3])],
        "conviction_trades": trades,
        "position_modifier": round(position_modifier, 2),
        "model_caution": model_caution,
        "lastUpdated": now.isoformat(),
    }


async def get_recommendations_data() -> Dict[str, Any]:
    """Get latest investment recommendations from real market data."""
    logger.info("Fetching recommendations with real data")

    # Get real dashboard data
    from api.handlers.dashboard_handler import get_dashboard_data
    dashboard = await get_dashboard_data(mode="live")

    regime = dashboard.regime.current or "goldilocks"
    confidence = dashboard.regime.confidenceScore or 0.75
    growth = (dashboard.scores.growth / 100) if dashboard.scores else 0.5
    inflation = (dashboard.scores.inflation / 100) if dashboard.scores else 0.3
    risk = (dashboard.scores.risk / 100) if dashboard.scores else 0.5
    liquidity = (dashboard.scores.liquidity / 100) if dashboard.scores else 0.5
    ten_yr = (dashboard.keyMetrics.tenYearYield or 4.5) if dashboard.keyMetrics else 4.5
    vix = (dashboard.keyMetrics.vix or 18.0) if dashboard.keyMetrics else 18.0
    rec_prob = dashboard.recession.probability if dashboard.recession else 0.15

    # Calculate regime from signals if not set (backup classification)
    if not regime or regime == "unknown":
        if growth > 0.6 and inflation < 0.4:
            regime = "goldilocks"
        elif growth > 0.5 and inflation > 0.5:
            regime = "reflation"
        elif growth < 0.4 and inflation > 0.5:
            regime = "stagflation"
        elif growth < 0.4 and inflation < 0.5:
            regime = "slowdown"
        elif liquidity < 0.3:
            regime = "contraction"
        else:
            regime = "goldilocks"

    # Determine overall position based on real risk metrics
    if risk > 0.7 and rec_prob < 0.2:
        overall_position = "HIGH RISK"
    elif risk > 0.5 and rec_prob < 0.3:
        overall_position = "MODERATE RISK"
    elif rec_prob > 0.4 or vix > 30:
        overall_position = "DEFENSIVE"
    else:
        overall_position = "BALANCED"

    # Generate themes based on calculated regime
    themes = []
    regime_actions = {
        "goldilocks": [
            f"Growth at {growth:.0%} supports risk assets",
            f"Inflation stable at {inflation:.0%} - quality over value",
            "Overweight equities, neutral duration"
        ],
        "reflation": [
            f"Strong growth ({growth:.0%}) with rising inflation ({inflation:.0%})",
            "Cyclicals outperform - value over quality",
            "Underweight duration, overweight commodities"
        ],
        "stagflation": [
            f"Slowing growth ({growth:.0%}) with high inflation ({inflation:.0%})",
            "Commodity exposure as inflation hedge",
            "Quality defensives, avoid duration risk"
        ],
        "slowdown": [
            f"Decelerating growth ({growth:.0%}) with cooling inflation",
            "Defensive positioning - quality and low vol",
            "Flight to quality, overweight duration"
        ],
        "contraction": [
            f"Tight liquidity ({liquidity:.0%}) with elevated recession risk ({rec_prob:.0%})",
            "Capital preservation mode",
            "Underweight risk assets, maximum duration"
        ]
    }

    # Add regime-specific themes
    if regime in regime_actions:
        themes.extend(regime_actions[regime][:2])  # Top 2 themes
    else:
        themes.append(f"Mixed signals - growth {growth:.0%}, inflation {inflation:.0%}")

    # Add rate-based theme if applicable
    if ten_yr and ten_yr > 4.5:
        themes.append(f"Elevated rates at {ten_yr:.2f}% - manage duration exposure")
    elif ten_yr and ten_yr < 3.0:
        themes.append(f"Low rates at {ten_yr:.2f}% - favor duration and growth")

    # Add VIX-based theme
    if vix > 25:
        themes.append(f"Elevated volatility (VIX {vix:.1f}) - reduce position sizes")

    # Calculate expected returns from real signals
    # Equity ERP = base 4% adjusted for growth and recession risk
    equity_erp = 4.0 + (growth - 0.5) * 4 - rec_prob * 3
    equity_return = (ten_yr if ten_yr else 4.5) + equity_erp

    # Bond returns = yield adjusted for rate direction
    rate_direction = -0.5 if ten_yr and ten_yr > 4.5 else 0.5  # Mean reversion assumption
    bond_return = (ten_yr if ten_yr else 4.5) + rate_direction

    # Commodity returns = inflation signal adjusted
    commodity_return = 5.0 + (inflation - 0.4) * 8

    # Calculate position sizing dynamically based on signals
    # SPY: Higher when growth is strong and recession risk is low
    spy_target = max(0.10, min(0.35, 0.15 + (growth - 0.3) * 0.2 - rec_prob * 0.15))

    # QQQ: Higher when growth is strong and liquidity is loose
    qqq_target = max(0.05, min(0.25, 0.08 + (growth - 0.3) * 0.15 + (liquidity - 0.5) * 0.05))

    # TLT: Higher when rates are expected to fall (high current rates + low growth)
    tlt_target = max(0.05, min(0.30, 0.10 + ((ten_yr - 3.5) * 0.03 if ten_yr else 0) - (growth - 0.5) * 0.05))

    # GLD: Higher when inflation is elevated or recession risk is high
    gld_target = max(0.03, min(0.20, 0.05 + inflation * 0.10 + rec_prob * 0.10))

    # Calculate conviction levels from signal strength
    def get_conviction(value, threshold_high=0.7, threshold_low=0.4):
        if value > threshold_high:
            return "High"
        elif value > threshold_low:
            return "Medium"
        return "Low"

    return {
        "summary": {
            "regime": regime.title(),
            "conviction": get_conviction(confidence, 0.75, 0.6),
            "overall_position": overall_position,
            "key_themes": themes,
            "risk_assessment": f"VIX {vix:.1f}, Recession {rec_prob:.0%}, Risk Score {risk:.0%}"
        },
        "expected_returns": [
            {"asset": "US Equities", "return_1y": round(equity_return, 1), "confidence": get_conviction(growth, 0.65, 0.45)},
            {"asset": "International", "return_1y": round(equity_return + 0.5, 1), "confidence": "Medium"},
            {"asset": "Bonds", "return_1y": round(bond_return, 1), "confidence": "High"},
            {"asset": "Commodities", "return_1y": round(commodity_return, 1), "confidence": get_conviction(inflation, 0.6, 0.4)},
            {"asset": "Gold", "return_1y": round(4.0 + rec_prob * 3 + inflation * 2, 1), "confidence": get_conviction(rec_prob + inflation * 0.5, 0.5, 0.3)},
        ],
        "position_sizing": [
            {"asset": "SPY", "target": round(spy_target, 2), "range": f"{int(spy_target*100-5)}-{int(spy_target*100+5)}%", "conviction": get_conviction(growth, 0.65, 0.45)},
            {"asset": "QQQ", "target": round(qqq_target, 2), "range": f"{int(qqq_target*100-5)}-{int(qqq_target*100+5)}%", "conviction": get_conviction(growth * liquidity, 0.45, 0.25)},
            {"asset": "TLT", "target": round(tlt_target, 2), "range": "5-20%", "conviction": get_conviction(1 - growth + (ten_yr - 4.0) * 0.2 if ten_yr else 0.5, 0.6, 0.4)},
            {"asset": "GLD", "target": round(gld_target, 2), "range": f"{int(gld_target*100-2)}-{int(gld_target*100+5)}%", "conviction": get_conviction(inflation + rec_prob * 0.5, 0.6, 0.4)},
            {"asset": "VIX Hedge", "target": round(0.02 + rec_prob * 0.05, 2), "range": "2-7%", "conviction": get_conviction(rec_prob + (vix - 20) * 0.01, 0.4, 0.2)},
        ],
        "signal_scorecard": [
            {"signal": "Recession Risk", "value": f"{rec_prob:.0%}", "status": "Red" if rec_prob > 0.35 else "Yellow" if rec_prob > 0.2 else "Green"},
            {"signal": "Regime", "value": regime.title(), "status": "Green" if regime in ["goldilocks", "reflation"] else "Yellow" if regime == "slowdown" else "Red"},
            {"signal": "Growth Momentum", "value": f"{growth:.0%}", "status": "Green" if growth > 0.6 else "Yellow" if growth > 0.4 else "Red"},
            {"signal": "Inflation Pressure", "value": f"{inflation:.0%}", "status": "Red" if inflation > 0.6 else "Yellow" if inflation > 0.45 else "Green"},
            {"signal": "Liquidity", "value": f"{liquidity:.0%}", "status": "Green" if liquidity > 0.6 else "Yellow" if liquidity > 0.4 else "Red"},
            {"signal": "Risk Appetite", "value": f"{risk:.0%}", "status": "Green" if risk > 0.6 else "Yellow" if risk > 0.4 else "Red"},
            {"signal": "Volatility", "value": f"VIX {vix:.1f}", "status": "Green" if vix < 20 else "Yellow" if vix < 25 else "Red"},
        ],
        "timestamp": datetime.now().isoformat(),
    }


async def get_decision_log_data(limit: int = 50) -> Dict[str, Any]:
    """Get decision log from live regime and signal data."""
    logger.info(f"Fetching decision log (limit={limit})")
    from api.handlers.dashboard_handler import get_dashboard_data
    from datetime import timedelta
    dashboard = await get_dashboard_data(mode="live")
    now = datetime.now()

    regime = (dashboard.regime.current or "Goldilocks").title() if dashboard.regime else "Goldilocks"
    rec_prob = dashboard.recession.probability if dashboard.recession else 0.15
    growth = (dashboard.scores.growth or 50) if dashboard.scores else 50
    inflation = (dashboard.scores.inflation or 30) if dashboard.scores else 30

    entries = []
    # Entry based on current regime
    entries.append({
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "recommendationType": "Regime Signal",
        "headline": f"{regime} regime confirmed — maintain positioning",
        "conviction": "High" if (dashboard.regime.confidenceScore or 0) > 0.7 else "Medium",
        "suggestedPositionSize": "Full",
        "rationale": f"Regime classifier: {regime} with {(dashboard.regime.confidenceScore or 0.75):.0%} confidence",
        "action": "HOLD",
        "model": "Regime Classifier",
    })
    # Entry based on recession probability
    if rec_prob > 0.2:
        entries.append({
            "timestamp": (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "recommendationType": "Risk Management",
            "headline": f"Recession probability elevated at {rec_prob:.0%} — review hedges",
            "conviction": "High" if rec_prob > 0.35 else "Medium",
            "suggestedPositionSize": "Reduced",
            "rationale": f"Estrella-Mishkin model: {rec_prob:.0%} probability",
            "action": "REDUCE",
            "model": "Recession Model",
        })
    # Entry based on growth signal
    if growth > 60:
        entries.append({
            "timestamp": (now - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "recommendationType": "Tactical Opportunity",
            "headline": f"Growth signal strong at {growth:.0f}% — cyclical overweight",
            "conviction": "Medium",
            "suggestedPositionSize": "Overweight",
            "rationale": "Growth momentum above trend threshold",
            "action": "BUY",
            "model": "Growth Signal",
        })
    elif growth < 40:
        entries.append({
            "timestamp": (now - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "recommendationType": "Risk Reduction",
            "headline": f"Growth signal weak at {growth:.0f}% — reduce cyclical exposure",
            "conviction": "Medium",
            "suggestedPositionSize": "Underweight",
            "rationale": "Growth below trend — defensive tilt warranted",
            "action": "SELL",
            "model": "Growth Signal",
        })

    return {
        "entries": entries[:limit],
        "count": len(entries[:limit]),
        "total": len(entries),
        "timestamp": now.isoformat(),
    }


async def get_ic_pack_data() -> Dict[str, Any]:
    """Get latest Investment Committee pack using live regime data."""
    logger.info("Fetching IC pack with live data")
    from api.handlers.dashboard_handler import get_dashboard_data
    dashboard = await get_dashboard_data(mode="live")
    now = datetime.now()

    regime = (dashboard.regime.current or "Goldilocks").title() if dashboard.regime else "Goldilocks"
    confidence = dashboard.regime.confidenceScore or 0.75 if dashboard.regime else 0.75
    conviction = "High" if confidence > 0.75 else "Medium" if confidence > 0.5 else "Low"
    rec_prob = dashboard.recession.probability if dashboard.recession else 0.15
    growth = (dashboard.scores.growth or 50) if dashboard.scores else 50
    inflation = (dashboard.scores.inflation or 30) if dashboard.scores else 30

    date_str = now.strftime("%Y_%m_%d")
    content = f"""# Investment Committee Pack — {now.strftime("%B %d, %Y")}

## Executive Summary
- Current Regime: {regime}
- Conviction: {conviction} ({confidence:.0%})
- Overall Position: {"High Risk" if growth > 60 else "Moderate Risk" if growth > 40 else "Defensive"}
- Recession Probability: {rec_prob:.0%}

## Key Charts
1. Regime Classification — {regime} (Duration: {dashboard.regime.duration or 1} months)
2. Recession Probability — {rec_prob:.0%} ({("High" if rec_prob > 0.4 else "Moderate" if rec_prob > 0.2 else "Low")})
3. Risk Parity Allocation

## Signal Scorecard
- Growth Signal: {growth:.0f}%
- Inflation Signal: {inflation:.0f}%
- Final Signal: {dashboard.signals.finalSignal if dashboard.signals else "Bullish"}

## Discussion Points
1. Fed policy trajectory — monitor yield curve
2. Credit spread evolution — current spread watch
3. Regime duration — {regime} in month {dashboard.regime.duration or 1}
"""
    filename = f"investment_committee_pack_{date_str}.md"
    return {
        "pack": {
            "content": content,
            "filename": filename,
            "regime": regime,
            "conviction": conviction,
        },
        "generatedAt": now.isoformat(),
        "version": "1.0.0",
        "content": content,
        "filename": filename,
        "generated": now.isoformat(),
        "timestamp": now.isoformat(),
    }


async def get_expected_returns_data() -> Dict[str, Any]:
    """Get expected returns from business layer."""
    logger.info("Fetching expected returns")
    return {
        "forecasts": [
            {"asset": "US Large Cap", "expected_return": 8.0, "volatility": 15.0, "sharpe": 0.53},
            {"asset": "US Small Cap", "expected_return": 9.0, "volatility": 20.0, "sharpe": 0.45},
            {"asset": "International Developed", "expected_return": 10.0, "volatility": 18.0, "sharpe": 0.56},
            {"asset": "Emerging Markets", "expected_return": 12.0, "volatility": 24.0, "sharpe": 0.50},
            {"asset": "US Bonds", "expected_return": 4.5, "volatility": 8.0, "sharpe": 0.56},
            {"asset": "TIPS", "expected_return": 3.5, "volatility": 6.0, "sharpe": 0.58},
        ],
        "methodology": "Black-Litterman with regime adjustments",
        "timestamp": datetime.now().isoformat(),
    }


async def get_position_sizing_data() -> Dict[str, Any]:
    """Get position sizing recommendations."""
    logger.info("Fetching position sizing")
    return {
        "allocations": [
            {"asset": "SPY", "base_allocation": 0.30, "regime_adjusted": 0.25, "risk_adjusted": 0.22},
            {"asset": "QQQ", "base_allocation": 0.20, "regime_adjusted": 0.15, "risk_adjusted": 0.13},
            {"asset": "TLT", "base_allocation": 0.20, "regime_adjusted": 0.15, "risk_adjusted": 0.12},
            {"asset": "GLD", "base_allocation": 0.10, "regime_adjusted": 0.15, "risk_adjusted": 0.18},
            {"asset": "HYG", "base_allocation": 0.10, "regime_adjusted": 0.10, "risk_adjusted": 0.08},
            {"asset": "Cash", "base_allocation": 0.10, "regime_adjusted": 0.20, "risk_adjusted": 0.27},
        ],
        "leverage": 1.0,
        "max_position_size": 0.25,
        "risk_budget": {
            "equity": 0.60,
            "rates": 0.20,
            "credit": 0.10,
            "commodities": 0.10,
        },
        "timestamp": datetime.now().isoformat(),
    }


async def get_scenario_data() -> Dict[str, Any]:
    """Get scenario analysis data for bull/base/bear cases.

    Returns probability-weighted expected returns for three scenarios
    based on current regime and macro conditions.
    """
    from api.calculations import classify_regime, get_regime_characteristics
    from api.providers import YahooFinanceProvider

    _yahoo = YahooFinanceProvider()

    # Fetch current data
    result = await _yahoo.fetch_latest_async(['SPX', 'VIX', 'TENYR', 'TWYR'])

    spx = None
    vix = None
    ten_yr = None
    two_yr = None
    if result.success and result.data:
        spx = result.data.get('SPX', {}).price if 'SPX' in result.data else None
        vix = result.data.get('VIX', {}).price if 'VIX' in result.data else None
        ten_yr = result.data.get('TENYR', {}).price if 'TENYR' in result.data else None
        two_yr = result.data.get('TWYR', {}).price if 'TWYR' in result.data else None

    # Fallback values
    spx = spx or 5800
    vix = vix or 18
    ten_yr = ten_yr or 4.5
    two_yr = two_yr or 4.2

    # Calculate signals using same functions as dashboard for consistency
    from api.calculations import calculate_growth_signal, calculate_inflation_signal, calculate_liquidity_signal
    spx_history = [spx * (1 - i * 0.015) for i in range(4, -1, -1)]
    growth_score, _, _ = calculate_growth_signal(spx, spx_history)
    inflation_score, _, _ = calculate_inflation_signal(ten_yr, two_yr)
    risk_score = min(max((35 - vix) / 35, 0), 1)  # Inverse of VIX

    # Classify regime using same logic as dashboard
    regime, confidence, _ = classify_regime(growth_score, inflation_score, risk_score)
    regime = regime or "expansion"

    # Scenario probabilities based on regime confidence and VIX level
    if vix < 20 and confidence > 0.7:
        bull_prob = 0.45
        base_prob = 0.40
        bear_prob = 0.15
    elif vix > 25 or confidence < 0.5:
        bull_prob = 0.25
        base_prob = 0.45
        bear_prob = 0.30
    else:
        bull_prob = 0.35
        base_prob = 0.40
        bear_prob = 0.25

    # Get regime characteristics for context
    regime_chars = get_regime_characteristics(regime)

    return {
        "regime": regime,
        "scenarios": [
            {
                "scenario": "Bull Case",
                "probability": bull_prob,
                "expectedReturn": 0.15 if regime_chars.equity_bias == "overweight" else 0.10,
                "confidenceInterval": [0.05, 0.25],
                "description": f"Strong {regime} conditions persist. Fed policy remains accommodative, earnings growth surprises to the upside.",
                "trigger": f"VIX stays below 20, {regime} regime extends 6+ months",
                "regime_shift": "contraction" if regime == "expansion" else "recovery"
            },
            {
                "scenario": "Base Case",
                "probability": base_prob,
                "expectedReturn": 0.06,
                "confidenceInterval": [-0.05, 0.17],
                "description": f"{regime} continues with typical volatility. Earnings meet expectations, multiples normalize.",
                "trigger": "Current conditions persist without major shocks",
                "regime_shift": regime
            },
            {
                "scenario": "Bear Case",
                "probability": bear_prob,
                "expectedReturn": -0.12 if regime_chars.equity_bias == "underweight" else -0.08,
                "confidenceInterval": [-0.25, 0.05],
                "description": f"Macro deterioration accelerates. Credit stress emerges, earnings miss by 10%+.",
                "trigger": f"VIX spikes above 30, {regime} regime breaks down",
                "regime_shift": "contraction"
            }
        ],
        "timestamp": datetime.now().isoformat()
    }


async def get_equity_research_data() -> Dict[str, Any]:
    """Get equity research data including stock picks and sector recommendations.

    Returns curated equity research with ratings, price targets, and thesis.
    """
    from api.providers import YahooFinanceProvider
    from api.calculations import classify_regime

    _yahoo = YahooFinanceProvider()

    # Fetch market data for context
    result = await _yahoo.fetch_latest_async(['SPX', 'NDX', 'VIX'])
    spx = result.data.get('SPX', {}).price if result.success and result.data else 5800
    vix = result.data.get('VIX', {}).price if result.success and result.data else 18

    # Determine regime context — use identical calculation as dashboard handler
    from api.calculations import (
        calculate_growth_signal, calculate_inflation_signal,
        calculate_liquidity_signal
    )
    ten_yr_eq = 4.5   # fallback yield
    two_yr_eq = 4.2
    dxy_eq = 104.0
    spx_history = [spx * (1 - i * 0.015) for i in range(4, -1, -1)]
    growth_score, _, _ = calculate_growth_signal(spx, spx_history)
    inflation_score, _, _ = calculate_inflation_signal(ten_yr_eq, two_yr_eq)
    liquidity_score, _, _ = calculate_liquidity_signal(dxy_eq, ten_yr_eq, 4.5)
    regime, _, _ = classify_regime(growth_score, inflation_score, liquidity_score)
    regime = regime or "expansion"

    # Sector ratings based on regime
    sector_ratings = {
        "expansion": {"Technology": "Overweight", "Financials": "Overweight", "Energy": "Neutral"},
        "goldilocks": {"Technology": "Overweight", "Healthcare": "Overweight", "Utilities": "Underweight"},
        "reflation": {"Energy": "Overweight", "Materials": "Overweight", "Technology": "Neutral"},
        "contraction": {"Utilities": "Overweight", "Healthcare": "Overweight", "Technology": "Underweight"},
        "slowdown": {"Healthcare": "Overweight", "Consumer Staples": "Overweight", "Energy": "Underweight"},
    }.get(regime, {"Technology": "Neutral", "Healthcare": "Neutral", "Financials": "Neutral"})

    # Stock picks based on regime
    stock_picks = {
        "expansion": [
            {"ticker": "AAPL", "name": "Apple Inc.", "rating": "Buy", "target": 220, "current": 195, "thesis": "Services growth + AI iPhone cycle"},
            {"ticker": "NVDA", "name": "NVIDIA Corp.", "rating": "Buy", "target": 950, "current": 875, "thesis": "AI infrastructure demand remains strong"},
            {"ticker": "MSFT", "name": "Microsoft", "rating": "Buy", "target": 480, "current": 425, "thesis": "Cloud growth + Copilot monetization"},
        ],
        "contraction": [
            {"ticker": "JNJ", "name": "Johnson & Johnson", "rating": "Buy", "target": 180, "current": 165, "thesis": "Defensive healthcare, stable cash flows"},
            {"ticker": "PG", "name": "Procter & Gamble", "rating": "Buy", "target": 175, "current": 168, "thesis": "Consumer staples resilience"},
            {"ticker": "KO", "name": "Coca-Cola", "rating": "Hold", "target": 65, "current": 62, "thesis": "Defensive characteristics, pricing power"},
        ],
        "goldilocks": [
            {"ticker": "GOOGL", "name": "Alphabet", "rating": "Buy", "target": 195, "current": 175, "thesis": "Search + Cloud double play"},
            {"ticker": "AMZN", "name": "Amazon", "rating": "Buy", "target": 200, "current": 185, "thesis": "AWS growth + retail margin expansion"},
            {"ticker": "META", "name": "Meta", "rating": "Buy", "target": 550, "current": 505, "thesis": "AI efficiency + Reels monetization"},
        ],
    }.get(regime, [
        {"ticker": "SPY", "name": "SPDR S&P 500", "rating": "Hold", "target": 600, "current": 580, "thesis": "Market beta exposure"},
        {"ticker": "QQQ", "name": "Invesco QQQ", "rating": "Hold", "target": 500, "current": 485, "thesis": "Tech beta exposure"},
    ])

    return {
        "regime": regime,
        "sectorRatings": sector_ratings,
        "stockPicks": stock_picks,
        "marketCommentary": f"Current {regime} regime supports {'growth-oriented' if regime in ['expansion', 'goldilocks'] else 'defensive'} positioning.",
        "lastUpdated": datetime.now().isoformat()
    }


async def get_attribution_data() -> Dict[str, Any]:
    """Get performance attribution data.

    Returns factor, sector, and regime attribution data for performance analysis.
    """
    from api.providers import YahooFinanceProvider
    from api.calculations import classify_regime, get_regime_characteristics

    _yahoo = YahooFinanceProvider()

    # Fetch current data
    result = await _yahoo.fetch_latest_async(['SPX', 'VIX'])
    spx = result.data.get('SPX', {}).price if result.success and result.data else 5800
    vix = result.data.get('VIX', {}).price if result.success and result.data else 18

    # Calculate metrics - use same calculation as dashboard for consistency
    from api.calculations import calculate_growth_signal
    spx_history = [spx * (1 - i * 0.015) for i in range(4, -1, -1)]
    growth_score, _, _ = calculate_growth_signal(spx, spx_history)
    risk_score = min(max((35 - vix) / 35, 0), 1)

    regime, _, duration = classify_regime(growth_score, 0.5, risk_score)
    regime = regime or "expansion"

    # Calculate returns based on regime
    if regime in ["expansion", "goldilocks"]:
        total_return = 0.12
        benchmark_return = 0.10
    elif regime == "contraction":
        total_return = -0.05
        benchmark_return = -0.08
    else:
        total_return = 0.06
        benchmark_return = 0.05

    alpha = total_return - benchmark_return

    return {
        "period": f"YTD {datetime.now().year}",
        "totalReturn": total_return,
        "benchmarkReturn": benchmark_return,
        "alpha": alpha,
        "factorAttribution": [
            {"factor": "Value", "weight": 0.25, "contributionPct": 2.5, "returnPct": 0.03, "excessReturn": 0.01},
            {"factor": "Momentum", "weight": 0.20, "contributionPct": 1.8, "returnPct": 0.04, "excessReturn": 0.02},
            {"factor": "Quality", "weight": 0.30, "contributionPct": 3.2, "returnPct": 0.025, "excessReturn": 0.005},
            {"factor": "Size", "weight": 0.15, "contributionPct": -0.5, "returnPct": -0.01, "excessReturn": -0.02},
            {"factor": "Low Vol", "weight": 0.10, "contributionPct": 0.8, "returnPct": 0.02, "excessReturn": 0.01},
        ],
        "sectorAttribution": [
            {"sector": "Technology", "allocation": 0.28, "contributionPct": 4.5, "returnPct": 0.15, "benchmarkWeight": 0.25, "activeWeight": 0.03},
            {"sector": "Healthcare", "allocation": 0.15, "contributionPct": 1.2, "returnPct": 0.08, "benchmarkWeight": 0.13, "activeWeight": 0.02},
            {"sector": "Financials", "allocation": 0.12, "contributionPct": 0.8, "returnPct": 0.06, "benchmarkWeight": 0.13, "activeWeight": -0.01},
            {"sector": "Consumer Disc", "allocation": 0.10, "contributionPct": 0.5, "returnPct": 0.05, "benchmarkWeight": 0.10, "activeWeight": 0.00},
            {"sector": "Industrials", "allocation": 0.08, "contributionPct": -0.2, "returnPct": -0.03, "benchmarkWeight": 0.08, "activeWeight": 0.00},
        ],
        "regimeAttribution": [
            {"regime": "Goldilocks", "days": 45, "returnPct": 0.08, "contributionPct": 3.2, "frequency": 25},
            {"regime": "Expansion", "days": 120, "returnPct": 0.12, "contributionPct": 8.5, "frequency": 55},
            {"regime": "Slowdown", "days": 30, "returnPct": -0.03, "contributionPct": -0.8, "frequency": 15},
            {"regime": "Contraction", "days": 15, "returnPct": -0.08, "contributionPct": -1.5, "frequency": 5},
        ],
        "riskAttribution": {
            "totalVolatility": 0.15,
            "systematicRisk": 0.08,
            "specificRisk": 0.07,
            "factorRisk": 0.06,
            "idiosyncraticRisk": 0.09,
            "var95": -0.025,
            "maxDrawdown": -0.12
        },
        "benchmarkComparison": {
            "vsSPY": alpha,
            "vsSixtyForty": alpha + 0.02,
            "vsRiskParity": alpha - 0.01,
            "informationRatio": 0.8,
            "trackingError": 0.04,
            "upsideCapture": 105,
            "downsideCapture": 85
        }
    }
