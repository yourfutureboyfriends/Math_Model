"""
QuantConnect-style algorithms on the Code Lab's event engine — a compatibility layer, so an imported LEAN Python
algorithm keeps its structure (initialize, on_data, scheduled events, universe changes, order events, stateful
indicators, warm-up) instead of being rewritten as a pandas weight table.

    class MyAlgo(QCAlgorithm):
        def initialize(self):
            self.set_start_date(2015, 1, 1); self.set_cash(100_000)
            self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
            self.fast, self.slow = self.ema(self.spy, 50), self.ema(self.spy, 200)
            self.schedule.on(self.date_rules.month_start(self.spy), self.time_rules.after_market_open(self.spy, 30),
                             self.rebalance)
        def rebalance(self):
            self.set_holdings(self.spy, 1.0 if self.fast.current.value > self.slow.current.value else 0.0)

Both the snake_case API and the older PascalCase one (SetStartDate, AddEquity, OnData, …) are accepted.

Semantics (API version qc-compat/1, DAILY resolution — every result says so):
  data          daily bars only. A requested minute/second/hour resolution runs on daily bars (reported).
  time          on_data(slice) and scheduled events run after each session's close (LEAN delivers a daily bar after
                the close too). Time rules (after_market_open(30), before_market_close(5), at(10, 0)) cannot be honoured
                within the day: the event runs at that session's close decision, orders fill per below (reported).
  orders        market orders fill at the next session's open (LEAN converts daily-data market orders placed after
                the close to market-on-open); market_on_close_order fills at the next session's close; limit, stop,
                stop-limit and trailing-stop orders are checked against each later session's range (gap-through fills
                at the open). Quantities are shares; participation caps can split a market order over days
                (PARTIALLY_FILLED events). Costs, borrow, margin calls, lots: the Code Lab's cost model.
  indicators    stateful, updated bar by bar with LEAN's definitions (SMA, EMA seeded with the SMA of its first n inputs,
                Wilder RSI and ATR, MACD, Bollinger Bands on population standard deviation, ROC, momentum, max/min of the
                close, std, ADX) — checked against LEAN's own reference data (api/tests/test_qcalgo_lean_parity.py).
  warm-up       indicators are primed from the history before the start date, bar by bar; set_warm_up(n) also calls
                on_data for those bars with is_warming_up = True (orders are refused, as in LEAN).
  universes     add_universe(selector) runs the selector each session on every point-in-time S&P 500 member with a
                bar (symbol, price, volume, dollar_volume, and SEC point-in-time fundamentals with LEAN's names when used:
                market_cap, valuation_ratios.*, operation_ratios.*, earning_reports.*); additions and removals call
                on_securities_changed. self.universe.etf("SPY" | "IVV" | "VOO") = point-in-time S&P 500.
  not available historical option / future chains, consolidators, intraday bars, custom data, alpha/portfolio
                framework models, live brokerages — the importer's compatibility report lists them by line.
"""
from __future__ import annotations

import ast
import math
from collections import deque
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

API_VERSION = "qc-compat/1 (daily)"


# ── enums ────────────────────────────────────────────────────────────────────
class _Enum:
    pass


class Resolution(_Enum):
    TICK, SECOND, MINUTE, HOUR, DAILY = "tick", "second", "minute", "hour", "daily"
    Tick, Second, Minute, Hour, Daily = TICK, SECOND, MINUTE, HOUR, DAILY


class OrderStatus(_Enum):
    NEW, SUBMITTED, PARTIALLY_FILLED, FILLED, CANCELED, NONE, INVALID, CANCEL_PENDING, UPDATE_SUBMITTED = (
        "new", "submitted", "partially_filled", "filled", "canceled", "none", "invalid", "cancel_pending", "update_submitted")
    New, Submitted, PartiallyFilled, Filled, Canceled, Invalid = NEW, SUBMITTED, PARTIALLY_FILLED, FILLED, CANCELED, INVALID


class OrderDirection(_Enum):
    BUY, SELL, HOLD = "buy", "sell", "hold"
    Buy, Sell, Hold = BUY, SELL, HOLD


class OrderType(_Enum):
    MARKET, LIMIT, STOP_MARKET, STOP_LIMIT, MARKET_ON_OPEN, MARKET_ON_CLOSE, TRAILING_STOP = (
        "market", "limit", "stop_market", "stop_limit", "market_on_open", "market_on_close", "trailing_stop")
    Market, Limit, StopMarket, StopLimit, MarketOnOpen, MarketOnClose, TrailingStop = (
        MARKET, LIMIT, STOP_MARKET, STOP_LIMIT, MARKET_ON_OPEN, MARKET_ON_CLOSE, TRAILING_STOP)


class MovingAverageType(_Enum):
    SIMPLE, EXPONENTIAL, WILDERS = "simple", "exponential", "wilders"
    Simple, Exponential, Wilders = SIMPLE, EXPONENTIAL, WILDERS


class DataNormalizationMode(_Enum):
    ADJUSTED, RAW, SPLIT_ADJUSTED, TOTAL_RETURN = "adjusted", "raw", "split_adjusted", "total_return"
    Adjusted, Raw, SplitAdjusted, TotalReturn = ADJUSTED, RAW, SPLIT_ADJUSTED, TOTAL_RETURN


class BrokerageName(_Enum):
    DEFAULT, INTERACTIVE_BROKERS_BROKERAGE, ALPACA, TRADIER_BROKERAGE, QUANTCONNECT_BROKERAGE = (
        "default", "ibkr", "alpaca", "tradier", "default")
    Default, InteractiveBrokersBrokerage, Alpaca = DEFAULT, INTERACTIVE_BROKERS_BROKERAGE, ALPACA


class AccountType(_Enum):
    MARGIN, CASH = "margin", "cash"
    Margin, Cash = MARGIN, CASH


class DayOfWeek(_Enum):
    MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY = range(5)
    Monday, Tuesday, Wednesday, Thursday, Friday = range(5)


class Market(_Enum):
    USA = "usa"


# ── symbols and data ─────────────────────────────────────────────────────────
class Symbol:
    def __init__(self, ticker: str):
        self.value = str(ticker).upper()
        self.id = self.value

    def __str__(self):
        return self.value

    def __repr__(self):
        return self.value

    def __eq__(self, other):
        return str(other).upper() == self.value

    def __hash__(self):
        return hash(self.value)

    @staticmethod
    def create(ticker: str, *a, **k) -> "Symbol":
        return Symbol(ticker)


def _sym(x: Any) -> str:
    return x.value if isinstance(x, Symbol) else (x.symbol.value if isinstance(x, Security) else str(x).upper())


class TradeBar:
    def __init__(self, symbol: Symbol, time: datetime, o: float, h: float, l: float, c: float, v: float):
        self.symbol, self.time, self.end_time = symbol, time, time
        self.open, self.high, self.low, self.close, self.volume = o, h, l, c, v
        self.value = self.price = c
        self.period = timedelta(days=1)
        self.Open, self.High, self.Low, self.Close, self.Volume, self.Value = o, h, l, c, v, c


class Slice:
    """One session's bars: slice[symbol], slice.bars[symbol], symbol in slice, slice.contains_key(symbol)."""

    def __init__(self, time: datetime, bars: Dict[str, TradeBar]):
        self.time = time
        self._b = bars
        self.bars = _SymbolDict(bars)
        self.Bars = self.bars

    def __getitem__(self, s):
        return self._b[_sym(s)]

    def __contains__(self, s):
        return _sym(s) in self._b

    def contains_key(self, s) -> bool:
        return _sym(s) in self._b

    ContainsKey = contains_key

    def get(self, s, default=None):
        return self._b.get(_sym(s), default)

    def keys(self):
        return [b.symbol for b in self._b.values()]

    def values(self):
        return list(self._b.values())

    def items(self):
        return [(b.symbol, b) for b in self._b.values()]

    def __len__(self):
        return len(self._b)


class _SymbolDict(dict):
    def __getitem__(self, s):
        return dict.__getitem__(self, _sym(s))

    def __contains__(self, s):
        return dict.__contains__(self, _sym(s))

    def contains_key(self, s) -> bool:
        return _sym(s) in self

    ContainsKey = contains_key

    def get(self, s, default=None):
        return dict.get(self, _sym(s), default)


# ── indicators (stateful, LEAN definitions) ─────────────────────────────────
class IndicatorDataPoint:
    def __init__(self, time=None, value: float = 0.0):
        self.time, self.value = time, float(value)
        self.Value = self.value

    def __float__(self):
        return self.value

    def __repr__(self):
        return f"{self.value:.6g}"


class Indicator:
    """Update with update(time, value) or update(trade_bar); read .current.value, .is_ready, .samples."""
    warm_up_period = 1

    def __init__(self, name: str = ""):
        self.name = name
        self.samples = 0
        self.current = IndicatorDataPoint()
        self.updated: List[Callable] = []

    @property
    def is_ready(self) -> bool:
        return self.samples >= self.warm_up_period

    IsReady = is_ready

    @property
    def value(self) -> float:
        return self.current.value

    @property
    def Current(self):
        return self.current

    def __float__(self):
        return self.current.value

    def update(self, time, value=None) -> bool:
        if value is None and isinstance(time, (TradeBar, IndicatorDataPoint)):
            bar = time
            time, value = bar.time, bar
        self.samples += 1
        v = self._compute(value)
        if v is not None and np.isfinite(v):
            self.current = IndicatorDataPoint(time, v)
        for cb in self.updated:
            cb(self, self.current)
        return self.is_ready

    Update = update

    def reset(self) -> None:
        self.__init__(*self._args) if hasattr(self, "_args") else None

    Reset = reset

    def _x(self, value) -> float:
        return float(value.close if isinstance(value, TradeBar) else value.value if isinstance(value, IndicatorDataPoint) else value)

    def _compute(self, value):
        raise NotImplementedError


