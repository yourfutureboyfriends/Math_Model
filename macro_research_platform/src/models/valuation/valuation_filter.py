"""
Valuation Filter Module

Multi-asset class valuation assessment using:
- Equities: Shiller CAPE (Cyclically Adjusted PE)
- Bonds: 10Y TIPS Real Yield
- Credit: IG and HY Option-Adjusted Spreads

Output is a position size scalar [0.5, 1.5] where:
- <1 = reduce position sizes (expensive valuations)
- >1 = increase position sizes (cheap valuations)
- 1 = neutral (fair value)

Research basis:
- CAPE: Shiller (2005), "Irrational Exuberance"
- Real yields: Campbell et al. (2014), "The Real Term Structure..."
- Credit spreads: Gilchrist & Zakrajšek (2012), "Credit Spreads and Business Cycle Fluctuations"
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional
from datetime import datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ValuationResult:
    """Result from valuation filter computation."""
    overall_valuation: str        # "CHEAP", "FAIR", "STRETCHED"
    position_size_scalar: float   # [0.5, 1.5]
    components: Dict[str, dict]   # Per-asset details
    description: str


class ValuationFilterModel:
    """
    Compute valuation-based position size adjustment.
    """

    def __init__(self):
        pass

    def _get_equity_valuation(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        Get equity valuation from CAPE.
        Rich > 75th percentile, Cheap < 25th percentile.
        """
        cape_col = None
        for col in df.columns:
            if 'cape' in col.lower() or 'shiller' in col.lower():
                cape_col = col
                break

        if cape_col is None:
            return None

        cape_series = df[cape_col].dropna()
        if len(cape_series) < 60:  # Need at least 5 years
            return None

        current_cape = float(cape_series.iloc[-1])

        # Historical percentiles (approximate based on historical CAPE range 10-35)
        percentile = (current_cape - 10) / (35 - 10) * 100
        percentile = max(0, min(100, percentile))

        if percentile > 75:
            signal = "EXPENSIVE"
            scalar = 0.7
        elif percentile < 25:
            signal = "CHEAP"
            scalar = 1.3
        else:
            signal = "FAIR"
            scalar = 1.0

        return {
            "value": round(current_cape, 1),
            "percentile": int(percentile),
            "signal": signal,
            "scalar": scalar,
        }

    def _get_bond_valuation(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        Get bond valuation from TIPS real yield.
        Higher real yield = cheaper bonds.
        """
        real_yield_col = None
        for col in df.columns:
            if 'tips' in col.lower() or 'real_yield' in col.lower() or 'dfii' in col.lower():
                real_yield_col = col
                break

        if real_yield_col is None:
            return None

        yields = df[real_yield_col].dropna()
        if len(yields) < 60:
            return None

        current_yield = float(yields.iloc[-1])

        # Historical percentiles (real yields typically -1% to +3%)
        percentile = (current_yield - (-1)) / (3 - (-1)) * 100
        percentile = max(0, min(100, percentile))

        if percentile > 75:
            signal = "ATTRACTIVE"  # High real yield = cheap bonds
            scalar = 1.2
        elif percentile < 25:
            signal = "UNATTRACTIVE"
            scalar = 0.8
        else:
            signal = "FAIR"
            scalar = 1.0

        return {
            "value": round(current_yield, 2),
            "percentile": int(percentile),
            "signal": signal,
            "scalar": scalar,
        }

    def _get_credit_valuation(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        Get credit valuation from IG and HY spreads.
        Wider spreads = cheaper credit.
        """
        # Look for credit spread columns
        ig_col = None
        hy_col = None

        for col in df.columns:
            col_lower = col.lower()
            if 'ig' in col_lower or 'bamlc0' in col_lower or 'bamlc' in col_lower:
                ig_col = col
            elif 'hy' in col_lower or 'bamlh0' in col_lower or 'high_yield' in col_lower:
                hy_col = col

        if hy_col is None and ig_col is None:
            return None

        # Calculate average z-score of spreads
        zscores = []

        for col in [ig_col, hy_col]:
            if col is not None:
                spreads = df[col].dropna()
                if len(spreads) >= 60:
                    # Current spread
                    current = float(spreads.iloc[-1])
                    # Historical
                    hist_mean = spreads.mean()
                    hist_std = spreads.std()
                    if hist_std > 0:
                        zscore = (current - hist_mean) / hist_std
                        zscores.append(zscore)

        if not zscores:
            return None

        avg_zscore = np.mean(zscores)

        # Invert: negative zscore (tight spreads) = expensive
        # Positive zscore (wide spreads) = cheap
        if avg_zscore < -0.5:
            signal = "TIGHT"  # Expensive
            scalar = 0.85
        elif avg_zscore > 0.5:
            signal = "WIDE"  # Cheap
            scalar = 1.15
        else:
            signal = "FAIR"
            scalar = 1.0

        return {
            "value": round(avg_zscore, 2),
            "percentile": int(50 - avg_zscore * 25),  # Approximate
            "signal": signal,
            "scalar": scalar,
        }

    def compute(self, df: pd.DataFrame) -> ValuationResult:
        """
        Compute valuation filter.

        Args:
            df: DataFrame with market data

        Returns:
            ValuationResult with position size scalar
        """
        components = {}
        scalars = []

        # Equities
        equity_val = self._get_equity_valuation(df)
        if equity_val:
            components["equities_cape"] = equity_val
            scalars.append(equity_val["scalar"])

        # Bonds
        bond_val = self._get_bond_valuation(df)
        if bond_val:
            components["bonds_real_yield"] = bond_val
            scalars.append(bond_val["scalar"])

        # Credit
        credit_val = self._get_credit_valuation(df)
        if credit_val:
            components["credit_spreads"] = credit_val
            scalars.append(credit_val["scalar"])

        if len(scalars) == 0:
            logger.warning("No valuation components available")
            return ValuationResult(
                overall_valuation="FAIR",
                position_size_scalar=1.0,
                components={},
                description="Insufficient data for valuation filter",
            )

        # Average scalar
        avg_scalar = np.mean(scalars)
        avg_scalar = np.clip(avg_scalar, 0.5, 1.5)

        # Overall classification
        if avg_scalar < 0.85:
            overall = "STRETCHED"
        elif avg_scalar > 1.15:
            overall = "CHEAP"
        else:
            overall = "FAIR"

        description = (
            f"Valuation: {overall} (scalar: {avg_scalar:.2f}x) | "
            f"Components: {len(components)}"
        )

        return ValuationResult(
            overall_valuation=overall,
            position_size_scalar=round(avg_scalar, 2),
            components=components,
            description=description,
        )


def get_valuation_filter(df: pd.DataFrame) -> ValuationResult:
    """Compute valuation filter from DataFrame."""
    model = ValuationFilterModel()
    return model.compute(df)


def get_valuation_dict(df: pd.DataFrame) -> dict:
    """Get valuation as simple dict for API response."""
    result = get_valuation_filter(df)
    return {
        "overall_valuation": result.overall_valuation,
        "position_size_scalar": result.position_size_scalar,
        "components": result.components,
        "description": result.description,
    }
