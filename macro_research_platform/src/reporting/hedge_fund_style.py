"""
hedge_fund_style.py — Institutional language and formatting for macro research outputs.

This module provides hedge fund appropriate language, terminology, and formatting
for investment memos, dashboards, and reports.
"""

from typing import Dict, List, Optional
import pandas as pd


# =============================================================================
# Professional Terminology Mapping
# =============================================================================

TERMINOLOGY_MAP = {
    # Original → Professional
    "growth_score": "Growth momentum",
    "inflation_score": "Inflation pressure",
    "liquidity_score": "Financial conditions",
    "risk_score": "Risk appetite / market stress",
    "recession_prob": "Recession risk",
    "sector_recommendation": "Sector allocation view",
    "educational": "Research framework",
    "signal": "conviction level",
    "overweight": "Overweight",
    "underweight": "Underweight",
    "neutral": "Neutral",
}


# =============================================================================
# Institutional Signal Descriptors
# =============================================================================

def get_growth_descriptor(score: float, direction: str) -> str:
    """Institutional description of growth conditions."""
    if score > 1.0:
        return "Activity running above trend with broad-based expansion"
    elif score > 0.5:
        return "Activity improving but not yet entrenched"
    elif score > -0.5:
        return "Activity stable near trend"
    elif score > -1.0:
        return "Activity softening, momentum weakening"
    else:
        return "Activity contracting, clear below-trend conditions"


def get_inflation_descriptor(score: float, direction: str) -> str:
    """Institutional description of inflation conditions."""
    if score > 1.0:
        return "Inflation elevated with broad-based price pressure"
    elif score > 0.5:
        return "Inflation above target, pressure building"
    elif score > -0.5:
        return "Inflation near target, pressure balanced"
    elif score > -1.0:
        return "Inflation easing, disinflationary impulse"
    else:
        return "Inflation low, risk of deflationary conditions"


def get_liquidity_descriptor(score: float, direction: str) -> str:
    """Institutional description of financial conditions."""
    if score > 1.0:
        return "Accommodative policy stance, loose financial conditions"
    elif score > 0.5:
        return "Supportive policy, easing financial conditions"
    elif score > -0.5:
        return "Neutral policy stance, balanced conditions"
    elif score > -1.0:
        return "Restrictive policy, tightening financial conditions"
    else:
        return "Tight policy stance, constrained credit availability"


def get_risk_descriptor(score: float, direction: str) -> str:
    """Institutional description of risk conditions."""
    if score > 1.0:
        return "Risk-seeking environment, low volatility regime"
    elif score > 0.5:
        return "Risk-on conditions, supportive sentiment"
    elif score > -0.5:
        return "Balanced risk appetite, neutral sentiment"
    elif score > -1.0:
        return "Risk-off conditions, elevated caution"
    else:
        return "Risk-averse environment, stress indicators elevated"


def get_regime_descriptor(regime: str) -> str:
    """Institutional description of macro regime."""
    descriptors = {
        "Goldilocks": "Expansionary activity with contained inflation — constructive for risk assets",
        "Reflation": "Above-trend activity with rising inflation — early-cycle, policy tightening risk",
        "Slowdown": "Decelerating activity with falling inflation — mid-to-late cycle, policy pivot potential",
        "Stagflation": "Weak activity with elevated inflation — policy constrained, risk-off bias warranted",
    }
    return descriptors.get(regime, "Transitional regime — signal clarity low")


# =============================================================================
# Conviction Level Classification
# =============================================================================

def get_conviction_level(score: float) -> str:
    """Convert score to institutional conviction level."""
    abs_score = abs(score)
    if abs_score > 1.0:
        return "High conviction"
    elif abs_score > 0.5:
        return "Moderate conviction"
    else:
        return "Low conviction / balanced"


def get_signal_level(score: float) -> str:
    """Convert score to 5-level signal classification."""
    if score >= 0.60:
        return "Overweight"
    elif score >= 0.20:
        return "Slight Overweight"
    elif score > -0.20:
        return "Neutral"
    elif score > -0.60:
        return "Slight Underweight"
    else:
        return "Underweight"


def get_signal_strength(score: float) -> str:
    """Signal strength classification."""
    abs_score = abs(score)
    if abs_score > 1.5:
        return "Strong"
    elif abs_score > 0.8:
        return "Moderate"
    elif abs_score > 0.3:
        return "Weak"
    else:
        return "Insufficient"


# =============================================================================
# Institutional Sector Rationales
# =============================================================================