class SimpleMovingAverage(Indicator):
    def __init__(self, period: int, name: str = ""):
        super().__init__(name or f"SMA({period})")
        self._args = (period, name)
        self.period = self.warm_up_period = int(period)
        self._w: deque = deque(maxlen=self.period)

    def _compute(self, value):
        self._w.append(self._x(value))
        return sum(self._w) / len(self._w)


class ExponentialMovingAverage(Indicator):
    """LEAN: 0 until ready; the value at sample n is the simple average of the first n inputs; then
    k·x + (1 − k)·previous with k = 2/(n + 1)."""

    def __init__(self, period: int, smoothing_factor: Optional[float] = None, name: str = ""):
        super().__init__(name or f"EMA({period})")
        self._args = (period, smoothing_factor, name)
        self.period = self.warm_up_period = int(period)
        self.k = smoothing_factor if smoothing_factor is not None else 2.0 / (period + 1)
        self._v: Optional[float] = None
        self._seed: List[float] = []

    def _compute(self, value):
        x = self._x(value)
        if self._v is None:
            self._seed.append(x)
            if len(self._seed) < self.period:
                return 0.0
            self._v = sum(self._seed) / self.period
            return self._v
        self._v = self.k * x + (1 - self.k) * self._v
        return self._v


class WildersMovingAverage(Indicator):
    """LEAN: a simple average of the first n inputs, then (previous·(n − 1) + x) / n."""

    def __init__(self, period: int, name: str = ""):
        super().__init__(name or f"WWMA({period})")
        self._args = (period, name)
        self.period = self.warm_up_period = int(period)
        self._buf: List[float] = []
        self._v: Optional[float] = None

    def _compute(self, value):
        x = self._x(value)
        if self._v is None:
            self._buf.append(x)
            if len(self._buf) < self.period:
                return sum(self._buf) / len(self._buf)
            self._v = sum(self._buf) / self.period
            return self._v
        self._v = (self._v * (self.period - 1) + x) / self.period
        return self._v


def _ma(kind: str, period: int):
    return {MovingAverageType.SIMPLE: SimpleMovingAverage, MovingAverageType.EXPONENTIAL: ExponentialMovingAverage,
            MovingAverageType.WILDERS: WildersMovingAverage}.get(kind, SimpleMovingAverage)(period)


class RelativeStrengthIndex(Indicator):
    def __init__(self, period: int, moving_average_type: str = MovingAverageType.WILDERS, name: str = ""):
        super().__init__(name or f"RSI({period})")
        self._args = (period, moving_average_type, name)
        self.period = int(period)
        self.warm_up_period = self.period + 1
        self.average_gain, self.average_loss = _ma(moving_average_type, period), _ma(moving_average_type, period)
        self._prev: Optional[float] = None

    def _compute(self, value):
        x = self._x(value)
        if self._prev is None:
            self._prev = x
            return None
        ch = x - self._prev
        self._prev = x
        self.average_gain.update(None, max(ch, 0.0))
        self.average_loss.update(None, max(-ch, 0.0))
        g, l = self.average_gain.current.value, self.average_loss.current.value
        return 100.0 if l == 0 else 100.0 - 100.0 / (1 + g / l)


class AverageTrueRange(Indicator):
    def __init__(self, period: int, moving_average_type: str = MovingAverageType.WILDERS, name: str = ""):
        super().__init__(name or f"ATR({period})")
        self._args = (period, moving_average_type, name)
        self.period = self.warm_up_period = int(period)
        self._ma = _ma(moving_average_type, period)
        self._prev_close: Optional[float] = None
        self.true_range = IndicatorDataPoint()

    def _compute(self, bar):
        if not isinstance(bar, TradeBar):
            raise ValueError("ATR needs trade bars (it is updated automatically when created with self.atr()).")
        tr = bar.high - bar.low if self._prev_close is None else max(bar.high - bar.low, abs(bar.high - self._prev_close),
                                                                      abs(bar.low - self._prev_close))
        self._prev_close = bar.close
        self.true_range = IndicatorDataPoint(bar.time, tr)
        self._ma.update(bar.time, tr)
        return self._ma.current.value


class StandardDeviation(Indicator):
    """Population standard deviation over the window (LEAN)."""

    def __init__(self, period: int, name: str = ""):
        super().__init__(name or f"STD({period})")
        self._args = (period, name)
        self.period = self.warm_up_period = int(period)
        self._w: deque = deque(maxlen=self.period)

    def _compute(self, value):
        self._w.append(self._x(value))
        return float(np.std(self._w)) if len(self._w) > 1 else 0.0


class BollingerBands(Indicator):
    def __init__(self, period: int, k: float, moving_average_type: str = MovingAverageType.SIMPLE, name: str = ""):
        super().__init__(name or f"BB({period},{k})")
        self._args = (period, k, moving_average_type, name)
        self.period = self.warm_up_period = int(period)
        self.k = float(k)
        self.middle_band, self.standard_deviation = _ma(moving_average_type, period), StandardDeviation(period)
        self.upper_band, self.lower_band = IndicatorDataPoint(), IndicatorDataPoint()
        self.band_width, self.percent_b = IndicatorDataPoint(), IndicatorDataPoint()

    def _compute(self, value):
        x = self._x(value)
        self.middle_band.update(None, x)
        self.standard_deviation.update(None, x)
        m, sd = self.middle_band.current.value, self.standard_deviation.current.value
        self.upper_band, self.lower_band = IndicatorDataPoint(None, m + self.k * sd), IndicatorDataPoint(None, m - self.k * sd)
        width = self.upper_band.value - self.lower_band.value
        self.band_width = IndicatorDataPoint(None, width / m if m else 0.0)
        self.percent_b = IndicatorDataPoint(None, (x - self.lower_band.value) / width if width else 0.0)
        return m


class MovingAverageConvergenceDivergence(Indicator):
    def __init__(self, fast: int, slow: int, signal: int, moving_average_type: str = MovingAverageType.EXPONENTIAL,
                 name: str = ""):
        super().__init__(name or f"MACD({fast},{slow},{signal})")
        self._args = (fast, slow, signal, moving_average_type, name)
        self.warm_up_period = int(slow) + int(signal) - 1
        self.fast, self.slow = _ma(moving_average_type, fast), _ma(moving_average_type, slow)
        self.signal = _ma(moving_average_type, signal)
        self.histogram = IndicatorDataPoint()

    def _compute(self, value):
        x = self._x(value)
        self.fast.update(None, x)
        self.slow.update(None, x)
        if not self.slow.is_ready:
            return None
        macd = self.fast.current.value - self.slow.current.value
        self.signal.update(None, macd)
        self.histogram = IndicatorDataPoint(None, macd - self.signal.current.value)
        return macd


class RateOfChange(Indicator):
    def __init__(self, period: int, name: str = ""):
        super().__init__(name or f"ROC({period})")
        self._args = (period, name)
        self.period = int(period)
        self.warm_up_period = self.period + 1
        self._w: deque = deque(maxlen=self.period + 1)

    def _compute(self, value):
        self._w.append(self._x(value))
        return (self._w[-1] / self._w[0] - 1) if len(self._w) == self._w.maxlen and self._w[0] else 0.0


class RateOfChangePercent(RateOfChange):
    def _compute(self, value):
        r = super()._compute(value)
        return None if r is None else 100 * r


class Momentum(Indicator):
    def __init__(self, period: int, name: str = ""):
        super().__init__(name or f"MOM({period})")
        self._args = (period, name)
        self.period = int(period)
        self.warm_up_period = self.period + 1
        self._w: deque = deque(maxlen=self.period + 1)

    def _compute(self, value):
        self._w.append(self._x(value))
        return self._w[-1] - self._w[0]


class Maximum(Indicator):
    def __init__(self, period: int, name: str = ""):
        super().__init__(name or f"MAX({period})")
        self._args = (period, name)
        self.period = self.warm_up_period = int(period)
        self._w: deque = deque(maxlen=self.period)

    def _compute(self, value):
        self._w.append(self._x(value))                    # LEAN's helpers feed the close
        return max(self._w)


class Minimum(Maximum):
    def _compute(self, value):
        self._w.append(self._x(value))
        return min(self._w)


class AverageDirectionalIndex(Indicator):
    def __init__(self, period: int, name: str = ""):
        super().__init__(name or f"ADX({period})")
        self._args = (period, name)
        self.period = int(period)
        self.warm_up_period = 2 * self.period
        self._prev: Optional[TradeBar] = None
        self._tr, self._pdm, self._ndm = WildersMovingAverage(period), WildersMovingAverage(period), WildersMovingAverage(period)
        self._adx = WildersMovingAverage(period)
        self.positive_directional_index, self.negative_directional_index = IndicatorDataPoint(), IndicatorDataPoint()

    def _compute(self, bar):
        if not isinstance(bar, TradeBar):
            raise ValueError("ADX needs trade bars (created with self.adx()).")
        p = self._prev
        self._prev = bar
        if p is None:
            return None
        up, dn = bar.high - p.high, p.low - bar.low
        tr = max(bar.high - bar.low, abs(bar.high - p.close), abs(bar.low - p.close))
        self._tr.update(None, tr)
        self._pdm.update(None, up if up > dn and up > 0 else 0.0)
        self._ndm.update(None, dn if dn > up and dn > 0 else 0.0)
        t = self._tr.current.value
        pdi = 100 * self._pdm.current.value / t if t else 0.0
        ndi = 100 * self._ndm.current.value / t if t else 0.0
        if self._tr.samples < self.period:                  # LEAN: DI is 0 until the smoothed sums are ready
            return 0.0
        self.positive_directional_index, self.negative_directional_index = IndicatorDataPoint(None, pdi), IndicatorDataPoint(None, ndi)
        if pdi + ndi == 0:
            return 50.0
        self._adx.update(None, 100 * abs(pdi - ndi) / (pdi + ndi))
        return self._adx.current.value


