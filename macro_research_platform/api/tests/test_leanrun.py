"""Real-LEAN runs (api/quant/leanrun.py): data written in LEAN's format; a smoke backtest on the official image (skipped
when Docker or the image is not available — it is ~40 GB)."""
import zipfile

import pandas as pd
import pytest

from api.quant import leanrun


def test_lean_ticker_mapping():
    assert leanrun.lean_ticker("SPY") == "spy" and leanrun.lean_ticker("BRK-B") == "brk.b"
    assert leanrun.lean_ticker("7203.T") is None and leanrun.lean_ticker("EURUSD=X") is None


def test_daily_files_in_lean_format(tmp_path):
    idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
    fr = pd.DataFrame({"open": [100.0, 101.0], "high": [102.0, 103.5], "low": [99.5, 100.25], "close": [101.0, 103.0],
                       "volume": [1000, 2000]}, index=idx)
    assert leanrun.write_daily(tmp_path, "abc", fr) == 2
    with zipfile.ZipFile(tmp_path / "equity/usa/daily/abc.zip") as z:
        rows = z.read("abc.csv").decode().splitlines()
    assert rows[0] == "20240102 00:00,1000000,1020000,995000,1010000,1000"
    assert (tmp_path / "equity/usa/map_files/abc.csv").read_text().strip().endswith("20501231,abc")
    assert (tmp_path / "equity/usa/factor_files/abc.csv").read_text().startswith("20231223,1,1,1")


@pytest.mark.network
@pytest.mark.skipif(not leanrun.status(refresh=True)["available"], reason="Docker or the LEAN image is not available")
def test_real_lean_smoke_run():
    code = '''from AlgorithmImports import *
class LeanSmoke(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2023, 1, 1)
        self.set_end_date(2023, 12, 31)
        self.set_cash(100000)
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
    def on_data(self, data):
        if not self.portfolio.invested:
            self.set_holdings(self.spy, 1.0)
'''
    r = leanrun.run(code, timeout=600)
    assert r["engine"].startswith("QuantConnect LEAN") and int(r["statistics"]["Total Orders"]) >= 1
    assert r["equity_curve"] and not r["runtime_errors"]


def test_classify_and_crypto_forex_files(tmp_path):
    assert leanrun.classify("BTC-USD") == ("crypto", ("BTC", "USD"))
    assert leanrun.classify("EURUSD=X") == ("forex", "EURUSD")
    assert leanrun.classify("SPY") == ("equity", "spy") and leanrun.classify("7203.T") == (None, None)
    idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
    fr = pd.DataFrame({"open": [42000.5, 43000.0], "high": [43500.0, 44000.0], "low": [41000.0, 42500.0],
                       "close": [43000.0, 43800.25], "volume": [123.5, 98.0]}, index=idx)
    pairs = leanrun.write_crypto(tmp_path, "BTC", "USD", fr)
    assert pairs[0] == "btcusd" and "btcusdt" in pairs
    with zipfile.ZipFile(tmp_path / "crypto/binance/daily/btcusdt_trade.zip") as z:
        assert z.read("btcusdt.csv").decode().splitlines()[0] == "20240102 00:00,42000.5,43500,41000,43000,123.5"
    with zipfile.ZipFile(tmp_path / "crypto/coinbase/daily/btcusd_quote.zip") as z:
        assert z.read("btcusd.csv").decode().splitlines()[1] == "20240103 00:00,43000,44000,42500,43800.25,0,43000,44000,42500,43800.25,0"
    leanrun.write_forex(tmp_path, "EURUSD", fr / 40000)
    assert (tmp_path / "forex/oanda/daily/eurusd.zip").exists() and (tmp_path / "forex/fxcm/daily/eurusd.zip").exists()


@pytest.mark.network
@pytest.mark.skipif(not leanrun.status(refresh=True)["available"], reason="Docker or the LEAN image is not available")
def test_real_lean_crypto_on_a_named_venue():
    code = '''from AlgorithmImports import *
class C(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2023, 1, 1)
        self.SetEndDate(2023, 12, 31)
        self.SetCash(10000)
        self.SetBrokerageModel(BrokerageName.COINBASE, AccountType.CASH)
        self.btc = self.AddCrypto("BTCUSD", Resolution.Daily, Market.COINBASE).Symbol
    def OnData(self, data):
        if not self.Portfolio.Invested:
            self.SetHoldings(self.btc, 0.5)
'''
    r = leanrun.run(code, timeout=600)
    assert int(r["statistics"]["Total Orders"]) >= 1 and not r["runtime_errors"]


LEAN_UP = pytest.mark.skipif(not leanrun.status(refresh=True)["available"], reason="Docker or the LEAN image is not available")


