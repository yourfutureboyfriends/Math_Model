"""
Dashboard Components Module

Reusable UI components for the Macro Research Platform dashboard.
No icons - all visual indicators use colors and text only.
"""

from typing import Optional, Tuple
from .theme import Theme, get_current_theme


# =============================================================================
# Status Badges
# =============================================================================

def render_status_badge(status: str, theme: Optional[Theme] = None) -> str:
    """Render a status badge with appropriate colors."""
    theme = theme or get_current_theme()
    status = status.lower()

    color = theme.get_status_color(status)
    bg = theme.get_status_bg(status)

    return (
        f'<span style="'
        f'background-color: {bg}; '
        f'color: {color}; '
        f'padding: 2px 8px; '
        f'border-radius: 4px; '
        f'font-size: 11px; '
        f'font-weight: 600; '
        f'text-transform: uppercase; '
        f'letter-spacing: 0.05em; '
        f'border: 1px solid {color};"'
        f'>{status}</span>'
    )


def render_regime_badge(regime: str, theme: Optional[Theme] = None) -> str:
    """Render a regime badge with regime-specific colors."""
    theme = theme or get_current_theme()
    regime_lower = regime.lower()

    if "expansion" in regime_lower:
        color, bg = theme.success, theme.success_bg
    elif "late" in regime_lower or "inflation" in regime_lower:
        color, bg = theme.warning, theme.warning_bg
    elif "recession" in regime_lower:
        color, bg = theme.danger, theme.danger_bg
    elif "recovery" in regime_lower:
        color, bg = theme.info, theme.info_bg
    else:
        color, bg = theme.neutral, theme.neutral_bg

    return (
        f'<span style="'
        f'background-color: {bg}; '
        f'color: {color}; '
        f'padding: 4px 12px; '
        f'border-radius: 6px; '
        f'font-size: 12px; '
        f'font-weight: 600; '
        f'text-transform: uppercase; '
        f'letter-spacing: 0.05em; '
        f'border: 1px solid {color};"'
        f'>{regime}</span>'
    )


def render_direction_indicator(direction: str, theme: Optional[Theme] = None) -> str:
    """Render a direction indicator."""
    theme = theme or get_current_theme()
    direction = direction.lower()

    if "up" in direction or "rising" in direction or "increasing" in direction:
        return f'<span style="color: {theme.success}; font-weight: 600;">Rising</span>'
    elif "down" in direction or "falling" in direction or "decreasing" in direction:
        return f'<span style="color: {theme.danger}; font-weight: 600;">Falling</span>'
    else:
        return f'<span style="color: {theme.text_muted}; font-weight: 600;">Stable</span>'


# =============================================================================
# Cards
# =============================================================================

def card_html(content: str, elevated: bool = False, theme: Optional[Theme] = None) -> str:
    """Return a card container HTML."""
    theme = theme or get_current_theme()
    bg = theme.card_bg_secondary if elevated else theme.card_bg
    return f'''
    <div style="
        background-color: {bg};
        border: 1px solid {theme.border};
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 16px;
    ">
        {content}
    </div>
    '''


def metric_card_html(label: str, value: str, delta: Optional[str] = None,
                     delta_positive: Optional[bool] = None,
                     theme: Optional[Theme] = None) -> str:
    """Render a metric card with optional delta indicator."""
    theme = theme or get_current_theme()
    delta_html = ""
    if delta:
        if delta_positive is True:
            delta_color = theme.success
            delta_prefix = "+"
        elif delta_positive is False:
            delta_color = theme.danger
            delta_prefix = ""
        else:
            delta_color = theme.text_muted
            delta_prefix = ""
        delta_html = f'<div style="color: {delta_color}; font-size: 13px; font-weight: 500;">{delta_prefix}{delta}</div>'

    return card_html(f'''
        <div style="font-size: 12px; color: {theme.text_subtle}; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px;">
            {label}
        </div>
        <div style="font-size: 24px; font-weight: 700; color: {theme.text}; margin-bottom: 4px;">
            {value}
        </div>
        {delta_html}
    ''', elevated=False, theme=theme)


def info_card_html(title: str, description: str, status: str = "neutral",
                   theme: Optional[Theme] = None) -> str:
    """Render an info card with status indicator."""
    status_badge = render_status_badge(status, theme)

    return card_html(f'''
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
            <div style="font-size: 14px; font-weight: 600; color: {theme.text if theme else 'inherit'};">
                {title}
            </div>
            {status_badge}
        </div>
        <div style="font-size: 13px; color: {theme.text_muted if theme else 'inherit'}; line-height: 1.5;">
            {description}
        </div>
    ''', elevated=False, theme=theme)


