"""Any account currency, any listing: FX conversion through USD crosses, cash rates by currency (as-of only),
country / region / combined tradable universes, the header, and the sandbox carrying instrument metadata."""
import numpy as np
import pandas as pd
import pytest

from api.quant import codelab as cl
from api.quant import codeserver, rates, sandbox


def _fake_panel(frames):
    """qdata.panel stand-in serving {ticker: series} for whatever is asked."""
    def panel(syms, start=None, end=None, fill=True):
        have = [s for s in syms if s in frames]
        df = pd.DataFrame({s: frames[s] for s in have})
        return ({k: df.copy() for k in ("close", "open", "high", "low")} | {"volume": df * 0 + 1e6}, [s for s in syms if s not in frames])
    return panel


def test_any_listing_converts_into_any_account_currency(monkeypatch):
    from api.quant import data as qdata
    idx = pd.bdate_range("2024-01-01", periods=30)
    gbp_x = pd.Series(np.r_[[0.80] * 15, [0.75] * 15], index=idx)            # £ per $1
    eur_x = pd.Series(0.90, index=idx)                                           # € per $1
    monkeypatch.setattr(qdata, "panel", _fake_panel({"GBP=X": gbp_x, "EUR=X": eur_x}))
    px = pd.DataFrame({"HSBA.L": 100.0, "AAPL": 200.0, "SAP.DE": 150.0}, index=idx)
    pan = {k: px.copy() for k in ("close", "open", "high", "low", "volume")}
    inst = {"HSBA.L": {"currency": "GBP", "quote_currency": "GBp", "unit_divisor": 100.0, "fx_ticker": "GBP=X"},
            "AAPL": {"currency": "USD", "quote_currency": "USD", "unit_divisor": 1.0, "fx_ticker": None},
            "SAP.DE": {"currency": "EUR", "quote_currency": "EUR", "unit_divisor": 1.0, "fx_ticker": "EUR=X"}}
    out, info, usd_per_unit = codeserver._to_account_currency(pan, list(px.columns), inst, "2024-01-01", None, "EUR")
    assert out["close"]["HSBA.L"].iloc[0] == pytest.approx(1.0 * 0.90 / 0.80)          # 100p = £1 → €1.125
    assert out["close"]["HSBA.L"].iloc[20] == pytest.approx(0.90 / 0.75)
    assert out["open"]["HSBA.L"].iloc[15] == pytest.approx(0.90 / 0.80)                # open: previous FX closes
    assert out["close"]["AAPL"].iloc[0] == pytest.approx(200 * 0.90)                    # $200 → €180
    assert (out["close"]["SAP.DE"] == 150.0).all()                                      # already in EUR: untouched
    assert "SAP.DE" not in info["pairs"] and info["account_currency"] == "EUR"
    assert usd_per_unit.iloc[0] == pytest.approx(1 / 0.90)


def test_missing_account_fx_is_an_error_not_a_silent_usd_account(monkeypatch):
    from api.quant import data as qdata
    idx = pd.bdate_range("2024-01-01", periods=5)
    monkeypatch.setattr(qdata, "panel", _fake_panel({}))
    pan = {k: pd.DataFrame({"AAPL": 1.0}, index=idx) for k in ("close", "open", "high", "low", "volume")}
    inst = {"AAPL": {"currency": "USD", "quote_currency": "USD", "unit_divisor": 1.0, "fx_ticker": None}}
    with pytest.raises(ValueError, match="account currency"):
        codeserver._to_account_currency(pan, ["AAPL"], inst, "2024-01-01", None, "JPY")


def test_spread_model_is_the_same_in_any_account_currency():
    idx = pd.bdate_range("2023-01-02", periods=120)
    rng = np.random.default_rng(3)
    usd = pd.DataFrame({"X": 50 * np.cumprod(1 + rng.normal(0, 0.01, 120))}, index=idx)
    vol = pd.DataFrame({"X": 2e5}, index=idx)
    a = cl.half_spread_bps(usd, vol)
    b = cl.half_spread_bps(usd * 150.0, vol, usd_per_unit=pd.Series(1 / 150.0, index=idx))   # the same stock, in yen
    pd.testing.assert_frame_equal(a, b)


