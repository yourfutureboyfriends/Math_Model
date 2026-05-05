"""
Advanced Indicators Section

Renders Bridgewater-level leading indicators:
  1. Sahm Rule — Real-time recession trigger (Sahm 2019)
  2. Credit Impulse — Demand leading indicator (Biggs-Mayer-Pick 2010)
  3. LEI Composite — Conference Board style leading index
  4. All Weather Risk Parity — Qian (2005) / Bridgewater asset allocation

All models are designed to fail gracefully when data series are not yet loaded.
Run `python pipeline.py --mode refresh-live-data` to fetch expanded FRED series.
"""

import logging
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..theme import Theme, get_current_theme

logger = logging.getLogger(__name__)


# =============================================================================
# Colour helpers
# =============================================================================

def _signal_color(signal: str, theme: Theme) -> str:
    """Map signal strings to Bloomberg terminal colours."""
    upper = signal.upper()
    if upper in ("POSITIVE", "CLEAR", "EXPANDING", "EXPANSION"):
        return theme.success
    elif upper in ("NEGATIVE", "RECESSION", "CONTRACTING", "CONTRACTION"):
        return theme.danger
    elif upper in ("WARNING", "WATCH", "MODERATING"):
        return theme.warning
    else:
        return theme.text_muted


def _amber_bar(value: float, max_val: float, theme: Theme) -> str:
    """Render a simple ASCII progress bar in amber."""
    pct = min(1.0, max(0.0, abs(value) / max(max_val, 0.01)))
    filled = int(pct * 20)
    bar = "█" * filled + "░" * (20 - filled)
    color = theme.primary if value >= 0 else theme.danger
    return f'<span style="font-family:\'IBM Plex Mono\',monospace; color:{color}; font-size:11px;">{bar}</span>'


# =============================================================================
# 1 — Sahm Rule
# =============================================================================

def _render_sahm_rule(df_raw: pd.DataFrame, theme: Theme) -> None:
    """Render the Sahm Rule recession indicator panel."""
    try:
        from src.models.recession_risk.recession_model import (
            compute_sahm_rule, get_sahm_rule_signal
        )
        signal = get_sahm_rule_signal(df_raw)
        sahm_history = compute_sahm_rule(df_raw)
    except Exception as exc:
        logger.warning("Sahm Rule computation failed: %s", exc)
        st.caption("Sahm Rule data unavailable — run `pipeline.py --mode refresh-live-data`")
        return

    val = signal["value"]
    sig = signal["signal"]
    color = _signal_color(sig, theme)

    # Header
    st.markdown(
        f'<div style="font-family:\'IBM Plex Mono\',monospace; font-size:10px; '
        f'font-weight:700; letter-spacing:0.12em; color:{theme.primary}; '
        f'text-transform:uppercase; margin-bottom:8px;">Sahm Rule</div>',
        unsafe_allow_html=True
    )

    # Current value badge
    st.markdown(
        f'<div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">'
        f'<span style="font-family:\'IBM Plex Mono\',monospace; font-size:28px; '
        f'font-weight:700; color:{color};">{val:+.2f}<span style="font-size:14px;">pp</span></span>'
        f'<span style="background:{color}20; border:1px solid {color}; color:{color}; '
        f'font-family:\'IBM Plex Mono\',monospace; font-size:10px; font-weight:700; '
        f'padding:3px 8px; letter-spacing:0.10em;">{sig}</span>'
        f'</div>',
        unsafe_allow_html=True
    )

    # Threshold bar: 0.50pp = recession trigger
    st.markdown(
        f'<div style="font-family:\'IBM Plex Mono\',monospace; font-size:10px; '
        f'color:{theme.text_muted}; margin-bottom:4px;">'
        f'Trigger at 0.50pp &nbsp;|&nbsp; {_amber_bar(val, 0.5, theme)}'
        f'</div>',
        unsafe_allow_html=True
    )
    st.markdown(
        f'<div style="font-size:11px; color:{theme.text_subtle}; line-height:1.4; '
        f'font-family:\'IBM Plex Mono\',monospace;">{signal["description"]}</div>',
        unsafe_allow_html=True
    )

    # Mini sparkline
    if not sahm_history.dropna().empty and len(sahm_history.dropna()) >= 6:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=sahm_history.index,
            y=sahm_history.values,
            mode="lines",
            line=dict(color=theme.primary, width=1.5),
            name="Sahm Rule",
            hovertemplate="<b>%{x|%b %Y}</b><br>%{y:.3f}pp<extra></extra>",
        ))
        # Recession threshold line
        fig.add_hline(
            y=0.50,
            line_dash="dash",
            line_color=theme.danger,
            line_width=1,
            annotation_text="0.50pp trigger",
            annotation_font_color=theme.danger,
            annotation_font_size=9,
        )
        fig.update_layout(
            height=120,
            margin=dict(l=0, r=0, t=4, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, linecolor=theme.border),
            yaxis=dict(showgrid=False, zeroline=True, zerolinecolor=theme.border,
                       showticklabels=True, tickfont=dict(size=8, color=theme.text_muted),
                       linecolor=theme.border),
        )
        st.plotly_chart(fig, width='stretch', config={"displayModeBar": False})


