# Quant Lab algorithm API — QuantConnect compatibility layer (qc-compat/1, daily)

Imported LEAN (QuantConnect) Python algorithms run on the Code Lab's event engine **without being rewritten as
pandas weight tables**: their `initialize`, `on_data`, scheduled events, universe changes, order tickets and events,
stateful indicators and warm-up keep their structure. Module: `api/quant/qcalgo.py`; engine hooks: `Ctx.order_shares`,
`Ctx.executions`, share-quantity orders in `codelab.backtest`. Tests: `api/tests/test_qcalgo.py`. Example:
`examples/quantconnect/ema_cross_rotation.py`.

Paste a LEAN algorithm into **Code Lab**. The check line under the editor shows a compatibility report (supported /
approximated / unsupported, by line) produced **statically** — the server never executes user code outside the
sandbox. `GET /api/v1/quant/code/api` lists the API.

## What a file looks like

```python
from AlgorithmImports import *          # accepted (a no-op: every name is already defined)

class MyAlgo(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2016, 1, 1)   # literals: read without running the code
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        for t in ["SPY", "TLT"]:          # literal lists (also class attributes) are expanded
            self.add_equity(t, Resolution.DAILY)
        self.fast = self.ema("SPY", 50)
        self.set_warm_up(200)
        self.schedule.on(self.date_rules.month_start("SPY"), self.time_rules.after_market_open("SPY", 30), self.rebalance)

    def rebalance(self):
        self.set_holdings("SPY", 0.6 if self.fast.current.value < self.securities["SPY"].price else 0.0)

    def on_order_event(self, order_event):
        if order_event.status == OrderStatus.FILLED:
            self.debug(f"filled {order_event.fill_quantity} {order_event.symbol} @ {order_event.fill_price}")
```

Both the snake_case API and the older PascalCase one (`SetStartDate`, `AddEquity`, `OnData`, `SetHoldings`, …) work.
Top-level `PARAMS = {"name": [values]}` still drives walk-forward; read the current value with `self.get_parameter`.

## Semantics

| Area | Behaviour | vs LEAN |
|---|---|---|
| Data | daily bars, split- and dividend-adjusted (total return) | LEAN default is adjusted too; raw / split-only modes not available |
| Event time | `on_data`, scheduled events and universe selection run after each session's close | LEAN also delivers daily bars after the close |
| Time rules | `after_market_open(n)`, `before_market_close(n)`, `at(h, m)` run at that session's close decision | **approximated** — no intraday data |
| Market orders | fill at the next session's open, in shares | LEAN converts daily-data market orders to market-on-open: same |
| Market-on-close | fills at the next session's close | same |
| Limit / stop / stop-limit / trailing | checked against each later session's high/low; a gap through fills at the open | same idea; no intraday path |
| Partial fills | a participation cap (default 10% of 63-day traded value) splits an order over days: `PARTIALLY_FILLED` events | LEAN's fill models differ |
| Costs | the Code Lab model (spread, impact, commission, SEC fee, borrow, financing); `set_brokerage_model(InteractiveBrokers…)` → $0.005/share, $1 min, 1% cap | close to LEAN's IB fee model |
| Margin | maintenance margin with a forced cut (margin call) | LEAN models per-security buying power |
| Holdings | shares; `portfolio[s].quantity / invested / average_price / unrealized_profit`, `total_portfolio_value`, `cash` | same names |
| Orders | `OrderTicket` (`status`, `quantity_filled`, `average_fill_price`, `cancel()`), `OrderEvent` (SUBMITTED → PARTIALLY_FILLED → FILLED / CANCELED), `transactions.get_open_orders / cancel_open_orders` | a market order already sent to the next open cannot be cancelled |
| Indicators | stateful, updated bar by bar: SMA, EMA (seeded with the first value), Wilder RSI / ATR, Bollinger (population σ), MACD, ROC/ROCP, momentum, max/min, std, ADX; `RollingWindow` | LEAN definitions |
| Warm-up | indicators are primed bar by bar on the history before the start; `set_warm_up(n)` also calls `on_data` for those n bars with `is_warming_up` (orders refused) | same |
| Universes | `add_universe(selector)` runs each session on **point-in-time S&P 500 members** with a bar (`symbol, price, volume, dollar_volume`); additions/removals call `on_securities_changed`; `universe.etf("SPY")` = point-in-time S&P 500 | no market cap or Morningstar fields; other ETFs' historical constituents are not free |
| History | `history(symbols, n | timedelta)` → DataFrame (symbol, time) × OHLCV, never past the current bar | same shape |

## Not available (the report flags these by line and the run is refused)

Historical option and futures chains (`add_option`, `add_future`, …), consolidators, minute/second/tick data, custom
data, the Algorithm Framework (`set_alpha`, `set_portfolio_construction`, `set_execution`, `set_risk_management`),
object store, downloads, live brokerages.

## Sandbox rules for algorithm classes

Classes may derive only from `QCAlgorithm` (the algorithm) or nothing/`object` (helpers such as `SymbolData`), without
decorators or metaclasses. Allowed special methods: `__init__` (helpers only — the algorithm uses `initialize`),
`__repr__`, `__str__`, `__len__`, comparisons, `__hash__`. `self._name` is allowed for names the code itself assigns and
the API does not use internally; `self` cannot be reassigned; methods are reached only through instances
(`Class.method` is refused). Imports: numpy, pandas, math, datetime, `AlgorithmImports`. Built-ins add `hasattr`,
`callable`, `next`, `iter`. Dunder access, `getattr`, `type`, file/network access remain blocked, as before.

## Status against the engine-gap review (2026-10)

| Gap | Status |
|---|---|
| Event-driven API (initialize, data events, scheduled events, security changes, order events, warm-up) | **done** (daily) |
| Scheduled execution (month-end, week-start, open + 30 min, 5 min before close) | date rules done; time-of-day **approximated** (daily) |
| Order lifecycle (submitted, partial, filled, cancelled, invalid) | **done**; rejected-for-margin reasons not modelled |
| Stateful indicators, rolling windows, exact warm-up | **done** for the listed indicators |
| Market / limit / stop / stop-limit / trailing / MOO / MOC | **done** |
| Partial fills, volume-aware fills | **done** (participation cap) |
| Broker commissions, minimum fees, regulatory fees | **done** (presets; SEC fee) |
| Margin calls, forced liquidation | **done** (account-level) |
| Dynamic universes, security-change events | **done** on point-in-time S&P 500 |
| Point-in-time membership | S&P 500 **done**; QQQ / sector ETFs — no free source |
| Point-in-time fundamentals | SEC XBRL (US) in vectorised strategies; not yet exposed to selectors |
| Delisted securities | partly — removed S&P members with free price history; 161 without are reported |
| Multi-currency accounting, FX | **done** (vectorised and event engines) |
| Strategy-language issues (`hasattr`, `_`, classes) | **done**; compile-time checks with line numbers |
| Intraday data | **not available** free beyond Yahoo's short windows (2 years hourly) |
| Historical option / futures chains, assignment on real contracts | **not available** free (options research uses labelled model prices) |
| Settlement delays (T+1), cash accounts, tax lots, short-sale locates | **not done** |
| Live broker integration | **out of scope by policy** (paper only) |
| Deterministic parity tests against known QuantConnect algorithms | **not done** — needs LEAN reference outputs on the same data |
