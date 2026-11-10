---
date: 2026-10-13
tags: [quant, options, implementation]
status: implemented-pending-market-validation
---

# Multi-strategy options decision engine

Implemented 13 October 2026. This is a native Python backend and authenticated Quant Lab API. It applies externally validated configurations; it does not fit models or optimize parameters. No paper book or approved trading configuration was deployed during development. Live execution has no adapter and is rejected.

## What changed

`api/quant/optengine/` contains independent bull put credit, bull call debit, bear put debit and short iron condor builders; regime classification; opportunity measurement; portfolio risk sizing; paper accounting; historical replay; and a versioned configuration/audit registry. `api/routers/options_engine.py` exposes these through the existing quant router. The working GLOBAL strategy is preserved byte-for-byte in `api/quant/optengine/baselines/options_strategy_universal_v1.py`.

The other AI's `optresearch` package and its active research work were left separate. Existing Code Lab `strategy(data)` and `OPTIONS/data.opt` paths remain usable. This engine uses a new native replay endpoint because real contract quotes, currencies, exercise events and settlement instructions cannot be represented honestly by merely pasting a live order generator into that daily target-weight interface. No new frontend tab was added; the API is available through the existing app router and its API documentation after normal server reload.

## Strategy decisions

| Module | Legs and initial selection | Additional entry requirements |
| --- | --- | --- |
| `bull_put` | Short OTM put near 25 absolute delta, long lower put near 10; 30–45 DTE | Bullish trend/momentum; IV above forecast RV; premium/risk, net edge and confidence thresholds |
| `bull_call` | Long call near 50 delta, short higher call near 25 | Strong bullish signal; positive expected net payoff and reward/risk after costs |
| `bear_put` | Long put near 50 absolute delta, short lower put near 25 | Bearish trend/momentum, no configured market rebound exclusion; bearish forecast sufficient to pay for the spread |
| `iron_condor` | OTM short put and call near 25, protective put/call wings near 10 | Range conditions, rich IV versus forecast RV, sufficient forecast edge after four-leg costs |

Each strategy has its own enable flag, delta targets/tolerance, DTE range, entry thresholds and exit settings. Builders enforce common underlying, expiry, currency, multiplier, exercise style and settlement type. No naked short strategy is enabled. Payoff bounds are computed from the actual selected strikes and quantities, rather than assumed from a strategy label. At most three contracts per delta target and two expiries are examined; these are computational candidate limits, not claims of globally optimal strike selection.

A regime only makes a strategy eligible. It cannot bypass forecast, cost, liquidity, assignment or portfolio checks. Insufficient advantage leaves cash unallocated. No minimum number of positions is imposed.

## Forecast and scoring contract

The implemented forecast is deliberately explicit: daily log-return mean equals a Quant Lab supplied intercept plus supplied coefficients on momentum, market momentum, realized volatility and drawdown features. Annual volatility is a supplied weighted blend of 20-, 63- and 252-session estimates. The engine performs no fitting, coefficient search or parameter sweep.

A validated forecast requires a validation identifier and a training-end timestamp strictly earlier than each decision. `validated=False` is the delivered default, so the default configuration creates no entries. A true flag is provenance supplied by the researcher, not an independently verified statistical result; paper approval also requires an explicit PM/risk review record.

Expected terminal spread payoff uses a conditional lognormal distribution and 41-node Gaussian quadrature. Daily log means are multiplied by estimated remaining trading sessions; annual volatility is scaled by calendar time. The score uses the worst expected net result across the central mean and the configured positive/negative mean uncertainty. The reported probability of profit is a model probability, not a historical win-rate. Zero uncertainty is allowed for mechanics testing but must not be treated as established forecast precision.

Entry costs use buying at ask plus slippage and selling at bid minus slippage, rounded outward to contract tick size. The expected-edge calculation reserves entry/exit commissions and closing spread/slippage costs. Delta, gamma, vega, theta, expiry, breakevens, entry debit/credit, maximum expiration payoff loss, reward, funding, expected net result and score terms are logged. Breakevens are quote-entry breakevens before fees and future exit costs. Score weights are configurable: initial edge 55%, direction 15%, liquidity 20%, diversification 10%.

This model assumes a constant conditional drift and volatility over the option horizon; it is not an American exercise pricing model or a calibrated volatility surface. Correlation is measured on observed underlying returns, not option payoff correlations. FX at entry is held fixed in the forecast scenarios; the book is revalued using subsequent supplied FX. These assumptions require Quant Lab stress tests and empirical validation.

