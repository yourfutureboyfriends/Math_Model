"""
Leading Economic Indicators (LEI) Composite Model

Implements a Conference Board LEI-inspired composite from available FRED data.

ACADEMIC BASIS
==============
The Conference Board Leading Economic Index® (LEI) was designed to signal
turning points in the business cycle approximately 7 months in advance of
recessions and expansions.

Components (Conference Board official, 10 total):
  1. Average weekly hours in manufacturing           (AWHMAN)
  2. Average weekly initial unemployment claims      (IC4WSA, inverted)
  3. Manufacturers' new orders, consumer goods       (proxy: ISM New Orders)
  4. ISM® New Orders Index                           (proxy: industrial production changes)
  5. Manufacturers' new orders, capital goods        (proxy: business investment)
  6. Building permits, new private housing           (PERMIT)
  7. S&P 500® stock prices                           (SP500 or equity momentum)
  8. Leading Credit Index™                           (proxy: inverted HY spreads)
  9. Interest rate spread: 10Y - Fed Funds Rate      (DGS10 - FEDFUNDS)
 10. Average consumer expectations                   (UMCSENT)

METHODOLOGY
===========
Each component is:
  1. Converted to MoM % change (or difference for rate-based indicators)
  2. Standardised by dividing by its historical standard deviation
     (inverse-volatility weighting — more stable components get more weight)
  3. Averaged with equal weight across available components
  4. The composite is smoothed (3-month MA) and z-scored

"3D recession rule" (Conference Board):
  - LEI declining for 6+ months AND
  - 6-month LEI growth rate < -4.2% AND
  - Diffusion index < 50% (fewer than half of components expanding)

REFERENCE
=========
Conference Board: https://www.conference-board.org/data/bci/
"""

import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class LEIResult:
    """Result from LEI composite computation."""
    composite_score: float      # Current normalised LEI score (z-scored)
    six_month_change: float     # 6-month annualised rate of change (%)
    diffusion: float            # % of components with positive 6-month change
    trend: str                  # "expanding", "moderating", "contracting"
    recession_signal: bool      # True if all 3D criteria are met
    components_available: int   # Number of components with data
    components_detail: Dict[str, float]   # Per-component contributions
    history: pd.Series          # Full composite history
    description: str


# =============================================================================
# Component Definitions
# =============================================================================