SECTOR_RATIONALES = {
    "Banks": {
        "ow": "Favourable net interest margin expansion from steep yield curve and rate environment. Credit conditions supportive.",
        "sow": "Some support from rate environment, but credit dynamics mixed. Selective exposure warranted.",
        "n": "Rate and credit dynamics mixed. Sector view neutral pending clearer signal.",
        "suw": "Flattening yield curve pressure on margins. Credit conditions warrant caution.",
        "uw": "Flattening yield curve compresses margins. Credit deterioration risk rising in slowdown conditions.",
    },
    "Energy": {
        "ow": "Inflation impulse and commodity tightness supportive. Supply constraints outweigh demand concerns.",
        "sow": "Energy remains cleanest inflation hedge, but signal strength depends on oil momentum and demand confirmation.",
        "n": "Supply-demand dynamics balanced. Idiosyncratic factors dominate macro signal.",
        "suw": "Demand uncertainty rising. Inflation impulse insufficient for strong positioning.",
        "uw": "Demand destruction risk from activity slowdown outweighs supply factors.",
    },
    "Technology": {
        "ow": "Rate sensitivity favourable with financial conditions easing. Duration exposure attractive.",
        "sow": "Risk-on price action supports sector, but elevated inflation and rate sensitivity limit conviction.",
        "n": "Rate outlook and earnings trajectory unclear. Sector view balanced.",
        "suw": "Rate pressure and valuation concerns emerging. Defensive positioning warranted.",
        "uw": "Rising real yields and restrictive conditions pressure long-duration cash flows. Valuation compression risk.",
    },
    "Consumer Discretionary": {
        "ow": "Labour market resilience and real wage growth support consumption. Late-cycle strength possible.",
        "sow": "Low recession risk supports spending, but inflation pressure can hurt real spending power.",
        "n": "Consumer fundamentals mixed. Spending rotation unclear.",
        "suw": "Inflation pressure on real wages and slowing momentum warrant caution.",
        "uw": "Employment softening and savings drawdown pressure consumer spending. Cyclical exposure vulnerable.",
    },
    "Utilities": {
        "ow": "Defensive characteristics attractive in slowdown. Rate sensitivity favourable as yields fall.",
        "sow": "Defensive earnings stability attractive, but rate environment only partially supportive.",
        "n": "Rate and growth outlook balanced. Defensive characteristics appropriately priced.",
        "suw": "Rate pressures emerging. Growth outlook reduces defensive urgency.",
        "uw": "Rate rise environment pressures bond-proxy valuations. Growth acceleration reduces defensive appeal.",
    },
    "Industrials": {
        "ow": "Activity acceleration and capex recovery supportive. Early-to-mid cycle exposure attractive.",
        "sow": "Activity indicators mixed. Regional exposure differences create selective opportunities.",
        "n": "Activity indicators mixed. Regional exposure differences significant.",
        "suw": "Manufacturing momentum slowing in key markets. Capex cycle headwinds emerging.",
        "uw": "Manufacturing momentum slowing. Global trade and capex cycle headwinds.",
    },
    "Healthcare": {
        "ow": "Defensive characteristics warranted. Earnings stability attractive in uncertain environment.",
        "sow": "Defensive earnings stability supports sector, but risk-on market confirmation reduces defensive urgency.",
        "n": "Sector fundamentals stable. Macro signal neutral.",
        "suw": "Policy headwinds and pricing pressure emerging. Defensive demand moderating.",
        "uw": "Policy and pricing headwinds. Growth recovery reduces defensive demand.",
    },
}


def get_sector_rationale(sector: str, signal: str) -> str:
    """Get institutional rationale for sector signal."""
    signal_map = {
        "Overweight": "ow",
        "Slight Overweight": "sow",
        "Neutral": "n",
        "Slight Underweight": "suw",
        "Underweight": "uw"
    }
    signal_key = signal_map.get(signal, "n")
    return SECTOR_RATIONALES.get(sector, {}).get(signal_key, "Macro signal insufficient for clear view.")


# =============================================================================
# Transmission Channel Analysis
# =============================================================================

def get_transmission_analysis(
    growth_score: float,
    inflation_score: float,
    liquidity_score: float,
    risk_score: float,
) -> Dict[str, str]:
    """Analyze transmission channels to asset prices."""

    analysis = {}

    # Rates channel
    if liquidity_score < -0.5:
        analysis["rates"] = "Restrictive policy stance pressuring duration. Real yields elevated, discount rate headwind."
    elif liquidity_score > 0.5:
        analysis["rates"] = "Accommodative conditions supportive of duration. Falling yields reduce discount rate pressure."
    else:
        analysis["rates"] = "Rate outlook balanced. Duration exposure neutral."

    # Credit channel
    if liquidity_score < -0.5 and risk_score < -0.3:
        analysis["credit"] = "Tightening financial conditions and widening spreads. Credit risk premium rising."
    elif liquidity_score > 0.3 and risk_score > 0.0:
        analysis["credit"] = "Supportive credit conditions. Spreads tight, risk appetite constructive."
    else:
        analysis["credit"] = "Credit conditions mixed. Spread direction unclear."

    # Earnings channel
    if growth_score > 0.5:
        analysis["earnings"] = "Above-trend activity supporting revenue growth and margin expansion."
    elif growth_score < -0.5:
        analysis["earnings"] = "Below-trend activity pressuring revenues and margins. Downside risk to estimates."
    else:
        analysis["earnings"] = "Activity near trend. Earnings revisions likely modest."

    # Valuation channel
    if liquidity_score < -0.5 and growth_score < 0:
        analysis["valuation"] = "Double pressure: rising discount rates and falling earnings expectations. Multiple compression risk."
    elif liquidity_score > 0.5 and growth_score > 0:
        analysis["valuation"] = "Dual tailwind: falling discount rates and rising earnings. Multiple expansion potential."
    else:
        analysis["valuation"] = "Cross-currents between rate and earnings outlook. Valuation impact mixed."

    # Risk appetite channel
    if risk_score > 0.5:
        analysis["risk_appetite"] = "Risk-seeking environment supporting risk premia compression."
    elif risk_score < -0.5:
        analysis["risk_appetite"] = "Risk-off conditions driving risk premia expansion."
    else:
        analysis["risk_appetite"] = "Risk appetite balanced. No significant sentiment-driven repricing."

    return analysis


