"""Every `price_service.<method>` call site must resolve to a real method.

The /ws/prices loop called `price_service.get_latest_prices([...])` for months. No such method
exists; the AttributeError was caught and logged at DEBUG, so the socket silently emitted bare
heartbeats and nothing looked broken. A renamed or misspelled service method is invisible to
the type checker here because the call sits inside a `try/except Exception`, so check it once
statically instead.
"""
import ast
from pathlib import Path

from api.services.price_service import PriceService, price_service

API_DIR = Path(__file__).resolve().parents[1]


def _call_sites():
    """Yield (attr, file, lineno) for every `price_service.<attr>` in api/, tests excluded."""
    for path in sorted(API_DIR.rglob("*.py")):
        if "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                    and node.value.id == "price_service":
                yield node.attr, path.relative_to(API_DIR.parent), node.lineno


def test_price_service_call_sites_all_resolve():
    sites = list(_call_sites())
    assert sites, "no price_service call sites found — the scan itself is broken"
    missing = [(a, f, ln) for a, f, ln in sites if not hasattr(price_service, a)]
    assert not missing, (
        "price_service has no such attribute; the call would raise AttributeError "
        f"and, inside a try/except, fail silently: {missing}"
    )


def test_price_service_methods_are_declared_on_the_class():
    # Guards the singleton drifting from its class (e.g. an attr set only in __init__),
    # which would make the check above pass for one instance and fail for a fresh one.
    for attr, _, _ in _call_sites():
        assert hasattr(PriceService, attr), f"{attr} is not declared on PriceService"


def test_current_prices_is_a_flat_symbol_to_number_map():
    # The websocket forwards this straight into the store's `prices` map, which is typed
    # {SYMBOL: number | null}; a nested payload would type-check nowhere and render as NaN.
    prices = price_service.get_current_prices()
    assert isinstance(prices, dict)
    for symbol, value in prices.items():
        assert isinstance(symbol, str) and symbol == symbol.upper(), symbol
        assert isinstance(value, (int, float)) and not isinstance(value, bool), (symbol, value)
