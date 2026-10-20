"""A corpus of algorithms written the way QuantConnect users write them — old PascalCase and new snake_case APIs,
indicators, history DataFrames, universes, the Algorithm Framework, consolidators, order tickets, scheduling, the
scientific stack, the object store, custom data and non-literal set-up values. Each must import with nothing unsupported
and nothing unknown, and run to the end. A new gap in the compatibility layer shows up here as a failing case."""
import numpy as np
import pandas as pd
import pytest

from api.quant import codelab, customdata, qcalgo, sandbox
from api.tests.test_qcalgo import _data

TICKERS = ("SPY", "QQQ", "TLT", "GLD", "IEF", "XLK", "XLF", "XLE", "AAA", "BBB", "BTC-USD", "ETH-USD")

CORPUS = {
"basic_template_pascal": '''
from AlgorithmImports import *
class BasicTemplateAlgorithm(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2019, 6, 3)
        self.SetEndDate(2021, 3, 1)
        self.SetCash(100000)
        self.spy = self.AddEquity("SPY", Resolution.Minute).Symbol
    def OnData(self, data):
        if not self.Portfolio.Invested:
            self.SetHoldings(self.spy, 1)
            self.Debug("Purchased Stock")
''',

"ema_cross_snake": '''
from AlgorithmImports import *
class EmaCross(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2019, 6, 3)
        self.set_cash(50_000)
        self.symbol = self.add_equity("QQQ", Resolution.DAILY).symbol
        self.fast = self.ema(self.symbol, 20, Resolution.DAILY)
        self.slow = self.ema(self.symbol, 50, Resolution.DAILY)
        self.set_warm_up(50, Resolution.DAILY)
    def on_data(self, data: Slice):
        if self.is_warming_up or not self.slow.is_ready:
            return
        holdings = self.portfolio[self.symbol].quantity
        if holdings <= 0 and self.fast.current.value > self.slow.current.value * 1.001:
            self.set_holdings(self.symbol, 1.0)
        elif holdings > 0 and self.fast.current.value < self.slow.current.value:
            self.liquidate(self.symbol)
        self.plot("Trade", "fast", self.fast.current.value)
''',

"bollinger_rolling_window_limits": '''
from AlgorithmImports import *
class MeanReversion(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2019, 6, 3)
        self.sym = self.add_equity("TLT").symbol
        self.bb = self.bb(self.sym, 20, 2, MovingAverageType.SIMPLE, Resolution.DAILY)
        self.window = RollingWindow[TradeBar](5) if False else RollingWindow(5)
        self.tickets = []
    def on_data(self, data):
        if not data.contains_key(self.sym) or data[self.sym] is None:
            return
        bar = data[self.sym]
        self.window.add(bar)
        if not self.bb.is_ready or not self.window.is_ready:
            return
        price = self.securities[self.sym].close
        if not self.portfolio[self.sym].invested and price < self.bb.lower_band.current.value if hasattr(self.bb.lower_band, "current") else price < self.bb.lower_band.value:
            qty = self.calculate_order_quantity(self.sym, 0.5)
            self.tickets.append(self.limit_order(self.sym, qty, round(price * 0.995, 2)))
        elif self.portfolio[self.sym].invested and price > self.bb.middle_band.current.value:
            self.liquidate(self.sym)
    def on_order_event(self, order_event: OrderEvent):
        if order_event.status == OrderStatus.FILLED:
            self.log(f"{order_event.symbol} filled {order_event.fill_quantity} @ {order_event.fill_price}")
''',

"momentum_rotation_history_frames": '''
from AlgorithmImports import *
import numpy as np
class Rotation(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2019, 9, 2)
        self.SetCash(100000)
        self.tickers = ["SPY", "QQQ", "TLT", "GLD", "IEF"]
        self.symbols = [self.AddEquity(t, Resolution.Daily).Symbol for t in self.tickers]
        self.Schedule.On(self.DateRules.MonthStart("SPY"), self.TimeRules.AfterMarketOpen("SPY", 30), self.Rebalance)
    def Rebalance(self):
        hist = self.History(self.symbols, 126, Resolution.Daily)
        if hist.empty:
            return
        closes = hist["close"].unstack(level=0)
        mom = closes.iloc[-1] / closes.iloc[0] - 1
        top = mom.nlargest(2).index
        for s in self.symbols:
            if str(s) not in [str(t) for t in top]:
                self.Liquidate(s)
        for t in top:
            self.SetHoldings(t, 0.5)
''',

"coarse_universe_selection": '''
from AlgorithmImports import *
class Liquid(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2019, 6, 3)
        self.UniverseSettings.Resolution = Resolution.Daily
        self.AddUniverse(self.CoarseSelectionFunction)
        self.changes = None
    def CoarseSelectionFunction(self, coarse):
        filtered = [x for x in coarse if x.HasFundamentalData or x.Price > 10]
        ranked = sorted(filtered, key=lambda x: x.DollarVolume, reverse=True)
        return [x.Symbol for x in ranked[:3]]
    def OnSecuritiesChanged(self, changes):
        for security in changes.RemovedSecurities:
            if security.Invested if hasattr(security, "Invested") else self.Portfolio[security.Symbol].Invested:
                self.Liquidate(security.Symbol)
        for security in changes.AddedSecurities:
            self.SetHoldings(security.Symbol, 0.3)
''',

"framework_builtin_models": '''
from AlgorithmImports import *
class FrameworkAlgo(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2019, 6, 3)
        self.SetCash(100000)
        symbols = [Symbol.Create(t, SecurityType.Equity, Market.USA) for t in ["SPY", "TLT", "GLD"]]
        self.SetUniverseSelection(ManualUniverseSelectionModel(symbols))
        self.SetAlpha(RsiAlphaModel(14, Resolution.Daily))
        self.SetPortfolioConstruction(InsightWeightingPortfolioConstructionModel())
        self.AddRiskManagement(TrailingStopRiskManagementModel(0.05))
        self.SetExecution(ImmediateExecutionModel())
''',

"framework_custom_alpha": '''
from AlgorithmImports import *
class MeanReversionAlpha(AlphaModel):
    def __init__(self, lookback=20):
        self.lookback = lookback
        self.name = "MeanReversionAlpha"
    def update(self, algorithm, data):
        insights = []
        for symbol in data.keys():
            hist = algorithm.history(symbol, self.lookback)
            if len(hist) < self.lookback:
                continue
            z = (hist["close"].iloc[-1] - hist["close"].mean()) / hist["close"].std()
            if z < -1:
                insights.append(Insight.price(symbol, timedelta(days=5), InsightDirection.UP, weight=0.5))
            elif z > 1:
                insights.append(Insight.price(symbol, timedelta(days=5), InsightDirection.FLAT))
        return insights
class Algo(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2019, 6, 3)
        for t in ["XLK", "XLF", "XLE"]:
            self.add_equity(t)
        self.add_alpha(MeanReversionAlpha(20))
        self.set_portfolio_construction(EqualWeightingPortfolioConstructionModel(portfolio_bias=PortfolioBias.LONG))
        self.add_risk_management(MaximumDrawdownPercentPortfolio(0.2, is_trailing=True))
''',

"consolidator_events_pascal": '''
from AlgorithmImports import *
class Weekly(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2019, 6, 3)
        self.spy = self.AddEquity("SPY", Resolution.Daily).Symbol
        consolidator = TradeBarConsolidator(timedelta(days=7))
        consolidator.DataConsolidated += self.OnWeeklyBar
        self.SubscriptionManager.AddConsolidator(self.spy, consolidator)
        self.weeklySma = SimpleMovingAverage(10)
        self.RegisterIndicator(self.spy, self.weeklySma, consolidator)
        self.monthly = []
        self.Consolidate(self.spy, Calendar.Monthly, lambda bar: self.monthly.append(bar.Close))
    def OnWeeklyBar(self, sender, bar):
        if self.weeklySma.IsReady and bar.Close > self.weeklySma.Current.Value and not self.Portfolio.Invested:
            self.SetHoldings(self.spy, 0.9)
        elif self.weeklySma.IsReady and bar.Close < self.weeklySma.Current.Value:
            self.Liquidate()
''',

"order_tickets_stop_updates": '''
from AlgorithmImports import *
class StopTrail(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2019, 6, 3)
        self.s = self.add_equity("AAA").symbol
        self.stop_ticket = None
        self.highest = 0
    def on_data(self, data):
        price = self.securities[self.s].price
        if not self.portfolio.invested and not self.transactions.get_open_orders(self.s):
            self.market_order(self.s, 100)
            return
        if self.portfolio.invested and self.stop_ticket is None:
            self.stop_ticket = self.stop_market_order(self.s, -100, price * 0.95)
            self.highest = price
        elif self.stop_ticket is not None and price > self.highest:
            self.highest = price
            fields = UpdateOrderFields()
            fields.stop_price = price * 0.95
            self.stop_ticket.update(fields)
    def on_order_event(self, e):
        if self.stop_ticket is not None and e.order_id == self.stop_ticket.order_id and e.status == OrderStatus.FILLED:
            self.stop_ticket = None
''',

"indicator_breadth_and_extensions": '''
from AlgorithmImports import *
class Many(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2019, 6, 3)
        s = self.AddEquity("SPY", Resolution.Daily).Symbol
        self.s = s
        self.inds = [self.MACD(s, 12, 26, 9, MovingAverageType.Exponential, Resolution.Daily), self.ADX(s, 14),
                     self.ATR(s, 14), self.CCI(s, 20), self.WILR(s, 14), self.AROON(s, 25, 25), self.KCH(s, 20, 1.5),
                     self.DCH(s, 20), self.VWAP(s, 20), self.OBV(s), self.MFI(s, 14), self.STO(s, 14, 3, 3),
                     self.HMA(s, 20), self.TEMA(s, 10), self.KAMA(s, 10), self.CMO(s, 14), self.LOGR(s, 5), self.NATR(s, 14),
                     self.PSAR(s), self.TRIX(s, 10), self.PPO(s, 12, 26)]
        self.rsi = self.RSI(s, 14)
        self.rsi_sma = IndicatorExtensions.SMA(self.rsi, 10)
        self.spread = IndicatorExtensions.Minus(self.EMA(s, 10), self.SMA(s, 30))
        self.updates = 0
        self.rsi.Updated += self.OnRsi
        self.beta_ind = self.BETA("QQQ", s, 60) if False else None
    def OnRsi(self, sender, updated):
        self.updates += 1
    def OnData(self, data):
        if all(i.IsReady for i in self.inds) and self.rsi_sma.IsReady and not self.Portfolio.Invested:
            sto = self.inds[11]
            if sto.StochK.Value > 0 and self.spread.Current.Value is not None:
                self.SetHoldings(self.s, 0.5)
''',

"pairs_trading_statsmodels": '''
from AlgorithmImports import *
import numpy as np
import statsmodels.api as sm
class Pairs(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2019, 9, 2)
        self.a = self.add_equity("XLK").symbol
        self.b = self.add_equity("QQQ").symbol
        self.schedule.on(self.date_rules.every_day(self.a), self.time_rules.before_market_close(self.a, 10), self.trade)
    def trade(self):
        h = self.history([self.a, self.b], 60, Resolution.DAILY)["close"].unstack(level=0)
        if len(h) < 60:
            return
        x, y = np.log(h[str(self.b)]), np.log(h[str(self.a)])
        model = sm.OLS(y, sm.add_constant(x)).fit()
        spread = y - model.params.iloc[1] * x
        z = (spread.iloc[-1] - spread.mean()) / spread.std()
        if z > 2:
            self.set_holdings(self.a, -0.5); self.set_holdings(self.b, 0.5)
        elif z < -2:
            self.set_holdings(self.a, 0.5); self.set_holdings(self.b, -0.5)
        elif abs(z) < 0.5:
            self.liquidate()
''',

"risk_parity_sklearn_dataclass": '''
from AlgorithmImports import *
from dataclasses import dataclass, field
from collections import defaultdict
import numpy as np
from sklearn.covariance import LedoitWolf

@dataclass
class Config:
    lookback: int = 63
    tickers: list = field(default_factory=lambda: ["SPY", "TLT", "GLD", "IEF"])

class Base(QCAlgorithm):
    @property
    def cfg(self) -> Config:
        return Config()

class RiskParity(Base):
    def initialize(self):
        self.set_start_date(2019, 9, 2)
        self.syms = [self.add_equity(t).symbol for t in self.cfg.tickers]
        self.stats = defaultdict(list)
        self.schedule.on(self.date_rules.week_start(), self.time_rules.at(10, 0), self.rebalance)
    def rebalance(self):
        r = self.history(self.syms, self.cfg.lookback)["close"].unstack(level=0).pct_change().dropna()
        if len(r) < 20:
            return
        cov = LedoitWolf().fit(r.values).covariance_
        inv = 1 / np.sqrt(np.diag(cov))
        w = inv / inv.sum()
        for s, wi in zip(r.columns, w):
            self.set_holdings(s, float(wi))
            self.stats[s].append(float(wi))
''',

"setup_from_variables_store_notify": '''
from AlgorithmImports import *
from datetime import datetime
START = datetime(2019, 6, 3)
CAPITAL = 2 * 50_000
UNIVERSE = {"growth": "QQQ", "bonds": "TLT"}
class Configured(QCAlgorithm):
    def initialize(self):
        self.set_start_date(START)
        self.set_end_date(START.year + 1, 12, 31)
        self.set_cash(CAPITAL)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.assets = {k: self.add_equity(v).symbol for k, v in UNIVERSE.items()}
        self.set_benchmark(self.assets["growth"])
        runs = int(self.object_store.read("runs")) if self.object_store.contains_key("runs") else 0
        self.object_store.save("runs", str(runs + 1))
        self.train(self.fit)
        self.model = None
    def fit(self):
        self.model = {"ok": True}
    def on_data(self, data):
        if not self.portfolio.invested:
            self.set_holdings(self.assets["growth"], 0.6)
            self.set_holdings(self.assets["bonds"], 0.4)
            self.notify.email("me@example.com", "rebalanced", "done")
    def on_end_of_algorithm(self):
        self.log(f"final value {self.portfolio.total_portfolio_value:,.0f}")
''',

"csharp_collections_kvp": '''
from AlgorithmImports import *
class Collections(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2019, 6, 3)
        for t in ["SPY", "TLT", "GLD"]:
            self.AddEquity(t, Resolution.Daily)
    def OnData(self, data):
        n = self.Securities.Count + data.Count + len(list(data.Keys)) + len(list(data.Values))
        for symbol in self.Securities.Keys:
            if not self.Portfolio[symbol].Invested:
                self.SetHoldings(symbol, 0.3)
        for kvp in self.Portfolio:
            if kvp.Value.Invested and kvp.Value.UnrealizedProfitPercent < -0.2:
                self.Liquidate(kvp.Key)
        for kvp in data.Bars:
            _ = (kvp.Key, kvp.Value.Close)
        held = [h for h in self.Portfolio.Values if h.Invested]
        self.Debug(f"{n} {len(held)}")
''',

"crypto_venues_selectors": '''
from AlgorithmImports import *
class AbanicoWalkForwardAtr(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2019, 6, 3)
        self.SetCash(10000)
        self.SetTimeZone(TimeZones.UTC)
        self.SetBrokerageModel(BrokerageName.COINBASE, AccountType.CASH)
        self.btc = self.AddCrypto("BTCUSD", Resolution.Daily, Market.COINBASE).Symbol
        self.eth = self.add_crypto("ETHUSD", Resolution.DAILY, Market.Binance).symbol
        self.atr = self.ATR(self.btc, 14, MovingAverageType.Wilders)
        self.hi = self.MAX(self.btc, 20, Resolution.Daily, Field.High)
        self.mid = self.SMA(self.btc, 20, Resolution.Daily, Field.TypicalPrice)
        self.venue = (Market.KRAKEN, Market.Bybit, BrokerageName.KRAKEN, TimeZones.NEW_YORK, SecurityType.CRYPTO)
    def OnData(self, data):
        if not (self.atr.IsReady and self.hi.IsReady):
            return
        price = self.Securities[self.btc].Price
        if price >= self.hi.Current.Value and not self.Portfolio[self.btc].Invested:
            self.SetHoldings(self.btc, 0.9)
        elif self.Portfolio[self.btc].Invested and price < self.mid.Current.Value - 2 * self.atr.Current.Value:
            self.Liquidate(self.btc)
''',

"custom_data_signal": '''
from AlgorithmImports import *
class Signal(PythonData):
    def GetSource(self, config, date, isLive):
        return SubscriptionDataSource("https://example.com/signal.csv", SubscriptionTransportMedium.RemoteFile)
class CustomSignalAlgo(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2019, 6, 3)
        self.spy = self.AddEquity("SPY").Symbol
        self.signal = self.AddData(Signal, "corpus_signal", Resolution.Daily).Symbol
    def OnData(self, data):
        if data.ContainsKey(self.signal):
            v = data[self.signal].Value
            self.SetHoldings(self.spy, 1.0 if v > 0 else 0.0)
''',

"generics_windows_collections": '''
from AlgorithmImports import *
class WindowedBreakout(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2019, 6, 3)
        self.SetCash(100000)
        self.syms = List[Symbol]()
        for t in ["SPY", "QQQ"]:
            self.syms.Add(self.AddEquity(t, Resolution.Daily).Symbol)
        self.bars = Dictionary[Symbol, RollingWindow[TradeBar]]()
        self.closes = {s: RollingWindow[float](20) for s in self.syms}
        self.sma = {s: self.SMA(s, 10, Resolution.Daily) for s in self.syms}
        self.smaWin = {s: RollingWindow[IndicatorDataPoint](3) for s in self.syms}
        for s in self.syms:
            self.bars.Add(s, RollingWindow[TradeBar](5))
            self.sma[s].Updated += lambda sender, updated, s=s: self.smaWin[s].Add(updated)
        self.seen = HashSet[str]()
    def OnData(self, data):
        for s in self.syms:
            if not data.ContainsKey(s) or data[s] is None:
                continue
            self.bars[s].Add(data[s])
            self.closes[s].Add(data[s].Close)
            self.seen.Add(str(s))
            w = self.closes[s]
            if not (w.IsReady and self.bars[s].IsFull and self.smaWin[s].IsReady):
                continue
            hi = max(w[1:20])
            rising = self.smaWin[s][0].Value > self.smaWin[s][2].Value
            if w[0] > hi and rising and not self.Portfolio[s].Invested:
                self.SetHoldings(s, 0.5)
            elif w[0] < self.bars[s][4].Low and self.Portfolio[s].Invested:
                self.Liquidate(s)
        found, win = self.bars.TryGetValue(self.syms[0])
        assert found and win.Size == 5 and win.Samples >= win.Count
''',
}


