"""
Market Repository — Single source of truth for market data access.

All services read market data through this repository.
No direct provider calls from services or endpoints.
"""

import logging
import threading
from typing import Dict, Optional, Any, List
from datetime import datetime

from api.providers.yahoo_provider import YahooFinanceProvider
from api.normalization.prices import calculate_price_changes
from api.validation.prices import validate_price_batch, check_stale_prices

logger = logging.getLogger(__name__)


class MarketRepository:
    """
    Repository for market prices and changes.

    Responsibilities:
    - Cache market prices in memory
    - Provide read access to prices
    - Track metadata (last update, staleness)

    Does NOT:
    - Fetch prices directly (coordinator does this)
    - Apply business logic
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, cache_ttl_seconds: int = 60):
        if self._initialized:
            return

        self._cache: Dict[str, Dict[str, Any]] = {}
        self._changes: Dict[str, Optional[float]] = {}
        self._last_update: Optional[datetime] = None
        self._cache_ttl = cache_ttl_seconds
        self._provider = YahooFinanceProvider()
        self._initialized = True

    def get_price(self, symbol: str) -> Optional[float]:
        """Get cached price for a symbol."""
        data = self._cache.get(symbol.upper())
        if data:
            return data.get("price")
        return None

    def get_all_prices(self) -> Dict[str, float]:
        """Get all cached prices."""
        return {
            sym: data["price"]
            for sym, data in self._cache.items()
            if data.get("price") is not None
        }

    def get_price_with_metadata(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get price with full metadata."""
        return self._cache.get(symbol.upper())

    def get_all_with_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Get all prices with metadata."""
        return self._cache.copy()

    def get_changes(self) -> Dict[str, Optional[float]]:
        """Get daily percent changes."""
        return self._changes.copy()

    def get_change(self, symbol: str) -> Optional[float]:
        """Get daily change for a symbol."""
        return self._changes.get(symbol.upper())

    def is_fresh(self, max_age_seconds: int = 120) -> bool:
        """Check if cache is fresh."""
        if self._last_update is None:
            return False
        age = (datetime.utcnow() - self._last_update).total_seconds()
        return age < max_age_seconds

    def get_last_update(self) -> Optional[datetime]:
        """Get timestamp of last update."""
        return self._last_update

    def get_stale_symbols(self, max_age_minutes: int = 5) -> List[str]:
        """Get list of stale symbols."""
        return check_stale_prices(self._cache, max_age_minutes)

    def update_prices(self, prices: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
        """
        Update the cache with new prices.

        Args:
            prices: Dict of symbol -> normalized price data

        Returns:
            Dict of validation errors by symbol.
        """
        # Validate
        errors = validate_price_batch(prices)
        valid_prices = {k: v for k, v in prices.items() if k not in errors}

        # Store previous for change calculation
        previous_prices = self.get_all_prices()

        # Update cache
        self._cache.update(valid_prices)
        self._last_update = datetime.utcnow()

        # Calculate changes
        current_prices = self.get_all_prices()
        self._changes = calculate_price_changes(current_prices, previous_prices)

        if errors:
            logger.warning(f"Price update had {len(errors)} validation errors")

        return errors

    def get_symbols(self) -> List[str]:
        """Get list of all cached symbols."""
        return list(self._cache.keys())

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()
        self._changes.clear()
        self._last_update = None

    def get_metadata(self) -> Dict[str, Any]:
        """Get repository metadata for health checks."""
        return {
            "symbol_count": len(self._cache),
            "last_update": self._last_update.isoformat() if self._last_update else None,
            "is_fresh": self.is_fresh(),
            "stale_symbols": len(self.get_stale_symbols()),
        }


# Global instance
market_repository = MarketRepository()
