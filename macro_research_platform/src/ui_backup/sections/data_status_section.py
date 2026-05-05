"""
Data Status Section

Renders the data status panel showing data mode, freshness, and allocation gating.
"""

from datetime import datetime
from typing import Optional

import streamlit as st

from ..components import render_status_badge
from ..theme import Theme, get_current_theme


def render_data_status_section(
    is_sample: bool,
    live_series_count: int,
    days_since: int,
    latest_date: datetime,
    allocation_allowed: bool,
    allocation_reason: str,
    theme: Optional[Theme] = None,
) -> None:
    """
    Render the data status panel.

    Args:
        is_sample: Whether using sample data
        live_series_count: Number of live data series available
        days_since: Days since last data update
        latest_date: Date of latest data
        allocation_allowed: Whether allocation is allowed
        allocation_reason: Explanation for allocation status
        theme: Optional theme override
    """
    theme = theme or get_current_theme()

    # MINIMUM REQUIREMENTS for allocation
    MIN_CORE_MACRO_SERIES = 8
    MIN_MARKET_RISK_SERIES = 4
    MIN_TOTAL_SERIES = MIN_CORE_MACRO_SERIES + MIN_MARKET_RISK_SERIES

    # Check if minimums are met
    min_requirements_met = (live_series_count >= MIN_TOTAL_SERIES) and (
        live_series_count >= MIN_CORE_MACRO_SERIES
    )

    # Determine data mode display
    if is_sample:
        data_mode = "Sample"
        mode_color = theme.warning
        mode_bg = theme.warning_bg
        warning_msg = "Sample data mode - outputs are not current investment views."
    elif days_since > 90:
        data_mode = "Stale Live"
        mode_color = theme.danger
        mode_bg = theme.danger_bg
        warning_msg = f"Data is {days_since} days old (stale)."
    elif days_since < 0:
        data_mode = "Invalid"
        mode_color = theme.danger
        mode_bg = theme.danger_bg
        warning_msg = f"Future-dated data detected."
    elif not min_requirements_met:
        data_mode = "Partial Live"
        mode_color = theme.warning
        mode_bg = theme.warning_bg
        warning_msg = f"Insufficient live data ({live_series_count}/{MIN_TOTAL_SERIES} series)."
    elif days_since > 45:
        data_mode = "Cached Live"
        mode_color = theme.info
        mode_bg = theme.info_bg
        warning_msg = "Using cached live data."
    else:
        data_mode = "Live"
        mode_color = theme.success
        mode_bg = theme.success_bg
        warning_msg = "Live data mode active."

    # Data quality details
    data_quality_details = f"""
    <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid {theme.border};">
        <div style="font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: {theme.text_muted}; margin-bottom: 8px;">Data Requirements Check</div>
        <div style="display: flex; gap: 24px; flex-wrap: wrap; font-size: 12px;">
            <div>
                <span style="color: {theme.success if live_series_count >= MIN_CORE_MACRO_SERIES else theme.danger};">●</span>
                Core Macro Series: {live_series_count if not is_sample else 0}/{MIN_CORE_MACRO_SERIES}
            </div>
            <div>
                <span style="color: {theme.success if live_series_count >= MIN_MARKET_RISK_SERIES else theme.danger};">●</span>
                Market/Risk Series: {live_series_count if not is_sample else 0}/{MIN_MARKET_RISK_SERIES}
            </div>
            <div>
                <span style="color: {theme.success if min_requirements_met else theme.danger};">●</span>
                Minimum Met: {'Yes' if min_requirements_met else 'No'}
            </div>
        </div>
        <div style="font-size: 11px; color: {theme.text_muted}; margin-top: 8px; font-style: italic;">
            Reason: {allocation_reason}
        </div>
    </div>
    """

    # Render the status panel
    st.markdown(f"""
    <div style="background: {theme.card_bg}; border: 1px solid {theme.border}; border-radius: 8px; padding: 16px 20px; margin-bottom: 24px;">
        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px;">
            <div style="display: flex; align-items: center; gap: 12px;">
                <div style="background: {mode_bg}; border: 1px solid {mode_color}; border-radius: 6px; padding: 6px 12px;">
                    <span style="color: {mode_color}; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;">{data_mode} Mode</span>
                </div>
                <div style="font-size: 13px; color: {theme.text_muted};">
                    {warning_msg}
                </div>
            </div>
            <div style="display: flex; gap: 24px; flex-wrap: wrap;">
                <div>
                    <div style="font-size: 10px; color: {theme.text_muted}; text-transform: uppercase; letter-spacing: 0.05em;">Latest Data Date</div>
                    <div style="font-size: 13px; font-weight: 600; color: {theme.text};">{latest_date.strftime('%Y-%m-%d')}</div>
                </div>
                <div>
                    <div style="font-size: 10px; color: {theme.text_muted}; text-transform: uppercase; letter-spacing: 0.05em;">Days Since Update</div>
                    <div style="font-size: 13px; font-weight: 600; color: {theme.text};">{days_since if not is_sample else 'N/A'}</div>
                </div>
                <div>
                    <div style="font-size: 10px; color: {theme.text_muted}; text-transform: uppercase; letter-spacing: 0.05em;">Series Available</div>
                    <div style="font-size: 13px; font-weight: 600; color: {theme.text};">{live_series_count if not is_sample else 17}</div>
                </div>
                <div>
                    <div style="font-size: 10px; color: {theme.text_muted}; text-transform: uppercase; letter-spacing: 0.05em;">Allocation Allowed</div>
                    <div style="font-size: 13px; font-weight: 600; color: {theme.success if allocation_allowed else theme.danger};">{'Yes' if allocation_allowed else 'No'}</div>
                </div>
            </div>
        </div>
        {data_quality_details if not is_sample else ""}
    </div>
    """, unsafe_allow_html=True)
