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
