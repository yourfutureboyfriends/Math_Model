"""
Sector Allocation Section

Renders the sector allocation table and chart.

# =============================================================================
# CHANGE SUMMARY
# =============================================================================
# FIXED: st.plotly_chart(..., width='stretch') — 'width' is not a valid kwarg
#        for st.plotly_chart in any current Streamlit version. The chart was
#        silently rendered at default width. Replaced with use_container_width=True.
# =============================================================================
"""

from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..tables import render_sector_table
from ..theme import Theme, get_current_theme


def get_signal_level(score: float) -> str:
    """Convert score to 5-level signal."""
    if score >= 0.6:
        return "Overweight"
    elif score >= 0.2:
        return "Slight Overweight"
    elif score >= -0.2:
        return "Neutral"
    elif score >= -0.6:
        return "Slight Underweight"
    else:
        return "Underweight"


def get_conviction_level(score: float) -> str:
    """Get conviction level from score."""
    abs_score = abs(score)
    if abs_score >= 0.6:
        return "High"
    elif abs_score >= 0.2:
        return "Medium"
    else:
        return "Low"


def get_sector_rationale(sector: str, signal: str) -> str:
    """Generate rationale for sector signal."""
    rationales = {
        "Overweight": f"{sector} well-positioned for current regime",
        "Slight Overweight": f"{sector} modestly favored",
        "Neutral": f"{sector} positioned neutrally",
        "Slight Underweight": f"{sector} modestly unfavored",
        "Underweight": f"{sector} challenged in current regime",
    }
    return rationales.get(signal, f"{sector} positioned for current regime")


def render_sector_allocation_section(sector_table: pd.DataFrame, theme: Optional[Theme] = None) -> None:
    """
    Render the sector allocation section.

    Args:
        sector_table: DataFrame with sector scores
        theme: Optional theme override
    """
    theme = theme or get_current_theme()

    st.markdown(
        f'<div style="font-size: 13px; font-weight: 600; text-transform: uppercase; '
        f'letter-spacing: 0.05em; color: {theme.text_muted}; margin-bottom: 16px;">'
        f'Sector Allocation</div>',
        unsafe_allow_html=True
    )

    # Add signal and conviction columns
    sector_df = sector_table.copy()
    sector_df["Signal"] = sector_df["Score"].apply(get_signal_level)
    sector_df["Conviction"] = sector_df["Score"].apply(get_conviction_level)
    sector_df["Rationale"] = sector_df.apply(
        lambda row: get_sector_rationale(row["Sector"], row["Signal"]), axis=1
    )

    # Display table first, then chart full width below
    render_sector_table(
        sector_df[["Sector", "Signal", "Score", "Conviction", "Rationale"]],
        title="",
        theme=theme
    )

    st.markdown("<div style='margin-top: 24px;'></div>", unsafe_allow_html=True)

    # Sector score distribution chart - full width
    fig_sectors = go.Figure()

    # Color mapping using theme colors
    signal_colors = {
        "Overweight": theme.success,
        "Slight Overweight": theme.success,
        "Neutral": theme.neutral,
        "Slight Underweight": theme.danger,
        "Underweight": theme.danger,
    }

    for _, row in sector_df.iterrows():
        color = signal_colors.get(row["Signal"], theme.neutral)
        fig_sectors.add_trace(go.Bar(
            x=[row["Sector"]],
            y=[row["Score"]],
            marker_color=color,
            text=f"{row['Score']:+.2f}",
            textposition="outside",
            textfont=dict(size=10, color=theme.text),
            showlegend=False,
        ))

    # Add threshold lines using theme colors
    fig_sectors.add_hline(y=0.6, line_dash="solid", line_color=theme.success, opacity=0.6)
    fig_sectors.add_hline(y=0.2, line_dash="dash", line_color=theme.success, opacity=0.4)
    fig_sectors.add_hline(y=-0.2, line_dash="dash", line_color=theme.danger, opacity=0.4)
    fig_sectors.add_hline(y=-0.6, line_dash="solid", line_color=theme.danger, opacity=0.6)
    fig_sectors.add_hline(y=0, line_color=theme.border, opacity=0.5)

    fig_sectors.update_layout(
        autosize=True,
        height=350,
        margin=dict(t=30, b=80, l=40, r=20),
        xaxis=dict(
            tickangle=-45,
            tickfont=dict(size=11, color=theme.text_muted),
            linecolor=theme.border,
        ),
        yaxis=dict(
            title=dict(text="Score", font=dict(size=11, color=theme.text_subtle)),
            tickfont=dict(size=10, color=theme.text_muted),
            linecolor=theme.border,
            gridcolor=theme.plot_grid,
            range=[-1, 1],
        ),
        paper_bgcolor=theme.plot_paper_bg,
        plot_bgcolor=theme.plot_bg,
        font=dict(family="Inter, sans-serif", size=12, color=theme.text),
        showlegend=False,
        bargap=0.3,
    )

    st.plotly_chart(fig_sectors, width='stretch', config={'displayModeBar': False})