class RollingWindow:
    """window[0] is the newest value. add(), count, size, is_ready."""

    def __init__(self, size: int):
        self.size = int(size)
        self._d: deque = deque(maxlen=self.size)

    def add(self, x) -> None:
        self._d.appendleft(x)

    Add = add

    def __getitem__(self, i):
        return self._d[i]

    def __len__(self):
        return len(self._d)

    def __iter__(self):
        return iter(self._d)

    @property
    def count(self) -> int:
        return len(self._d)

    Count = count

    @property
    def is_ready(self) -> bool:
        return len(self._d) == self.size

    IsReady = is_ready

    def reset(self) -> None:
        self._d.clear()


# ── portfolio, securities, orders ────────────────────────────────────────────
class Security:
    def __init__(self, ticker: str, resolution: str):
        self.symbol = Symbol(ticker)
        self.Symbol = self.symbol
        self.resolution = resolution
        self.price = self.close = self.open = self.high = self.low = float("nan")
        self.volume = 0.0
        self.has_data = False
        self.fee_model = self.fill_model = self.slippage_model = None

    @property
    def Price(self):
        return self.price

    def set_data_normalization_mode(self, mode) -> None:
        pass                                                     # prices are total-return adjusted (reported)

    SetDataNormalizationMode = set_data_normalization_mode

    def set_leverage(self, leverage) -> None:
        pass

    SetLeverage = set_leverage


class SecurityHolding:
    def __init__(self, symbol: Symbol):
        self.symbol = symbol
        self.quantity = 0.0
        self.average_price = 0.0
        self.price = float("nan")

    @property
    def invested(self) -> bool:
        return abs(self.quantity) > 1e-9

    Invested = invested

    @property
    def is_long(self) -> bool:
        return self.quantity > 1e-9

    @property
    def is_short(self) -> bool:
        return self.quantity < -1e-9

    @property
    def holdings_value(self) -> float:
        return self.quantity * (self.price if np.isfinite(self.price) else 0.0)

    HoldingsValue = holdings_value

    @property
    def absolute_holdings_value(self) -> float:
        return abs(self.holdings_value)

    @property
    def unrealized_profit(self) -> float:
        return self.quantity * ((self.price if np.isfinite(self.price) else 0.0) - self.average_price)

    UnrealizedProfit = unrealized_profit

    @property
    def Quantity(self):
        return self.quantity


class Portfolio(dict):
    def __init__(self, algo: "QCAlgorithm"):
        super().__init__()
        self._algo = algo

    def __getitem__(self, s):
        k = _sym(s)
        if not dict.__contains__(self, k):
            dict.__setitem__(self, k, SecurityHolding(Symbol(k)))
        return dict.__getitem__(self, k)

    def __contains__(self, s):
        return dict.__contains__(self, _sym(s))

    @property
    def total_portfolio_value(self) -> float:
        return self._algo._ctx.nav * self._algo._capital

    TotalPortfolioValue = total_portfolio_value

    @property
    def cash(self) -> float:
        return self._algo._ctx.cash * self._algo._capital

    Cash = cash

    @property
    def total_holdings_value(self) -> float:
        return sum(abs(h.holdings_value) for h in self.values())

    TotalHoldingsValue = total_holdings_value

    @property
    def invested(self) -> bool:
        return any(h.invested for h in self.values())

    Invested = invested

    @property
    def margin_remaining(self) -> float:
        return self.total_portfolio_value - 0.5 * self.total_holdings_value


class OrderEvent:
    def __init__(self, order_id: int, symbol: Symbol, time, status: str, fill_price: float = 0.0, fill_quantity: float = 0.0,
                 message: str = ""):
        self.order_id, self.symbol, self.utc_time, self.status = order_id, symbol, time, status
        self.fill_price, self.fill_quantity, self.message = fill_price, fill_quantity, message
        self.direction = OrderDirection.BUY if fill_quantity > 0 else OrderDirection.SELL if fill_quantity < 0 else OrderDirection.HOLD
        self.is_assignment = False
        self.OrderId, self.Symbol, self.Status, self.FillPrice, self.FillQuantity, self.Direction = (
            order_id, symbol, status, fill_price, fill_quantity, self.direction)

    def __repr__(self):
        return f"OrderEvent({self.order_id} {self.symbol} {self.status} {self.fill_quantity}@{self.fill_price:.4f})"


class OrderTicket:
    def __init__(self, algo, order_id: int, symbol: Symbol, quantity: float, order_type: str, tag: str = "", **prices):
        self._algo = algo
        self.order_id, self.symbol, self.quantity, self.order_type, self.tag = order_id, symbol, quantity, order_type, tag
        self.status = OrderStatus.SUBMITTED if order_id else OrderStatus.INVALID
        self.quantity_filled = 0.0
        self.average_fill_price = 0.0
        self.time = algo.time
        self.prices = prices
        self.OrderId, self.Quantity = order_id, quantity

    @property
    def Status(self):
        return self.status

    @property
    def QuantityFilled(self):
        return self.quantity_filled

    @property
    def AverageFillPrice(self):
        return self.average_fill_price

    def cancel(self, tag: str = "") -> bool:
        if self.status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.INVALID):
            return False
        ok = self._algo._ctx.cancel_order(self.order_id)
        if ok:
            self.status = OrderStatus.CANCELED
            self._algo._emit(OrderEvent(self.order_id, self.symbol, self._algo.time, OrderStatus.CANCELED, message=tag))
        return ok

    Cancel = cancel

    def _fill(self, qty: float, price: float, time) -> str:
        tot = self.quantity_filled + qty
        if tot:
            self.average_fill_price = (self.average_fill_price * self.quantity_filled + price * qty) / tot
        self.quantity_filled = tot
        done = abs(tot) >= abs(self.quantity) - 1e-6
        self.status = OrderStatus.FILLED if done else OrderStatus.PARTIALLY_FILLED
        return self.status


class Transactions:
    def __init__(self, algo):
        self._algo = algo

    def get_open_orders(self, symbol=None) -> List[OrderTicket]:
        return [t for t in self._algo._tickets.values() if t.status in (OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED)
                and (symbol is None or t.symbol == _sym(symbol))]

    GetOpenOrders = get_open_orders
    get_open_order_tickets = get_open_orders
    GetOpenOrderTickets = get_open_orders

    def cancel_open_orders(self, symbol=None, tag: str = "") -> List[OrderTicket]:
        out = []
        for t in self.get_open_orders(symbol):
            if t.cancel(tag):
                out.append(t)
        return out

    CancelOpenOrders = cancel_open_orders

    def get_order_ticket(self, order_id: int) -> Optional[OrderTicket]:
        return self._algo._tickets.get(order_id)

    GetOrderTicket = get_order_ticket

    def get_order_tickets(self) -> List[OrderTicket]:
        return list(self._algo._tickets.values())


# ── schedule ─────────────────────────────────────────────────────────────────
class DateRule:
    def __init__(self, name: str, fn: Callable[[pd.Timestamp, pd.DatetimeIndex, int], bool]):
        self.name, self._fn = name, fn


class TimeRule:
    def __init__(self, name: str):
        self.name = name


class DateRules:
    def __init__(self, algo):
        self._a = algo

    def every_day(self, *a, **k) -> DateRule:
        return DateRule("every_day", lambda d, idx, i: True)

    def every(self, *days) -> DateRule:
        ds = set()
        for d in days:
            ds |= set(d) if isinstance(d, (list, tuple, set)) else {d}
        return DateRule("every", lambda d, idx, i: d.weekday() in ds)

    def _nth(self, period: str, from_end: bool, offset: int) -> DateRule:
        def f(d, idx, i):
            per = idx.to_period(period)
            same = np.nonzero(per == per[i])[0]
            k = (len(same) - 1 - offset) if from_end else offset
            return 0 <= k < len(same) and same[k] == i
        return DateRule(f"{'end' if from_end else 'start'} of {period}+{offset}", f)

    def week_start(self, symbol=None, days_offset: int = 0) -> DateRule:
        return self._nth("W", False, days_offset)

    def week_end(self, symbol=None, days_offset: int = 0) -> DateRule:
        return self._nth("W", True, days_offset)

    def month_start(self, symbol=None, days_offset: int = 0) -> DateRule:
        return self._nth("M", False, days_offset)

    def month_end(self, symbol=None, days_offset: int = 0) -> DateRule:
        return self._nth("M", True, days_offset)

    def year_start(self, symbol=None, days_offset: int = 0) -> DateRule:
        return self._nth("Y", False, days_offset)

    def year_end(self, symbol=None, days_offset: int = 0) -> DateRule:
        return self._nth("Y", True, days_offset)

    def on(self, *dates) -> DateRule:
        ds = {pd.Timestamp(d).normalize() for d in (dates[0] if len(dates) == 1 and isinstance(dates[0], (list, tuple)) else dates)}
        return DateRule("on", lambda d, idx, i: d.normalize() in ds)

    EveryDay, Every, WeekStart, WeekEnd, MonthStart, MonthEnd, YearStart, YearEnd, On = (
        every_day, every, week_start, week_end, month_start, month_end, year_start, year_end, on)


