# Next-stage implementation — 3 November 2026

## Available workflows

Open **Markets → Research desk → Open evidence tools**. New tabs: Macro vintages, Portfolio stress, Probability check and Experiment history. Existing evidence tools now offer guided fields, an advanced JSON editor, file import and drafts retained when switching tabs during the current session. Results have readable tables alongside full calculation evidence and export. Evaluated macro/stress/probability results can be saved through existing versioned research storage.

### Macro historical comparison

- Reuses ALFRED with bounded complete revision-interval downloads; truncated responses are rejected.
- Rebuilds each decision's training panel from observations/revisions available by its month-end. Excludes incomplete observation months and aligns inputs to earliest archived availability months. This alignment is conservative and differs from the old approximate-lag method.
- Compares US vintage-selected versus revised-data models over 1–24 evaluation months with identical model parameters and return histories. A request lock prevents concurrent expensive comparisons in one process; downloads are limited to three concurrent requests.
- Reports selected-input hashes, 17-series coverage, common scored months, probability differences and new/revised/withdrawn source observations. Future interval expiry changes do not alter earlier selected-input hashes.
- Works as an explicit research tool. Existing live macro allocations and order generation continue using their disclosed current input basis.

Limitations: daily ALFRED dates do not verify intraday availability or always establish an observation's original publication date. Returns, FX and cash-rate histories are not archived point-in-time. Comparisons combine revision and alignment effects. Source changes are not causal probability contributions. Final factor-based outcome labels can change with re-estimation and are not GDP/CPI outcomes. International vintage models and an automatic production switch are not included.

### Probability reliability

Existing macro backtests now include Brier/log scores, baseline-relative Brier skill, reliability bins, counts, calibration error and descriptive Wilson intervals. The Macro Model page displays these diagnostics and clarifies the final-factor target basis. The standalone workbench rejects future outcomes, training after forecast issue and duplicate issue times; evaluate one model/target/horizon per request. No recalibration is fitted on the evaluation sample. Wilson intervals assume independent binary outcomes and may be too narrow for overlapping/serially dependent forecasts.

### Original forecast replay

New primary FCFF and excess-return valuations can carry a trusted server artifact linking the engine source, effective constants, exact inputs and keyword arguments, recorded FX, expected output and Python version. Artifacts are content-addressed and atomically written, with a 250 MB run-storage budget. Repeated identical artifacts are reused.

**Capture audit → Rerun archived forecast** verifies the saved valuation against its server artifact, then executes the archived forecasting code in a separate isolated Python interpreter. A Python audit hook blocks socket/process operations; uncaptured provider dependencies fail. Imported JSON cannot provide executable source or arbitrary artifact paths. Replay checks exact output equality and reports key value differences.

Limitations: this is not an OS-level sandbox for arbitrary untrusted code; only server-created engine artifacts are accepted. The exact Python version is required. DDM, source ingestion, sensitivity grids and macro engine replay are not included. Old captures retain the arithmetic replay path. No historic executable bundle is fabricated for them. Archive storage failure leaves valuation available but marks the artifact unavailable.

### Valuation expectations

The existing DCF expectations panel now shows a frontier of alternative growth/margin combinations that reconcile to the current price, with solved-case revenue/reinvestment evidence in the response. Other assumptions remain fixed. This extends existing reverse DCF, cyclical normalization and reinvestment rules; it does not impose a regional market discount or fit intrinsic assumptions to current prices. No unique simultaneous growth/margin/discount solution is claimed.

### Portfolio stress and liquidity

Load actual direct holdings, then supply explicit instrument types, base-currency values and sensitivities. Unspecified holdings remain uncovered rather than receiving an assumed equity beta.

- Equity beta and multiplicative FX shocks.
- Bond duration plus convexity with rates/spread shocks; approximate, unsuitable for defaults and embedded-option repricing.
- European vanilla option full Black–Scholes repricing with explicit contract, volatility, rate, dividend, multiplier, quantity and FX terms. Instantaneous shocks retain time-to-expiry; P&L is anchored to the supplied current market value. American/path-dependent options remain unsupported.
- Stressed-volume/participation ADV liquidation estimates, explicit cash/redemptions and supplied margin rates. No assumed sale proceeds, broker netting or short collateral are invented.
- Reverse stress along a supplied shock path: sample for a loss-threshold breach, then refine the first detected bracket. This is not a globally most probable stress scenario.

Position P&L and gross-value coverage are shown together. Incomplete coverage withholds total scenario P&L and margin completeness. All amounts use the declared base currency. Direct holdings are not historical fund look-through, and capacity estimates are not executable liquidity.

### Experiment registry and performance

Experiment history audits existing account-wide Code Lab/strategy records, including missing Sharpe metrics and repeated holdout evaluation. Counts are not advertised as a complete historical search registry. The existing quant registry is shared account research, not a fund-specific portfolio ledger. Database initialization now recognizes a changed database path. The proof-page headline no longer calls historical alpha criteria proven alpha.

Admin performance diagnostics now include route median latency, bounded stage p95/error statistics and request-linked stage totals for cache fills and Yahoo/ALFRED calls. Internal bounded stage names are used; no symbols, query strings, credentials or research payloads are retained. Nested/concurrent durations overlap, so stage totals must not be summed as wall-clock latency. These remain process-local measurements, not a durable distributed tracing installation.

## Validation and outstanding work

Tests cover future revisions and releases, stable input hashes, incomplete months, source-change classifications, probability bins and leakage, original-code replay/configuration/FX/checksums, account registry isolation, stress reconciliation, short positions, option put–call parity, unsupported coverage and guided forms. Production types/build and affected backend/frontend suites are checked separately.

Validation passed: 85 backend acceptance/regression tests; a separate affected DCF/Code Lab/proof/snapshot suite passed 82 tests (overlapping suites, not additive); 536 frontend unit/component tests; five focused UI tests after the final form additions; TypeScript and the production build. The build retains its large-chunk warning. An attempted live-API frontend suite could not connect from the sandbox and is not counted as passing.

A January–March 2025 US comparison through the existing source/cache paths completed with 17 configured series, two common scored months and two source-change windows. This did not independently verify a fresh upstream fetch; cache timestamps and that limitation are now exposed. It confirms the integration operates; two observations do not establish forecast skill or investment usefulness. No new monitoring, trade, notification or subscription was activated. Tests use temporary accounts/databases; no illustrative research records were written to the user's fund. The running browser reached sign-in without captured JavaScript errors; populated authenticated pages were not visually verified.

Remaining roadmap work: sourced segment-level forecasts and cross-accounting-standard normalization adapters, international vintage histories, calibrated production probability models, macro/DDM executable archives, complete experiment capture across every engine, dated ETF/fund look-through and entitled intraday/execution data. These require further implementation or additional data; this release does not claim those capabilities are complete.
