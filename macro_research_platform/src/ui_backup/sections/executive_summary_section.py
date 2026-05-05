"""
Executive Summary Section

Renders the executive summary card with regime and confidence information.

# =============================================================================
# CHANGE SUMMARY
# =============================================================================
# FIXED: render_status_badge("High Confidence", ...) passed wrong string —
#        the badge function lowercases and looks up the status key; "high
#        confidence" is not in the lookup map so it rendered grey. Now mapped
#        to the correct semantic keys ("success", "info", "warning", "neutral").
# FIXED: render_status_badge("info", ...) for moderate confidence also produced
#        a blue "info" badge regardless of actual confidence level. Now mapped
#        to "warning" for moderate and "neutral" for unknown.
# =============================================================================
"""

from typing import List, Optional

import streamlit as st

from ..components import render_regime_badge, render_status_badge
from ..theme import Theme, get_current_theme


def get_regime_color(regime: str, theme: Theme) -> tuple:
    """Get color and description for a regime."""
    regime_colors = {
        "Goldilocks": (theme.success, "growth positive, inflation contained"),
        "Reflation": (theme.warning, "growth recovering, inflation rising"),
        "Slowdown": (theme.info, "growth decelerating, inflation falling"),
        "Stagflation": (theme.danger, "growth weak, inflation elevated"),
        "Inflation Pressure / Late-Cycle": (theme.warning, "inflation elevated, selective positioning warranted"),
        "Recovery / Mixed": (theme.accent, "growth improving from low base"),
        "Mixed / Transition": (theme.neutral, "conflicting signals, high uncertainty"),
    }
    return regime_colors.get(regime, (theme.neutral, "unclear regime dynamics"))


def generate_executive_summary_text(
    regime: str,
    growth_score: float,
    growth_state: str,
    inflation_score: float,
    inflation_state: str,
    recession_prob: float,
    credit_stress: str,
    confidence: str,
    confidence_score: float,
) -> str:
    """Generate hedge fund-style executive summary text."""
    # Growth condition
    if "strong" in growth_state or growth_score > 0.5:
        growth_desc = "Growth remains robust"
    elif "weak" in growth_state or growth_score < -0.5:
        growth_desc = "Growth has weakened materially"
    else:
        growth_desc = "Growth is broadly neutral"

    # Inflation condition
    if "elevated" in inflation_state or inflation_score > 0.5:
        infl_desc = "inflation pressure remains elevated"
    elif "low" in inflation_state or inflation_score < -0.5:
        infl_desc = "inflation is contained"
    else:
        infl_desc = "inflation is near target levels"

    # Credit/recession context
    if recession_prob < 15:
        rec_desc = "Recession risk remains low"
    elif recession_prob < 30:
        rec_desc = "Recession risk is elevated but not acute"
    else:
        rec_desc = "Recession risk is elevated"

    if credit_stress == "normal":
        credit_desc = "credit stress is contained"
    else:
        credit_desc = f"credit stress is {credit_stress}"

    # Portfolio stance
    stance_map = {
        "Inflation Pressure / Late-Cycle": "selective positioning rather than a full defensive rotation",
        "Goldilocks": "full risk-on positioning across cyclical assets",
        "Stagflation": "defensive positioning with inflation hedges",
        "Slowdown": "duration and quality defensive positioning",
        "Reflation": "cyclical and value-oriented positioning",
    }
    stance = stance_map.get(regime, "cautious, diversified positioning")

    # Confidence explanation
    if confidence in ["low", "very_low"]:
        conf_reason = f"Confidence is {confidence} due to mixed signal strength across models."
    elif confidence == "moderate":
        conf_reason = f"Moderate confidence reflects elevated inflation but limited confirmation from recession risk and credit stress."
    else:
        conf_reason = f"High confidence reflects strong signal alignment across models."

    return f"{growth_desc} while {infl_desc}. {rec_desc} and {credit_desc}, suggesting {stance}.|{conf_reason}"


def generate_confidence_explanation(
    confidence: str,
    confidence_score: float,
    warnings: List[str],
    evidence: List[str],
) -> str:
    """Generate confidence explanation text."""
    parts = []

    if confidence == "high":
        parts.append("Strong signal alignment across all models.")
    elif confidence == "moderate":
        parts.append("Mixed signal strength with some model disagreement.")
        if warnings:
            parts.append(f"Key uncertainty: {warnings[0]}")
    else:
        parts.append("High uncertainty due to conflicting signals.")
        if warnings:
            parts.append(f"Primary concern: {warnings[0]}")

    if evidence:
        parts.append(f"Supporting evidence: {evidence[0]}")

    return " ".join(parts)


