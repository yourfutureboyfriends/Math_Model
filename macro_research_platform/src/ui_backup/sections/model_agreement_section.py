"""
Model Agreement Section

Renders the model agreement table showing how different models align.

# =============================================================================
# CHANGE SUMMARY
# =============================================================================
# FIXED: interpret_credit_stress was defined as a LOCAL namedtuple at the
#        bottom of this file with only 2 fields (level, interpretation).  The
#        full MetricInterpretation dataclass has 5 fields (level, direction,
#        combined, interpretation, confidence).  Any call-site accessing
#        .direction or .combined on the namedtuple result would raise
#        AttributeError.  Removed the local stub; import the canonical
#        function from src.utils.metric_interpretation instead.
# FIXED: interpret_credit_stress was not imported at the top of the module —
#        it only existed as a local definition after the render function.
#        Python's function scoping means the cs_interp call at line 95 used
#        the local definition, but that definition comes AFTER the call in
#        source order (though it still works at runtime because Python resolves
#        the name at call time, not definition time — however, it duplicated
#        logic and produced inconsistent level labels versus the rest of the
#        platform).  Now imported from the shared module for consistency.
# =============================================================================
"""

from typing import Optional

import pandas as pd
import streamlit as st

from ..tables import render_model_agreement_table
from ..theme import Theme, get_current_theme
# FIXED: Import canonical interpret_credit_stress from shared utility module
# instead of relying on the local namedtuple stub defined at the end of this file.
from ...utils.metric_interpretation import interpret_credit_stress


def render_model_agreement_section(
    regime: str,
    regime_confidence: str,
    scores: dict,
    directions: dict,
    model_results: dict,
    nowcast: dict,
    growth_interp,
    inflation_interp,
    fc_interp,
    rec_interp,
    risk_interp,
    theme: Optional[Theme] = None,
) -> None:
    """
    Render the model agreement section.

    Args:
        regime: Current regime
        regime_confidence: Regime confidence level
        scores: Dictionary of scores
        directions: Dictionary of directions
        model_results: Model results dictionary
        nowcast: Business conditions nowcast
        growth_interp: Growth interpretation
        inflation_interp: Inflation interpretation
        fc_interp: Financial conditions interpretation
        rec_interp: Recession risk interpretation
        risk_interp: Risk appetite interpretation
        theme: Optional theme override
    """
    theme = theme or get_current_theme()

    st.markdown(
        f'<div style="font-size: 13px; font-weight: 600; text-transform: uppercase; '
        f'letter-spacing: 0.05em; color: {theme.text_muted}; margin-bottom: 16px;">'
        f'Model Agreement</div>',
        unsafe_allow_html=True
    )

    # Build model agreement data
    model_agreement_data = []

    # Regime model
    model_agreement_data.append({
        "Model": "Regime Classification",
        "Signal": regime,
        "Interpretation": f"Growth: {growth_interp.level}, Inflation: {inflation_interp.level}",
        "Impact": "Primary determinant"
    })

    # Business conditions
    if nowcast:
        bc = nowcast
        model_agreement_data.append({
            "Model": "Business Conditions",
            "Signal": f"{bc['direction']} ({bc['score']:+.2f})",
            "Interpretation": f"Nowcast confidence: {bc['confidence']}",
            "Impact": "Confirms growth view" if bc["direction"] == "improving" else "Cautions on growth"
        })

    # Inflation pressure
    model_agreement_data.append({
        "Model": "Inflation Pressure",
        "Signal": f"{scores['inflation']:+.2f}",
        "Interpretation": f"{inflation_interp.level} + {inflation_interp.direction}",
        "Impact": "Supports late-cycle view" if inflation_interp.level == "Elevated" else "Contained"
    })

    # Financial conditions
    model_agreement_data.append({
        "Model": "Financial Conditions",
        "Signal": fc_interp.level,
        "Interpretation": f"{fc_interp.direction}",
        "Impact": "Tightening headwind" if fc_interp.direction == "Tightening" else "Easing tailwind" if fc_interp.direction == "Easing" else "Neutral"
    })

    # Credit stress — uses the imported canonical function (5-field MetricInterpretation)
    cs_score = model_results.get("credit_stress", {}).get("stress_score", 0)
    cs_interp = interpret_credit_stress(cs_score)  # FIXED: now uses imported function
    model_agreement_data.append({
        "Model": "Credit Stress",
        "Signal": cs_interp.level,
        "Interpretation": f"Score: {cs_score:+.2f}",
        "Impact": "Supports defensive" if cs_interp.level in ["Elevated"] else "Allows risk-on"
    })

    # Recession risk
    recession_prob = model_results.get("recession_probability", 0)
    model_agreement_data.append({
        "Model": "Recession Risk",
        "Signal": f"{recession_prob:.1f}%",
        "Interpretation": rec_interp.level,
        "Impact": "Allows risk-on" if rec_interp.level == "Low" else "Caution warranted"
    })

    # Risk appetite
    model_agreement_data.append({
        "Model": "Risk Appetite",
        "Signal": f"{scores['risk']:+.2f}",
        "Interpretation": f"{risk_interp.level} + {risk_interp.direction}",
        "Impact": "Confirms risk appetite" if risk_interp.level == "Risk-On" else "Suggests caution"
    })

    # Market confirmation
    mc = model_results.get("market_confirmation", {})
    if mc:
        mc_signal = mc.get("signal", "neutral")
        mc_alignment = mc.get("alignment", 0)
        model_agreement_data.append({
            "Model": "Market Confirmation",
            "Signal": mc_signal.replace("_", " ").title(),
            "Interpretation": f"Alignment: {mc_alignment:.0%}",
            "Impact": "Strong confirm" if mc_alignment > 0.7 else "Divergence warning" if mc_alignment < 0.4 else "Partial confirm"
        })

    # Create agreement dataframe
    agreement_df = pd.DataFrame(model_agreement_data)

    # Use dark HTML table with styled impact column
    render_model_agreement_table(agreement_df, title="", theme=theme)

    # Final view summary
    regime_color = theme.warning if "Inflation" in regime else theme.success if "Goldilocks" in regime else theme.danger if "Recession" in regime else theme.text
    st.markdown(f"""
    <div style="background: {theme.card_bg}; border-left: 3px solid {regime_color}; padding: 12px 16px; margin-top: 16px; border-radius: 0 4px 4px 0;">
        <div style="font-size: 12px; color: {theme.text_muted}; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;">Final Model View</div>
        <div style="font-size: 16px; font-weight: 600; color: {theme.text};">{regime} — {regime_confidence.title()} Confidence</div>
    </div>
    """, unsafe_allow_html=True)

# FIXED: Removed the duplicate local interpret_credit_stress namedtuple stub.
# That stub only had 2 fields (level, interpretation) and was inconsistent with
# the canonical MetricInterpretation dataclass (5 fields: level, direction,
# combined, interpretation, confidence).  The canonical function is now
# imported at the top of this module.
