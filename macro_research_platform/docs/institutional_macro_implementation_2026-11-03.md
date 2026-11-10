# Institutional macro laboratory implementation — 3 November 2026

Open **Markets → Research desk → Open macro laboratory**. The panel is lazily loaded alongside existing workflows, uses existing account/fund authorization and offers guided forms plus bounded JSON imports. Array inputs are paginated in groups of 20 to avoid rendering thousands of controls; all rows remain available to evaluation. Routine data collection begins only when requested. No new dependency or paid feed was installed.

## Release ledger and source-linked review

The release ledger is append-only, with a transactional server receipt time and event identity comprising country, indicator, reference period, units, transformation and seasonal basis. Forecasts distinguish analyst, model and declared-consensus inputs, with contributor count/dispersion left unknown when absent. Actuals/revisions require source publication timestamps. Revisions must reference the latest recorded actual and advance its publication date. Duplicate evidence is rejected.

The ledger retains late historical forecasts but excludes them from pre-release scoring. A first recorded actual is not certified as the first official print. Even a forecast received before its declared schedule is excluded if an imported actual says publication preceded the forecast receipt. Publisher schedules and source contents remain unverified assertions. Multiple forecasts per named source/basis are resolved to the latest eligible capture. Raw surprise units are preserved; incompatible periods/units/bases form separate events.

Actuals and revisions generate account/fund review inbox events with source and explicitly analyst-linked symbols. Historical receipt cutoffs are available through the API. Storage is bounded to 10,000 entries / 25 MB per account/fund and 16 KB per entry; display is limited to the latest 2,000 entries, visibly flagged. This does not provide complete historical economist consensus or an intraday causal market-reaction study.

## Official financial conditions

The Federal Reserve's baseline three-year-lookback FCI-G CSV is parsed against an explicit schema. Every row must have finite values, a unique date, and component totals that reconcile within 1e-7. The UI shows the level, observation date/age, component contributions, month-to-month component changes, original source and retrieval time. Publication time remains unknown. Positive is a modeled GDP-growth headwind; negative is a tailwind.

The existing cache/single-flight/stale-response infrastructure is reused, including persisted last observations. Saved/stale responses keep their retrieval time and stale flags. This is the Fed's revised published history, not Goldman or Bloomberg FCI and not a standalone GDP forecast. The inspected official file contained 441 rows through September 2026; all components reconciled.

## Model specification and uncertainty

Known model parameters now require finite values, bounded ranges and whole-number windows. The live Black–Litterman convention is preserved: when view variance scales with tau, tau cancels from posterior expected returns. The existing tau control is disabled and described accordingly. The uncertainty audit can compare that convention with explicitly supplied independent monthly view-error variances; such supplied variances are not certified as empirically estimated.

Posterior calculations use linear solves. Covariance symmetry/positive definiteness and variance domains are checked. No automatic switch to independent view uncertainty, joint regimes or a new allocation strategy occurs.

The audit also corrected initial-loss drawdown accounting and strategic rebalancing costs: initial losses count relative to starting wealth, and strategic turnover compares target weights with drifted holdings. Model version 1.4 invalidates stale saved-model quality claims while background refresh proceeds.

## Registered US challengers

The laboratory extends the existing bounded US ALFRED comparison, up to 24 target months per run. Economic, excess-return momentum and combined sleeves use the same supported assets, observations, volatility ceiling, gross cap and one-way turnover costs. Exposure coefficients, lookbacks and classifier regularization are fixed and returned with results. Return momentum is based on existing total-return proxy excess histories, not a pure spot-price series.

Research sleeves may take negative weights, with gross capped at one and risk scaled down to the existing volatility ceiling. This is a research calculation, not an order engine. Missing held returns, unsupported exposure classes, insufficient features or exhausted portfolio equity withhold sleeve performance rather than substitute zero returns. Correlations require at least 12 common observations; a combined sleeve is not an independent strategy.

A regularized multinomial classifier is compared with the current independent growth/inflation probabilities on paired scored months. It requires 84 matured training observations, at least eight per class and complete current features. Forecast-coverage and target-label-coverage gaps are separate diagnostics. Labels are final evaluation-vintage factor directions, not immutable GDP/CPI outcomes. Historical label scoring is separated from the ability to construct the final allocation, so an unavailable final allocation does not discard otherwise supported historical outcomes.