def test_account_currency_cash_rate_is_as_of_and_spliced(monkeypatch):
    oecd = pd.Series([2.0, 3.0], index=pd.to_datetime(["2020-01-01", "2020-02-01"]))     # monthly averages
    estr = pd.Series([4.0, 4.1], index=pd.to_datetime(["2020-02-28", "2020-03-31"]))     # daily fixings
    monkeypatch.setattr(rates, "_fred", lambda sid: oecd if sid.startswith("IR3TIB01") else estr)
    rates._cache.pop(("ccy", "EUR"), None)
    d = rates.daily(["2020-02-14", "2020-02-17", "2020-03-16", "2020-04-01"], "EUR") * 252 * 100
    assert d.iloc[0] == 0.0                                    # January's average is not known until 15 February
    assert d.iloc[1] == pytest.approx(2.0)                     # …then it is
    assert d.iloc[2] == pytest.approx(3.0)                     # February's from 15 March; €STR only extends after it
    assert d.iloc[3] == pytest.approx(4.1)                     # 31 March fixing, usable 1 April
    rates._cache.pop(("ccy", "EUR"), None)


def test_pegged_and_unknown_currencies(monkeypatch):
    irx = pd.Series(5.0, index=pd.bdate_range("2019-01-01", periods=400))
    monkeypatch.setattr(rates, "_irx", lambda: irx)
    for c in ("HKD", "TWD"):
        rates._cache.pop(("ccy", c), None)
    assert rates.describe("HKD")["kind"] == "proxy" and rates.daily(["2020-01-02"], "HKD").iloc[0] == pytest.approx(0.05 / 252)
    assert rates.known("TWD") is False and rates.daily(["2020-01-02"], "TWD").iloc[0] == 0.0


@pytest.fixture()
def universe(monkeypatch):
    from api import global_universe
    stocks = [{"symbol": "AAPL", "listing_country": "US", "currency": "USD", "market_class": "Developed", "region": "Americas", "traded_usd": 9e9},
              {"symbol": "7203.T", "listing_country": "JP", "currency": "JPY", "market_class": "Developed", "region": "Asia-Pacific", "traded_usd": 3e8},
              {"symbol": "0700.HK", "listing_country": "HK", "currency": "HKD", "market_class": "Developed", "region": "Asia-Pacific", "traded_usd": 2e9},
              {"symbol": "VOD.L", "listing_country": "GB", "currency": "GBp", "market_class": "Developed", "region": "Europe", "traded_usd": 1e8}]
    monkeypatch.setattr(global_universe, "load", lambda **k: {"stocks": stocks})


def test_country_region_and_combined_universes(universe):
    assert codeserver.tradable_universe("JP") == ["7203.T"]
    assert codeserver.tradable_universe("JP+HK") == ["0700.HK", "7203.T"]
    assert codeserver.tradable_universe(["hk", "jp"]) == ["0700.HK", "7203.T"]
    assert codeserver.tradable_universe("ASIA_PACIFIC") == ["0700.HK", "7203.T"]
    assert codeserver.tradable_universe("EUROPE+US") == ["AAPL", "VOD.L"]
    with pytest.raises(ValueError, match="not known"):
        codeserver.tradable_universe("ATLANTIS")
    with pytest.raises(ValueError, match="no stocks"):
        codeserver.tradable_universe("NZ")
    with pytest.raises(ValueError, match="cannot be combined"):
        codeserver.tradable_universe("SP500_PIT+JP")