class TimeRules:
    def __init__(self, algo):
        self._a = algo

    def at(self, hour: int = 0, minute: int = 0, *a, **k) -> TimeRule:
        return TimeRule(f"at {hour:02d}:{minute:02d}")

    def after_market_open(self, symbol=None, minutes_after_open: float = 0, *a, **k) -> TimeRule:
        return TimeRule(f"{minutes_after_open} min after the open")

    def before_market_close(self, symbol=None, minutes_before_close: float = 0, *a, **k) -> TimeRule:
        return TimeRule(f"{minutes_before_close} min before the close")

    def every(self, interval=None) -> TimeRule:
        return TimeRule("every interval")

    @property
    def midnight(self) -> TimeRule:
        return TimeRule("midnight")

    @property
    def noon(self) -> TimeRule:
        return TimeRule("noon")

    At, AfterMarketOpen, BeforeMarketClose, Every = at, after_market_open, before_market_close, every


class Schedule:
    def __init__(self, algo):
        self._a = algo
        self.events: List[tuple] = []

    def on(self, date_rule: DateRule, time_rule: TimeRule, callback: Callable, *a) -> None:
        if not callable(callback):
            raise ValueError("schedule.on(date_rule, time_rule, callback): the callback must be a method or function.")
        self.events.append((date_rule, time_rule, callback))
        if time_rule.name not in ("midnight",):
            self._a._approx.add(f"schedule: '{time_rule.name}' runs at the session's close decision (daily data)")

    On = on


class _UniverseHelper:
    def __init__(self, algo):
        self._a = algo
        self.dollar_volume = _DollarVolume(algo)

    def etf(self, ticker, *a, **k):
        t = _sym(ticker)
        if t in ("SPY", "IVV", "VOO", "SPLG"):
            return "__SP500_PIT__"
        raise NotImplementedError(f"universe.etf('{t}'): no free point-in-time constituents for this ETF — only the "
                                  "S&P 500 (SPY, IVV, VOO) is available. Use add_universe(selector) on the S&P 500.")

    ETF = etf


class _DollarVolume:
    def __init__(self, algo):
        self._a = algo

    def top(self, n: int):
        return lambda funds: [f.symbol for f in sorted(funds, key=lambda f: -f.dollar_volume)[:int(n)]]

    Top = top


class _Field(float):
    """A Morningstar-style multi-period field: usable as a number, or via .value / .one_year / .twelve_months."""

    @property
    def value(self):
        return float(self)

    one_year = twelve_months = three_months = value


class _Group:
    def __init__(self, **kv):
        for k, v in kv.items():
            setattr(self, k, v)


# LEAN Fundamental field → Code Lab point-in-time fundamental (SEC filings as first filed, from the next session)
FUND_FIELDS = {"market_cap": "market_cap", "pe_ratio": "earnings_yield", "earning_yield": "earnings_yield",
               "pb_ratio": "book_to_price", "book_value_yield": "book_to_price", "ps_ratio": "sales_to_price",
               "sales_yield": "sales_to_price", "fcf_yield": "fcf_yield", "roe": "roe", "gross_margin": "gross_profitability",
               "debt_to_assets": "leverage", "basic_eps": "eps_ttm", "diluted_eps": "eps_ttm"}


class Fundamental:
    """What a universe selector receives per stock and session: price, volume, dollar volume, and — when the selector uses
    them — point-in-time fundamentals from SEC filings (US filers): market_cap; valuation_ratios.pe_ratio, pb_ratio,
    ps_ratio, earning_yield, fcf_yield; operation_ratios.roe, gross_margin, debt_to_assets;
    earning_reports.basic_eps.twelve_months. Missing values are NaN; has_fundamental_data says whether any exist."""

    def __init__(self, symbol: Symbol, price: float, volume: float, fund: Optional[Dict[str, float]] = None):
        self.symbol, self.price, self.volume = symbol, price, volume
        self.dollar_volume = price * volume
        f = fund or {}
        g = lambda k: float(f.get(k, np.nan)) if f.get(k) is not None else float("nan")
        inv = lambda k: (1.0 / g(k)) if g(k) and np.isfinite(g(k)) and g(k) > 0 else float("nan")
        self.has_fundamental_data = any(np.isfinite(v) for v in f.values() if v is not None)
        self.market_cap = g("market_cap")
        self.valuation_ratios = _Group(pe_ratio=inv("earnings_yield"), earning_yield=g("earnings_yield"),
                                       pb_ratio=inv("book_to_price"), book_value_yield=g("book_to_price"),
                                       ps_ratio=inv("sales_to_price"), sales_yield=g("sales_to_price"), fcf_yield=g("fcf_yield"))
        self.operation_ratios = _Group(roe=_Field(g("roe")), gross_margin=_Field(g("gross_profitability")),
                                       debt_to_assets=_Field(g("leverage")))
        self.earning_reports = _Group(basic_eps=_Field(g("eps_ttm")), diluted_eps=_Field(g("eps_ttm")))
        self.Symbol, self.Price, self.Volume, self.DollarVolume, self.HasFundamentalData, self.MarketCap = (
            symbol, price, volume, self.dollar_volume, self.has_fundamental_data, self.market_cap)
        self.ValuationRatios, self.OperationRatios, self.EarningReports = self.valuation_ratios, self.operation_ratios, self.earning_reports


CoarseFundamental = Fundamental


class SecurityChanges:
    def __init__(self, added: List[Security], removed: List[Security]):
        self.added_securities, self.removed_securities = added, removed
        self.AddedSecurities, self.RemovedSecurities = added, removed


class PortfolioTarget:
    def __init__(self, symbol, quantity_or_percent: float):
        self.symbol, self.quantity = Symbol(_sym(symbol)), float(quantity_or_percent)


class _Settings:
    def __init__(self):
        self.free_portfolio_value_percentage = 0.0025
        self.minimum_order_margin_portfolio_percentage = 0.0
        self.rebalance_portfolio_on_security_changes = False


class _UniverseSettings:
    def __init__(self):
        self.resolution = Resolution.DAILY
        self.leverage = 1.0
        self.data_normalization_mode = DataNormalizationMode.ADJUSTED


