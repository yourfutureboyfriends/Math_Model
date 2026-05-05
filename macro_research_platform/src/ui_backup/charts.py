"""
Dashboard Charts Module

Theme-aware chart rendering for the Macro Research Platform dashboard.
"""

from typing import Optional, List, Dict, Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .theme import Theme, get_current_theme


# =============================================================================
# Theme Application
# =============================================================================

def apply_theme_layout(fig: go.Figure, theme: Optional[Theme] = None) -> go.Figure:
    """Apply theme layout to a Plotly figure.

    This is the unified function for applying themes to Plotly charts.
    It detects dark/light mode and applies appropriate styling.
    """
    theme = theme or get_current_theme()
    is_dark = theme.page_bg == "#0B0F17" or "dark" in theme.page_bg.lower()

    fig.update_layout(
        template="plotly_dark" if is_dark else "plotly_white",
        paper_bgcolor=theme.plot_paper_bg,
        plot_bgcolor=theme.plot_bg,
        font=dict(
            family="Inter, -apple-system, sans-serif",
            color=theme.text
        ),
        margin=dict(l=50, r=25, t=35, b=45),
        legend=dict(
            bgcolor=theme.plot_legend_bg,
            bordercolor=theme.border,
            borderwidth=1,
            font=dict(color=theme.text)
        ),
        xaxis=dict(
            gridcolor=theme.plot_grid,
            zerolinecolor=theme.plot_zero,
            linecolor=theme.border,
            tickfont=dict(color=theme.text_muted)
        ),
        yaxis=dict(
            gridcolor=theme.plot_grid,
            zerolinecolor=theme.plot_zero,
            linecolor=theme.border,
            tickfont=dict(color=theme.text_muted)
        ),
        title_font=dict(color=theme.text),
    )
    return fig


# Backward compatibility aliases
def apply_dark_layout(fig: go.Figure, theme: Optional[Theme] = None) -> go.Figure:
    """Apply dark theme layout to a Plotly figure (backward compatibility)."""
    return apply_theme_layout(fig, theme)


def apply_dark_plotly_layout(fig: go.Figure, theme: Optional[Theme] = None) -> go.Figure:
    """Apply dark theme to a Plotly figure (backward compatibility)."""
    return apply_theme_layout(fig, theme)


# =============================================================================
# Chart Components
# =============================================================================

def render_regime_timeline(df: pd.DataFrame, title: str = "Regime History",
                           theme: Optional[Theme] = None) -> go.Figure:
    """Render a regime timeline chart."""
    theme = theme or get_current_theme()

    regime_colors = {
        "Expansion": theme.success,
        "Late-Cycle": theme.warning,
        "Recession": theme.danger,
        "Recovery": theme.info,
        "Inflation": theme.warning,
        "Deflation": theme.accent,
    }

    fig = go.Figure()

    for regime in df['regime'].unique():
        regime_data = df[df['regime'] == regime]
        color = regime_colors.get(regime, theme.neutral)

        fig.add_trace(go.Scatter(
            x=regime_data['date'],
            y=regime_data['value'],
            mode='lines',
            name=regime,
            line=dict(color=color, width=2),
            hovertemplate='%{x}<br>%{y:.2f}<br>' + regime + '<extra></extra>'
        ))

    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Score",
        hovermode='x unified',
        showlegend=True,
    )

    return apply_theme_layout(fig, theme)


def render_scorecard_bars(categories: List[str], scores: List[float],
                          title: str = "Signal Scores",
                          theme: Optional[Theme] = None) -> go.Figure:
    """Render horizontal bar chart for signal scores."""
    theme = theme or get_current_theme()

    colors = []
    for score in scores:
        if score > 0.5:
            colors.append(theme.success)
        elif score > 0:
            colors.append(theme.warning)
        elif score > -0.5:
            colors.append(theme.neutral)
        else:
            colors.append(theme.danger)

    fig = go.Figure(data=[
        go.Bar(
            y=categories,
            x=scores,
            orientation='h',
            marker_color=colors,
            text=[f"{s:+.2f}" for s in scores],
            textposition='outside',
            textfont=dict(color=theme.text),
        )
    ])

    fig.update_layout(
        title=title,
        xaxis_title="Score",
        yaxis_title=None,
        xaxis=dict(range=[-1.5, 1.5], zeroline=True),
        showlegend=False,
    )

    return apply_theme_layout(fig, theme)