# =============================================================================
# 2 — Credit Impulse
# =============================================================================

def _render_credit_impulse(df_raw: pd.DataFrame, theme: Theme) -> None:
    """Render the Credit Impulse panel."""
    try:
        from src.models.credit.credit_impulse_model import get_credit_impulse
        result = get_credit_impulse(df_raw)
    except Exception as exc:
        logger.warning("Credit impulse computation failed: %s", exc)
        st.caption("Credit impulse unavailable")
        return

    color = _signal_color(result.signal, theme)

    st.markdown(
        f'<div style="font-family:\'IBM Plex Mono\',monospace; font-size:10px; '
        f'font-weight:700; letter-spacing:0.12em; color:{theme.primary}; '
        f'text-transform:uppercase; margin-bottom:8px;">Credit Impulse</div>',
        unsafe_allow_html=True
    )

    direction_arrow = "↑" if result.direction == "accelerating" else ("↓" if result.direction == "decelerating" else "→")

    st.markdown(
        f'<div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">'
        f'<span style="font-family:\'IBM Plex Mono\',monospace; font-size:28px; '
        f'font-weight:700; color:{color};">{result.impulse:+.2f}<span style="font-size:14px;">σ</span></span>'
        f'<span style="background:{color}20; border:1px solid {color}; color:{color}; '
        f'font-family:\'IBM Plex Mono\',monospace; font-size:10px; font-weight:700; '
        f'padding:3px 8px; letter-spacing:0.10em;">{result.signal}</span>'
        f'<span style="font-size:18px; color:{color};">{direction_arrow}</span>'
        f'</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        f'<div style="font-size:11px; color:{theme.text_subtle}; line-height:1.5; '
        f'font-family:\'IBM Plex Mono\',monospace; margin-bottom:4px;">'
        f'{result.description}</div>',
        unsafe_allow_html=True
    )

    # Components breakdown
    if result.components:
        comp_lines = " &nbsp;|&nbsp; ".join(
            f'<span style="color:{theme.text_muted};">{k}:</span> <span style="color:{theme.text};">{v:+.1f}</span>'
            for k, v in result.components.items()
        )
        st.markdown(
            f'<div style="font-size:10px; font-family:\'IBM Plex Mono\',monospace; '
            f'margin-top:4px;">{comp_lines}</div>',
            unsafe_allow_html=True
        )

    # Sparkline
    if not result.history.dropna().empty and len(result.history.dropna()) >= 6:
        hist = result.history
        fig = go.Figure()
        # Colour bars by positive/negative
        colors = [theme.success if v >= 0 else theme.danger for v in hist.values]
        fig.add_trace(go.Bar(
            x=hist.index[-48:],  # Last 4 years
            y=hist.values[-48:],
            marker_color=colors[-48:],
            name="Credit Impulse",
            hovertemplate="<b>%{x|%b %Y}</b><br>%{y:.3f}σ<extra></extra>",
        ))
        fig.add_hline(y=0, line_color=theme.border_light, line_width=1)
        fig.update_layout(
            height=120,
            margin=dict(l=0, r=0, t=4, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
            bargap=0.05,
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, linecolor=theme.border),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=True,
                       tickfont=dict(size=8, color=theme.text_muted), linecolor=theme.border),
        )
        st.plotly_chart(fig, width='stretch', config={"displayModeBar": False})


