"""Tickers the static reader cannot follow are found by running initialize() (in the sandbox on the server, in the engine
where the code already runs); selectors see today's sector as a Morningstar sector code."""
import numpy as np
import pandas as pd

from api.quant import codelab, qcalgo, sandbox
from api.tests.test_qcalgo import _data

ALGO = '''
from AlgorithmImports import *

BENCH = "SPY"
SECTORS = {"XLK": "tech", "XLF": "financials"}

def pick(funds, code):
    return [f.symbol for f in funds if f.asset_classification.morningstar_sector_code == code]

class TacticalRSStrategy(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2019, 6, 3)
        self.bench = self.add_equity(BENCH).symbol                 # a module constant: not readable statically
        self.extra = [self.add_equity(t).symbol for t in ["AAA"] + list(SECTORS)]   # a comprehension over an expression
        self.add_universe(self.select)
        self.schedule.on(self.date_rules.every_day(), self.time_rules.at(10, 0), self.noop)
        self.chosen = []
    def select(self, funds):
        out = pick(funds, MorningstarSectorCode.TECHNOLOGY)
        self.chosen = [str(s) for s in out]
        return out
    def noop(self):
        pass
'''


def test_static_header_flags_then_discovery_resolves():
    h = qcalgo.static_header(ALGO)
    assert qcalgo.needs_discovery(h)
    st = codelab.load_strategy(ALGO)                         # where code runs (browser / sandbox): discovery inline
    assert {"SPY", "AAA", "XLK", "XLF"} <= set(st["qc"]["universe"])
    assert not [r for r in st["qc"]["report"] if r["level"] == "unsupported"]
    assert any("resolved by running initialize()" in r["message"] for r in st["qc"]["report"])


def test_server_check_discovers_in_the_sandbox():
    sandbox._DISCOVERED.clear()
    h = sandbox.check(ALGO)
    assert {"SPY", "AAA", "XLK", "XLF"} <= set(h["universe"])
    assert h["qc"].get("discovered")


def test_selector_sees_morningstar_sector_codes():
    d = _data(tickers=("AAA", "BBB", "CCC"))
    d.instruments = {"AAA": {"sector": "Technology"}, "BBB": {"sector": "Financial Services"},
                     "CCC": {"sector": "Information Technology"}}
    code = '''
class A(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2019, 6, 3)
        self.add_universe(self.select)
        self.seen = []
    def select(self, funds):
        self.seen = sorted((str(f.symbol), f.asset_classification.morningstar_sector_code) for f in funds)
        return []
'''
    st = codelab.load_strategy(code)
    codelab.backtest(None, d, {"capital": 100_000}, "2019-06-03", on_bar=st["on_bar"])
    algo = st["on_bar"].state["algo"]
    assert algo.seen == [("AAA", 311.0), ("BBB", 103.0), ("CCC", 311.0)]
    rep = qcalgo.static_header(code.replace("return []", "return [f.symbol for f in funds if f.AssetClassification.MorningstarSectorCode == 311]"))
    assert not [r for r in rep["report"] if r["level"] == "unsupported"]
