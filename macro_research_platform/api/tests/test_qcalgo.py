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
def test_ema_seeded_with_sma_and_wilder_rsi():
    e = qcalgo.ExponentialMovingAverage(3)
    for v in (1, 2, 3, 4):
        e.update(None, v)
    # LEAN: the value at the 3rd input is mean(1, 2, 3) = 2; then 0.5·4 + 0.5·2 = 3
    assert e.is_ready and abs(e.current.value - 3.0) < 1e-12
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
    tk = [t for t in algo._ql_tickets.values() if t.order_type == qcalgo.OrderType.MARKET_ON_CLOSE][0]
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
    ("x = self._ql_ctx", "the engine context (holds future prices)"),
    ("x = self._ql_ctx._data", "the engine's full price history"),
    ("x = self.initialize.__globals__", "a function's globals"),
    ("x = (lambda: 0).__code__", "code objects"),
    ("x = eval('1')", "eval"),
    ("exec('x = 1')", "exec"),
    ("import os", "os import"),
    ("import requests", "network"),
    ("from api.quant import qcalgo", "the platform's engine"),
    ("x = '{0.__globals__}'.format(self.initialize)", "format-string escape"),
    ("x = self.__dict__['_ql_ctx']", "the engine context by name"),
])
def test_sandbox_rejects_escapes(snippet, why):
    code = OK_CLASS.replace("        _ = self._h.n", "        " + snippet)
    with pytest.raises(sandbox.SandboxError):
        sandbox.check(code)


def test_sandbox_admits_ordinary_python():
    """Isolation is the container's job: classes, inheritance, decorators, super(), properties, private names, the
    scientific stack and reaching methods through a class are all ordinary Python and allowed."""
    code = OK_CLASS.replace("class Helper(object):", """import scipy.stats as ss
from dataclasses import dataclass
from collections import defaultdict
@dataclass
class Cfg:
    n: int = 3
class Base:
    @property
    def k(self):
        return 2
    @staticmethod
    def f(x):
        return x
class Helper(Base):""").replace("        _ = self._h.n", "        _ = (self._h.n, self._never_assigned_ok if False else 0, A.on_data, ss.norm.cdf(0), defaultdict(list))")
    assert sandbox.check(code)["universe"] == ["SPY"]


def test_sandbox_admits_python_that_used_to_be_refused():
    """Metaclasses, any special method, async code, __class__ / __dict__ / vars(), open(), file-like objects in memory,
    pickle, threads and any installed library pass the check (isolation and the run-time guard are the boundary)."""
    import importlib.util
    # torch lives in QuantConnect's research image: import it only when Docker (with the LEAN image) or a local
    # install provides it, so the language checks below run on any machine
    has_torch = "torch" in sandbox.lean_modules() or importlib.util.find_spec("torch") is not None
    extra = ("import io, pickle, threading, asyncio" + (", torch" if has_torch else "") + """
class Meta(type):
    pass
class Helper(object, metaclass=Meta):
    def __eq__(self, o):
        return True
    def __hash__(self):
        return 1
async def later():
    return 1
""")
    code = OK_CLASS.replace("class Helper(object):", extra + "class Helper2(object):").replace(
        "        _ = self._h.n", "        _ = (self.__class__.__name__, self.__dict__, vars(self), io.StringIO('a'), pickle.dumps(1))")
    assert sandbox.check(code)["universe"] == ["SPY"]


def test_sandbox_still_refuses_banned_dunders_reserved_names_and_unavailable_data():
    with pytest.raises(sandbox.SandboxError):
        sandbox.check(OK_CLASS.replace("    def __init__(self, n):", "    def __getattribute__(self, n):"))
    with pytest.raises(sandbox.SandboxError):
        sandbox.check(OK_CLASS.replace('        self.add_equity("SPY")', '        self.add_equity("SPY")\n        self.add_future("ES")'))
    with pytest.raises(sandbox.SandboxError):              # overwriting a name the API uses internally
        sandbox.check(OK_CLASS.replace("        self._h = Helper(3)", "        self._ql_log = []"))


# ── account model: buying power, settlement, locates, tax lots ──
def _acct(body, data=None, start="2019-06-03"):
    code = "class A(QCAlgorithm):\n    def initialize(self):\n        self.set_start_date(2019, 6, 3)\n" + body
    return _run(code, data or _data())


def test_cash_account_refuses_shorts_and_unsettled_cash():
    res, algo = _acct('''        self.set_brokerage_model(BrokerageName.DEFAULT, AccountType.CASH)
        self.add_equity("AAA")
        self.add_equity("BBB")
        self._step = 0
    def on_data(self, data):
        self._step += 1
        if self._step == 1:
            self.short = self.market_order("BBB", -10)
            self.set_holdings("AAA", 0.9)
        elif self._step == 3:
            self.liquidate("AAA")
        elif self._step == 4:
            self.rebuy = self.set_holdings("BBB", 0.5)        # the AAA proceeds have not settled yet (T+2 in 2019)
        elif self._step == 7:
            self.later = self.set_holdings("BBB", 0.5)        # now they have
''')
    assert algo.short.status == "invalid" and "cannot sell short" in algo._ql_rejected[0]["reason"]
    assert algo.rebuy and algo.rebuy[0].status == "invalid" and "settled cash" in algo.rebuy[0]._algo._ql_rejected[-1]["reason"]
    assert algo.later and algo.later[0].status in ("submitted", "filled")


