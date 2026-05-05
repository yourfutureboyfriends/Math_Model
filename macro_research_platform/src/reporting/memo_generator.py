"""
memo_generator.py — Auto-generate plain-English investment memos.

Financial context:
  A good investment memo does three things:
    1. States the current view clearly and simply.
    2. Explains the transmission mechanism — HOW does the macro picture
       translate into asset prices?
    3. Specifies what would invalidate the view (risk to the thesis).

  This module generates two versions:
    - Brief memo: one paragraph, suitable for a committee update.
    - Detailed memo: four sections covering what changed, why it matters,
      portfolio implications, and what would prove it wrong.

  These are TEMPLATE-BASED memos, not AI-generated prose.  They are
  deliberately simple so you can see exactly how the output is constructed
  and improve them for your specific fund context.
"""

# Import shared interpretation module for consistent metric labels
from src.utils.metric_interpretation import (
    interpret_inflation,
    interpret_growth,
    interpret_financial_conditions_ease,
    interpret_risk_appetite,
    interpret_recession_risk,
)

# Import new sector model (functions to be adapted)
# from src.models.portfolio_construction.sector_allocation_model import ...

# Placeholder for backward compatibility
SECTOR_CONFIG = {
    "Technology": {"rationale": "Growth-oriented, rates-sensitive"},
    "Healthcare": {"rationale": "Defensive, stable demand"},
    "Financials": {"rationale": "Rates-sensitive, cyclical"},
    "Energy": {"rationale": "Commodity-driven, inflation-sensitive"},
    "Utilities": {"rationale": "Defensive, bond-like"},
    "Consumer_Discretionary": {"rationale": "Cyclical, consumer-driven"},
    "Industrials": {"rationale": "Cyclical, global trade"},
}


def get_sectors_by_signal(sector_signals: dict) -> dict:
    """Group sectors by signal type.

    Returns dict with keys: Overweight, Neutral, Underweight
    """
    grouped = {"Overweight": [], "Neutral": [], "Underweight": []}
    for sector, signal in sector_signals.items():
        if signal in grouped:
            grouped[signal].append(sector)
    return grouped


# ---------------------------------------------------------------------------
# Text building blocks
# ---------------------------------------------------------------------------

def _describe_score(score: float, positive_words: tuple, negative_words: tuple) -> str:
    """Pick a descriptive word based on how positive or negative the score is."""
    if score > 1.0:
        return positive_words[0]
    elif score > 0.3:
        return positive_words[1]
    elif score > -0.3:
        return "stable"
    elif score > -1.0:
        return negative_words[0]
    else:
        return negative_words[1]


def _growth_descriptor(score: float) -> str:
    return _describe_score(score,
        positive_words=("strongly improving", "improving"),
        negative_words=("weakening", "deteriorating sharply"),
    )


def _inflation_descriptor(score: float, change: float = None) -> str:
    """Use shared interpretation for consistent inflation descriptions."""
    interp = interpret_inflation(score, change)
    return interp.interpretation


def _liquidity_descriptor(score: float) -> str:
    return _describe_score(score,
        positive_words=("very loose", "accommodative"),
        negative_words=("tightening", "very tight"),
    )


def _risk_descriptor(score: float) -> str:
    return _describe_score(score,
        positive_words=("very low", "low"),
        negative_words=("moderate", "elevated"),
    )


def _invalidation_condition(regime: str) -> str:
    """Return the key data trigger that would invalidate the current regime view."""
    conditions = {
        "Goldilocks": (
            "a surprise re-acceleration in core inflation (taking it durably above 3%) "
            "or a sharp deterioration in PMIs below 50, which would shift the regime to "
            "Reflation or Slowdown respectively."
        ),
        "Reflation": (
            "a sudden weakening in PMIs and employment data signalling that growth is "
            "rolling over before inflation is controlled — which would push into Stagflation. "
            "Alternatively, a rapid disinflation without growth damage would signal Goldilocks."
        ),
        "Slowdown": (
            "a resurgence in commodity prices or wages that re-accelerates inflation "
            "even as growth slows — the Stagflation scenario.  Alternatively, a faster-than-"
            "expected fiscal or monetary stimulus response could restore growth (Goldilocks)."
        ),
        "Stagflation": (
            "inflation breaking lower convincingly (e.g. CPI falling below 4% YoY) while "
            "central banks signal a pause in tightening.  Also watch for a growth shock so "
            "severe it forces emergency monetary easing despite elevated inflation."
        ),
    }
    return conditions.get(regime, "a significant shift in either growth or inflation direction.")


