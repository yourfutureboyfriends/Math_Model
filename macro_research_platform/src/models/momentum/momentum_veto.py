"""
Momentum Veto Module

Implements 12-1 month momentum filter (Asness 1997) with regime-aware dampening.

For each asset:
- Calculate 12-1 month momentum (skip most recent month to avoid reversal)
- Compare momentum direction vs regime allocation
- If conflict: apply 50% weight dampener
- If alignment: full weight

Research basis:
- Asness (1997): "The Interaction of Value and Momentum Strategies"
- Moskowitz & Grinblatt (1999): "Do Industries Explain Momentum?"

Assets tracked:
- SPY (US Equities)
- TLT (Long-Term Treasuries)
- GLD (Gold)
- DBC (Commodities)
- UUP (US Dollar)
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class MomentumVetoResult:
    """Result from momentum veto computation."""
    veto_active: bool
    assets: Dict[str, dict]
    description: str


class MomentumVetoModel:
    """
    Compute momentum-based position adjustments.
    """

    ETF_SYMBOLS = {
        "SPY": "US Equities",
        "TLT": "Long Treasuries",
        "GLD": "Gold",
        "DBC": "Commodities",
        "UUP": "US Dollar",
    }

    def __init__(self, dampener: float = 0.5):
        self.dampener = dampener

    def _calculate_momentum(self, prices: pd.Series) -> Optional[float]:
        """
        Calculate 12-1 month momentum (skip most recent month).
        Returns annualised return %.
        """
        if len(prices) < 252:  # Need at least 1 year
            return None

        # Current price
        current = prices.iloc[-1]

        # Price 12 months ago
        price_12m = prices.iloc[-252]

        # Price 1 month ago (skip recent month)
        price_1m = prices.iloc[-21]

        if price_12m > 0 and price_1m > 0:
            # 12-1 month return
            ret_12m = (current / price_12m - 1) * 100
            ret_1m = (current / price_1m - 1) * 100
            momentum_12_1 = ret_12m - ret_1m
            return momentum_12_1

        return None

    def _get_regime_expected_direction(self, symbol: str, regime: str) -> str:
        """
        Get expected direction for asset in current regime.
        """
        regime_directions = {
            "Goldilocks": {
                "SPY": "UP",
                "TLT": "FLAT",
                "GLD": "FLAT",
                "DBC": "UP",
                "UUP": "FLAT",
            },
            "Reflation": {
                "SPY": "UP",
                "TLT": "DOWN",
                "GLD": "UP",
                "DBC": "UP",
                "UUP": "DOWN",
            },
            "Slowdown": {
                "SPY": "DOWN",
                "TLT": "UP",
                "GLD": "UP",
                "DBC": "DOWN",
                "UUP": "FLAT",
            },
            "Stagflation": {
                "SPY": "DOWN",
                "TLT": "DOWN",
                "GLD": "UP",
                "DBC": "UP",
                "UUP": "UP",
            },
        }

        return regime_directions.get(regime, {}).get(symbol, "FLAT")

    def compute(
        self, df: pd.DataFrame, regime: str = "Goldilocks"
    ) -> MomentumVetoResult:
        """
        Compute momentum veto adjustments.

        Args:
            df: DataFrame with price data
            regime: Current regime classification

        Returns:
            MomentumVetoResult with per-asset adjustments
        """
        assets = {}
        veto_count = 0

        for symbol, name in self.ETF_SYMBOLS.items():
            # Find price column
            price_col = None
            for col in df.columns:
                if symbol.lower() in col.lower() or col.lower() == symbol.lower():
                    price_col = col
                    break

            if price_col is None:
                continue

            prices = df[price_col].dropna()
            momentum = self._calculate_momentum(prices)

            if momentum is None:
                continue

            # Determine direction
            if momentum > 5:
                direction = "UP"
            elif momentum < -5:
                direction = "DOWN"
            else:
                direction = "FLAT"

            # Check vs regime expectation
            expected = self._get_regime_expected_direction(symbol, regime)

            # Veto if opposite to expectation (and not flat)
            dampener_applied = False
            if expected != "FLAT" and direction != "FLAT":
                if direction != expected:
                    dampener_applied = True
                    veto_count += 1

            assets[symbol] = {
                "name": name,
                "momentum_zscore": round(momentum / 20, 2),  # Rough z-score
                "direction": direction,
                "expected_direction": expected,
                "dampener_applied": dampener_applied,
                "momentum_pct": round(momentum, 2),
            }

        veto_active = veto_count >= 2  # Veto if 2+ assets conflict

        description = (
            f"Momentum Veto: {'ACTIVE' if veto_active else 'PASS'} | "
            f"Conflicts: {veto_count}/{len(assets)} | "
            f"Dampener: {self.dampener*100:.0f}%"
        )

        return MomentumVetoResult(
            veto_active=veto_active,
            assets=assets,
            description=description,
        )


def get_momentum_veto(df: pd.DataFrame, regime: str = "Goldilocks") -> MomentumVetoResult:
    """Compute momentum veto from DataFrame."""
    model = MomentumVetoModel()
    return model.compute(df, regime)


def get_momentum_veto_dict(df: pd.DataFrame, regime: str = "Goldilocks") -> dict:
    """Get momentum veto as simple dict for API response."""
    result = get_momentum_veto(df, regime)
    return {
        "veto_active": result.veto_active,
        "assets": result.assets,
        "description": result.description,
    }
