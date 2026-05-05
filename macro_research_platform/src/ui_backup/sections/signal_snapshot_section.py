"""
Signal Snapshot Section

Renders the signal snapshot table with current states and interpretations.
Uses color-coded badges for Direction and State columns with zebra striping.

# =============================================================================
# CHANGE SUMMARY
# =============================================================================
# FIXED: Zebra striping used `idx % 2 == 0` where `idx` is the DataFrame's row
#        label from iterrows(), NOT an enumeration counter. With a non-integer
#        or non-zero-based index this raises TypeError or produces wrong colors.
#        Replaced with enumerate() so the parity test is always on a plain int.
# =============================================================================
"""

from typing import Optional

import pandas as pd
import streamlit as st

from ..theme import Theme, get_current_theme


def get_3m_change(series: pd.Series) -> float:
    """Get 3-month change for a series."""
    if len(series) < 4:
        return 0
    return series.iloc[-1] - series.iloc[-4]


def _get_state_color(state: str, theme: Theme) -> str:
    """Get color for state value."""
    state_lower = str(state).lower()
    if any(word in state_lower for word in ['strong', 'positive', 'risk-on', 'low', 'easy', 'healthy', 'normal']):
        return theme.success
    elif any(word in state_lower for word in ['weak', 'negative', 'elevated', 'high', 'tight', 'stressed']):
        return theme.danger
    elif any(word in state_lower for word in ['moderate', 'neutral', 'stable']):
        return theme.warning
    return theme.text_muted


def _get_direction_color(direction: str, theme: Theme) -> str:
    """Get color for direction value."""
    direction_lower = str(direction).lower()
    if any(word in direction_lower for word in ['improving', 'rising', 'increasing', 'strengthening']):
        return theme.success
    elif any(word in direction_lower for word in ['deteriorating', 'falling', 'decreasing', 'weakening']):
        return theme.danger
    elif any(word in direction_lower for word in ['stable', 'neutral']):
        return theme.warning
    return theme.text_muted


def _render_badge(text: str, color: str, bg_alpha: str = "0.10") -> str:
    """Render a colored badge."""
    # Convert hex color to rgba for background
    text_upper = text.upper() if len(text) < 15 else text
    return (
        f'<span style="'
        f'color: {color}; '
        f'font-weight: 600; '
        f'font-size: 11px; '
        f'text-transform: uppercase; '
        f'letter-spacing: 0.04em;"'
        f'>{text_upper}</span>'
    )


def _render_signal_table_html(df: pd.DataFrame, theme: Theme) -> str:
    """Generate styled HTML table with zebra striping and color-coded badges."""
    html_parts = []

    html_parts.append(f'''
    <table style="
        background-color: {theme.card_bg};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-collapse: collapse;
        width: 100%;
        font-size: 13px;
        border-radius: 8px;
        overflow: hidden;
    ">
    ''')

    # Header with bold, uppercase styling
    html_parts.append(f'<thead><tr style="background-color: {theme.elevated};">')
    for col in df.columns:
        html_parts.append(
            f'<th style="'
            f'border-bottom: 2px solid {theme.border}; '
            f'padding: 14px 12px; '
            f'text-align: left; '
            f'font-weight: 700; '
            f'font-size: 11px; '
            f'text-transform: uppercase; '
            f'letter-spacing: 0.08em; '
            f'color: {theme.text};"'
            f'>{col}</th>'
        )
    html_parts.append('</tr></thead>')

    # Body with zebra striping
    html_parts.append('<tbody>')
    # FIXED: Use enumerate(df.iterrows()) so `row_num` is always a plain int.
    # Previously `idx % 2 == 0` operated on the DataFrame's row label which
    # raises TypeError for string labels and gives wrong colors for non-zero-
    # based integer labels.
    for row_num, (_, row) in enumerate(df.iterrows()):
        # FIXED: zebra parity on row_num (enumeration counter), not DataFrame label
        if row_num % 2 == 0:
            bg_color = theme.card_bg
        else:
            bg_color = "rgba(255,255,255,0.04)" if "dark" in theme.page_bg else "rgba(0,0,0,0.02)"

        html_parts.append(f'<tr style="border-bottom: 1px solid {theme.border_light}; background-color: {bg_color};">')

        for col in df.columns:
            val = row.get(col, "")
            cell_style = f'padding: 12px; color: {theme.text_muted};'

            # Apply special styling for State and Direction columns
            if col == "State":
                color = _get_state_color(val, theme)
                val = _render_badge(val, color)
                cell_style = f'padding: 12px;'
            elif col == "Direction":
                color = _get_direction_color(val, theme)
                val = _render_badge(val, color)
                cell_style = f'padding: 12px;'
            elif col == "Signal":
                cell_style = f'padding: 12px; color: {theme.text}; font-weight: 500;'
            elif col == "Latest Score":
                # Color-code the score
                try:
                    score_val = float(str(val).replace('%', '').replace('—', '0'))
                    if score_val > 0:
                        color = theme.success
                    elif score_val < 0:
                        color = theme.danger
                    else:
                        color = theme.text_muted
                    val = f'<span style="color: {color}; font-weight: 600;">{val}</span>'
                except (ValueError, TypeError):
                    pass
                cell_style = f'padding: 12px;'

            html_parts.append(f'<td style="{cell_style}">{val}</td>')

        html_parts.append('</tr>')

    html_parts.append('</tbody></table>')
    return ''.join(html_parts)


