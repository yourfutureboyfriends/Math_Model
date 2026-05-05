"""
Investment Memo Section

Renders the investment memo with what changed, why it matters, portfolio implications, and what would prove it wrong.
"""

from typing import Optional

import streamlit as st

from ..theme import Theme, get_current_theme


def render_investment_memo_section(
    regime: str,
    scores: dict,
    directions: dict,
    regime_classification: dict,
    is_sample: bool,
    days_since: int,
    theme: Optional[Theme] = None,
) -> None:
    """
    Render the investment memo section.

    Args:
        regime: Current regime
        scores: Dictionary of scores
        directions: Dictionary of directions
        regime_classification: Regime classification details
        is_sample: Whether using sample data
        days_since: Days since last update
        theme: Optional theme override
    """
    theme = theme or get_current_theme()

    st.markdown(
        f'<div style="font-size: 13px; font-weight: 600; text-transform: uppercase; '
        f'letter-spacing: 0.05em; color: {theme.text_muted}; margin-bottom: 16px;">'
        f'Investment Memo</div>',
        unsafe_allow_html=True
    )

    # Data mode disclaimer
    if is_sample:
        st.error("""
        **SAMPLE DATA MODE**

        This output uses synthetic data for testing only. Not for investment decisions.
        Run `python pipeline.py --mode refresh-live-data` to use live FRED data.
        """)
    elif days_since > 90:
        st.warning(f"""
        **STALE DATA — {days_since} days old**

        Consider refreshing: `python pipeline.py --mode refresh-live-data`
        """)

    # Generate memo content
    growth_dir = directions.get('growth', 'stable')
    inflation_dir = directions.get('inflation', 'stable')
    liquidity_dir = directions.get('liquidity', 'stable')
    risk_dir = directions.get('risk', 'stable')

    what_changed = f"""**What changed:**
- Growth momentum is {growth_dir} (score: {scores['growth']:+.2f})
- Inflation pressure is {inflation_dir} (score: {scores['inflation']:+.2f})
- Financial conditions are {liquidity_dir} (score: {scores['liquidity']:+.2f})
- Risk appetite is {risk_dir} (score: {scores['risk']:+.2f})
"""

    why_matters = f"""**Why it matters:**
The model points to a **{regime}** environment. """

    if scores['inflation'] > 0.5 and abs(scores['growth']) < 0.5:
        why_matters += "Inflation pressure remains elevated while growth momentum is broadly neutral rather than clearly deteriorating. Low recession risk and normal credit stress argue against a full stagflation or recessionary classification."
    elif scores['growth'] > 0.5 and scores['inflation'] < 0.3:
        why_matters += "Strong growth with contained inflation supports risk asset valuations. Financial conditions are constructive."
    elif scores['growth'] < -0.5:
        why_matters += "Weakening growth momentum warrants defensive positioning. Monitor credit conditions closely."

    # Portfolio implication
    portfolio_implication = "**Portfolio implication:**\n"
    if regime == "Inflation Pressure / Late-Cycle":
        portfolio_implication += "Selective positioning rather than aggressively defensive. Inflation-sensitive exposure can be maintained, but broad cyclical risk should depend on confirmation from business conditions, credit spreads, and market momentum."
    elif regime == "Goldilocks":
        portfolio_implication += "Full risk-on positioning across cyclical assets warranted. Duration exposure should be limited given positive growth momentum."
    elif regime == "Stagflation":
        portfolio_implication += "Defensive positioning with inflation hedges. Quality and short duration preferred."
    elif regime == "Slowdown":
        portfolio_implication += "Duration and quality defensive positioning. Cyclical exposure should be reduced."
    else:
        portfolio_implication += "Diversified positioning with selective opportunities. Await clearer regime confirmation."

    # What would prove it wrong
    what_proves_wrong = "**What would prove this wrong:**\n"
    if regime == "Inflation Pressure / Late-Cycle":
        what_proves_wrong += """
- A move toward stronger growth (+0.5 or higher) with easing inflation (<0.3) would shift the model toward Goldilocks
- Weaker growth (<-0.5) alongside persistent inflation (>0.5) would raise stagflation risk and warrant defensive rotation
- Significant credit stress elevation (beyond normal levels) would increase recession probability and reduce risk appetite
"""
    elif regime == "Goldilocks":
        what_proves_wrong += """
- Inflation reacceleration above 0.5 would shift toward late-cycle inflation pressure
- Growth deterioration below 0 would threaten the positive momentum story
- Credit spread widening would signal impending regime change
"""
    else:
        what_proves_wrong += """
- Monitor growth and inflation trajectories for regime shift signals
- Credit stress indicators and recession probability for defensive urgency
- Risk appetite scores for market confirmation or divergence
"""

    # Render memo
    st.markdown(f"{what_changed}\n{why_matters}\n\n{portfolio_implication}\n\n{what_proves_wrong}")
