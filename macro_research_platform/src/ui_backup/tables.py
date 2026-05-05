"""
Dashboard Tables Module

Theme-aware table rendering for the Macro Research Platform dashboard.
Uses HTML tables instead of st.dataframe for consistent theme styling.

# =============================================================================
# CHANGE SUMMARY
# =============================================================================
# FIXED: Zebra striping in _generate_table_html() used `idx % 2 == 0` where
#        `idx` is the DataFrame's row LABEL from iterrows(), NOT an enumeration
#        counter.  With a non-zero-based integer index (or any string index)
#        this produces wrong alternating colors or raises TypeError.
#        Replaced with enumerate() so parity is always on a plain int.
# FIXED: Same zebra-striping bug fixed in render_model_agreement_table() which
#        had its own inline HTML-generation loop with the same pattern.
# =============================================================================
"""

from typing import Optional

import pandas as pd
import streamlit as st

from .theme import Theme, get_current_theme


def render_dark_table(df: pd.DataFrame, title: str = None, columns: dict = None,
                      theme: Optional[Theme] = None) -> None:
    """Render a DataFrame as a themed HTML table in Streamlit."""
    html = _generate_table_html(df, title, columns, theme)
    st.markdown(html, unsafe_allow_html=True)


def _generate_table_html(df: pd.DataFrame, title: str = None, columns: dict = None,
                         theme: Optional[Theme] = None) -> str:
    """Generate themed table HTML."""
    theme = theme or get_current_theme()
    html_parts = []

    if title:
        html_parts.append(
            f'<div style="font-size: 13px; font-weight: 600; color: {theme.text_subtle}; '
            f'margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.05em;">'
            f'{title}</div>'
        )

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

    # Header
    html_parts.append(f'<thead><tr style="background-color: {theme.elevated};">')
    for col in df.columns:
        html_parts.append(
            f'<th style="'
            f'border-bottom: 2px solid {theme.border}; '
            f'padding: 12px; '
            f'text-align: left; '
            f'font-weight: 600; '
            f'color: {theme.text};"'
            f'>{col}</th>'
        )
    html_parts.append('</tr></thead>')

    # Body
    html_parts.append('<tbody>')
    # FIXED: Use enumerate(df.iterrows()) so row_num is always a plain int.
    # Previously `idx % 2 == 0` used the DataFrame's row label which is
    # non-zero-based or string-typed in many real DataFrames and raises
    # TypeError or produces the wrong alternating pattern.
    for row_num, (_, row) in enumerate(df.iterrows()):
        bg_color = theme.card_bg if row_num % 2 == 0 else theme.card_bg_secondary  # FIXED
        html_parts.append(f'<tr style="border-bottom: 1px solid {theme.border_light}; background-color: {bg_color};">')
        for col in df.columns:
            val = row.get(col, "")
            # Format based on column config
            if columns and col in columns:
                val = _format_cell(val, columns[col], theme)
            html_parts.append(
                f'<td style="'
                f'padding: 10px 12px; '
                f'color: {theme.text_muted};"'
                f'>{val}</td>'
            )
        html_parts.append('</tr>')
    html_parts.append('</tbody></table>')

    return ''.join(html_parts)


def _format_cell(val, col_config: dict, theme: Theme) -> str:
    """Format a cell value based on column configuration."""
    col_type = col_config.get("type", "text")

    if col_type == "number":
        fmt = col_config.get("format", "{:.2f}")
        try:
            return fmt.format(float(val))
        except (ValueError, TypeError):
            return str(val)
    elif col_type == "percent":
        try:
            return f"{float(val):.1f}%"
        except (ValueError, TypeError):
            return str(val)
    elif col_type == "badge":
        return _render_badge(val, theme)
    elif col_type == "styled":
        # Apply custom styling based on value
        return _apply_value_styling(val, col_config.get("style_rules", {}), theme)
    else:
        return str(val)


def _apply_value_styling(val, style_rules: dict, theme: Theme) -> str:
    """Apply styling based on value rules."""
    try:
        numeric_val = float(val)
        for rule in style_rules.get("rules", []):
            condition = rule.get("condition")
            if callable(condition) and condition(numeric_val):
                color = rule.get("color", theme.text)
                return f'<span style="color: {color}; font-weight: 600;">{val}</span>'
    except (ValueError, TypeError):
        pass
    return str(val)


def _render_badge(val: str, theme: Theme) -> str:
    """Render a status badge."""
    val_lower = str(val).lower()

    # Map values to theme colors
    if val_lower in ["live", "success", "overweight"]:
        color, bg = theme.success, theme.success_bg
    elif val_lower in ["sample", "warning", "slight overweight"]:
        color, bg = theme.warning, theme.warning_bg
    elif val_lower in ["error", "danger", "underweight"]:
        color, bg = theme.danger, theme.danger_bg
    elif val_lower in ["info"]:
        color, bg = theme.info, theme.info_bg
    elif val_lower in ["slight underweight"]:
        # Use muted versions for slight underweight
        color, bg = theme.danger, "rgba(239, 68, 68, 0.05)" if "dark" in theme.page_bg else "rgba(220, 38, 38, 0.05)"
    else:
        color, bg = theme.neutral, theme.neutral_bg

    return (
        f'<span style="'
        f'background-color: {bg}; '
        f'color: {color}; '
        f'padding: 2px 8px; '
        f'border-radius: 4px; '
        f'font-size: 11px; '
        f'font-weight: 600; '
        f'text-transform: uppercase; '
        f'border: 1px solid {color};"'
        f'>{val}</span>'
    )


