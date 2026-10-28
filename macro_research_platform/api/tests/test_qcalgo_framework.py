"""QuantConnect Algorithm Framework, consolidators and the object store on the event engine (api/quant/qcalgo.py)."""
import numpy as np
import pandas as pd
import pytest

from api.quant import qcalgo, sandbox
from api.tests.test_qcalgo import _data, _run


FRAMEWORK = '''
from AlgorithmImports import *

class F(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2019, 6, 3)
        self.set_cash(100000)
        self.set_universe_selection(ManualUniverseSelectionModel([Symbol.create("AAA", SecurityType.EQUITY, Market.USA),
                                                                 Symbol.create("BBB", SecurityType.EQUITY, Market.USA)]))
        self.set_alpha(ConstantAlphaModel(InsightType.PRICE, InsightDirection.UP, timedelta(days=5)))
        self.set_portfolio_construction(EqualWeightingPortfolioConstructionModel())
        self.set_execution(ImmediateExecutionModel())
        self.set_risk_management(NullRiskManagementModel())
'''


def test_static_header_reads_manual_universe_symbols():
    h = qcalgo.static_header(FRAMEWORK)
    assert h["universe"] == ["AAA", "BBB"]
    assert not [r for r in h["report"] if r["level"] == "unsupported"]
    assert sandbox.check(FRAMEWORK)["universe"] == ["AAA", "BBB"]


def test_constant_alpha_equal_weight_holds_both_halves():
    res, algo = _run(FRAMEWORK, _data())
    assert algo._ql_framework.count > 0
    tpv = algo.portfolio.total_portfolio_value
    for t in ("AAA", "BBB"):
        h = algo.portfolio[t]
        assert h.quantity > 0 and 0.4 < h.holdings_value / tpv < 0.52
    rep = res["execution"]["algorithm"]["framework"]
    assert rep["insights"] > 0 and "EqualWeightingPortfolioConstructionModel" in rep["models"]


def test_custom_alpha_and_pcm_with_pascal_case_methods_and_long_only_bias():
    code = '''
class Down(AlphaModel):
    def Update(self, algorithm, data):
        return [Insight.price(s, timedelta(days=3), InsightDirection.DOWN) for s in data.keys()]

class F(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2019, 6, 3)
        self.add_equity("AAA")
        self.add_alpha(Down())
        self.set_portfolio_construction(EqualWeightingPortfolioConstructionModel(portfolio_bias=PortfolioBias.LONG))
'''
    res, algo = _run(code, _data())
    assert algo._ql_framework.count > 0 and not algo.portfolio["AAA"].invested     # DOWN insights, long-only: no position


def test_drawdown_risk_model_flattens_a_losing_position():
    n = 320
    idx = pd.bdate_range("2019-01-01", periods=n)
    px = np.r_[np.full(160, 100.0), np.linspace(100, 60, n - 160)]          # a steady 40% fall after the start
    close = pd.DataFrame({"AAA": px}, index=idx)
    from api.quant import codelab
    data = codelab.Data(close, close, close * 1.001, close * 0.999, pd.DataFrame(5e6, index=idx, columns=["AAA"]))
    code = '''
class F(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2019, 6, 3)
        self.add_equity("AAA")
        self.set_alpha(ConstantAlphaModel(InsightType.PRICE, InsightDirection.UP, timedelta(days=400)))
        self.set_portfolio_construction(EqualWeightingPortfolioConstructionModel(rebalance=None))
        self.add_risk_management(MaximumDrawdownPercentPerSecurity(0.10))
'''
    res, algo = _run(code, data)
    assert res["execution"]["algorithm"]["orders"] >= 2, "bought on the UP insight, then sold on the stop"
    assert not algo.portfolio["AAA"].invested, "the 10% stop flattened it"


def test_weekly_consolidator_builds_week_bars_and_feeds_an_indicator():
    code = '''
class F(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2019, 6, 3)
        self.a = self.add_equity("AAA").symbol
        self.weeks = []
        self.consolidate(self.a, Calendar.WEEKLY, self.on_week)
        self.wsma = SimpleMovingAverage(4)
        self.register_indicator(self.a, self.wsma, Calendar.WEEKLY)
    def on_week(self, bar):
        self.weeks.append((bar.time, bar.end_time, bar.open, bar.high, bar.low, bar.close))
'''
    data = _data()
    res, algo = _run(code, data)
    assert len(algo.weeks) > 20
    t0, t1, o, hi, lo, c = algo.weeks[5]
    week = data.close.loc[t0:t1, "AAA"]
    assert pd.Timestamp(t0).isocalendar()[1] == pd.Timestamp(t1).isocalendar()[1]          # one calendar week
    assert abs(c - week.iloc[-1]) < 1e-9 and abs(hi - data.high.loc[t0:t1, "AAA"].max()) < 1e-9
    assert algo.wsma.is_ready and algo.wsma.samples == len(algo.weeks)


def test_intraday_consolidation_is_refused_with_a_reason():
    with pytest.raises(NotImplementedError, match="intraday"):
        qcalgo.TradeBarConsolidator(qcalgo.timedelta(minutes=30))


def test_object_store_round_trip_and_final_report():
    qcalgo.OBJECT_STORE_SEED.clear()
    qcalgo.OBJECT_STORE_SEED["F"] = {"runs": "2"}
    code = '''
class F(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2019, 6, 3)
        self.add_equity("AAA")
        n = int(self.object_store.read("runs")) if self.object_store.contains_key("runs") else 0
        self.object_store.save("runs", str(n + 1))
        self.object_store.save_json("cfg", {"lookback": 20})
        self.object_store.save_bytes("blob", b"abc")
        self.seen = self.object_store.read_json("cfg")["lookback"], self.object_store.read_bytes("blob")
'''
    res, algo = _run(code, _data())
    assert algo.seen == (20, b"abc")
    store = res["execution"]["algorithm"]["object_store"]
    assert store["class"] == "F" and store["data"]["runs"] == "3"
    qcalgo.OBJECT_STORE_SEED.clear()
