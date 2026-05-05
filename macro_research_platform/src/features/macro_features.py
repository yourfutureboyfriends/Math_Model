"""
transformations.py — Compute derived metrics from raw macro indicators.

Financial context:
  Raw macro data is not directly comparable across indicators.  PMI ranges from
  30-65; CPI ranges from 0-10%; oil price is in dollars.  To compare them we
  need to transform them into a common scale.

  We compute four transforms for each indicator:

  1. MoM change  — month-on-month difference (how did it move last month?)
  2. YoY change  — year-on-year difference (how does it compare to a year ago?)
  3. 3M MA       — 3-month moving average (smooth out noise)
  4. Z-score     — how many standard deviations from the recent mean?

  The Z-score is the most important for SCORING.  A z-score of +2 means the
  indicator is 2 standard deviations above its recent average — a strong signal.
  We compute it over a ROLLING 36-month (3-year) window so the model adapts
  to changing macro regimes rather than anchoring to all-time history.

  min_periods=12 means z-scores become available after 12 months of data, not
  only after a full 36-month window — a practical trade-off for early dates.
"""

import pandas as pd
import numpy as np
from typing import Optional

from src.data.data_loader import INDICATOR_CONFIG


ZSCORE_WINDOW = 36    # 3 years of rolling history
MA_WINDOW     = 3     # 3-month moving average
MIN_PERIODS   = 12    # minimum observations before computing rolling stats


def compute_all_transforms(df: pd.DataFrame) -> pd.DataFrame:
    """Compute MoM change, YoY change, 3M MA, and 36M rolling z-score for each indicator.

    Returns an enriched DataFrame with extra columns named:
      {indicator}_mom, {indicator}_yoy, {indicator}_ma3, {indicator}_zscore

    The original columns are preserved so you can still inspect raw values.
    """
    result = df.copy()

    for col in INDICATOR_CONFIG:
        if col not in df.columns:
            continue

        series = df[col]

        # --- MoM change ---
        # For most indicators, a simple 1-month difference is clearest.
        # (For price levels like oil, this gives the dollar change; for rates,
        # the bps change.  We don't use pct_change to avoid divide-near-zero
        # issues with indicators that can pass through zero like yield_curve.)
        result[f"{col}_mom"] = series.diff(1)

        # --- YoY change ---
        # 12-month difference captures the year-over-year trend.
        result[f"{col}_yoy"] = series.diff(12)

        # --- 3-month moving average ---
        # Smoothing removes month-to-month noise.  Important for volatile
        # indicators like VIX or oil price.
        result[f"{col}_ma3"] = series.rolling(MA_WINDOW, min_periods=1).mean()

        # --- Rolling z-score (36-month window) ---
        # This is the key transform for scoring.  It answers:
        #   "Is this indicator high or low relative to its recent history?"
        # Using a rolling window (not all-history) means the model adapts
        # as macro regimes shift — an important design choice.
        rolling = series.rolling(ZSCORE_WINDOW, min_periods=MIN_PERIODS)
        roll_mean = rolling.mean()
        roll_std  = rolling.std()

        # Avoid division by zero when std is near zero (flat series)
        result[f"{col}_zscore"] = np.where(
            roll_std > 1e-8,
            (series - roll_mean) / roll_std,
            0.0
        )

    return result


def get_latest_snapshot(df_transformed: pd.DataFrame) -> pd.Series:
    """Return the most recent row of transformed data as a Series."""
    return df_transformed.iloc[-1]


def get_zscore_columns(df_transformed: pd.DataFrame) -> list[str]:
    """Return a list of all z-score column names."""
    return [c for c in df_transformed.columns if c.endswith("_zscore")]


# =============================================================================
# Advanced Statistical Transforms (Phase 2 enhancements)
# =============================================================================

def compute_surprise_index(
    df: pd.DataFrame,
    consensus_df: pd.DataFrame,
    window: int = 3,
) -> pd.DataFrame:
    """
    Compute surprise index: actual minus consensus for each indicator.

    Financial context:
      Markets move on surprises, not just the data level. If GDP comes in at
      +2.5% but consensus was +2.0%, the surprise is +0.5%. This surprise
      drives short-term price movements more than the absolute number.

      The surprise index aggregates recent surprises across indicators to
      identify whether macro data is systematically beating or missing
      economist expectations.

    Args:
        df: DataFrame with actual indicator values
        consensus_df: DataFrame with consensus estimates (same columns as df)
        window: Rolling window for aggregating surprises (default 3 months)

    Returns:
        DataFrame with surprise columns ({indicator}_surprise) and
        aggregated surprise score (_surprise_index).
    """
    result = pd.DataFrame(index=df.index)

    # Align indices
    consensus_aligned = consensus_df.reindex(df.index)

    for col in df.columns:
        if col not in consensus_aligned.columns:
            continue

        # Compute surprise as actual - consensus
        surprise = df[col] - consensus_aligned[col]
        result[f"{col}_surprise"] = surprise

    # Aggregate across all surprises (equal weight)
    surprise_cols = [c for c in result.columns if c.endswith("_surprise")]
    if surprise_cols:
        # Z-score the surprises to put them on common scale
        surprise_z = result[surprise_cols].apply(
            lambda x: (x - x.rolling(window*12, min_periods=6).mean()) /
                     x.rolling(window*12, min_periods=6).std().replace(0, np.nan),
            axis=0
        ).fillna(0)

        # Rolling average of surprises
        result["surprise_index"] = surprise_z.mean(axis=1).rolling(window, min_periods=1).mean()

    return result