def test_header_account_currency_and_long_lists():
    body = '\ndef strategy(data):\n    return data.close * 0\n'
    h = sandbox.check('UNIVERSE = ["7203.T"]\nTRADABLE_UNIVERSE = ["jp", "hk"]\nACCOUNT_CURRENCY = "jpy"' + body)
    assert h["account"] == "JPY" and h["tradable"] == "HK+JP"
    assert sandbox.check('UNIVERSE = ["SPY"]' + body)["account"] == "USD"
    with pytest.raises(sandbox.SandboxError, match="not supported"):
        sandbox.check('UNIVERSE = ["SPY"]\nACCOUNT_CURRENCY = "XYZ"' + body)
    many = "UNIVERSE = [" + ", ".join(f'"S{i}"' for i in range(300)) + "]"
    assert len(sandbox.check(many + body)["universe"]) == 300                    # > UNIVERSE_LIMIT: a server job
    st = cl.load_strategy('UNIVERSE = ["SPY"]\nACCOUNT_CURRENCY = "eur"\nTRADABLE_UNIVERSE = "jp+hk"' + body)
    assert st["account"] == "EUR" and st["tradable"] == "HK+JP"


def test_exposure_breakdown_by_currency_country_sector():
    inst = {"A": {"currency": "JPY", "country": "JP", "sector": "Tech"}, "B": {"currency": "JPY", "country": "JP", "sector": "Banks"},
            "C": {"currency": "USD", "country": "US", "sector": "Tech"}}
    e = cl.exposure_breakdown({"A": 0.3, "B": 0.2, "C": -0.1}, inst)
    assert e["currency"] == {"JPY": 0.5, "USD": -0.1} and e["sector"] == {"Tech": 0.2, "Banks": 0.2}


def test_data_info_frame():
    idx = pd.bdate_range("2024-01-01", periods=3)
    px = pd.DataFrame({"A": 1.0, "B": 2.0}, index=idx)
    d = cl.Data(px, px, px, px, px * 0 + 1, instruments={"A": {"country": "JP", "sector": "Tech"}}, account_currency="JPY")
    assert d.info.loc["A", "sector"] == "Tech" and d.info.loc["B", "country"] == "US" and d.account_currency == "JPY"


def test_sandbox_charges_venue_taxes_and_reports_the_account_currency(monkeypatch):
    """Regression: the sandbox child used to drop instrument metadata, so stamp duty was never charged there."""
    idx = pd.bdate_range("2014-01-01", periods=900)
    px = pd.DataFrame({"VOD.L": np.linspace(1.0, 1.2, 900), "SPY": np.linspace(100, 150, 900)}, index=idx)
    vol = px * 0 + 1e7
    inst = {"VOD.L": {"country": "GB", "currency": "GBP", "sec_fee": False, "tax_buy_bps": 50.0, "tax_sell_bps": 0.0},
            "SPY": {"country": "US", "currency": "USD", "sec_fee": True}}
    d = cl.Data(px, px, px, px, vol, instruments=inst, account_currency="GBP",
                usd_per_unit=pd.Series(1.25, index=idx), provenance={"account_currency": "GBP"})
    monkeypatch.setattr(codeserver, "load_data", lambda u, s, end=None, **kw: d)
    monkeypatch.setattr(codeserver, "benchmark_series", lambda sym, start, account="USD": px["SPY"])
    code = ('UNIVERSE = ["VOD.L", "SPY"]\nSTART = "2015-01-01"\nACCOUNT_CURRENCY = "GBP"\n'
            'def strategy(data):\n    w = data.close * 0\n    w["VOD.L"] = 1.0\n    return hold_monthly(w)\n')
    res = sandbox.run(code, {"commission_bps": 0.0, "spread_mult": 0.0, "impact_coef_bps": 0.0})
    assert res["costs"]["fees"] > 0                                               # 0.5% stamp duty on the purchase
    assert res["account_currency"] == "GBP" and res["exposure"]["currency"] == {"GBP": pytest.approx(1.0, abs=0.01)}


