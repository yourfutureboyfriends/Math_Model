"""
Provider-agnostic data access layer (Universal Data Layer, Phase 1).

The rest of the app asks the ProviderRegistry for a Quote / TimeSeries / MacroSeries by
symbol + asset class; the registry routes to the best-fit provider by priority and, if the
primary fails / times out / rate-limits, automatically falls back to the next provider —
logging every fallback so degraded reliance on backups is visible in System Health.

Adding a provider = implement the small DataProvider protocol and register() it. Keyed
providers (Alpha Vantage, Polygon, …) activate automatically when their key is present,
with zero changes to calculation logic.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

AssetClass = str  # "equity" | "index" | "fx" | "commodity" | "crypto" | "rate" | "bond" | "macro"


# ── Common internal data contract (provider-independent) ──────────────────────
@dataclass
class Quote:
    symbol: str
    price: float
    timestamp: datetime
    source: str
    asset_class: AssetClass = "equity"
    change_pct: Optional[float] = None
    currency: str = "USD"


@dataclass
class TimeSeriesPoint:
    timestamp: str
    close: float
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    volume: Optional[float] = None


@dataclass
class TimeSeries:
    symbol: str
    interval: str
    points: List[TimeSeriesPoint]
    source: str


@runtime_checkable
class DataProvider(Protocol):
    name: str
    priority: int
    asset_classes: List[AssetClass]

    def supports(self, symbol: str, asset_class: AssetClass) -> bool: ...
    def healthy(self) -> bool: ...
    def get_quote(self, symbol: str, asset_class: AssetClass) -> Optional[Quote]: ...


# ── Registry ──────────────────────────────────────────────────────────────────
@dataclass
class _ProviderState:
    provider: object
    fallback_count: int = 0
    error_count: int = 0
    served_count: int = 0
    last_error: Optional[str] = None
    down_since: Optional[float] = None


class ProviderRegistry:
    def __init__(self) -> None:
        self._states: List[_ProviderState] = []

    def register(self, provider) -> None:
        self._states.append(_ProviderState(provider=provider))
        # keep sorted by priority (lower = tried first)
        self._states.sort(key=lambda s: getattr(s.provider, "priority", 99))
        logger.info("[registry] registered provider %s (priority %s, classes %s)",
                    provider.name, provider.priority, provider.asset_classes)

    def _candidates(self, symbol: str, asset_class: AssetClass) -> List[_ProviderState]:
        out = []
        for st in self._states:
            p = st.provider
            try:
                if asset_class in getattr(p, "asset_classes", []) and p.supports(symbol, asset_class) and p.healthy():
                    out.append(st)
            except Exception:
                continue
        return out

    def get_quote(self, symbol: str, asset_class: AssetClass = "equity") -> Optional[Quote]:
        """Return a Quote from the highest-priority provider that answers; fall back on
        failure and record every fallback event."""
        cands = self._candidates(symbol, asset_class)
        if not cands:
            logger.error("[registry] no provider available for %s (%s)", symbol, asset_class)
            return None
        primary = cands[0].provider.name
        for i, st in enumerate(cands):
            p = st.provider
            try:
                q = p.get_quote(symbol, asset_class)
                if q is not None:
                    st.served_count += 1
                    st.down_since = None
                    if i > 0:
                        cands[0].fallback_count += 1
                        logger.warning("[registry] FALLBACK %s -> %s served %s (%s)",
                                       primary, p.name, symbol, asset_class)
                    return q
                raise ValueError("empty result")
            except Exception as e:
                st.error_count += 1
                st.last_error = str(e)[:120]
                if st.down_since is None:
                    st.down_since = time.time()
                logger.warning("[registry] provider %s failed for %s: %s", p.name, symbol, str(e)[:80])
                continue
        logger.error("[registry] ALL providers failed for %s (%s)", symbol, asset_class)
        return None

    def status(self) -> List[Dict]:
        now = time.time()
        out = []
        for st in self._states:
            p = st.provider
            down_min = round((now - st.down_since) / 60, 1) if st.down_since else 0
            out.append({
                "name": p.name,
                "priority": p.priority,
                "asset_classes": list(p.asset_classes),
                "healthy": bool(_safe(p.healthy, False)),
                "served": st.served_count,
                "errors": st.error_count,
                "fallbacks_triggered": st.fallback_count,
                "last_error": st.last_error,
                "down_minutes": down_min,
            })
        return out


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default