# =============================================================================
# 3 — LEI Composite
# =============================================================================

def _render_lei_composite(df_raw: pd.DataFrame, theme: Theme) -> None:
    """Render the LEI Composite panel."""
    try:
        from src.models.leading_indicators.lei_composite import get_lei_composite
        result = get_lei_composite(df_raw)
    except Exception as exc:
        logger.warning("LEI composite computation failed: %s", exc)
        st.caption("LEI composite unavailable")
        return

    color = _signal_color(result.trend, theme)
    recession_color = theme.danger if result.recession_signal else theme.text_subtle

    st.markdown(
        f'<div style="font-family:\'IBM Plex Mono\',monospace; font-size:10px; '
        f'font-weight:700; letter-spacing:0.12em; color:{theme.primary}; '
        f'text-transform:uppercase; margin-bottom:8px;">LEI Composite</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        f'<div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">'
        f'<span style="font-family:\'IBM Plex Mono\',monospace; font-size:28px; '
        f'font-weight:700; color:{color};">{result.composite_score:+.2f}<span style="font-size:14px;">σ</span></span>'
        f'<span style="background:{color}20; border:1px solid {color}; color:{color}; '
        f'font-family:\'IBM Plex Mono\',monospace; font-size:10px; font-weight:700; '
        f'padding:3px 8px; letter-spacing:0.10em;">{result.trend.upper()}</span>'
        f'</div>',
        unsafe_allow_html=True
    )

    # Three stats inline
    st.markdown(
        f'<div style="display:flex; gap:16px; font-family:\'IBM Plex Mono\',monospace; '
        f'font-size:10px; margin-bottom:8px;">'
        f'<div><span style="color:{theme.text_muted};">6M CHG</span> '
        f'<span style="color:{color};">{result.six_month_change:+.1f}%</span></div>'
        f'<div><span style="color:{theme.text_muted};">DIFFUSION</span> '
        f'<span style="color:{theme.text};">{result.diffusion:.0f}%</span></div>'
        f'<div><span style="color:{theme.text_muted};">COMPONENTS</span> '
        f'<span style="color:{theme.text};">{result.components_available}</span></div>'
        f'<div><span style="color:{theme.text_muted};">3D RULE</span> '
        f'<span style="color:{recession_color};">{"TRIGGERED" if result.recession_signal else "CLEAR"}</span></div>'
        f'</div>',
        unsafe_allow_html=True
    )

    # Sparkline
    if not result.history.dropna().empty and len(result.history.dropna()) >= 6:
        hist = result.history
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=hist.index,
            y=hist.values,
            mode="lines",
            fill="tozeroy",
            fillcolor=f"rgba(255,102,0,0.08)",
            line=dict(color=theme.primary, width=1.5),
            name="LEI",
            hovertemplate="<b>%{x|%b %Y}</b><br>%{y:.3f}σ<extra></extra>",
        ))
        fig.add_hline(y=0, line_color=theme.border_light, line_width=1)
        fig.update_layout(
            height=120,
            margin=dict(l=0, r=0, t=4, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, linecolor=theme.border),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=True,
                       tickfont=dict(size=8, color=theme.text_muted), linecolor=theme.border),
        )
        st.plotly_chart(fig, width='stretch', config={"displayModeBar": False})