# =============================================================================
# Research Framework References
# =============================================================================

RESEARCH_BACKING = {
    "regime_classification": [
        "Hamilton (1989) — Markov-switching regime model framework",
        "Ang & Bekaert (2002) — International regime-switching evidence",
    ],
    "recession_model": [
        "Estrella & Mishkin (1998) — Yield curve recession prediction",
        "Campbell & Shiller (1991) — Term structure predictive power",
    ],
    "factor_model": [
        "Chen, Roll & Ross (1986) — APT macro factor framework",
        "Fama & French (1989) — Business cycle expected returns",
    ],
    "inflation_nowcast": [
        "Stock & Watson (2002) — Dynamic factor nowcasting",
        "Bridge equation literature",
    ],
    "sector_allocation": [
        "Stangl, Jacobsen & Visaltanachoti (2008) — Sector rotation evidence",
        "Industry momentum literature",
    ],
}


def get_research_backing(component: str) -> List[str]:
    """Get research backing for model component."""
    return RESEARCH_BACKING.get(component, [])


# =============================================================================
# Investment Memo Templates
# =============================================================================

def generate_executive_summary(
    regime: str,
    scores: Dict[str, float],
    directions: Dict[str, str],
    sector_signals: Dict[str, str],
) -> str:
    """Generate executive summary in hedge fund style."""

    # Base case statement
    growth_desc = get_growth_descriptor(scores["growth"], directions["growth"])
    infl_desc = get_inflation_descriptor(scores["inflation"], directions["inflation"])
    liq_desc = get_liquidity_descriptor(scores["liquidity"], directions["liquidity"])

    paragraphs = []

    # Base case paragraph
    base_case = f"""The model points to {get_regime_descriptor(regime).lower()}.
{growth_desc}. {infl_desc}. {liq_desc}."""
    paragraphs.append(base_case)

    # Sector view
    ow_sectors = [s for s, sig in sector_signals.items() if sig == "Overweight"]
    uw_sectors = [s for s, sig in sector_signals.items() if sig == "Underweight"]

    if ow_sectors or uw_sectors:
        sector_text = "The sector allocation view favours "
        if ow_sectors:
            sector_text += f"overweight positioning in {', '.join(ow_sectors)}"
        if ow_sectors and uw_sectors:
            sector_text += " and "
        if uw_sectors:
            sector_text += f"underweight exposure to {', '.join(uw_sectors)}"
        sector_text += "."
        paragraphs.append(sector_text)

    # Risk case
    risk_paragraph = "The main risk to this view is a simultaneous "
    if directions["growth"] == "deteriorating":
        risk_paragraph += "improvement in activity indicators, "
    else:
        risk_paragraph += "deterioration in activity indicators, "

    if directions["liquidity"] == "tightening":
        risk_paragraph += "easing of financial conditions, and "
    else:
        risk_paragraph += "tightening of financial conditions, and "

    if directions["risk"] == "falling":
        risk_paragraph += "renewed risk appetite, which would suggest the macro environment is shifting faster than the model captures."
    else:
        risk_paragraph += "risk-off sentiment, which would accelerate the regime shift."

    paragraphs.append(risk_paragraph)

    return "\n\n".join(paragraphs)


def get_data_to_watch(scores: Dict[str, float], directions: Dict[str, str]) -> List[str]:
    """Generate list of data releases to watch."""
    watch_list = []

    if abs(scores["growth"]) < 0.5 or directions["growth"] == "stable":
        watch_list.append("PMI releases — activity direction still unclear")

    if abs(scores["inflation"]) < 0.5 or directions["inflation"] == "stable":
        watch_list.append("CPI/PPI — inflation trajectory pivotal for policy outlook")

    if abs(scores["liquidity"]) < 0.5:
        watch_list.append("Fed communications — policy stance clarity needed")

    if scores["risk"] < -0.3:
        watch_list.append("Credit spreads — stress indicators warrant monitoring")

    watch_list.append("Earnings revisions — fundamental validation of macro view")

    return watch_list