def test_margin_account_caps_gross_at_twice_portfolio_value():
    res, algo = _acct('''        self.add_equity("AAA")
        self._done = False
    def on_data(self, data):
        if not self._done:
            self.ok = self.set_holdings("AAA", 1.5)
            self.too_much = self.market_order("AAA", 10 * self.portfolio.total_portfolio_value / data["AAA"].close)
            self._done = True
''')
    assert algo.ok[0].status == "filled" and algo.too_much.status == "invalid"
    assert "buying power" in algo._ql_rejected[-1]["reason"]


def test_short_locate_refused_for_penny_stock():
    d = _data()
    for f in ("close", "open", "high", "low"):
        getattr(d, f)["BBB"] = getattr(d, f)["BBB"] / 40          # ~ $2.50 a share
    res, algo = _acct('''        self.add_equity("BBB")
        self._done = False
    def on_data(self, data):
        if not self._done:
            self.short = self.market_order("BBB", -100)
            self._done = True
''', d)
    assert algo.short.status == "invalid" and "located" in algo._ql_rejected[-1]["reason"]


def test_tax_lots_fifo_and_holding_period():
    algo = qcalgo.QCAlgorithm()
    algo._ql_ctx = type("C", (), {"i": 0})()
    algo._ql_book_lots("X", 10, 100.0, "2020-01-02", 0)
    algo._ql_book_lots("X", 10, 110.0, "2021-06-01", 1)
    algo._ql_book_lots("X", -15, 120.0, "2021-07-01", 2)       # 10 from 2020 (long-term) + 5 from 2021 (short-term)
    assert abs(algo._ql_realized["long_term"] - 10 * 20) < 1e-9 and abs(algo._ql_realized["short_term"] - 5 * 10) < 1e-9
    assert algo.tax_lots("X") == [{"shares": 5, "price": 110.0, "date": "2021-06-01"}]


def test_selector_sees_point_in_time_fundamentals():
    data = _data(tickers=("AAA", "BBB", "CCC"))
    idx, cols = data.close.index, data.close.columns
    mcap = pd.DataFrame(np.nan, index=idx, columns=cols)
    mcap.loc[:, "AAA"], mcap.loc[:, "BBB"] = 5e9, 9e10                 # CCC: no filing → NaN
    mcap.loc[idx >= idx[250], "AAA"] = 2e11                          # a later filing makes AAA the largest
    data = codelab.Data(data.close, data.open, data.high, data.low, data.volume, fundamentals={"market_cap": mcap})
    data.members = pd.DataFrame(True, index=idx, columns=cols)
    code = '''
class F(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2019, 6, 3)
        self.add_universe(self.pick)
        self._seen = []
    def pick(self, funds):
        have = [f for f in funds if f.has_fundamental_data and f.market_cap > 0]
        top = sorted(have, key=lambda f: -f.market_cap)[:1]
        self._seen.append(str(top[0].symbol) if top else None)
        return [f.symbol for f in top]
'''
    h = qcalgo.static_header(code)
    assert h["fundamentals"] == ["market_cap"]
    res, algo = _run(code, data)
    assert algo._seen[0] == "BBB" and algo._seen[-1] == "AAA" and "CCC" not in algo._seen


def test_plain_strategy_header_may_be_computed():
    code = '''SECTORS = "KFE"
UNIVERSE = [f"XL{s}" for s in SECTORS] + ["SPY"]
START = "20" + "15-01-01"
PARAMS = {"lookback": list(range(20, 101, 40))}
def strategy(data, lookback=60):
    return data.close.pct_change(lookback).rank(axis=1).le(2).astype(float) / 2
'''
    sandbox._DISCOVERED.clear()
    h = sandbox.check(code)
    assert h["universe"] == ["XLK", "XLF", "XLE", "SPY"] and h["start"] == "2015-01-01"
    assert h["params"] == {"lookback": [20, 60, 100]}


def test_unknown_library_is_reported_and_known_ones_pick_a_runtime():
    with pytest.raises(sandbox.SandboxError, match="there is no module 'surely_not_a_module'"):
        sandbox.check(OK_CLASS.replace("class Helper(object):", "import surely_not_a_module\nclass Helper(object):"))
    assert sandbox.check(OK_CLASS)["runtime"] == "default"
    if "talib" in sandbox.lean_modules():                    # QuantConnect's environment present (LEAN image)
        assert sandbox.check(OK_CLASS.replace("class Helper(object):", "import talib\nclass Helper(object):"))["runtime"] == "full"


def test_algorithm_may_define_init_and_never_holds_the_engine_context():
    code = '''class A(QCAlgorithm):
    def __init__(self):
        self.mine = 1
    def initialize(self):
        self.set_start_date(2019, 6, 3)
        self.add_equity("AAA")
        self.seen = sorted(k for k in vars(self) if "ctx" in k)
    def on_data(self, data):
        if not self.portfolio.invested:
            self.set_holdings("AAA", 1)
'''
    res, algo = _run(code, _data())
    assert algo.mine == 1 and algo.seen == [] and "_ql_ctx" not in algo.__dict__
    assert algo.portfolio["AAA"].invested                   # the engine's own set-up ran despite the custom __init__
