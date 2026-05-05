"""
Signalling module for Macro Terminal.

Contains trade recommendation engine components:
- universe_builder: Discovers and enriches tradeable instruments
- trade_engine: Generates LONG/SHORT recommendations based on regime × factor × macro scoring
"""

from .universe_builder import (
    build_universe,
    get_universe_by_class,
    get_universe_by_factor,
    get_universe_by_regime_score,
    EXCHANGES,
    MACRO_ETF_TICKERS,
    SECTOR_REGIME_MAP,
    FACTOR_WEIGHTS_BY_REGIME,
    ETF_ASSET_CLASS_MAP,
)

from .trade_engine import (
    generate_all_recommendations,
    UNIVERSE,
    BASE_WEIGHTS,
)

__all__ = [
    "build_universe",
    "get_universe_by_class",
    "get_universe_by_factor",
    "get_universe_by_regime_score",
    "EXCHANGES",
    "MACRO_ETF_TICKERS",
    "SECTOR_REGIME_MAP",
    "FACTOR_WEIGHTS_BY_REGIME",
    "ETF_ASSET_CLASS_MAP",
    "generate_all_recommendations",
    "UNIVERSE",
    "BASE_WEIGHTS",
]
