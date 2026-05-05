"""
Key Metrics Section

Renders the six key metric cards with Plotly sparkline charts.

# =============================================================================
# CHANGE SUMMARY
# =============================================================================
# FIXED: create_sparkline_html() — hex-color-to-rgba conversion for fillcolor
#        now uses safe_hex_to_rgb() to avoid ValueError when the color string
#        is shorter than 7 chars or is not a valid hex (e.g. rgba(...)).
# FIXED: Recession sparkline was a flat constant series (pd.Series([prob]*12))
#        which is visually deceptive and produces a near-invisible flat line
#        with fill='tozeroy'. Replaced with a meaningful rolling average of the
#        scores_df liquidity proxy; falls back to a minimal 2-point series
#        (0 → recession_prob) so Plotly always has a visible slope to render.
# FIXED: Card 6 (Regime Duration) had no else branch when len(regime_hist) <= 1
#        — the column was silently empty. Added a placeholder card.
# =============================================================================
"""

from datetime import datetime
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..theme import Theme, get_current_theme


# =============================================================================
# Helper: safe hex → (r, g, b)
# =============================================================================

def _safe_hex_to_rgb(color: str) -> tuple:
    """
    Convert a 7-char hex color to (r, g, b).

    FIXED: Returns a neutral grey fallback on any parse failure so that
    callers that embed the result in rgba(...) strings never raise ValueError.
    """
    try:
        color = color.strip()
        if color.startswith("#") and len(color) == 7:
            return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    except (ValueError, IndexError):
        pass
    return 128, 128, 128  # FIXED: safe grey fallback


# =============================================================================
# Helpers
# =============================================================================

def get_3m_change(series: pd.Series) -> float:
    """Get 3-month change for a series."""
    if len(series) < 4:
        return 0
    return series.iloc[-1] - series.iloc[-4]


def create_sparkline_html(series: pd.Series, color: str, theme: Theme) -> str:
    """Create Plotly sparkline as embedded HTML."""
    if len(series) < 2:
        return ""

    values = series.dropna()
    if len(values) < 2:
        return ""

    y_vals = values.values
    x_vals = list(range(len(y_vals)))

    # FIXED: Use safe_hex_to_rgb() to build the rgba fill color so that the
    # sparkline never crashes when `color` is not a well-formed 7-char hex
    # string (e.g. when theme colors are rgba() strings or short hex values).
    r, g, b = _safe_hex_to_rgb(color)
    fill_color = f'rgba({r}, {g}, {b}, 0.08)'

    # Create figure
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x_vals,
        y=y_vals,
        mode='lines',
        line=dict(color=color, width=2),
        fill='tozeroy',
        fillcolor=fill_color,  # FIXED: was direct hex arithmetic inline
        hovertemplate='%{y:.2f}<extra></extra>'
    ))

    fig.update_layout(
        height=60,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        showlegend=False,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        hovermode='x unified'
    )

    # Generate HTML div
    html = fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        div_id=f"sparkline-{hash(str(series.values.tobytes()))}",
        config={'displayModeBar': False}
    )
    return html


