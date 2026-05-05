"""
learning_explainer.py — Educational explanations for each model output.

Financial context:
  One of the most important lessons in macro investing is understanding WHY
  a model says what it says — not just what it says.

  This module generates plain-English educational notes alongside the model's
  output so you build intuition as you use the tool.  Each explanation:

    1. States what the model found.
    2. Explains the underlying financial logic.
    3. Highlights common pitfalls or counter-intuitive behaviour.
"""

from src.models.macro_regime.classifier import REGIMES


# ---------------------------------------------------------------------------
# Regime explanations
# ---------------------------------------------------------------------------

REGIME_EDUCATIONAL: dict[str, str] = {
    "Goldilocks": """
**Why is this called Goldilocks?**
The name comes from the fairy tale — the economy is "not too hot, not too cold."
Growth is expanding, which supports corporate earnings, but inflation is not rising
fast enough to force central banks to tighten aggressively.  This combination keeps
discount rates low (supporting valuation multiples) while earnings grow.

Historically, equity markets tend to perform well in Goldilocks.  Risk assets benefit
from the "dual tailwind" of earnings growth AND stable/falling rates.

**What to watch for:**
Goldilocks rarely lasts.  It typically transitions into Reflation (if demand exceeds
supply capacity) or Slowdown (if growth momentum fades).  Watch PMI new orders,
labour market tightness, and inflation expectations for early warning signs.

**Common pitfall:**
Even in Goldilocks, markets can sell off if they were already pricing in a "perfect"
scenario.  Valuation matters — an expensive Goldilocks market has little margin for
disappointment.
""",

    "Reflation": """
**What is Reflation?**
Reflation occurs when an economy re-accelerates after a period of weakness, and this
acceleration begins to push prices higher.  It often follows a recession or slowdown.

Key drivers: strong fiscal spending, easy monetary policy, pent-up demand, or
commodity supply shocks.  The 2020-2021 period (post-COVID stimulus + supply
chain disruptions) is a recent clear example.

**Which assets tend to do well?**
- Cyclicals: energy, materials, industrials — their revenues grow with the economy.
- Banks: steeper yield curves improve net interest margins.
- Commodities: rising demand + often supply constraints.
- Equities broadly (until rates rise enough to compress multiples).

**What to watch for:**
Reflation has a natural ceiling: when inflation rises too fast, central banks hike
aggressively.  If rate hikes slow growth significantly, the regime can turn to
Stagflation (rare) or Slowdown.  Watch the pace of central bank response.
""",

    "Slowdown": """
**What is a Slowdown?**
Growth is falling AND inflation is falling.  This is the disinflation phase of the
cycle, often driven by tighter financial conditions (rate hikes taking effect),
weaker corporate capex, or fading consumer confidence.

**Why do bonds and defensives outperform?**
Two reasons:
  1. Falling inflation → central banks can cut rates → bond prices rise.
  2. Falling growth → investors seek stability → healthcare, utilities, staples.

**A key insight: markets often anticipate the recovery.**
Ironically, stock markets can rally during slowdowns if the market believes the
central bank will cut rates aggressively.  The trough in equities often comes BEFORE
the trough in economic data.  This is why market prices lead macro data.

**Common pitfall:**
Slowdown feels safe because inflation is falling.  But corporate earnings are also
falling — and if earnings fall faster than rates, equity markets still decline.
""",

    "Stagflation": """
**What is Stagflation — and why is it the worst?**
Stagflation = stagnant growth + elevated inflation.  Central banks face a
"monetary trilemma": they cannot simultaneously fight inflation (raise rates) and
support growth (cut rates).

The 1970s oil-shock era is the canonical example.  The 2022 episode was a mild version.

**Why is it bad for most assets?**
- Equities: earnings fall (weak economy) AND multiples compress (high rates).
- Bonds: inflation erodes their real value.
- Cash: negative real returns if inflation > interest rates.

**What provides protection?**
- Commodities (especially energy — often the CAUSE of stagflation).
- Real assets (infrastructure, real estate if rates not too high).
- Short-duration bonds or inflation-linked bonds (TIPS/gilts).

**Key learning:**
Stagflation often forces markets to price in a "recession cure" — where a deep enough
slowdown kills inflation and eventually allows rate cuts.  Timing this inflection is
extremely difficult.
""",
}


# ---------------------------------------------------------------------------
# Score explanations
# ---------------------------------------------------------------------------

