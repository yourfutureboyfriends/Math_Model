"""QuantConnect-style API (api/quant/qcalgo.py): indicators, order lifecycle, scheduling, warm-up, universes, and the
sandbox rules that admit algorithm classes without opening the sandbox."""
import numpy as np
import pandas as pd
import pytest

from api.quant import codelab, qcalgo, sandbox


def _data(n=320, tickers=("AAA", "BBB"), seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2019-01-01", periods=n)
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, (n, len(tickers))), axis=0)), index=idx, columns=list(tickers))
    open_ = close.shift(1).fillna(close.iloc[0]) * (1 + rng.normal(0, 0.002, close.shape))
    high = np.maximum(open_, close) * 1.004
    low = np.minimum(open_, close) * 0.996
    vol = pd.DataFrame(5e6, index=idx, columns=list(tickers))
    return codelab.Data(close, open_, high, low, vol)


def _run(code, data, start="2019-06-03", costs=None):
    st = codelab.load_strategy(code)
    res = codelab.backtest(None, data, {"capital": 100_000, **(costs or {})}, start, on_bar=st["on_bar"])
    return res, st["on_bar"].state["algo"]


# ── indicators: LEAN definitions ──
def test_ema_seeded_with_first_value_and_wilder_rsi():
    e = qcalgo.ExponentialMovingAverage(3)
    for v in (1, 2, 3, 4):
        e.update(None, v)
    k = 0.5
    want = 1
    for v in (2, 3, 4):
        want = k * v + (1 - k) * want
    assert e.is_ready and abs(e.current.value - want) < 1e-12
    r = qcalgo.RelativeStrengthIndex(2)
    for v in (10, 11, 10, 12):                     # changes +1, −1, +2
        r.update(None, v)
    # Wilder: first average over 2 changes (gain 0.5, loss 0.5), then (0.5·1 + 2)/2 = 1.25 and (0.5·1 + 0)/2 = 0.25
    assert abs(r.current.value - (100 - 100 / (1 + 1.25 / 0.25))) < 1e-9 and r.is_ready


def test_sma_bollinger_population_std_and_rolling_window():
    b = qcalgo.BollingerBands(3, 2)
    for v in (1, 2, 3):
        b.update(None, v)
    sd = np.std([1, 2, 3])
    assert abs(b.upper_band.value - (2 + 2 * sd)) < 1e-12
    w = qcalgo.RollingWindow(2)
    w.add(1); w.add(2); w.add(3)
    assert w[0] == 3 and w[1] == 2 and w.is_ready and w.count == 2


# ── algorithms on the engine ──
ALGO = '''
from AlgorithmImports import *

class T(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2019, 6, 3)
        self.set_cash(100000)
        self.a = self.add_equity("AAA").symbol
        self.add_equity("BBB")
        self.ma = self.sma(self.a, 20)
        self.set_warm_up(10)
        self._events = []
        self._warm_orders = 0
        self.schedule.on(self.date_rules.month_start(self.a), self.time_rules.after_market_open(self.a, 30), self.go)

    def on_data(self, data):
        if self.is_warming_up:
            t = self.market_order(self.a, 10)
            if t.status == OrderStatus.INVALID:
                self._warm_orders += 1

    def go(self):
        self.set_holdings(self.a, 0.5)
        self.market_on_close_order("BBB", 7)

    def on_order_event(self, e):
        self._events.append((e.order_id, e.status, e.fill_quantity, str(e.utc_time)[:10]))
'''


def test_orders_fill_with_events_and_warm_up_refuses_orders():
    data = _data()
    res, algo = _run(ALGO, data)
    assert algo.ma.is_ready and algo._warm_orders == 10                 # 10 warm-up bars, orders refused
    statuses = {}
    for oid, s, q, d in algo._events:
        statuses.setdefault(oid, []).append(s)
    assert statuses and all(v[0] == "submitted" and v[-1] == "filled" for v in statuses.values())
    # the market-on-close order fills at the next session's close, the market order at the next open
    tk = [t for t in algo._tickets.values() if t.order_type == qcalgo.OrderType.MARKET_ON_CLOSE][0]
    sub = pd.Timestamp(tk.time).normalize()
    nxt = data.close.index[data.close.index.searchsorted(sub, side="right")]
    assert abs(tk.average_fill_price - data.close.loc[nxt, "BBB"]) < 1e-9
    # set_holdings: about half of portfolio value in AAA after the first rebalance (whole shares)
    assert algo.portfolio["AAA"].quantity > 0 and float(algo.portfolio["AAA"].quantity) == int(algo.portfolio["AAA"].quantity)