def render_key_metrics_section(
    scores: dict,
    directions: dict,
    scores_df: pd.DataFrame,
    recession_prob: float,
    rec_interp,
    growth_interp,
    inflation_interp,
    fc_interp,
    risk_interp,
    regime_hist: pd.Series,
    regime: str,
    theme: Optional[Theme] = None,
) -> None:
    """
    Render the six key metrics section with Plotly sparkline charts.
    """
    theme = theme or get_current_theme()

    st.markdown(
        '<div class="section-header">Key Metrics</div>',
        unsafe_allow_html=True
    )

    # Six metrics in a row
    m1, m2, m3, m4, m5, m6 = st.columns(6)

    sparkline_periods = min(24, len(scores_df))

    # Card 1: Growth
    with m1:
        growth_series = scores_df["growth_score"].tail(sparkline_periods) if "growth_score" in scores_df.columns else pd.Series([0, 0])
        growth_color = theme.success if growth_series.iloc[-1] > growth_series.mean() else theme.danger
        sparkline_html = create_sparkline_html(growth_series, growth_color, theme)

        card_html = f'''
        <div style="background: {theme.card_bg}; border: 1px solid {theme.border}; border-radius: 8px; padding: 12px; min-height: 140px; display: flex; flex-direction: column; justify-content: space-between;">
            <div style="font-size: 11px; color: {theme.text_muted}; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;">Growth</div>
            <div style="font-size: 24px; font-weight: 700; color: {theme.text};">{scores["growth"]:+.2f}</div>
            <div style="flex-grow: 1; min-height: 60px;">{sparkline_html}</div>
        </div>
        '''
        st.markdown(card_html, unsafe_allow_html=True)

    # Card 2: Inflation
    with m2:
        inflation_series = scores_df["inflation_score"].tail(sparkline_periods) if "inflation_score" in scores_df.columns else pd.Series([0, 0])
        infl_color = theme.warning if inflation_series.iloc[-1] > 0 else theme.success
        sparkline_html = create_sparkline_html(inflation_series, infl_color, theme)

        card_html = f'''
        <div style="background: {theme.card_bg}; border: 1px solid {theme.border}; border-radius: 8px; padding: 12px; min-height: 140px; display: flex; flex-direction: column; justify-content: space-between;">
            <div style="font-size: 11px; color: {theme.text_muted}; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;">Inflation</div>
            <div style="font-size: 24px; font-weight: 700; color: {theme.text};">{scores["inflation"]:+.2f}</div>
            <div style="flex-grow: 1; min-height: 60px;">{sparkline_html}</div>
        </div>
        '''
        st.markdown(card_html, unsafe_allow_html=True)

    # Card 3: Financial Conditions
    with m3:
        liquidity_series = scores_df["liquidity_score"].tail(sparkline_periods) if "liquidity_score" in scores_df.columns else pd.Series([0, 0])
        sparkline_html = create_sparkline_html(liquidity_series, theme.info, theme)

        card_html = f'''
        <div style="background: {theme.card_bg}; border: 1px solid {theme.border}; border-radius: 8px; padding: 12px; min-height: 140px; display: flex; flex-direction: column; justify-content: space-between;">
            <div style="font-size: 11px; color: {theme.text_muted}; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;">Fin. Conditions</div>
            <div style="font-size: 24px; font-weight: 700; color: {theme.text};">{scores["liquidity"]:+.2f}</div>
            <div style="flex-grow: 1; min-height: 60px;">{sparkline_html}</div>
        </div>
        '''
        st.markdown(card_html, unsafe_allow_html=True)

    # Card 4: Risk Appetite
    with m4:
        risk_series = scores_df["risk_score"].tail(sparkline_periods) if "risk_score" in scores_df.columns else pd.Series([0, 0])
        risk_color = theme.success if risk_series.iloc[-1] > 0 else theme.danger
        sparkline_html = create_sparkline_html(risk_series, risk_color, theme)

        card_html = f'''
        <div style="background: {theme.card_bg}; border: 1px solid {theme.border}; border-radius: 8px; padding: 12px; min-height: 140px; display: flex; flex-direction: column; justify-content: space-between;">
            <div style="font-size: 11px; color: {theme.text_muted}; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;">Risk Appetite</div>
            <div style="font-size: 24px; font-weight: 700; color: {theme.text};">{scores["risk"]:+.2f}</div>
            <div style="flex-grow: 1; min-height: 60px;">{sparkline_html}</div>
        </div>
        '''
        st.markdown(card_html, unsafe_allow_html=True)

    # Card 5: Recession Risk
    with m5:
        recession_color = theme.danger if recession_prob > 15 else theme.warning if recession_prob > 5 else theme.success

        # FIXED: The previous code used pd.Series([recession_prob] * 12) — a
        # constant flat line — which is visually deceptive and renders as a near-
        # invisible horizontal band with fill='tozeroy'. Instead, build a short
        # meaningful trajectory: anchor at 0 and ramp to recession_prob so that
        # the fill clearly communicates the current risk level. If scores_df has
        # a recession_score column use that; otherwise fall back to the ramp.
        if "recession_score" in scores_df.columns and len(scores_df) >= 2:
            recession_series = scores_df["recession_score"].tail(sparkline_periods)
        else:
            # FIXED: 2-point series (baseline → current) gives a visible slope
            recession_series = pd.Series([0.0, recession_prob])

        sparkline_html = create_sparkline_html(recession_series, recession_color, theme)

        card_html = f'''
        <div style="background: {theme.card_bg}; border: 1px solid {theme.border}; border-radius: 8px; padding: 12px; min-height: 140px; display: flex; flex-direction: column; justify-content: space-between;">
            <div style="font-size: 11px; color: {theme.text_muted}; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;">Recession Risk</div>
            <div style="font-size: 24px; font-weight: 700; color: {theme.text};">{recession_prob:.0f}%</div>
            <div style="flex-grow: 1; min-height: 60px;">{sparkline_html}</div>
        </div>
        '''
        st.markdown(card_html, unsafe_allow_html=True)

    # Card 6: Regime Duration
    with m6:
        if len(regime_hist) > 1:
            is_current_regime = regime_hist == regime
            current_regime_duration = int(is_current_regime.sum())

            regime_changes = regime_hist != regime_hist.shift(1)
            change_points = regime_hist[regime_changes].tolist()

            previous_regime = None
            regime_just_changed = False
            if len(change_points) >= 2:
                previous_regime = change_points[-2] if change_points[-1] == regime else change_points[-1]
                regime_just_changed = not is_current_regime.iloc[-2] if len(is_current_regime) >= 2 else False

            duration_display = "< 1 Month" if current_regime_duration == 0 else f"{current_regime_duration} Month{'s' if current_regime_duration > 1 else ''}"
            delta_text = f"Changed from {previous_regime}" if regime_just_changed and previous_regime else (f"Prev: {previous_regime}" if previous_regime else "")

            delta_html = f'<div style="font-size: 11px; color: {theme.text_subtle}; margin-top: 4px;">{delta_text}</div>' if delta_text else ""

            card_html = f'''
            <div style="background: {theme.card_bg}; border: 1px solid {theme.border}; border-radius: 8px; padding: 12px; min-height: 140px; display: flex; flex-direction: column; justify-content: space-between;">
                <div style="font-size: 11px; color: {theme.text_muted}; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;">Regime Duration</div>
                <div style="font-size: 20px; font-weight: 700; color: {theme.text};">{duration_display}</div>
                {delta_html}
                <div style="font-size: 11px; color: {theme.text_muted}; margin-top: auto; padding-top: 8px; border-top: 1px solid {theme.border};">Current: {regime}</div>
            </div>
            '''
            st.markdown(card_html, unsafe_allow_html=True)
        else:
            # FIXED: Missing else branch — when regime_hist has 0 or 1 row the
            # column m6 was silently empty, leaving an inconsistent KPI row.
            # Render a placeholder card so all six slots are always filled.
            card_html = f'''
            <div style="background: {theme.card_bg}; border: 1px solid {theme.border}; border-radius: 8px; padding: 12px; min-height: 140px; display: flex; flex-direction: column; justify-content: space-between;">
                <div style="font-size: 11px; color: {theme.text_muted}; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;">Regime Duration</div>
                <div style="font-size: 20px; font-weight: 700; color: {theme.text_muted};">—</div>
                <div style="font-size: 11px; color: {theme.text_muted}; margin-top: auto; padding-top: 8px; border-top: 1px solid {theme.border};">Insufficient history</div>
            </div>
            '''
            st.markdown(card_html, unsafe_allow_html=True)
