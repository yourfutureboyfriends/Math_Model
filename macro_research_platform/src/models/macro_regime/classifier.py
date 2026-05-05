"""
regimes.py — Classify the macro environment into one of four regimes.

Financial context:
  The 2×2 regime matrix uses growth and inflation as the two axes.
  This framework is common in macro investing (see Bridgewater's "All Weather"
  and Fidelity's sector cycle work).

  The four regimes:

  ┌─────────────────┬────────────────────┬─────────────────────┐
  │                 │  Inflation RISING   │  Inflation FALLING  │
  ├─────────────────┼────────────────────┼─────────────────────┤
  │ Growth RISING   │  REFLATION         │  GOLDILOCKS         │
  │ Growth FALLING  │  STAGFLATION       │  SLOWDOWN           │
  └─────────────────┴────────────────────┴─────────────────────┘

  Goldilocks  → the "sweet spot" — growth up, inflation not a problem.
                Risk assets perform well; central banks can stay accommodative.

  Reflation   → growth recovery with rising prices.  Cyclicals, commodities,
                and banks tend to outperform.  Central banks begin to tighten.

  Slowdown    → growth falling, inflation falling.  Defensive sectors and bonds
                outperform.  Central banks can ease.

  Stagflation → worst regime for most assets — growth falling AND inflation
                rising.  Commodities and real assets provide some protection.
                Central banks face a painful trade-off.

  We also track the LEVEL of growth score (positive/negative) so we can add
  nuance: a Reflation with a very negative growth level is early Reflation
  (just recovering) vs. late Reflation (strong growth, inflation building).
"""

import pandas as pd

REGIMES = {
    "Goldilocks":  "Growth rising, inflation falling or stable — the sweet spot for risk assets.",
    "Reflation":   "Growth rising, inflation rising — cyclicals and commodities tend to do well.",
    "Slowdown":    "Growth falling, inflation falling — defensive sectors and bonds outperform.",
    "Stagflation": "Growth falling, inflation rising — the hardest environment for most portfolios.",
}

REGIME_COLOURS = {
    "Goldilocks":  "#2ecc71",   # green
    "Reflation":   "#f39c12",   # amber
    "Slowdown":    "#3498db",   # blue
    "Stagflation": "#e74c3c",   # red
}


def classify_regime(growth_direction: str, inflation_direction: str) -> str:
    """Return the regime name given growth and inflation direction strings.

    growth_direction:    'improving' | 'stable' | 'deteriorating'
    inflation_direction: 'rising'    | 'stable' | 'falling'
    """
    growth_up = growth_direction == "improving"
    infl_up   = inflation_direction == "rising"

    if growth_up and not infl_up:
        return "Goldilocks"
    elif growth_up and infl_up:
        return "Reflation"
    elif not growth_up and not infl_up:
        return "Slowdown"
    else:
        return "Stagflation"


def get_regime_history(scores_df: pd.DataFrame, directions_window: int = 3) -> pd.Series:
    """Classify the regime at every date in the scores DataFrame.

    Uses a rolling 3-month direction window so we get a time series of regimes.
    Returns a pd.Series indexed by date with regime name strings.
    """
    regimes = []

    for i in range(len(scores_df)):
        if i < directions_window:
            regimes.append(None)
            continue

        # Growth direction at this point in history
        g_now   = scores_df["growth_score"].iloc[i]
        g_past  = scores_df["growth_score"].iloc[i - directions_window]
        i_now   = scores_df["inflation_score"].iloc[i]
        i_past  = scores_df["inflation_score"].iloc[i - directions_window]

        THRESHOLD = 0.10
        g_dir = "improving" if (g_now - g_past) > THRESHOLD else \
                "deteriorating" if (g_now - g_past) < -THRESHOLD else "stable"
        i_dir = "rising"    if (i_now - i_past) > THRESHOLD else \
                "falling"   if (i_now - i_past) < -THRESHOLD else "stable"

        regimes.append(classify_regime(g_dir, i_dir))

    return pd.Series(regimes, index=scores_df.index, name="regime")


def get_regime_description(regime: str) -> str:
    """Return a short description of a regime."""
    return REGIMES.get(regime, "Unknown regime")


def get_regime_colour(regime: str) -> str:
    """Return a hex colour string for a regime (useful in dashboard charts)."""
    return REGIME_COLOURS.get(regime, "#95a5a6")
