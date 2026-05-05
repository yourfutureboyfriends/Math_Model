"""
Liquidity Conditions Index

Composite index measuring overall liquidity conditions in the financial system.

Components:
- M2 Money Supply YoY% change
- TED Spread (3-month LIBOR - T-bills, proxy for credit risk)
- SOFR - Fed Funds spread (bank funding stress)
- Fed Balance Sheet 13-week change% (quantitative easing/tightening)

Methodology:
- Normalise each component to z-score (rolling 5-year window)
- Inverse-volatility weighting (stable components get more weight)
- Positive score = easing liquidity, negative = tightening

Research basis:
- Ilmanen (2011): "Expected Returns" - liquidity as risk factor
- Tobias Adrian et al. (2019): "Vulnerable Growth" - credit conditions
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional
from datetime import datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class LiquidityResult:
    """Result from liquidity index computation."""
    liquidity_index: float      # Composite score
    signal: str                   # "EASING", "NEUTRAL", "TIGHTENING"
    components: Dict[str, float]  # Individual z-scores
    percentile_rank: int          # Historical percentile
    description: str


class LiquidityIndexModel:
    """
    Compute liquidity conditions index from financial system data.
    """

    # Component definitions with column aliases
    COMPONENTS = {
        "m2_growth": {
            "aliases": ["M2SL", "m2_yoy", "money_supply_yoy", "us_m2_yoy"],
            "direction": 1,  # Higher = more liquidity
            "description": "M2 Money Supply YoY%",
        },
        "ted_spread": {
            "aliases": ["TEDRATE", "ted_spread", "libor_ois_spread"],
            "direction": -1,  # Lower = more liquidity
            "description": "TED Spread",
        },
        "sofr_spread": {
            "aliases": ["SOFR", "sofr_rate", "sofr_fed_spread"],
            "direction": -1,  # Lower SOFR vs Fed Funds = more liquidity
            "description": "SOFR - Fed Funds Spread",
        },
        "fed_balance_sheet": {
            "aliases": ["WALCL", "fed_balance_sheet", "fed_assets"],
            "direction": 1,  # Growing = QE = more liquidity
            "description": "Fed Balance Sheet 13W Change%",
        },
    }

    def __init__(self, zscore_window: int = 60):  # 5 years monthly
        self.zscore_window = zscore_window

    def _get_series(self, df: pd.DataFrame, component: str) -> Optional[pd.Series]:
        """Find series in DataFrame by component name."""
        config = self.COMPONENTS[component]
        aliases = config["aliases"]

        for alias in aliases:
            if alias in df.columns:
                return df[alias].copy()
            # Try variations
            variations = [
                alias.lower(),
                alias.upper(),
                f"us_{alias.lower()}",
            ]
            for var in variations:
                if var in df.columns:
                    return df[var].copy()
        return None

    def _transform_component(self, series: pd.Series, component: str) -> pd.Series:
        """Transform series to appropriate metric."""
        if component == "m2_growth":
            # YoY% change
            return series.pct_change(12) * 100
        elif component == "fed_balance_sheet":
            # 13-week change%
            return series.pct_change(3) * 100 * 4  # Annualise roughly
        elif component == "sofr_spread":
            # SOFR - Fed Funds (need both)
            # For now, return as-is if already calculated
            return series
        else:
            return series

    def _compute_zscore(self, series: pd.Series) -> pd.Series:
        """Compute rolling z-score."""
        roll = series.rolling(self.zscore_window, min_periods=24)
        zscore = (series - roll.mean()) / roll.std().replace(0, np.nan)
        return zscore

    def _inverse_vol_weight(self, series: pd.Series) -> float:
        """Compute inverse volatility weight."""
        vol = series.rolling(self.zscore_window, min_periods=24).std()
        return 1.0 / max(vol.iloc[-1], 0.01) if not vol.empty else 1.0

    def compute(self, df: pd.DataFrame) -> LiquidityResult:
        """
        Compute liquidity conditions index.

        Args:
            df: DataFrame with macro indicators

        Returns:
            LiquidityResult with composite score
        """
        component_zscores = {}
        component_raw = {}

        for comp_name, config in self.COMPONENTS.items():
            series = self._get_series(df, comp_name)
            if series is None or series.dropna().empty:
                logger.debug(f"Liquidity component {comp_name} not available")
                continue

            # Transform
            transformed = self._transform_component(series, comp_name)
            transformed = transformed.dropna()

            if len(transformed) < 12:
                continue

            # Z-score
            zscore = self._compute_zscore(transformed)
            current_z = float(zscore.iloc[-1]) if not zscore.dropna().empty else 0.0

            # Apply direction
            adjusted_z = current_z * config["direction"]
            component_zscores[comp_name] = adjusted_z
            component_raw[comp_name] = float(transformed.iloc[-1])

        if len(component_zscores) < 2:
            logger.warning(f"Insufficient liquidity components: {len(component_zscores)}")
            return LiquidityResult(
                liquidity_index=0.0,
                signal="NEUTRAL",
                components={},
                percentile_rank=50,
                description="Insufficient data for liquidity index",
            )

        # Inverse-volatility weighting
        weights = {}
        total_weight = 0.0
        for comp in component_zscores.keys():
            series = self._get_series(df, comp)
            if series is not None:
                transformed = self._transform_component(series, comp)
                w = self._inverse_vol_weight(transformed.dropna())
                weights[comp] = w
                total_weight += w

        # Normalise weights
        if total_weight > 0:
            weights = {k: v / total_weight for k, v in weights.items()}
        else:
            weights = {k: 1.0 / len(component_zscores) for k in component_zscores}

        # Weighted composite
        composite = sum(component_zscores[k] * weights.get(k, 0) for k in component_zscores)

        # Signal classification
        if composite > 0.5:
            signal = "EASING"
        elif composite < -0.5:
            signal = "TIGHTENING"
        else:
            signal = "NEUTRAL"

        # Percentile rank (approximate)
        percentile = int(50 + composite * 25)
        percentile = max(0, min(100, percentile))

        description = (
            f"Liquidity Index: {composite:+.2f}σ ({signal}) | "
            f"Components: {len(component_zscores)} | "
            f"M2: {component_raw.get('m2_growth', 0):.1f}% | "
            f"Fed BS: {component_raw.get('fed_balance_sheet', 0):+.1f}%"
        )

        return LiquidityResult(
            liquidity_index=round(composite, 2),
            signal=signal,
            components=component_zscores,
            percentile_rank=percentile,
            description=description,
        )


def get_liquidity_index(df: pd.DataFrame) -> LiquidityResult:
    """Compute liquidity index from DataFrame."""
    model = LiquidityIndexModel()
    return model.compute(df)


def get_liquidity_dict(df: pd.DataFrame) -> dict:
    """Get liquidity index as simple dict for API response."""
    result = get_liquidity_index(df)
    return {
        "liquidity_index": result.liquidity_index,
        "signal": result.signal,
        "components": result.components,
        "percentile_rank": result.percentile_rank,
        "description": result.description,
    }