def explain_score(group: str, score: float, direction: str) -> str:
    """Return a plain-English explanation of a group score."""
    templates = {
        "growth": (
            f"The growth score is **{score:+.2f}** and {direction}.  "
            "This score aggregates PMI, GDP growth, industrial production, retail sales, "
            "and unemployment into a single z-score-based measure.\n\n"
            "A positive score means growth is running above its recent historical average; "
            "negative means below.  The **direction** (improving vs deteriorating) is more "
            "important than the absolute level for regime classification."
        ),
        "inflation": (
            f"The inflation score is **{score:+.2f}** and {direction}.  "
            "This aggregates CPI, core CPI, PPI, wages, and oil price z-scores.\n\n"
            "A high positive score means inflation is running hot relative to recent history. "
            "A deeply negative score suggests disinflationary pressure.  "
            "Remember: the model measures RELATIVE inflation pressure, not whether inflation "
            "is 'high' in absolute terms."
        ),
        "liquidity": (
            f"The liquidity score is **{score:+.2f}** and {direction}.  "
            "This aggregates policy rate, yield curve, credit spreads, and money supply growth.\n\n"
            "A positive score means financial conditions are accommodative — credit is cheap "
            "and available, which supports asset prices.  A negative score means conditions "
            "are tight — borrowing is expensive, which pressures valuations and earnings."
        ),
        "risk": (
            f"The market risk score is **{score:+.2f}** and {direction}.  "
            "This aggregates VIX, equity momentum, the dollar index, and HY spreads.\n\n"
            "A positive risk score means markets are in risk-ON mode: volatility is low, "
            "equities are trending up, and credit markets are calm.  "
            "A negative score signals risk-OFF: fear is elevated, momentum is weak."
        ),
    }
    return templates.get(group, f"Score for {group}: {score:+.2f}, direction: {direction}.")


# ---------------------------------------------------------------------------
# Indicator-level explanations
# ---------------------------------------------------------------------------

INDICATOR_EDUCATIONAL: dict[str, str] = {
    "pmi": (
        "PMI is a survey of purchasing managers.  Above 50 = expansion; below 50 = contraction.  "
        "It is one of the best LEADING indicators — it turns before GDP data is published."
    ),
    "gdp_growth": (
        "GDP is the broadest output measure, but it is LAGGING — we learn Q1 GDP in late April.  "
        "Markets move on PMI and earnings first; GDP confirms the story."
    ),
    "unemployment_rate": (
        "Unemployment LAGS the cycle by ~6 months.  The rate peaks AFTER the recession ends.  "
        "Watch jobless CLAIMS (weekly) for a more timely signal."
    ),
    "yield_curve": (
        "An inverted yield curve (2Y > 10Y) has preceded every US recession since 1970, "
        "typically 12-18 months in advance.  The current slope signals whether banks are "
        "incentivised to lend (positive slope = profitable to borrow short, lend long)."
    ),
    "credit_spreads": (
        "Credit spreads are one of the most reliable LEADING risk indicators.  They often "
        "widen months before equity markets fall.  Watch for spreads rising while equities "
        "are still stable — a classic early warning."
    ),
    "vix": (
        "VIX is a FEAR index, not a prediction tool.  It tells you how worried options markets "
        "are RIGHT NOW.  At extremes (VIX > 40), it has historically been a strong contrarian "
        "buy signal — fear is highest at or near market bottoms."
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_regime_educational_note(regime: str) -> str:
    """Return the educational note for a given regime."""
    return REGIME_EDUCATIONAL.get(regime, f"Educational note for {regime} not yet written.")


def get_score_explanation(
    scores: dict[str, float],
    directions: dict[str, str],
) -> str:
    """Return a formatted multi-section educational explanation of all four scores."""
    sections = []
    for group in ["growth", "inflation", "liquidity", "risk"]:
        sections.append(f"### {group.capitalize()} Score\n" +
                        explain_score(group, scores[group], directions.get(group, "stable")))
    return "\n\n".join(sections)


def get_indicator_note(indicator: str) -> str:
    """Return an educational note for a specific indicator."""
    return INDICATOR_EDUCATIONAL.get(indicator, "")


def get_model_limitations() -> str:
    """Return a plain-English summary of what the model cannot do."""
    return """
## Model Limitations

**This model is a framework, not a prediction machine.**

1. **Macro data is lagged.**  GDP data arrives 30+ days after quarter-end and is
   often revised.  PMI is more timely but is a SURVEY, not hard data.

2. **Markets move on expectations, not current data.**  A weak PMI that beats
   expectations can cause markets to rally.  The model scores actual data, not
   whether it surprised.

3. **Valuation is not captured.**  An overweight signal in a sector that is
   already trading at 30× earnings has a lower expected return than the same
   signal in a sector at 12× earnings.

4. **Positioning and sentiment matter.**  If the whole market is already
   positioned for Goldilocks, the trade is crowded and the upside is limited.

5. **Regime changes happen faster than data.**  The model uses monthly data.
   Crises (e.g. COVID, SVB) can shift regimes in days — the model will lag.

6. **Single-country bias.**  This version uses US-centric data.  For a global
   fund, you would want separate models for US, Europe, EM, etc.

**Use this model as a starting point for investment discussion, not as a
mechanical trading signal.**
"""
