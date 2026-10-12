"""Global tradable universe for Code Lab jobs: symbol forms, market-class filters, FX gaps reported not fatal."""
import numpy as np
import pandas as pd
import pytest

from api.quant import codeserver


@pytest.fixture()
def universe(monkeypatch):
    from api import global_universe
    stocks = [{"symbol": "BRK.B", "country": "US", "listing_country": "US", "currency": "USD", "market_class": "Developed", "traded_usd": 5e9},
              {"symbol": "VOD.L", "country": "GB", "currency": "GBp", "market_class": "Developed", "traded_usd": 1e8},
              {"symbol": "7203.T", "country": "JP", "currency": "JPY", "market_class": "Developed", "traded_usd": 3e8},
              {"symbol": "PETR4.SA", "country": "BR", "currency": "BRL", "market_class": "Emerging", "traded_usd": 2e8}]
    monkeypatch.setattr(global_universe, "load", lambda **k: {"stocks": stocks})


def test_global_keeps_exchange_suffixes_and_dashes_us_classes(universe):
    assert codeserver.tradable_universe("GLOBAL") == sorted(["BRK-B", "VOD.L", "7203.T", "PETR4.SA"])
    assert codeserver.tradable_universe("US") == ["BRK-B"]
    assert codeserver.tradable_universe("DEVELOPED") == sorted(["BRK-B", "VOD.L", "7203.T"])
    assert codeserver.tradable_universe("EMERGING") == ["PETR4.SA"]
    with pytest.raises(ValueError):
        codeserver.tradable_universe("MARS")


def test_missing_fx_drops_only_that_currency_and_reports_it(monkeypatch):
    from api.quant import data as qdata
    idx = pd.bdate_range("2024-01-01", periods=10)
    px = pd.DataFrame({"VOD.L": 100.0, "PETR4.SA": 30.0}, index=idx)
    fx = pd.DataFrame({"GBP=X": 0.8}, index=idx)
    monkeypatch.setattr(qdata, "panel", lambda syms, start=None, end=None, fill=True: (
        {k: fx[[s for s in syms if s in fx]] for k in ("close", "open", "high", "low", "volume")}, [s for s in syms if s not in fx]))
    inst = {"VOD.L": {"currency": "GBP", "quote_currency": "GBp", "unit_divisor": 100.0, "fx_ticker": "GBP=X"},
            "PETR4.SA": {"currency": "BRL", "quote_currency": "BRL", "unit_divisor": 1.0, "fx_ticker": "BRL=X"}}
    pan = {k: px.copy() for k in ("close", "open", "high", "low", "volume")}
    out, info = codeserver._to_account_currency(pan, list(px.columns), inst, "2024-01-01", None)
    assert info["dropped_no_fx"] == ["PETR4.SA"] and info["missing_fx"] == ["BRL"]
    assert out["close"]["VOD.L"].iloc[-1] == pytest.approx(1 / 0.8)                   # 100p = £1 = $1.25


def test_scrub_is_causal_and_accepts_only_plausible_new_levels():
    x = np.array([10, 10.2, 1.0, 10.1, 10.3] + [10.0] * 3, float)               # isolated 10× print
    assert codeserver._scrub(x, 4.0).tolist() == [False, False, True] + [False] * 5
    redenom = np.array([100.0, 101, 1.0, 1.01, 1.0, 1.02, 1.01, 1.0], float)    # genuine 100→1 level change
    bad = codeserver._scrub(redenom, 4.0)
    assert bad[2:6].all() and not bad[6:].any()                                   # accepted after 5 agreeing bars
    garbage = np.array([1500.0, 1510] + [2.8e10] * 8, float)                     # 18-million-× "level"
    assert codeserver._scrub(garbage, 4.0)[2:].all()                              # never accepted
    for n in range(3, len(x)):                                                    # prefix-stable: no look-ahead
        assert codeserver._scrub(x[:n], 4.0).tolist() == codeserver._scrub(x, 4.0)[:n].tolist()


def test_minor_unit_switches_are_rescaled_not_dropped():
    idx = pd.bdate_range("2024-01-01", periods=6)
    agorot = pd.Series([4700.0, 4710, 47.2, 47.3, 4730, 4740], index=idx)       # ILA quotes switching to ILS
    pan = {f: pd.DataFrame({"X.TA": agorot}) for f in ("close", "open", "high", "low")}
    fixed = codeserver._rescale_minor_units(pan, ["X.TA"])
    assert fixed == {"X.TA": 2}
    np.testing.assert_allclose(pan["close"]["X.TA"].to_numpy(), [4700, 4710, 4720, 4730, 4730, 4740])
