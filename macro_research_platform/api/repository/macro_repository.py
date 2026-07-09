"""
Macro Repository — Single source of truth for macroeconomic data.

Stores normalized FRED macro series.
"""

import logging
from typing import Dict, Optional, Any, List
from datetime import datetime

from api.data_contracts import CONTRACTS

logger = logging.getLogger(__name__)


class MacroRepository:
    """
    Repository for macroeconomic indicators.

    Stores metrics by name with full history and metadata.
    """

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}  # metric_name -> latest data
        self._history: Dict[str, List[Dict[str, Any]]] = {}  # metric_name -> history
        self._last_update: Optional[datetime] = None

    def get_metric(self, name: str) -> Optional[Dict[str, Any]]:
        """Get latest value for a macro metric."""
        return self._cache.get(name)

    def get_metric_value(self, name: str) -> Optional[float]:
        """Get just the value for a metric."""
        data = self._cache.get(name)
        if data:
            return data.get("value")
        return None

    def get_history(self, name: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get historical values for a metric."""
        history = self._history.get(name, [])
        return history[-limit:]

    def update_metric(self, name: str, data: Dict[str, Any]) -> None:
        """Update a macro metric."""
        self._cache[name] = data

        # Add to history
        if name not in self._history:
            self._history[name] = []
        self._history[name].append(data)

        # Limit history size
        if len(self._history[name]) > 1000:
            self._history[name] = self._history[name][-1000:]

        self._last_update = datetime.utcnow()

    def get_all_metrics(self) -> Dict[str, float]:
        """Get all current metric values."""
        return {
            name: data.get("value")
            for name, data in self._cache.items()
            if data.get("value") is not None
        }

    def get_metrics_by_category(self, category: str) -> List[str]:
        """Get metric names by category (e.g., 'rates', 'inflation')."""
        # Simple categorization based on contract
        categories = {
            "rates": ["fed_funds", "yield_curve", "tenyr", "twoyr"],
            "inflation": ["inflation", "cpi_yoy"],
            "growth": ["growth", "m2_yoy"],
            "credit": ["hy_spread"],
            "volatility": ["vix"],
            "labor": ["sahm_rule", "unemployment"],
        }
        return categories.get(category, [])

    def get_metadata(self) -> Dict[str, Any]:
        """Get repository metadata."""
        return {
            "metric_count": len(self._cache),
            "last_update": self._last_update.isoformat() if self._last_update else None,
        }


# Global instance
macro_repository = MacroRepository()