def test_paper_book_adds_currencies_up_in_usd(monkeypatch, tmp_path):
    from api.quant import trader
    monkeypatch.setattr(trader, "DISK", tmp_path)                 # an empty result cache
    monkeypatch.setattr(trader, "FREEZE", False)                  # no writes to the app's paper record
    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2024-01-01", periods=40)]
    monkeypatch.setattr(trader, "eval_code_spec", lambda spec, light=False: {
        "dates": dates, "returns": [0.0] * 40, "weights_last": {"7203.T": 1.0},
        "provenance": {"account_currency": "JPY"}})
    usd = pd.Series(np.r_[[1 / 150] * 20, [1 / 140] * 20], index=pd.to_datetime(dates))   # the yen strengthens
    monkeypatch.setattr(codeserver, "usd_per", lambda ccy, ds: usd.reindex(pd.to_datetime(list(ds))))
    dep = {"id": 1, "name": "jp", "strategy_id": None, "owner": "a", "deployed_at": dates[5], "capital": 150_000_000.0,
           "spec": {"kind": "code", "code": 'UNIVERSE = ["7203.T"]\ndef strategy(data):\n    return data.close * 0 + 1\n'}}
    row = trader._one(dep)
    assert row["currency"] == "JPY" and row["nav"] == pytest.approx(150_000_000.0)       # flat in yen
    assert row["capital_usd"] == pytest.approx(1_000_000.0)                              # ¥150m at 150
    assert row["nav_usd"] == pytest.approx(150_000_000.0 / 140)                          # worth more in dollars
    assert row["positions"][0]["usd"] == pytest.approx(150_000_000.0 / 140)


def test_fx_conversion_cost_only_on_cross_currency_trades():
    idx = pd.bdate_range("2024-01-01", periods=30)
    px = pd.DataFrame({"SAP.DE": 100.0, "AAPL": 100.0}, index=idx)
    inst = {"SAP.DE": {"country": "DE", "currency": "EUR", "sec_fee": False}, "AAPL": {"country": "US", "currency": "USD", "sec_fee": False}}
    zero = {"commission_bps": 0.0, "spread_mult": 0.0, "impact_coef_bps": 0.0, "fx_cost_bps": 10.0}
    w = pd.DataFrame(np.nan, index=idx, columns=px.columns)
    for acct, held, charged in (("EUR", "SAP.DE", False), ("EUR", "AAPL", True), ("USD", "SAP.DE", True)):
        d = cl.Data(px, px, px, px, px * 0 + 1e9, instruments=inst, account_currency=acct)
        ww = w.copy()
        ww.iloc[0] = 0.0
        ww.iloc[0, list(px.columns).index(held)] = 1.0
        fees = cl.backtest(ww, d, zero)["fees"].sum()
        assert (fees == pytest.approx(0.001 / 1.001, rel=1e-6)) if charged else fees == 0.0, (acct, held)


def test_trader_serves_cached_results_and_refreshes_in_the_background(monkeypatch, tmp_path):
    from api.quant import store, trader
    monkeypatch.setattr(trader, "DISK", tmp_path)
    monkeypatch.setattr(trader, "FREEZE", False)
    monkeypatch.setattr(trader, "_alerts", lambda *a: None)
    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2024-01-01", periods=40)]
    calls = []
    def fake(spec, light=False):
        calls.append(light)
        return {"dates": dates, "returns": [0.001] * 40, "weights_last": {f"S{i}": 0.01 for i in range(60)},
                "provenance": {"account_currency": "USD"}}
    monkeypatch.setattr(trader, "eval_code_spec", fake)
    dep = {"id": 9001, "name": "big", "strategy_id": None, "owner": "a", "deployed_at": dates[5], "capital": 1e6,
           "active": 1, "spec": {"kind": "code", "code": 'UNIVERSE = ["SPY"]\\ndef strategy(data):\\n    return data.close * 0\\n'}}
    monkeypatch.setattr(store, "list_deployments", lambda active_only=True: [dep])
    monkeypatch.setattr(trader, "book_of", lambda d: "technical")
    trader._cache.clear()
    first = trader.book(which="technical")
    assert first["pending"] == [{"id": 9001, "name": "big"}] and first["deployments"] == []   # never blocks
    for _ in range(100):                                                                       # background job
        if not trader._refreshing:
            break
        import time
        time.sleep(0.05)
    trader._cache.clear()
    second = trader.book(which="technical")
    row = second["deployments"][0]
    assert calls == [True]                                                                    # light, once
    assert len(row["positions"]) == trader.SHOW_POSITIONS and row["positions_other"]["count"] == 60 - trader.SHOW_POSITIONS
    assert second["positions_total"] == 60 and len(second["exposure"]) == trader.SHOW_EXPOSURE
    assert second["exposure_other"]["count"] == 60 - trader.SHOW_EXPOSURE