def render_executive_summary_section(
    regime: str,
    regime_confidence: str,
    confidence_score: float,
    scores: dict,
    growth_interp,
    inflation_interp,
    recession_prob: float,
    credit_stress: str,
    validation_warnings: List[str],
    supporting_evidence: List[str],
    theme: Optional[Theme] = None,
) -> None:
    """
    Render the executive summary section.

    Args:
        regime: Current regime classification
        regime_confidence: Confidence level (high/moderate/low)
        confidence_score: Numeric confidence score (0-1)
        scores: Dictionary of macro scores
        growth_interp: Growth interpretation object
        inflation_interp: Inflation interpretation object
        recession_prob: Recession probability percentage
        credit_stress: Credit stress level
        validation_warnings: List of validation warnings
        supporting_evidence: List of supporting evidence
        theme: Optional theme override
    """
    theme = theme or get_current_theme()

    st.markdown(
        f'<div style="font-size: 13px; font-weight: 600; text-transform: uppercase; '
        f'letter-spacing: 0.05em; color: {theme.text_muted}; margin-bottom: 16px;">'
        f'Executive Summary</div>',
        unsafe_allow_html=True
    )

    # Get regime color and description
    regime_color, regime_desc = get_regime_color(regime, theme)

    # FIXED: render_status_badge() looks up the status string in a predefined
    # colour map. "High Confidence", "info", "warning", "neutral" were being
    # passed verbatim; the first one isn't in the map so it fell through to
    # the grey fallback.  Mapped to the correct semantic keys instead.
    if regime_confidence == "high":
        conf_badge = render_status_badge("success", theme)   # FIXED: was "High Confidence"
    elif regime_confidence == "moderate":
        conf_badge = render_status_badge("warning", theme)   # FIXED: was "info"
    elif regime_confidence == "low":
        conf_badge = render_status_badge("warning", theme)   # unchanged
    else:
        conf_badge = render_status_badge("neutral", theme)   # unchanged

    # Generate executive summary
    exec_summary = generate_executive_summary_text(
        regime=regime,
        growth_score=scores.get('growth', 0),
        growth_state=growth_interp.level.lower(),
        inflation_score=scores.get('inflation', 0),
        inflation_state=inflation_interp.level.lower(),
        recession_prob=recession_prob,
        credit_stress=credit_stress,
        confidence=regime_confidence,
        confidence_score=confidence_score,
    )

    # Split summary
    exec_parts = exec_summary.split("|")
    exec_main = exec_parts[0] if len(exec_parts) > 0 else exec_summary
    exec_conf = exec_parts[1] if len(exec_parts) > 1 else ""

    confidence_explanation = generate_confidence_explanation(
        regime_confidence, confidence_score, validation_warnings, supporting_evidence
    )

    # Render executive summary card with visual hierarchy
    st.markdown(f"""
    <div style="background: {theme.card_bg}; border: 1px solid {theme.border}; border-left: 4px solid {regime_color}; border-radius: 12px; padding: 24px; margin-bottom: 24px;">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; flex-wrap: wrap; gap: 12px;">
            <div style="display: flex; align-items: center; gap: 12px;">
                <div style="width: 12px; height: 12px; border-radius: 50%; background: {regime_color}; box-shadow: 0 0 12px {regime_color};"></div>
                <div style="font-size: 1.6rem; font-weight: 700; color: {theme.text}; letter-spacing: -0.01em;">{regime}</div>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 0.8rem; color: {theme.text_muted}; margin-right: 8px;">Confidence:</span>
                {conf_badge}
            </div>
        </div>
        <div style="font-size: 14px; color: {theme.text_subtle}; line-height: 1.6; margin-bottom: 16px;">
            <p>{exec_main}</p>
            <p style="margin-top: 12px; font-size: 12px; color: {theme.text_muted};">{exec_conf}</p>
        </div>
        <div style="display: flex; gap: 24px; font-size: 12px; color: {theme.text_muted}; flex-wrap: wrap;">
            <div>Confidence Score: <strong style="color: {theme.text};">{confidence_score:.0%}</strong></div>
            <div style="flex: 1; min-width: 300px;">Explanation: {confidence_explanation}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
