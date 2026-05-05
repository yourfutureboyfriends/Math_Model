"""
Regime Model - Aggregate indicator z-scores into four group scores.

Financial context:
  We have ~20 individual indicators. Rather than looking at each one in
  isolation, we want to know the overall state of each macro dimension:

    Growth score    — Is the economy expanding or contracting?
    Inflation score — Is inflation pressure building or easing?
    Liquidity score — Are financial conditions loose or tight?
    Risk score      — Is market sentiment risk-on or risk-off?

  Method:
    1. Take the rolling z-score for each indicator.
    2. Flip the sign for indicators where HIGHER = WORSE.
    3. Average the adjusted z-scores within each group.

  The result is a score roughly in the range [-3, +3].
  Positive = healthier / more inflationary / looser / risk-on.
  Negative = weaker / disinflationary / tighter / risk-off.

  DIRECTION tells us which way the score is moving over the last 3 months.
  This is used for regime classification.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional

# Import from data_loader for indicator config
from src.data.data_loader import INDICATOR_CONFIG, INDICATORS_BY_GROUP, GROUPS

DIRECTION_WINDOW = 3  # months to look back when computing score direction


def compute_group_scores(df_transformed: pd.DataFrame) -> pd.DataFrame:
    """
    Compute four group scores (growth, inflation, liquidity, risk) for every date.

    Returns a DataFrame with columns:
      growth_score, inflation_score, liquidity_score, risk_score
    indexed by date.
    """
    scores: Dict[str, pd.Series] = {}

    for group in GROUPS:
        indicators = INDICATORS_BY_GROUP[group]
        adjusted_zscores = []

        for ind in indicators:
            col = f"{ind}_zscore"
            if col not in df_transformed.columns:
                continue

            z = df_transformed[col].copy()

            # Flip sign for indicators where higher = negative for the group.
            if not INDICATOR_CONFIG[ind]["higher_is_positive"]:
                z = -z

            adjusted_zscores.append(z)

        if adjusted_zscores:
            # Simple equal-weight average across indicators in the group.
            scores[f"{group}_score"] = pd.concat(adjusted_zscores, axis=1).mean(axis=1)
        else:
            scores[f"{group}_score"] = pd.Series(0.0, index=df_transformed.index)

    return pd.DataFrame(scores)


def compute_score_directions(scores_df: pd.DataFrame) -> Dict[str, str]:
    """
    Return the 3-month trend direction for each group score at the latest date.

    Returns a dict like:
      {'growth': 'improving', 'inflation': 'rising', 'liquidity': 'loosening', 'risk': 'rising'}
    """
    if len(scores_df) < DIRECTION_WINDOW + 1:
        # Not enough history
        return {g: "stable" for g in GROUPS}

    current = scores_df.iloc[-1]
    past = scores_df.iloc[-(DIRECTION_WINDOW + 1)]
    delta = current - past

    THRESHOLD = 0.10  # ignore tiny moves

    # Maps for how to describe direction in each group
    labels = {
        "growth": ("improving", "stable", "deteriorating"),
        "inflation": ("rising", "stable", "falling"),
        "liquidity": ("loosening", "stable", "tightening"),
        "risk": ("rising", "stable", "falling"),
    }

    directions: Dict[str, str] = {}
    for group in GROUPS:
        col = f"{group}_score"
        if col not in scores_df.columns:
            directions[group] = "stable"
            continue

        d = delta[col]
        up, flat, down = labels[group]

        if d > THRESHOLD:
            directions[group] = up
        elif d < -THRESHOLD:
            directions[group] = down
        else:
            directions[group] = flat

    return directions


def get_current_scores(scores_df: pd.DataFrame) -> Dict[str, float]:
    """Extract current (latest) scores as a dict."""
    latest = scores_df.iloc[-1]
    return {
        "growth": latest.get("growth_score", 0.0),
        "inflation": latest.get("inflation_score", 0.0),
        "liquidity": latest.get("liquidity_score", 0.0),
        "risk": latest.get("risk_score", 0.0),
    }


def score_to_label(score: float) -> str:
    """Convert a score to a descriptive label."""
    if score > 1.0:
        return "Strong positive"
    elif score > 0.3:
        return "Mildly positive"
    elif score > -0.3:
        return "Neutral"
    elif score > -1.0:
        return "Mildly negative"
    else:
        return "Strong negative"


# Placeholder for advanced scoring with PCA (imported in tests)
def compute_group_scores_advanced(
    df_transformed: pd.DataFrame,
    use_pca: bool = False,
    pca_weight: float = 0.3,
) -> pd.DataFrame:
    """
    Advanced scoring with optional PCA-based composite.

    For now, just returns equal-weight scores with _ew suffix.
    """
    scores = compute_group_scores(df_transformed)

    # Rename to match expected interface
    result = scores.copy()
    for col in scores.columns:
        result[f"{col}_ew"] = scores[col]
        result[f"{col.replace('_score', '_score_composite')}"] = scores[col]

    return result
