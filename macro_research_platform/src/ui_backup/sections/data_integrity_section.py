"""
Data Integrity Section

Renders data integrity and lineage information with vertically centered icons.

# =============================================================================
# CHANGE SUMMARY
# =============================================================================
# FIXED: lineage_exists used Path("outputs/data_lineage_report.csv").exists()
#        — a relative path that resolves against the process CWD, which varies
#        depending on how Streamlit is launched. Replaced with an absolute path
#        anchored to this file's location (__file__).
# FIXED: pd.read_csv("outputs/data_lineage_report.csv") had the same relative
#        path problem.  Replaced with the absolute path via OUTPUTS_DIR.
# FIXED: lineage_icon / lineage_exists were defined inside the `with col_di2:`
#        block but referenced later in the "Data Lineage Summary" sub-section
#        outside that block. The variables are now declared before the column
#        layout so they are always in scope when referenced.
# FIXED: Zebra striping in _render_recession_table_html() used `idx % 2 == 0`
#        on the DataFrame row label; replaced with enumerate() counter.
# =============================================================================
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from ..tables import render_dark_table
from ..theme import Theme, get_current_theme

# FIXED: Resolve outputs directory relative to this source file so the path
# is always correct regardless of the process working directory.
_THIS_FILE = Path(__file__).resolve()
OUTPUTS_DIR = _THIS_FILE.parent.parent.parent.parent / "outputs"
LINEAGE_CSV = OUTPUTS_DIR / "data_lineage_report.csv"


def _get_recession_risk_color(value: str, theme: Theme) -> str:
    """Get color for recession risk value."""
    try:
        # Parse percentage from string like "15.5%"
        pct_str = str(value).replace('%', '').strip()
        pct = float(pct_str)
        if pct < 5:
            return theme.success
        elif pct <= 15:
            return theme.warning
        else:
            return theme.danger
    except (ValueError, TypeError):
        return theme.text


def _render_recession_table_html(df: pd.DataFrame, theme: Theme) -> str:
    """Generate styled HTML table with color-coded values."""
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

    # Body
    html_parts.append('<tbody>')
    # FIXED: enumerate so row_num is always a plain int for zebra striping
    for row_num, (_, row) in enumerate(df.iterrows()):
        bg_color = theme.card_bg if row_num % 2 == 0 else theme.card_bg_secondary  # FIXED
        html_parts.append(f'<tr style="border-bottom: 1px solid {theme.border_light}; background-color: {bg_color};">')

        for col in df.columns:
            val = row.get(col, "")
            if col == "Value":
                # Color-code the value based on percentage
                color = _get_recession_risk_color(val, theme)
                val = f'<span style="color: {color}; font-weight: 700; font-size: 14px;">{val}</span>'
                cell_style = f'padding: 12px;'
            elif col == "Source":
                cell_style = f'padding: 12px; color: {theme.text}; font-weight: 500;'
            else:
                cell_style = f'padding: 12px; color: {theme.text_muted};'

            html_parts.append(f'<td style="{cell_style}">{val}</td>')

        html_parts.append('</tr>')

    html_parts.append('</tbody></table>')
    return ''.join(html_parts)


def render_data_integrity_section(
    is_sample: bool,
    latest_date: datetime,
    live_series_count: int,
    global_view=None,
    world_map_df=None,
    model_results: dict = None,
    theme: Optional[Theme] = None,
) -> None:
    """
    Render the data integrity and lineage section with vertically centered icons.

    Args:
        is_sample: Whether using sample data
        latest_date: Date of latest data
        live_series_count: Number of live data series
        global_view: Global macro view object (optional)
        world_map_df: World map DataFrame (optional)
        model_results: Model results dictionary (optional)
        theme: Optional theme override
    """
    theme = theme or get_current_theme()

    st.markdown(
        f'<div style="font-size: 13px; font-weight: 600; text-transform: uppercase; '
        f'letter-spacing: 0.05em; color: {theme.text_muted}; margin-bottom: 16px;">'
        f'Data Integrity &amp; Lineage</div>',
        unsafe_allow_html=True
    )

    # FIXED: Resolve lineage_exists BEFORE the column layout so the variable
    # is in scope for both the middle card and the later "Data Lineage Summary"
    # sub-section. Also use the absolute LINEAGE_CSV path.
    lineage_exists = LINEAGE_CSV.exists()  # FIXED: was Path("outputs/...").exists()
    lineage_icon = "✓" if lineage_exists else "—"
    lineage_color = theme.success if lineage_exists else theme.text_muted
    lineage_value = "Available" if lineage_exists else "—"

    # Data Quality Summary - 3 column layout with vertically centered content
    col_di1, col_di2, col_di3 = st.columns(3)

    with col_di1:
        status_icon = "⚠️" if is_sample else "✓"
        status_color = theme.danger if is_sample else theme.success
        status_value = "Sample" if is_sample else "0"
        status_desc = "Sample data detected" if is_sample else "No critical issues"

        st.markdown(f"""
        <div style="background: {theme.card_bg}; border: 1px solid {theme.border}; border-radius: 8px; padding: 20px; display: flex; flex-direction: column; justify-content: center; min-height: 120px;">
            <div style="font-size: 11px; color: {theme.text_muted}; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px;">Data Quality Issues</div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 28px; color: {status_color};">{status_icon}</span>
                <span style="font-size: 28px; font-weight: 700; color: {status_color};">{status_value}</span>
            </div>
            <div style="font-size: 12px; color: {theme.text_subtle}; margin-top: 8px;">{status_desc}</div>
        </div>
        """, unsafe_allow_html=True)

    with col_di2:
        # FIXED: lineage_exists, lineage_icon, lineage_color, lineage_value are
        # now computed above this block so they are always in scope here.
        st.markdown(f"""
        <div style="background: {theme.card_bg}; border: 1px solid {theme.border}; border-radius: 8px; padding: 20px; display: flex; flex-direction: column; justify-content: center; min-height: 120px;">
            <div style="font-size: 11px; color: {theme.text_muted}; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px;">Data Lineage</div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 28px; color: {lineage_color};">{lineage_icon}</span>
                <span style="font-size: 28px; font-weight: 700; color: {lineage_color};">{lineage_value}</span>
            </div>
            <div style="font-size: 12px; color: {theme.text_subtle}; margin-top: 8px;">21 metrics tracked</div>
        </div>
        """, unsafe_allow_html=True)

    with col_di3:
        # FIXED: Strip tzinfo from latest_date before comparing to datetime.now()
        # to avoid TypeError when latest_date is a tz-aware pandas Timestamp.
        latest_naive = (
            latest_date.to_pydatetime().replace(tzinfo=None)
            if hasattr(latest_date, "to_pydatetime")
            else latest_date
        )
        future_date_issues = 1 if latest_naive > datetime.now() else 0
        future_icon = "⚠️" if future_date_issues > 0 else "✓"
        future_color = theme.danger if future_date_issues > 0 else theme.success
        future_value = str(future_date_issues) if future_date_issues > 0 else "0"
        future_desc = "Latest > today" if future_date_issues > 0 else "Dates valid"

        st.markdown(f"""
        <div style="background: {theme.card_bg}; border: 1px solid {theme.border}; border-radius: 8px; padding: 20px; display: flex; flex-direction: column; justify-content: center; min-height: 120px;">
            <div style="font-size: 11px; color: {theme.text_muted}; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px;">Future Date Issues</div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 28px; color: {future_color};">{future_icon}</span>
                <span style="font-size: 28px; font-weight: 700; color: {future_color};">{future_value}</span>
            </div>
            <div style="font-size: 12px; color: {theme.text_subtle}; margin-top: 8px;">{future_desc}</div>
        </div>
        """, unsafe_allow_html=True)

    # Recession Risk Hierarchy
    st.markdown(
        f'<div style="font-size: 11px; font-weight: 600; text-transform: uppercase; '
        f'letter-spacing: 0.05em; color: {theme.text_muted}; margin: 20px 0 12px 0;">'
        f'Recession Risk Hierarchy</div>',
        unsafe_allow_html=True
    )

    rec_data = []
    if model_results:
        # Top-level (from model)
        top_rec = model_results.get('recession_risk', {}).get('probability', 0)
        rec_data.append({
            "Source": "Top-Level Model",
            "Value": f"{top_rec:.1f}%",
            "Description": "Primary recession probability from ensemble model"
        })

        # Global (from global view if available)
        if global_view:
            rec_data.append({
                "Source": "Global Aggregated",
                "Value": f"{global_view.global_recession_probability_12m:.0%}",
                "Description": "Weighted average of country recession risks"
            })

        # US (from world map if available)
        if world_map_df is not None and not world_map_df.empty:
            us_row = world_map_df[world_map_df['Region'] == 'United States']
            if not us_row.empty:
                rec_data.append({
                    "Source": "US-Specific",
                    "Value": us_row.iloc[0]['Recession Risk'],
                    "Description": "US-only recession risk from country model"
                })

    rec_df = pd.DataFrame(rec_data)
    if not rec_df.empty:
        # Use custom HTML table with color-coded values
        html_table = _render_recession_table_html(rec_df, theme)
        st.markdown(html_table, unsafe_allow_html=True)

        st.info("ℹ️ **Note:** Different recession risk values may appear because they measure different things:")
        st.markdown("""
        - **Top-Level Model**: Primary model output using US macro data
        - **Global Aggregated**: Weighted average across all countries
        - **US-Specific**: US country model output only
        """)

    # Data lineage summary
    st.markdown(
        f'<div style="font-size: 11px; font-weight: 600; text-transform: uppercase; '
        f'letter-spacing: 0.05em; color: {theme.text_muted}; margin: 20px 0 12px 0;">'
        f'Data Lineage Summary</div>',
        unsafe_allow_html=True
    )

    if lineage_exists:
        try:
            # FIXED: Absolute path via LINEAGE_CSV; was "outputs/data_lineage_report.csv"
            lineage_df = pd.read_csv(LINEAGE_CSV)
            issues = lineage_df[lineage_df['status'].isin([
                'INVALID_FUTURE_DATE',
                'SCORE_POSITIVE_BUT_STATE_LOW',
                'PLACEHOLDER',
                'INSUFFICIENT_FOR_ALLOCATION'
            ])]

            if len(issues) > 0:
                st.warning(f"Found {len(issues)} data quality issues:")
                render_dark_table(
                    issues[['dashboard_metric_name', 'value_displayed', 'status', 'issue_flags']].head(10),
                    title="",
                    theme=theme
                )
            else:
                st.success("✓ No critical data quality issues found")
        except Exception as e:
            st.error(f"Could not load lineage report: {e}")
    else:
        st.info("Run `python src/data/data_lineage_reporter.py` to generate data lineage report")
