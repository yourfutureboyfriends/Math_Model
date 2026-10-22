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
| Indicators | stateful, updated bar by bar: SMA, EMA (seeded with the SMA of its first n inputs), Wilder RSI / ATR, Bollinger (population σ), MACD, ROC/ROCP, momentum, max/min of the close, std, ADX; `RollingWindow` | matched to LEAN's reference values |
| C# generics & collections | `RollingWindow[float](n)`, `RollingWindow[TradeBar](n)` — `[T]` is accepted on every layer class; `List[T]` (`Add`, `Count`, `Contains`, `Remove`), `Dictionary[K, V]` (`Add`, `ContainsKey`, `TryGetValue` → `(found, value)`, `Keys`, `Values`), `HashSet[T]`; windows also have `Size`, `IsFull`, `Samples`, `MostRecentlyRemoved` and slices (`window[0:5]`, newest first) | same names |
| Warm-up | indicators are primed bar by bar on the history before the start; `set_warm_up(n)` also calls `on_data` for those n bars with `is_warming_up` (orders refused) | same |
| Universes | `add_universe(selector)` runs each session on **point-in-time S&P 500 members** with a bar (`symbol, price, volume, dollar_volume`); additions/removals call `on_securities_changed`; `universe.etf("SPY")` = point-in-time S&P 500 | no market cap or Morningstar fields; other ETFs' historical constituents are not free |
| History | `history(symbols, n | timedelta)` → DataFrame (symbol, time) × OHLCV, never past the current bar | same shape |

## Two engines

QuantConnect algorithms run on **real LEAN by default** whenever Docker and the image are available — the only way to
behave exactly like QuantConnect is to run QuantConnect's engine. The built-in layer is the fallback (Docker off) and
the engine for paper deployment and the research checks.

