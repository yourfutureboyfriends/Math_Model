"""Shared calculation module - all market data calculations in one place."""
from .regime import classify_regime, get_regime_characteristics
from .signals import calculate_growth_signal, calculate_inflation_signal, calculate_liquidity_signal, calculate_risk_signal
from .metrics import calculate_recession_probability, calculate_sector_allocation

__all__ = [
    'classify_regime',
    'get_regime_characteristics',
    'calculate_growth_signal',
    'calculate_inflation_signal',
    'calculate_liquidity_signal',
    'calculate_risk_signal',
    'calculate_recession_probability',
    'calculate_sector_allocation',
]
