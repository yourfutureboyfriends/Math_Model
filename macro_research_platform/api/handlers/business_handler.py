"""Business handler - business logic for business layer endpoints."""
from typing import Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# Regime -> trade playbook. Stops/targets are percentage distances from the LIVE entry
# price (previously entry prices were hardcoded, e.g. GLD $330 / $195, XLU $75, and SPY/QQQ
# were "SPX/10" and "SPX/12" — far from the real quotes).
# (ticker, direction, conviction, thesis, stop_pct, target_pct)
_TRADE_PLAYBOOK = {
    "goldilocks": [("SPY", "LONG", "HIGH", "Goldilocks regime — overweight equities", 0.05, 0.08),
                   ("QQQ", "LONG", "MEDIUM", "Tech momentum in growth regime", 0.06, 0.10)],
    "expansion": [("SPY", "LONG", "HIGH", "Expansion regime — overweight equities", 0.05, 0.08),
                  ("XLF", "LONG", "MEDIUM", "Financials benefit from rising rates in expansion", 0.07, 0.095)],
    "recovery": [("IWM", "LONG", "MEDIUM", "Early-cycle small-cap recovery", 0.07, 0.10),
                 ("XLF", "LONG", "MEDIUM", "Financials lead early-cycle recoveries", 0.07, 0.095)],
    "reflation": [("GLD", "LONG", "HIGH", "Reflation — real assets outperform", 0.036, 0.061),
                  ("SPY", "LONG", "MEDIUM", "Equities benefit from nominal growth", 0.05, 0.06)],
    "stagflation": [("GLD", "LONG", "HIGH", "Stagflation hedge via gold", 0.045, 0.076),
                    ("TLT", "SHORT", "MEDIUM", "Inflation pressure on long bonds", 0.054, 0.076)],
    "slowdown": [("TLT", "LONG", "HIGH", "Flight to quality in slowdown", 0.033, 0.087),
                 ("XLU", "LONG", "MEDIUM", "Defensive utilities in slowdown", 0.04, 0.093)],
    "contraction": [("TLT", "LONG", "HIGH", "Duration rallies in contraction", 0.033, 0.087),
                    ("XLP", "LONG", "MEDIUM", "Defensive staples in contraction", 0.04, 0.07)],
}


# SPDR sector ETFs used for observed sector relative strength.
SECTOR_ETFS = {"XLK": "Technology", "XLF": "Financials", "XLE": "Energy", "XLV": "Healthcare",
               "XLI": "Industrials", "XLP": "Consumer Staples", "XLY": "Consumer Discretionary",
               "XLU": "Utilities", "XLB": "Materials", "XLRE": "Real Estate", "XLC": "Communication"}
# Per-asset cap of the risk-parity allocation used for position sizing (policy setting).
POSITION_CAP = 0.40


async def _regime_trades(regime: str) -> list:
    """Playbook trades for `regime` with entry = latest real close. Trades whose price
    can't be fetched are dropped rather than shown with a made-up level."""
    from api.handlers.market_handler import _fetch_closes_literal
    out = []
    for ticker, direction, conviction, thesis, stop_pct, target_pct in _TRADE_PLAYBOOK.get(
            (regime or "").lower(), []):
        closes = await _fetch_closes_literal(ticker)
        if not closes:
            continue
        entry = round(float(closes[-1]), 2)
        sign = 1 if direction == "LONG" else -1
        out.append({"ticker": ticker, "direction": direction, "conviction": conviction,
                    "thesis": thesis, "entry": entry,
                    "stop": round(entry * (1 - sign * stop_pct), 2),
                    "target": round(entry * (1 + sign * target_pct), 2)})
    return out


def _rec_price(data: Optional[dict], key: str, fallback=None):
    """Safely read `.price` from a provider result record.

    A record may be absent, a PriceRecord (`.price`), or a plain dict (`['price']`).
    `data.get(key, {}).price` crashes on the `{}` default when the key is missing —
    this guards every such access. Units: same as the provider (index level / price).
    """
    rec = (data or {}).get(key)
    if rec is None:
        return fallback
    if isinstance(rec, dict):
        return rec.get("price", fallback)
    return getattr(rec, "price", fallback)