# =============================================================================
# 4 — All Weather Risk Parity
# =============================================================================

def _render_risk_parity(df_raw: pd.DataFrame, theme: Theme) -> None:
    """Render the All Weather Risk Parity allocation panel."""
    try:
        from src.models.portfolio_construction.risk_parity import get_all_weather_summary
        rp = get_all_weather_summary(df_raw)
    except Exception as exc:
        logger.warning("Risk parity computation failed: %s", exc)
        st.caption("Risk parity data unavailable")
        return

    st.markdown(
        f'<div style="font-family:\'IBM Plex Mono\',monospace; font-size:10px; '
        f'font-weight:700; letter-spacing:0.12em; color:{theme.primary}; '
        f'text-transform:uppercase; margin-bottom:8px;">All Weather — Risk Parity</div>',
        unsafe_allow_html=True
    )

    # Portfolio stats
    st.markdown(
        f'<div style="display:flex; gap:20px; font-family:\'IBM Plex Mono\',monospace; '
        f'font-size:10px; margin-bottom:10px;">'
        f'<div><span style="color:{theme.text_muted};">PORT VOL</span> '
        f'<span style="color:{theme.text};">{rp["portfolio_vol"]:.1f}%</span></div>'
        f'<div><span style="color:{theme.text_muted};">DIV RATIO</span> '
        f'<span style="color:{theme.primary};">{rp["diversification_ratio"]:.2f}×</span></div>'
        f'<div><span style="color:{theme.text_muted};">POSITIONING</span> '
        f'<span style="color:{theme.text}; font-size:9px;">{rp["positioning"].upper()}</span></div>'
        f'</div>',
        unsafe_allow_html=True
    )

    weights = rp["weights"]
    rc = rp["risk_contributions"]

    # Asset class table
    LABELS = {
        "equities": "Equities",
        "nominal_bonds": "Nom. Bonds",
        "commodities": "Commodities",
        "credit": "Credit / HY",
        "inflation_linked": "TIPS / Infl",
    }

    if weights:
        rows_html = ""
        for k, w in sorted(weights.items(), key=lambda x: -x[1]):
            label = LABELS.get(k, k.replace("_", " ").title())
            rc_val = rc.get(k, 0.0)
            bar_w = int(w * 100)
            rc_bar = int(rc_val * 1.5)
            rows_html += (
                f'<tr>'
                f'<td style="font-family:\'IBM Plex Mono\',monospace; font-size:10px; '
                f'color:{theme.text_muted}; padding:3px 6px;">{label}</td>'
                f'<td style="font-family:\'IBM Plex Mono\',monospace; font-size:11px; '
                f'font-weight:600; color:{theme.text}; padding:3px 6px;">{w:.1%}</td>'
                f'<td style="padding:3px 6px;">'
                f'<span style="display:inline-block; width:{bar_w}px; height:8px; '
                f'background:{theme.primary}; vertical-align:middle;"></span>'
                f'</td>'
                f'<td style="font-family:\'IBM Plex Mono\',monospace; font-size:10px; '
                f'color:{theme.text_subtle}; padding:3px 6px;">{rc_val:.1f}%</td>'
                f'</tr>'
            )

        st.markdown(
            f'<table style="width:100%; border-collapse:collapse; margin-bottom:4px;">'
            f'<thead><tr>'
            f'<th style="font-family:\'IBM Plex Mono\',monospace; font-size:9px; '
            f'letter-spacing:0.10em; color:{theme.primary}; text-align:left; '
            f'padding:2px 6px; border-bottom:1px solid {theme.primary};">ASSET CLASS</th>'
            f'<th style="font-family:\'IBM Plex Mono\',monospace; font-size:9px; '
            f'letter-spacing:0.10em; color:{theme.primary}; text-align:left; '
            f'padding:2px 6px; border-bottom:1px solid {theme.primary};">WEIGHT</th>'
            f'<th style="border-bottom:1px solid {theme.primary};"></th>'
            f'<th style="font-family:\'IBM Plex Mono\',monospace; font-size:9px; '
            f'letter-spacing:0.10em; color:{theme.primary}; text-align:left; '
            f'padding:2px 6px; border-bottom:1px solid {theme.primary};">RISK %</th>'
            f'</tr></thead>'
            f'<tbody>{rows_html}</tbody>'
            f'</table>',
            unsafe_allow_html=True
        )

    st.markdown(
        f'<div style="font-size:9px; color:{theme.text_disabled}; '
        f'font-family:\'IBM Plex Mono\',monospace; margin-top:4px;">'
        f'Qian (2005) inverse-volatility weighting &nbsp;|&nbsp; '
        f'Bridgewater All Weather framework</div>',
        unsafe_allow_html=True
    )