The experiment specification/code hash is saved before computation in versioned account/fund storage. Failure/completion/unavailability is appended as a later version. Completed attempts also enter the existing account-wide quant registry. This records current attempts, not earlier unregistered searches, and does not make a repeatedly viewed interval an untouched holdout.

Limitations: current asset/cash/FX histories are not completely point-in-time archived; timing alignment differs from the old approximate-lag comparison. Drift uses the baseline excess-return convention. Costs do not include full futures rolls, shorts' borrow, financing or terminal liquidation. Requested versus scored target months and missing months are exposed. These limits prevent production-performance or institutional-replication claims.

## GDP bridge, strategic assumptions and view journal

The bridge accepts dated feature/outcome observations for one declared target and unit. Fixed ridge regression (alpha 10) uses at least 20 already released training targets, training-only scaling and mean imputation, and sufficient current feature coverage. Late features, already-known targets at forecast origin, duplicate target periods, nonfinite values and future supplied outcomes are rejected. Forecast errors are compared with the expanding training mean. It is a target-based challenger requiring sourced imports, not an automatically calibrated GDP nowcast or an unverified relabelling of the existing factor.

Strategic equity assumptions reconcile dividend reinvestment, per-share EPS growth, valuation change and compounding interactions. Buyback yield is not separately added to EPS growth. Bond assumptions use explicit annual carry/roll, duration/convexity and loss approximations. Nominal/real and FX/hedging effects are explicit. These are long-run assumptions, not next-month signals or complete multi-year bond repricing.

The scenario allocation tool compares a supplied baseline with constrained expected-case and worst-supplied-scenario portfolios. It uses explicit annual base-currency return assumptions, covariance, analyst scenario probabilities, risk aversion, turnover penalty, long-only weights, cash, asset caps and a volatility ceiling. Probabilities must sum to one; covariance must be positive definite. Solver failures are withheld without a fallback portfolio. The worst supplied scenario is not the worst possible future, and turnover penalties are not observed implementation costs. The horizon labels annualized assumptions, not a full multi-year simulation.

The view journal stores structural/cyclical/release/tactical views in existing versioned thesis storage, with baseline, invalidation, review date, source and optional override rationale. Writes use optimistic versions. Macro views have their own editor and are kept separate from the older security-thesis form.

## Validation

Regression tests cover release receipt cutoffs, retrospective imports, false schedules, revision chains, source/basis matching, owner/fund isolation, parameter domains, tau cancellation, independent view variance, official contribution reconciliation, model look-ahead, held-return coverage, turnover costs, initial drawdown, bridge feature/label timing and versioned views. UI tests cover explicit collection, read-only controls, guided inputs and unavailable results. Final suite counts and live comparison findings are recorded after verification.

Final affected backend suite: **107 passed**. Frontend unit/component suite: **542 passed across 63 files**, excluding the separate live-API integration suite. TypeScript and the production build passed; the build retains its existing large-chunk warning. A new regression verifies that supported historical classifier outcomes remain scorable when the final allocation itself is unavailable. All account/fund writes in tests use temporary databases.

A subsequent focused run passed 21 backend checks, including return-input fingerprint changes and empty-source handling, and seven UI checks after input pagination. Backend/frontend startup checks returned HTTP 200; anonymous access to the macro ledger returned HTTP 401. This confirms service availability and the authentication boundary, not a completed visual inspection of authenticated screens.

The public-source/cache exercise requested February 2024–January 2026 target months. It produced 22 common scored months; November and December 2025 were unscored. Economic-only excess-return proxy Sharpe was -0.33, return momentum 0.96, combined 0.95. These mixed results are retained; no parameter search was performed to improve them. After decoupling historical scoring from final allocation construction, 20 paired regime forecasts were scorable: independent multiclass Brier 0.7000 / log loss 1.2743; joint 0.6504 / 1.2036. Two joint forecasts lacked final target labels. This short, repeatedly inspected sample does not justify a production model switch or establish alpha. Source/cache paths were exercised; a fresh upstream fetch was not independently certified for every series.

See [the expanded firm research](/Users/daltonyuen/Math_Model/macro_research_platform/docs/quant_macro_firms_research_2026-11-03.md) for what can and cannot be inferred from Citadel, Millennium, Renaissance and other firms' public descriptions. Empirically calibrated scenario/uncertainty estimates, broader international data, complete consensus history and production promotion of candidate models remain further work.