| | Real LEAN (`Run`) | Built-in layer (`Run on built-in layer`) |
|---|---|---|
| Engine | QuantConnect's own LEAN, unmodified (`quantconnect/lean` image) | a Python re-implementation of LEAN's API (qc-compat) on the Code Lab engine |
| Prices | the platform's daily prices in LEAN's format: US equities (factor 1, already adjusted), crypto pairs on any LEAN venue (USD pairs stand in for stablecoin pairs), FX pairs; bid = ask (no free spread) | platform daily data: any market, FX, crypto |
| Universes | LEAN's own coarse and SPY-constituent files written per session from the point-in-time S&P 500 membership; `add_universe`, `universe.etf("SPY")`, the selection models run natively | point-in-time S&P 500 through the layer's selector |
| Fundamentals | a fundamental-data provider plugin fills `Fundamental`: `has_fundamental_data`, today's Morningstar sector code, SEC EDGAR filings point in time (market cap, shares, EPS, P/E, P/B, P/S, earnings / book / sales / FCF yield, ROE, ROA, gross / net margin, debt-to-assets, revenue, net income, gross profit, assets, liabilities, equity, free cash flow). Other Morningstar fields read as LEAN's defaults (0 / NaN); the run lists the ones used | the same SEC values and sector codes |
| Custom data | the algorithm's own `get_source` is run (sandbox) to find its URLs; the platform fetches them (public http/https only, ≤ 50 MB, cached a day) and LEAN runs the algorithm's own `reader` on them | the CSV uploaded under the `add_data` name |
| Resolution | free data is daily: tick / second / minute / hour requests (including LEAN's minute default when none is given) are served as daily and listed in the run's notes | daily |
| Use when | exact QuantConnect behaviour | paper deployment; look-ahead, capacity and Monte Carlo checks; non-US listings |

Real LEAN runs in a container with no network and dropped capabilities; it needs Docker running and the image
(~40 GB unpacked). The platform adds two things around the unmodified engine: a fundamental-data provider plugin
(`api/quant/lean_plugin`, compiled in the image, offline) and a thin subclass of the algorithm (`zzQuantLabDaily`,
appended to `main.py`) that maps finer resolutions to daily. Not available on free data: intraday bars, options and
futures chains, QuantConnect's alternative datasets.

## Multi-file projects

QuantConnect projects with several files: paste each extra file below a marker line —
`# file: alpha.py` (folders: `# file: alphas/rsi.py` → `import alphas.rsi`). Everything above the first marker is
`main.py`. The files are importable in both engines; line numbers in errors stay the editor's.

## How the universe is found

The importer reads `initialize()` without running it to learn which prices to load. When a ticker comes from something
it cannot follow — a module constant, a comprehension, a helper function — it **runs `initialize()` inside the sandbox**
(the container on the server; in the browser where the code already runs) with no data and records what was added;
the report lists those lines as "resolved by running initialize()". Calls that need prices (history, warm-up) are
skipped in that pass.

Universe selectors also receive `asset_classification.morningstar_sector_code` (today's sector for every date — free
sector history does not exist; industry codes are NaN) and `MorningstarSectorCode.TECHNOLOGY` etc.

## Algorithm Framework

```python
class Trend(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_universe_selection(ManualUniverseSelectionModel(
            [Symbol.create(t, SecurityType.EQUITY, Market.USA) for t in ["SPY", "TLT", "GLD"]]))
        self.set_alpha(EmaCrossAlphaModel(20, 60))                       # insights
        self.set_portfolio_construction(EqualWeightingPortfolioConstructionModel())   # insights → targets
        self.add_risk_management(MaximumDrawdownPercentPerSecurity(0.10))             # targets adjusted
        self.set_execution(ImmediateExecutionModel())                                  # targets → orders
```

Each session after `on_data`: new insights from the alpha models (and `emit_insights`), expired ones dropped (an
insight's period counts sessions); targets are rebuilt when insights change or the portfolio model's `rebalance` is
due; risk models adjust them; the execution model orders the difference. Your own models subclass `AlphaModel`
(`update`), `PortfolioConstructionModel` (`create_targets`), `RiskManagementModel` (`manage_risk`) or `ExecutionModel`
(`execute`), snake_case or PascalCase.

| Built in | |
|---|---|
| Alpha | `ConstantAlphaModel`, `EmaCrossAlphaModel`, `MacdAlphaModel`, `RsiAlphaModel`, `HistoricalReturnsAlphaModel`, `NullAlphaModel` |
| Portfolio | `EqualWeighting…`, `InsightWeighting…`, `ConfidenceWeighting…`, `RiskParity…` (inverse volatility), `Null…`; `portfolio_bias` |
| Risk | `MaximumDrawdownPercentPerSecurity`, `MaximumUnrealizedProfitPercentPerSecurity`, `MaximumDrawdownPercentPortfolio`, `TrailingStopRiskManagementModel`, `CompositeRiskManagementModel` |
| Execution | `ImmediateExecutionModel`; VWAP / standard-deviation / spread models fill like it (no intraday data — reported) |
| Universe | `ManualUniverseSelectionModel([...])` (read without running the code), `FundamentalUniverseSelectionModel(selector)` |

## Consolidators, object store, custom data

* `self.consolidate(symbol, Calendar.WEEKLY | MONTHLY | QUARTERLY | YEARLY | n_sessions | timedelta(days=7), handler)`;
  `TradeBarConsolidator(period)` with `data_consolidated += handler`, `subscription_manager.add_consolidator`;
  `register_indicator(symbol, indicator, Calendar.WEEKLY)` feeds an indicator weekly bars. Bars close on the last
  session of their period. Intraday periods are refused (no intraday data).
* `self.object_store.save / read / save_json / read_json / save_bytes / read_bytes / contains_key / delete / keys` —
  kept between server runs of the same algorithm class (10 MB); a browser run keeps it for that run.
* Custom data: upload a CSV (date column + numeric columns) under a name in Code Lab, then
  `self.add_data(MyData, "name")` (a `PythonData` subclass; `get_source` / `reader` are not called) — `slice[symbol]`
  on sessions with a fresh row (`.value`, `.time`, `point["column"]`), `history(symbol)`. Plain strategies:
  `CUSTOM_DATA = ["name"]` → `data.custom["name"]`. A row dated d is known from d's close.

## Not available on free data

Historical option and futures chains (`add_option`, `add_future`, …): the report flags them and the built-in layer
refuses the run. Minute / second / tick history: on real LEAN, intraday requests get **hourly** bars from Yahoo when the
backtest starts within about the last two years (for the securities the algorithm adds; universes stay daily), and
daily bars otherwise — every run lists each mapping. QuantConnect's licensed alternative datasets. Live brokerages.

## Isolation and what code may do

Server runs execute in a **throwaway Docker container** per run — no network, read-only root filesystem, every
capability dropped, no privilege escalation, an unprivileged user, memory / CPU / process caps; only the run's data
folder and the engine are mounted. Real LEAN runs in its own container the same way. Without Docker the built-in layer
falls back to a separate process under macOS `sandbox-exec` with an audit hook. Browser runs are isolated by the browser.

**Libraries.** Strategies may import any installed library. Two runtimes: the platform's scientific stack (numpy,
pandas, scipy, scikit-learn, statsmodels — also what the browser carries) and **QuantConnect's own research
environment** in the LEAN image (~800 packages: torch, tensorflow, keras, xgboost, lightgbm, catboost, TA-Lib, ta, arch,
cvxpy, hmmlearn, pykalman, PyPortfolioOpt, prophet, sktime, statsforecast, numba, …). A strategy that imports
something outside the first set runs on the server in the second, automatically. On real LEAN every library works. On
the built-in layer, libraries that call C code through `ctypes` at run time (xgboost, lightgbm, TA-Lib) run in the
Docker sandbox (the container is the boundary); the macOS fallback sandbox refuses ctypes. Strategy code itself can
never import or name `ctypes`.

**Python.** The code check is a short blocklist:

* allowed — any Python: classes, inheritance, metaclasses, any special method, decorators, dataclasses, async code,
  `__class__` / `__dict__` / `vars()`, private names (only `_ql_…` is reserved for the engine), your own `__init__`
  on the algorithm (with or without `super().__init__()`), `open` (the run-time guard refuses the run's data folder and
  writes outside a scratch folder), `io.StringIO`, `pickle`, threads, and computed settings in plain strategies
  (`UNIVERSE = [f"XL{s}" for s in "KFE"]` — evaluated in the sandbox);
* refused — system, process and network modules (`os`, `sys`, `subprocess`, `ctypes`, `importlib`, `socket`, `requests`,
  …: there is no network — outside data comes in as custom data or a `get_source` URL on real LEAN), the platform's own
  modules, `eval` / `exec` / `compile`, and frame / code-object / globals internals. These guard the engine's context,
  which holds the whole price history: reaching it would be look-ahead (integrity, not security).

**Limits.** Code up to 2 MB; 1,800 s per server run; universes up to 12,000 names; parameter grids up to 500
combinations; custom data uploads up to 200 MB / 20 M rows / 2,000 columns.

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
| Point-in-time fundamentals | **done** — SEC XBRL (US) in vectorised strategies and in universe selectors with LEAN names (market_cap, valuation_ratios, operation_ratios, earning_reports) |
| Delisted securities | partly — removed S&P members with free price history; 161 without are reported |
| Multi-currency accounting, FX | **done** (vectorised and event engines) |
| Strategy-language issues (`hasattr`, `_`, classes) | **done**; compile-time checks with line numbers |
| Intraday data | **not available** free beyond Yahoo's short windows (2 years hourly) |
| Historical option / futures chains, assignment on real contracts | **not available** free (options research uses labelled model prices) |
| Algorithm Framework (alpha, portfolio construction, risk, execution, universe models) | **done** (daily) |
| Consolidators | **done** for daily → weekly / monthly / quarterly / yearly / n-session bars; intraday not available |
| Object store, custom data | **done** (server store per algorithm class; CSV uploads) |
| Python language limits | **lifted** — isolation moved to a per-run container; a short blocklist remains |
| Settlement delays, cash accounts, buying-power reservations, rejected-order reasons | **done** — cash accounts trade on settled cash (T+2 before 28 May 2024, T+1 after); margin accounts Reg-T 2× net of open orders; rejected orders carry a reason |
| Tax lots, short-sale locates | **done** — FIFO lots with short/long-term realised P&L; shorts refused under $5 or $5m average traded value (policy assumption — no free borrow data) |
| Live broker integration | **out of scope by policy** (paper only) |
| Parity with LEAN | **indicators done** — 16 tests against LEAN's own reference data (api/tests/test_qcalgo_lean_parity.py); whole-algorithm parity still needs LEAN runs on identical data |
