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
