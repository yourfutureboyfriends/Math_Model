"""
Transmission Analysis Section

Renders the transmission channels analysis (rates, credit, earnings, valuation).
"""

from typing import Optional

import streamlit as st

from ..theme import Theme, get_current_theme


def get_transmission_analysis(
    growth: float,
    inflation: float,
    liquidity: float,
    risk: float,
) -> dict:
    """Generate transmission channel analysis."""
    # Rates channel
    if liquidity > 0.5:
        rates = "Accommodative policy stance supports growth. Low real rates encourage risk-taking."
    elif liquidity < -0.5:
        rates = "Tightening cycle underway. Higher rates pressure duration-sensitive assets and leveraged strategies."
    else:
        rates = "Neutral policy stance. Rates not currently a dominant driver of asset returns."

    # Credit channel
    if risk > 0.5:
        credit = "Tight credit spreads reflect risk appetite. Credit availability supports economic activity."
    elif risk < -0.5:
        credit = "Widening spreads signal credit stress. Reduced credit availability may constrain growth."
    else:
        credit = "Credit conditions neutral. Spreads neither tight nor distressed."

    # Earnings channel
    if growth > 0.5:
        earnings = "Positive growth momentum supports forward earnings estimates. Revenue growth likely to beat."
    elif growth < -0.5:
        earnings = "Slowing growth pressures margins. Earnings revisions likely negative."
    else:
        earnings = "Growth-neutral environment. Earnings growth expected to track historical averages."

    # Valuation channel
    if inflation > 0.5:
        valuation = "Elevated inflation pressures discount rates. Multiple compression risk elevated."
    elif inflation < -0.5:
        valuation = "Low inflation supports higher multiples. Disinflationary tailwind for valuations."
    else:
        valuation = "Inflation contained. Valuation multiples supported by stable discount rate environment."

    return {
        "rates": rates,
        "credit": credit,
        "earnings": earnings,
        "valuation": valuation,
    }


def render_transmission_section(scores: dict, theme: Optional[Theme] = None) -> None:
    """
    Render the transmission channels section.

    Args:
        scores: Dictionary of scores
        theme: Optional theme override
    """
    theme = theme or get_current_theme()

    st.markdown(
        f'<div style="font-size: 13px; font-weight: 600; text-transform: uppercase; '
        f'letter-spacing: 0.05em; color: {theme.text_muted}; margin-bottom: 16px;">'
        f'Transmission Channels</div>',
        unsafe_allow_html=True
    )

    transmission = get_transmission_analysis(
        scores["growth"],
        scores["inflation"],
        scores["liquidity"],
        scores["risk"],
    )

    col_t1, col_t2 = st.columns(2)

    def transmission_card(title: str, body: str, colour: str = "#4f98a3", theme: Theme = None) -> str:
        theme = theme or get_current_theme()
        return f'''
        <div style="
            background: {theme.card_bg};
            border: 1px solid {theme.border};
            border-left: 3px solid {colour};
            border-radius: 8px;
            padding: 1rem 1.25rem;
            height: 100%;
            margin-bottom: 1rem;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        ">
            <div style="
                font-size: 0.7rem;
                font-weight: 700;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                color: {theme.text_muted};
                margin-bottom: 0.5rem;
            ">{title}</div>
            <div style="
                font-size: 0.875rem;
                color: {theme.text};
                line-height: 1.5;
            ">{body}</div>
        </div>
        '''

    with col_t1:
        for title, content in [("Rates", transmission["rates"]), ("Credit", transmission["credit"])]:
            st.markdown(transmission_card(title, content, theme.info, theme), unsafe_allow_html=True)

    with col_t2:
        for title, content in [("Earnings", transmission["earnings"]), ("Valuation", transmission["valuation"])]:
            st.markdown(transmission_card(title, content, theme.info, theme), unsafe_allow_html=True)
