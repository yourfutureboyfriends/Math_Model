# Next-stage research priorities — 3 November 2026

This is a research and engineering recommendation, not an implementation or demonstrated investment edge. It follows the evidence-workbench implementation and compares selected current code with primary-source methodology and institutional product documentation. Vendor descriptions establish capabilities, not accuracy. This is not a new exhaustive audit of every route.

## 1. Make macro backtests vintage-correct

**Confirmed gap:** `api/model/data.py`, `economies.py`, `quality.py` and `backtest.py` disclose revised inputs and approximate monthly lags. `api/handlers/macro_inputs.py:cpi_release_series` uses an approximate publication date. ALFRED already exists in `api/providers/alfred.py` and selected economic-release tools, so the next task is integration, not another provider wrapper.

Use each decision date to select available vintages, actual release dates and train-only transformations. Persist the selected vintage IDs. Distinguish daily information availability from monthly factor dates and do not pretend day-level ALFRED dates establish an intraday release time. Report performance against revised-history results so the revision effect is visible.

Acceptance: a later revision cannot change an earlier saved decision; unreleased observations remain unavailable; revised versus real-time results are separately labelled. Start with a bounded US model before extending international coverage.

Sources: [FRED real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html), [observation API](https://fred.stlouisfed.org/docs/api/fred/series_observations.html).

## 2. Explain macro forecast changes and calibrate probabilities

Add a release-by-release explanation separating new observations, revisions, changing model parameters and residual interactions. For the existing regime model, distinguish a change in standardized factor level from a forecast of GDP or CPI. Evaluate direction probabilities with reliability bins, Brier/log scores, sample counts and time-ordered out-of-sample comparisons to a simple baseline. Fit probability calibration only on training windows.

The New York Fed describes tracking both its nowcast and the impact of new releases. That is a useful workflow reference; it does not establish that the platform's model has comparable predictive performance.

Acceptance: explanations reconcile to the output change under a disclosed method; probabilities marked 70% can be compared with actual frequencies, with uncertainty and small samples visible.

Source: [New York Fed Staff Nowcast](https://www.newyorkfed.org/research/policy/nowcast/).

## 3. Strengthen valuation assumptions, rather than impose regional discounts

Existing DCF already contains reverse valuation, cyclical-margin normalization, reinvestment, terminal checks and SBC treatment. Extend these with segment-level revenue/margin/capital requirements, sourced market-size feasibility checks, explicit normalization bridges and a joint reverse-expectations frontier. One price cannot uniquely identify growth, margin and discount rate simultaneously.

Add cross-market accounting comparability: IFRS/US GAAP research capitalization, lease treatment, fiscal-period alignment and share/ADR units. Each optional adjustment must reconcile to reported accounts. Avoid subtracting SBC twice when EBIT already expenses it. Show which assumptions dominate value and distinguish intrinsic assumptions from a market-implied expectations view.

Acceptance: growth has an associated reinvestment requirement; segment values reconcile; incompatible accounting bases are flagged; country and sector differences are supported by inputs. Do not lower US or European fair values merely because a market appears expensive.

Sources: [Damodaran growth value drivers](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/littlebook/growthvaluedrivers.htm), [fundamental determinants of growth](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/growth.htm).

## 4. Connect stress tests, liquidity and actual holdings

Extend existing portfolio analytics into a saved scenario workspace: rate curves, FX, credit spreads, equity factors and volatility. Reprice nonlinear instruments with their models rather than applying equity beta to everything. Add reverse stress questions such as which supported shocks breach a chosen loss or cash threshold.

Combine price stress with lower trading volume, wider costs, redemption needs and margin requirements where contract data exists. Make holding dates, ETF look-through dates and unknown exposure shares visible; do not silently renormalize incomplete coverage to 100%.

Acceptance: scenario P&L reconciles by position and currency; unknown exposures remain unknown; liquidity assumptions and model sensitivity are inspectable. Estimated liquidation capacity is not guaranteed executable volume.

Sources: [MSCI total portfolio solutions](https://www.msci.com/data-and-analytics/total-portfolio-solutions), [BIS stress-testing principles](https://www.bis.org/committees/bcbs/basel-consolidated-guidelines/module/rma/30). These are methodological references, not a claim that banking requirements apply to this application.

## 5. Finish reproducibility and production data controls

The new workbench captures checksums and replays saved FCFF arithmetic; it does not archive the original forecasting engine. Add trusted server-side model artifacts, dependency locks, effective configuration and input references, with a network-disabled replay worker. Never execute source code supplied in imported observation JSON.

Extend metadata coverage into expected-universe coverage, provider disagreement queues and field-specific validity rules. Start with a disclosed stratified sample across developed markets, sectors and company sizes. Report missing combinations, real filing comparisons and unresolved discrepancies, not just test counts.

Acceptance: a saved model reruns under its original engine and inputs; numerical tolerance is declared; source verification is distinct from a passing software test. Licensed data storage rights remain a prerequisite where applicable.

## 6. Make research validation govern the entire experiment history

The platform already has deflated Sharpe/overfitting checks and a durable strategy/Code Lab registry in `api/quant/store.py`, including unsuccessful Code Lab runs and holdout views. Extend and audit that registry across all research engines, parameter searches, universe versions and costs. In `api/quant/proof.py`, the trial count is constructed from loaded strategies and signal collections; verify its relationship to actual historical searches rather than treating the current catalogue size as the complete search history. An automatically displayed correction is not meaningful if the number of trials is incomplete.

Add time-ordered train/test partitions, leakage tests for overlapping forecast horizons, delisted securities where available, and parameter stability reports. Reserve a final untouched evaluation period; a strategy revised after viewing it needs a new evaluation boundary. Explicitly label survivor-selected universes.

Acceptance: trial counts include unsuccessful runs; feature availability follows information time; results show net costs, baseline comparison, universe coverage and the number of observations. Do not present a robustness score as proof of future alpha.

## 7. Replace technical imports with guided analyst workflows

The evidence workbench is useful but several workflows require JSON. Add typed forms with units/date validation, sample previews, recoverable drafts and inline links back to source fields. Keep advanced JSON available. Carry selected security, fund, currency and information cutoff between valuation, filings, portfolio and inbox pages.

Add linked comparison views, saved workspace layouts, useful empty states and keyboard navigation. Use a consistent evidence panel for observed, estimated, proxy, missing and stale values. Avoid a single unexplained quality score that combines unrelated problems.

Acceptance: an analyst can capture a source discrepancy, inspect affected holdings, compare a valuation and record a review without copying JSON between pages. No outbound notification or trading is required.

## 8. Measure reliability from the page to its upstream source

Existing caching, single-flight and circuit-breaker work should be retained. Extend request timing into request-to-provider traces, refresh queues, cache age/hit rates and upstream error classes. Track page-specific p50/p95 latency, cold-load behavior and stale-response frequency before choosing optimizations. Avoid putting credentials or raw sensitive research payloads in telemetry.

Acceptance: a slow page can be attributed to its provider, computation or rendering; concurrent refreshes are bounded; stale responses show observation time; performance budgets are measured under representative load. Prefer lazy loading and table virtualization where measured rendering cost justifies them.

Source: [OpenTelemetry signals](https://opentelemetry.io/docs/concepts/signals/).

## Delivery order

1. Vintage-correct US macro integration and explicit revised-versus-real-time evaluation.
2. Guided evidence workflows and measured provider/page reliability, alongside full model archival.
3. Joint valuation expectation analysis and accounting reconciliation on a representative company sample.
4. Portfolio stress/liquidity integration, calibrated macro probabilities and the experiment ledger.
5. Broader international, consensus and intraday sources after coverage and entitlement evaluation.

Public official data can support the first steps. Complete broker consensus, historical constituents, global intraday quotes, detailed fund look-through and actual cargo manifests may require licensed feeds. No subscription, new scheduled collection, external message or runtime behavior was changed by this research.
