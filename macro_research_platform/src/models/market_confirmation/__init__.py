"""
Market Confirmation Module

Validates macro regime signals against actual market price action.
"""

from .trend_confirmation_model import (
    MarketConfirmationModel,
    TrendConfirmationResult,
    TrendSignal,
    calculate_market_regime_alignment,
)

__all__ = [
    "MarketConfirmationModel",
    "TrendConfirmationResult",
    "TrendSignal",
    "calculate_market_regime_alignment",
]
