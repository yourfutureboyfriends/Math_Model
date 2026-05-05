"""
Business Layer Section

Renders business layer outputs including recommendations, expected returns, position sizing, etc.

# =============================================================================
# CHANGE SUMMARY
# =============================================================================
# FIXED: Expected Returns table accessed hard-coded column names without
#        checking whether they exist in the loaded CSV.  A CSV with different
#        or fewer columns would raise KeyError and crash the section.  Added
#        safe column selection that filters to only columns that are present.
# FIXED: Position Sizing table had the same unchecked column access issue.
# FIXED: Signal Scorecard table had the same unchecked column access issue.
# FIXED: Decision Log table had the same unchecked column access issue.
# FIXED: memo_content was wrapped in a combined <style>+<div>+<pre> HTML block
#        passed to st.markdown(unsafe_allow_html=True).  In several Streamlit
#        versions a leading <style> tag prevents the rest of the HTML from
#        rendering, causing the raw tag strings to appear as visible text
#        (e.g. "<div class="memo-content">") on screen.  Replaced with a plain
#        st.markdown(memo_content) call — the content is already valid markdown
#        and Streamlit's native renderer handles it correctly without any wrapper.
# =============================================================================
"""

# FIXED: Removed `import html as html_module` — the html.escape() call was
# only needed for the old HTML-wrapper approach that is now replaced with
# direct st.markdown(memo_content).  See CHANGE SUMMARY above.
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from ..tables import render_dark_table
from ..theme import Theme, get_current_theme


def _safe_select_columns(df: pd.DataFrame, desired: list) -> pd.DataFrame:
    """
    Select only the columns that actually exist in df.

    FIXED: Prevents KeyError when a CSV is missing some expected columns.
    """
    available = [c for c in desired if c in df.columns]
    return df[available].copy()


def load_business_outputs(outputs_dir: Path) -> dict:
    """Load business layer output files."""
    business_data = {
        "recommendations": None,
        "expected_returns": None,
        "position_sizing": None,
        "signal_scorecard": None,
        "decision_log": None,
        "ic_pack_exists": False,
    }

    # Load recommendation summary
    rec_path = outputs_dir / "latest_recommendation_summary.md"
    if rec_path.exists():
        with open(rec_path) as f:
            business_data["recommendations"] = f.read()

    # Load expected return scores
    er_path = outputs_dir / "latest_expected_return_scores.csv"
    if er_path.exists():
        business_data["expected_returns"] = pd.read_csv(er_path)

    # Load position sizing
    ps_path = outputs_dir / "latest_position_sizing.csv"
    if ps_path.exists():
        business_data["position_sizing"] = pd.read_csv(ps_path)

    # Load signal scorecard
    ss_path = outputs_dir / "latest_signal_scorecard.csv"
    if ss_path.exists():
        business_data["signal_scorecard"] = pd.read_csv(ss_path)

    # Load decision log
    dl_path = outputs_dir / "latest_decision_log.csv"
    if dl_path.exists():
        business_data["decision_log"] = pd.read_csv(dl_path)

    # Check if IC pack exists
    ic_files = list(outputs_dir.glob("investment_committee_pack_*.md"))
    if ic_files:
        business_data["ic_pack_path"] = str(ic_files[-1])
        business_data["ic_pack_exists"] = True

    return business_data


