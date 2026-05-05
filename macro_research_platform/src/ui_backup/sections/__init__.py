"""
Dashboard Sections Package

Each section of the dashboard is encapsulated in a module here.
"""

from .data_status_section import render_data_status_section
from .executive_summary_section import render_executive_summary_section
from .key_metrics_section import render_key_metrics_section
from .signal_snapshot_section import render_signal_snapshot_section
from .sector_allocation_section import render_sector_allocation_section
from .model_agreement_section import render_model_agreement_section
from .transmission_section import render_transmission_section
from .investment_memo_section import render_investment_memo_section
from .business_layer_section import render_business_layer_section
from .data_integrity_section import render_data_integrity_section
from .advanced_indicators_section import render_advanced_indicators_section

# Import section divider
from ..theme import section_divider_html

__all__ = [
    "render_data_status_section",
    "render_executive_summary_section",
    "render_key_metrics_section",
    "render_signal_snapshot_section",
    "render_sector_allocation_section",
    "render_model_agreement_section",
    "render_transmission_section",
    "render_investment_memo_section",
    "render_business_layer_section",
    "render_data_integrity_section",
    "render_advanced_indicators_section",
]
