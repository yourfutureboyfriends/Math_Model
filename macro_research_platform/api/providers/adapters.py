"""
Concrete DataProvider adapters behind the common contract (Phase 1C).

- YahooDownloadProvider : wraps the existing YahooFinanceProvider (yfinance download path).
- YahooChartProvider    : direct query1.finance.yahoo.com chart JSON (independent keyless
                          code path — used to demonstrate real failover).
- AlphaVantageProvider  : keyed; activates automatically only when ALPHA_VANTAGE_KEY is set.
- FredMacroProvider     : wraps FREDProvider for macro series.

Each is small and self-contained; adding another provider is the same shape.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import List, Optional

from api.providers.registry import Quote, AssetClass

logger = logging.getLogger(__name__)

_PRICE_CLASSES = ["equity", "index", "fx", "commodity", "crypto"]


class YahooDownloadProvider:
    name = "yahoo_download"
    priority = 1
    asset_classes: List[AssetClass] = _PRICE_CLASSES

    def __init__(self):
        from api.providers.yahoo_provider import YahooFinanceProvider
        self._yf = YahooFinanceProvider()

    def supports(self, symbol: str, asset_class: AssetClass) -> bool:
        return asset_class in self.asset_classes

    def healthy(self) -> bool:
        return True

    def get_quote(self, symbol: str, asset_class: AssetClass = "equity") -> Optional[Quote]:
        rec = self._yf.fetch_single(symbol)
        if rec is None or not getattr(rec, "price", None):
            return None
        return Quote(symbol=symbol, price=float(rec.price),
                     timestamp=getattr(rec, "timestamp", datetime.now()),
                     source=self.name, asset_class=asset_class,
                     currency=getattr(rec, "currency", "USD"))


class YahooChartProvider:
    """Independent keyless second Yahoo path (chart JSON), so the registry has a real
    fallback to route to when the download path fails."""
    name = "yahoo_chart"
    priority = 2
    asset_classes: List[AssetClass] = _PRICE_CLASSES

    def supports(self, symbol: str, asset_class: AssetClass) -> bool:
        return asset_class in self.asset_classes

    def healthy(self) -> bool:
        return True

    def get_quote(self, symbol: str, asset_class: AssetClass = "equity") -> Optional[Quote]:
        import requests
        # Reuse the canonical->yfinance symbol map so aliases (SPX->^GSPC) resolve here too.
        try:
            from api.providers.yahoo_provider import YahooFinanceProvider
            mapped = YahooFinanceProvider.SYMBOL_MAP.get(symbol, symbol)
        except Exception:
            mapped = symbol
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{mapped}?range=1d&interval=1d"
        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        result = r.json()["chart"]["result"][0]
        meta = result.get("meta", {})
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        if price is None:
            return None
        change_pct = round((price / prev - 1) * 100, 2) if prev else None
        return Quote(symbol=symbol, price=float(price), timestamp=datetime.now(),
                     source=self.name, asset_class=asset_class, change_pct=change_pct,
                     currency=meta.get("currency", "USD"))


class AlphaVantageProvider:
    """Keyed multi-asset provider — inactive (healthy()=False) until ALPHA_VANTAGE_KEY is set,
    so it slots into the fallback chain zero-code once a key exists."""
    name = "alpha_vantage"
    priority = 3
    asset_classes: List[AssetClass] = ["equity", "index", "fx", "crypto"]

    def __init__(self):
        self._key = os.getenv("ALPHA_VANTAGE_KEY")

    def supports(self, symbol: str, asset_class: AssetClass) -> bool:
        return asset_class in self.asset_classes

    def healthy(self) -> bool:
        return bool(self._key)

    def get_quote(self, symbol: str, asset_class: AssetClass = "equity") -> Optional[Quote]:
        if not self._key:
            return None
        import requests
        r = requests.get("https://www.alphavantage.co/query", timeout=8, params={
            "function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": self._key})
        q = r.json().get("Global Quote", {})
        price = q.get("05. price")
        if not price:
            return None
        return Quote(symbol=symbol, price=float(price), timestamp=datetime.now(),
                     source=self.name, asset_class=asset_class)


class FredMacroProvider:
    name = "fred"
    priority = 1
    asset_classes: List[AssetClass] = ["macro"]

    def __init__(self):
        try:
            from api.providers.fred_provider import FREDProvider
            self._fred = FREDProvider()
            self._ok = True
        except Exception as e:
            logger.warning("[fred adapter] init failed: %s", e)
            self._ok = False

    def supports(self, symbol: str, asset_class: AssetClass) -> bool:
        return asset_class == "macro"

    def healthy(self) -> bool:
        return self._ok and bool(os.getenv("FRED_API_KEY"))

    def get_quote(self, symbol: str, asset_class: AssetClass = "macro") -> Optional[Quote]:
        # For macro, "quote" = latest observation value of the series.
        try:
            res = self._fred.fetch_series(symbol, limit=1)
            obs = getattr(res, "observations", None) or []
            if not obs:
                return None
            latest = obs[-1]
            val = getattr(latest, "value", None)
            if val is None:
                return None
            return Quote(symbol=symbol, price=float(val), timestamp=datetime.now(),
                         source=self.name, asset_class="macro")
        except Exception:
            return None


def build_default_registry():
    """Register the default providers in priority order."""
    from api.providers.registry import ProviderRegistry
    reg = ProviderRegistry()
    reg.register(YahooDownloadProvider())
    reg.register(YahooChartProvider())
    reg.register(AlphaVantageProvider())
    reg.register(FredMacroProvider())
    return reg