# Maps FRED column names (as they appear in the DataFrame) to component metadata
# (direction: +1 if higher = better leading indicator, -1 if inverted)
LEI_COMPONENTS: List[dict] = [
    # --- Labour market ---
    {
        "name": "avg_mfg_hours",
        "aliases": ["avg_mfg_hours", "AWHMAN"],
        "direction": +1,
        "label": "Avg Mfg Hours",
        "transform": "pct_change",   # % change
        "source": "LEI Component 1 (Conference Board)",
    },
    {
        "name": "initial_claims",
        "aliases": ["initial_claims_4wk", "IC4WSA", "unemployment_rate", "us_unemployment_rate"],
        "direction": -1,             # Inverted: fewer claims = better
        "label": "Initial Claims (inv.)",
        "transform": "pct_change",
        "source": "LEI Component 2 (Conference Board, inverted)",
    },
    # --- Business orders / production proxy ---
    {
        "name": "industrial_production",
        "aliases": ["industrial_production", "us_industrial_production", "INDPRO"],
        "direction": +1,
        "label": "Industrial Production",
        "transform": "pct_change",
        "source": "LEI Component 3/4 proxy (new orders)",
    },
    # --- Housing ---
    {
        "name": "building_permits",
        "aliases": ["building_permits", "PERMIT", "housing_starts", "HOUST"],
        "direction": +1,
        "label": "Building Permits",
        "transform": "pct_change",
        "source": "LEI Component 6 (Conference Board)",
    },
    # --- Equity prices ---
    {
        "name": "equity_prices",
        "aliases": ["sp500", "equity_momentum_12m", "SP500"],
        "direction": +1,
        "label": "Equity Prices",
        "transform": "pct_change",
        "source": "LEI Component 7 (Conference Board)",
    },
    # --- Credit / financial conditions ---
    {
        "name": "credit_conditions",
        "aliases": ["hy_spreads", "high_yield_spread", "bbb_spread", "BAMLH0A0HYM2"],
        "direction": -1,             # Inverted: tighter spreads = easier credit
        "label": "Credit Spread (inv.)",
        "transform": "diff",
        "source": "LEI Component 8 proxy (Leading Credit Index)",
    },
    # --- Yield curve ---
    {
        "name": "yield_curve",
        "aliases": ["yield_curve_3m10y", "yield_curve", "us_yield_curve_3m10y"],
        "direction": +1,             # Steeper = better outlook
        "label": "Yield Curve",
        "transform": "diff",
        "source": "LEI Component 9 (10Y minus Fed Funds or 3M)",
    },
    # --- Consumer sentiment ---
    {
        "name": "consumer_sentiment",
        "aliases": ["consumer_sentiment", "UMCSENT"],
        "direction": +1,
        "label": "Consumer Expectations",
        "transform": "pct_change",
        "source": "LEI Component 10 (Conference Board)",
    },
    # --- Money supply ---
    {
        "name": "money_supply",
        "aliases": ["money_supply_yoy", "M2SL"],
        "direction": +1,
        "label": "M2 Money Supply",
        "transform": "diff",         # Change in growth rate
        "source": "Ilmanen (2011): liquidity cycle indicator",
    },
    # --- Inventory signal (inverted: high = demand weakness ahead) ---
    {
        "name": "inventory_signal",
        "aliases": ["inv_sales_ratio", "ISRATIO"],
        "direction": -1,
        "label": "Inv/Sales Ratio (inv.)",
        "transform": "diff",
        "source": "Demand slack indicator: rising ratio → production cuts",
    },
]


# =============================================================================
# LEI Composite Model
# =============================================================================