def render_signal_snapshot_section(
    scores_df: pd.DataFrame,
    model_results: dict,
    interpret_growth,
    interpret_inflation,
    interpret_financial_conditions_ease,
    interpret_risk_appetite,
    interpret_credit_stress,
    interpret_recession_risk,
    recession_prob: float,
    theme: Optional[Theme] = None,
) -> None:
    """
    Render the signal snapshot table with color-coded badges and zebra striping.

    Args:
        scores_df: DataFrame with score history
        model_results: Model results dictionary
        interpret_growth: Growth interpretation function
        interpret_inflation: Inflation interpretation function
        interpret_financial_conditions_ease: Financial conditions interpretation function
        interpret_risk_appetite: Risk appetite interpretation function
        interpret_credit_stress: Credit stress interpretation function
        interpret_recession_risk: Recession risk interpretation function
        recession_prob: Recession probability percentage
        theme: Optional theme override
    """
    theme = theme or get_current_theme()

    st.markdown(
        f'<div style="font-size: 13px; font-weight: 600; text-transform: uppercase; '
        f'letter-spacing: 0.05em; color: {theme.text_muted}; margin-bottom: 16px;">'
        f'Latest Signal Snapshot</div>',
        unsafe_allow_html=True
    )

    # Build snapshot data
    snapshot_data = []

    # Growth
    if "growth_score" in scores_df.columns:
        g_series = scores_df["growth_score"]
        g_latest = g_series.iloc[-1]
        g_change = get_3m_change(g_series)
        g_interp = interpret_growth(g_latest, g_change)

        snapshot_data.append({
            "Signal": "Growth",
            "Latest Score": f"{g_latest:+.2f}",
            "3M Change": f"{g_change:+.2f}",
            "State": g_interp.level,
            "Direction": g_interp.direction,
            "Interpretation": g_interp.interpretation
        })

    # Inflation
    if "inflation_score" in scores_df.columns:
        i_series = scores_df["inflation_score"]
        i_latest = i_series.iloc[-1]
        i_change = get_3m_change(i_series)
        i_interp = interpret_inflation(i_latest, i_change)

        snapshot_data.append({
            "Signal": "Inflation",
            "Latest Score": f"{i_latest:+.2f}",
            "3M Change": f"{i_change:+.2f}",
            "State": i_interp.level,
            "Direction": i_interp.direction,
            "Interpretation": i_interp.interpretation
        })

    # Financial Conditions
    if "liquidity_score" in scores_df.columns:
        l_series = scores_df["liquidity_score"]
        l_latest = l_series.iloc[-1]
        l_change = get_3m_change(l_series)
        fc_interp = interpret_financial_conditions_ease(l_latest, l_change)

        snapshot_data.append({
            "Signal": "Fin. Conditions",
            "Latest Score": f"{l_latest:+.2f}",
            "3M Change": f"{l_change:+.2f}",
            "State": fc_interp.level,
            "Direction": fc_interp.direction,
            "Interpretation": fc_interp.interpretation
        })

    # Risk Appetite
    if "risk_score" in scores_df.columns:
        r_series = scores_df["risk_score"]
        r_latest = r_series.iloc[-1] if len(r_series) > 0 else 0.0
        r_change = get_3m_change(r_series) if len(r_series) > 0 else 0.0
        r_interp = interpret_risk_appetite(r_latest, r_change)

        snapshot_data.append({
            "Signal": "Risk Appetite",
            "Latest Score": f"{r_latest:+.2f}",
            "3M Change": f"{r_change:+.2f}",
            "State": r_interp.level,
            "Direction": r_interp.direction,
            "Interpretation": r_interp.interpretation
        })

    # Credit Stress
    cs_score = model_results.get("credit_stress", {}).get("stress_score", 0)
    cs_interp = interpret_credit_stress(cs_score)
    snapshot_data.append({
        "Signal": "Credit Stress",
        "Latest Score": f"{cs_score:+.2f}",
        "3M Change": "—",
        "State": cs_interp.level,
        "Direction": "—",
        "Interpretation": cs_interp.interpretation
    })

    # Recession Risk
    rec_interp = interpret_recession_risk(recession_prob)
    snapshot_data.append({
        "Signal": "Recession Risk",
        "Latest Score": f"{recession_prob:.1f}%",
        "3M Change": "—",
        "State": rec_interp.level,
        "Direction": "—",
        "Interpretation": rec_interp.interpretation
    })

    # Convert to DataFrame and render using styled HTML table
    snapshot_df = pd.DataFrame(snapshot_data)
    html_table = _render_signal_table_html(snapshot_df, theme)
    st.markdown(html_table, unsafe_allow_html=True)