# ── the algorithm base class ─────────────────────────────────────────────────
class QCAlgorithm:
    """Subclass this; define initialize() and on_data(slice) (and optionally on_securities_changed, on_order_event,
    on_end_of_day, on_warmup_finished, on_end_of_algorithm). See the module docstring for the semantics."""

    def __init__(self):
        self._ctx = None
        self._capital = 100_000.0
        self.portfolio = Portfolio(self)
        self.securities: Dict[str, Security] = _SymbolDict()
        self.transactions = Transactions(self)
        self.schedule = Schedule(self)
        self.date_rules, self.time_rules = DateRules(self), TimeRules(self)
        self.universe = _UniverseHelper(self)
        self.universe_settings = _UniverseSettings()
        self.settings = _Settings()
        self.time = None
        self.start_date = self.end_date = None
        self.is_warming_up = False
        self.live_mode = False
        self._tickets: Dict[int, OrderTicket] = {}
        self._indicators: Dict[str, List[Indicator]] = {}
        self._selectors: List[Callable] = []
        self._warm = 0
        self._approx: set = set()
        self._params: Dict[str, Any] = {}
        self._log: List[str] = []
        # account model (LEAN-style pre-trade checks): margin (Reg-T 2× buying power) or cash (settled cash, no shorts)
        self._account = AccountType.MARGIN
        self._unsettled: List[tuple] = []                  # (settlement session position, proceeds)
        self._lots: Dict[str, List[List[Any]]] = {}       # symbol → FIFO lots [shares (signed), price, date]
        self._realized = {"short_term": 0.0, "long_term": 0.0}
        self._rejected: List[Dict[str, Any]] = []
        self.benchmark = None
        # PascalCase aliases (the older LEAN Python API)
        self.Portfolio, self.Securities, self.Transactions, self.Schedule = self.portfolio, self.securities, self.transactions, self.schedule
        self.DateRules, self.TimeRules, self.UniverseSettings, self.Settings = self.date_rules, self.time_rules, self.universe_settings, self.settings

    # lifecycle (overridden by the user)
    def initialize(self) -> None:
        pass

    def on_data(self, data: Slice) -> None:
        pass

    def on_securities_changed(self, changes: SecurityChanges) -> None:
        pass

    def on_order_event(self, order_event: OrderEvent) -> None:
        pass

    def on_end_of_day(self, symbol=None) -> None:
        pass

    def on_warmup_finished(self) -> None:
        pass

    def on_end_of_algorithm(self) -> None:
        pass

    @property
    def Time(self):
        return self.time

    @property
    def IsWarmingUp(self):
        return self.is_warming_up

    # set-up (the static importer reads the literal arguments of these; at run time they only record)
    def set_start_date(self, *a, **k) -> None:
        pass

    def set_end_date(self, *a, **k) -> None:
        pass

    def set_cash(self, *a, **k) -> None:
        pass

    def set_benchmark(self, symbol) -> None:
        self.benchmark = _sym(symbol)

    def set_time_zone(self, *a, **k) -> None:
        pass

    def set_brokerage_model(self, *a, **k) -> None:
        if AccountType.CASH in a or k.get("account_type") == AccountType.CASH or k.get("accountType") == AccountType.CASH:
            self._account = AccountType.CASH

    def set_security_initializer(self, *a, **k) -> None:
        self._approx.add("set_security_initializer: ignored (the Code Lab's cost and fill models apply)")

    def set_warm_up(self, period, resolution=None) -> None:
        n = period.days if isinstance(period, timedelta) else int(period)
        self._warm = max(self._warm, n)

    def add_equity(self, ticker: str, resolution: str = Resolution.DAILY, *a, **k) -> Security:
        t = _sym(ticker)
        if resolution not in (Resolution.DAILY, None):
            self._approx.add(f"add_equity('{t}', {resolution}): runs on daily bars")
        return self._add(t, resolution)

    def add_forex(self, ticker: str, resolution: str = Resolution.DAILY, *a, **k) -> Security:
        return self._add(_sym(ticker), resolution)

    def add_crypto(self, ticker: str, resolution: str = Resolution.DAILY, *a, **k) -> Security:
        t = _sym(ticker)
        return self._add(t[:-3] + "-" + t[-3:] if "-" not in t and len(t) > 3 else t, resolution)

    def add_option(self, *a, **k):
        raise NotImplementedError("add_option: no free historical option chains. Use the Options research tab "
                                  "(model-based, labelled) or OPTIONS = [...] synthetic options in a strategy.")

    def add_future(self, *a, **k):
        raise NotImplementedError("add_future: no free roll-adjusted futures history.")

    add_index_option = add_future_option = add_option

    def remove_security(self, symbol) -> None:
        t = _sym(symbol)
        sec = self.securities.get(t)
        if sec is not None:
            self.liquidate(t)
            dict.pop(self.securities, t, None)

    def add_universe(self, selector=None, *a, **k) -> None:
        if selector == "__SP500_PIT__":
            self._selectors.append(lambda funds: [f.symbol for f in funds])
        elif callable(selector):
            self._selectors.append(selector)
        else:
            raise NotImplementedError("add_universe: pass a selector function (fundamentals → symbols) or "
                                      "self.universe.etf('SPY').")

    def _add(self, t: str, resolution) -> Security:
        if t not in self.securities:
            dict.__setitem__(self.securities, t, Security(t, resolution))
        return self.securities[t]

    def symbol(self, ticker: str) -> Symbol:
        return Symbol(ticker)

    def get_parameter(self, name: str, default=None):
        """PARAMS = {"name": [values]} at the top of the file drives walk-forward; get_parameter reads the current one."""
        return getattr(self, "_params", {}).get(name, default)

    # data
    def history(self, symbols, periods=None, resolution=None, *a, **k) -> pd.DataFrame:
        """Daily bars up to the current session (never later): DataFrame indexed by (symbol, time) with open, high,
        low, close, volume — `periods` bars, or a timedelta / (start, end) span."""
        one = isinstance(symbols, (str, Symbol, Security))
        syms = [_sym(symbols)] if one else [_sym(s) for s in symbols]
        d = self._ctx._data
        i = self._ctx.i
        if isinstance(periods, timedelta):
            lo = max(0, int(d.close.index.searchsorted(d.close.index[i] - periods)))
        elif periods is None:
            lo = 0
        else:
            lo = max(0, i + 1 - int(periods))
        frames = []
        for s in syms:
            if s not in d.close.columns:
                continue
            sl = slice(lo, i + 1)
            obs = d.observed[s].iloc[sl]
            f = pd.DataFrame({"open": d.open[s].iloc[sl], "high": d.high[s].iloc[sl], "low": d.low[s].iloc[sl],
                              "close": d.close[s].iloc[sl], "volume": d.volume[s].iloc[sl]})[obs.to_numpy()]
            f.index.name = "time"
            frames.append(pd.concat({s: f}, names=["symbol"]))
        return pd.concat(frames) if frames else pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    # indicators (created and updated automatically with each daily bar)
    def _reg(self, symbol, ind: Indicator, bars: bool = False) -> Indicator:
        ind._bars = bars
        self._indicators.setdefault(_sym(symbol), []).append(ind)
        return ind

    def register_indicator(self, symbol, indicator: Indicator, *a, **k) -> None:
        self._reg(symbol, indicator, isinstance(indicator, (AverageTrueRange, AverageDirectionalIndex)))

    def sma(self, symbol, period: int, *a, **k) -> SimpleMovingAverage:
        return self._reg(symbol, SimpleMovingAverage(period))

    def ema(self, symbol, period: int, *a, **k) -> ExponentialMovingAverage:
        return self._reg(symbol, ExponentialMovingAverage(period))

    def rsi(self, symbol, period: int, moving_average_type=MovingAverageType.WILDERS, *a, **k) -> RelativeStrengthIndex:
        return self._reg(symbol, RelativeStrengthIndex(period, moving_average_type))

    def atr(self, symbol, period: int, moving_average_type=MovingAverageType.WILDERS, *a, **k) -> AverageTrueRange:
        return self._reg(symbol, AverageTrueRange(period, moving_average_type), True)

    def bb(self, symbol, period: int, k: float, moving_average_type=MovingAverageType.SIMPLE, *a, **kw) -> BollingerBands:
        return self._reg(symbol, BollingerBands(period, k, moving_average_type))

    def macd(self, symbol, fast: int, slow: int, signal: int, moving_average_type=MovingAverageType.EXPONENTIAL, *a, **k):
        return self._reg(symbol, MovingAverageConvergenceDivergence(fast, slow, signal, moving_average_type))

    def roc(self, symbol, period: int, *a, **k) -> RateOfChange:
        return self._reg(symbol, RateOfChange(period))

    def rocp(self, symbol, period: int, *a, **k) -> RateOfChangePercent:
        return self._reg(symbol, RateOfChangePercent(period))

    momp = rocp

    def mom(self, symbol, period: int, *a, **k) -> Momentum:
        return self._reg(symbol, Momentum(period))

    def max(self, symbol, period: int, *a, **k) -> Maximum:
        return self._reg(symbol, Maximum(period))

    def min(self, symbol, period: int, *a, **k) -> Minimum:
        return self._reg(symbol, Minimum(period))

    def std(self, symbol, period: int, *a, **k) -> StandardDeviation:
        return self._reg(symbol, StandardDeviation(period))

    def adx(self, symbol, period: int, *a, **k) -> AverageDirectionalIndex:
        return self._reg(symbol, AverageDirectionalIndex(period), True)

    def warm_up_indicator(self, symbol, indicator: Indicator, *a, **k) -> None:
        h = self.history(symbol, indicator.warm_up_period + 1)
        if len(h):
            for t, r in h.loc[_sym(symbol)].iterrows():
                bar = TradeBar(Symbol(_sym(symbol)), t, r.open, r.high, r.low, r.close, r.volume)
                indicator.update(bar if isinstance(indicator, (AverageTrueRange, AverageDirectionalIndex)) else t,
                                 None if isinstance(indicator, (AverageTrueRange, AverageDirectionalIndex)) else r.close)

    def consolidate(self, *a, **k):
        raise NotImplementedError("consolidate / consolidators: only daily bars are available.")

    # orders
    def _order(self, symbol, quantity: float, kind: str, tag: str = "", **prices) -> OrderTicket:
        t = _sym(symbol)
        q = float(int(quantity)) if abs(quantity - int(quantity)) < 1e-9 else float(quantity)
        if self.is_warming_up:
            self._log.append(f"{self.time}: order for {t} ignored during warm-up")
            return OrderTicket(self, 0, Symbol(t), q, kind, tag)
        if t not in self._ctx._data.close.columns:
            raise ValueError(f"Order for {t}: not in the universe (add_equity it, or select it in add_universe).")
        if not q:
            return OrderTicket(self, 0, Symbol(t), 0.0, kind, tag)
        reason = self._pretrade(t, q, prices.get("limit") or prices.get("price"))
        if reason:
            tk = OrderTicket(self, 0, Symbol(t), q, kind, tag, **prices)
            tk.status = OrderStatus.INVALID
            self._rejected.append({"time": str(self.time)[:10], "symbol": t, "quantity": q, "type": kind, "reason": reason})
            self._emit(OrderEvent(0, tk.symbol, self.time, OrderStatus.INVALID, message=reason))
            return tk
        engine_kind = {OrderType.MARKET: "market", OrderType.MARKET_ON_OPEN: "market", OrderType.MARKET_ON_CLOSE: "moc",
                       OrderType.LIMIT: "limit", OrderType.STOP_MARKET: "stop", OrderType.STOP_LIMIT: "stop_limit",
                       OrderType.TRAILING_STOP: "trailing"}[kind]
        oid = self._ctx.order_shares(t, q, engine_kind, price=prices.get("price"), limit=prices.get("limit"),
                                     trail=prices.get("trail"))
        tk = OrderTicket(self, oid, Symbol(t), q, kind, tag, **prices)
        self._tickets[oid] = tk
        self._emit(OrderEvent(oid, tk.symbol, self.time, OrderStatus.SUBMITTED, message=tag))
        return tk

    # ── account model ──
    def _price(self, t: str, hint=None) -> float:
        if hint:
            return float(hint)
        sec = self.securities.get(t)
        px = sec.price if sec is not None and np.isfinite(sec.price) else float(self._ctx.close.get(t, np.nan))
        return px

    def _open_quantity_all(self, t: Optional[str] = None) -> float:
        return sum(tk.quantity - tk.quantity_filled for tk in self.transactions.get_open_orders(t))

    def _reserved(self, buys_only: bool) -> float:
        tot = 0.0
        for tk in self.transactions.get_open_orders():
            rem = tk.quantity - tk.quantity_filled
            if buys_only and rem <= 0:
                continue
            tot += abs(rem) * (self._price(_sym(tk.symbol), tk.prices.get("limit") or tk.prices.get("price")) or 0.0)
        return tot

    def settled_cash(self) -> float:
        """Cash minus sale proceeds not yet settled (T+2 before 2024-05-28, T+1 after; cash accounts trade on this)."""
        i = self._ctx.i
        return self.portfolio.cash - sum(a for due, a in self._unsettled if due > i)

    def _adv(self, t: str) -> float:
        d, i = self._ctx._data, self._ctx.i
        sl = slice(max(0, i - 62), i + 1)
        v = (d.close[t].iloc[sl] * d.volume[t].iloc[sl]).where(d.observed[t].iloc[sl])
        return float(v.mean()) if v.notna().any() else 0.0

    def _pretrade(self, t: str, q: float, price_hint=None) -> Optional[str]:
        """LEAN-style pre-trade validation; a reason string rejects the order (status INVALID)."""
        px = self._price(t, price_hint)
        if not np.isfinite(px) or px <= 0:
            return "No price for this security yet"
        cur = self.portfolio[t].quantity + self._open_quantity_all(t)
        new = cur + q
        grows = abs(new) > abs(cur) + 1e-9 or (cur != 0 and np.sign(new) != np.sign(cur) and new != 0)
        if self._account == AccountType.CASH:
            if new < -1e-9:
                return "Cash accounts cannot sell short"
            if q > 0:
                need = q * px
                avail = self.settled_cash() - self._reserved(buys_only=True)
                if need > avail + 1e-6:
                    return (f"Insufficient settled cash: the order needs ${need:,.0f}, settled cash available is ${avail:,.0f} "
                            "(sale proceeds settle T+1; T+2 before 28 May 2024)")
            return None
        if grows:
            # gross exposure once every open order and this one have filled: Σ |shares held + pending| × price
            names = {k for k, h in self.portfolio.items() if h.invested} | {_sym(tk.symbol) for tk in self.transactions.get_open_orders()} | {t}
            gross = 0.0
            for k in names:
                qk = self.portfolio[k].quantity + self._open_quantity_all(k) + (q if k == t else 0.0)
                pk = px if k == t else self._price(k)
                gross += abs(qk) * (pk if np.isfinite(pk) else 0.0)
            limit = 2.0 * self.portfolio.total_portfolio_value               # Reg-T initial margin: 50%
            if gross > limit + 1e-6:
                return (f"Insufficient buying power: gross exposure would be ${gross:,.0f} against ${limit:,.0f} "
                        "(2× portfolio value, Reg-T initial margin)")
            if new < -1e-9 and (cur >= 0 or new < cur):
                if px < 5.0 or self._adv(t) < 5e6:
                    return ("No shares located to borrow (policy assumption: no shorting below $5 a share or under "
                            "$5m average daily traded value)")
        return None

    def tax_lots(self, symbol) -> List[Dict[str, Any]]:
        """Open lots (FIFO) for a symbol: shares (negative = short), price, date opened."""
        return [{"shares": s_, "price": p_, "date": d_} for s_, p_, d_ in self._lots.get(_sym(symbol), [])]

    def _book_lots(self, t: str, shares: float, px: float, when: str, i: int) -> None:
        lots = self._lots.setdefault(t, [])
        rem = shares
        while abs(rem) > 1e-9 and lots and np.sign(lots[0][0]) != np.sign(rem):
            lot = lots[0]
            closed = min(abs(rem), abs(lot[0])) * np.sign(lot[0])           # signed, as the lot
            pnl = closed * (px - lot[1])
            held = (pd.Timestamp(when) - pd.Timestamp(lot[2])).days
            # US rules: more than a year held → long-term; short sales are short-term
            self._realized["long_term" if (closed > 0 and held > 365) else "short_term"] += pnl
            lot[0] -= closed
            rem += closed
            if abs(lot[0]) < 1e-9:
                lots.pop(0)
        if abs(rem) > 1e-9:
            lots.append([rem, px, when])
        if shares < 0:                                                    # sale proceeds settle later
            lag = 1 if pd.Timestamp(when) >= pd.Timestamp("2024-05-28") else 2
            self._unsettled.append((i + lag, -shares * px))

    def _report(self) -> Dict[str, Any]:
        reasons: Dict[str, int] = {}
        for r in self._rejected:
            key = r["reason"].split(":")[0]
            reasons[key] = reasons.get(key, 0) + 1
        return {"api_version": API_VERSION, "account_type": self._account,
                "orders": len(self._tickets), "rejected": len(self._rejected), "rejected_by_reason": reasons,
                "rejected_last": self._rejected[-20:],
                "realized_pnl": {k: round(v, 2) for k, v in self._realized.items()},
                "open_lots": sum(len(v) for v in self._lots.values()), "approximations": sorted(self._approx),
                "log_tail": self._log[-30:]}

    def market_order(self, symbol, quantity: float, asynchronous: bool = False, tag: str = "", *a, **k) -> OrderTicket:
        return self._order(symbol, quantity, OrderType.MARKET, tag)

    def market_on_open_order(self, symbol, quantity: float, tag: str = "", *a, **k) -> OrderTicket:
        return self._order(symbol, quantity, OrderType.MARKET_ON_OPEN, tag)

    def market_on_close_order(self, symbol, quantity: float, tag: str = "", *a, **k) -> OrderTicket:
        return self._order(symbol, quantity, OrderType.MARKET_ON_CLOSE, tag)

    def limit_order(self, symbol, quantity: float, limit_price: float, tag: str = "", *a, **k) -> OrderTicket:
        return self._order(symbol, quantity, OrderType.LIMIT, tag, price=limit_price)

    def stop_market_order(self, symbol, quantity: float, stop_price: float, tag: str = "", *a, **k) -> OrderTicket:
        return self._order(symbol, quantity, OrderType.STOP_MARKET, tag, price=stop_price)

    def stop_limit_order(self, symbol, quantity: float, stop_price: float, limit_price: float, tag: str = "", *a, **k):
        return self._order(symbol, quantity, OrderType.STOP_LIMIT, tag, price=stop_price, limit=limit_price)

    def trailing_stop_order(self, symbol, quantity: float, trailing_amount: float, trailing_as_percentage: bool = True,
                            tag: str = "", *a, **k) -> OrderTicket:
        if not trailing_as_percentage:
            px = self.securities[_sym(symbol)].price
            trailing_amount = trailing_amount / px if px else trailing_amount
        return self._order(symbol, quantity, OrderType.TRAILING_STOP, tag, trail=trailing_amount)

    def calculate_order_quantity(self, symbol, target: float) -> float:
        t = _sym(symbol)
        sec = self.securities.get(t)
        px = sec.price if sec is not None else float(self._ctx.close.get(t, np.nan))
        if not px or not np.isfinite(px):
            return 0.0
        tpv = self.portfolio.total_portfolio_value * (1 - self.settings.free_portfolio_value_percentage)
        want = math.floor(abs(target) * tpv / px) * (1 if target >= 0 else -1)
        return float(want - self.portfolio[t].quantity - self._open_quantity(t))

    def _open_quantity(self, t: str) -> float:
        return sum(tk.quantity - tk.quantity_filled for tk in self.transactions.get_open_orders(t)
                   if tk.order_type in (OrderType.MARKET, OrderType.MARKET_ON_OPEN))

    def set_holdings(self, symbol, percentage: float = None, liquidate_existing_holdings: bool = False, tag: str = "",
                     *a, **k) -> List[OrderTicket]:
        """Target a fraction of portfolio value (LEAN: quantity from the current price, less the free-cash buffer);
        a list of PortfolioTarget sets several at once."""
        if isinstance(symbol, (list, tuple)):
            targets = {_sym(p.symbol): p.quantity for p in symbol}
        else:
            targets = {_sym(symbol): float(percentage)}
        out = []
        if liquidate_existing_holdings:
            for t, h in list(self.portfolio.items()):
                if h.invested and t not in targets:
                    out += self.liquidate(t)
        for t, w in targets.items():
            q = self.calculate_order_quantity(t, w)
            if q:
                out.append(self.market_order(t, q, tag=tag))
        return out

    def liquidate(self, symbol=None, tag: str = "Liquidated", *a, **k) -> List[OrderTicket]:
        names = [_sym(symbol)] if symbol is not None else [t for t, h in self.portfolio.items() if h.invested]
        out = []
        for t in names:
            self.transactions.cancel_open_orders(t)
            q = self.portfolio[t].quantity
            if abs(q) > 1e-9:
                out.append(self.market_order(t, -q, tag=tag))
        return out

    # output
    def debug(self, msg) -> None:
        self._log.append(f"{self.time}: {msg}")
        print(f"{self.time.date() if self.time is not None else ''} {msg}")

    log = error = debug

    def plot(self, chart: str, series: str, value: float) -> None:
        if self._ctx is not None and not self.is_warming_up:
            self._ctx.plot(chart, series, float(value))

    def quit(self, message: str = "") -> None:
        raise _Quit(message)

    def _emit(self, ev: OrderEvent) -> None:
        self.on_order_event(ev)

    # PascalCase API
    Initialize, OnData = initialize, on_data
    SetStartDate, SetEndDate, SetCash, SetBenchmark, SetWarmUp, SetBrokerageModel, SetTimeZone = (
        set_start_date, set_end_date, set_cash, set_benchmark, set_warm_up, set_brokerage_model, set_time_zone)
    AddEquity, AddForex, AddCrypto, AddOption, AddFuture, AddUniverse, RemoveSecurity = (
        add_equity, add_forex, add_crypto, add_option, add_future, add_universe, remove_security)
    History, RegisterIndicator, WarmUpIndicator, Consolidate = history, register_indicator, warm_up_indicator, consolidate
    SMA, EMA, RSI, ATR, BB, MACD, ROC, ROCP, MOMP, MOM, MAX, MIN, STD, ADX = (
        sma, ema, rsi, atr, bb, macd, roc, rocp, momp, mom, max, min, std, adx)
    MarketOrder, MarketOnOpenOrder, MarketOnCloseOrder, LimitOrder, StopMarketOrder, StopLimitOrder, TrailingStopOrder = (
        market_order, market_on_open_order, market_on_close_order, limit_order, stop_market_order, stop_limit_order,
        trailing_stop_order)
    SetHoldings, Liquidate, CalculateOrderQuantity, Debug, Log, Error, Plot, Quit, Symbol, GetParameter = (
        set_holdings, liquidate, calculate_order_quantity, debug, debug, debug, plot, quit, symbol, get_parameter)
    SettledCash, TaxLots = settled_cash, tax_lots


