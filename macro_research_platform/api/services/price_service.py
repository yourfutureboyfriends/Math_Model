"""
Price Service — Business logic for price-related computations.

Computations:
- Price percentiles
- Trend analysis
- Cross-asset correlations
- Alert thresholds

Reads from repository, not providers.
"""

import logging
import statistics
from typing import Dict, List, Optional, Any

from api.repository.market_repository import market_repository

logger = logging.getLogger(__name__)


class PriceService:
    """
    Business service for price analysis.

    All price computations go through this service.
    No direct provider access.
    """

    def __init__(self):
        self._repository = market_repository

    def get_current_prices(self) -> Dict[str, float]:
        """Get all current prices."""
        return self._repository.get_all_prices()

    def get_price(self, symbol: str) -> Optional[float]:
        """Get single price."""
        return self._repository.get_price(symbol)

    def get_change_pct(self, symbol: str) -> Optional[float]:
        """Get daily change percentage."""
        return self._repository.get_change(symbol)

    def get_price_with_change(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get price with change data."""
        price = self._repository.get_price(symbol)
        change = self._repository.get_change(symbol)

        if price is None:
            return None

        return {
            "symbol": symbol,
            "price": price,
            "change_pct": change,
            "change_abs": price * (change or 0) / 100 if change else None,
        }

    def calculate_percentile(self, symbol: str, history: List[float]) -> Optional[float]:
        """
        Calculate percentile of current price in history.

        Args:
            symbol: Symbol to check
            history: Historical prices

        Returns:
            Percentile (0-100) or None.
        """
        current = self._repository.get_price(symbol)
        if current is None or not history:
            return None

        # Calculate percentile
        below = sum(1 for p in history if p < current)
        return (below / len(history)) * 100

    def calculate_volatility(
        self,
        changes: List[float],
        annualize: bool = True
    ) -> Optional[float]:
        """
        Calculate realized volatility from changes.

        Args:
            changes: List of daily percent changes
            annualize: Annualize the result (multiply by sqrt(252))

        Returns:
            Volatility as percentage or None.
        """
        if len(changes) < 2:
            return None

        try:
            vol = statistics.stdev(changes)
            if annualize:
                vol *= (252 ** 0.5)  # sqrt(252)
            return vol
        except statistics.StatisticsError:
            return None

    def get_market_summary(self) -> Dict[str, Any]:
        """Get summary of market conditions."""
        prices = self._repository.get_all_prices()
        changes = self._repository.get_changes()

        if not prices:
            return {"error": "No price data available"}

        # Calculate aggregates
        valid_changes = [c for c in changes.values() if c is not None]
        avg_change = statistics.mean(valid_changes) if valid_changes else 0

        advancers = sum(1 for c in valid_changes if c > 0)
        decliners = sum(1 for c in valid_changes if c < 0)

        return {
            "symbols_tracked": len(prices),
            "avg_change_pct": round(avg_change, 2),
            "advancers": advancers,
            "decliners": decliners,
            "data_fresh": self._repository.is_fresh(),
        }

    def is_market_open_hours(self) -> bool:
        """
        Check if currently within US market hours.
        Simple check - not exact for holidays.
        """
        from datetime import datetime, time
        now = datetime.utcnow()

        # Convert to approximate US Eastern
        # UTC is 4-5 hours ahead of ET depending on DST
        hour_et = (now.hour - 5) % 24  # Rough conversion

        # Market hours: 9:30 AM - 4:00 PM ET
        return 9 <= hour_et <= 16


# Global instance
price_service = PriceService()