def test_live_record_is_append_only_and_revisions_are_counted(monkeypatch):
    from api.quant import store, trader
    mem = {}
    monkeypatch.setattr(store, "live_returns", lambda did: dict(mem.get(did, {})))
    monkeypatch.setattr(store, "append_live", lambda did, rows: mem.setdefault(did, {}).update({d: (a, b) for d, a, b in rows}))
    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2024-01-01", periods=10)]
    dep = {"id": 77, "deployed_at": dates[2]}
    mask = np.array([d > dep["deployed_at"] for d in dates])
    r1 = np.full(10, 0.01)
    d1, live1, _, rev1, prov1 = trader._frozen_live(dep, dates, r1, r1, mask)
    assert prov1 == dates[-1] and len(mem[77]) == 6 and rev1 == 0              # 7 live days: 6 final + 1 provisional
    r2 = r1.copy()
    r2[4] = -0.05                                                                # a data revision of a recorded day
    d2, live2, _, rev2, _ = trader._frozen_live(dep, dates, r2, r2, mask)
    assert live2[1] == pytest.approx(0.01) and rev2 == 1                         # the record keeps what was recorded


def test_code_deploy_returns_at_once_and_prepares_in_the_background(monkeypatch):
    import threading
    import time as _t
    from api.quant import codeserver, store, trader
    saved, updated = {}, {}
    gate = threading.Event()
    def slow_compute(dep):
        gate.wait(5)                                                     # a long sandbox run
        return {"daily_dates": ["2024-01-02", "2024-01-03"], "daily_returns": [0.0, 0.01], "positions": [],
                "currency": "USD", "metrics": {"cagr": 0.1, "vol": 0.2, "sharpe": 0.5, "max_drawdown": -0.1}}
    monkeypatch.setattr(trader, "_compute", slow_compute)
    monkeypatch.setattr(store, "deploy", lambda owner, name, spec, at, cap, sid, summary, book: saved.update(
        id=501, name=name, spec=spec, deployed_at=at, backtest=summary, book=book) or dict(saved))
    monkeypatch.setattr(store, "update_backtest", lambda did, s: updated.update({did: s}))
    monkeypatch.setattr(codeserver, "usd_per", lambda ccy, ds: pd.Series([1.0]))
    monkeypatch.setattr(codeserver, "_index_series", lambda sym, start: pd.Series([1.0, 2.0], index=pd.to_datetime(["2024-01-02", "2024-01-03"])))
    monkeypatch.setattr(trader, "classify", lambda spec: "technical")
    code = 'UNIVERSE = ["SPY"]\ndef strategy(data):\n    return data.close * 0 + 1\n'
    t0 = _t.time()
    d = trader.deploy("me", {"kind": "code", "name": "fast", "code": code}, 100000)
    assert _t.time() - t0 < 2 and d["preparing"] and d["backtest"]["pending"] and d["deployed_at"] == "2024-01-03"
    gate.set()
    for _ in range(100):
        if 501 in updated:
            break
        _t.sleep(0.05)
    assert updated[501]["sharpe"] == 0.5 and updated[501]["period"]["end"] == "2024-01-03"
