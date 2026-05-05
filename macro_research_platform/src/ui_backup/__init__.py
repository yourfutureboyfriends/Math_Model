"""
Dashboard UI Package

Modular UI components for the Macro Research Platform dashboard.
Supports both dark and light themes with professional styling.
"""

# Theme System
from .theme_config import (
    get_current_theme_name,
    init_theme,
    set_theme,
    toggle_theme,
    get_theme_toggle_button_html,
)
from .theme import (
    Theme,
    DARK_THEME,
    LIGHT_THEME,
    get_current_theme,
    apply_current_theme,
    section_divider_html,
    # Backward compatibility
    apply_dark_theme,
    generate_dark_css,
    dark_plotly_layout,
    # Legacy color constants
    PAGE_BG,
    CARD_BG,
    CARD_BG_2,
    ELEVATED,
    BORDER,
    BORDER_LIGHT,
    TEXT,
    TEXT_MUTED,
    TEXT_SUBTLE,
    TEXT_DISABLED,
    GREEN,
    RED,
    AMBER,
    BLUE,
    PURPLE,
    NEUTRAL,
    NEUTRAL_BG,
    DARK_THEME as DARK_THEME_DICT,
)

# Tables
from .tables import (
    render_dark_table,
    render_signal_table,
    render_allocation_table,
    render_sector_table,
    render_model_agreement_table,
    render_simple_table,
    render_status_table,
)

# Charts
from .charts import (
    apply_theme_layout,
    apply_dark_layout,
    apply_dark_plotly_layout,
    render_regime_timeline,
    render_scorecard_bars,
    render_macro_radar,
    render_time_series,
    render_heatmap,
    render_sector_performance,
    render_gauge,
)

# Components
from .components import (
    render_status_badge,
    render_regime_badge,
    render_direction_indicator,
    card_html,
    metric_card_html,
    info_card_html,
    alert_html,
    error_alert_html,
    warning_alert_html,
    success_alert_html,
    subsection_header_html,
    format_value_with_color,
    format_percent_with_color,
    progress_bar_html,
    get_conviction_label,
)

__all__ = [
    # Theme Config
    "get_current_theme_name",
    "init_theme",
    "set_theme",
    "toggle_theme",
    "get_theme_toggle_button_html",
    # Theme
    "Theme",
    "DARK_THEME",
    "LIGHT_THEME",
    "get_current_theme",
    "apply_current_theme",
    "section_divider_html",
    "apply_dark_theme",
    "generate_dark_css",
    "dark_plotly_layout",
    # Legacy colors (backward compatibility)
    "PAGE_BG",
    "CARD_BG",
    "CARD_BG_2",
    "ELEVATED",
    "BORDER",
    "BORDER_LIGHT",
    "TEXT",
    "TEXT_MUTED",
    "TEXT_SUBTLE",
    "TEXT_DISABLED",
    "GREEN",
    "RED",
    "AMBER",
    "BLUE",
    "PURPLE",
    "NEUTRAL",
    "NEUTRAL_BG",
    "DARK_THEME_DICT",
    # Tables
    "render_dark_table",
    "render_signal_table",
    "render_allocation_table",
    "render_sector_table",
    "render_model_agreement_table",
    "render_simple_table",
    "render_status_table",
    # Charts
    "apply_theme_layout",
    "apply_dark_layout",
    "apply_dark_plotly_layout",
    "render_regime_timeline",
    "render_scorecard_bars",
    "render_macro_radar",
    "render_time_series",
    "render_heatmap",
    "render_sector_performance",
    "render_gauge",
    # Components
    "render_status_badge",
    "render_regime_badge",
    "render_direction_indicator",
    "card_html",
    "metric_card_html",
    "info_card_html",
    "alert_html",
    "error_alert_html",
    "warning_alert_html",
    "success_alert_html",
    "subsection_header_html",
    "format_value_with_color",
    "format_percent_with_color",
    "progress_bar_html",
    "get_conviction_label",
]