def render_business_layer_section(theme: Optional[Theme] = None) -> None:
    """Render the business layer outputs section.

    Args:
        theme: Optional theme override
    """
    theme = theme or get_current_theme()

    st.markdown(
        f'<div style="font-size: 13px; font-weight: 600; text-transform: uppercase; '
        f'letter-spacing: 0.05em; color: {theme.text_muted}; margin-bottom: 16px;">'
        f'Business Layer Outputs</div>',
        unsafe_allow_html=True
    )

    outputs_dir = Path(__file__).parent.parent.parent.parent / "outputs"
    business_data = load_business_outputs(outputs_dir)

    # Recommendations
    if business_data["recommendations"]:
        with st.expander("Recommendation Summary", expanded=True):
            memo_content = business_data["recommendations"]
            # FIXED: Previously wrapped memo_content in a <style>+<div>+<pre>
            # HTML block with unsafe_allow_html=True.  In several Streamlit
            # versions a <style> tag at the start of st.markdown() prevents the
            # subsequent HTML from rendering, causing the raw tag strings
            # (<div class="memo-content">, <pre style="...">) to appear as
            # visible text on screen.  Solution: render the memo directly as
            # native Streamlit markdown (no HTML wrapper needed — the content is
            # already well-formed markdown).  Theme-level CSS already styles
            # headings and text, so no extra <style> block is required.
            st.markdown(memo_content)
    else:
        st.warning("Business outputs not found. Run `python pipeline.py --mode run-sample` to generate.")

    # Expected Returns Table
    if business_data["expected_returns"] is not None:
        with st.expander("Expected Return Scores"):
            er_df = business_data["expected_returns"]
            # FIXED: Only select columns that actually exist in the DataFrame
            desired_er = ["asset_or_sector", "expected_return_score", "sharpe_estimate",
                          "confidence", "interpretation"]
            er_display = _safe_select_columns(er_df, desired_er)
            # Rename only the columns that were selected
            rename_map = {
                "asset_or_sector": "Asset/Sector",
                "expected_return_score": "Expected Return",
                "sharpe_estimate": "Sharpe Ratio",
                "confidence": "Confidence",
                "interpretation": "Interpretation",
            }
            er_display.rename(columns={k: v for k, v in rename_map.items() if k in er_display.columns}, inplace=True)
            render_dark_table(er_display, title="", theme=theme)

    # Position Sizing Table
    if business_data["position_sizing"] is not None:
        with st.expander("Position Sizing"):
            ps_df = business_data["position_sizing"]
            # FIXED: Only select columns that actually exist in the DataFrame
            desired_ps = ["asset_or_sector", "suggested_position_size", "position_bucket",
                          "conviction", "reason"]
            ps_display = _safe_select_columns(ps_df, desired_ps)
            rename_map = {
                "asset_or_sector": "Asset/Sector",
                "suggested_position_size": "Position Size",
                "position_bucket": "Bucket",
                "conviction": "Conviction",
                "reason": "Reason",
            }
            ps_display.rename(columns={k: v for k, v in rename_map.items() if k in ps_display.columns}, inplace=True)
            render_dark_table(ps_display, title="", theme=theme)

    # Signal Scorecard
    if business_data["signal_scorecard"] is not None:
        with st.expander("Signal Scorecard"):
            ss_df = business_data["signal_scorecard"]
            # FIXED: Only select columns that actually exist in the DataFrame
            desired_ss = ["signal", "category", "status", "confidence", "research_support"]
            ss_display = _safe_select_columns(ss_df, desired_ss)
            rename_map = {
                "signal": "Signal",
                "category": "Category",
                "status": "Status",
                "confidence": "Confidence",
                "research_support": "Research Support",
            }
            ss_display.rename(columns={k: v for k, v in rename_map.items() if k in ss_display.columns}, inplace=True)
            render_dark_table(ss_display, title="", theme=theme)

    # Decision Log
    if business_data["decision_log"] is not None:
        with st.expander("Recent Decision Log"):
            dl_df = business_data["decision_log"].head(5)
            # FIXED: Only select columns that actually exist in the DataFrame
            desired_dl = ["timestamp", "recommendation_type", "headline", "conviction", "suggested_position_size"]
            dl_display = _safe_select_columns(dl_df, desired_dl)
            rename_map = {
                "timestamp": "Timestamp",
                "recommendation_type": "Type",
                "headline": "Headline",
                "conviction": "Conviction",
                "suggested_position_size": "Position",
            }
            dl_display.rename(columns={k: v for k, v in rename_map.items() if k in dl_display.columns}, inplace=True)
            render_dark_table(dl_display, title="", theme=theme)

    # IC Pack Link
    if business_data["ic_pack_exists"]:
        ic_path = business_data.get("ic_pack_path", "")
        st.markdown(f"""
        <div style="background: {theme.info_bg}; border-left: 3px solid {theme.info}; padding: 12px 16px; margin: 16px 0; border-radius: 0 8px 8px 0;">
            <div style="font-size: 13px; color: {theme.text}; line-height: 1.5;">
                <strong>Investment Committee Pack</strong><br>
                <a href="file://{ic_path}" style="color: {theme.info}; text-decoration: none;">View Latest IC Pack</a>
            </div>
        </div>
        """, unsafe_allow_html=True)