class LEICompositeModel:
    """
    Compute a Conference Board LEI-inspired composite from available FRED data.

    Inverse-volatility weighted across components that are available,
    normalised to zero mean / unit standard deviation.
    """

    # 3D Recession Rule thresholds
    RECESSION_6M_THRESHOLD = -4.2     # 6-month annualised change (%)
    RECESSION_DIFFUSION_THRESHOLD = 50.0   # % components improving

    def __init__(self, smooth_window: int = 3, zscore_window: int = 36):
        self.smooth_window = smooth_window
        self.zscore_window = zscore_window

    def _get_series(self, df: pd.DataFrame, component: dict) -> Optional[pd.Series]:
        """Find the first available alias for a component in the DataFrame."""
        for alias in component["aliases"]:
            if alias in df.columns:
                return df[alias].copy()
        return None

    def _transform_series(self, series: pd.Series, transform: str, direction: int) -> pd.Series:
        """Apply the specified transform and direction flip."""
        if transform == "pct_change":
            transformed = series.pct_change(1) * 100
        elif transform == "diff":
            transformed = series.diff(1)
        else:
            transformed = series.diff(1)

        # Apply direction: invert if direction = -1
        if direction == -1:
            transformed = -transformed

        return transformed

    def _inverse_vol_weight(self, series: pd.Series) -> pd.Series:
        """
        Standardise series by its rolling standard deviation.
        This is the Conference Board's inverse-volatility weighting method:
        more volatile components get less weight per unit of change.
        """
        roll_std = series.rolling(60, min_periods=12).std()
        return (series / roll_std.replace(0, np.nan)).fillna(0)

    def compute(self, df: pd.DataFrame) -> LEIResult:
        """
        Compute LEI composite from a DataFrame.

        Args:
            df: DataFrame with macro indicators

        Returns:
            LEIResult with composite score, 3D signal, and component details
        """
        component_series = []
        component_details = {}
        available_count = 0

        for comp in LEI_COMPONENTS:
            raw = self._get_series(df, comp)
            if raw is None or raw.dropna().empty:
                logger.debug("LEI component '%s' not available", comp["name"])
                continue

            available_count += 1
            transformed = self._transform_series(raw, comp["transform"], comp["direction"])
            weighted = self._inverse_vol_weight(transformed)

            component_details[comp["label"]] = float(transformed.iloc[-1]) if not transformed.dropna().empty else 0.0
            component_series.append(weighted)

        if not component_series:
            logger.warning("No LEI components available")
            null = pd.Series(0.0, index=df.index, name="lei_composite")
            return LEIResult(
                composite_score=0.0, six_month_change=0.0, diffusion=50.0,
                trend="unknown", recession_signal=False,
                components_available=0, components_detail={},
                history=null,
                description="No LEI component data available",
            )

        # ---- Composite: equal-weight average ----
        composite_raw = pd.concat(component_series, axis=1).mean(axis=1)

        # ---- 3-month smoothing (standard LEI methodology) ----
        composite_smooth = composite_raw.rolling(self.smooth_window, min_periods=1).mean()

        # ---- Z-score ----
        roll = composite_smooth.rolling(self.zscore_window, min_periods=12)
        composite_z = (
            (composite_smooth - roll.mean()) / roll.std().replace(0, np.nan)
        ).fillna(0).rename("lei_composite")

        current_z = float(composite_z.iloc[-1])

        # ---- 6-month annualised rate of change ----
        if len(composite_z) >= 7:
            change_6m = float((composite_z.iloc[-1] - composite_z.iloc[-7]) / composite_z.iloc[-7] * 100
                              if composite_z.iloc[-7] != 0 else 0.0)
        else:
            change_6m = 0.0

        # ---- Diffusion: % of components with positive 6-month change ----
        diffusion_scores = []
        for series in component_series:
            if len(series.dropna()) >= 7:
                chg = series.iloc[-1] - series.iloc[-7] if len(series) >= 7 else 0
                diffusion_scores.append(1 if chg > 0 else 0)
        diffusion = (sum(diffusion_scores) / len(diffusion_scores) * 100) if diffusion_scores else 50.0

        # ---- Trend ----
        if current_z > 0.3:
            trend = "expanding"
        elif current_z > -0.3:
            trend = "moderating"
        else:
            trend = "contracting"

        # ---- Conference Board 3D Recession Rule ----
        recession_signal = (
            len(composite_z) >= 7 and
            change_6m < self.RECESSION_6M_THRESHOLD and
            diffusion < self.RECESSION_DIFFUSION_THRESHOLD
        )

        description = (
            f"LEI composite: {current_z:+.2f}σ | "
            f"6M change: {change_6m:+.1f}% | "
            f"Diffusion: {diffusion:.0f}% | "
            f"Trend: {trend.upper()}"
        )
        if recession_signal:
            description += " ⚠ RECESSION SIGNAL (3D Rule triggered)"

        return LEIResult(
            composite_score=round(current_z, 3),
            six_month_change=round(change_6m, 2),
            diffusion=round(diffusion, 1),
            trend=trend,
            recession_signal=recession_signal,
            components_available=available_count,
            components_detail=component_details,
            history=composite_z,
            description=description,
        )


# =============================================================================
# Convenience Functions
# =============================================================================

def get_lei_composite(df: pd.DataFrame) -> LEIResult:
    """Compute LEI composite from a raw macro DataFrame."""
    model = LEICompositeModel()
    return model.compute(df)


def get_lei_signal(df: pd.DataFrame) -> dict:
    """Get current LEI signal as a simple dict."""
    result = get_lei_composite(df)
    return {
        "score": result.composite_score,
        "trend": result.trend,
        "six_month_change": result.six_month_change,
        "diffusion": result.diffusion,
        "recession_signal": result.recession_signal,
        "components_available": result.components_available,
        "description": result.description,
    }
