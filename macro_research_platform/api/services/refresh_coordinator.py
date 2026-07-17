"""
Refresh Coordinator — Centralized data refresh orchestration.

Responsibilities:
1. Call providers
2. Normalize results
3. Validate results
4. Update repository state
5. Invalidate dependent computed caches
6. Preserve last known good data when safe
7. Record refresh metadata

Rules:
- Endpoints must never fetch external data directly
- One provider failure should not crash the whole refresh cycle
- Partial refresh is allowed, but must be explicit and logged
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from api.providers.yahoo_provider import YahooFinanceProvider
from api.providers.fred_provider import FREDProvider
from api.normalization.prices import normalize_prices
from api.normalization.macro_series import normalize_macro_value
from api.repository.market_repository import market_repository
from api.repository.macro_repository import macro_repository
from api.data_contracts import CONTRACTS

logger = logging.getLogger(__name__)


class ProviderState(Enum):
    """State of a provider refresh."""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    NOT_RUN = "not_run"


@dataclass
class ProviderStatus:
    """Status of a provider refresh."""
    name: str
    state: ProviderState
    last_attempt: Optional[datetime] = None
    last_success: Optional[datetime] = None
    latency_ms: float = 0.0
    records_fetched: int = 0
    records_accepted: int = 0
    records_rejected: int = 0
    is_stale: bool = True
    error_message: Optional[str] = None


@dataclass
class RefreshResult:
    """Result of a full refresh cycle."""
    success: bool
    timestamp: datetime
    provider_statuses: Dict[str, ProviderStatus] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


class RefreshCoordinator:
    """
    Centralized coordinator for all data refreshes.

    This is the ONLY place that should call providers directly.
    All refreshes go through this coordinator.
    """

    # Symbols to refresh
    DEFAULT_SYMBOLS = [
        "SPX", "NDX", "VIX", "TENYR", "TWYR",
        "DXY", "EURUSD", "GBPUSD", "USDJPY",
        "GLD", "WTI", "SPY", "TLT"
    ]

    # Metrics to refresh
    DEFAULT_METRICS = [
        "fed_funds", "inflation", "hy_spread",
        "yield_curve", "sahm_rule", "vix"
    ]

    def __init__(self):
        self._yahoo = YahooFinanceProvider()
        self._fred = FREDProvider()
        self._statuses: Dict[str, ProviderStatus] = {}

    def refresh_prices(self, symbols: Optional[List[str]] = None) -> ProviderStatus:
        """
        Refresh market prices from Yahoo Finance.

        Args:
            symbols: List of symbols to refresh (default: DEFAULT_SYMBOLS)

        Returns:
            ProviderStatus with results.
        """
        symbols = symbols or self.DEFAULT_SYMBOLS
        status = ProviderStatus(name="yahoo_finance", state=ProviderState.NOT_RUN)
        status.last_attempt = datetime.utcnow()

        try:
            # Fetch from provider
            result = self._yahoo.fetch_latest(symbols)
            status.latency_ms = result.latency_ms

            if not result.success:
                status.state = ProviderState.FAILED
                status.error_message = result.error
                logger.error(f"Yahoo Finance refresh failed: {result.error}")
                return status

            # Normalize
            normalized = normalize_prices(result.data or {})
            status.records_fetched = result.records_fetched

            # Validate and update repository
            errors = market_repository.update_prices(normalized)
            status.records_accepted = len(normalized) - len(errors)
            status.records_rejected = len(errors)

            if errors:
                logger.warning(f"Price validation errors: {errors}")

            # Determine state
            if status.records_accepted == 0:
                status.state = ProviderState.FAILED
            elif errors:
                status.state = ProviderState.PARTIAL
            else:
                status.state = ProviderState.SUCCESS
                status.last_success = datetime.utcnow()
                status.is_stale = False

        except Exception as e:
            status.state = ProviderState.FAILED
            status.error_message = str(e)
            logger.error(f"Price refresh exception: {e}", exc_info=True)

        self._statuses["yahoo_finance"] = status
        return status

    def refresh_macro(self, metrics: Optional[List[str]] = None) -> ProviderStatus:
        """
        Refresh macroeconomic data from FRED.

        Args:
            metrics: List of metric names (default: DEFAULT_METRICS)

        Returns:
            ProviderStatus with results.
        """
        metrics = metrics or self.DEFAULT_METRICS
        status = ProviderStatus(name="fred", state=ProviderState.NOT_RUN)
        status.last_attempt = datetime.utcnow()

        try:
            total_fetched = 0
            total_accepted = 0
            errors = []

            for metric_name in metrics:
                contract = CONTRACTS.get(metric_name)
                if not contract:
                    errors.append(f"No contract for {metric_name}")
                    continue

                if not contract.fred_series:
                    continue

                # Fetch
                obs = self._fred.fetch_latest(contract.fred_series)
                total_fetched += 1

                if obs is None:
                    errors.append(f"FRED fetch failed for {metric_name}")
                    continue

                # Normalize
                normalized = normalize_macro_value(
                    metric_name,
                    obs.value,
                    source=f"FRED:{contract.fred_series}"
                )

                if normalized:
                    macro_repository.update_metric(metric_name, normalized)
                    total_accepted += 1
                else:
                    errors.append(f"Normalization failed for {metric_name}")

            status.records_fetched = total_fetched
            status.records_accepted = total_accepted
            status.records_rejected = total_fetched - total_accepted

            if total_accepted == 0:
                status.state = ProviderState.FAILED
                status.error_message = "; ".join(errors[:5])
            elif errors:
                status.state = ProviderState.PARTIAL
                status.error_message = "; ".join(errors[:3])
            else:
                status.state = ProviderState.SUCCESS
                status.last_success = datetime.utcnow()
                status.is_stale = False

        except Exception as e:
            status.state = ProviderState.FAILED
            status.error_message = str(e)
            logger.error(f"Macro refresh exception: {e}", exc_info=True)

        self._statuses["fred"] = status
        return status

    def refresh_all(self) -> RefreshResult:
        """
        Run full refresh cycle for all providers.

        Returns:
            RefreshResult with all statuses.
        """
        result = RefreshResult(
            success=True,
            timestamp=datetime.utcnow(),
            provider_statuses={},
            errors=[]
        )

        # Refresh prices
        price_status = self.refresh_prices()
        result.provider_statuses["yahoo_finance"] = price_status

        if price_status.state == ProviderState.FAILED:
            result.errors.append(f"Price refresh failed: {price_status.error_message}")

        # Refresh macro
        macro_status = self.refresh_macro()
        result.provider_statuses["fred"] = macro_status

        if macro_status.state == ProviderState.FAILED:
            result.errors.append(f"Macro refresh failed: {macro_status.error_message}")

        # Overall success if at least prices succeeded
        result.success = price_status.state in (ProviderState.SUCCESS, ProviderState.PARTIAL)

        return result

    def get_status(self, provider_name: Optional[str] = None) -> Dict[str, Any]:
        """Get current status of providers."""
        if provider_name:
            status = self._statuses.get(provider_name)
            return status.__dict__ if status else {}
        return {name: status.__dict__ for name, status in self._statuses.items()}

    def is_healthy(self) -> bool:
        """Check if data sources are healthy."""
        for status in self._statuses.values():
            if status.is_stale and status.state != ProviderState.SUCCESS:
                return False
        return True


# Global coordinator instance
refresh_coordinator = RefreshCoordinator()