# =============================================================================
# Alerts and Notifications
# =============================================================================

def alert_html(message: str, alert_type: str = "info", theme: Optional[Theme] = None) -> str:
    """Render an alert/notification banner."""
    theme = theme or get_current_theme()
    alerts = {
        "success": (theme.success, theme.success_bg, "Success"),
        "error": (theme.danger, theme.danger_bg, "Error"),
        "warning": (theme.warning, theme.warning_bg, "Warning"),
        "info": (theme.info, theme.info_bg, "Info"),
    }

    color, bg, label = alerts.get(alert_type.lower(), (theme.neutral, theme.neutral_bg, "Note"))

    return f'''
    <div style="
        background-color: {bg};
        border: 1px solid {color};
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 16px;
    ">
        <div style="font-size: 13px; font-weight: 600; color: {color}; margin-bottom: 4px;">
            {label}
        </div>
        <div style="font-size: 13px; color: {theme.text};">
            {message}
        </div>
    </div>
    '''


def error_alert_html(message: str, theme: Optional[Theme] = None) -> str:
    """Render an error alert."""
    return alert_html(message, "error", theme)


def warning_alert_html(message: str, theme: Optional[Theme] = None) -> str:
    """Render a warning alert."""
    return alert_html(message, "warning", theme)


def success_alert_html(message: str, theme: Optional[Theme] = None) -> str:
    """Render a success alert."""
    return alert_html(message, "success", theme)


# =============================================================================
# Dividers and Spacers
# =============================================================================

def subsection_header_html(title: str, subtitle: Optional[str] = None,
                           theme: Optional[Theme] = None) -> str:
    """Render a subsection header."""
    theme = theme or get_current_theme()
    subtitle_html = ""
    if subtitle:
        subtitle_html = f'<div style="font-size: 13px; color: {theme.text_muted}; margin-top: 4px;">{subtitle}</div>'

    return f'''
    <div style="margin-bottom: 16px;">
        <div style="font-size: 14px; font-weight: 600; color: {theme.text}; text-transform: uppercase; letter-spacing: 0.05em;">
            {title}
        </div>
        {subtitle_html}
    </div>
    '''


# =============================================================================
# Data Display Helpers
# =============================================================================

def format_value_with_color(value: float, positive_good: bool = True,
                            theme: Optional[Theme] = None) -> str:
    """Format a numeric value with appropriate color."""
    theme = theme or get_current_theme()
    if value > 0:
        color = theme.success if positive_good else theme.danger
        prefix = "+"
    elif value < 0:
        color = theme.danger if positive_good else theme.success
        prefix = ""
    else:
        color = theme.text_muted
        prefix = ""

    return f'<span style="color: {color}; font-weight: 600;">{prefix}{value:.2f}</span>'


def format_percent_with_color(value: float, theme: Optional[Theme] = None) -> str:
    """Format a percentage with appropriate color."""
    theme = theme or get_current_theme()
    if value > 0:
        color = theme.success
        prefix = "+"
    elif value < 0:
        color = theme.danger
        prefix = ""
    else:
        color = theme.text_muted
        prefix = ""

    return f'<span style="color: {color}; font-weight: 600;">{prefix}{value:.1f}%</span>'


def progress_bar_html(value: float, max_value: float = 100.0,
                      color: Optional[str] = None, theme: Optional[Theme] = None) -> str:
    """Render a progress bar."""
    theme = theme or get_current_theme()
    percentage = min(100, max(0, (value / max_value) * 100))
    bar_color = color or theme.primary

    return f'''
    <div style="
        width: 100%;
        height: 8px;
        background-color: {theme.card_bg_secondary};
        border-radius: 4px;
        overflow: hidden;
    ">
        <div style="
            width: {percentage}%;
            height: 100%;
            background-color: {bar_color};
            border-radius: 4px;
        "></div>
    </div>
    '''


# =============================================================================
# Utility Functions
# =============================================================================

def truncate_text(text: str, max_length: int = 50) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def get_conviction_label(conviction: float, theme: Optional[Theme] = None) -> Tuple[str, str]:
    """Get conviction label and color."""
    theme = theme or get_current_theme()
    if conviction >= 0.8:
        return "High", theme.success
    elif conviction >= 0.5:
        return "Medium", theme.warning
    else:
        return "Low", theme.neutral