def render_status_table(df: pd.DataFrame, title: str = "Status",
                        theme: Optional[Theme] = None) -> None:
    """Render a status-focused table with badges."""
    render_dark_table(df, title, theme=theme)


def render_signal_table(df: pd.DataFrame, title: str = "Signals",
                        theme: Optional[Theme] = None) -> None:
    """Render a signal table with formatted values."""
    columns = {}
    if "Latest Score" in df.columns:
        columns["Latest Score"] = {"type": "text"}
    if "3M Change" in df.columns:
        columns["3M Change"] = {"type": "text"}
    if "State" in df.columns:
        columns["State"] = {"type": "text"}
    if "Direction" in df.columns:
        columns["Direction"] = {"type": "text"}
    render_dark_table(df, title, columns, theme=theme)


def render_allocation_table(df: pd.DataFrame, title: str = "Allocation",
                              theme: Optional[Theme] = None) -> None:
    """Render an allocation table with position sizing."""
    columns = {}
    if "Expected Return" in df.columns:
        columns["Expected Return"] = {"type": "percent"}
    if "Conviction" in df.columns:
        columns["Conviction"] = {"type": "percent"}
    if "Signal" in df.columns:
        columns["Signal"] = {"type": "badge"}
    render_dark_table(df, title, columns, theme=theme)


def render_simple_table(data: list, columns: list, title: str = None,
                        theme: Optional[Theme] = None) -> None:
    """Render a simple table from list of dicts."""
    df = pd.DataFrame(data, columns=columns)
    render_dark_table(df, title, theme=theme)


def render_sector_table(df: pd.DataFrame, title: str = "Sector Allocation",
                        theme: Optional[Theme] = None) -> None:
    """Render sector allocation table with styled signals."""
    theme = theme or get_current_theme()
    # Create a copy to avoid modifying original
    display_df = df.copy()

    # Format Score column
    if "Score" in display_df.columns:
        display_df["Score"] = display_df["Score"].apply(lambda x: f"{x:+.2f}")

    # Style Signal column with badges
    if "Signal" in display_df.columns:
        display_df["Signal"] = display_df["Signal"].apply(lambda x: _render_badge(x, theme))

    render_dark_table(display_df, title, theme=theme)


def render_model_agreement_table(df: pd.DataFrame, title: str = "Model Agreement",
                                 theme: Optional[Theme] = None) -> None:
    """Render model agreement table with styled impact column."""
    theme = theme or get_current_theme()
    display_df = df.copy()

    # Style Impact column with consistent color coding for ALL rows
    if "Impact" in display_df.columns:
        impact_colours = {
            "Primary determinant": theme.success,
            "Cautions on growth": theme.warning,
            "Confirms growth view": theme.success,
            "Supports late-cycle view": theme.info,
            "Contained": theme.success,
            "Tightening headwind": theme.warning,
            "Easing tailwind": theme.success,
            "Neutral": theme.text_muted,
            "Supports defensive": theme.danger,
            "Allows risk-on": theme.success,
            "Caution warranted": theme.warning,
            "Confirms risk appetite": theme.success,
            "Suggests caution": theme.warning,
            "Strong confirm": theme.success,
            "Partial confirm": theme.warning,
            "Divergence warning": theme.warning,
        }

        def style_impact(val):
            # First check exact matches
            if val in impact_colours:
                color = impact_colours[val]
            else:
                # Fall back to keyword matching
                val_str = str(val).lower()
                if "primary" in val_str or "strong" in val_str or "confirms" in val_str or "allows" in val_str:
                    color = theme.success
                elif "caution" in val_str or "divergence" in val_str or "warning" in val_str or "headwind" in val_str:
                    color = theme.warning
                elif "defensive" in val_str or "tightening" in val_str:
                    color = theme.danger
                elif "contained" in val_str or "low" in val_str:
                    color = theme.success
                else:
                    color = theme.text_muted
            return f'<span style="color: {color}; font-weight: 600;">{val}</span>'

        display_df["Impact"] = display_df["Impact"].apply(style_impact)

    # Generate HTML manually for styled content
    html_parts = []

    if title:
        html_parts.append(
            f'<div style="font-size: 13px; font-weight: 600; color: {theme.text_subtle}; '
            f'margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.05em;">'
            f'{title}</div>'
        )

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

    # Header
    html_parts.append(f'<thead><tr style="background-color: {theme.elevated};">')
    for col in display_df.columns:
        html_parts.append(
            f'<th style="border-bottom: 2px solid {theme.border}; padding: 12px; text-align: left; font-weight: 600; color: {theme.text};"'
            f'>{col}</th>'
        )
    html_parts.append('</tr></thead>')

    # Body
    html_parts.append('<tbody>')
    # FIXED: Use enumerate(display_df.iterrows()) so row_num is a plain int;
    # the original code used `idx % 2 == 0` on the DataFrame label which
    # fails for non-integer or non-zero-based indices.
    for row_num, (_, row) in enumerate(display_df.iterrows()):
        bg_color = theme.card_bg if row_num % 2 == 0 else theme.card_bg_secondary  # FIXED
        html_parts.append(f'<tr style="border-bottom: 1px solid {theme.border_light}; background-color: {bg_color};">')
        for col in display_df.columns:
            val = row.get(col, "")
            html_parts.append(
                f'<td style="padding: 10px 12px; color: {theme.text_muted};"'
                f'>{val}</td>'
            )
        html_parts.append('</tr>')
    html_parts.append('</tbody></table>')

    st.markdown(''.join(html_parts), unsafe_allow_html=True)
