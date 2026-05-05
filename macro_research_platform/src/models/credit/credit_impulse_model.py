"""
Credit Impulse Model

Implements the credit impulse framework from Biggs, Mayer & Pick (2010),
"Credit and Economic Recovery: Demystifying Phoenix Miracles"

ACADEMIC BASIS
==============
Biggs, Mayer & Pick (2010) showed that what drives demand is NOT the stock
of credit (how much debt exists) but the FLOW of new credit and, critically,
the ACCELERATION of that flow (the second derivative of credit).

    Credit Impulse = Δ(New Credit Flow) / GDP
                   ≈ [Credit(t) - 2·Credit(t-1) + Credit(t-2)] / GDP(t)

This explains "Phoenix Miracles": economies where total debt is still
contracting but demand is recovering. The demand impulse came from the
ACCELERATION of new credit, even while the total stock was still falling.

PRACTICAL IMPORTANCE
====================
- Leads GDP growth by 2-4 quarters (strong leading indicator)
- Bridgewater and major macro hedge funds watch credit impulse closely
- A key part of Dalio's "Economic Machine" framework
- China's credit impulse is particularly powerful given leverage in the system

IMPLEMENTATION
==============
We approximate the impulse using available FRED series:
  - Commercial & industrial loans (BUSLOANS) — corporate credit
  - Consumer credit (TOTALSL) — household credit
  - M2 money supply — broad credit proxy when loan data unavailable

The impulse is computed as the 12-month rate of change of the YoY growth
rate (i.e., the second derivative of credit normalised to GDP proxy).
"""

import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class CreditImpulseResult:
    """Result from credit impulse computation."""
    impulse: float          # Current credit impulse (normalised, z-scored)
    direction: str          # "accelerating", "stable", "decelerating"
    signal: str             # "POSITIVE", "NEUTRAL", "NEGATIVE"
    description: str        # Human-readable interpretation
    components: dict        # Component breakdown
    history: pd.Series      # Full impulse time series


# =============================================================================
# Credit Impulse Model
# =============================================================================