## Full-universe screening and global instruments

The engine accepts the complete configured underlying universe, including non-US names, rather than a fixed ETF basket. The default universe identifier is `GLOBAL`; the provider identifier must match the pinned configuration. Actual access depends on the supplied history, contract master, quote provider and permitted instruments. A Yahoo underlying symbol does not establish that historical or executable options exist for it.

1. Compute cached indicators across the full underlying matrix using only rows whose available-at timestamps precede the decision.
2. Reject insufficient observations, stale history, missing FX, unsuitable underlying types and inadequate traded value.
3. Rank qualifying underlyings by absolute momentum relative to realized volatility; retain 75 by default.
4. Use a point-in-time chain availability index when provided. The JSON adapter builds this index from supplied chain records. Without an index, availability is verified when a finalist chain is loaded; the engine does not silently claim coverage.
5. Load up to 35 new finalist chains lazily and filter quotes by age, identity, source, DTE, volume, open interest and relative spread. Existing positions and pending orders have priority and can require additional chains.
6. Build, measure and rank eligible structures. Reserve risk sequentially and queue only qualifying whole-contract orders.

Feature cache and chain cache sizes are bounded. The engine only uses explicitly supplied native currencies and account-currency FX. Quote currency must match the spot currency; multiplier and settlement style come from contract metadata. Current supported underlyings are stocks, ETFs and indices with vanilla call/put contracts. Futures options, FX-delivery options, rate contracts and exotics require a delivery/settlement adapter and are rejected when identified as such. This is global equity-options support, not a claim that all asset classes share stock assignment mechanics.

Global history must use each observation's actual availability time and consistent price basis. Supply point-in-time tradability, country, sector and corporate-action data. Unknown sector/country values are pooled into conservative UNKNOWN concentration buckets. Keep underlying/strike price bases consistent around splits; the adapter does not infer contract adjustments from ticker strings. Unobserved bars are excluded from calculations, and each realized-volatility window needs at least 80% valid returns (with a ten-return minimum). Current-survivor membership is not a valid historical universe by itself.

## Risk and position management

Initial limits are ten positions, 1% defined loss per new position, 5% aggregate defined loss, 2% sector and 3% country loss budgets. Absolute underlying correlation of 0.80 joins exposures into a 2.5% correlated-loss budget. Missing required correlation blocks additional entries. Delta notional, vega per one volatility percentage point and gamma sensitivity also have limits. A 5% equity sizing buffer reduces immediate fee-related limit breaches; it does not replace the portfolio limits.

Sizing uses whole contracts and the tightest constraint. Physical shorts reserve full short-strike funding by default in addition to debit/fees where applicable. Internal cash/collateral and supplied broker buying power both constrain orders. These reserves are conservative paper funding estimates, not a broker margin calculation or a guarantee of stock-borrow availability. Existing positions are monitored for defined-loss, sector/country, correlation and Greek concentration. A 15% drawdown latches the emergency stop. Automated stops cancel pending entries and attempt exits with valid current quotes; missing quotes produce a blocked-data record rather than an invented fill.

Default exits are 50% of modeled maximum reward, a loss of 50% of initial defined-loss reserve, seven DTE, or 45 calendar holding days. Early-assignment hazards around known dividends and low extrinsic value can trigger exits. There is no auto-reset after a stop; investigate, flatten/reconcile and create a fresh reviewed paper book.

A signal snapshot cannot fill its own order. At the next supplied snapshot, the engine rechecks quotes, contract identity, liquidity, currency, regime, expiry, edge and risk. Paper fills are atomic multi-leg simulations at bid/ask plus costs; actual partial leg fills, broker latency, spread-order rejection and assignment timing are not established by this simulation.

American exercise/assignment is processed from explicit time-stamped events. Partial assignments split the position's affected contracts, record stock inventory and strike cashflows, and unwind the affected residual options and stock when valid quotes exist. Cash expiration needs a matching observed official settlement record. Physical expiration additionally requires explicit boolean exercise/assignment instructions for every remaining leg. The engine does not pretend that fixed expiration payoff bounds remove funding, delivery, borrowing or FX risk.

Cash accrues using the previously known supplied cash rate; negative balances include a configured financing spread. Commissions and exercise fees are denominated in the account currency. Funding and Greeks are converted using point-in-time account FX. Trading and economic accounting errors stop the book and roll back that tick's economic mutations.

## Quant Lab approval and execution workflow

All endpoints are under `/api/v1/quant/options-engine` and require the app's verified authentication/roles. Configuration and book ownership are checked; an arbitrary `X-User` header does not authorize access.