def test_security_identifiers_match_lean():
    """The same encoding as LEAN's own sample coarse files (AAPL / A / AAL)."""
    assert leanrun.sid("aapl", pd.Timestamp("1998-01-02")) == "AAPL R735QTJ8XC9X"
    assert leanrun.sid("a", pd.Timestamp("1999-11-18")) == "A RPTMYV3VC57P"
    assert leanrun.sid("aal", pd.Timestamp("2013-12-09")) == "AAL VM9RIYHM8ACL"


def _frames():
    idx = pd.bdate_range("2024-01-01", periods=5)
    mk = lambda px, v: pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": v}, index=idx)
    return idx, {"AAA": mk([10.0, 11, 12, 13, 14], [100] * 5), "BBB": mk([20.0] * 5, [300] * 5)}


def test_universe_files_in_lean_format(tmp_path):
    idx, frames = _frames()
    members = pd.DataFrame({"AAA": [True] * 5, "BBB": [False, False, True, True, True]}, index=idx)
    info = leanrun.write_universe(tmp_path, frames, members, "2024-01-01")
    assert info["days"] == 5
    a_sid = leanrun.sid("aaa", leanrun.first_date(idx))
    rows = (tmp_path / "equity/usa/fundamental/coarse/20240101.csv").read_text().splitlines()
    assert rows == [f"{a_sid},AAA,10,100,1000,True,1,1"]                 # BBB not a member yet: absent (point in time)
    etf = (tmp_path / "equity/usa/universes/etf/spy/20240103.csv").read_text().splitlines()
    assert len(etf) == 2 and etf[0].startswith(f"AAA,{a_sid},20240103,")
    assert abs(sum(float(r.split(",")[3]) for r in etf) - 1) < 1e-6
    fund = leanrun.write_fundamentals(tmp_path, frames, {"AAA": {"sector": "Information Technology"}}, members,
                                      "2024-01-01", sec=False)
    lines = (tmp_path / "equity/usa/fundamental/free/20240101.csv").read_text().splitlines()
    assert lines[0].startswith("sid,AssetClassification_MorningstarSectorCode") and lines[1] == f"{a_sid},311"
    assert fund["days"] == 5


def test_morningstar_fields_used_and_unsupplied():
    f = leanrun.fine_fields("x = f.ValuationRatios.PERatio + f.earning_reports.basic_eps.twelve_months "
                            "+ f.OperationRatios.RevenueGrowth.OneYear + f.asset_classification.morningstar_sector_code")
    assert "valuation_ratios.pe_ratio" in f["used"] and f["unsupplied"] == ["operation_ratios.revenue_growth.one_year"]


def test_daily_wrapper_sorts_last_and_parses():
    """LEAN's Python loader takes the last QCAlgorithm subclass of main.py in name order — the wrapper must be it."""
    import ast
    src = "class ZetaAlgo:\n    pass\n" + leanrun.daily_wrapper("ZetaAlgo")
    tree = ast.parse(src)
    names = sorted(n.name for n in tree.body if isinstance(n, ast.ClassDef))
    assert names[-1] == "zzQuantLabDaily"
    body = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "zzQuantLabDaily").body
    assigned = {t.id for b in body if isinstance(b, ast.Assign) for t in b.targets}
    assert {"add_equity", "AddEquity", "history", "History", "SMA", "set_warm_up"} <= assigned


def test_custom_prelude_and_fetch_refusals():
    import ast
    ast.parse(leanrun.custom_prelude({"https://example.com/a.csv": "/Lean/Data/qlcustom/x.csv"}))
    for bad in ("file:///etc/passwd", "ftp://example.com/x.csv", "http://127.0.0.1/x.csv", "http://10.0.0.5/x.csv",
                "http://169.254.169.254/latest/meta-data"):
        with pytest.raises(leanrun.LeanError):
            leanrun.fetch_source(bad)


def test_custom_sources_found_by_running_get_source_in_the_sandbox():
    from api.quant import sandbox
    code = '''from AlgorithmImports import *
class Monthly(PythonData):
    def get_source(self, config, date, is_live):
        return SubscriptionDataSource(f"https://example.com/{config.symbol.value}/{date:%Y%m}.csv",
                                      SubscriptionTransportMedium.REMOTE_FILE)
class A(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2020, 1, 1)
        self.SetEndDate(2020, 3, 15)
        self.AddData(Monthly, "XYZ", Resolution.Daily)
'''
    sandbox._DISCOVERED.clear()
    srcs = leanrun.custom_sources(code)
    assert [s["url"] for s in srcs] == [f"https://example.com/XYZ/2020{m:02d}.csv" for m in (1, 2, 3)]
    with pytest.raises(leanrun.LeanError, match="no get_source"):
        leanrun.custom_sources(code.replace("    def get_source(self, config, date, is_live):\n        return SubscriptionDataSource(f\"https://example.com/{config.symbol.value}/{date:%Y%m}.csv\",\n                                      SubscriptionTransportMedium.REMOTE_FILE)\n", "    pass\n"))


