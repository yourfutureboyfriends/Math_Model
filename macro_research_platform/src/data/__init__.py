"""
Data module for macro research platform.

Provides:
- Multi-source data clients (FRED, BEA, BLS, etc.)
- Data caching and validation
- Freshness tracking
- Vintage data support
- Live data loader with strict mode enforcement
"""

# Core data loading (always available)
from .data_loader_live import (
    load_model_data,
    get_data_status,
    DataModeError,
    LiveDataLoader,
)

from .fred_live_fetcher import (
    FredLiveFetcher,
    refresh_fred_live_data,
    FRED_INDICATORS,
)

__all__ = [
    # Core data loading
    "load_model_data",
    "get_data_status",
    "DataModeError",
    "LiveDataLoader",
    # FRED client
    "FredLiveFetcher",
    "refresh_fred_live_data",
    "FRED_INDICATORS",
]
