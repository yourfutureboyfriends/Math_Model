"""IBKR TWS data source: contract mapping, the data-only guarantee, and a clear state when TWS is not running."""
import inspect
import re

import pytest

from api.providers import ibkr_tws as it


@pytest.mark.parametrize("sym,want", [("AAPL", ("AAPL", "SMART", "USD", "")), ("BRK-B", ("BRK B", "SMART", "USD", "")),
                                      ("HSBA.L", ("HSBA", "SMART", "GBP", "LSE")), ("SAP.DE", ("SAP", "SMART", "EUR", "IBIS")),
                                      ("7203.T", ("7203", "SMART", "JPY", "TSEJ")), ("0700.HK", ("700", "SMART", "HKD", "SEHK")),
                                      ("NESN.SW", ("NESN", "SMART", "CHF", "EBS"))])
def test_contract_mapping(sym, want):
    c = it.to_contract(sym)
    assert (c.symbol, c.exchange, c.currency, c.primaryExchange) == want


def test_indices_and_fx_are_not_stock_contracts():
    assert it.to_contract("^GSPC") is None and it.to_contract("EURUSD=X") is None


def test_module_is_data_only():
    code = re.sub(r'"""[\s\S]*?"""', "", inspect.getsource(it))
    code = "\n".join(l for l in code.splitlines() if not l.strip().startswith("#"))
    for call in ("placeOrder", "cancelOrder", "reqGlobalCancel", "Order(", "LimitOrder", "MarketOrder", "whatIfOrder"):
        assert call not in code, call


def test_without_tws_everything_reports_not_running(monkeypatch):
    monkeypatch.setattr(it, "tws_running", lambda: False)
    assert it.status()["connected"] is False
    with pytest.raises(it.IbkrUnavailable, match="not running"):
        it.quotes(["AAPL"])