def render_macro_radar(scores: Dict[str, float], title: str = "Macro Scorecard",
                       theme: Optional[Theme] = None) -> go.Figure:
    """Render a radar/spider chart for macro indicators."""
    theme = theme or get_current_theme()

    categories = list(scores.keys())
    values = list(scores.values())

    # Close the radar shape
    categories = categories + [categories[0]]
    values = values + [values[0]]

    fig = go.Figure(data=go.Scatterpolar(
        r=values,
        theta=categories,
        fill='toself',
        fillcolor=f'rgba(59, 130, 246, 0.2)',
        line=dict(color=theme.info, width=2),
    ))

    fig.update_layout(
        title=title,
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[-1, 1],
                gridcolor=theme.plot_grid,
                linecolor=theme.border,
            ),
            bgcolor=theme.plot_bg,
        ),
        showlegend=False,
    )

    return apply_theme_layout(fig, theme)


def render_time_series(df: pd.DataFrame, columns: List[str],
                       title: str = "Time Series",
                       theme: Optional[Theme] = None) -> go.Figure:
    """Render a multi-line time series chart."""
    theme = theme or get_current_theme()

    colors = [theme.info, theme.success, theme.warning, theme.danger,
              theme.accent, theme.neutral]

    fig = go.Figure()

    for i, col in enumerate(columns):
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index,
                y=df[col],
                mode='lines',
                name=col,
                line=dict(color=colors[i % len(colors)], width=2),
                hovertemplate='%{x}<br>' + col + ': %{y:.2f}<extra></extra>'
            ))

    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Value",
        hovermode='x unified',
        showlegend=True,
    )

    return apply_theme_layout(fig, theme)


def render_heatmap(data: pd.DataFrame, title: str = "Heatmap",
                   theme: Optional[Theme] = None) -> go.Figure:
    """Render a themed heatmap."""
    theme = theme or get_current_theme()

    fig = px.imshow(
        data,
        color_continuous_scale=[theme.danger, theme.neutral, theme.success],
        aspect='auto',
    )

    fig.update_layout(
        title=title,
        xaxis=dict(
            gridcolor=theme.plot_grid,
            tickfont=dict(color=theme.text_muted),
        ),
        yaxis=dict(
            gridcolor=theme.plot_grid,
            tickfont=dict(color=theme.text_muted),
        ),
        coloraxis_colorbar=dict(
            tickfont=dict(color=theme.text_muted),
            title_font=dict(color=theme.text),
        ),
    )

    return apply_theme_layout(fig, theme)


def render_sector_performance(sectors: List[str], returns: List[float],
                              title: str = "Sector Performance",
                              theme: Optional[Theme] = None) -> go.Figure:
    """Render sector performance bars."""
    theme = theme or get_current_theme()

    colors = []
    for ret in returns:
        if ret > 0:
            colors.append(theme.success)
        else:
            colors.append(theme.danger)

    fig = go.Figure(data=[
        go.Bar(
            x=sectors,
            y=returns,
            marker_color=colors,
            text=[f"{r:.1f}%" for r in returns],
            textposition='outside',
            textfont=dict(color=theme.text),
        )
    ])

    fig.update_layout(
        title=title,
        xaxis_title="Sector",
        yaxis_title="Return (%)",
        showlegend=False,
    )

    return apply_theme_layout(fig, theme)


def render_gauge(value: float, title: str, min_val: float = 0,
                 max_val: float = 100, threshold: float = 50,
                 theme: Optional[Theme] = None) -> go.Figure:
    """Render a gauge chart."""
    theme = theme or get_current_theme()

    # Determine color based on value
    if value < threshold:
        color = theme.danger
    elif value < threshold + (max_val - min_val) * 0.25:
        color = theme.warning
    else:
        color = theme.success

    fig = go.Figure(data=[
        go.Indicator(
            mode="gauge+number",
            value=value,
            title={'text': title, 'font': {'color': theme.text}},
            gauge={
                'axis': {'range': [min_val, max_val]},
                'bar': {'color': color},
                'bgcolor': theme.plot_grid,
                'bordercolor': theme.border,
                'steps': [
                    {'range': [min_val, threshold],
                     'color': f'rgba(239, 68, 68, 0.1)'},
                    {'range': [threshold, max_val],
                     'color': f'rgba(16, 185, 129, 0.1)'},
                ],
                'threshold': {
                    'line': {'color': theme.text, 'width': 2},
                    'thickness': 0.75,
                    'value': threshold
                }
            },
            number={'font': {'color': theme.text}}
        )
    ])

    fig.update_layout(
        margin=dict(l=20, r=20, t=50, b=20),
    )

    return apply_theme_layout(fig, theme)