| Endpoint | Use |
| --- | --- |
| `GET /meta` | Four strategy names and a fail-closed default research export |
| `POST /configs` | Import `{"export": <optengine.quantlab.v1 JSON>}`; verify configuration hash |
| `GET /configs/{config_id}` | Inspect an owned immutable configuration version |
| `POST /backtest` | Research replay from supplied history, snapshots, chains and settlement events |
| `POST /configs/{config_id}/approve` | PM/risk acknowledgement with exact config hash, Quant Lab run ID, validation ID, reviewer and validation-end time; approval scope is paper only |
| `POST /configs/{config_id}/revoke` | Revoke approval; subsequent paper processing stops new exposure |
| `POST /books` | Create research or approved paper book; `mode=live` is rejected |
| `POST /books/{book_id}/tick` | One decision snapshot and its historical context |
| `POST /books/{book_id}/stop` | Explicit PM/risk emergency-stop reason and acknowledgement |
| `GET /books/{book_id}` | Account state, positions and queued intents |
| `GET /books/{book_id}/events` | Paginated complete audit, using `after` and `limit` |

Configurations are canonical JSON with SHA-256 content identifiers. Parameter changes create a new identity; approved ranges are checked, not searched. Import never trusts an external approved-status assertion. Approval requires a validated forecast, observed-quote-only data settings and a validation period after training and before review. Approval records are reviewer attestations; the engine does not independently establish that a provided run ID represents a good holdout. No configuration was approved in this implementation session.

Registry data lives in `data/processed/quant/options_engine.sqlite`. Each committed tick atomically updates book revision/state and appends audit records; conflicting writers receive HTTP 409. Large audit records are losslessly compressed. API research replay streams complete audit into a research book and returns at most 1,000 event records by default; the response supplies `audit.book_id`, total count and whether the returned portion is complete. Query the book's events for the full record. The book retains the latest 256 fill records for operational inspection; all fills remain in persistent audit. Direct Python replay can provide an `event_sink`; without one, only the bounded response is retained and this is disclosed.

Backtest API input is `{"config_id": "...", "capital": 1000000, "event_limit": 1000, "data": {...}}`. It returns daily returns, dates, account records and existing `codelab.metrics` results, plus decisions and data provenance. Annualized metrics assume daily research snapshots; do not interpret sparse/intraday snapshot results as daily annualization. The API has a 240-second cooperative replay limit and one replay worker; long provider jobs can use the direct Python replay interface with persistent event sinks.

## Provider data contract

`data.history` contains `symbols`, timezone-aware `available_at`, two-dimensional aligned `close` and `volume` arrays, optional aligned `observed` mask, `market` benchmark and point-in-time `metadata`. Metadata includes native currency, sector, country, tradability, optional underlying type and availability timestamp. `data.snapshots` is an ordered unique list. Each item contains:

- `snapshot`: decision `asof`, spot bid/ask with quoted/available timestamps and native currency; FX rates in account-currency units per native unit, FX availability time, account currency, annual cash rate and optional buying power, assignment events and dividends.
- `chains`: underlying → contract records. Required fields are contract ID, underlying, call/put, native strike, expiry timestamp, bid/ask, IV, signed delta, gamma, vega per one IV percentage point, theta, integer volume/open interest and quoted/available timestamps. Multiplier, currency, exercise, settlement, tick size and source should be explicit.
- `settlements`: underlying, matching expiry, currency, available time, official price and source; physical contracts also need `exercises: {contract_id: boolean}`.

Assignment records contain event ID, owned position ID, contract ID, integer contract count, effective/available timestamps and `assigned` or `exercised` action. Repeated event IDs are idempotent. Dividend events include amount, ex-date and availability time.

`HistoricalProvider` also supports a callback-based chain loader and snapshot provider for integration with research data storage. Chain access is lazy and cached. Data providers are responsible for truthful point-in-time provenance; timestamps supplied by a caller cannot independently prove when a record was known. Real historical bid/ask, open interest and exercise data were not available in this workspace. Modeled/fixture chains can be used only in explicitly enabled research; they cannot obtain paper approval. A modeled options series from free data is not an observed listed-contract quote.

## Research used and its limits

The cumulative research register accompanies this document. Earlier research included firm disclosures, academic papers, technical methodologies and exchange specifications; public availability is not the same as open-source licensing. The implementation uses original code and copies no third-party trading engine.

