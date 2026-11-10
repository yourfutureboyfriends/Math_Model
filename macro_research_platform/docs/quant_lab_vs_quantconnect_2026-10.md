# Quant Lab vs QuantConnect (LEAN) — audit and upgrade, 13 October 2026

QuantConnect is the reference open platform for algorithmic research: the LEAN engine (open source), hosted data,
research notebooks, optimisation and live brokerage connections. This compares the Quant Lab with it feature by
feature, after the upgrade in this commit. ✅ at or above parity · ⚠️ partial · ❌ missing.

## Engine and simulation

| Feature | QuantConnect | Quant Lab | |
|---|---|---|---|
| Self-financing ledger, cash and holdings | ✅ | ✅ units + cash, reconciled daily | ✅ |
| Fill models: market at next bar, limit, stop | ✅ | ✅ next open / next-day VWAP / next close; limit, stop (gap-through fills at the open) | ✅ |
| Stop-limit, trailing stop, bracket / one-cancels-other | ✅ (stop-limit, trailing; OCO via code) | ✅ **new**: `ctx.stop_limit`, `ctx.trailing_stop`, `ctx.bracket` | ✅ |
| Market-on-open / market-on-close per order | ✅ | ⚠️ per run (`exec_price`), not per order | ⚠️ |
| Partial fills / volume limits | ✅ volume-share slippage | ✅ participation cap, remainder carried | ✅ |
| Slippage and market impact | ✅ constant/volume-share | ✅ liquidity- and volatility-based spread, square-root impact (AQR-calibrated), exchange tick floors | ✅+ |
| Brokerage fee models (IB, Alpaca, …) | ✅ | ✅ **new**: per-share with minimum and cap (IBKR Pro Fixed/Tiered), $0 PFOF brokers, IBKR non-US, crypto exchange fee | ✅ |
| Margin / buying power, margin calls | ✅ | ✅ maintenance margin with forced deleveraging; options 15%; FX ≈5% | ✅ |
| Short borrow | ✅ (constant, or data) | ✅ hard-to-borrow tiers by liquidity (no real borrow data) | ⚠️ |
| Settlement (T+1), cash vs margin accounts | ✅ | ❌ margin account only | ❌ |
| Event-driven API with real account state | ✅ `OnData` | ✅ `on_bar(ctx)` (+ vectorised `strategy(data)`) | ✅ |
| Warm-up | ✅ `SetWarmUp` | ✅ automatic history before `START` | ✅ |
| Scheduled events | ✅ date/time rules | ✅ `rebalance(w, "W"/"M"/"Q"/n)`, `hold_monthly`, `on_rolls` | ✅ |
| Universe selection (coarse/fine) | ✅ dynamic | ✅ `TRADABLE_UNIVERSE` (country/region/global, point-in-time S&P 500) + **new** `top_liquid(data, n)` | ✅ |
| Indicator library | ✅ 100+ | ✅ **new**: 22 core indicators (SMA/EMA/WMA/HMA, RSI, MACD, Bollinger, ATR, ADX, stochastic, Williams %R, CCI, ROC, z-score, Donchian, Keltner, OBV, MFI, VWAP, beta, drawdown) — vectorised over the whole universe | ⚠️ fewer, faster |
| Custom charts / logging | ✅ `Plot`, `Log` | ✅ **new** `plot()` / `ctx.plot()` → Charts tab; `print` → Output | ✅ |
| Multi-currency accounts | ✅ | ✅ 38 account currencies, FX at as-of rates, hedging, withholding tax | ✅+ |

## Asset classes and data

| | QuantConnect | Quant Lab | |
|---|---|---|---|
| US equities, survivorship-free | ✅ (paid data, free in cloud) | ⚠️ today's lists + point-in-time S&P 500 | ⚠️ |
| Global equities | ⚠️ limited | ✅ 3,100 largest companies in 40+ markets (free, Yahoo) | ✅+ |
| Crypto | ✅ | ✅ **new**: spot, every-day calendar, exchange fees | ✅ |
| Forex | ✅ | ✅ **new**: pairs as total-return (spot + carry) instruments | ✅ |
| Options | ✅ real chains | ⚠️ modelled (Black–Scholes on the VIX family), validated vs CBOE PUT | ⚠️ |
| Futures | ✅ continuous, roll-adjusted | ❌ (no free roll-adjusted data) | ❌ |
| Fundamentals | ✅ Morningstar | ✅ SEC XBRL point-in-time (US) | ✅ |
| Alternative data | ✅ marketplace | ⚠️ 13F holdings, macro data elsewhere on the platform | ⚠️ |
| Resolution | ✅ tick → daily | ❌ daily only | ❌ |

## Research, validation, reporting

| | QuantConnect | Quant Lab | |
|---|---|---|---|
| Backtest report: equity curve, drawdown, rolling stats | ✅ | ✅ deep report (calendar, regimes, crises, bootstrap) | ✅+ |
| Order log and trade statistics | ✅ | ✅ **new**: order log (CSV), round trips, win rate, P/L ratio, profit factor, expectancy, holding time | ✅ |
| Parameter optimisation | ✅ grid/Euler, cloud nodes | ✅ walk-forward over `PARAMS` + **new** sensitivity heatmap; ⚠️ ≤ 48 combinations | ⚠️ |
| Overfitting statistics (PSR/DSR, PBO, CPCV) | ⚠️ PSR | ✅ PSR, deflated Sharpe with trial registry, PBO, CPCV | ✅+ |
| Look-ahead detection | — (prevented by design) | ✅ automatic check for vectorised code | ✅ |
| Capacity | ✅ estimate | ✅ curve $1m–$1bn | ✅ |
| Attribution / risk models | ⚠️ | ✅ holdings, currency, Brinson; statistical + factor risk; stress tests | ✅+ |
| Research notebooks | ✅ Jupyter + QuantBook | ❌ (Code Lab only) | ❌ |
| Projects: multiple files, versioning, collaboration | ✅ | ⚠️ saved strategies, stored runs, compare | ⚠️ |
| Languages | Python, C# | Python (numpy/pandas) | ⚠️ |

## Deployment

| | QuantConnect | Quant Lab | |
|---|---|---|---|
| Paper trading | ✅ | ✅ three books, append-only daily record, alerts | ✅ |
| Live brokerage | ✅ 20+ brokers | ❌ by policy (no real orders) | — |

## Built in this upgrade

Indicator library, `rebalance`, `top_liquid`, `plot`/`ctx.plot` with a Charts tab; order log and trade
statistics with CSV export (Trades tab); stop-limit, trailing-stop and bracket orders; broker fee presets with
per-share commissions on traded share prices; crypto and forex as tradable asset classes; calendar-aware
annualisation (crypto's 365-day year); parameter-sensitivity heatmap. Tests: `api/tests/test_research_grade.py`.

## Still behind QuantConnect (by value)

1. **Intraday data** — Yahoo gives 2 years of hourly bars free; an hourly mode would cover most intraday research.
2. **Research notebook** — a cell-based scratchpad in the browser (Pyodide already runs the engine).
3. **Futures** — needs roll-adjusted continuous contracts (build from individual contract months, not free on Yahoo).
4. **Real option chains and borrow rates** — paid data.
5. **Bigger optimisation grids** — run on the server as a job (today ≤ 48 combinations).
6. **Per-order market-on-open/close** and cash-account settlement.