def _transmission_mechanism(regime: str, directions: dict[str, str]) -> str:
    """Explain how the current macro environment feeds into asset prices."""
    mechs = {
        "Goldilocks": (
            "Improving growth supports earnings revisions higher across cyclical sectors. "
            "Stable or falling inflation means central banks can remain patient, keeping real "
            "rates low and supporting equity valuations (particularly in rate-sensitive sectors "
            "like technology).  Credit spreads are likely to remain well-behaved, reducing "
            "refinancing risk across corporate bonds."
        ),
        "Reflation": (
            "Rising growth and inflation creates a 'rising tide' for nominal revenues: "
            "cyclicals, commodities, and banks tend to outperform in this environment. "
            "However, rising inflation will eventually prompt central bank tightening, which "
            "begins to compress equity multiples for long-duration assets like technology. "
            "The yield curve is likely to steepen, benefiting bank net interest margins."
        ),
        "Slowdown": (
            "Falling growth compresses earnings expectations for cyclical sectors.  However, "
            "falling inflation gives central banks room to cut rates, which is supportive of "
            "bond-like assets (utilities, healthcare) and high-quality bonds.  Credit spreads "
            "may widen as default concerns rise, particularly for high-yield issuers."
        ),
        "Stagflation": (
            "The most challenging environment for conventional portfolios.  Falling growth "
            "compresses earnings while rising inflation forces central banks to keep rates "
            "elevated (or continue tightening), compressing equity multiples simultaneously. "
            "Bonds provide limited protection because inflation erodes their real value. "
            "Hard assets (energy, commodities, real assets) historically provide the best "
            "shelter in this regime."
        ),
    }
    return mechs.get(regime, "The regime is transitional — the model is watching for clearer direction.")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_brief_memo(
    regime: str,
    scores: dict[str, float],
    directions: dict[str, str],
    signals: dict[str, str],
    allocation_allowed: bool = True,
) -> str:
    """Generate a short one-paragraph investment memo."""
    grouped = get_sectors_by_signal(signals)
    ow  = ", ".join(grouped["Overweight"])  or "none"
    n   = ", ".join(grouped["Neutral"])     or "none"
    uw  = ", ".join(grouped["Underweight"]) or "none"

    # Use shared interpretation for consistent metric descriptions
    g_interp = interpret_growth(scores["growth"])
    i_interp = interpret_inflation(scores["inflation"])
    l_interp = interpret_financial_conditions_ease(scores["liquidity"])
    r_interp = interpret_risk_appetite(scores["risk"])

    # Build memo with consistent interpretations
    memo = (
        f"The model points to a **{regime}** environment with {i_interp.interpretation}. "
        f"{g_interp.interpretation}. "
        f"{l_interp.interpretation}, while {r_interp.interpretation.lower()}. "
    )

    # Add allocation status warning if not allowed
    if not allocation_allowed:
        memo += (
            f"\n\n**IMPORTANT:** Allocation is currently NOT ALLOWED due to insufficient live data. "
            f"The signals below are partial model outputs and should not be treated as current "
            f"portfolio recommendations. "
        )
    else:
        memo += (
            f"This suggests considering overweighting **{ow}**, "
            f"staying neutral on **{n}**, and underweighting **{uw}**."
        )

    memo += f" The main risk to this view would be {_invalidation_condition(regime)}"

    return memo


def generate_detailed_memo(
    regime: str,
    scores: dict[str, float],
    directions: dict[str, str],
    signals: dict[str, str],
    top_indicators: dict[str, float] | None = None,
) -> str:
    """Generate a detailed four-section investment memo."""
    grouped = get_sectors_by_signal(signals)
    ow  = ", ".join(grouped["Overweight"])  or "none"
    n   = ", ".join(grouped["Neutral"])     or "none"
    uw  = ", ".join(grouped["Underweight"]) or "none"

    # Section 1: What changed
    growth_dir = directions.get("growth", "stable")
    infl_dir   = directions.get("inflation", "stable")
    liq_dir    = directions.get("liquidity", "stable")
    risk_dir   = directions.get("risk", "stable")

    what_changed = (
        f"Over the past three months, the growth score has been {growth_dir} "
        f"(current score: {scores['growth']:+.2f}), while the inflation score has been "
        f"{infl_dir} (current score: {scores['inflation']:+.2f}).  "
        f"Liquidity conditions are {liq_dir} "
        f"(score: {scores['liquidity']:+.2f}), and market risk sentiment is {risk_dir} "
        f"(score: {scores['risk']:+.2f}).  This combination places us in the **{regime}** regime."
    )

    # Section 2: Why it matters
    why_it_matters = _transmission_mechanism(regime, directions)

    # Section 3: Portfolio implications
    ow_rationale = "; ".join(
        f"{s} ({SECTOR_CONFIG[s]['description'].split('.')[0]})"
        for s in grouped["Overweight"]
    ) or "none at this time"
    uw_rationale = "; ".join(
        f"{s} ({SECTOR_CONFIG[s]['description'].split('.')[0]})"
        for s in grouped["Underweight"]
    ) or "none at this time"

    portfolio = (
        f"Given the {regime} regime, the model recommends **overweighting** {ow} "
        f"and **underweighting** {uw}.  Sectors on neutral signal include {n}.\n\n"
        f"Overweight rationale: {ow_rationale}.\n\n"
        f"Underweight rationale: {uw_rationale}."
    )

    # Section 4: What would prove this wrong
    risk_to_view = _invalidation_condition(regime)

    memo = f"""## Investment Memo — Macro Regime Model

**Current Regime: {regime}**

---

### What changed
{what_changed}

---

### Why it matters
{why_it_matters}

---

### Portfolio implication
{portfolio}

---

### What would prove this wrong
Watch for {risk_to_view}

---

*This memo is model-generated from macro indicators.  It should support investment
judgement, not replace it.  Sector performance also depends on valuation, earnings
momentum, positioning, and sentiment — none of which are captured here.*
"""
    return memo