@pytest.fixture(scope="module")
def data():
    return _data(n=600, tickers=TICKERS, seed=7)


@pytest.fixture(autouse=True)
def _custom(tmp_path, monkeypatch):
    monkeypatch.setattr(customdata, "DIR", tmp_path)
    customdata.save("corpus_signal", "date,value\n2019-06-03,1\n2019-12-02,-1\n2020-06-01,1\n", "corpus")
    qcalgo.OBJECT_STORE_SEED.clear()


@pytest.mark.parametrize("name", sorted(CORPUS))
def test_corpus_imports_cleanly(name):
    st = codelab.load_strategy(CORPUS[name])
    report = st["qc"]["report"]
    bad = [r for r in report if r["level"] in ("unsupported", "check")]
    assert not bad, f"{name}: {bad}"


@pytest.mark.parametrize("name", sorted(CORPUS))
def test_corpus_runs_to_the_end(name, data):
    code = CORPUS[name]
    st = codelab.load_strategy(code)
    from api.quant import codeserver
    d = _data(n=600, tickers=TICKERS, seed=7)
    codeserver.attach_custom(d, st["custom"])
    res = codelab.backtest(None, d, {"capital": 100_000}, st["start"], on_bar=st["on_bar"])
    algo = st["on_bar"].state["algo"]
    assert algo.time is not None and res["execution"]["mode"] == "event-driven"


