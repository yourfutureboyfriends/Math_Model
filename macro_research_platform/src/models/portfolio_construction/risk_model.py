"""
risk_monitor.py — Monitor portfolio and macro risk conditions.

Financial context:
  Risk management requires more than just position sizing. This module tracks
  higher-order risks that affect the model itself:

  1. Regime uncertainty: frequent regime changes suggest model instability
  2. Rapid macro shifts: large score reversals warn of inflection points
  3. Model confidence: disagreement between scoring methods

Risk flags:
  - "High regime uncertainty": >2 regime changes in 6 months
  - "Rapid macro shift": score reverses by >1 z-score in 1 month
  - "Model divergence": PCA score disagrees with equal-weight by >0.5

These are early warning signals, not trading decisions. They prompt review
of model assumptions rather than automatic action.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging

from settings import REGIME_CHANGE_THRESHOLD, RAPID_SHIFT_THRESHOLD

logger = logging.getLogger(__name__)


class RiskMonitor:
    """
    Monitor macro and portfolio risk conditions.
    """

    def __init__(
        self,
        regime_change_threshold: int = REGIME_CHANGE_THRESHOLD,
        rapid_shift_threshold: float = RAPID_SHIFT_THRESHOLD,
    ):
        """
        Initialize risk monitor.

        Args:
            regime_change_threshold: Number of regime changes to flag uncertainty
            rapid_shift_threshold: Z-score change threshold for rapid shift
        """
        self.regime_change_threshold = regime_change_threshold
        self.rapid_shift_threshold = rapid_shift_threshold

    def analyze_regime_stability(
        self,
        regime_history: pd.Series,
        window_months: int = 6,
    ) -> Dict:
        """
        Analyze regime change frequency.

        Args:
            regime_history: Series of regime classifications indexed by date
            window_months: Lookback window in months

        Returns:
            Dict with regime stability metrics
        """
        if len(regime_history) < window_months:
            return {
                "regime_changes": 0,
                "is_stable": True,
                "risk_flag": False,
                "message": "Insufficient history",
            }

        # Get recent window
        cutoff_date = regime_history.index[-1] - pd.DateOffset(months=window_months)
        recent = regime_history[regime_history.index >= cutoff_date]

        # Count changes
        changes = 0
        for i in range(1, len(recent)):
            if recent.iloc[i] != recent.iloc[i-1]:
                changes += 1

        is_stable = changes <= self.regime_change_threshold

        return {
            "regime_changes": changes,
            "is_stable": is_stable,
            "risk_flag": not is_stable,
            "message": (
                f"{changes} regime changes in {window_months} months. " +
                ("Stable" if is_stable else "HIGH UNCERTAINTY - review model assumptions")
            ),
        }

    def analyze_score_momentum(
        self,
        scores_df: pd.DataFrame,
        window: int = 1,
    ) -> List[Dict]:
        """
        Detect rapid shifts in group scores.

        Args:
            scores_df: DataFrame with group scores
            window: Month window for change calculation

        Returns:
            List of risk flags for rapidly shifting scores
        """
        flags = []

        if len(scores_df) < window + 1:
            return flags

        for group_col in scores_df.columns:
            if not group_col.endswith("_score"):
                continue

            group_name = group_col.replace("_score", "").capitalize()

            current = scores_df[group_col].iloc[-1]
            previous = scores_df[group_col].iloc[-(window + 1)]

            change = current - previous
            abs_change = abs(change)

            if abs_change >= self.rapid_shift_threshold:
                direction = "surged" if change > 0 else "plunged"
                flags.append({
                    "type": "rapid_shift",
                    "group": group_name,
                    "severity": "high" if abs_change > 2 else "medium",
                    "message": (
                        f"{group_name} score {direction} by {abs_change:.2f} z-scores "
                        f"in {window} month{'s' if window > 1 else ''}"
                    ),
                    "current_score": current,
                    "previous_score": previous,
                    "change": change,
                })

        return flags

    def analyze_model_divergence(
        self,
        scores_ew: pd.DataFrame,
        scores_pca: pd.DataFrame,
        threshold: float = 0.5,
    ) -> List[Dict]:
        """
        Detect disagreement between scoring methods.

        Args:
            scores_ew: Equal-weighted scores
            scores_pca: PCA-based scores
            threshold: Difference threshold to flag

        Returns:
            List of divergence warnings
        """
        flags = []

        if scores_ew.empty or scores_pca.empty:
            return flags

        for group in ["growth", "inflation", "liquidity", "risk"]:
            ew_col = f"{group}_score"
            pca_col = f"{group}_score_pca"

            if ew_col not in scores_ew.columns or pca_col not in scores_pca.columns:
                continue

            ew_score = scores_ew[ew_col].iloc[-1]
            pca_score = scores_pca[pca_col].iloc[-1]

            diff = abs(ew_score - pca_score)

            if diff >= threshold:
                flags.append({
                    "type": "model_divergence",
                    "group": group.capitalize(),
                    "severity": "medium" if diff < 1.0 else "high",
                    "message": (
                        f"{group.capitalize()} score: equal-weight={ew_score:+.2f}, "
                        f"PCA={pca_score:+.2f} (diff={diff:.2f})"
                    ),
                    "ew_score": ew_score,
                    "pca_score": pca_score,
                    "difference": diff,
                })

        return flags

    def get_all_risk_flags(
        self,
        scores_df: pd.DataFrame,
        regime_history: pd.Series,
        scores_pca: Optional[pd.DataFrame] = None,
    ) -> List[Dict]:
        """
        Get all active risk flags.

        Args:
            scores_df: Group scores DataFrame
            regime_history: Regime classification series
            scores_pca: Optional PCA scores for divergence check

        Returns:
            List of all risk flags
        """
        flags = []

        # Regime stability
        regime_analysis = self.analyze_regime_stability(regime_history)
        if regime_analysis["risk_flag"]:
            flags.append({
                "type": "regime_uncertainty",
                "severity": "high",
                "message": regime_analysis["message"],
            })

        # Score momentum
        score_flags = self.analyze_score_momentum(scores_df)
        flags.extend(score_flags)

        # Model divergence
        if scores_pca is not None:
            divergence_flags = self.analyze_model_divergence(scores_df, scores_pca)
            flags.extend(divergence_flags)

        return flags


def get_current_risk_flags(
    scores_df: pd.DataFrame,
    regime_history: pd.Series,
    scores_pca: Optional[pd.DataFrame] = None,
) -> List[Dict]:
    """
    Convenience function to get current risk flags.

    Args:
        scores_df: Group scores
        regime_history: Regime series
        scores_pca: Optional PCA scores

    Returns:
        List of active risk flags
    """
    monitor = RiskMonitor()
    return monitor.get_all_risk_flags(scores_df, regime_history, scores_pca)


def format_risk_flags(flags: List[Dict]) -> str:
    """
    Format risk flags for display.

    Args:
        flags: List of risk flag dicts

    Returns:
        Formatted string
    """
    if not flags:
        return "✅ No active risk flags"

    lines = ["⚠️ **Risk Flags Active**", ""]

    for flag in flags:
        emoji = "🔴" if flag.get("severity") == "high" else "🟡"
        lines.append(f"{emoji} {flag['message']}")

    return "\n".join(lines)