async def get_trade_ideas_data() -> Dict[str, Any]:
    """Trade ideas endpoint with real calculated data from regime."""
    logger.info("Fetching trade ideas with calculated data")

    # Get real calculated dashboard data
    from api.handlers.dashboard_handler import get_dashboard_data
    dashboard = await get_dashboard_data(mode="live")

    regime = (dashboard.regime.current or "").lower()
    ideas = [{"asset": t["ticker"], "direction": t["direction"], "entry": t["entry"],
              "stop": t["stop"], "target": t["target"], "conviction": t["conviction"],
              "rationale": t["thesis"]} for t in await _regime_trades(regime)]

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

    km = dashboard.keyMetrics
    spx = km.spxLevel if km else None
    vix = km.vix if km else None
    ten_yr = km.tenYearYield if km else None

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
    if risk < 40 and vix is not None:
        risks.append(f"Risk appetite low — VIX at {vix:.1f}")
    if ten_yr and ten_yr > 4.5:
        risks.append(f"Rates at {ten_yr:.2f}% — duration risk elevated")

    # Only data-backed risks are listed (generic filler such as "HY spreads near 400bps"
    # was asserted regardless of the actual spread).

    # Conviction trades from the shared regime playbook at live ETF prices
    trades = await _regime_trades(regime)

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
    # `risk` here is risk APPETITE (high = benign/risk-on), so a high value means "position
    # risk-ON", not "the environment is high-risk". Label it as a stance to avoid reading as a
    # warning (and it collides in tone with the header's complementary "risk level" metric).
    if risk > 0.7 and rec_prob < 0.2:
        overall_position = "RISK-ON"
    elif risk > 0.5 and rec_prob < 0.3:
        overall_position = "MODERATE RISK-ON"
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
            "risk_assessment": f"VIX {vix:.1f}, Recession {rec_prob:.0%}, Risk Appetite {risk:.0%}"
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
            "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "recommendationType": "Risk Management",
            "headline": f"Recession probability elevated at {rec_prob:.0%} — review hedges",
            "conviction": "High" if rec_prob > 0.35 else "Medium",
            "suggestedPositionSize": "Reduced",
            "rationale": f"Recession probit (yield curve + Fed funds): {rec_prob:.0%} 12-month probability",
            "action": "REDUCE",
            "model": "Recession Model",
        })
    # Entry based on growth signal
    if growth > 60:
        entries.append({
            "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
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
            "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "recommendationType": "Risk Reduction",
            "headline": f"Growth signal weak at {growth:.0f}% — reduce cyclical exposure",
            "conviction": "Medium",
            "suggestedPositionSize": "Underweight",
            "rationale": "Growth below trend — defensive tilt warranted",
            "action": "SELL",
            "model": "Growth Signal",
        })

    # Every entry reflects the CURRENT signals (they used to be back-dated 1-3 days, which
    # presented today's readings as a past decision history).
    return {
        "basis": "current signals (not a stored history of past decisions)",
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
    """Expected returns, conforming to ExpectedReturnsResponse — the dashboard's long-term
    CMA (gmoForecasts): equities = ETF earnings yield + 10Y breakeven, bonds = 10Y yield.
    `components` are those building blocks; TIPS = 10Y real yield (FRED DFII10) + breakeven.
    `confidence` is "unrated" — forecast uncertainty is not modelled. Empty when unavailable."""
    from api.handlers.dashboard_handler import get_dashboard_data
    from api.handlers.macro_inputs import load_fred_series
    logger.info("Fetching expected returns")
    dashboard = await get_dashboard_data(mode="live")
    cma = dashboard.gmoForecasts or {}
    returns = [{"asset": f["assetClass"], "expectedReturn": f["expectedReturn"],
                "confidence": "unrated", "components": f.get("components") or {}}
               for f in cma.get("forecasts", [])]
    real = (await load_fred_series(["DFII10"])).get("DFII10")
    be = cma.get("breakeven")
    if real and be is not None:
        returns.append({"asset": "TIPS", "expectedReturn": round(real.latest + be, 2), "confidence": "unrated",
                        "components": {"real_yield": round(real.latest, 2), "inflation": round(be, 2)}})
    return {"returns": returns, "lastUpdated": datetime.now().isoformat()}


async def get_position_sizing_data() -> Dict[str, Any]:
    """Position sizing, conforming to PositionSizingResponse: the dashboard's inverse-vol
    risk-parity weights (SPY/TLT/GLD/DBC, real 60d volatility). `maxSize` is the per-asset
    cap of this allocation (a policy setting); `confidence` is the 3m trend t-stat / 3,
    capped at 1. Empty when price history is unavailable."""
    from api.handlers.dashboard_handler import get_dashboard_data
    logger.info("Fetching position sizing")
    dashboard = await get_dashboard_data(mode="live")
    rp = dashboard.riskParityAllocation or {}
    recommendations = [
        {"asset": h["ticker"], "size": h["baseWeight"], "maxSize": POSITION_CAP,
         "confidence": round(min(abs(h.get("signalScore") or 0.0), 3.0) / 3.0, 2)}
        for h in rp.get("holdings", [])
    ]
    return {"recommendations": recommendations, "lastUpdated": datetime.now().isoformat()}


async def get_scenario_data() -> Dict[str, Any]:
    """Scenario analysis from history: next-month growth×inflation quadrant probabilities
    (empirical transition matrix, FRED since 1985) × the historical annualized 60/40 return
    in each quadrant, with 95% CIs — the dashboard's expectedReturns.next12Months. Empty
    scenarios when the monthly history is unavailable."""
    from api.handlers.dashboard_handler import get_dashboard_data
    dashboard = await get_dashboard_data(mode="live")
    er = dashboard.expectedReturns
    current = er.currentQuadrant if er else None
    scenarios = []
    for sc in (er.next12Months if er else []):
        q = sc["scenario"]
        scenarios.append({
            "scenario": q if q != current else f"{q} (stay)",
            "probability": sc["probability"],
            "expectedReturn": sc["expectedReturn"],
            "confidenceInterval": sc["confidenceInterval"],
            "description": (f"Historical annualized 60/40 (SPY/TLT) return in {q} months "
                            f"({sc.get('months')} months since inception of the ETFs)."),
            "trigger": (f"Growth/inflation quadrant {'stays' if q == current else 'moves to'} {q} "
                        f"next month (empirical probability {sc['probability']:.0%})."),
            "regime_shift": q,
        })
    return {"regime": (dashboard.regime.current or "").lower() or None,
            "quadrant": current,
            "scenarios": scenarios,
            "methodology": er.methodology if er else None,
            "timestamp": datetime.now().isoformat()}


async def get_equity_research_data() -> Dict[str, Any]:
    """Sector ratings from observed relative strength: each SPDR sector ETF's 3-month
    return vs SPY, as a percentile of the past year (≥ 0.66 Overweight, ≤ 0.34 Underweight).
    No stock picks: no research / price-target source is configured, and invented targets
    would be presented as research."""
    import asyncio
    from api.calculations import market_stats as ms
    from api.handlers.dashboard_handler import get_dashboard_data
    from api.handlers.market_handler import _fetch_dated_closes_literal

    dashboard = await get_dashboard_data(mode="live")
    regime = (dashboard.regime.current or "").lower() or None
    tickers = ["SPY"] + list(SECTOR_ETFS)
    dated = await asyncio.gather(*[_fetch_dated_closes_literal(t) for t in tickers], return_exceptions=True)
    px = {t: d for t, d in zip(tickers, dated) if isinstance(d, dict) and d}
    ratings, detail = {}, []
    if "SPY" in px:
        for etf, sector in SECTOR_ETFS.items():
            if etf not in px:
                continue
            _, al = ms.align_dated({etf: px[etf], "SPY": px["SPY"]})
            rs = ms.relative_strength_score(al[etf], al["SPY"])
            if not rs:
                continue
            pct = rs["percentile"]
            rating = "Overweight" if pct >= 0.66 else "Underweight" if pct <= 0.34 else "Neutral"
            ratings[sector] = rating
            detail.append({"sector": sector, "etf": etf, "rating": rating,
                           "relativeReturn3m": round(rs["relativeReturn"], 4), "percentile": round(pct, 2)})
    leaders = [d["sector"] for d in sorted(detail, key=lambda d: d["relativeReturn3m"], reverse=True)[:3]]
    return {
        "regime": regime,
        "sectorRatings": ratings,
        "sectors": detail,
        "stockPicks": [],
        "marketCommentary": (f"3-month sector leaders vs SPY: {', '.join(leaders)}." if leaders
                             else "Sector price history unavailable."),
        "methodology": "Sector ETF 3m return minus SPY, percentile within its past year (Yahoo daily closes).",
        "lastUpdated": datetime.now().isoformat(),
    }


async def get_attribution_data() -> Dict[str, Any]:
    """Get performance attribution data.

    Returns factor, sector, and regime attribution data for performance analysis.
    """
    # HONEST ABSENCE: this legacy endpoint previously returned a fully hardcoded factor/sector/
    # regime/risk attribution table (fabricated performance numbers stamped "YTD"). Real,
    # position-level performance attribution is computed from actual holdings at
    # /api/v1/portfolio/attribution — which is what the frontend panel already uses. No live
    # panel consumes this endpoint, so we return structured absence rather than fake data.
    return {
        "available": False,
        "reason": "Static per-factor/sector attribution was removed as non-real. "
                  "Live position-level attribution is at /api/v1/portfolio/attribution.",
        "period": f"YTD {datetime.now().year}",
        "factorAttribution": [],
        "sectorAttribution": [],
        "regimeAttribution": [],
        "riskAttribution": {},
        "benchmarkComparison": {},
    }