class CreditImpulseModel:
    """
    Compute the credit impulse from available macro data.

    The impulse measures the acceleration of new credit creation, which
    Biggs, Mayer & Pick (2010) showed leads aggregate demand by 2-4 quarters.

    Works with whatever credit-related columns are available:
      Priority 1: BUSLOANS + TOTALSL (commercial + consumer credit)
      Priority 2: M2SL (broad money as credit proxy)
      Priority 3: HY spread inversely as credit availability signal
    """

    SIGNAL_THRESHOLDS = {
        "POSITIVE": 0.25,    # z-score above this = positive impulse
        "NEGATIVE": -0.25,   # z-score below this = negative impulse
    }

    def __init__(self, zscore_window: int = 36):
        self.zscore_window = zscore_window

    def _compute_series_impulse(self, series: pd.Series, name: str = "") -> pd.Series:
        """
        Compute credit impulse for a single credit series.

        Method: 12-month change in the 12-month growth rate.
        This is the second derivative (acceleration) of the credit stock.

        Rationale: what matters for demand is whether new credit is
        accelerating or decelerating, not whether debt levels are rising.
        """
        if series.dropna().empty:
            return pd.Series(dtype=float, name=f"{name}_impulse")

        # Step 1: 12-month YoY growth rate (first derivative, level)
        yoy_growth = series.pct_change(12) * 100   # in %

        # Step 2: 12-month change in growth rate (second derivative = impulse)
        impulse_raw = yoy_growth.diff(12)

        logger.debug("Credit impulse for %s: latest=%.2f", name, impulse_raw.iloc[-1] if not impulse_raw.empty else float('nan'))

        return impulse_raw.rename(f"{name}_impulse")

    def compute(self, df: pd.DataFrame) -> CreditImpulseResult:
        """
        Compute composite credit impulse from available data.

        Args:
            df: DataFrame with macro indicator columns

        Returns:
            CreditImpulseResult with current impulse reading and history
        """
        components = {}
        impulse_series_list = []

        # ---- Component 1: Commercial & industrial loans (primary) ----
        for col_name in ["commercial_loans", "BUSLOANS", "us_commercial_loans"]:
            if col_name in df.columns:
                imp = self._compute_series_impulse(df[col_name], "commercial_loans")
                if not imp.dropna().empty:
                    components["commercial_loans"] = float(imp.iloc[-1]) if not imp.dropna().empty else 0.0
                    impulse_series_list.append(imp)
                break

        # ---- Component 2: Consumer credit (secondary) ----
        for col_name in ["consumer_credit", "TOTALSL", "us_consumer_credit"]:
            if col_name in df.columns:
                imp = self._compute_series_impulse(df[col_name], "consumer_credit")
                if not imp.dropna().empty:
                    components["consumer_credit"] = float(imp.iloc[-1]) if not imp.dropna().empty else 0.0
                    impulse_series_list.append(imp)
                break

        # ---- Component 3: M2 money supply (broad proxy fallback) ----
        for col_name in ["money_supply_yoy", "M2SL", "us_m2", "m2_growth"]:
            if col_name in df.columns:
                # M2 is already in YoY terms; compute impulse as rate of change of growth
                series = df[col_name]
                imp = series.diff(6).rename("m2_impulse")  # 6-month change in M2 growth
                if not imp.dropna().empty:
                    components["m2_impulse"] = float(imp.iloc[-1]) if not imp.dropna().empty else 0.0
                    impulse_series_list.append(imp)
                break

        # ---- Fallback: HY spread as inverse credit availability ----
        if not impulse_series_list:
            for col_name in ["hy_spreads", "high_yield_spread", "baa_credit_spread"]:
                if col_name in df.columns:
                    # Invert: tightening spreads = credit becoming more available
                    imp = (-df[col_name]).diff(3).rename("credit_avail_impulse")
                    if not imp.dropna().empty:
                        components["credit_availability"] = float(imp.iloc[-1]) if not imp.dropna().empty else 0.0
                        impulse_series_list.append(imp)
                    break

        if not impulse_series_list:
            logger.warning("No credit series available for impulse computation")
            null_series = pd.Series(0.0, index=df.index, name="credit_impulse")
            return CreditImpulseResult(
                impulse=0.0, direction="stable", signal="NEUTRAL",
                description="No credit data available",
                components={}, history=null_series,
            )

        # ---- Composite: equal-weight average of available components ----
        composite_df = pd.concat(impulse_series_list, axis=1)
        composite = composite_df.mean(axis=1)

        # ---- Z-score normalise ----
        rolling = composite.rolling(self.zscore_window, min_periods=12)
        composite_z = (composite - rolling.mean()) / rolling.std().replace(0, np.nan)
        composite_z = composite_z.fillna(0).rename("credit_impulse")

        current_z = float(composite_z.iloc[-1])
        current_raw = float(composite.iloc[-1])

        # ---- Direction: 3-month trend in impulse ----
        if len(composite_z) >= 4:
            delta = composite_z.iloc[-1] - composite_z.iloc[-4]
            if delta > 0.15:
                direction = "accelerating"
            elif delta < -0.15:
                direction = "decelerating"
            else:
                direction = "stable"
        else:
            direction = "stable"

        # ---- Signal ----
        if current_z >= self.SIGNAL_THRESHOLDS["POSITIVE"]:
            signal = "POSITIVE"
            description = (
                f"Credit impulse positive ({current_z:+.2f}σ) — credit acceleration "
                f"supports demand growth 2-4Q ahead (Biggs-Mayer-Pick 2010)"
            )
        elif current_z <= self.SIGNAL_THRESHOLDS["NEGATIVE"]:
            signal = "NEGATIVE"
            description = (
                f"Credit impulse negative ({current_z:+.2f}σ) — credit deceleration "
                f"signals demand headwind 2-4Q ahead"
            )
        else:
            signal = "NEUTRAL"
            description = (
                f"Credit impulse neutral ({current_z:+.2f}σ) — credit conditions "
                f"neither supporting nor constraining demand"
            )

        return CreditImpulseResult(
            impulse=round(current_z, 3),
            direction=direction,
            signal=signal,
            description=description,
            components=components,
            history=composite_z,
        )


# =============================================================================
# Convenience Functions
# =============================================================================

def get_credit_impulse(df: pd.DataFrame) -> CreditImpulseResult:
    """Compute credit impulse from a raw data DataFrame."""
    model = CreditImpulseModel()
    return model.compute(df)


def get_credit_impulse_signal(df: pd.DataFrame) -> dict:
    """Get current credit impulse as a simple signal dict."""
    result = get_credit_impulse(df)
    return {
        "value": result.impulse,
        "signal": result.signal,
        "direction": result.direction,
        "description": result.description,
        "components": result.components,
    }
