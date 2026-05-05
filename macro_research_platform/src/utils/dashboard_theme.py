"""
Dashboard Theme Helper

Centralized dark theme styling for the Macro Research Platform dashboard.
Ensures visual consistency across all dashboard elements.
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import streamlit as st


# =============================================================================
# Dark Theme Color Palette
# =============================================================================

DARK_THEME = {
    # Backgrounds
    "page_bg": "#0B0F17",
    "card_bg": "#111827",
    "card_bg_secondary": "#151C2C",
    "elevated": "#1F2937",
    "input_bg": "#0B0F17",

    # Borders
    "border": "#263244",
    "border_light": "#374151",
    "border_focus": "#3B82F6",

    # Text
    "text_primary": "#E5E7EB",
    "text_secondary": "#9CA3AF",
    "text_muted": "#6B7280",
    "text_disabled": "#4B5563",

    # Accents
    "accent": "#3B82F6",
    "accent_hover": "#2563EB",

    # Status Colors
    "success": "#10B981",
    "success_bg": "rgba(16, 185, 129, 0.10)",
    "warning": "#F59E0B",
    "warning_bg": "rgba(245, 158, 11, 0.10)",
    "danger": "#EF4444",
    "danger_bg": "rgba(239, 68, 68, 0.10)",
    "info": "#3B82F6",
    "info_bg": "rgba(59, 130, 246, 0.10)",
    "neutral": "#6B7280",
    "neutral_bg": "rgba(107, 114, 128, 0.10)",

    # Plotly Specific
    "plot_bg": "#111827",
    "plot_paper_bg": "#0B0F17",
    "plot_grid": "#263244",
    "plot_zero": "#374151",
    "plot_legend_bg": "rgba(17, 24, 39, 0.90)",
}


# =============================================================================
# CSS Generation
# =============================================================================

def generate_dark_css() -> str:
    """Generate comprehensive dark theme CSS for Streamlit."""
    t = DARK_THEME

    return f"""
    <style>
        /* Import font */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        /* Root variables */
        :root {{
            --color-page-bg: {t['page_bg']};
            --color-card-bg: {t['card_bg']};
            --color-card-secondary: {t['card_bg_secondary']};
            --color-elevated: {t['elevated']};
            --color-border: {t['border']};
            --color-border-light: {t['border_light']};
            --color-text-primary: {t['text_primary']};
            --color-text-secondary: {t['text_secondary']};
            --color-text-muted: {t['text_muted']};
            --color-accent: {t['accent']};
            --color-success: {t['success']};
            --color-warning: {t['warning']};
            --color-danger: {t['danger']};
        }}

        /* Main app background */
        .stApp {{
            background-color: {t['page_bg']} !important;
        }}

        /* Main container */
        .main .block-container {{
            background-color: {t['page_bg']} !important;
            padding-top: 2rem !important;
            padding-bottom: 2rem !important;
        }}

        /* Typography */
        * {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
        }}

        h1, h2, h3, h4, h5, h6 {{
            color: {t['text_primary']} !important;
        }}

        p, span, div {{
            color: {t['text_primary']};
        }}

        /* Sidebar */
        [data-testid="stSidebar"] {{
            background-color: {t['card_bg']} !important;
            border-right: 1px solid {t['border']} !important;
        }}

        [data-testid="stSidebar"] .stApp {{
            background-color: {t['card_bg']} !important;
        }}

        /* Buttons */
        .stButton>button {{
            background-color: {t['card_bg_secondary']} !important;
            color: {t['text_primary']} !important;
            border: 1px solid {t['border']} !important;
            border-radius: 6px !important;
        }}

        .stButton>button:hover {{
            background-color: {t['elevated']} !important;
            border-color: {t['border_light']} !important;
        }}

        .stButton>button[kind="primary"] {{
            background-color: {t['accent']} !important;
            border-color: {t['accent']} !important;
        }}

        .stButton>button[kind="primary"]:hover {{
            background-color: {t['accent_hover']} !important;
        }}

        /* Expander */
        .streamlit-expanderHeader {{
            background-color: {t['card_bg']} !important;
            color: {t['text_secondary']} !important;
            border: 1px solid {t['border']} !important;
            border-radius: 8px !important;
        }}

        .streamlit-expanderContent {{
            background-color: {t['card_bg']} !important;
            border: 1px solid {t['border']} !important;
            border-top: none !important;
            border-radius: 0 0 8px 8px !important;
        }}

        /* Selectbox, Text Input, etc. */
        .stSelectbox, .stTextInput, .stNumberInput, .stTextArea {{
            background-color: {t['input_bg']} !important;
        }}

        .stSelectbox>div>div, .stTextInput>div>div>input,
        .stNumberInput>div>div>input, .stTextArea>div>div>textarea {{
            background-color: {t['card_bg_secondary']} !important;
            color: {t['text_primary']} !important;
            border: 1px solid {t['border']} !important;
            border-radius: 6px !important;
        }}

        /* Toggle */
        .stCheckbox label, .stRadio label {{
            color: {t['text_secondary']} !important;
        }}

        /* Metric cards */
        [data-testid="stMetric"] {{
            background-color: {t['card_bg']} !important;
            border: 1px solid {t['border']} !important;
            border-radius: 8px !important;
        }}

        [data-testid="stMetricLabel"] {{
            color: {t['text_muted']} !important;
        }}

        [data-testid="stMetricValue"] {{
            color: {t['text_primary']} !important;
        }}

        /* DataFrames / Tables */
        .stDataFrame {{
            background-color: {t['card_bg']} !important;
        }}

        .stDataFrame table {{
            background-color: {t['card_bg']} !important;
            color: {t['text_primary']} !important;
            border: 1px solid {t['border']} !important;
        }}

        .stDataFrame th {{
            background-color: {t['elevated']} !important;
            color: {t['text_primary']} !important;
            border-bottom: 1px solid {t['border']} !important;
            font-weight: 600 !important;
        }}

        .stDataFrame td {{
            background-color: {t['card_bg']} !important;
            color: {t['text_secondary']} !important;
            border-bottom: 1px solid {t['border_light']} !important;
        }}

        .stDataFrame tr:hover td {{
            background-color: {t['card_bg_secondary']} !important;
        }}

        /* Alerts / Info boxes */
        .stAlert {{
            border-radius: 8px !important;
            border: 1px solid !important;
        }}

        .stAlert[data-baseweb="notification"] {{
            background-color: {t['info_bg']} !important;
            border-color: {t['info']} !important;
        }}

        /* Success message */
        .stAlert.success {{
            background-color: {t['success_bg']} !important;
            border-color: {t['success']} !important;
            color: {t['success']} !important;
        }}

        /* Warning message */
        .stAlert.warning {{
            background-color: {t['warning_bg']} !important;
            border-color: {t['warning']} !important;
            color: {t['warning']} !important;
        }}

        /* Error message */
        .stAlert.error {{
            background-color: {t['danger_bg']} !important;
            border-color: {t['danger']} !important;
            color: {t['danger']} !important;
        }}

        /* Info message */
        .stAlert.info {{
            background-color: {t['info_bg']} !important;
            border-color: {t['info']} !important;
            color: {t['info']} !important;
        }}

        /* Divider */
        hr {{
            border-color: {t['border']} !important;
        }}

        /* Custom card styles */
        .dark-card {{
            background-color: {t['card_bg']};
            border: 1px solid {t['border']};
            border-radius: 8px;
            padding: 16px;
        }}

        .dark-card-elevated {{
            background-color: {t['card_bg_secondary']};
            border: 1px solid {t['border']};
            border-radius: 8px;
            padding: 16px;
        }}

        /* Badge styles */
        .badge-success {{
            background-color: {t['success_bg']};
            color: {t['success']};
            border: 1px solid {t['success']};
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }}

        .badge-warning {{
            background-color: {t['warning_bg']};
            color: {t['warning']};
            border: 1px solid {t['warning']};
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }}

        .badge-danger {{
            background-color: {t['danger_bg']};
            color: {t['danger']};
            border: 1px solid {t['danger']};
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }}

        .badge-neutral {{
            background-color: {t['neutral_bg']};
            color: {t['neutral']};
            border: 1px solid {t['neutral']};
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }}

        .badge-info {{
            background-color: {t['info_bg']};
            color: {t['info']};
            border: 1px solid {t['info']};
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }}

        /* Code blocks */
        code {{
            background-color: {t['elevated']} !important;
            color: {t['text_primary']} !important;
            border: 1px solid {t['border']} !important;
            border-radius: 4px !important;
        }}

        /* Preformatted text */
        pre {{
            background-color: {t['card_bg']} !important;
            border: 1px solid {t['border']} !important;
            border-radius: 8px !important;
        }}

        /* Tables rendered via markdown */
        table {{
            background-color: {t['card_bg']} !important;
            color: {t['text_primary']} !important;
            border: 1px solid {t['border']} !important;
        }}

        th {{
            background-color: {t['elevated']} !important;
            color: {t['text_primary']} !important;
            border-bottom: 2px solid {t['border']} !important;
        }}

        td {{
            border-bottom: 1px solid {t['border_light']} !important;
        }}

        tr:hover {{
            background-color: {t['card_bg_secondary']} !important;
        }}

        /* Links */
        a {{
            color: {t['accent']} !important;
        }}

        a:hover {{
            color: {t['accent_hover']} !important;
        }}

        /* Scrollbar */
        ::-webkit-scrollbar {{
            width: 8px;
            height: 8px;
        }}

        ::-webkit-scrollbar-track {{
            background: {t['card_bg']};
        }}

        ::-webkit-scrollbar-thumb {{
            background: {t['border_light']};
            border-radius: 4px;
        }}

        ::-webkit-scrollbar-thumb:hover {{
            background: {t['text_muted']};
        }}
    </style>
    """


def apply_plotly_dark_theme(fig: go.Figure) -> go.Figure:
    """Apply dark theme to a Plotly figure."""
    t = DARK_THEME

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=t['plot_paper_bg'],
        plot_bgcolor=t['plot_bg'],
        font=dict(
            family="Inter, -apple-system, sans-serif",
            color=t['text_primary']
        ),
        xaxis=dict(
            gridcolor=t['plot_grid'],
            zerolinecolor=t['plot_zero'],
            linecolor=t['border'],
            tickcolor=t['text_muted'],
            tickfont=dict(color=t['text_secondary']),
        ),
        yaxis=dict(
            gridcolor=t['plot_grid'],
            zerolinecolor=t['plot_zero'],
            linecolor=t['border'],
            tickcolor=t['text_muted'],
            tickfont=dict(color=t['text_secondary']),
        ),
        legend=dict(
            bgcolor=t['plot_legend_bg'],
            bordercolor=t['border'],
            borderwidth=1,
            font=dict(color=t['text_primary']),
        ),
        title_font=dict(color=t['text_primary']),
        margin=dict(l=60, r=40, t=60, b=60),
    )

    # Update all axes (for subplots)
    for axis in fig.layout:
        if axis.startswith('xaxis') or axis.startswith('yaxis'):
            fig.layout[axis].gridcolor = t['plot_grid']
            fig.layout[axis].zerolinecolor = t['plot_zero']
            fig.layout[axis].linecolor = t['border']

    return fig


def style_dataframe_dark(df: pd.DataFrame) -> pd.DataFrame:
    """Apply dark theme styling to a pandas DataFrame for display."""
    t = DARK_THEME

    styled = df.style\
        .set_properties(**{
            'background-color': t['card_bg'],
            'color': t['text_primary'],
            'border': f'1px solid {t["border"]}',
        })\
        .set_table_styles([
            {'selector': 'th', 'props': [
                ('background-color', t['elevated']),
                ('color', t['text_primary']),
                ('font-weight', '600'),
                ('border-bottom', f'2px solid {t["border"]}'),
            ]},
            {'selector': 'td', 'props': [
                ('border-bottom', f'1px solid {t["border_light"]}'),
            ]},
            {'selector': 'tr:hover', 'props': [
                ('background-color', t['card_bg_secondary']),
            ]},
        ])

    return styled


def get_card_style(elevated: bool = False) -> str:
    """Get CSS style string for a card container."""
    t = DARK_THEME
    bg = t['card_bg_secondary'] if elevated else t['card_bg']

    return f"""
        background-color: {bg};
        border: 1px solid {t['border']};
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 16px;
    """


def get_status_badge_style(status: str) -> str:
    """Get CSS style for a status badge."""
    t = DARK_THEME

    styles = {
        'success': (t['success_bg'], t['success']),
        'warning': (t['warning_bg'], t['warning']),
        'danger': (t['danger_bg'], t['danger']),
        'info': (t['info_bg'], t['info']),
        'neutral': (t['neutral_bg'], t['neutral']),
    }

    bg, color = styles.get(status, styles['neutral'])

    return f"""
        display: inline-flex;
        align-items: center;
        padding: 4px 12px;
        border-radius: 4px;
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        background-color: {bg};
        color: {color};
        border: 1px solid {color};
    """


def apply_theme():
    """Apply the complete dark theme to the Streamlit app."""
    css = generate_dark_css()
    st.markdown(css, unsafe_allow_html=True)


def get_theme_colors() -> dict:
    """Get the theme color dictionary."""
    return DARK_THEME.copy()
