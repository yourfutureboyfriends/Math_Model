"""
Known-answer tests for the provider registry + failover (Universal Data Layer, Phase 1).
Run: pytest api/tests/test_provider_registry.py
"""
from datetime import datetime
from api.providers.registry import ProviderRegistry, Quote


class _Provider:
    def __init__(self, name, priority, classes, behaviour):
        self.name = name; self.priority = priority; self.asset_classes = classes
        self._behaviour = behaviour  # "ok" | "raise" | "none" | "down"
    def supports(self, symbol, asset_class): return asset_class in self.asset_classes
    def healthy(self): return self._behaviour != "down"
    def get_quote(self, symbol, asset_class="equity"):
        if self._behaviour == "raise":
            raise RuntimeError("simulated provider outage")
        if self._behaviour == "none":
            return None
        return Quote(symbol=symbol, price=100.0, timestamp=datetime.now(), source=self.name, asset_class=asset_class)


def test_primary_serves_when_healthy():
    reg = ProviderRegistry()
    reg.register(_Provider("primary", 1, ["equity"], "ok"))
    reg.register(_Provider("backup", 2, ["equity"], "ok"))
    q = reg.get_quote("SPY", "equity")
    assert q is not None and q.source == "primary"
    st = {s["name"]: s for s in reg.status()}
    assert st["primary"]["served"] == 1


def test_fallback_on_primary_exception():
    reg = ProviderRegistry()
    reg.register(_Provider("primary", 1, ["equity"], "raise"))
    reg.register(_Provider("backup", 2, ["equity"], "ok"))
    q = reg.get_quote("SPY", "equity")
    assert q is not None and q.source == "backup"          # failover worked
    st = {s["name"]: s for s in reg.status()}
    assert st["primary"]["errors"] == 1
    assert st["primary"]["fallbacks_triggered"] == 1        # fallback event recorded


def test_fallback_on_primary_empty():
    reg = ProviderRegistry()
    reg.register(_Provider("primary", 1, ["equity"], "none"))
    reg.register(_Provider("backup", 2, ["equity"], "ok"))
    assert reg.get_quote("SPY", "equity").source == "backup"


def test_all_providers_fail_returns_none():
    reg = ProviderRegistry()
    reg.register(_Provider("a", 1, ["equity"], "raise"))
    reg.register(_Provider("b", 2, ["equity"], "raise"))
    assert reg.get_quote("SPY", "equity") is None           # honest failure, not fabricated


def test_unhealthy_provider_skipped():
    reg = ProviderRegistry()
    reg.register(_Provider("down", 1, ["equity"], "down"))   # skipped (healthy()=False)
    reg.register(_Provider("up", 2, ["equity"], "ok"))
    assert reg.get_quote("SPY", "equity").source == "up"


def test_routes_by_asset_class():
    reg = ProviderRegistry()
    reg.register(_Provider("prices", 1, ["equity", "fx"], "ok"))
    reg.register(_Provider("macro", 1, ["macro"], "ok"))
    assert reg.get_quote("GDP", "macro").source == "macro"
    assert reg.get_quote("EURUSD", "fx").source == "prices"