# =============================================================================
# Main Section Renderer
# =============================================================================

def render_advanced_indicators_section(
    df_raw: pd.DataFrame,
    theme: Optional[Theme] = None,
) -> None:
    """
    Render the Advanced Indicators section.

    Displays four research-backed leading indicators in a 2×2 grid:
      Row 1: Sahm Rule  |  Credit Impulse
      Row 2: LEI Composite  |  All Weather Risk Parity

    Args:
        df_raw: Raw macro DataFrame (live or sample)
        theme: Optional theme override
    """
    theme = theme or get_current_theme()

    # Section header
    st.markdown(
        f'<div style="font-family:\'IBM Plex Mono\',monospace; font-size:0.62rem; '
        f'font-weight:700; text-transform:uppercase; letter-spacing:0.14em; '
        f'color:{theme.primary}; border-left:3px solid {theme.primary}; '
        f'padding-left:8px; margin-bottom:16px;">Advanced Indicators</div>',
        unsafe_allow_html=True
    )

    # Research citation banner
    st.markdown(
        f'<div style="background:{theme.card_bg}; border-left:2px solid {theme.border_light}; '
        f'padding:8px 12px; margin-bottom:16px; '
        f'font-family:\'IBM Plex Mono\',monospace; font-size:9px; '
        f'color:{theme.text_subtle}; line-height:1.6;">'
        f'SAHM (2019) &nbsp;·&nbsp; BIGGS-MAYER-PICK (2010) &nbsp;·&nbsp; '
        f'CONFERENCE BOARD LEI &nbsp;·&nbsp; QIAN/BRIDGEWATER (2005) &nbsp;·&nbsp; '
        f'ESTRELLA-MISHKIN (1998) &nbsp;·&nbsp; ILMANEN (2011)'
        f'</div>',
        unsafe_allow_html=True
    )

    # Row 1: Sahm Rule + Credit Impulse
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            f'<div style="background:{theme.card_bg}; border-left:2px solid {theme.border_light}; '
            f'padding:14px 16px; margin-bottom:12px;">',
            unsafe_allow_html=True
        )
        _render_sahm_rule(df_raw, theme)
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown(
            f'<div style="background:{theme.card_bg}; border-left:2px solid {theme.border_light}; '
            f'padding:14px 16px; margin-bottom:12px;">',
            unsafe_allow_html=True
        )
        _render_credit_impulse(df_raw, theme)
        st.markdown('</div>', unsafe_allow_html=True)

    # Row 2: LEI Composite + Risk Parity
    col3, col4 = st.columns(2)
    with col3:
        st.markdown(
            f'<div style="background:{theme.card_bg}; border-left:2px solid {theme.border_light}; '
            f'padding:14px 16px;">',
            unsafe_allow_html=True
        )
        _render_lei_composite(df_raw, theme)
        st.markdown('</div>', unsafe_allow_html=True)

    with col4:
        st.markdown(
            f'<div style="background:{theme.card_bg}; border-left:2px solid {theme.border_light}; '
            f'padding:14px 16px;">',
            unsafe_allow_html=True
        )
        _render_risk_parity(df_raw, theme)
        st.markdown('</div>', unsafe_allow_html=True)