| Research | Relevant implementation choice | What was not reproduced |
| --- | --- | --- |
| [D. E. Shaw, Machine Teaching](https://www.deshaw.com/assets/articles/DESCO_Machine_Teaching_20231211.pdf) | Inspect forecast uncertainty and unintended concentration; keep reviewed constraints separate from runtime application | The firm's optimizer, forecasts or alpha |
| [AQR, Time Series Momentum](https://pages.stern.nyu.edu/~lpederse/papers/TimeSeriesMomentum.pdf) | Historical momentum as an observable feature family | Published futures portfolio and its returns; the selected 21/63/252 windows are engineering parameters |
| [Duke/Man, The Impact of Volatility Targeting](https://people.duke.edu/~charvey/Research/Published_Papers/P135_The_impact_of.pdf) | Fast/slow realized-volatility features and expansion guard | Published volatility-targeting portfolio or its asset-class performance |
| [AQR, Covered Call Strategies: One Fact and Eight Myths](https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/FAJ-Covered-Call-Strategies-One-Fact-and-Eight-Myths.pdf) | Separate underlying direction and volatility-premium exposure; deduct trading costs | Evidence that every single-stock spread has positive alpha |
| [CFM, Risk Premia: Asymmetric Tail Risks and Excess Returns](https://www.cfm.com/wp-content/uploads/2022/12/239-2014-Risk-Premia-Asymmetric-Tail-Risks-and-Excess-Returns.pdf) | Recognize short-volatility tail compensation; cap spread losses/concentration | A calibrated jump/tail distribution |
| [Goldman Sachs, corrections for discrete hedging](https://emanuelderman.com/wp-content/uploads/1998/12/risk-non_continuous_hedge.pdf) | Treat execution/hedging frictions as economically material | Continuous delta hedging, Black–Scholes replication or Goldman proprietary models |
| [J.P. Morgan/ETH, Deep Hedging](https://arxiv.org/abs/1802.03042) | Keep costs, risk constraints and realistic derivative state separate from signals | Neural hedging training, author code or validated predictive alpha |
| [Renaissance-affiliated Johnstone/Lu, Sparse PCA](https://arxiv.org/pdf/0901.4392), Two Sigma factor papers and Citadel Securities market-structure white paper | Retained in cumulative bibliography with verified affiliations and context | Sparse PCA, factor forecasting and Citadel alpha are not implemented in this engine |

These sources motivate engineering choices; they do not validate the four default delta/DTE choices or establish profitability. The conditional linear/lognormal forecast and ranking weights are explicit configurable engineering specifications awaiting Quant Lab calibration and validation. The previously weaker research variant was not promoted over the existing baseline.

## Verification and profiling

Run the targeted tests with the project's Python environment:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/daltonyuen/Math_Model/.venv/bin/python -m pytest --noconftest -p no:cacheprovider api/tests/test_options_decision_engine.py api/tests/test_options.py -q
```

Final targeted result: **64 passed**, with two pre-existing Pydantic deprecation warnings. The checks cover four bounded spread payoffs, each strategy's decision path, no-edge rejection, config/export validation, stale/future/missing data, point-in-time history, model/paper separation, all-universe lazy screening, FX/risk sizing, concentration, next-snapshot execution, cash reconciliation, partial physical assignment, expiry instructions, drawdown stops, missing-position-data rollback, approval/ownership, concurrent-write conflicts, audit compression/streaming and authenticated router/replay integration. Existing options tests run alongside them. Synthetic quotes/forecasts test mechanics; they are not historical market evidence.

Profiling preceded architecture changes. The old strategy on the cached 2,500-row/36-series fixture took 7.58 seconds under cProfile, with repeated pandas indexing among the hot paths. The new full-width scaling fixture uses 2,520 rows × 3,117 underlyings and profiles one final decision tick. Exact results are recorded in `options_engine_profile.json`. These scopes differ, so no speedup ratio is claimed. A ten-year actual options replay was not run.

## Remaining validation before paper approval

Connect an observed historical contract/quote provider with trustworthy availability times, historical membership, corporate-action adjustments and exercise/settlement data. Quant Lab must fit and freeze forecast/regime parameters on training data, evaluate chronological holdouts, compare net results against the unchanged baseline and relevant benchmarks, and test liquidity/capacity, clustered assignments, gaps and FX stress. Approval should reference that exact frozen configuration and run. Broker integration would require a separately authorized execution adapter, margin/borrow checks and real multi-leg order reconciliation.

The implementation is ready for these research/provider integrations. Improved growth, S&P outperformance and stable live profitability have not been demonstrated.

Companion research history: [[projects/quant-research/options/decision-engine-implementation]].
