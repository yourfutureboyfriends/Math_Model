"""
portfolio_constructor.py — Construct model portfolio from sector signals.

Financial context:
  Sector signals (OW/N/UW) need to be translated into actual portfolio weights.
  This module implements a systematic approach to constructing weights while
  respecting constraints and maintaining interpretability.

Portfolio construction process:
  1. Start with equal-weight benchmark (1/7 ≈ 14.3% per sector)
  2. Apply tilts based on signals: OW +5%, UW -5%
  3. Apply constraints: max 25%, min 5%
  4. Rescale to sum to 100%
  5. Compute deviations from benchmark and rationale

Why equal-weight benchmark?
  - Simple, transparent, widely used
  - Avoids concentration risk of market-cap weighting
  - Easy to understand deviations

Why fixed tilts?
  - Avoids overfitting to historical optimal weights
  - Clear connection between signal and weight
  - Easy to adjust based on conviction level

Constraints rationale:
  - Max 25%: prevents concentration, manages single-sector risk
  - Min 5%: maintains diversification, avoids zero-weight sectors
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import logging

from settings import MAX_SECTOR_WEIGHT, MIN_SECTOR_WEIGHT, TILT_MAGNITUDE
from src.sector_model import SECTOR_CONFIG

logger = logging.getLogger(__name__)


class PortfolioConstructor:
    """
    Construct model portfolio from sector signals with constraints.
    """

    def __init__(
        self,
        base_weight: float = 1.0 / 7,  # Equal weight across 7 sectors
        tilt_magnitude: float = TILT_MAGNITUDE,
        max_weight: float = MAX_SECTOR_WEIGHT,
        min_weight: float = MIN_SECTOR_WEIGHT,
    ):
        """
        Initialize portfolio constructor.

        Args:
            base_weight: Starting weight for each sector (equal weight)
            tilt_magnitude: Magnitude of OW/UW tilt in percentage points
            max_weight: Maximum allowed sector weight
            min_weight: Minimum allowed sector weight
        """
        self.base_weight = base_weight
        self.tilt_magnitude = tilt_magnitude
        self.max_weight = max_weight
        self.min_weight = min_weight

    def construct(
        self,
        sector_signals: Dict[str, str],
        sector_scores: Optional[Dict[str, float]] = None,
    ) -> pd.DataFrame:
        """
        Construct model portfolio from sector signals.

        Args:
            sector_signals: Dict mapping sector name to signal (Overweight/Neutral/Underweight)
            sector_scores: Optional dict of sector scores for additional weighting

        Returns:
            DataFrame with portfolio construction details
        """
        rows = []

        # Step 1: Start with equal weights
        weights = {sector: self.base_weight for sector in sector_signals}

        # Step 2: Apply tilts based on signals
        for sector, signal in sector_signals.items():
            if signal == "Overweight":
                weights[sector] += self.tilt_magnitude
            elif signal == "Underweight":
                weights[sector] -= self.tilt_magnitude

        # Step 3: Apply constraints
        # First pass: cap max weights
        for sector in weights:
            weights[sector] = min(weights[sector], self.max_weight)

        # Second pass: floor min weights
        for sector in weights:
            weights[sector] = max(weights[sector], self.min_weight)

        # Step 4: Rescale to sum to 100%
        total_weight = sum(weights.values())
        if abs(total_weight - 1.0) > 0.001:
            scale_factor = 1.0 / total_weight
            weights = {k: v * scale_factor for k, v in weights.items()}

        # Step 5: Build output DataFrame
        for sector in sector_signals:
            signal = sector_signals[sector]
            score = sector_scores.get(sector, 0.0) if sector_scores else 0.0

            # Generate rationale
            rationale = self._generate_rationale(sector, signal, score)

            rows.append({
                "Sector": sector,
                "Signal": signal,
                "Score": score,
                "Model Weight": weights[sector],
                "Benchmark Weight": self.base_weight,
                "Deviation": weights[sector] - self.base_weight,
                "Active Weight %": (weights[sector] - self.base_weight) * 100,
                "Rationale": rationale,
            })

        df = pd.DataFrame(rows)

        # Sort by model weight descending
        df = df.sort_values("Model Weight", ascending=False).reset_index(drop=True)

        return df

    def _generate_rationale(self, sector: str, signal: str, score: float) -> str:
        """Generate human-readable rationale for the weight."""
        if sector not in SECTOR_CONFIG:
            return f"{signal} based on macro model"

        desc = SECTOR_CONFIG[sector]["description"].split(".")[0]

        if signal == "Overweight":
            return f"Overweight: {desc}. Strong macro tailwinds (score: {score:+.2f})"
        elif signal == "Underweight":
            return f"Underweight: {desc}. Macro headwinds (score: {score:+.2f})"
        else:
            return f"Neutral: {desc}. No strong macro signal (score: {score:+.2f})"

    def get_summary(self, portfolio_df: pd.DataFrame) -> Dict:
        """
        Generate portfolio summary statistics.

        Args:
            portfolio_df: Output from construct()

        Returns:
            Dict with summary statistics
        """
        if portfolio_df.empty:
            return {}

        active_weights = portfolio_df["Active Weight %"].abs()

        return {
            "n_sectors": len(portfolio_df),
            "max_position": portfolio_df["Model Weight"].max(),
            "min_position": portfolio_df["Model Weight"].min(),
            "largest_ow": portfolio_df[portfolio_df["Deviation"] > 0]["Deviation"].max() if (portfolio_df["Deviation"] > 0).any() else 0,
            "largest_uw": portfolio_df[portfolio_df["Deviation"] < 0]["Deviation"].min() if (portfolio_df["Deviation"] < 0).any() else 0,
            "total_active_risk": active_weights.sum(),
            "avg_active_weight": portfolio_df["Active Weight %"].mean(),
        }


def construct_model_portfolio(
    sector_signals: Dict[str, str],
    sector_scores: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """
    Convenience function to construct model portfolio.

    Args:
        sector_signals: Dict mapping sector to signal
        sector_scores: Optional dict of scores

    Returns:
        Portfolio construction DataFrame
    """
    constructor = PortfolioConstructor()
    return constructor.construct(sector_signals, sector_scores)


def get_portfolio_weights_chart(portfolio_df: pd.DataFrame) -> Dict:
    """
    Generate data for portfolio weights visualization.

    Args:
        portfolio_df: Portfolio DataFrame from construct()

    Returns:
        Dict with chart data
    """
    if portfolio_df.empty:
        return {}

    return {
        "sectors": portfolio_df["Sector"].tolist(),
        "model_weights": (portfolio_df["Model Weight"] * 100).tolist(),
        "benchmark_weights": (portfolio_df["Benchmark Weight"] * 100).tolist(),
        "deviations": portfolio_df["Active Weight %"].tolist(),
    }