def test_corpus_server_check_agrees():
    for name, code in CORPUS.items():
        if "custom_data" in name:
            continue
        h = sandbox.check(code)
        assert h["universe"], name


def test_header_values_from_variables_are_discovered():
    st = codelab.load_strategy(CORPUS["setup_from_variables_store_notify"])
    q = st["qc"]
    assert q["start"] == "2019-06-03" and q["end"] == "2020-12-31" and q["capital"] == 100000.0
    assert q["benchmark"] == "QQQ" and set(q["universe"]) == {"QQQ", "TLT"}


MULTI_FILE = '''from AlgorithmImports import *
from alpha import ReversalAlpha
from helpers.dates import start_of
class ShortTermReversalAlgorithm(QCAlgorithm):
    def initialize(self):
        self.set_start_date(start_of())
        self.set_cash(100000)
        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.select)
        self.add_alpha(ReversalAlpha())
        self.set_portfolio_construction(EqualWeightingPortfolioConstructionModel())
    def select(self, fundamental):
        return [f.symbol for f in sorted(fundamental, key=lambda f: f.dollar_volume)[-3:]]
# file: alpha.py
from AlgorithmImports import *
class ReversalAlpha(AlphaModel):
    def update(self, algorithm, data):
        out = []
        for symbol in data.keys():
            h = algorithm.history(symbol, 6)
            if len(h) == 6 and h["close"].iloc[-1] < h["close"].iloc[0]:
                out.append(Insight.price(symbol, timedelta(days=5), InsightDirection.UP))
        return out
# file: helpers/dates.py
from datetime import datetime
def start_of():
    return datetime(2019, 6, 3)
'''


