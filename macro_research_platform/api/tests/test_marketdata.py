"""Markets mode backend, offline (yfinance stubbed): honest errors, universal search,
cross-listing removal, London international lines, pence market caps, yields in bp."""
import sys
import types

import numpy as np
import pandas as pd
import pytest

from api.marketdata import core


@pytest.fixture(autouse=True)
def clear_cache():
    core._cache.clear()
    yield
    core._cache.clear()


def _fake_yf(monkeypatch, **attrs):
    mod = types.SimpleNamespace(**attrs)
    monkeypatch.setitem(sys.modules, "yfinance", mod)
    return mod


def test_unknown_symbol_is_not_found_not_zero(monkeypatch):
    class T:
        def __init__(self, s): self.info = {"trailingPegRatio": None}
    _fake_yf(monkeypatch, Ticker=T)
    with pytest.raises(core.NotFound):
        core.quote("ZZZZ")


def test_quote_maps_any_instrument(monkeypatch):
    class T:
        def __init__(self, s):
            self.info = {"quoteType": "CRYPTOCURRENCY", "shortName": "Bitcoin USD", "regularMarketPrice": 100.0,
                         "regularMarketPreviousClose": 80.0, "currency": "USD", "exchange": "CCC"}
    _fake_yf(monkeypatch, Ticker=T)
    q = core.quote("btc-usd")
    assert q["symbol"] == "BTC-USD" and q["type"] == "Crypto" and q["change_pct"] == pytest.approx(0.25)


def test_search_keeps_indices_fx_futures_and_crypto(monkeypatch):
    class S:
        def __init__(self, q, **k):
            self.quotes = [{"symbol": "^N225", "quoteType": "INDEX", "shortname": "Nikkei"},
                           {"symbol": "EURUSD=X", "quoteType": "CURRENCY", "shortname": "EUR/USD"},
                           {"symbol": "GC=F", "quoteType": "FUTURE", "shortname": "Gold"},
                           {"symbol": "BRK-B", "quoteType": "EQUITY", "longname": "Berkshire"}]
    _fake_yf(monkeypatch, Search=S)
    assert [r["symbol"] for r in core.search("x")] == ["^N225", "EURUSD=X", "GC=F", "BRK-B"]   # nothing filtered out


def test_primary_only_drops_cross_listings_and_duplicates(monkeypatch):
    monkeypatch.setattr(core, "_foreign_names", lambda region: {core._norm("NVIDIA Corporation")})
    rows = [{"symbol": "NVD.DE", "name": "NVIDIA Corp"}, {"symbol": "SAP.DE", "name": "SAP SE"},
            {"symbol": "SAP.F", "name": "SAP SE"}]
    assert [r["symbol"] for r in core._primary_only(rows, "de")] == ["SAP.DE"]
    assert core._primary_only(rows, "us") == rows


def test_london_international_lines():
    assert core._is_secondary_line("0YG8.L") and not core._is_secondary_line("HSBA.L") and not core._is_secondary_line("0700.HK")


def test_uk_market_caps_are_in_pence(monkeypatch):
    calls = {}

    def fake_cached(key, ttl, fn):
        calls[key] = True
        return 0.75 if key == "fx:GBP" else fn()
    monkeypatch.setattr(core, "_cached", fake_cached)
    assert core.usd_to_local("gb") == pytest.approx(75.0) and core.usd_to_local("us") == 1.0


def test_overview_reports_yield_moves_in_basis_points(monkeypatch):
    idx = pd.bdate_range("2025-12-01", periods=60)
    syms = [s for g in core.OVERVIEW.values() for s, _ in g]
    cols = pd.MultiIndex.from_product([syms, ["Close"]])
    data = np.full((len(idx), len(syms)), 100.0)
    data[:, syms.index("^TNX")] = np.linspace(4.0, 4.5, len(idx))
    df = pd.DataFrame(data, index=idx, columns=cols)
    _fake_yf(monkeypatch, download=lambda *a, **k: df)
    out = core.overview()
    tnx = next(r for g in out["groups"] for r in g["rows"] if r["symbol"] == "^TNX")
    assert tnx["is_yield"] and tnx["change_1d_bp"] == pytest.approx((4.5 - 4.5 + 0.5 / 59) * 100, rel=1e-6)
    assert "change_1d" not in tnx                      # no misleading % change of a yield level


def test_cross_listing_detection():
    """Foreign companies' lines on another market are dropped; domestic companies (including
    Hong Kong's mainland-Chinese majors and dual primaries) are kept."""
    from api.marketdata import core
    fidx = {"names": {core._norm("NVIDIA Corporation")}}
    row = lambda sym, name, mc, px, vol, ccy="EUR": {"symbol": sym, "name": name, "market_cap": mc, "price": px, "volume": vol, "currency": ccy}
    assert core._is_cross_listing(row("NVD.DE", "NVIDIA Corporation", 4.9e12, 200, 1e5), "de", fidx)            # name
    assert core._is_cross_listing(row("GCP.DE", "General Electric Company", 2.8e11, 273, 400), "de", fidx)       # barely trades here
    assert not core._is_cross_listing(row("SAP.DE", "SAP SE", 2.2e11, 191, 1.5e6), "de", fidx)
    assert not core._is_cross_listing(row("0005.HK", "HSBC Holdings plc", 2.5e12, 145, 1e3, "HKD"), "hk", fidx)  # dual primary
    assert not core._is_cross_listing(row("HSBA.L", "HSBC Holdings plc", 2.4e11, 1395.8, 2e7, "GBp"), "gb", fidx)  # pence handled


def test_brazilian_depositary_receipts_are_secondary_lines():
    from api.marketdata import core
    assert core._is_secondary_line("AAPL34.SA") and core._is_secondary_line("T2TD34.SA")
    assert not core._is_secondary_line("PETR3.SA") and not core._is_secondary_line("BPAC11.SA")
    assert core._is_secondary_line("0YG8.L") and not core._is_secondary_line("HSBA.L")