class _Quit(Exception):
    pass


# The user's class may define PascalCase handlers (OnData, OnSecuritiesChanged, …); the runtime calls whichever exists.
_HANDLERS = {"on_data": "OnData", "on_securities_changed": "OnSecuritiesChanged", "on_order_event": "OnOrderEvent",
             "on_end_of_day": "OnEndOfDay", "on_warmup_finished": "OnWarmupFinished",
             "on_end_of_algorithm": "OnEndOfAlgorithm", "initialize": "Initialize"}


def _handler(algo, name: str) -> Callable:
    cls = type(algo)
    pas = _HANDLERS[name]
    if pas in cls.__dict__ or any(pas in c.__dict__ for c in cls.__mro__[:-1] if c is not QCAlgorithm):
        return getattr(algo, pas)
    return getattr(algo, name)


# ── the runtime: an on_bar(ctx) driving the algorithm ───────────────────────
def adapter(cls, header: Dict[str, Any]) -> Callable:
    """on_bar(ctx) for the engine: builds the algorithm on the first bar (the close before the start), primes indicators
    from the history before the start bar by bar, then each session: fills → order events, universe changes,
    indicator updates, scheduled events, on_data."""
    st: Dict[str, Any] = {}

    def bar_of(d, t, i) -> Optional[TradeBar]:
        if t not in d.close.columns or not bool(d.observed[t].iloc[i]):
            return None
        return TradeBar(Symbol(t), d.close.index[i].to_pydatetime(), float(d.open[t].iloc[i]), float(d.high[t].iloc[i]),
                        float(d.low[t].iloc[i]), float(d.close[t].iloc[i]), float(d.volume[t].iloc[i]))

    def update_indicators(algo, d, i):
        for t, inds in algo._indicators.items():
            b = bar_of(d, t, i)
            if b is None:
                continue
            for ind in inds:
                if getattr(ind, "_bars", False):
                    ind.update(b)
                else:
                    ind.update(b.time, b.close)

    def select(algo, d, i, ctx) -> None:
        if not algo._selectors:
            return
        mem = getattr(d, "members", None)
        cols = list(d.close.columns)
        obs = d.observed.iloc[i].to_numpy()
        ok = obs & (mem.iloc[i].to_numpy() if mem is not None else np.ones(len(cols), bool))
        px, vol = d.close.iloc[i].to_numpy(), d.volume.iloc[i].to_numpy()
        fr = {n: d.fund[n].iloc[i].to_numpy() for n in getattr(d, "fund", {}) or {}}
        funds = [Fundamental(Symbol(c), float(px[k]), float(vol[k]), {n: v[k] for n, v in fr.items()} if fr else None)
                 for k, c in enumerate(cols) if ok[k] and c not in st["static"]]
        chosen = set()
        for f in algo._selectors:
            chosen |= {_sym(s) for s in (f(funds) or [])}
        cur = st["dynamic"]
        added = sorted(chosen - cur)
        removed = sorted(cur - chosen)
        st["dynamic"] = chosen
        if added or removed:
            add_s = [algo._add(t, algo.universe_settings.resolution) for t in added]
            rem_s = [algo.securities.get(t) or Security(t, Resolution.DAILY) for t in removed]
            for t in removed:
                dict.pop(algo.securities, t, None)
            _handler(algo, "on_securities_changed")(SecurityChanges(add_s, rem_s))

    def sync(algo, ctx, i):
        d = ctx._data
        algo.time = d.close.index[i].to_pydatetime()
        units = ctx.units
        cap = algo._capital
        for t in set(list(algo.securities.keys()) + [k for k, h in algo.portfolio.items() if h.invested]):
            if t in d.close.columns:
                px = float(d.close[t].iloc[i])
                sec = algo.securities.get(t)
                if sec is not None:
                    b = bar_of(d, t, i)
                    sec.price = sec.close = px
                    if b is not None:
                        sec.open, sec.high, sec.low, sec.volume, sec.has_data = b.open, b.high, b.low, b.volume, True
                h = algo.portfolio[t]
                h.price = px
                h.quantity = round(float(units.get(t, 0.0)) * cap, 6)        # shares (engine units × capital)

    def process_fills(algo, ctx):
        for ex in ctx.executions:
            ids = ex.get("ids") or []
            qty_left = round(ex["shares"], 6)
            px = ex["price"] * 1.0
            t = ex["ticker"]
            h = algo.portfolio[t]
            prev_q = h.quantity - ex["shares"]
            if abs(h.quantity) > 1e-9 and (prev_q == 0 or np.sign(prev_q) == np.sign(ex["shares"])):
                h.average_price = ((h.average_price * abs(prev_q)) + px * abs(ex["shares"])) / abs(h.quantity)
            elif abs(h.quantity) <= 1e-9:
                h.average_price = 0.0
            algo._book_lots(t, round(ex["shares"], 6), px, ex["date"], ctx.i)
            for oid in ids:
                tk = algo._tickets.get(oid)
                if tk is None or abs(qty_left) < 1e-9:
                    continue
                want = tk.quantity - tk.quantity_filled
                q = want if abs(qty_left) >= abs(want) - 1e-6 else qty_left
                status = tk._fill(q, px, ex["date"])
                qty_left -= q
                algo._emit(OrderEvent(oid, tk.symbol, algo.time, status, px, q))

    def on_bar(ctx, **params):
        d = ctx._data
        i = ctx.i
        if st.get("ctx") is not ctx:                                     # a new backtest run: a fresh algorithm
            st.clear()
            st["ctx"] = ctx
        if "algo" not in st:
            algo = cls()
            algo._ctx = ctx
            algo._params = dict(params)
            algo._capital = ctx.capital
            ctx.hold_by_default = True
            algo.time = d.close.index[max(i, 0)].to_pydatetime()
            _handler(algo, "initialize")()
            st["algo"] = algo
            st["static"] = set(algo.securities.keys())
            st["dynamic"] = set()
            # prime indicators bar by bar on the history before the start; set_warm_up(n) replays its last n bars
            # through on_data with is_warming_up (orders refused)
            first_live = max(i, 0)
            warm_from = max(0, first_live - algo._warm + 1) if algo._warm else first_live + 1   # the n bars ending at the close before the start
            for k in range(0, first_live + 1):
                algo.is_warming_up = k < first_live or algo._warm > 0
                sync(algo, ctx, k) if k >= warm_from else None
                update_indicators(algo, d, k)
                if algo._warm and k >= warm_from:
                    ctx_i = ctx.i
                    ctx.i = k
                    select(algo, d, k, ctx)
                    bars = {t: b for t in algo.securities.keys() if (b := bar_of(d, t, k)) is not None}
                    _handler(algo, "on_data")(Slice(algo.time, bars))
                    ctx.i = ctx_i
            if algo._warm:
                algo.is_warming_up = False
                _handler(algo, "on_warmup_finished")()
            algo.is_warming_up = False
            sync(algo, ctx, i)
            select(algo, d, i, ctx)
            return
        algo = st["algo"]
        algo._ctx = ctx
        sync(algo, ctx, i)
        process_fills(algo, ctx)
        update_indicators(algo, d, i)
        select(algo, d, i, ctx)
        idx = d.close.index
        for dr, tr, cb in algo.schedule.events:
            if dr._fn(idx[i], idx, i):
                cb()
        bars = {t: b for t in algo.securities.keys() if (b := bar_of(d, t, i)) is not None}
        if bars:
            _handler(algo, "on_data")(Slice(algo.time, bars))
        if i == len(idx) - 1:
            _handler(algo, "on_end_of_algorithm")()
        ctx.report = algo._report()

    on_bar.state = st
    return on_bar