def compute_momentum_score(
    series: pd.Series,
    windows: list[int] = [1, 3, 6, 12],
    weights: Optional[list[float]] = None,
) -> pd.Series:
    """
    Compute multi-horizon momentum composite score.

    Financial context:
      Single-horizon momentum (e.g., 12-month) can be noisy and miss inflection
      points. A composite that combines short-term (1M), medium-term (3M, 6M),
      and long-term (12M) momentum provides a richer picture of trend.

      Weighting scheme: shorter windows get more weight for responsiveness,
      longer windows get weight for confirmation.

    Args:
        series: Time series of indicator values
        windows: List of month windows for momentum calculation
        weights: Optional weights for each window. If None, uses [0.4, 0.3, 0.2, 0.1]

    Returns:
        Series of composite momentum scores (z-scored)
    """
    if weights is None:
        # Default: short-term momentum gets higher weight for responsiveness
        weights = [0.4, 0.3, 0.2, 0.1][:len(windows)]

    # Normalize weights to sum to 1
    weights = np.array(weights) / sum(weights)

    momentums = []
    for w in windows:
        # Momentum = current / w-periods-ago - 1 (for % change)
        # Use diff for rate-style indicators where levels matter
        mom = series.diff(w)
        momentums.append(mom)

    # Weighted average
    composite = sum(m * w for m, w in zip(momentums, weights))

    # Z-score for interpretability
    rolling = composite.rolling(36, min_periods=12)
    zscore = (composite - rolling.mean()) / rolling.std().replace(0, np.nan)

    return zscore.fillna(0)


def compute_diffusion_index(
    df: pd.DataFrame,
    group: str,
    threshold: float = 0.0,
) -> pd.Series:
    """
    Compute diffusion index: % of indicators in a group that are above threshold.

    Financial context:
      A diffusion index answers: "what percentage of indicators are improving?"
      This is a classic business cycle tool (ISM uses 50 as neutral; we use 0
      as the z-score neutral point).

      A diffusion index > 50% means more than half the indicators in the group
      are positive — expansion. < 50% means contraction.

      The advantage over a simple average: it's less sensitive to outliers.
      One indicator with extreme z-score won't dominate the signal.

    Args:
        df: DataFrame with indicator data
        group: Group name (e.g., "growth", "inflation")
        threshold: Z-score threshold for "positive" (default 0.0)

    Returns:
        Series of diffusion percentages (0-100)
    """
    from src.data_loader import INDICATORS_BY_GROUP

    indicators = INDICATORS_BY_GROUP.get(group, [])
    if not indicators:
        return pd.Series(0, index=df.index)

    # Get z-score columns for this group
    zscore_cols = [f"{ind}_zscore" for ind in indicators if f"{ind}_zscore" in df.columns]

    if not zscore_cols:
        return pd.Series(50, index=df.index)  # Neutral if no data

    # Count how many are above threshold
    positive_count = (df[zscore_cols] > threshold).sum(axis=1)
    total = len(zscore_cols)

    # Convert to percentage
    diffusion = (positive_count / total) * 100

    return diffusion


def compute_all_advanced_transforms(
    df: pd.DataFrame,
    df_transformed: pd.DataFrame,
    consensus_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Compute all advanced transforms including momentum and diffusion indices.

    Args:
        df: Original raw data DataFrame
        df_transformed: DataFrame with basic transforms (z-scores, MoM, etc.)
        consensus_df: Optional DataFrame with consensus estimates for surprise index

    Returns:
        DataFrame with all advanced transforms added.
    """
    result = df_transformed.copy()

    # Add momentum scores for each group
    from src.data_loader import INDICATORS_BY_GROUP, GROUPS

    for group in GROUPS:
        indicators = INDICATORS_BY_GROUP.get(group, [])
        for ind in indicators:
            zscore_col = f"{ind}_zscore"
            if zscore_col in result.columns:
                mom_col = f"{ind}_momentum"
                result[mom_col] = compute_momentum_score(result[zscore_col])

        # Add diffusion index for the group
        diff_col = f"{group}_diffusion"
        result[diff_col] = compute_diffusion_index(result, group)

    # Add surprise index if consensus data provided
    if consensus_df is not None and not consensus_df.empty:
        surprise_df = compute_surprise_index(df, consensus_df)
        # Merge surprise columns
        for col in surprise_df.columns:
            result[col] = surprise_df[col]

    return result
