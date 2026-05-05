"""
Dashboard Theme Module

Centralized theme system for the Macro Research Platform dashboard.
Supports both dark and light modes with a professional design.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any

import plotly.graph_objects as go
import streamlit as st

from .theme_config import get_current_theme_name


@dataclass
class Theme:
    """Complete theme definition for light or dark mode."""
    # Backgrounds
    page_bg: str
    card_bg: str
    card_bg_secondary: str
    elevated: str
    input_bg: str

    # Borders
    border: str
    border_light: str
    border_focus: str

    # Text
    text: str
    text_muted: str
    text_subtle: str
    text_disabled: str

    # Status Colors (primary)
    success: str
    warning: str
    danger: str
    info: str
    neutral: str

    # Status Colors (background)
    success_bg: str
    warning_bg: str
    danger_bg: str
    info_bg: str
    neutral_bg: str

    # Chart Colors
    plot_bg: str
    plot_paper_bg: str
    plot_grid: str
    plot_zero: str
    plot_legend_bg: str

    # Accent Colors
    primary: str = field(default="")
    secondary: str = field(default="")
    accent: str = field(default="")

    def __post_init__(self):
        """Set default accent colors if not provided."""
        if not self.primary:
            self.primary = self.info
        if not self.secondary:
            self.secondary = self.neutral
        if not self.accent:
            self.accent = self.info

    def get_status_color(self, status: str) -> str:
        """Get color for a status level."""
        status = status.lower()
        colors = {
            "success": self.success,
            "good": self.success,
            "healthy": self.success,
            "live": self.success,
            "warning": self.warning,
            "warn": self.warning,
            "caution": self.warning,
            "amber": self.warning,
            "error": self.danger,
            "danger": self.danger,
            "critical": self.danger,
            "fail": self.danger,
            "info": self.info,
            "neutral": self.neutral,
            "disabled": self.text_disabled,
            "inactive": self.text_disabled,
        }
        return colors.get(status, self.text_muted)

    def get_status_bg(self, status: str) -> str:
        """Get background color for a status level."""
        status = status.lower()
        colors = {
            "success": self.success_bg,
            "good": self.success_bg,
            "healthy": self.success_bg,
            "live": self.success_bg,
            "warning": self.warning_bg,
            "warn": self.warning_bg,
            "caution": self.warning_bg,
            "amber": self.warning_bg,
            "error": self.danger_bg,
            "danger": self.danger_bg,
            "critical": self.danger_bg,
            "fail": self.danger_bg,
            "info": self.info_bg,
            "neutral": self.neutral_bg,
            "disabled": f"rgba(0,0,0,0.1)",
            "inactive": f"rgba(0,0,0,0.1)",
        }
        return colors.get(status, self.neutral_bg)

    def generate_css(self) -> str:
        """Generate comprehensive theme CSS for Streamlit."""
        return f"""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;500;600;700&display=swap');

            :root {{
                --color-page-bg: {self.page_bg};
                --color-card-bg: {self.card_bg};
                --color-card-secondary: {self.card_bg_secondary};
                --color-elevated: {self.elevated};
                --color-border: {self.border};
                --color-border-light: {self.border_light};
                --color-text: {self.text};
                --color-text-muted: {self.text_muted};
                --color-text-subtle: {self.text_subtle};
            }}

            .stApp {{
                background-color: {self.page_bg} !important;
            }}

            .main .block-container {{
                background-color: {self.page_bg} !important;
                padding-top: 2rem !important;
                padding-bottom: 2rem !important;
            }}

            * {{
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
            }}

            h1, h2, h3, h4, h5, h6 {{
                color: {self.text} !important;
            }}

            p, span, div {{
                color: {self.text};
            }}

            /* Sidebar */
            [data-testid="stSidebar"] {{
                background-color: {self.card_bg} !important;
                border-right: 1px solid {self.border} !important;
            }}

            /* Buttons */
            .stButton > button {{
                background-color: {self.card_bg_secondary} !important;
                color: {self.text} !important;
                border: 1px solid {self.border} !important;
                border-radius: 6px !important;
            }}

            .stButton > button:hover {{
                background-color: {self.elevated} !important;
                border-color: {self.border_light} !important;
            }}

            .stButton > button[kind="primary"] {{
                background-color: {self.primary} !important;
                border-color: {self.primary} !important;
                color: #FFFFFF !important;
            }}

            /* Inputs */
            .stSelectbox > div > div, .stTextInput > div > div > input {{
                background-color: {self.card_bg_secondary} !important;
                color: {self.text} !important;
                border: 1px solid {self.border} !important;
                border-radius: 6px !important;
            }}

            /* Expander */
            .streamlit-expanderHeader {{
                background-color: {self.card_bg} !important;
                color: {self.text_muted} !important;
                border: 1px solid {self.border} !important;
                border-radius: 8px !important;
            }}

            .streamlit-expanderContent {{
                background-color: {self.card_bg} !important;
                border: 1px solid {self.border} !important;
                border-top: none !important;
                border-radius: 0 0 8px 8px !important;
            }}

            /* ===========================================================
               MATERIAL ICON TEXT SUPPRESSION (theme-level, all versions)
               ===========================================================
               Applied on every theme switch so icon text never flashes
               visible during a re-render.                              */

            /* Material Icons (Streamlit < v1.33) */
            .material-icons,
            .material-icons-outlined,
            .material-icons-round,
            .material-icons-sharp {{
                font-size: 0 !important;
                line-height: 0 !important;
                color: transparent !important;
                user-select: none !important;
            }}

            /* Material Symbols (Streamlit v1.33+ / v1.56+) */
            .material-symbols-rounded,
            .material-symbols-outlined,
            .material-symbols-sharp,
            span[class*="material-symbols"],
            span[class*="material-icons"] {{
                font-size: 0 !important;
                line-height: 0 !important;
                color: transparent !important;
                user-select: none !important;
            }}

            /* Streamlit toolbar icons (theme switch, deploy, hamburger) */
            [data-testid="stToolbar"] span,
            [data-testid="stToolbarActions"] span,
            [data-testid="stHeader"] span,
            header[data-testid="stHeader"] button span {{
                font-size: 0 !important;
                line-height: 0 !important;
                color: transparent !important;
            }}

            /* Collapsed-sidebar toggle (double_arrow_right) */
            [data-testid="collapsedControl"] span,
            [data-testid="collapsedControl"] button span {{
                font-size: 0 !important;
                color: transparent !important;
            }}

            /* Disable ligature rendering globally */
            * {{ font-variant-ligatures: none !important; }}

            /* Expander header */
            .streamlit-expanderHeader {{
                background-color: {self.card_bg} !important;
                color: {self.text_muted} !important;
                border: 1px solid {self.border} !important;
                border-radius: 8px !important;
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
            }}

            [data-testid="stExpander"] .streamlit-expanderHeader div[data-testid] {{
                color: {self.text_muted} !important;
            }}

            /* Metric cards */
            [data-testid="stMetric"] {{
                background-color: {self.card_bg} !important;
                border: 1px solid {self.border} !important;
                border-radius: 8px !important;
            }}

            [data-testid="stMetricLabel"] {{
                color: {self.text_subtle} !important;
            }}

            [data-testid="stMetricValue"] {{
                color: {self.text} !important;
            }}

            [data-testid="stMetricDelta"] svg {{
                fill: {self.text_muted} !important;
            }}

            /* DataFrames */
            .stDataFrame {{
                background-color: {self.card_bg} !important;
            }}

            .stDataFrame table {{
                background-color: {self.card_bg} !important;
                color: {self.text} !important;
            }}

            .stDataFrame th {{
                background-color: {self.elevated} !important;
                color: {self.text} !important;
                border-bottom: 1px solid {self.border} !important;
            }}

            .stDataFrame td {{
                background-color: {self.card_bg} !important;
                color: {self.text_muted} !important;
                border-bottom: 1px solid {self.border_light} !important;
            }}

            /* Alerts */
            .stAlert {{
                border-radius: 8px !important;
                border: 1px solid !important;
            }}

            /* Code blocks */
            code {{
                background-color: {self.elevated} !important;
                color: {self.text} !important;
                border: 1px solid {self.border} !important;
            }}

            /* Tables */
            table {{
                background-color: {self.card_bg} !important;
                color: {self.text} !important;
                border: 1px solid {self.border} !important;
                border-collapse: collapse !important;
                width: 100% !important;
            }}

            th {{
                background-color: {self.elevated} !important;
                color: {self.text} !important;
                border-bottom: 2px solid {self.border} !important;
                padding: 12px !important;
                text-align: left !important;
                font-weight: 600 !important;
            }}

            td {{
                border-bottom: 1px solid {self.border_light} !important;
                padding: 10px 12px !important;
            }}

            tr:hover {{
                background-color: {self.card_bg_secondary} !important;
            }}

            /* Scrollbar */
            ::-webkit-scrollbar {{
                width: 8px;
                height: 8px;
            }}

            ::-webkit-scrollbar-track {{
                background: {self.card_bg};
            }}

            ::-webkit-scrollbar-thumb {{
                background: {self.border_light};
                border-radius: 4px;
            }}

            /* Header/Toolbar */
            [data-testid="stHeader"] {{
                background-color: {self.page_bg} !important;
            }}

            [data-testid="stToolbar"] {{
                background-color: {self.page_bg} !important;
            }}

            [data-testid="stDecoration"] {{
                background-color: {self.page_bg} !important;
            }}

            [data-testid="stStatusWidget"] {{
                background-color: {self.page_bg} !important;
                color: {self.text} !important;
            }}

            /* Expander/Details fixes */
            details {{
                background-color: {self.card_bg} !important;
                border: 1px solid {self.border} !important;
                border-radius: 8px !important;
            }}

            summary {{
                color: {self.text} !important;
                background-color: {self.card_bg} !important;
            }}

            /* Toggle fixes */
            .stToggle > div > div {{
                background-color: {self.card_bg_secondary} !important;
            }}

            /* Selectbox fixes */
            .stSelectbox > div > div > div {{
                background-color: {self.card_bg_secondary} !important;
                color: {self.text} !important;
            }}

            /* Plotly modebar hide */
            .modebar {{
                display: none !important;
            }}

            /* Max-width container for wide screens */
            .main .block-container {{
                max-width: 1400px !important;
                padding-left: 2rem !important;
                padding-right: 2rem !important;
            }}

            /* Pulsing live dot animation */
            @keyframes pulse-dot {{
                0%, 100% {{ opacity: 1; box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.4); }}
                50% {{ opacity: 0.6; box-shadow: 0 0 0 8px rgba(34, 197, 94, 0); }}
            }}

            .live-dot {{
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: {self.success};
                animation: pulse-dot 1.5s ease-in-out infinite;
                display: inline-block;
                margin-right: 6px;
            }}

            /* Expander styling improvements */
            details {{
                background-color: {self.card_bg} !important;
                border: 1px solid {self.border} !important;
                border-radius: 8px !important;
                transition: all 0.2s ease !important;
            }}

            details[open] {{
                border-color: {self.border_light} !important;
            }}

            summary {{
                color: {self.text} !important;
                background-color: {self.card_bg} !important;
                padding: 12px 16px !important;
                border-radius: 8px !important;
                cursor: pointer !important;
            }}

            details[open] summary {{
                border-radius: 8px 8px 0 0 !important;
                border-bottom: 1px solid {self.border} !important;
            }}

            /* Expander content fade-in animation */
            .streamlit-expanderContent {{
                animation: fadeIn 0.2s ease-in !important;
            }}

            @keyframes fadeIn {{
                from {{ opacity: 0; }}
                to {{ opacity: 1; }}
            }}

            /* Section header styling */
            .section-header {{
                font-size: 0.7rem !important;
                font-weight: 600 !important;
                text-transform: uppercase !important;
                letter-spacing: 0.08em !important;
                color: {self.text_muted} !important;
                margin-bottom: 16px !important;
                padding-bottom: 8px !important;
                border-bottom: 1px solid {self.border} !important;
            }}

            /* Ensure no white backgrounds */
            .element-container, .stMarkdown, .stText {{
                background-color: transparent !important;
            }}

            /* Spinner */
            .stSpinner > div {{
                border-color: {self.primary} transparent transparent transparent !important;
            }}

            /* Success/Error/Warning messages */
            .stSuccess {{
                background-color: {self.success_bg} !important;
                border: 1px solid {self.success} !important;
                color: {self.text} !important;
            }}

            .stError {{
                background-color: {self.danger_bg} !important;
                border: 1px solid {self.danger} !important;
                color: {self.text} !important;
            }}

            .stWarning {{
                background-color: {self.warning_bg} !important;
                border: 1px solid {self.warning} !important;
                color: {self.text} !important;
            }}

            .stInfo {{
                background-color: {self.info_bg} !important;
                border: 1px solid {self.info} !important;
                color: {self.text} !important;
            }}

            /* Slider */
            .stSlider > div > div > div > div {{
                background-color: {self.primary} !important;
            }}

            /* Checkbox/Radio */
            .stCheckbox > div > div > div, .stRadio > div > div > div {{
                color: {self.text} !important;
            }}

            /* Tabs */
            .stTabs [data-baseweb="tab-list"] {{
                background-color: {self.card_bg} !important;
            }}

            .stTabs [data-baseweb="tab"] {{
                color: {self.text_muted} !important;
            }}

            .stTabs [aria-selected="true"] {{
                color: {self.text} !important;
                border-bottom-color: {self.primary} !important;
            }}

            /* ===========================================================
               BLOOMBERG TERMINAL STYLE OVERRIDES
               Ultra-dense, monospace numbers, amber accents, sharp corners
               =========================================================== */

            /* Monospace font for all numeric / data values */
            [data-testid="stMetricValue"],
            [data-testid="stMetricDelta"],
            td, .mono-num {{
                font-family: 'IBM Plex Mono', 'Courier New', monospace !important;
                font-variant-numeric: tabular-nums !important;
            }}

            /* Sharp corners everywhere — terminal aesthetic */
            [data-testid="stExpander"],
            [data-testid="stMetric"],
            .stButton > button,
            .stSelectbox > div > div,
            .stTextInput > div > div > input,
            details, summary,
            [data-testid="stSidebar"] {{
                border-radius: 0 !important;
            }}

            /* Metric cards: amber left-border, no rounded corners */
            [data-testid="stMetric"] {{
                border-left: 2px solid {self.primary} !important;
                border-top: none !important;
                border-right: none !important;
                border-bottom: 1px solid {self.border} !important;
                border-radius: 0 !important;
                padding: 10px 14px !important;
                min-height: 80px !important;
                background-color: {self.card_bg} !important;
            }}

            /* Metric labels: all-caps, tight tracking */
            [data-testid="stMetricLabel"] {{
                font-size: 10px !important;
                letter-spacing: 0.10em !important;
                text-transform: uppercase !important;
                color: {self.text_muted} !important;
            }}

            /* Metric values: large monospace numbers */
            [data-testid="stMetricValue"] {{
                font-size: 22px !important;
                font-weight: 600 !important;
                color: {self.text} !important;
                font-family: 'IBM Plex Mono', monospace !important;
            }}

            /* Section headers: amber left-bar, uppercase, very tight */
            .section-header {{
                border-left: 3px solid {self.primary} !important;
                border-bottom: none !important;
                padding-left: 8px !important;
                padding-bottom: 0 !important;
                font-size: 0.62rem !important;
                letter-spacing: 0.14em !important;
                text-transform: uppercase !important;
                color: {self.primary} !important;
                margin-bottom: 12px !important;
            }}

            /* Table headers: amber bottom border, uppercase tiny font */
            th {{
                font-size: 0.62rem !important;
                letter-spacing: 0.10em !important;
                text-transform: uppercase !important;
                padding: 5px 8px !important;
                border-bottom: 1px solid {self.primary} !important;
                border-radius: 0 !important;
                background-color: {self.card_bg} !important;
                color: {self.text_muted} !important;
            }}

            /* Table data: dense monospace */
            td {{
                font-size: 0.8rem !important;
                padding: 4px 8px !important;
                font-family: 'IBM Plex Mono', monospace !important;
                border-radius: 0 !important;
            }}

            /* Expanders: amber left-border on header, no radius */
            [data-testid="stExpander"] {{
                border: none !important;
                border-left: 2px solid {self.border_light} !important;
                border-radius: 0 !important;
                background-color: {self.card_bg} !important;
            }}

            details {{
                border: none !important;
                border-left: 2px solid {self.border_light} !important;
                border-radius: 0 !important;
            }}

            details[open] {{
                border-left-color: {self.primary} !important;
            }}

            summary {{
                border-radius: 0 !important;
                font-size: 0.72rem !important;
                font-weight: 600 !important;
                letter-spacing: 0.08em !important;
                text-transform: uppercase !important;
                color: {self.text_muted} !important;
                padding: 8px 12px !important;
            }}

            /* Sidebar: amber right-border accent */
            [data-testid="stSidebar"] {{
                border-right: 1px solid {self.primary} !important;
            }}

            /* Buttons: square, amber border */
            .stButton > button {{
                border-radius: 0 !important;
                border: 1px solid {self.border_light} !important;
                font-size: 0.75rem !important;
                letter-spacing: 0.06em !important;
                text-transform: uppercase !important;
                font-weight: 600 !important;
            }}

            .stButton > button:hover {{
                border-color: {self.primary} !important;
                color: {self.primary} !important;
            }}

            .stButton > button[kind="primary"] {{
                background-color: {self.primary} !important;
                border-color: {self.primary} !important;
                color: #000000 !important;
                font-weight: 700 !important;
            }}

            /* Compact main container padding */
            .main .block-container {{
                padding-top: 1.2rem !important;
                padding-bottom: 1.5rem !important;
            }}

            /* Live dot: use amber for Bloomberg orange */
            .live-dot {{
                background: {self.primary} !important;
            }}

            @keyframes pulse-dot {{
                0%, 100% {{ opacity: 1; box-shadow: 0 0 0 0 rgba(255, 102, 0, 0.4); }}
                50% {{ opacity: 0.6; box-shadow: 0 0 0 8px rgba(255, 102, 0, 0); }}
            }}

            /* Plotly chart: zero-radius */
            .js-plotly-plot, .plot-container {{
                border-radius: 0 !important;
            }}

            /* Scrollbar: amber thumb */
            ::-webkit-scrollbar-thumb {{
                background: {self.border_light} !important;
                border-radius: 0 !important;
            }}

            ::-webkit-scrollbar-thumb:hover {{
                background: {self.primary} !important;
            }}
        </style>
        """

    def apply_to_plotly(self, fig: go.Figure) -> go.Figure:
        """Apply theme to a Plotly figure."""
        _dark_pages = {"#0b0f17", "#000000", "#0a0a0a", "#0c0c0c"}
        fig.update_layout(
            template="plotly_dark" if self.page_bg.lower() in _dark_pages else "plotly_white",
            paper_bgcolor=self.plot_paper_bg,
            plot_bgcolor=self.plot_bg,
            font=dict(
                family="Inter, -apple-system, sans-serif",
                color=self.text
            ),
            margin=dict(l=50, r=25, t=35, b=45),
            legend=dict(
                bgcolor=self.plot_legend_bg,
                bordercolor=self.border,
                borderwidth=1,
                font=dict(color=self.text)
            ),
            xaxis=dict(
                gridcolor=self.plot_grid,
                zerolinecolor=self.plot_zero,
                linecolor=self.border,
                tickfont=dict(color=self.text_muted)
            ),
            yaxis=dict(
                gridcolor=self.plot_grid,
                zerolinecolor=self.plot_zero,
                linecolor=self.border,
                tickfont=dict(color=self.text_muted)
            ),
        )
        return fig


# =============================================================================
# Theme Definitions
# =============================================================================

DARK_THEME = Theme(
    # Backgrounds — Bloomberg Terminal: jet black
    page_bg="#000000",
    card_bg="#0C0C0C",
    card_bg_secondary="#141414",
    elevated="#1C1C1C",
    input_bg="#000000",

    # Borders — near-invisible dark seams
    border="#1E1E1E",
    border_light="#2A2A2A",
    border_focus="#FF6600",

    # Text — bright-white primary, warm greys
    text="#E0E0E0",
    text_muted="#888888",
    text_subtle="#555555",
    text_disabled="#333333",

    # Status Colors — Bloomberg palette
    success="#00CC44",           # Bloomberg green
    warning="#FF6600",           # Bloomberg orange
    danger="#FF3333",            # red
    info="#0099CC",              # Bloomberg cyan-blue
    neutral="#555555",

    # Status Backgrounds
    success_bg="rgba(0, 204, 68, 0.08)",
    warning_bg="rgba(255, 102, 0, 0.08)",
    danger_bg="rgba(255, 51, 51, 0.08)",
    info_bg="rgba(0, 153, 204, 0.08)",
    neutral_bg="rgba(85, 85, 85, 0.08)",

    # Chart Colors — black canvas
    plot_bg="#000000",
    plot_paper_bg="#000000",
    plot_grid="#1E1E1E",
    plot_zero="#2A2A2A",
    plot_legend_bg="rgba(12, 12, 12, 0.95)",

    # Accents — amber/orange Bloomberg primary
    primary="#FF6600",
    secondary="#555555",
    accent="#FF8C00",
)

LIGHT_THEME = Theme(
    # Backgrounds
    page_bg="#F8FAFC",
    card_bg="#FFFFFF",
    card_bg_secondary="#F1F5F9",
    elevated="#E2E8F0",
    input_bg="#FFFFFF",

    # Borders
    border="#E2E8F0",
    border_light="#CBD5E1",
    border_focus="#3B82F6",

    # Text
    text="#0F172A",
    text_muted="#475569",
    text_subtle="#64748B",
    text_disabled="#94A3B8",

    # Status Colors
    success="#059669",
    warning="#D97706",
    danger="#DC2626",
    info="#2563EB",
    neutral="#64748B",

    # Status Backgrounds
    success_bg="rgba(5, 150, 105, 0.08)",
    warning_bg="rgba(217, 119, 6, 0.08)",
    danger_bg="rgba(220, 38, 38, 0.08)",
    info_bg="rgba(37, 99, 235, 0.08)",
    neutral_bg="rgba(100, 116, 139, 0.08)",

    # Chart Colors
    plot_bg="#FFFFFF",
    plot_paper_bg="#F8FAFC",
    plot_grid="#E2E8F0",
    plot_zero="#CBD5E1",
    plot_legend_bg="rgba(255, 255, 255, 0.95)",

    # Accents
    primary="#2563EB",
    secondary="#64748B",
    accent="#7C3AED",
)


# =============================================================================
# Backward Compatibility: DARK_THEME_DICT Dictionary
# =============================================================================

DARK_THEME_DICT = {
    # Backgrounds
    "page_bg": DARK_THEME.page_bg,
    "card_bg": DARK_THEME.card_bg,
    "card_bg_secondary": DARK_THEME.card_bg_secondary,
    "elevated": DARK_THEME.elevated,
    "input_bg": DARK_THEME.input_bg,
    # Borders
    "border": DARK_THEME.border,
    "border_light": DARK_THEME.border_light,
    "border_focus": DARK_THEME.border_focus,
    # Text
    "text_primary": DARK_THEME.text,
    "text_secondary": DARK_THEME.text_muted,
    "text_muted": DARK_THEME.text_subtle,
    "text_disabled": DARK_THEME.text_disabled,
    # Accents
    "accent": DARK_THEME.accent,
    "accent_hover": DARK_THEME.primary,
    # Status Colors
    "success": DARK_THEME.success,
    "success_bg": DARK_THEME.success_bg,
    "warning": DARK_THEME.warning,
    "warning_bg": DARK_THEME.warning_bg,
    "danger": DARK_THEME.danger,
    "danger_bg": DARK_THEME.danger_bg,
    "info": DARK_THEME.info,
    "info_bg": DARK_THEME.info_bg,
    "neutral": DARK_THEME.neutral,
    "neutral_bg": DARK_THEME.neutral_bg,
    # Plotly Specific
    "plot_bg": DARK_THEME.plot_bg,
    "plot_paper_bg": DARK_THEME.plot_paper_bg,
    "plot_grid": DARK_THEME.plot_grid,
    "plot_zero": DARK_THEME.plot_zero,
    "plot_legend_bg": DARK_THEME.plot_legend_bg,
}


# Keep reference to backward compatibility dict for imports
DARK_THEME_LEGACY = DARK_THEME_DICT


# =============================================================================
# Theme Helpers
# =============================================================================

def get_current_theme() -> Theme:
    """Get the current theme from session state."""
    theme_name = get_current_theme_name()
    return DARK_THEME if theme_name == "dark" else LIGHT_THEME


def apply_current_theme() -> None:
    """Apply the current theme CSS to the Streamlit app."""
    theme = get_current_theme()
    st.markdown(theme.generate_css(), unsafe_allow_html=True)


def section_divider_html(theme: Optional[Theme] = None) -> str:
    """Return a section divider HTML."""
    theme = theme or get_current_theme()
    return f'<hr style="border: 0; height: 1px; background: linear-gradient(90deg, transparent, {theme.border}, transparent); margin: 32px 0;">'


# Aliases for backward compatibility
def apply_dark_theme() -> None:
    """Apply the complete dark theme to the Streamlit app (backward compatibility)."""
    apply_current_theme()


def generate_dark_css() -> str:
    """Generate comprehensive dark theme CSS (backward compatibility)."""
    return DARK_THEME.generate_css()


def dark_plotly_layout(fig: go.Figure) -> go.Figure:
    """Apply dark theme to a Plotly figure (backward compatibility)."""
    return get_current_theme().apply_to_plotly(fig)


# =============================================================================
# Legacy Color Constants (for backward compatibility)
# =============================================================================

PAGE_BG = DARK_THEME.page_bg
CARD_BG = DARK_THEME.card_bg
CARD_BG_2 = DARK_THEME.card_bg_secondary
ELEVATED = DARK_THEME.elevated
INPUT_BG = DARK_THEME.input_bg

BORDER = DARK_THEME.border
BORDER_LIGHT = DARK_THEME.border_light
BORDER_FOCUS = DARK_THEME.border_focus

TEXT = DARK_THEME.text
TEXT_MUTED = DARK_THEME.text_muted
TEXT_SUBTLE = DARK_THEME.text_subtle
TEXT_DISABLED = DARK_THEME.text_disabled

GREEN = DARK_THEME.success
GREEN_BG = DARK_THEME.success_bg
RED = DARK_THEME.danger
RED_BG = DARK_THEME.danger_bg
AMBER = DARK_THEME.warning
AMBER_BG = DARK_THEME.warning_bg
ORANGE = DARK_THEME.primary   # Bloomberg orange
BLUE = DARK_THEME.info
BLUE_BG = DARK_THEME.info_bg
PURPLE = DARK_THEME.accent
NEUTRAL = DARK_THEME.neutral
NEUTRAL_BG = DARK_THEME.neutral_bg

PLOT_BG = DARK_THEME.plot_bg
PLOT_PAPER_BG = DARK_THEME.plot_paper_bg
PLOT_GRID = DARK_THEME.plot_grid
PLOT_ZERO = DARK_THEME.plot_zero
PLOT_LEGEND_BG = DARK_THEME.plot_legend_bg