# ── static import: header and compatibility report (no user code is executed) ─
SUPPORTED = {
    "initialize", "on_data", "on_securities_changed", "on_order_event", "on_end_of_day", "on_warmup_finished",
    "on_end_of_algorithm", "set_start_date", "set_end_date", "set_cash", "set_benchmark", "set_warm_up", "add_equity",
    "add_forex", "add_crypto", "add_universe", "remove_security", "history", "sma", "ema", "rsi", "atr", "bb", "macd",
    "roc", "rocp", "momp", "mom", "max", "min", "std", "adx", "register_indicator", "warm_up_indicator",
    "market_order", "market_on_open_order", "market_on_close_order", "limit_order", "stop_market_order",
    "stop_limit_order", "trailing_stop_order", "set_holdings", "liquidate", "calculate_order_quantity", "debug", "log",
    "error", "plot", "quit", "symbol", "get_parameter", "settled_cash", "tax_lots", "schedule", "portfolio", "securities", "transactions", "time", "is_warming_up",
    "date_rules", "time_rules", "universe", "universe_settings", "settings", "set_brokerage_model", "set_time_zone",
}
APPROXIMATED = {
    "after_market_open": "runs at the session's close decision (daily data)",
    "before_market_close": "runs at the session's close decision (daily data)",
    "at": "runs at the session's close decision (daily data)",
    "set_security_initializer": "ignored — the Code Lab's cost and fill models apply",
    "set_brokerage_model": "commission model mapped to the Code Lab's broker presets where known; otherwise defaults",
    "set_data_normalization_mode": "prices are split- and dividend-adjusted (total return); raw prices are not used",
    "Resolution.MINUTE": "minute data is not available — runs on daily bars",
    "Resolution.HOUR": "hourly data is not available here — runs on daily bars",
    "Resolution.SECOND": "runs on daily bars", "Resolution.TICK": "runs on daily bars",
    "dollar_volume": "selection by daily dollar volume of point-in-time S&P 500 members",
}
UNSUPPORTED = {
    "add_option": "no free historical option chains", "add_future": "no free roll-adjusted futures history",
    "add_index_option": "no free historical option chains", "add_future_option": "no free historical option chains",
    "consolidate": "consolidators need intraday bars", "subscription_manager": "custom subscriptions are not available",
    "add_data": "custom data sources are not available", "set_alpha": "the Algorithm Framework is not available",
    "set_portfolio_construction": "the Algorithm Framework is not available",
    "set_execution": "the Algorithm Framework is not available", "set_risk_management": "the Algorithm Framework is not available",
    "set_universe_selection": "use add_universe(selector) instead", "option_chain_provider": "no option chains",
    "object_store": "no object store", "asset_classification": "no point-in-time sector codes (data.info has today's sector)",
    "download": "no network access from strategy code", "train": "no background training",
}


