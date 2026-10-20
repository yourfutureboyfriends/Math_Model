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
  framework     alpha → portfolio construction → risk → execution models (LEAN's built-ins and your own), insights with
                periods in sessions, manual and fundamental universe selection models.
  consolidators daily bars → weekly / monthly / quarterly / yearly / n-session bars (Calendar, TradeBarConsolidator).
  storage       object_store kept between server runs of the same algorithm class; add_data(…, "name") = uploaded CSV.
  not available historical option / future chains, intraday bars, live brokerages — the importer's compatibility
                report lists them by line.
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
    Usa = USA


class SecurityType(_Enum):
    EQUITY, FOREX, CRYPTO, CFD, INDEX, OPTION, FUTURE = "equity", "forex", "crypto", "cfd", "index", "option", "future"
    Equity, Forex, Crypto, Cfd, Index, Option, Future = EQUITY, FOREX, CRYPTO, CFD, INDEX, OPTION, FUTURE


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


# quote currencies, longest first: BTCUSDT → BTC / USDT (not BTCU / SDT)
_CRYPTO_QUOTES = ("FDUSD", "USDT", "USDC", "BUSD", "TUSD", "USDP", "DAI", "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF",
                  "BTC", "ETH", "BNB")
_STABLE = {"USDT", "USDC", "BUSD", "TUSD", "USDP", "DAI", "FDUSD"}


def crypto_pair(ticker: str):
    """'BTCUSDT' / 'BTC-USDT' / 'BTC/USDT' → ('BTC', 'USDT'); None when no known quote currency ends it."""
    t = str(ticker).upper().replace("/", "-")
    if "-" in t:
        b, q = t.split("-", 1)
        return (b, q) if b and q else None
    for q in _CRYPTO_QUOTES:
        if t.endswith(q) and len(t) > len(q):
            return t[:-len(q)], q
    return None


def crypto_yahoo(ticker: str):
    """The free daily series for a crypto pair: Yahoo's BASE-QUOTE; a stablecoin quote uses BASE-USD (≈ 1:1). Returns
    (yahoo ticker, approximation note or None)."""
    p = crypto_pair(ticker)
    if p is None:
        return str(ticker).upper(), None
    b, q = p
    if q in _STABLE:
        return f"{b}-USD", f"{b}{q}: priced from {b}-USD ({q} taken as 1 USD)"
    return f"{b}-{q}", None


def _sym(x: Any) -> str:
    return x.value if isinstance(x, Symbol) else (x.symbol.value if isinstance(x, Security) else str(x).upper())


class TradeBar:
    def __init__(self, symbol: Symbol, time: datetime, o: float, h: float, l: float, c: float, v: float):
        self.symbol, self.time, self.end_time = symbol, time, time
        self.open, self.high, self.low, self.close, self.volume = o, h, l, c, v
        self.value = self.price = c
        self.period = timedelta(days=1)
        self.Open, self.High, self.Low, self.Close, self.Volume, self.Value = o, h, l, c, v, c


class PythonData:
    """Custom data (LEAN's PythonData). Subclass it — get_source / reader are not called: the data is the CSV uploaded
    under the name passed to add_data (Quant Lab → Custom data), aligned as of each session. A point exposes .value
    (the 'value' column, else the first), .time, .symbol and every column: point["sentiment"] or point.sentiment."""

    def __init__(self, symbol=None, time=None, values: Optional[Dict[str, float]] = None):
        self.symbol = Symbol(_sym(symbol)) if symbol is not None else None
        self.time = self.end_time = time
        self._v = dict(values or {})
        self.value = float(self._v.get("value", next(iter(self._v.values()), float("nan"))))
        self.price = self.close = self.value
        self.Value, self.Symbol, self.Time = self.value, self.symbol, time

    def __getitem__(self, k):
        return self._v[str(k).lower()]

    def __getattr__(self, k):
        v = self.__dict__.get("_v") or {}
        if k.lower() in v:
            return v[k.lower()]
        raise AttributeError(k)

    def get_source(self, *a, **k):
        return None

    def reader(self, *a, **k):
        return None

    GetSource, Reader = get_source, reader


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


class MorningstarSectorCode(_Enum):
    BASIC_MATERIALS, CONSUMER_CYCLICAL, FINANCIAL_SERVICES, REAL_ESTATE = 101, 102, 103, 104
    CONSUMER_DEFENSIVE, HEALTHCARE, UTILITIES = 205, 206, 207
    COMMUNICATION_SERVICES, ENERGY, INDUSTRIALS, TECHNOLOGY = 308, 309, 310, 311
    BasicMaterials, ConsumerCyclical, FinancialServices, RealEstate = 101, 102, 103, 104
    ConsumerDefensive, Healthcare, Utilities = 205, 206, 207
    CommunicationServices, Energy, Industrials, Technology = 308, 309, 310, 311


# Yahoo and GICS sector names → Morningstar sector codes (LEAN's asset_classification.morningstar_sector_code)
_MS_SECTOR = {"technology": 311, "information technology": 311, "financial services": 103, "financials": 103,
              "healthcare": 206, "health care": 206, "consumer cyclical": 102, "consumer discretionary": 102,
              "consumer defensive": 205, "consumer staples": 205, "energy": 309, "utilities": 207, "industrials": 310,
              "basic materials": 101, "materials": 101, "real estate": 104, "communication services": 308,
              "communication": 308, "telecommunication services": 308}


def morningstar_sector(name: Optional[str]) -> float:
    return float(_MS_SECTOR.get(str(name or "").strip().lower(), float("nan")))


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

    def __init__(self, symbol: Symbol, price: float, volume: float, fund: Optional[Dict[str, float]] = None,
                 sector: Optional[str] = None):
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
        # today's sector for every date (point-in-time sector history is not free) — reported as approximated
        code = morningstar_sector(sector)
        self.asset_classification = _Group(morningstar_sector_code=code, MorningstarSectorCode=code,
                                           morningstar_industry_group_code=float("nan"), morningstar_industry_code=float("nan"),
                                           sector_name=sector)
        self.AssetClassification = self.asset_classification
        self.Symbol, self.Price, self.Volume, self.DollarVolume, self.HasFundamentalData, self.MarketCap = (
            symbol, price, volume, self.dollar_volume, self.has_fundamental_data, self.market_cap)
        self.ValuationRatios, self.OperationRatios, self.EarningReports = self.valuation_ratios, self.operation_ratios, self.earning_reports


CoarseFundamental = Fundamental


class SecurityChanges:
    def __init__(self, added: List[Security], removed: List[Security]):
        self.added_securities, self.removed_securities = added, removed
        self.AddedSecurities, self.RemovedSecurities = added, removed


class PortfolioTarget:
    """A target holding. In the framework `quantity` is shares (PortfolioTarget.percent converts a fraction of portfolio
    value); in a set_holdings([...]) list it is a fraction, as in LEAN."""

    def __init__(self, symbol, quantity_or_percent: float, tag: str = ""):
        self.symbol, self.quantity = Symbol(_sym(symbol)), float(quantity_or_percent)
        self.percent_target = None
        self.tag = tag
        self.Symbol, self.Quantity = self.symbol, self.quantity

    @staticmethod
    def percent(algorithm, symbol, percent: float, *a, **k) -> Optional["PortfolioTarget"]:
        t = _sym(symbol)
        px = algorithm._price(t)
        if not px or not np.isfinite(px):
            return None
        tpv = algorithm.portfolio.total_portfolio_value * (1 - algorithm.settings.free_portfolio_value_percentage)
        q = math.floor(abs(percent) * tpv / px) * (1 if percent >= 0 else -1)
        tg = PortfolioTarget(t, q)
        tg.percent_target = float(percent)
        return tg

    Percent = percent


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


# ── Algorithm Framework (alpha → portfolio construction → risk → execution) ──
class InsightDirection(_Enum):
    UP, DOWN, FLAT = 1, -1, 0
    Up, Down, Flat = UP, DOWN, FLAT


class InsightType(_Enum):
    PRICE, VOLATILITY = "price", "volatility"
    Price, Volatility = PRICE, VOLATILITY


class PortfolioBias(_Enum):
    LONG, SHORT, LONG_SHORT = 1, -1, 0
    Long, Short, LongShort = LONG, SHORT, LONG_SHORT


def _period_days(period) -> int:
    """An insight period in sessions: timedelta → its days (≥ 1), an int → that many daily bars, a Resolution → 1."""
    if isinstance(period, timedelta):
        return max(1, int(round(period.total_seconds() / 86400)))
    if isinstance(period, (int, float)) and not isinstance(period, bool):
        return max(1, int(period))
    return 1


class Insight:
    """A prediction: symbol, direction (UP / DOWN / FLAT), how long it holds (period), optional magnitude, confidence and
    weight. Active from the session it is emitted until its period (in sessions on daily data) has passed."""

    def __init__(self, symbol, period, type=InsightType.PRICE, direction=InsightDirection.FLAT, magnitude=None,
                 confidence=None, source_model=None, weight=None, tag=""):
        self.symbol = Symbol(_sym(symbol))
        self.period = period
        self.type, self.direction = type, int(direction)
        self.magnitude, self.confidence, self.weight = magnitude, confidence, weight
        self.source_model, self.tag = source_model, tag
        self.generated_time = self.close_time = None
        self._bars = _period_days(period)
        self._born = None
        self.Symbol, self.Direction, self.Period, self.Magnitude, self.Confidence, self.Weight = (
            self.symbol, self.direction, period, magnitude, confidence, weight)

    @staticmethod
    def price(symbol, period, direction, magnitude=None, confidence=None, source_model=None, weight=None, tag="") -> "Insight":
        return Insight(symbol, period, InsightType.PRICE, direction, magnitude, confidence, source_model, weight, tag)

    Price = price

    @staticmethod
    def group(*insights) -> List["Insight"]:
        return list(insights[0]) if len(insights) == 1 and isinstance(insights[0], (list, tuple)) else list(insights)

    Group = group

    def is_active(self, i: int) -> bool:
        return self._born is not None and i < self._born + self._bars

    def __repr__(self):
        return f"Insight({self.symbol} {['DOWN', 'FLAT', 'UP'][self.direction + 1]} {self._bars}d)"


def _call(obj, snake: str, *args):
    """A model method by its snake_case or PascalCase name (LEAN Python accepts both)."""
    pas = "".join(w[:1].upper() + w[1:] for w in snake.split("_"))
    fn = getattr(obj, pas, None) if type(obj).__dict__.get(pas) or any(pas in c.__dict__ for c in type(obj).__mro__[:-1]
                                                                     if c.__module__ != __name__) else None
    return (fn or getattr(obj, snake))(*args)


def _as_list(x) -> list:
    if x is None:
        return []
    if isinstance(x, (list, tuple)):
        return list(x)
    if isinstance(x, Insight):
        return [x]
    return list(x)


class AlphaModel:
    """Override update(algorithm, data) → list of Insight; optionally on_securities_changed(algorithm, changes)."""

    def __init__(self, *a, **k):
        self.name = type(self).__name__

    def update(self, algorithm, data) -> List[Insight]:
        return []

    def on_securities_changed(self, algorithm, changes) -> None:
        pass


class NullAlphaModel(AlphaModel):
    pass


class ConstantAlphaModel(AlphaModel):
    """The same insight for every security, re-emitted when the previous one expires."""

    def __init__(self, type, direction, period, magnitude=None, confidence=None, weight=None):
        super().__init__()
        self.type, self.direction, self.period = type, direction, period
        self.magnitude, self.confidence, self.weight = magnitude, confidence, weight
        self._last: Dict[str, int] = {}

    def update(self, algorithm, data):
        out, i, n = [], algorithm._ctx.i, _period_days(self.period)
        for t in list(algorithm.securities.keys()):
            if t in data and (t not in self._last or i - self._last[t] >= n):
                self._last[t] = i
                out.append(Insight(t, self.period, self.type, self.direction, self.magnitude, self.confidence,
                                   self.name, self.weight))
        return out


class EmaCrossAlphaModel(AlphaModel):
    """UP when the fast EMA crosses above the slow one, DOWN when below (LEAN's model); insight period = fast bars."""

    def __init__(self, fast_period: int = 12, slow_period: int = 26, resolution=Resolution.DAILY):
        super().__init__()
        self.fast_period, self.slow_period = int(fast_period), int(slow_period)
        self._s: Dict[str, Dict[str, Any]] = {}

    def on_securities_changed(self, algorithm, changes):
        for sec in changes.added_securities:
            t = _sym(sec)
            if t not in self._s:
                f, s = algorithm.ema(t, self.fast_period), algorithm.ema(t, self.slow_period)
                algorithm.warm_up_indicator(t, f)
                algorithm.warm_up_indicator(t, s)
                self._s[t] = {"fast": f, "slow": s, "above": None}
        for sec in changes.removed_securities:
            self._s.pop(_sym(sec), None)

    def update(self, algorithm, data):
        out = []
        for t, st in self._s.items():
            f, s = st["fast"], st["slow"]
            if not (f.is_ready and s.is_ready) or t not in data:
                continue
            above = f.current.value > s.current.value
            if st["above"] is not None and above != st["above"]:
                out.append(Insight.price(t, timedelta(days=self.fast_period),
                                         InsightDirection.UP if above else InsightDirection.DOWN, source_model=self.name))
            st["above"] = above
        return out


class MacdAlphaModel(AlphaModel):
    """Direction of the MACD histogram (normalised by price) beyond a small bounce threshold; LEAN's model."""

    def __init__(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9,
                 moving_average_type=MovingAverageType.EXPONENTIAL, resolution=Resolution.DAILY):
        super().__init__()
        self.args = (int(fast_period), int(slow_period), int(signal_period), moving_average_type)
        self._s: Dict[str, Dict[str, Any]] = {}
        self.bounce = 0.01

    def on_securities_changed(self, algorithm, changes):
        for sec in changes.added_securities:
            t = _sym(sec)
            if t not in self._s:
                m = algorithm.macd(t, *self.args)
                algorithm.warm_up_indicator(t, m)
                self._s[t] = {"macd": m, "dir": InsightDirection.FLAT}
        for sec in changes.removed_securities:
            self._s.pop(_sym(sec), None)

    def update(self, algorithm, data):
        out = []
        for t, st in self._s.items():
            m = st["macd"]
            px = algorithm.securities[t].price if t in algorithm.securities else float("nan")
            if not m.is_ready or not px or not np.isfinite(px) or t not in data:
                continue
            nh = (m.current.value - m.signal.current.value) / px
            d = InsightDirection.UP if nh > self.bounce else InsightDirection.DOWN if nh < -self.bounce else InsightDirection.FLAT
            if d != st["dir"]:
                st["dir"] = d
                out.append(Insight.price(t, timedelta(days=self.args[0]), d, source_model=self.name))
        return out


class RsiAlphaModel(AlphaModel):
    """RSI below 30 → UP, above 70 → DOWN, emitted when the state changes (LEAN's model); period = RSI period."""

    def __init__(self, period: int = 14, resolution=Resolution.DAILY):
        super().__init__()
        self.period = int(period)
        self._s: Dict[str, Dict[str, Any]] = {}

    def on_securities_changed(self, algorithm, changes):
        for sec in changes.added_securities:
            t = _sym(sec)
            if t not in self._s:
                r = algorithm.rsi(t, self.period, MovingAverageType.WILDERS)
                algorithm.warm_up_indicator(t, r)
                self._s[t] = {"rsi": r, "state": "middle"}
        for sec in changes.removed_securities:
            self._s.pop(_sym(sec), None)

    def update(self, algorithm, data):
        out = []
        for t, st in self._s.items():
            r = st["rsi"]
            if not r.is_ready or t not in data:
                continue
            v = r.current.value
            state = "low" if v < 30 else "high" if v > 70 else "middle"
            if state != st["state"] and state != "middle":
                out.append(Insight.price(t, timedelta(days=self.period),
                                         InsightDirection.UP if state == "low" else InsightDirection.DOWN,
                                         source_model=self.name))
            st["state"] = state
        return out


class HistoricalReturnsAlphaModel(AlphaModel):
    """Direction of each security's return over the lookback, with that return as the magnitude."""

    def __init__(self, lookback: int = 1, resolution=Resolution.DAILY):
        super().__init__()
        self.lookback = int(lookback)

    def update(self, algorithm, data):
        out = []
        for t in list(algorithm.securities.keys()):
            if t not in data:
                continue
            h = algorithm.history(t, self.lookback + 1)
            if len(h) < self.lookback + 1:
                continue
            c = h["close"].to_numpy()
            r = c[-1] / c[0] - 1
            out.append(Insight.price(t, timedelta(days=self.lookback), InsightDirection.UP if r > 0 else
                                     InsightDirection.DOWN if r < 0 else InsightDirection.FLAT, magnitude=float(r),
                                     source_model=self.name))
        return out


class PortfolioConstructionModel:
    """Override create_targets(algorithm, insights) → list of PortfolioTarget. `rebalance`: a Resolution (every
    session), a timedelta, a function of the time returning the next rebalance time, or None (only when insights
    change)."""

    def __init__(self, rebalance=Resolution.DAILY, portfolio_bias=PortfolioBias.LONG_SHORT, *a, **k):
        self.rebalance, self.portfolio_bias = rebalance, portfolio_bias
        self._next = None

    def create_targets(self, algorithm, insights) -> List["PortfolioTarget"]:
        return []

    def on_securities_changed(self, algorithm, changes) -> None:
        pass

    def _due(self, algorithm) -> bool:
        r, now = self.rebalance, algorithm.time
        if r is None:
            return False
        if isinstance(r, str):                               # a Resolution: every session on daily data
            return True
        if isinstance(r, timedelta):
            if self._next is None or now >= self._next:
                self._next = now + r
                return True
            return False
        if callable(r):
            if self._next is None or now >= self._next:
                nxt = r(now)
                self._next = nxt if isinstance(nxt, datetime) else now + timedelta(days=1)
                return True
        return False

    def _bias_ok(self, d: int) -> bool:
        return not ((self.portfolio_bias == PortfolioBias.LONG and d < 0) or (self.portfolio_bias == PortfolioBias.SHORT and d > 0))

    def _weights_to_targets(self, algorithm, weights: Dict[str, float], insights: List[Insight]) -> List["PortfolioTarget"]:
        tg = [PortfolioTarget.percent(algorithm, t, w) for t, w in weights.items()]
        for ins in insights:                                 # filtered out by the bias → flat
            if ins.symbol.value not in weights:
                tg.append(PortfolioTarget(ins.symbol, 0))
        return [t for t in tg if t is not None]


class NullPortfolioConstructionModel(PortfolioConstructionModel):
    def __init__(self, *a, **k):
        super().__init__(None)


class EqualWeightingPortfolioConstructionModel(PortfolioConstructionModel):
    """Equal weight across the active insights' directions (FLAT → 0), as LEAN."""

    def create_targets(self, algorithm, insights):
        act = [i for i in insights if self._bias_ok(i.direction)]
        n = sum(1 for i in act if i.direction != 0)
        w = {i.symbol.value: (i.direction / n if n else 0.0) for i in act}
        return self._weights_to_targets(algorithm, w, insights)


class InsightWeightingPortfolioConstructionModel(PortfolioConstructionModel):
    """Weights ∝ each insight's |weight| (scaled down so gross ≤ 100%), signed by direction."""

    _attr = "weight"

    def create_targets(self, algorithm, insights):
        act = [i for i in insights if self._bias_ok(i.direction) and getattr(i, self._attr) is not None]
        tot = sum(abs(float(getattr(i, self._attr))) for i in act)
        scale = 1.0 / tot if tot > 1 else 1.0
        w = {i.symbol.value: i.direction * abs(float(getattr(i, self._attr))) * scale for i in act}
        return self._weights_to_targets(algorithm, w, insights)


class ConfidenceWeightingPortfolioConstructionModel(InsightWeightingPortfolioConstructionModel):
    _attr = "confidence"


class RiskParityPortfolioConstructionModel(PortfolioConstructionModel):
    """Inverse-volatility weights (60 sessions) across the insights' directions — a simple risk-parity allocation."""

    def __init__(self, rebalance=Resolution.DAILY, portfolio_bias=PortfolioBias.LONG_SHORT, lookback: int = 60, *a, **k):
        super().__init__(rebalance, portfolio_bias)
        self.lookback = int(lookback)

    def create_targets(self, algorithm, insights):
        act = [i for i in insights if self._bias_ok(i.direction) and i.direction != 0]
        inv = {}
        for i in act:
            h = algorithm.history(i.symbol, self.lookback + 1)
            r = h["close"].pct_change().dropna() if len(h) > 2 else None
            sd = float(r.std()) if r is not None and len(r) > 2 else 0.0
            if sd > 0:
                inv[i.symbol.value] = (i.direction, 1.0 / sd)
        tot = sum(v for _, v in inv.values())
        w = {t: d * v / tot for t, (d, v) in inv.items()} if tot else {}
        return self._weights_to_targets(algorithm, w, insights)


class RiskManagementModel:
    """Override manage_risk(algorithm, targets) → targets that override the portfolio model's for their symbols."""

    def manage_risk(self, algorithm, targets) -> List["PortfolioTarget"]:
        return []

    def on_securities_changed(self, algorithm, changes) -> None:
        pass


class NullRiskManagementModel(RiskManagementModel):
    pass


class MaximumDrawdownPercentPerSecurity(RiskManagementModel):
    """Flatten a holding once its unrealized loss exceeds the limit (LEAN: 5%)."""

    def __init__(self, maximum_drawdown_percent: float = 0.05):
        self.limit = abs(float(maximum_drawdown_percent))

    def manage_risk(self, algorithm, targets):
        out = []
        for t, h in algorithm.portfolio.items():
            if h.invested and h.average_price and np.isfinite(h.price):
                pnl = (h.price / h.average_price - 1) * (1 if h.quantity > 0 else -1)
                if pnl < -self.limit:
                    out.append(PortfolioTarget(t, 0))
        return out


class MaximumUnrealizedProfitPercentPerSecurity(RiskManagementModel):
    """Take profit: flatten a holding once its unrealized gain exceeds the limit (LEAN: 5%)."""

    def __init__(self, maximum_unrealized_profit_percent: float = 0.05):
        self.limit = abs(float(maximum_unrealized_profit_percent))

    def manage_risk(self, algorithm, targets):
        out = []
        for t, h in algorithm.portfolio.items():
            if h.invested and h.average_price and np.isfinite(h.price):
                pnl = (h.price / h.average_price - 1) * (1 if h.quantity > 0 else -1)
                if pnl > self.limit:
                    out.append(PortfolioTarget(t, 0))
        return out


class MaximumDrawdownPercentPortfolio(RiskManagementModel):
    """Flatten everything once the portfolio is down more than the limit from its start (or, trailing, its peak)."""

    def __init__(self, maximum_drawdown_percent: float = 0.05, is_trailing: bool = False):
        self.limit, self.trailing = abs(float(maximum_drawdown_percent)), bool(is_trailing)
        self._ref = None

    def manage_risk(self, algorithm, targets):
        v = algorithm.portfolio.total_portfolio_value
        if self._ref is None or (self.trailing and v > self._ref):
            self._ref = v
        if self._ref and v / self._ref - 1 < -self.limit:
            self._ref = v                                       # reset after liquidating, as LEAN
            return [PortfolioTarget(t, 0) for t, h in algorithm.portfolio.items() if h.invested]
        return []


class TrailingStopRiskManagementModel(RiskManagementModel):
    """Flatten a holding once it falls the given fraction from its best price since entry."""

    def __init__(self, maximum_drawdown_percent: float = 0.05):
        self.limit = abs(float(maximum_drawdown_percent))
        self._best: Dict[str, float] = {}

    def manage_risk(self, algorithm, targets):
        out = []
        for t, h in algorithm.portfolio.items():
            if not h.invested or not np.isfinite(h.price):
                self._best.pop(t, None)
                continue
            long = h.quantity > 0
            b = self._best.get(t, h.price)
            b = max(b, h.price) if long else min(b, h.price)
            self._best[t] = b
            dd = (h.price / b - 1) if long else (b / h.price - 1)
            if dd < -self.limit:
                out.append(PortfolioTarget(t, 0))
                self._best.pop(t, None)
        return out


class CompositeRiskManagementModel(RiskManagementModel):
    def __init__(self, *models):
        self.models = list(models[0]) if len(models) == 1 and isinstance(models[0], (list, tuple)) else list(models)

    def manage_risk(self, algorithm, targets):
        out = []
        for m in self.models:
            out += _as_list(_call(m, "manage_risk", algorithm, targets))
        return out


class ExecutionModel:
    """Override execute(algorithm, targets): place the orders that move holdings to the targets."""

    def execute(self, algorithm, targets) -> None:
        pass

    def on_securities_changed(self, algorithm, changes) -> None:
        pass


class NullExecutionModel(ExecutionModel):
    pass


class ImmediateExecutionModel(ExecutionModel):
    """Market orders for the difference between each target and holdings plus open orders (LEAN)."""

    def execute(self, algorithm, targets):
        for tg in targets:
            t = _sym(tg.symbol)
            q = tg.quantity - algorithm.portfolio[t].quantity - algorithm._open_quantity_all(t)
            if abs(q) >= 1:
                algorithm.market_order(t, math.floor(abs(q)) * (1 if q > 0 else -1), tag="framework")


# daily data: these execute at the next session's open like ImmediateExecutionModel (reported)
VolumeWeightedAveragePriceExecutionModel = StandardDeviationExecutionModel = SpreadExecutionModel = ImmediateExecutionModel


class UniverseSelectionModel:
    pass


class ManualUniverseSelectionModel(UniverseSelectionModel):
    """A fixed list of securities (read without running the code, like add_equity)."""

    def __init__(self, symbols=None, *a, **k):
        self.symbols = [_sym(s) for s in (symbols or [])]


class FundamentalUniverseSelectionModel(UniverseSelectionModel):
    """select(fundamentals) → symbols each session on point-in-time S&P 500 members (as add_universe)."""

    def __init__(self, selector=None, *a, **k):
        self.selector = selector

    def select(self, algorithm, fundamentals):
        return self.selector(fundamentals) if self.selector else []


CoarseFundamentalUniverseSelectionModel = FundamentalUniverseSelectionModel


class _Framework:
    """The per-algorithm framework state: models, active insights per symbol, last targets."""

    def __init__(self):
        self.alphas: List[Any] = []
        self.pcm: Any = None
        self.execution: Any = None
        self.risk: List[Any] = []
        self.active: Dict[str, Insight] = {}
        self.emitted: List[Insight] = []
        self.targets: Dict[str, Any] = {}
        self.count = 0
        self.used = False

    def models(self) -> list:
        return self.alphas + [m for m in (self.pcm, self.execution) if m is not None] + self.risk

    def securities_changed(self, algo, changes) -> None:
        for m in self.models():
            if hasattr(m, "on_securities_changed") or hasattr(m, "OnSecuritiesChanged"):
                _call(m, "on_securities_changed", algo, changes)

    def step(self, algo, data) -> None:
        """One session: insights from the alphas → targets (when insights change or the model's rebalance is due) →
        risk adjustments → execution."""
        if not self.used:
            return
        i = algo._ctx.i
        new = list(self.emitted)
        self.emitted.clear()
        for a in self.alphas:
            new += _as_list(_call(a, "update", algo, data))
        for ins in new:
            ins._born = i
            ins.generated_time = algo.time
            ins.close_time = algo.time + timedelta(days=ins._bars)
            self.active[ins.symbol.value] = ins
        self.count += len(new)
        expired = [t for t, ins in self.active.items() if not ins.is_active(i)]
        pcm = self.pcm or NullPortfolioConstructionModel()
        due = pcm._due(algo) if isinstance(pcm, PortfolioConstructionModel) else True
        if new or expired or due:
            for t in expired:                                   # an insight whose period ended no longer counts
                self.active.pop(t, None)
            live = list(self.active.values())
            tg = _as_list(_call(pcm, "create_targets", algo, live))
            got = {_sym(t.symbol) for t in tg}
            if not isinstance(pcm, NullPortfolioConstructionModel):
                tg += [PortfolioTarget(t, 0) for t in expired if t not in got and algo.portfolio[t].invested]
            for t in tg:
                self.targets[_sym(t.symbol)] = t
        adj = []
        for r in self.risk:
            adj += _as_list(_call(r, "manage_risk", algo, list(self.targets.values())))
        for t in adj:
            self.targets[_sym(t.symbol)] = t
        if self.targets:
            _call(self.execution or ImmediateExecutionModel(), "execute", algo, list(self.targets.values()))
            # targets reached (or already flat) are done; unfilled ones stay for the next session
            self.targets = {s: t for s, t in self.targets.items()
                            if abs(t.quantity - algo.portfolio[s].quantity - algo._open_quantity_all(s)) >= 1}


# ── consolidators: daily bars → weekly, monthly, quarterly or n-session bars ──
class Calendar(_Enum):
    WEEKLY, MONTHLY, QUARTERLY, YEARLY = "W", "M", "Q", "Y"
    Weekly, Monthly, Quarterly, Yearly = WEEKLY, MONTHLY, QUARTERLY, YEARLY


class _Event:
    """`consolidator.data_consolidated += handler` (handler(sender, bar)), as in LEAN."""

    def __init__(self):
        self.handlers: List[Callable] = []

    def __iadd__(self, fn):
        self.handlers.append(fn)
        return self

    def __isub__(self, fn):
        if fn in self.handlers:
            self.handlers.remove(fn)
        return self

    def fire(self, sender, bar) -> None:
        for h in list(self.handlers):
            h(sender, bar)


class TradeBarConsolidator:
    """Builds bars from daily bars: a Calendar period (WEEKLY / MONTHLY / QUARTERLY / YEARLY), a whole number of sessions,
    or a timedelta of whole days (7 → weekly, 30/31 → monthly, else that many sessions). A bar is emitted on the last
    session of its period. Intraday periods need intraday data, which the platform does not have."""

    def __init__(self, period):
        if isinstance(period, timedelta):
            d = period.total_seconds() / 86400
            if d < 1:
                raise NotImplementedError("consolidating into intraday bars needs intraday data — only daily bars are "
                                          "available. Use a period of one or more days, or Calendar.WEEKLY / MONTHLY.")
            d = int(round(d))
            period = Calendar.WEEKLY if d == 7 else Calendar.MONTHLY if d in (28, 29, 30, 31) else d
        elif callable(period) and not isinstance(period, str):
            period = Calendar.WEEKLY
        elif isinstance(period, str) and period in (Resolution.MINUTE, Resolution.HOUR, Resolution.SECOND, Resolution.TICK):
            raise NotImplementedError(f"consolidating {period} bars needs intraday data — only daily bars are available.")
        elif period == Resolution.DAILY:
            period = 1
        self.period = period
        self.data_consolidated = _Event()
        self.DataConsolidated = self.data_consolidated
        self.consolidated = None
        self._bars: List[TradeBar] = []

    def _close(self) -> None:
        b = self._bars
        bar = TradeBar(b[0].symbol, b[0].time, b[0].open, max(x.high for x in b), min(x.low for x in b), b[-1].close,
                       sum(x.volume for x in b))
        bar.end_time = b[-1].time
        bar.period = b[-1].time - b[0].time + timedelta(days=1)
        self._bars = []
        self.consolidated = bar
        self.data_consolidated.fire(self, bar)

    def update(self, bar: TradeBar, next_time=None) -> None:
        self._bars.append(bar)
        if isinstance(self.period, int):
            if len(self._bars) >= self.period:
                self._close()
            return
        ends = next_time is None or pd.Timestamp(next_time).to_period(self.period) != pd.Timestamp(bar.time).to_period(self.period)
        if ends:
            self._close()

    Update = update


TradeBarConsolidatorBase = TradeBarConsolidator


class _SubscriptionManager:
    def __init__(self, algo):
        self._a = algo

    def add_consolidator(self, symbol, consolidator) -> None:
        self._a._consolidators.append((_sym(symbol), consolidator))

    def remove_consolidator(self, symbol, consolidator) -> None:
        self._a._consolidators = [(s, c) for s, c in self._a._consolidators if c is not consolidator]

    AddConsolidator, RemoveConsolidator = add_consolidator, remove_consolidator


# ── object store: state kept between backtests (per algorithm class) ─────────
class ObjectStore:
    """save / read text, save_bytes / read_bytes, save_json / read_json, contains_key, delete, keys. Kept between runs
    of the same algorithm class on the server (10 MB); a browser run keeps it for that run only."""

    LIMIT = 10_000_000

    def __init__(self, seed: Optional[Dict[str, str]] = None):
        self._d: Dict[str, str] = dict(seed or {})

    def _size(self) -> int:
        return sum(len(k) + len(v) for k, v in self._d.items())

    def save(self, key: str, value) -> bool:
        v = value if isinstance(value, str) else str(value)
        old = self._d.get(str(key))
        self._d[str(key)] = v
        if self._size() > self.LIMIT:
            if old is None:
                self._d.pop(str(key))
            else:
                self._d[str(key)] = old
            raise ValueError("object store limit (10 MB) reached")
        return True

    def read(self, key: str) -> str:
        if str(key) not in self._d:
            raise KeyError(f"object store has no key '{key}'")
        return self._d[str(key)]

    def save_bytes(self, key: str, data) -> bool:
        import base64
        return self.save(key, "b64:" + base64.b64encode(bytes(data)).decode())

    def read_bytes(self, key: str) -> bytes:
        import base64
        v = self.read(key)
        return base64.b64decode(v[4:]) if v.startswith("b64:") else v.encode()

    def save_json(self, key: str, obj) -> bool:
        import json as _json
        return self.save(key, _json.dumps(obj, default=str))

    def read_json(self, key: str):
        import json as _json
        return _json.loads(self.read(key))

    def contains_key(self, key: str) -> bool:
        return str(key) in self._d

    def delete(self, key: str) -> bool:
        return self._d.pop(str(key), None) is not None

    @property
    def keys(self) -> List[str]:
        return list(self._d)

    def get_file_path(self, key: str):
        raise NotImplementedError("object_store.get_file_path: strategy code has no file access — use save / read.")

    Save, Read, SaveBytes, ReadBytes, ContainsKey, Delete, GetFilePath = (
        save, read, save_bytes, read_bytes, contains_key, delete, get_file_path)
    SaveJson, ReadJson = save_json, read_json


OBJECT_STORE_SEED: Dict[str, Dict[str, str]] = {}           # class name → stored keys (set by the runner)


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
        self._framework = _Framework()
        self._custom: Dict[str, Security] = {}
        self._consolidators: List[tuple] = []
        self.subscription_manager = _SubscriptionManager(self)
        self.object_store = ObjectStore(OBJECT_STORE_SEED.get(type(self).__name__))
        self.SubscriptionManager, self.ObjectStore = self.subscription_manager, self.object_store
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
        t, approx = crypto_yahoo(_sym(ticker))
        if approx:
            self._approx.add(approx)
        return self._add(t, resolution)

    def add_option(self, *a, **k):
        raise NotImplementedError("add_option: no free historical option chains. Use the Options research tab "
                                  "(model-based, labelled) or OPTIONS = [...] synthetic options in a strategy.")

    def add_future(self, *a, **k):
        raise NotImplementedError("add_future: no free roll-adjusted futures history.")

    add_index_option = add_future_option = add_option

    def add_data(self, data_type=None, ticker: Optional[str] = None, resolution=None, *a, **k) -> Security:
        """Custom data uploaded under `ticker` (Quant Lab → Custom data): delivered in on_data as slice[symbol] on the
        sessions with a fresh row, and through history(symbol). Not tradable."""
        name = str(ticker if ticker is not None else data_type).strip().lower()
        d = getattr(self._ctx, "_data", None) if self._ctx is not None else None
        if d is not None and name not in getattr(d, "custom", {}):
            raise ValueError(f"Custom data '{name}' is not loaded — upload it (Quant Lab → Custom data) and keep the "
                             "name a literal in add_data(…, \"name\").")
        sec = Security(name, resolution or Resolution.DAILY)
        sec._custom_type = data_type if isinstance(data_type, type) else PythonData
        self._custom[name] = sec
        return sec

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
            cust = getattr(d, "custom", {}).get(s.lower())
            if cust is not None and s.lower() in self._custom:
                f = cust.iloc[lo:i + 1]
                f = f[f["_new"] > 0].drop(columns=["_new"])
                f.index.name = "time"
                frames.append(pd.concat({s.lower(): f}, names=["symbol"]))
                continue
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
        """Updated with each daily bar — or, given a consolidator (or a Calendar / timedelta period), with its bars."""
        bars = isinstance(indicator, (AverageTrueRange, AverageDirectionalIndex))
        src = a[0] if a else k.get("consolidator") or k.get("resolution")
        if src is not None and not (isinstance(src, str) and src == Resolution.DAILY):
            c = src if isinstance(src, TradeBarConsolidator) else TradeBarConsolidator(src)
            if not isinstance(src, TradeBarConsolidator):
                self.subscription_manager.add_consolidator(symbol, c)
            c.data_consolidated += (lambda sender, bar: indicator.update(bar) if bars else indicator.update(bar.time, bar.close))
            return
        self._reg(symbol, indicator, bars)

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

    def consolidate(self, symbol, period, handler=None, *a, **k) -> TradeBarConsolidator:
        """Weekly / monthly / n-session bars built from daily bars: handler(bar) on the last session of each period."""
        if handler is None and a and callable(a[0]):
            handler = a[0]
        if not callable(handler):
            raise ValueError("consolidate(symbol, period, handler): the handler must be a method or function.")
        c = TradeBarConsolidator(period)
        c.data_consolidated += (lambda sender, bar: handler(bar))
        self.subscription_manager.add_consolidator(symbol, c)
        return c

    # ── Algorithm Framework ──
    def set_alpha(self, model) -> None:
        self._framework.alphas = [model]
        self._framework.used = True

    def add_alpha(self, model) -> None:
        self._framework.alphas.append(model)
        self._framework.used = True

    def set_portfolio_construction(self, model) -> None:
        self._framework.pcm = model
        self._framework.used = True

    def set_execution(self, model) -> None:
        self._framework.execution = model
        self._framework.used = True

    def set_risk_management(self, model) -> None:
        self._framework.risk = [model]
        self._framework.used = True

    def add_risk_management(self, model) -> None:
        self._framework.risk.append(model)
        self._framework.used = True

    def set_universe_selection(self, model) -> None:
        if isinstance(model, ManualUniverseSelectionModel):
            for t in model.symbols:
                self._add(t, self.universe_settings.resolution)
        elif isinstance(model, FundamentalUniverseSelectionModel):
            self.add_universe(lambda funds: _call(model, "select", self, funds))
        else:
            raise NotImplementedError("set_universe_selection: ManualUniverseSelectionModel([...]) or "
                                      "FundamentalUniverseSelectionModel(selector) are supported.")

    add_universe_selection = set_universe_selection

    def emit_insights(self, *insights) -> List[Insight]:
        ins = Insight.group(*insights)
        self._framework.emitted += ins
        self._framework.used = True
        return ins

    @property
    def insights(self) -> List[Insight]:
        return list(self._framework.active.values())

    Insights = insights

    # orders
    def _order(self, symbol, quantity: float, kind: str, tag: str = "", **prices) -> OrderTicket:
        t = _sym(symbol)
        q = float(int(quantity)) if abs(quantity - int(quantity)) < 1e-9 else float(quantity)
        if self.is_warming_up:
            self._log.append(f"{self.time}: order for {t} ignored during warm-up")
            return OrderTicket(self, 0, Symbol(t), q, kind, tag)
        if t not in self._ctx._data.close.columns:
            if t.lower() in self._custom:
                raise ValueError(f"Order for {t}: custom data is not tradable.")
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

    def _report(self, final: bool = False) -> Dict[str, Any]:
        reasons: Dict[str, int] = {}
        for r in self._rejected:
            key = r["reason"].split(":")[0]
            reasons[key] = reasons.get(key, 0) + 1
        return {"api_version": API_VERSION, "account_type": self._account,
                "orders": len(self._tickets), "rejected": len(self._rejected), "rejected_by_reason": reasons,
                "rejected_last": self._rejected[-20:],
                "realized_pnl": {k: round(v, 2) for k, v in self._realized.items()},
                "open_lots": sum(len(v) for v in self._lots.values()), "approximations": sorted(self._approx),
                "log_tail": self._log[-30:],
                **({"framework": {"insights": self._framework.count, "active_insights": len(self._framework.active),
                                  "models": [type(m).__name__ for m in self._framework.models()]}}
                   if self._framework.used else {}),
                **({"object_store": {"class": type(self).__name__, "data": dict(self.object_store._d)}}
                   if self.object_store._d else {})}

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
    AddEquity, AddForex, AddCrypto, AddOption, AddFuture, AddUniverse, RemoveSecurity, AddData = (
        add_equity, add_forex, add_crypto, add_option, add_future, add_universe, remove_security, add_data)
    History, RegisterIndicator, WarmUpIndicator, Consolidate = history, register_indicator, warm_up_indicator, consolidate
    SMA, EMA, RSI, ATR, BB, MACD, ROC, ROCP, MOMP, MOM, MAX, MIN, STD, ADX = (
        sma, ema, rsi, atr, bb, macd, roc, rocp, momp, mom, max, min, std, adx)
    MarketOrder, MarketOnOpenOrder, MarketOnCloseOrder, LimitOrder, StopMarketOrder, StopLimitOrder, TrailingStopOrder = (
        market_order, market_on_open_order, market_on_close_order, limit_order, stop_market_order, stop_limit_order,
        trailing_stop_order)
    SetHoldings, Liquidate, CalculateOrderQuantity, Debug, Log, Error, Plot, Quit, Symbol, GetParameter = (
        set_holdings, liquidate, calculate_order_quantity, debug, debug, debug, plot, quit, symbol, get_parameter)
    SettledCash, TaxLots = settled_cash, tax_lots
    SetAlpha, AddAlpha, SetPortfolioConstruction, SetExecution, SetRiskManagement, AddRiskManagement = (
        set_alpha, add_alpha, set_portfolio_construction, set_execution, set_risk_management, add_risk_management)
    SetUniverseSelection, AddUniverseSelection, EmitInsights = set_universe_selection, add_universe_selection, emit_insights


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
                sel = getattr(ind, "_selector", None)
                if sel is not None:
                    ind.update(b.time, float(sel(b)))
                elif getattr(ind, "_bars", False):
                    ind.update(b)
                else:
                    ind.update(b.time, b.close)
        for b_ in getattr(algo, "_betas", []):
            for t in (b_.target, b_.reference):
                bb = bar_of(d, t, i)
                if bb is not None:
                    b_.update_pair(bb.time, t, bb.close)
        idx = d.close.index
        nxt = idx[i + 1].to_pydatetime() if i + 1 < len(idx) else None    # the trading calendar, not future prices
        for t, c in list(algo._consolidators):
            b = bar_of(d, t, i)
            if b is not None:
                c.update(b, nxt)

    def select(algo, d, i, ctx) -> None:
        if not algo._selectors:
            return
        mem = getattr(d, "members", None)
        cols = list(d.close.columns)
        obs = d.observed.iloc[i].to_numpy()
        ok = obs & (mem.iloc[i].to_numpy() if mem is not None else np.ones(len(cols), bool))
        px, vol = d.close.iloc[i].to_numpy(), d.volume.iloc[i].to_numpy()
        fr = {n: d.fund[n].iloc[i].to_numpy() for n in getattr(d, "fund", {}) or {}}
        info = getattr(d, "instruments", {}) or {}
        funds = [Fundamental(Symbol(c), float(px[k]), float(vol[k]), {n: v[k] for n, v in fr.items()} if fr else None,
                             (info.get(c) or {}).get("sector"))
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
            ch = SecurityChanges(add_s, rem_s)
            _handler(algo, "on_securities_changed")(ch)
            algo._framework.securities_changed(algo, ch)

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
                algo._emit(OrderEvent(tk.order_id, tk.symbol, algo.time, status, px, q))   # the ticket's id (stable across updates)

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
            if algo._framework.used and algo.securities:          # framework models see the initial securities
                algo._framework.securities_changed(algo, SecurityChanges(list(algo.securities.values()), []))
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
        for name, sec in algo._custom.items():                        # custom data: sessions with a fresh row
            cf = getattr(d, "custom", {}).get(name)
            if cf is not None and cf["_new"].iloc[i] > 0:
                row = {k: float(v) for k, v in cf.iloc[i].items() if k != "_new"}
                pt = sec._custom_type(name, algo.time, row) if sec._custom_type is not PythonData else PythonData(name, algo.time, row)
                if not isinstance(pt, PythonData) or pt.symbol is None:
                    pt = PythonData(name, algo.time, row)
                bars[_sym(sec.symbol)] = pt
                sec.price = pt.value
        if bars:
            sl = Slice(algo.time, bars)
            _handler(algo, "on_data")(sl)
            algo._framework.step(algo, sl)
        last = i == len(idx) - 1
        if last:
            _handler(algo, "on_end_of_algorithm")()
        ctx.report = algo._report(final=last)

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
    "set_alpha", "add_alpha", "set_portfolio_construction", "set_execution", "set_risk_management", "add_risk_management",
    "set_universe_selection", "add_universe_selection", "emit_insights", "insights", "consolidate", "subscription_manager",
    "add_consolidator", "object_store", "add_data",
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
    "asset_classification": "today's sector as a Morningstar sector code for every date (no free sector history; "
                            "industry codes are NaN)",
    "VolumeWeightedAveragePriceExecutionModel": "fills like ImmediateExecutionModel (next open) — no intraday volume profile",
    "StandardDeviationExecutionModel": "fills like ImmediateExecutionModel (next open) — no intraday prices",
    "SpreadExecutionModel": "fills like ImmediateExecutionModel (next open) — no quotes",
    "MeanVarianceOptimizationPortfolioConstructionModel": "not built in — use RiskParityPortfolioConstructionModel or your own create_targets",
}
UNSUPPORTED = {
    "add_option": "no free historical option chains", "add_future": "no free roll-adjusted futures history",
    "add_index_option": "no free historical option chains", "add_future_option": "no free historical option chains",
    "option_chain_provider": "no option chains",

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
    """The algorithm: a class deriving from QCAlgorithm directly or through your own base classes; when several do, the
    last one that defines initialize() (the most derived)."""
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    by_name = {c.name: c for c in classes}

    def is_algo(c, seen=()):
        for b in c.bases:
            nm = b.id if isinstance(b, ast.Name) else b.attr if isinstance(b, ast.Attribute) else None
            if nm in ("QCAlgorithm", "QCAlgorithmFramework"):
                return True
            if nm in by_name and nm not in seen and is_algo(by_name[nm], seen + (c.name,)):
                return True
        return False

    def defines_init(c, seen=()):
        if any(isinstance(f, ast.FunctionDef) and f.name in ("initialize", "Initialize") for f in c.body):
            return True
        return any(isinstance(b, ast.Name) and b.id in by_name and b.id not in seen and defines_init(by_name[b.id], seen + (c.name,))
                   for b in c.bases)
    algos = [c for c in classes if is_algo(c)]
    with_init = [c for c in algos if defines_init(c)]
    return (with_init or algos or [None])[-1]


def _init_of(tree: ast.Module, cls: ast.ClassDef) -> Optional[ast.FunctionDef]:
    """initialize() of the algorithm class, or of the nearest base class in the file that defines it."""
    by_name = {c.name: c for c in tree.body if isinstance(c, ast.ClassDef)}
    todo, seen = [cls], set()
    while todo:
        c = todo.pop(0)
        if c.name in seen:
            continue
        seen.add(c.name)
        f = next((f for f in c.body if isinstance(f, ast.FunctionDef) and f.name in ("initialize", "Initialize")), None)
        if f is not None:
            return f
        todo += [by_name[b.id] for b in c.bases if isinstance(b, ast.Name) and b.id in by_name]
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
        note("unsupported", n.lineno, m, UNRESOLVED, discover=True)
        return
    t = args[0].upper()
    if m == "add_forex":
        t = t if t.endswith("=X") else f"{t}=X"
    elif m == "add_crypto":
        t, approx = crypto_yahoo(t)
        if approx:
            note("approximated", n.lineno, f"add_crypto('{args[0]}')", approx)
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
    init = _init_of(tree, cls)
    if init is None:
        raise ValueError("The algorithm has no initialize(self) method.")
    h: Dict[str, Any] = {"universe": [], "dynamic_universe": False, "class": cls.name}
    rep: List[Dict[str, Any]] = []
    seen = set()

    def note(level, line, feature, msg, discover=False):
        key = (level, feature, line)
        if key not in seen:
            seen.add(key)
            rep.append({"level": level, "line": line, "feature": feature, "message": msg, **({"discover": True} if discover else {})})
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
            if m in ("add_equity", "add_forex", "add_crypto", "add_cfd", "add_index") and n.args:
                firsts = resolve(n.args[0], n)
                rest = [_lit(a) for a in n.args[1:]]
                for f0 in firsts:
                    if m == "add_index" and isinstance(f0, str):
                        f0 = _INDEX_STATIC.get(f0.upper().lstrip("^"), f0 if f0.startswith("^") else "^" + f0.upper())
                    _read_call("add_equity" if m in ("add_cfd", "add_index") else m, [f0] + rest, n, h, note)
                continue
            args = [_lit(a) for a in n.args]
            if m in ("set_start_date", "set_end_date"):
                v = args[0] if len(args) == 1 else (date(*args[:3]) if len(args) >= 3 and all(isinstance(a, int) for a in args[:3]) else None)
                if v is None:
                    note("unsupported", n.lineno, m, "the date is not a literal — read by running initialize()", discover=True)
                else:
                    h["start" if m == "set_start_date" else "end"] = str(v)[:10]
            elif m == "set_cash":
                amt = next((a for a in reversed(args) if isinstance(a, (int, float)) and not isinstance(a, bool)), None)
                if amt is not None:
                    h["capital"] = float(amt)
                else:
                    note("unsupported", n.lineno, m, "the amount is not a literal — read by running initialize()", discover=True)
            elif m == "set_benchmark":
                if args and isinstance(args[0], str):
                    h["benchmark"] = args[0].upper()
                else:
                    note("unsupported", n.lineno, m, "the benchmark is not a literal — read by running initialize()", discover=True)
            elif m in ("set_universe_selection", "add_universe_selection"):
                src = ast.unparse(n)
                if "Fundamental" in src or "Coarse" in src:
                    h["dynamic_universe"] = True
                for c in ast.walk(n):                              # Symbol.create("SPY", …) / "SPY" in the manual list
                    if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr in ("create", "Create") \
                            and c.args and isinstance(_lit(c.args[0]), str):
                        _read_call("add_equity", [_lit(c.args[0])], n, h, note)
                    elif isinstance(c, (ast.List, ast.Tuple)):
                        for e in c.elts:
                            if isinstance(_lit(e), str):
                                _read_call("add_equity", [_lit(e)], n, h, note)
            elif m == "add_data":
                lits = [a for a in args if isinstance(a, str)]
                if lits:
                    h.setdefault("custom", []).append(lits[0].strip().lower())
                    note("approximated", n.lineno, "add_data", "custom data = the CSV uploaded under this name (Quant Lab "
                         "→ Custom data), as of each session; get_source / reader are not called")
                else:
                    note("unsupported", n.lineno, "add_data", "the dataset name must be a literal: add_data(MyData, \"name\")")
            elif m == "add_universe":
                h["dynamic_universe"] = True
                note("approximated", n.lineno, "add_universe", "selection runs each session on point-in-time S&P 500 "
                     "members: price, volume, dollar volume, point-in-time SEC fundamentals (market cap, valuation and "
                     "operation ratios, EPS) and today's sector")
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
        elif isinstance(n, ast.Name) and n.id in APPROXIMATED:
            note("approximated", line, n.id, APPROXIMATED[n.id])
    _check_unknown(tree, cls, note)
    used = {_snake(n.attr) for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    need = sorted({FUND_FIELDS[u] for u in used if u in FUND_FIELDS})
    if need:
        h["fundamentals"] = need
        note("approximated", None, "fundamentals", "point-in-time SEC filings (US filers, as first filed, from the next "
             "session) in place of Morningstar: " + ", ".join(need))
    if not h["universe"] and not h["dynamic_universe"] and not any(r.get("discover") for r in rep):
        if h.get("custom"):
            h["universe"] = [h.get("benchmark") or "SPY"]          # custom data only: the benchmark sets the calendar
        else:                                                      # built in code (a variable, a model): run it to see
            note("unsupported", init.lineno, "universe", "no ticker is readable without running initialize()", discover=True)
    h["report"] = sorted(rep, key=lambda r: ({"unsupported": 0, "check": 1, "approximated": 2}.get(r["level"], 3), r["line"] or 0))
    h["api_version"] = API_VERSION
    return h


UNRESOLVED = "the ticker must be a literal (or a literal list looped over) in initialize()"
_INDEX_STATIC = {"SPX": "^GSPC", "NDX": "^NDX", "VIX": "^VIX", "DJI": "^DJI", "RUT": "^RUT"}


def _known_algo_attrs() -> set:
    a = QCAlgorithm()
    names = set(dir(a)) | set(a.__dict__)
    return names | {_snake(n) for n in names} | {_pascal(n) for n in names if n.islower()}


def _check_unknown(tree: ast.Module, cls: ast.ClassDef, note) -> None:
    """Report, before running, every `self.X` on the algorithm and every global name the layer does not provide — so a
    gap shows up as a line in the report, not as an error halfway through a backtest."""
    import builtins
    import symtable
    known = _known_algo_attrs()
    mine = set()
    for c in ast.walk(tree):
        if isinstance(c, ast.ClassDef):
            for b in c.body:
                if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    mine.add(b.name)
                elif isinstance(b, ast.Assign):
                    mine |= {t.id for t in b.targets if isinstance(t, ast.Name)}
                elif isinstance(b, ast.AnnAssign) and isinstance(b.target, ast.Name):
                    mine.add(b.target.id)
        if isinstance(c, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            for t in (c.targets if isinstance(c, ast.Assign) else [c.target]):
                for e in ([t] + (list(t.elts) if isinstance(t, (ast.Tuple, ast.List)) else [])):
                    if isinstance(e, ast.Attribute) and isinstance(e.value, ast.Name) and e.value.id == "self":
                        mine.add(e.attr)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "setattr" and len(c.args) > 1 \
                and isinstance(c.args[1], ast.Constant):
            mine.add(str(c.args[1].value))
    mine |= {_snake(n) for n in mine} | {_pascal(n) for n in mine}
    for fn in [b for b in cls.body if isinstance(b, ast.FunctionDef)]:
        for c in ast.walk(fn):
            if isinstance(c, ast.Attribute) and isinstance(c.value, ast.Name) and c.value.id == "self" \
                    and isinstance(c.ctx, ast.Load) and c.attr not in known and _snake(c.attr) not in known \
                    and c.attr not in mine and _snake(c.attr) not in mine:
                kind = "unsupported" if _snake(c.attr) in UNSUPPORTED else "check"
                note(kind, c.lineno, f"self.{c.attr}", UNSUPPORTED.get(_snake(c.attr)) or
                     "not part of the compatibility layer — the run stops with an error if this line executes")
    # global names: referenced somewhere, defined nowhere in the file, not a builtin, not provided by the layer
    try:
        top = symtable.symtable(ast.unparse(tree), "<strategy>", "exec")
    except SyntaxError:
        return
    defined = {s_.get_name() for s_ in top.get_symbols() if s_.is_assigned() or s_.is_imported() or s_.is_namespace()}
    refs = {}

    def walk(t):
        for s_ in t.get_symbols():
            if s_.is_referenced() and (t is top or s_.is_global()):
                refs.setdefault(s_.get_name(), None)
        for ch in t.get_children():
            walk(ch)
    walk(top)
    provided = set(NAMES) | set(dir(builtins)) | {"np", "pd", "math", "self", "cls", "AlgorithmImports"}
    lines = {n.id: n.lineno for n in ast.walk(tree) if isinstance(n, ast.Name)}
    for name in sorted(set(refs) - defined - provided):
        note("check", lines.get(name), name, "not defined in this file or by the compatibility layer — the run stops "
             "with a NameError if this line executes")


def needs_discovery(header: Dict[str, Any]) -> bool:
    return any(r.get("discover") or r["message"] == UNRESOLVED for r in header.get("report") or [])


def discover(cls) -> Dict[str, Any]:
    """Run the algorithm's initialize() without data to learn what it adds — for tickers the static reader cannot follow
    (variables, constants, comprehensions, helpers). Only ever called where user code may run (the browser, the
    sandbox). Calls that need prices (history, warm-up) fail harmlessly here: what was added before them is kept."""
    algo = cls()
    algo._ctx = None
    algo.time = datetime(2000, 1, 1)
    err = None
    try:
        _handler(algo, "initialize")()
    except Exception as e:                                      # noqa: BLE001 — partial discovery is still useful
        err = f"{type(e).__name__}: {str(e)[:160]}"
    for m in getattr(algo._framework, "models", lambda: [])():
        if isinstance(m, ManualUniverseSelectionModel):
            for t in m.symbols:
                algo._add(t, Resolution.DAILY)
    hdr = getattr(algo, "_hdr", {}) or {}
    return {"universe": [t for t in algo.securities.keys()], "custom": list(algo._custom.keys()),
            "dynamic_universe": bool(algo._selectors), "error": err,
            **{k: hdr[k] for k in ("start", "end", "capital", "benchmark") if k in hdr}}


def resolve(header: Dict[str, Any], found: Dict[str, Any]) -> Dict[str, Any]:
    """Merge a discovery run into the static header; the unreadable-ticker notes become approximations."""
    h = dict(header)
    h["universe"] = list(dict.fromkeys(list(h.get("universe") or []) + [str(t).upper() for t in found.get("universe") or []]))
    if found.get("custom"):
        h["custom"] = list(dict.fromkeys(list(h.get("custom") or []) + list(found["custom"])))
    if found.get("dynamic_universe"):
        h["dynamic_universe"] = True
    for k in ("start", "end", "capital", "benchmark"):
        if found.get(k) is not None and h.get(k) is None:
            h[k] = found[k]
    field = {"set_start_date": "start", "set_end_date": "end", "set_cash": "capital", "set_benchmark": "benchmark"}
    err = found.get("error")

    def done(r) -> bool:
        k = field.get(r["feature"])
        return (found.get(k) is not None) if k else bool(found.get("universe") or found.get("dynamic_universe"))
    out = []
    for r in h.get("report") or []:
        if not (r.get("discover") or r["message"] == UNRESOLVED):
            out.append(r)
            continue
        base = {k: v for k, v in r.items() if k != "discover"}
        if done(r):
            out.append({**base, "level": "approximated", "message": "resolved by running initialize() in the sandbox"
                        + (f" (it stopped early: {err})" if err else "")})
        else:
            out.append({**base, "level": "unsupported", "message": "could not be read: running initialize() failed with "
                        + (err or "no value set") + " — fix that error and check again"})
    h["report"] = out
    h["discovered"] = True
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
    "DataNormalizationMode", "BrokerageName", "AccountType", "DayOfWeek", "Market", "SecurityType", "MorningstarSectorCode",
    "Symbol", "TradeBar", "Slice",
    "RollingWindow", "SimpleMovingAverage", "ExponentialMovingAverage", "WildersMovingAverage", "RelativeStrengthIndex",
    "AverageTrueRange", "BollingerBands", "MovingAverageConvergenceDivergence", "RateOfChange", "RateOfChangePercent",
    "Momentum", "Maximum", "Minimum", "StandardDeviation", "AverageDirectionalIndex", "IndicatorDataPoint",
    "PortfolioTarget", "SecurityChanges", "Fundamental", "CoarseFundamental", "OrderEvent", "OrderTicket",
    # Algorithm Framework
    "Insight", "InsightDirection", "InsightType", "PortfolioBias", "AlphaModel", "NullAlphaModel", "ConstantAlphaModel",
    "EmaCrossAlphaModel", "MacdAlphaModel", "RsiAlphaModel", "HistoricalReturnsAlphaModel", "PortfolioConstructionModel",
    "NullPortfolioConstructionModel", "EqualWeightingPortfolioConstructionModel", "InsightWeightingPortfolioConstructionModel",
    "ConfidenceWeightingPortfolioConstructionModel", "RiskParityPortfolioConstructionModel", "RiskManagementModel",
    "NullRiskManagementModel", "MaximumDrawdownPercentPerSecurity", "MaximumUnrealizedProfitPercentPerSecurity",
    "MaximumDrawdownPercentPortfolio", "TrailingStopRiskManagementModel", "CompositeRiskManagementModel", "ExecutionModel",
    "NullExecutionModel", "ImmediateExecutionModel", "VolumeWeightedAveragePriceExecutionModel",
    "StandardDeviationExecutionModel", "SpreadExecutionModel", "UniverseSelectionModel", "ManualUniverseSelectionModel",
    "FundamentalUniverseSelectionModel", "CoarseFundamentalUniverseSelectionModel",
    # consolidators, object store
    "Calendar", "TradeBarConsolidator", "TradeBarConsolidatorBase", "ObjectStore", "PythonData")}
NAMES.update({"timedelta": timedelta, "datetime": datetime, "date": date})


# ════════════════════════════════════════════════════════════════════════════
# Breadth: the rest of the commonly used LEAN surface, and both naming styles everywhere
# ════════════════════════════════════════════════════════════════════════════
def _pascal(name: str) -> str:
    return "".join(w[:1].upper() + w[1:] for w in name.split("_") if w)


def _case_getattr(self, name: str):
    """LEAN Python accepts SetHoldings and set_holdings, IsReady and is_ready: whichever spelling is missing resolves to
    the other; anything else is a clear 'not in the compatibility layer' error instead of a bare AttributeError."""
    if name.startswith("_"):
        raise AttributeError(name)
    for alt in ({_snake(name), _snake(name).replace("warmup", "warm_up")} if any(c.isupper() for c in name)
                else {_pascal(name), _pascal(name.replace("warm_up", "warmup"))}):
        if alt != name:
            try:
                return object.__getattribute__(self, alt)
            except AttributeError:
                pass
    raise AttributeError(f"'{type(self).__name__}' has no '{name}' in the QuantConnect compatibility layer ({API_VERSION}); "
                         "see Code Lab → QuantConnect API for what is available")


class _Updated(list):
    """indicator.updated += handler (C#-style event, as LEAN Python allows); handler(sender, point)."""

    def __iadd__(self, fn):
        if callable(fn):
            self.append(fn)
            return self
        return list.__iadd__(self, fn)

    def __isub__(self, fn):
        if fn in self:
            self.remove(fn)
        return self


_orig_ind_init = Indicator.__init__


def _ind_init(self, name: str = ""):
    _orig_ind_init(self, name)
    self.updated = _Updated()


Indicator.__init__ = _ind_init


class _BarIndicator(Indicator):
    needs_bars = True

    def _bar(self, value) -> TradeBar:
        if not isinstance(value, TradeBar):
            raise ValueError(f"{type(self).__name__} needs trade bars (created with its self.<helper>(), or register_indicator "
                             "with a symbol).")
        return value


class LinearWeightedMovingAverage(Indicator):
    def __init__(self, period: int, name: str = ""):
        super().__init__(name or f"LWMA({period})")
        self._args = (period, name)
        self.period = self.warm_up_period = int(period)
        self._w: deque = deque(maxlen=self.period)

    def _compute(self, value):
        self._w.append(self._x(value))
        n = len(self._w)
        wts = range(1, n + 1)
        return sum(w * x for w, x in zip(wts, self._w)) / sum(wts)


class HullMovingAverage(Indicator):
    def __init__(self, period: int, name: str = ""):
        super().__init__(name or f"HMA({period})")
        self._args = (period, name)
        p = int(period)
        self.period = p
        self._a, self._b = LinearWeightedMovingAverage(max(1, p // 2)), LinearWeightedMovingAverage(p)
        self._h = LinearWeightedMovingAverage(max(1, int(round(math.sqrt(p)))))
        self.warm_up_period = p + self._h.period - 1

    def _compute(self, value):
        x = self._x(value)
        self._a.update(None, x)
        self._b.update(None, x)
        if not self._b.is_ready:
            return None
        self._h.update(None, 2 * self._a.current.value - self._b.current.value)
        return self._h.current.value


class DoubleExponentialMovingAverage(Indicator):
    def __init__(self, period: int, name: str = ""):
        super().__init__(name or f"DEMA({period})")
        self._args = (period, name)
        self.period = int(period)
        self.warm_up_period = 2 * self.period - 1
        self._e1, self._e2 = ExponentialMovingAverage(period), ExponentialMovingAverage(period)

    def _compute(self, value):
        self._e1.update(None, self._x(value))
        if not self._e1.is_ready:
            return 0.0
        self._e2.update(None, self._e1.current.value)
        return 2 * self._e1.current.value - self._e2.current.value if self._e2.is_ready else self._e1.current.value


class TripleExponentialMovingAverage(Indicator):
    def __init__(self, period: int, name: str = ""):
        super().__init__(name or f"TEMA({period})")
        self._args = (period, name)
        self.period = int(period)
        self.warm_up_period = 3 * self.period - 2
        self._e = [ExponentialMovingAverage(period) for _ in range(3)]

    def _compute(self, value):
        v = self._x(value)
        for k, e in enumerate(self._e):
            e.update(None, v)
            if not e.is_ready:
                return self._e[0].current.value if k else 0.0
            v = e.current.value
        e1, e2, e3 = (e.current.value for e in self._e)
        return 3 * e1 - 3 * e2 + e3


class KaufmanAdaptiveMovingAverage(Indicator):
    def __init__(self, period: int, fast_ema_period: int = 2, slow_ema_period: int = 30, name: str = ""):
        super().__init__(name or f"KAMA({period})")
        self._args = (period, fast_ema_period, slow_ema_period, name)
        self.period = int(period)
        self.warm_up_period = self.period + 1
        self._w: deque = deque(maxlen=self.period + 1)
        self._fast, self._slow = 2 / (fast_ema_period + 1), 2 / (slow_ema_period + 1)
        self._v: Optional[float] = None

    def _compute(self, value):
        x = self._x(value)
        self._w.append(x)
        if len(self._w) <= self.period:
            return x
        if self._v is None:
            self._v = self._w[-2]
        w = list(self._w)
        vol = sum(abs(w[k] - w[k - 1]) for k in range(1, len(w)))
        er = abs(w[-1] - w[0]) / vol if vol else 0.0
        sc = (er * (self._fast - self._slow) + self._slow) ** 2
        self._v = self._v + sc * (x - self._v)
        return self._v


class Trix(Indicator):
    def __init__(self, period: int, name: str = ""):
        super().__init__(name or f"TRIX({period})")
        self._args = (period, name)
        self.period = int(period)
        self.warm_up_period = 3 * self.period
        self._e = [ExponentialMovingAverage(period) for _ in range(3)]
        self._prev: Optional[float] = None

    def _compute(self, value):
        v = self._x(value)
        for e in self._e:
            e.update(None, v)
            if not e.is_ready:
                return 0.0
            v = e.current.value
        out = 100 * (v / self._prev - 1) if self._prev else 0.0
        self._prev = v
        return out


class AbsolutePriceOscillator(Indicator):
    def __init__(self, fast_period: int, slow_period: int, moving_average_type=MovingAverageType.SIMPLE, name: str = ""):
        super().__init__(name or f"APO({fast_period},{slow_period})")
        self._args = (fast_period, slow_period, moving_average_type, name)
        self.fast, self.slow = _ma(moving_average_type, fast_period), _ma(moving_average_type, slow_period)
        self.warm_up_period = int(slow_period)

    def _compute(self, value):
        x = self._x(value)
        self.fast.update(None, x)
        self.slow.update(None, x)
        return self.fast.current.value - self.slow.current.value if self.slow.is_ready else 0.0


class PercentagePriceOscillator(AbsolutePriceOscillator):
    def _compute(self, value):
        d = super()._compute(value)
        s = self.slow.current.value
        return 100 * d / s if self.slow.is_ready and s else 0.0


class ChandeMomentumOscillator(Indicator):
    def __init__(self, period: int, name: str = ""):
        super().__init__(name or f"CMO({period})")
        self._args = (period, name)
        self.period = int(period)
        self.warm_up_period = self.period + 1
        self._w: deque = deque(maxlen=self.period + 1)

    def _compute(self, value):
        self._w.append(self._x(value))
        w = list(self._w)
        ch = [w[k] - w[k - 1] for k in range(1, len(w))]
        up, dn = sum(c for c in ch if c > 0), -sum(c for c in ch if c < 0)
        return 100 * (up - dn) / (up + dn) if up + dn else 0.0


class LogReturn(Indicator):
    def __init__(self, period: int = 1, name: str = ""):
        super().__init__(name or f"LOGR({period})")
        self._args = (period, name)
        self.period = int(period)
        self.warm_up_period = self.period + 1
        self._w: deque = deque(maxlen=self.period + 1)

    def _compute(self, value):
        self._w.append(self._x(value))
        return math.log(self._w[-1] / self._w[0]) if len(self._w) == self._w.maxlen and self._w[0] > 0 and self._w[-1] > 0 else 0.0


class Delay(Indicator):
    def __init__(self, period: int, name: str = ""):
        super().__init__(name or f"DELAY({period})")
        self._args = (period, name)
        self.period = int(period)
        self.warm_up_period = self.period + 1
        self._w: deque = deque(maxlen=self.period + 1)

    def _compute(self, value):
        self._w.append(self._x(value))
        return self._w[0]


class Identity(Indicator):
    def __init__(self, name: str = ""):
        super().__init__(name or "IDENTITY")
        self._args = (name,)

    def _compute(self, value):
        return self._x(value)


class TrueRange(_BarIndicator):
    def __init__(self, name: str = ""):
        super().__init__(name or "TR")
        self._args = (name,)
        self.warm_up_period = 2
        self._prev: Optional[float] = None

    def _compute(self, value):
        b = self._bar(value)
        tr = b.high - b.low if self._prev is None else max(b.high - b.low, abs(b.high - self._prev), abs(b.low - self._prev))
        self._prev = b.close
        return tr


class NormalizedAverageTrueRange(_BarIndicator):
    def __init__(self, period: int, name: str = ""):
        super().__init__(name or f"NATR({period})")
        self._args = (period, name)
        self.period = self.warm_up_period = int(period)
        self._atr = AverageTrueRange(period)

    def _compute(self, value):
        b = self._bar(value)
        self._atr.update(b)
        return 100 * self._atr.current.value / b.close if b.close else 0.0


class CommodityChannelIndex(_BarIndicator):
    def __init__(self, period: int, moving_average_type=MovingAverageType.SIMPLE, name: str = ""):
        super().__init__(name or f"CCI({period})")
        self._args = (period, moving_average_type, name)
        self.period = self.warm_up_period = int(period)
        self._w: deque = deque(maxlen=self.period)

    def _compute(self, value):
        b = self._bar(value)
        tp = (b.high + b.low + b.close) / 3
        self._w.append(tp)
        m = sum(self._w) / len(self._w)
        md = sum(abs(x - m) for x in self._w) / len(self._w)
        return (tp - m) / (0.015 * md) if md else 0.0


class Stochastic(_BarIndicator):
    """fast_stoch (raw %K over `period`), stoch_k (SMA of it over k_period), stoch_d (SMA of %K over d_period);
    the current value is fast_stoch, as LEAN."""

    def __init__(self, period: int, k_period: int, d_period: int, name: str = ""):
        super().__init__(name or f"STO({period},{k_period},{d_period})")
        self._args = (period, k_period, d_period, name)
        self.period = int(period)
        self.warm_up_period = self.period + max(int(k_period), 1) + max(int(d_period), 1) - 2
        self._hi: deque = deque(maxlen=self.period)
        self._lo: deque = deque(maxlen=self.period)
        self._k, self._d = SimpleMovingAverage(k_period), SimpleMovingAverage(d_period)
        self.fast_stoch, self.stoch_k, self.stoch_d = IndicatorDataPoint(), IndicatorDataPoint(), IndicatorDataPoint()

    def _compute(self, value):
        b = self._bar(value)
        self._hi.append(b.high)
        self._lo.append(b.low)
        hh, ll = max(self._hi), min(self._lo)
        fast = 100 * (b.close - ll) / (hh - ll) if hh > ll else 0.0
        self._k.update(None, fast)
        self._d.update(None, self._k.current.value)
        self.fast_stoch = IndicatorDataPoint(b.time, fast)
        self.stoch_k = IndicatorDataPoint(b.time, self._k.current.value)
        self.stoch_d = IndicatorDataPoint(b.time, self._d.current.value)
        return fast


class WilliamsPercentR(_BarIndicator):
    def __init__(self, period: int, name: str = ""):
        super().__init__(name or f"WILR({period})")
        self._args = (period, name)
        self.period = self.warm_up_period = int(period)
        self._hi: deque = deque(maxlen=self.period)
        self._lo: deque = deque(maxlen=self.period)

    def _compute(self, value):
        b = self._bar(value)
        self._hi.append(b.high)
        self._lo.append(b.low)
        hh, ll = max(self._hi), min(self._lo)
        return -100 * (hh - b.close) / (hh - ll) if hh > ll else 0.0


class AroonOscillator(_BarIndicator):
    def __init__(self, up_period: int, down_period: int, name: str = ""):
        super().__init__(name or f"AROON({up_period},{down_period})")
        self._args = (up_period, down_period, name)
        self.up_period, self.down_period = int(up_period), int(down_period)
        self.warm_up_period = max(self.up_period, self.down_period) + 1
        self._hi: deque = deque(maxlen=self.up_period + 1)
        self._lo: deque = deque(maxlen=self.down_period + 1)
        self.aroon_up, self.aroon_down = IndicatorDataPoint(), IndicatorDataPoint()

    def _compute(self, value):
        b = self._bar(value)
        self._hi.append(b.high)
        self._lo.append(b.low)
        hi, lo = list(self._hi), list(self._lo)
        since_hi = len(hi) - 1 - max(range(len(hi)), key=lambda k: (hi[k], k))
        since_lo = len(lo) - 1 - min(range(len(lo)), key=lambda k: (lo[k], -k))
        up = 100 * (self.up_period - since_hi) / self.up_period
        dn = 100 * (self.down_period - since_lo) / self.down_period
        self.aroon_up, self.aroon_down = IndicatorDataPoint(b.time, up), IndicatorDataPoint(b.time, dn)
        return up - dn


class DonchianChannel(_BarIndicator):
    def __init__(self, upper_period: int, lower_period: Optional[int] = None, name: str = ""):
        super().__init__(name or f"DCH({upper_period})")
        lower_period = int(lower_period or upper_period)
        self._args = (upper_period, lower_period, name)
        self.warm_up_period = max(int(upper_period), lower_period)
        self._hi: deque = deque(maxlen=int(upper_period))
        self._lo: deque = deque(maxlen=lower_period)
        self.upper_band, self.lower_band = IndicatorDataPoint(), IndicatorDataPoint()

    def _compute(self, value):
        b = self._bar(value)
        self._hi.append(b.high)
        self._lo.append(b.low)
        u, l = max(self._hi), min(self._lo)
        self.upper_band, self.lower_band = IndicatorDataPoint(b.time, u), IndicatorDataPoint(b.time, l)
        return (u + l) / 2


class KeltnerChannels(_BarIndicator):
    def __init__(self, period: int, k: float, moving_average_type=MovingAverageType.SIMPLE, name: str = ""):
        super().__init__(name or f"KCH({period},{k})")
        self._args = (period, k, moving_average_type, name)
        self.period = self.warm_up_period = int(period)
        self.k = float(k)
        self.middle_band, self.average_true_range = _ma(moving_average_type, period), AverageTrueRange(period, moving_average_type)
        self.upper_band, self.lower_band = IndicatorDataPoint(), IndicatorDataPoint()

    def _compute(self, value):
        b = self._bar(value)
        self.middle_band.update(None, b.close)
        self.average_true_range.update(b)
        m, a = self.middle_band.current.value, self.average_true_range.current.value
        self.upper_band, self.lower_band = IndicatorDataPoint(b.time, m + self.k * a), IndicatorDataPoint(b.time, m - self.k * a)
        return m


class OnBalanceVolume(_BarIndicator):
    def __init__(self, name: str = ""):
        super().__init__(name or "OBV")
        self._args = (name,)
        self.warm_up_period = 2
        self._prev: Optional[float] = None
        self._v = 0.0

    def _compute(self, value):
        b = self._bar(value)
        if self._prev is not None:
            self._v += b.volume if b.close > self._prev else -b.volume if b.close < self._prev else 0.0
        self._prev = b.close
        return self._v


class VolumeWeightedAveragePriceIndicator(_BarIndicator):
    def __init__(self, period: int, name: str = ""):
        super().__init__(name or f"VWAP({period})")
        self._args = (period, name)
        self.period = self.warm_up_period = int(period)
        self._w: deque = deque(maxlen=self.period)

    def _compute(self, value):
        b = self._bar(value)
        self._w.append(((b.high + b.low + b.close) / 3, b.volume))
        v = sum(x[1] for x in self._w)
        return sum(x[0] * x[1] for x in self._w) / v if v else b.close


class MoneyFlowIndex(_BarIndicator):
    def __init__(self, period: int, name: str = ""):
        super().__init__(name or f"MFI({period})")
        self._args = (period, name)
        self.period = int(period)
        self.warm_up_period = self.period + 1
        self._prev: Optional[float] = None
        self._pos: deque = deque(maxlen=self.period)
        self._neg: deque = deque(maxlen=self.period)

    def _compute(self, value):
        b = self._bar(value)
        tp = (b.high + b.low + b.close) / 3
        mf = tp * b.volume
        if self._prev is not None:
            self._pos.append(mf if tp > self._prev else 0.0)
            self._neg.append(mf if tp < self._prev else 0.0)
        self._prev = tp
        p, n = sum(self._pos), sum(self._neg)
        return 100.0 if n == 0 and p > 0 else (100 * p / (p + n) if p + n else 50.0)


class ParabolicStopAndReverse(_BarIndicator):
    def __init__(self, af_start: float = 0.02, af_increment: float = 0.02, af_max: float = 0.2, name: str = ""):
        super().__init__(name or "PSAR")
        self._args = (af_start, af_increment, af_max, name)
        self.warm_up_period = 2
        self._s, self._i, self._m = af_start, af_increment, af_max
        self._long, self._sar, self._ep, self._af, self._prev = True, None, None, af_start, None

    def _compute(self, value):
        b = self._bar(value)
        if self._prev is None:
            self._prev = b
            return b.close
        if self._sar is None:
            self._long = b.close >= self._prev.close
            self._sar = self._prev.low if self._long else self._prev.high
            self._ep = b.high if self._long else b.low
        else:
            self._sar = self._sar + self._af * (self._ep - self._sar)
            if self._long:
                self._sar = min(self._sar, self._prev.low, b.low)
                if b.low < self._sar:
                    self._long, self._sar, self._ep, self._af = False, self._ep, b.low, self._s
                elif b.high > self._ep:
                    self._ep, self._af = b.high, min(self._af + self._i, self._m)
            else:
                self._sar = max(self._sar, self._prev.high, b.high)
                if b.high > self._sar:
                    self._long, self._sar, self._ep, self._af = True, self._ep, b.high, self._s
                elif b.low < self._ep:
                    self._ep, self._af = b.low, min(self._af + self._i, self._m)
        self._prev = b
        return self._sar


class Beta(Indicator):
    """Beta of `target` returns on `reference` returns over `period` sessions (fed with both symbols' closes)."""

    def __init__(self, target, reference, period: int, name: str = ""):
        super().__init__(name or f"BETA({_sym(target)},{_sym(reference)},{period})")
        self._args = (target, reference, period, name)
        self.target, self.reference = _sym(target), _sym(reference)
        self.period = int(period)
        self.warm_up_period = self.period + 1
        self._last: Dict[str, Any] = {}
        self._prev: Dict[str, float] = {}
        self._rt: deque = deque(maxlen=self.period)
        self._rr: deque = deque(maxlen=self.period)

    def update_pair(self, time, symbol: str, close: float) -> None:
        self._last[symbol] = (time, close)
        if all(k in self._last for k in (self.target, self.reference)) and \
                self._last[self.target][0] == self._last[self.reference][0]:
            t, r = self._last[self.target][1], self._last[self.reference][1]
            if self.target in self._prev:
                self._rt.append(t / self._prev[self.target] - 1)
                self._rr.append(r / self._prev[self.reference] - 1)
            self._prev = {self.target: t, self.reference: r}
            self.samples += 1
            if len(self._rr) > 2:
                rr, rt = np.array(self._rr), np.array(self._rt)
                v = float(np.var(rr, ddof=1))
                if v > 0:
                    self.current = IndicatorDataPoint(time, float(np.cov(rt, rr, ddof=1)[0, 1] / v))
            for cb in self.updated:
                cb(self, self.current)
            self._last.clear()

    def _compute(self, value):
        return None


class _Composite(Indicator):
    """IndicatorExtensions: an indicator over another indicator's values, or a combination of two."""

    def __init__(self, name: str, fn: Callable[[], Optional[float]], sources: List[Indicator], warm: int):
        super().__init__(name)
        self._fn = fn
        self.warm_up_period = warm
        for s_ in sources:
            s_.updated += (lambda sender, pt: self._tick(pt))

    def _tick(self, pt) -> None:
        self.samples += 1
        v = self._fn()
        if v is not None and np.isfinite(v):
            self.current = IndicatorDataPoint(pt.time, v)
        for cb in self.updated:
            cb(self, self.current)

    def _compute(self, value):
        return None


class IndicatorExtensions:
    @staticmethod
    def _over(inner: Indicator, outer: Indicator, name: str) -> Indicator:
        def fn():
            if inner.is_ready:
                outer.update(None, inner.current.value)
            return outer.current.value
        return _Composite(name, fn, [inner], inner.warm_up_period + outer.warm_up_period - 1)

    @staticmethod
    def sma(indicator: Indicator, period: int, *a) -> Indicator:
        return IndicatorExtensions._over(indicator, SimpleMovingAverage(period), f"SMA({period}) of {indicator.name}")

    @staticmethod
    def ema(indicator: Indicator, period: int, *a) -> Indicator:
        return IndicatorExtensions._over(indicator, ExponentialMovingAverage(period), f"EMA({period}) of {indicator.name}")

    @staticmethod
    def of(second: Indicator, first: Indicator, *a) -> Indicator:
        return IndicatorExtensions._over(first, second, f"{second.name} of {first.name}")

    @staticmethod
    def _combine(a, b, op, sym) -> Indicator:
        val = (lambda x: x.current.value if isinstance(x, Indicator) else float(x))
        srcs = [x for x in (a, b) if isinstance(x, Indicator)]
        name = f"{getattr(a, 'name', a)} {sym} {getattr(b, 'name', b)}"
        return _Composite(name, lambda: op(val(a), val(b)), srcs, max(x.warm_up_period for x in srcs))

    @staticmethod
    def plus(a, b) -> Indicator:
        return IndicatorExtensions._combine(a, b, lambda x, y: x + y, "+")

    @staticmethod
    def minus(a, b) -> Indicator:
        return IndicatorExtensions._combine(a, b, lambda x, y: x - y, "-")

    @staticmethod
    def times(a, b) -> Indicator:
        return IndicatorExtensions._combine(a, b, lambda x, y: x * y, "×")

    @staticmethod
    def over(a, b) -> Indicator:
        return IndicatorExtensions._combine(a, b, lambda x, y: x / y if y else float("nan"), "/")

    SMA, EMA, Of, Plus, Minus, Times, Over = sma, ema, of, plus, minus, times, over


# ── QCAlgorithm: more of LEAN's helpers ──────────────────────────────────────
def _bars_ind(ind) -> bool:
    return isinstance(ind, (AverageTrueRange, AverageDirectionalIndex)) or getattr(ind, "needs_bars", False)


def _helper(cls_):
    def make(self, symbol, *a, **k):
        ind = cls_(*a, **{kk: v for kk, v in k.items() if kk not in ("resolution", "selector")})
        return self._reg(symbol, ind, _bars_ind(ind))
    make.__doc__ = f"{cls_.__name__}, created and updated with each daily bar."
    return make


for _n, _c in {"wma": LinearWeightedMovingAverage, "lwma": LinearWeightedMovingAverage, "hma": HullMovingAverage,
               "dema": DoubleExponentialMovingAverage, "tema": TripleExponentialMovingAverage,
               "kama": KaufmanAdaptiveMovingAverage, "trix": Trix, "apo": AbsolutePriceOscillator,
               "ppo": PercentagePriceOscillator, "cmo": ChandeMomentumOscillator, "logr": LogReturn,
               "tr": TrueRange, "natr": NormalizedAverageTrueRange, "cci": CommodityChannelIndex, "sto": Stochastic,
               "wilr": WilliamsPercentR, "aroon": AroonOscillator, "dch": DonchianChannel, "kch": KeltnerChannels,
               "obv": OnBalanceVolume, "vwap": VolumeWeightedAveragePriceIndicator, "mfi": MoneyFlowIndex,
               "psar": ParabolicStopAndReverse, "delay": Delay, "identity": Identity}.items():
    setattr(QCAlgorithm, _n, _helper(_c))


def _beta(self, target, reference, period: int, *a, **k) -> Beta:
    b = Beta(target, reference, period)
    self._betas.append(b)
    return b


def _record(self, key: str, value) -> None:
    hdr = self.__dict__.setdefault("_hdr", {})
    hdr[key] = value


def _date_of(args) -> Optional[str]:
    if len(args) >= 3 and all(isinstance(a, (int, np.integer)) for a in args[:3]):
        return str(date(int(args[0]), int(args[1]), int(args[2])))
    if args and isinstance(args[0], (datetime, date, pd.Timestamp)):
        return str(pd.Timestamp(args[0]).date())
    if args and isinstance(args[0], str):
        return str(pd.Timestamp(args[0]).date())
    return None


def _set_start_date(self, *a, **k):
    d = _date_of(a)
    if d:
        _record(self, "start", d)
        self.start_date = pd.Timestamp(d).to_pydatetime()


def _set_end_date(self, *a, **k):
    d = _date_of(a)
    if d:
        _record(self, "end", d)
        self.end_date = pd.Timestamp(d).to_pydatetime()


def _set_cash(self, *a, **k):
    amt = next((x for x in reversed(a) if isinstance(x, (int, float)) and not isinstance(x, bool)), None)
    if amt is not None:
        _record(self, "capital", float(amt))


_orig_set_benchmark = QCAlgorithm.set_benchmark


def _set_benchmark(self, symbol):
    _orig_set_benchmark(self, symbol)
    _record(self, "benchmark", _sym(symbol))


_INDEX = {"SPX": "^GSPC", "NDX": "^NDX", "VIX": "^VIX", "DJI": "^DJI", "RUT": "^RUT", "SPY": "SPY"}


def _add_index(self, ticker: str, resolution=Resolution.DAILY, *a, **k) -> Security:
    t = _INDEX.get(_sym(ticker).lstrip("^"), _sym(ticker) if _sym(ticker).startswith("^") else "^" + _sym(ticker))
    return self._add(t, resolution)


class _Notify:
    def __getattr__(self, name):                       # email / sms / web / telegram: no live channel in backtests
        return lambda *a, **k: True


def _train(self, *a, **k):
    fn = next((x for x in a if callable(x)), None)
    if fn is not None:
        self._approx.add("train: runs the function immediately (no background training in a backtest)")
        fn()


_extra = {
    "beta": _beta, "set_start_date": _set_start_date, "set_end_date": _set_end_date, "set_cash": _set_cash,
    "set_benchmark": _set_benchmark, "add_index": _add_index, "add_cfd": QCAlgorithm.add_equity,
    "set_warmup": QCAlgorithm.set_warm_up, "train": _train,
    "buy": lambda self, symbol, quantity, *a, **k: self.market_order(symbol, abs(quantity), tag=k.get("tag", "")),
    "sell": lambda self, symbol, quantity, *a, **k: self.market_order(symbol, -abs(quantity), tag=k.get("tag", "")),
    "order": lambda self, symbol, quantity, *a, **k: self.market_order(symbol, quantity, tag=k.get("tag", "")),
    "is_market_open": lambda self, symbol=None: True,
    "set_account_currency": lambda self, ccy, *a, **k: (None if str(ccy).upper() == "USD" else self._approx.add(
        "set_account_currency: use ACCOUNT_CURRENCY = \"…\" at the top of the file for a non-USD account")),
    "set_run_mode": lambda self, *a, **k: None, "set_runtime_statistic": lambda self, name, value: _record(self, f"stat:{name}", str(value)),
    "set_parameters": lambda self, params: self.__dict__.setdefault("_params", {}).update(params or {}),
    "set_security_initializer": QCAlgorithm.set_security_initializer,
    "on_margin_call": lambda self, requests: requests, "on_margin_call_warning": lambda self: None,
    "on_dividends": lambda self, dividends: None, "on_splits": lambda self, splits: None,
    "on_delistings": lambda self, delistings: None, "on_symbol_changed_events": lambda self, events: None,
    "on_brokerage_message": lambda self, message: None, "on_assignment_order_event": lambda self, event: None,
}
for _n, _f in _extra.items():
    setattr(QCAlgorithm, _n, _f)

_orig_qc_init = QCAlgorithm.__init__


def _qc_init(self):
    _orig_qc_init(self)
    self._betas: List[Beta] = []
    self._hdr: Dict[str, Any] = {}
    self.notify = self.Notify = _Notify()


QCAlgorithm.__init__ = _qc_init
QCAlgorithm.utc_time = property(lambda self: self.time)

# ── portfolio, holdings, securities, transactions, events, slices ───────────
SecurityHolding.unrealized_profit_percent = property(
    lambda self: (self.price / self.average_price - 1) * (1 if self.quantity > 0 else -1)
    if self.average_price and np.isfinite(self.price) and self.invested else 0.0)
SecurityHolding.holdings_cost = property(lambda self: self.quantity * self.average_price)
SecurityHolding.absolute_quantity = property(lambda self: abs(self.quantity))
SecurityHolding.average_price_ = SecurityHolding.average_price if hasattr(SecurityHolding, "average_price") else None
Portfolio.total_unrealized_profit = property(lambda self: sum(h.unrealized_profit for h in self.values()))
Portfolio.total_absolute_holdings_cost = property(lambda self: sum(abs(h.holdings_cost) for h in self.values()))
Portfolio.total_margin_used = property(lambda self: 0.5 * self.total_holdings_value)
Portfolio.get_buying_power = lambda self, *a, **k: 2.0 * self.total_portfolio_value - self.total_holdings_value
Portfolio.keys_ = dict.keys


class _Exchange:
    exchange_open = True
    ExchangeOpen = True

    def date_is_open(self, *a, **k) -> bool:
        return True

    DateIsOpen = date_is_open


Security.holdings = property(lambda self: getattr(self, "_holding", None) or SecurityHolding(self.symbol))
Security.is_tradable = property(lambda self: not getattr(self, "_custom_type", None))
Security.exchange = property(lambda self: _Exchange())
Security.ask_price = Security.bid_price = property(lambda self: self.price)
Security.is_delisted = False
Security.fundamentals = None

Transactions.get_orders = lambda self, *a, **k: list(self._algo._tickets.values())
Transactions.get_order_by_id = lambda self, order_id: self._algo._tickets.get(order_id)
Transactions.cancel_order = lambda self, order_id, *a, **k: (self._algo._tickets[order_id].cancel()
                                                           if order_id in self._algo._tickets else False)
Transactions.orders_count = property(lambda self: len(self._algo._tickets))
OrderEvent.quantity = property(lambda self: self.fill_quantity)
OrderEvent.absolute_fill_quantity = property(lambda self: abs(self.fill_quantity))
OrderEvent.order_fee = property(lambda self: 0.0)

_orig_slice_init = Slice.__init__


def _slice_init(self, time, bars):
    _orig_slice_init(self, time, bars)
    # prices are split- and dividend-adjusted, so these corporate-action collections are always empty
    self.splits, self.dividends, self.delistings, self.symbol_changed_events = (_SymbolDict(), _SymbolDict(),
                                                                                _SymbolDict(), _SymbolDict())
    self.quote_bars, self.ticks = _SymbolDict(), _SymbolDict()


Slice.__init__ = _slice_init
Slice.has_data = property(lambda self: len(self._b) > 0)

# both spellings on every object strategy code touches
for _cls in (QCAlgorithm, Security, SecurityHolding, Portfolio, Slice, TradeBar, OrderTicket, OrderEvent, Indicator,
             IndicatorDataPoint, RollingWindow, Insight, Fundamental, PortfolioTarget, ObjectStore, Transactions, Schedule,
             DateRules, TimeRules, SecurityChanges, _Group, TradeBarConsolidator, _SubscriptionManager, AlphaModel,
             PortfolioConstructionModel, RiskManagementModel, ExecutionModel, _UniverseHelper, _Settings, _UniverseSettings):
    if "__getattr__" not in _cls.__dict__:
        _cls.__getattr__ = _case_getattr

NAMES.update({k: v for k, v in globals().items() if k in (
    "LinearWeightedMovingAverage", "HullMovingAverage", "DoubleExponentialMovingAverage", "TripleExponentialMovingAverage",
    "KaufmanAdaptiveMovingAverage", "Trix", "AbsolutePriceOscillator", "PercentagePriceOscillator",
    "ChandeMomentumOscillator", "LogReturn", "Delay", "Identity", "TrueRange", "NormalizedAverageTrueRange",
    "CommodityChannelIndex", "Stochastic", "WilliamsPercentR", "AroonOscillator", "DonchianChannel", "KeltnerChannels",
    "OnBalanceVolume", "VolumeWeightedAveragePriceIndicator", "MoneyFlowIndex", "ParabolicStopAndReverse", "Beta",
    "IndicatorExtensions", "Indicator", "PythonIndicator")})
NAMES["PythonIndicator"] = Indicator                     # custom indicators: subclass and implement update / _compute
NAMES["QCAlgorithmFramework"] = QCAlgorithm


class UpdateOrderFields:
    """ticket.update(UpdateOrderFields(stop_price=…, limit_price=…, quantity=…, tag=…)) — LEAN's order update."""

    def __init__(self, quantity=None, limit_price=None, stop_price=None, trigger_price=None, trailing_amount=None, tag=None,
                 **k):
        self.quantity = k.get("Quantity", quantity)
        self.limit_price = k.get("LimitPrice", limit_price)
        self.stop_price = k.get("StopPrice", stop_price)
        self.trailing_amount = k.get("TrailingAmount", trailing_amount)
        self.tag = k.get("Tag", tag)

    def __setattr__(self, name, value):                 # fields.LimitPrice = 101 works too
        object.__setattr__(self, _snake(name) if any(c.isupper() for c in name) else name, value)


def _ticket_update(self, fields: UpdateOrderFields):
    """Cancel-and-replace the working order with the new prices / quantity (the ticket keeps its id)."""
    if self.status not in (OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED):
        return _Response(False, "the order is no longer open")
    algo = self._algo
    q = float(fields.quantity) if fields.quantity is not None else self.quantity
    price = fields.stop_price if fields.stop_price is not None else (
        fields.limit_price if self.order_type == OrderType.LIMIT and fields.limit_price is not None else self.prices.get("price"))
    limit = fields.limit_price if self.order_type == OrderType.STOP_LIMIT and fields.limit_price is not None else self.prices.get("limit")
    trail = fields.trailing_amount if fields.trailing_amount is not None else self.prices.get("trail")
    kind = {OrderType.LIMIT: "limit", OrderType.STOP_MARKET: "stop", OrderType.STOP_LIMIT: "stop_limit",
            OrderType.TRAILING_STOP: "trailing"}.get(self.order_type)
    if kind is None:
        return _Response(False, "market orders fill at the next open and cannot be updated")
    ids = [oid for oid, tk in algo._tickets.items() if tk is self]
    for oid in ids:
        algo._ctx.cancel_order(oid)
    rem = q - self.quantity_filled
    new_id = algo._ctx.order_shares(_sym(self.symbol), rem, kind, price=price, limit=limit, trail=trail)
    algo._tickets[new_id] = self
    self.quantity = q
    self.prices.update({k_: v for k_, v in (("price", price), ("limit", limit), ("trail", trail)) if v is not None})
    if fields.tag is not None:
        self.tag = fields.tag
    algo._emit(OrderEvent(self.order_id, self.symbol, algo.time, OrderStatus.UPDATE_SUBMITTED, message=self.tag))
    return _Response(True, "")


class _Response:
    def __init__(self, ok: bool, message: str):
        self.is_success, self.error_message = ok, message
        self.IsSuccess, self.ErrorMessage = ok, message


OrderTicket.update = _ticket_update
OrderTicket.update_stop_price = lambda self, p, tag=None: self.update(UpdateOrderFields(stop_price=p, tag=tag))
OrderTicket.update_limit_price = lambda self, p, tag=None: self.update(UpdateOrderFields(limit_price=p, tag=tag))
OrderTicket.update_quantity = lambda self, q, tag=None: self.update(UpdateOrderFields(quantity=q, tag=tag))
OrderTicket.get = lambda self, field, *a: {"stop_price": self.prices.get("price"), "limit_price": self.prices.get("limit")}.get(
    _snake(str(field)), None)
NAMES["UpdateOrderFields"] = UpdateOrderFields
NAMES["OrderField"] = type("OrderField", (), {"STOP_PRICE": "stop_price", "LIMIT_PRICE": "limit_price",
                                              "StopPrice": "stop_price", "LimitPrice": "limit_price"})


# custom-data plumbing names used inside PythonData subclasses (get_source / reader are never called — the uploaded CSV
# is the data — but the class body must still import cleanly)
class SubscriptionDataSource:
    def __init__(self, source=None, transport=None, format=None, *a, **k):
        self.source, self.transport, self.format = source, transport, format


class SubscriptionTransportMedium(_Enum):
    LOCAL_FILE, REMOTE_FILE, REST, STREAMING, OBJECT_STORE = "local", "remote", "rest", "streaming", "object_store"
    LocalFile, RemoteFile, Rest, Streaming, ObjectStore = LOCAL_FILE, REMOTE_FILE, REST, STREAMING, OBJECT_STORE


class FileFormat(_Enum):
    CSV, UNFOLDING_COLLECTION, ZIP_ENTRY_NAME, INDEX = "csv", "unfolding", "zip", "index"
    Csv, UnfoldingCollection, ZipEntryName, Index = CSV, UNFOLDING_COLLECTION, ZIP_ENTRY_NAME, INDEX


NAMES.update({"SubscriptionDataSource": SubscriptionDataSource, "SubscriptionTransportMedium": SubscriptionTransportMedium,
              "FileFormat": FileFormat})


UNSUPPORTED.pop("train", None)
APPROXIMATED["train"] = "runs the function immediately (no background training in a backtest)"


def _alias_both_spellings(cls) -> None:
    """Class-level aliases (Symbol.Create / Symbol.create, Insight.Price / Insight.price, constants): what instance
    __getattr__ cannot cover, because it is reached through the class itself."""
    for name, val in list(cls.__dict__.items()):
        if name.startswith("_") or isinstance(val, property):
            continue                                       # properties: instance __getattr__ covers them (no setter clash)
        alts = {_snake(name)} if any(ch.isupper() for ch in name) else {_pascal(name)}
        for alt in alts:
            if alt and alt != name and alt not in cls.__dict__ and not any(alt in b.__dict__ for b in cls.__mro__[1:]):
                try:
                    setattr(cls, alt, val)
                except (AttributeError, TypeError):
                    pass


for _cls in {v for v in list(globals().values()) if isinstance(v, type) and v.__module__ == __name__}:
    _alias_both_spellings(_cls)



# ── C# collections: Keys / Values / Count are properties, and iterating yields key–value pairs ─────────
class _KVP(str):
    """What iterating Portfolio / Securities / a Slice yields: the ticker (a str, so `symbol in …`, dict lookups and
    printing work as before) that also carries LEAN's KeyValuePair fields — kvp.Key, kvp.Value."""

    def __new__(cls, key, value):
        o = str.__new__(cls, str(key))
        o.key = o.Key = Symbol(str(key))
        o.value = o.Value = value
        return o


def _dict_like(cls, getter):
    cls.Keys = property(lambda self: [Symbol(k) for k in dict.keys(self)] if issubclass(cls, dict) else list(self.keys()))
    cls.Values = property(lambda self: list(dict.values(self)) if issubclass(cls, dict) else list(self.values()))
    cls.Count = property(lambda self: len(self))
    cls.count = property(lambda self: len(self)) if "count" not in cls.__dict__ else cls.__dict__["count"]


for _c in (_SymbolDict, Portfolio):
    _dict_like(_c, None)
    _c.__iter__ = lambda self: iter([_KVP(k, dict.__getitem__(self, k)) for k in dict.keys(self)])

Slice.Keys = property(lambda self: self.keys())
Slice.Values = property(lambda self: self.values())
Slice.Count = property(lambda self: len(self))
Slice.__iter__ = lambda self: iter([_KVP(b.symbol, b) for b in self._b.values()])
ObjectStore.Keys = property(lambda self: list(self._d))


# ── label enums: every LEAN member works (unknown ones pass through as their name) ──────────────────────
class _PassThroughMeta(type):
    """Market.COINBASE, BrokerageName.KRAKEN, TimeZones.TOKYO …: these only label things on daily data, so any member LEAN
    has resolves (to its lower-case name) instead of stopping the algorithm."""

    def __getattr__(cls, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return _snake(name)


class Market(_Enum, metaclass=_PassThroughMeta):
    USA, OANDA, FXCM, DUKASCOPY, BITFINEX, GDAX, COINBASE, BINANCE, BINANCE_US, KRAKEN, BYBIT, BITSTAMP = (
        "usa", "oanda", "fxcm", "dukascopy", "bitfinex", "coinbase", "coinbase", "binance", "binanceus", "kraken", "bybit",
        "bitstamp")
    CME, CBOT, NYMEX, COMEX, ICE, CFE, CBOE, NASDAQ, NYSE, INDIA, NSE, SGX, HKFE, EUREX, OSE, JAPAN, FTX, INTERACTIVE_BROKERS = (
        "cme", "cbot", "nymex", "comex", "ice", "cfe", "cboe", "nasdaq", "nyse", "india", "nse", "sgx", "hkfe", "eurex",
        "ose", "japan", "ftx", "interactivebrokers")


class BrokerageName(_Enum, metaclass=_PassThroughMeta):
    DEFAULT, INTERACTIVE_BROKERS_BROKERAGE, ALPACA, TRADIER_BROKERAGE, QUANTCONNECT_BROKERAGE = (
        "default", "ibkr", "alpaca", "tradier", "default")
    COINBASE, GDAX, BINANCE, BINANCE_US, KRAKEN, BITFINEX, BYBIT, OANDA_BROKERAGE, FXCM_BROKERAGE, TD_AMERITRADE, CHARLES_SCHWAB = (
        "coinbase", "coinbase", "binance", "binanceus", "kraken", "bitfinex", "bybit", "oanda", "fxcm", "tdameritrade",
        "schwab")


class SecurityType(_Enum, metaclass=_PassThroughMeta):
    EQUITY, FOREX, CRYPTO, CRYPTO_FUTURE, CFD, INDEX, OPTION, FUTURE, FUTURE_OPTION, INDEX_OPTION, BASE = (
        "equity", "forex", "crypto", "cryptofuture", "cfd", "index", "option", "future", "futureoption", "indexoption", "base")


class DataNormalizationMode(_Enum, metaclass=_PassThroughMeta):
    ADJUSTED, RAW, SPLIT_ADJUSTED, TOTAL_RETURN, FORWARD_PANAMA_CANAL, BACKWARDS_RATIO = (
        "adjusted", "raw", "split_adjusted", "total_return", "forward_panama_canal", "backwards_ratio")


class TimeZones(_Enum, metaclass=_PassThroughMeta):
    NEW_YORK, UTC, CHICAGO, LONDON, TOKYO, HONG_KONG, SINGAPORE, SYDNEY, FRANKFURT, PARIS, ZURICH, TORONTO, KOLKATA = (
        "America/New_York", "UTC", "America/Chicago", "Europe/London", "Asia/Tokyo", "Asia/Hong_Kong", "Asia/Singapore",
        "Australia/Sydney", "Europe/Berlin", "Europe/Paris", "Europe/Zurich", "America/Toronto", "Asia/Kolkata")


class OptionRight(_Enum, metaclass=_PassThroughMeta):
    CALL, PUT = "call", "put"


class OptionStyle(_Enum, metaclass=_PassThroughMeta):
    AMERICAN, EUROPEAN = "american", "european"


class Field:
    """Indicator input selectors: self.sma(symbol, 20, Resolution.DAILY, Field.HIGH)."""
    OPEN = staticmethod(lambda b: b.open)
    HIGH = staticmethod(lambda b: b.high)
    LOW = staticmethod(lambda b: b.low)
    CLOSE = VALUE = staticmethod(lambda b: b.close)
    VOLUME = staticmethod(lambda b: b.volume)
    AVERAGE = staticmethod(lambda b: (b.open + b.high + b.low + b.close) / 4)
    MEDIAN = staticmethod(lambda b: (b.high + b.low) / 2)
    TYPICAL_PRICE = staticmethod(lambda b: (b.high + b.low + b.close) / 3)
    WEIGHTED_CLOSE = staticmethod(lambda b: (b.high + b.low + 2 * b.close) / 4)
    SEVEN_BAR = SDEV = None


for _cls in (Market, BrokerageName, SecurityType, DataNormalizationMode, TimeZones, OptionRight, OptionStyle, Field):
    _alias_both_spellings(_cls)
for _n in ("Open", "High", "Low", "Close", "Value", "Volume", "Average", "Median", "TypicalPrice", "WeightedClose"):
    setattr(Field, _n, getattr(Field, _snake(_n).upper()))
NAMES.update({"Market": Market, "BrokerageName": BrokerageName, "SecurityType": SecurityType,
              "DataNormalizationMode": DataNormalizationMode, "TimeZones": TimeZones, "OptionRight": OptionRight,
              "OptionStyle": OptionStyle, "Field": Field})

# ── indicator selectors: a callable (Field.HIGH, lambda bar: …) after the period feeds that value, not the close ──
_SELECTOR_HELPERS = ("sma", "ema", "rsi", "bb", "macd", "roc", "rocp", "momp", "mom", "max", "min", "std", "wma", "lwma",
                     "hma", "dema", "tema", "kama", "trix", "apo", "ppo", "cmo", "logr", "delay", "identity")


def _with_selector(fn):
    def wrapped(self, symbol, *a, **k):
        sel = k.pop("selector", None)
        rest = []
        for x in a:
            if sel is None and callable(x) and not isinstance(x, type) and not isinstance(x, str):
                sel = x
            else:
                rest.append(x)
        ind = fn(self, symbol, *rest, **k)
        if sel is not None:
            ind._selector = sel
        return ind
    wrapped.__doc__ = fn.__doc__
    return wrapped


for _n in _SELECTOR_HELPERS:
    if _n in QCAlgorithm.__dict__:
        setattr(QCAlgorithm, _n, _with_selector(QCAlgorithm.__dict__[_n]))
        setattr(QCAlgorithm, _n.upper(), getattr(QCAlgorithm, _n))