def test_multi_file_project_imports_checks_and_runs():
    h = sandbox.check(MULTI_FILE)                                   # server: discovery in the sandbox, project imports
    assert h["start"] == "2019-06-03" and h["qc"]["dynamic_universe"]
    st = codelab.load_strategy(MULTI_FILE)
    assert not [r for r in st["qc"]["report"] if r["level"] in ("unsupported", "check")]
    d = _data(n=600, tickers=TICKERS, seed=7)
    codelab.backtest(None, d, {"capital": 100_000}, st["start"], on_bar=st["on_bar"])
    assert st["on_bar"].state["algo"]._framework.count >= 0


def test_unknown_module_says_how_to_add_a_project_file():
    with pytest.raises(sandbox.SandboxError, match="# file: alpha.py"):
        sandbox.check(MULTI_FILE.split("# file: alpha.py")[0])


def test_failed_discovery_names_the_error():
    bad = MULTI_FILE.replace("return datetime(2019, 6, 3)", "return undefined_name")
    with pytest.raises(sandbox.SandboxError, match="NameError"):
        sandbox.check(bad)



def test_field_selector_feeds_the_chosen_price():
    st = codelab.load_strategy(CORPUS["crypto_venues_selectors"])
    d = _data(n=600, tickers=TICKERS, seed=7)
    codelab.backtest(None, d, {"capital": 100_000}, st["start"], on_bar=st["on_bar"])
    algo = st["on_bar"].state["algo"]
    last = algo.time
    hi20 = d.high["BTC-USD"].loc[:last].tail(20).max()
    assert abs(algo.hi.current.value - hi20) < 1e-9                  # MAX over highs, not closes
    assert algo.venue == ("kraken", "bybit", "kraken", "America/New_York", "crypto")


def test_generic_brackets_on_every_layer_class():
    """C# generic syntax (RollingWindow[float], List[Symbol], Dictionary[K, V], any layer class[T]) is accepted."""
    for name, v in qcalgo.NAMES.items():
        if isinstance(v, type) and v.__module__ == qcalgo.__name__:
            assert v[float] is v, name
    w = qcalgo.RollingWindow[float](3)
    for x in range(5):
        w.add(float(x))
    assert list(w) == [4.0, 3.0, 2.0] and w[0:2] == [4.0, 3.0] and w.most_recently_removed == 1.0 and w.samples == 5