def test_limit_order_fills_only_when_the_range_reaches_it():
    code = '''
class L(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2019, 6, 3)
        self.add_equity("AAA")
        self._done = False
    def on_data(self, data):
        if not self._done:
            self._t = self.limit_order("AAA", 100, data["AAA"].close * 0.9)
            self._u = self.limit_order("AAA", 50, data["AAA"].close * 0.999)
            self._done = True
'''
    data = _data()
    res, algo = _run(code, data)
    deep, near = algo._t, algo._u
    low_after = data.low["AAA"][data.close.index > pd.Timestamp(deep.time)].min()
    assert (deep.status == "filled") == (low_after <= deep.prices["price"])
    if near.status == "filled":
        assert near.average_fill_price <= near.prices["price"] + 1e-9


def test_dynamic_universe_raises_security_changes():
    code = '''
class U(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2019, 6, 3)
        self.add_universe(self.pick)
        self._changes = []
    def pick(self, funds):
        return [f.symbol for f in sorted(funds, key=lambda f: -f.dollar_volume)[:1]]
    def on_securities_changed(self, changes):
        self._changes.append(([str(s.symbol) for s in changes.added_securities], [str(s.symbol) for s in changes.removed_securities]))
'''
    data = _data()
    data.members = pd.DataFrame(True, index=data.close.index, columns=data.close.columns)
    res, algo = _run(code, data)
    assert algo._changes and algo._changes[0][0]                         # the first selection adds a name


def test_static_header_reads_loops_and_reports_unsupported():
    h = qcalgo.static_header('''
class X(QCAlgorithm):
    TICKERS = ["SPY", "TLT"]
    def initialize(self):
        self.SetStartDate(2012, 3, 1)
        for t in self.TICKERS:
            self.AddEquity(t, Resolution.Minute)
        self.add_option("SPY")
''')
    assert h["universe"] == ["SPY", "TLT"] and h["start"] == "2012-03-01"
    lv = {(r["level"], r["feature"]) for r in h["report"]}
    assert ("unsupported", "add_option") in lv and any(l == "approximated" for l, _ in lv)


# ── sandbox rules ──
OK_CLASS = '''
from AlgorithmImports import *
from datetime import timedelta
class Helper(object):
    def __init__(self, n):
        self.n = n
class A(QCAlgorithm):
    def initialize(self):
        self.add_equity("SPY")
        self._h = Helper(3)
    def on_data(self, data):
        _ = self._h.n
        if hasattr(self, "_h"):
            pass
'''


def test_sandbox_admits_algorithm_classes():
    h = sandbox.check(OK_CLASS)
    assert h["mode"] == "event" and h["universe"] == ["SPY"]


@pytest.mark.parametrize("snippet,why", [
    ("x = self._ctx", "API-internal private name"),
    ("x = self._never_assigned", "private name not assigned by the code"),
    ("x = A.on_data", "method through the class"),
    ("self = 1", "reassigning self"),
    ("x = ().__class__", "dunder access"),
    ("x = self.__dict__", "dunder on self"),
])
def test_sandbox_rejects_escapes(snippet, why):
    code = OK_CLASS.replace("        _ = self._h.n", "        " + snippet)
    with pytest.raises(sandbox.SandboxError):
        sandbox.check(code)


def test_sandbox_rejects_special_methods_and_other_bases():
    with pytest.raises(sandbox.SandboxError):
        sandbox.check(OK_CLASS.replace("class Helper(object):", "class Helper(dict):"))
    with pytest.raises(sandbox.SandboxError):
        sandbox.check(OK_CLASS.replace("    def __init__(self, n):", "    def __getattr__(self, n):"))
    with pytest.raises(sandbox.SandboxError):
        sandbox.check(OK_CLASS.replace('        self.add_equity("SPY")', '        self.add_equity("SPY")\n        self.add_future("ES")'))