@pytest.mark.network
@LEAN_UP
def test_real_lean_minute_default_is_served_as_daily():
    """add_equity("SPY") with no resolution is minute in LEAN; free data is daily — the wrapper maps it and says so."""
    code = '''from AlgorithmImports import *
class NoRes(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2023, 1, 1)
        self.SetEndDate(2023, 6, 30)
        self.spy = self.AddEquity("SPY").Symbol
        self.fast = self.SMA(self.spy, 5, Resolution.Minute)
    def OnData(self, data):
        if self.fast.IsReady and not self.Portfolio.Invested:
            self.SetHoldings(self.spy, 1)
'''
    r = leanrun.run(code, timeout=600)
    assert int(r["statistics"]["Total Orders"]) >= 1 and not r["runtime_errors"]
    assert any("served as daily" in n for n in r["data"]["notes"])


@pytest.mark.network
@LEAN_UP
def test_real_lean_fundamental_universe_with_free_fundamentals():
    code = '''from AlgorithmImports import *
class MegaCaps(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2022, 3, 31)
        self.add_universe(self.select)
        self.month = -1
        self.seen = 0
    def select(self, fundamental):
        if self.time.month == self.month:
            return Universe.UNCHANGED
        self.month = self.time.month
        top = sorted([f for f in fundamental if f.has_fundamental_data and f.valuation_ratios.pe_ratio > 0
                      and f.asset_classification.morningstar_sector_code == MorningstarSectorCode.TECHNOLOGY],
                     key=lambda f: f.market_cap, reverse=True)[:5]
        self.seen = len(top)
        return [f.symbol for f in top]
    def on_data(self, data):
        for s in self.active_securities.keys():
            if s.value != "SPY" and data.contains_key(s) and not self.portfolio[s].invested:
                self.set_holdings(s, 0.2)
'''
    r = leanrun.run(code, timeout=1500)
    assert int(r["statistics"]["Total Orders"]) >= 5 and not r["runtime_errors"]
    assert r["data"]["universe"]["fundamentals"]["days"] > 0


@pytest.mark.network
@LEAN_UP
def test_real_lean_custom_data_from_get_source():
    """The algorithm's own get_source URL is fetched by the platform and its own reader runs on it inside LEAN."""
    from api.quant import sandbox
    code = '''from AlgorithmImports import *
class Vix(PythonData):
    def GetSource(self, config, date, isLive):
        return SubscriptionDataSource("https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
                                      SubscriptionTransportMedium.RemoteFile)
    def Reader(self, config, line, date, isLive):
        if not (line.strip() and line[0].isdigit()):
            return None
        c = line.split(",")
        x = Vix()
        x.Symbol = config.Symbol
        x.Time = datetime.strptime(c[0], "%m/%d/%Y")
        x.EndTime = x.Time + timedelta(days=1)
        x.Value = float(c[4])
        return x
class VixTiming(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2020, 1, 1)
        self.SetEndDate(2021, 12, 31)
        self.spy = self.AddEquity("SPY", Resolution.Daily).Symbol
        self.vix = self.AddData(Vix, "VIX", Resolution.Daily).Symbol
        self.last = None
    def OnData(self, data):
        if data.ContainsKey(self.vix):
            self.last = data[self.vix].Value
        if self.last is None or not data.ContainsKey(self.spy):
            return
        if self.last < 25 and not self.Portfolio.Invested:
            self.SetHoldings(self.spy, 1)
        elif self.last > 35 and self.Portfolio.Invested:
            self.Liquidate()
'''
    sandbox._DISCOVERED.clear()
    r = leanrun.run(code, timeout=900)
    assert int(r["statistics"]["Total Orders"]) >= 3 and not r["runtime_errors"]    # in and out around March 2020


@pytest.mark.network
def test_crypto_volume_is_in_units_of_the_asset():
    """Yahoo's BTC-USD volume is dollars; the loader converts it to BTC so traded value (close × volume), impact,
    capacity and LEAN's bars are right — not inflated by the price."""
    from api.quant import codeserver
    d = codeserver.load_data(["BTC-USD", "SPY"], "2024-01-01", allow_missing=True)
    btc = d.volume["BTC-USD"].dropna()
    assert 1e3 < btc.median() < 1e7                     # coins per day, not ~$3e10
    assert (d.close["BTC-USD"] * d.volume["BTC-USD"]).dropna().median() > 1e9          # ≈ dollars traded