def _snake(name: str) -> str:
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i and (not name[i - 1].isupper() or (i + 1 < len(name) and name[i + 1].islower())):
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def find_class(tree: ast.Module) -> Optional[ast.ClassDef]:
    for n in tree.body:
        if isinstance(n, ast.ClassDef) and any(isinstance(b, ast.Name) and b.id == "QCAlgorithm" for b in n.bases):
            return n
    return None


def _lit(node) -> Any:
    try:
        return ast.literal_eval(node)
    except Exception:
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("datetime", "date"):
            try:
                return date(*[ast.literal_eval(a) for a in node.args[:3]])
            except Exception:
                return None
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "Resolution":
            return getattr(Resolution, node.attr, None)
        return None


def _read_call(m: str, args: List[Any], n, h: Dict[str, Any], note) -> None:
    if not args or not isinstance(args[0], str):
        note("unsupported", n.lineno, m, "the ticker must be a literal (or a literal list looped over) in initialize()")
        return
    t = args[0].upper()
    if m == "add_forex":
        t = t if t.endswith("=X") else f"{t}=X"
    elif m == "add_crypto" and "-" not in t:
        t = t[:-3] + "-" + t[-3:]
    if t not in h["universe"]:
        h["universe"].append(t)
    if len(args) > 1 and args[1] not in (None, Resolution.DAILY):
        note("approximated", n.lineno, f"{m} resolution {args[1]}", "runs on daily bars")


def static_header(code: str) -> Dict[str, Any]:
    """Read initialize() without running it: START, END, CAPITAL, UNIVERSE, BENCHMARK, a dynamic universe, the broker
    model, and a compatibility report by line. Raises ValueError when the header cannot be determined."""
    tree = ast.parse(code)
    cls = find_class(tree)
    if cls is None:
        raise ValueError("No class derived from QCAlgorithm.")
    init = next((f for f in cls.body if isinstance(f, ast.FunctionDef) and f.name in ("initialize", "Initialize")), None)
    if init is None:
        raise ValueError("The algorithm has no initialize(self) method.")
    h: Dict[str, Any] = {"universe": [], "dynamic_universe": False, "class": cls.name}
    rep: List[Dict[str, Any]] = []
    seen = set()

    def note(level, line, feature, msg):
        key = (level, feature, line)
        if key not in seen:
            seen.add(key)
            rep.append({"level": level, "line": line, "feature": feature, "message": msg})
    # literal names: class attributes and assignments in initialize (`tickers = [...]`, `self._tickers = [...]`);
    # a call inside `for t in <literal list>:` is read once per element
    env: Dict[str, Any] = {}

    def key(t):
        if isinstance(t, ast.Name):
            return t.id
        if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self":
            return "self." + t.attr
        return None
    for n in list(cls.body) + list(ast.walk(init)):
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and key(n.targets[0]):
            v = _lit(n.value)
            if v is not None:
                env[key(n.targets[0])] = v
                if isinstance(n.targets[0], ast.Name) and n in cls.body:
                    env["self." + n.targets[0].id] = v
    loops: Dict[int, tuple] = {}
    for n in ast.walk(init):
        if isinstance(n, ast.For) and isinstance(n.target, ast.Name):
            items = env.get(key(n.iter)) if key(n.iter) else _lit(n.iter)
            if isinstance(items, (list, tuple)):
                for c in ast.walk(n):
                    loops[id(c)] = (n.target.id, list(items))

    def resolve(node, call):
        v = _lit(node)
        if v is not None:
            return [v]
        k = key(node)
        if k and k in env and not isinstance(env[k], (list, tuple)):
            return [env[k]]
        lp = loops.get(id(call))
        if lp and isinstance(node, ast.Name) and node.id == lp[0]:
            return lp[1]
        return [None]
    for n in ast.walk(init):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == "self":
            m = _snake(n.func.attr)
            if m in ("add_equity", "add_forex", "add_crypto") and n.args:
                firsts = resolve(n.args[0], n)
                rest = [_lit(a) for a in n.args[1:]]
                for f0 in firsts:
                    _read_call(m, [f0] + rest, n, h, note)
                continue
            args = [_lit(a) for a in n.args]
            if m in ("set_start_date", "set_end_date"):
                v = args[0] if len(args) == 1 else (date(*args[:3]) if len(args) >= 3 and all(isinstance(a, int) for a in args[:3]) else None)
                if v is None:
                    note("unsupported", n.lineno, m, "the date must be a literal: set_start_date(2015, 1, 1)")
                else:
                    h["start" if m == "set_start_date" else "end"] = str(v)[:10]
            elif m == "set_cash" and args and isinstance(args[0], (int, float)):
                h["capital"] = float(args[0])
            elif m == "set_benchmark" and args and isinstance(args[0], str):
                h["benchmark"] = args[0].upper()
            elif m == "add_universe":
                h["dynamic_universe"] = True
                note("approximated", n.lineno, "add_universe", "selection runs each session on point-in-time S&P 500 "
                     "members (price, volume, dollar volume; no historical market cap or Morningstar fields)")
            elif m == "set_brokerage_model":
                src = ast.unparse(n)
                h["broker"] = "ibkr" if "Interactive" in src or "INTERACTIVE" in src else "alpaca" if "Alpaca" in src or "ALPACA" in src else None
                h["account_type"] = "cash" if ("AccountType.CASH" in src or "AccountType.Cash" in src) else "margin"
    for n in ast.walk(tree):
        line = getattr(n, "lineno", None)
        if isinstance(n, ast.Attribute):
            a = _snake(n.attr)
            full = f"{n.value.id}.{n.attr}" if isinstance(n.value, ast.Name) else n.attr
            if full in APPROXIMATED:
                note("approximated", line, full, APPROXIMATED[full])
            elif a in UNSUPPORTED:
                note("unsupported", line, n.attr, UNSUPPORTED[a])
            elif a in APPROXIMATED:
                note("approximated", line, n.attr, APPROXIMATED[a])
        elif isinstance(n, ast.ImportFrom) and n.module not in ("AlgorithmImports", "math", "datetime"):
            note("unsupported", line, f"from {n.module} import", "only AlgorithmImports, math and datetime")
    used = {_snake(n.attr) for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    need = sorted({FUND_FIELDS[u] for u in used if u in FUND_FIELDS})
    if need:
        h["fundamentals"] = need
        note("approximated", None, "fundamentals", "point-in-time SEC filings (US filers, as first filed, from the next "
             "session) in place of Morningstar: " + ", ".join(need))
    if not h["universe"] and not h["dynamic_universe"]:
        raise ValueError("initialize() adds no securities (add_equity('SPY') …) and no universe.")
    h["report"] = sorted(rep, key=lambda r: ({"unsupported": 0, "approximated": 1}[r["level"]], r["line"] or 0))
    h["api_version"] = API_VERSION
    return h


def prepare_source(code: str) -> str:
    """`from AlgorithmImports import *` / `from QuantConnect… import` lines become no-ops (every name is already in the
    namespace); line numbers are preserved."""
    out = []
    for ln in code.splitlines():
        s = ln.strip()
        if s.startswith("from AlgorithmImports import") or s.startswith("from QuantConnect") or s == "import AlgorithmImports":
            out.append(ln[:len(ln) - len(ln.lstrip())] + "pass")
        else:
            out.append(ln)
    return "\n".join(out)


NAMES = {k: v for k, v in globals().items() if k in (
    "QCAlgorithm", "Resolution", "OrderStatus", "OrderDirection", "OrderType", "MovingAverageType",
    "DataNormalizationMode", "BrokerageName", "AccountType", "DayOfWeek", "Market", "Symbol", "TradeBar", "Slice",
    "RollingWindow", "SimpleMovingAverage", "ExponentialMovingAverage", "WildersMovingAverage", "RelativeStrengthIndex",
    "AverageTrueRange", "BollingerBands", "MovingAverageConvergenceDivergence", "RateOfChange", "RateOfChangePercent",
    "Momentum", "Maximum", "Minimum", "StandardDeviation", "AverageDirectionalIndex", "IndicatorDataPoint",
    "PortfolioTarget", "SecurityChanges", "Fundamental", "CoarseFundamental", "OrderEvent", "OrderTicket")}
NAMES.update({"timedelta": timedelta, "datetime": datetime, "date": date})
