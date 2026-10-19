# Options strategy research — framework, data, and measured results (October 2026)

Quant Lab → **Options research**. Code: `api/quant/optresearch/` (pricing, vol, market, strategies, simulate, portfolio,
regimes, validate, analytics, registry, deploy, runner, selfcheck); API: `api/routers/optresearch.py`; dashboard:
`frontend/src/components/sections/model/quant/OptionsResearch.tsx`; tests: `api/tests/test_optresearch.py`;
command line: `scripts/run_options_research.py --stage N`. Research only — nothing here places orders.

## 1. What the data allow (and what they do not)

| Data | Status | Source |
|---|---|---|
| Underlying prices, dividends, splits | observed | Yahoo daily (adjusted for returns; traded share price for strikes) |
| Point-in-time S&P 500 membership | observed | change-date snapshots since 1996; 145 removed members with price history are in the panel, 161 without are listed as missing |
| At-the-money implied volatility | **observed for 16 underlyings** since 2009–2011 (SPY's full VIX term structure; QQQ, IWM, DIA, AAPL, AMZN, GOOGL, GS, IBM, EEM, EWZ, FXI, SLV, GLD, USO, TLT) | CBOE volatility indices |
| Strategy benchmarks | observed | CBOE PUT, CNDR, BFLY, BXM, BXMD, PPUT, CLL, WPUT, CMBO (daily history from cdn.cboe.com) |
| **Historical option quotes** (bid/ask, IV by strike, volume, open interest), listed strikes and expiries | **not available free** | — |
| Earnings dates (for the IV term structure) | not used | — |

Consequently every option result is a **model-based simulation** and is labelled with its class:
`model_observed_iv` (observed ATM IV, modelled smile, term structure and quotes) or `model_iv` (modelled IV — single
stocks without a CBOE index). No modelled price is presented as an observed one.

## 2. How good is the option model? (measured against observed CBOE indices)

The same rules as CBOE's indices were priced on SPY with the observed VIX term structure, at mid prices, and compared
month by month with CBOE's published series (excess returns over T-bills). Calibrated on 2011–2017 only:

* **ATM scale**: the VIX → at-the-money mapping was set to 0.84 × VIX (from the PutWrite index; the earlier default of
  0.92 overpriced puts). PutWrite out of sample (2018–2026): model +6.3% vs CBOE +6.2% excess a year, correlation 0.98,
  tracking error 2.6% — before calibration the model overstated it by **2.2% a year**.
* **Out-of-the-money options remain too rich in the model.** Iron condor (CNDR) out of sample: model +1.1% vs CBOE −1.3%
  excess a year (correlation 0.75) — an overstatement of about **2.3% a year of index notional** that no smile slope in
  the grid removed. Credit strategies (bull put, iron condor) are therefore likely to look better here than they were.
  Every strategy must also survive with all implied volatilities 10% lower (survival test added after this finding and
  before any stage-3/4 run).
* **Single-stock IV model** (log IV on blended realised vol, VIX and S&P realised vol, fitted ≤ 2018 on the observed-IV
  names): out-of-sample mean absolute error **3.4 vol points**, bias −0.05, median correlation 0.89. Hypothesis H14
  (error < 3 points) is **rejected**: stock-level option results carry more model risk than index results.

## 3. Execution, accounting, validation (all pre-declared)

Fills at the natural price per leg (buy at the ask, sell at the bid) with a modelled half-spread by liquidity tier,
widened when VIX > 20; $0.65 + $0.02 per contract per leg; American early assignment (short calls before ex-dividend,
deep in-the-money short puts) and physical exercise at expiry with a stock-closing cost; defined-risk margin (maximum
loss). One account per system, marked to the model mid, cash at the T-bill rate; NAV reconciles to trade P&L plus
interest to the cent (stage 1).

Segments: development 2016–2021 (searched), validation 2022–2023, holdout 2024 → (sealed; every reveal logged).
Survival: Sharpe > 0 on validation and on a walk-forward over the pre-declared structure grid (2018–2023); 5th
percentile of a block bootstrap of walk-forward excess returns > 0; positive at 1.5× option spreads; positive excess
return with implied vols 10% lower; deflated Sharpe ≥ 0.90 for every configuration tried (including earlier
experiments); PBO < 0.5.

## 4. Results

### Stage 1 — correctness (synthetic)
10/10 checks pass: textbook BSM (10.4506 / 5.5735) and parity, Greeks vs finite differences, 25-delta strike, bounded
payoffs, NAV reconciliation, **a fair-value market (IV = realised vol) shows no edge** (expectancy ≈ −costs), exits
after entry, no look-ahead (prefix invariance), wider spreads lower P&L.

### Stage 2 — SPY, QQQ, IWM, DIA (observed IV; 97 s, 0.9 GB)
No strategy survived. All four looked attractive in development (Sharpe 1.2–1.6 for the credit spreads and bull call
spreads) and failed in 2022–2023 (Sharpe −0.74 to −0.07). A first shakedown run before the CBOE calibration (and with the
bootstrap on raw instead of excess returns) showed the iron condor "surviving"; it is marked **superseded** and is not a
result.

### Stage 3 — 17 ETFs + the 100 most liquid point-in-time S&P 500 members (667 s, 3.5 GB)

| System | Development CAGR / Sharpe | Validation CAGR / Sharpe / max DD |
|---|---|---|
| Existing options algorithm (recorded, different engine) | — | +3.1% / 0.04 / −15.2% |
| SPY buy-and-hold | — | +1.6% / −0.00 / −24.5% |
| Bull put credit spreads | +11.2% / 1.10 | −1.3% / −0.44 / −16.1% |
| Bull call debit spreads | +9.8% / 0.56 | −9.6% / −1.38 / −21.9% |
| Bear put debit spreads | −2.7% / −0.32 | +0.0% / −0.80 / −9.8% |
| Short iron condors | +3.3% / 0.52 | +6.4% / 0.57 / −4.6% |
| Combined four (equal risk budgets) | +3.8% / 0.24 | −7.1% / −1.27 / −15.2% |
| Regime-switching (random forest, chosen on development) | +8.6% / 0.90 | −2.3% / −0.65 / −16.8% |

No strategy survived: the iron condor was positive in validation but failed the walk-forward (Sharpe −1.53), the
implied-vol stress and the deflated Sharpe. Survivorship (point-in-time vs today's list) moved Sharpe by −0.10 to
+0.01. Regime classifiers' out-of-sample balanced accuracy was 0.27–0.36 (chance 0.33; always predicting the majority
class 0.39); the model chosen on development Sharpe lost in validation. Portfolio construction: every variant lost in
2022–2023; ranking beat random order (−1.27 vs −2.19 validation Sharpe); the vega cap never bound.

### Stage 4 — full point-in-time universe (870 underlyings, 63 min, 4.8 GB peak, 577 configurations)

Every point-in-time S&P 500 member with free price history (including later-removed names) plus 18 optionable ETFs;
a stock is eligible only while it is an index member. 92–98% of the chosen strategies' trades used **modelled** IV.

| System | Development (2016–21) CAGR / Sharpe | Validation (2022–23) CAGR / Sharpe / max DD |
|---|---|---|
| Existing options algorithm (recorded; different engine) | +14.9% / 0.97 | +3.1% / 0.04 / −15.2% |
| Its options sleeve only (recorded) | +1.9% / 0.68 | +3.6% / −0.01 / −1.0% |
| SPY buy-and-hold | +17.3% / 0.92 | +1.6% / −0.00 / −24.5% |
| Bull put credit spreads | +4.3% / 0.44 | +1.1% / −0.24 / −9.1% |
| Bull call debit spreads | +12.8% / 0.72 | −6.1% / −0.68 / −20.3% |
| Bear put debit spreads | −1.9% / −0.33 | −1.0% / −0.15 / −28.1% |
| Short iron condors | +2.4% / 0.24 | +3.1% / −0.03 / −8.3% |
| Combined four (equal risk budgets) | +1.8% / 0.13 | −3.9% / −1.15 / −14.1% |
| Regime-switching (logistic, chosen on development) | +2.1% / 0.18 | +3.2% / −0.04 / −5.8% |

**No strategy survived validation.** Walk-forward Sharpe (2018–2023): bull put −1.36, bull call −0.70, bear put
−0.94, iron condor −1.60; deflated Sharpe ≈ 0 for all four after 577 + earlier configurations.

What the run shows:
* **Costs dominate the premium strategies.** Modelled option spreads and fees took 68% (bull put) and 86% (iron condor)
  of gross P&L — single-stock option bid/ask is the binding constraint, and it is modelled, not observed.
* **Index vs single-stock premia (H02, inconclusive).** Iron condors on observed-IV ETFs: 27 trades, mean R +0.13
  (t = 3.1); on modelled-IV stocks: 458 trades, mean R +0.005. Bull puts: +0.047 vs +0.019. Consistent with the
  earlier research, but stock IV is modelled, so this cannot confirm a stock-level premium.
* **Bull call spreads on momentum leaders** earned mean R +0.15 (t = 3.1, 316 trades, development and validation
  together) yet lost in validation (−0.68 Sharpe): the edge in development did not persist through 2022.
* **Regime models:** out-of-sample balanced accuracy 0.26–0.36 (chance 0.33). Logistic regression was chosen on
  development; its gating beat the fixed combination in both segments (H08 inconclusive), but the gated portfolio
  still lost money in validation. No machine-learning model is promoted.
* **Portfolio construction:** of 25 variants of the combined portfolio, one had a positive validation Sharpe
  (inverse-volatility strategy budgets, +0.42) — one of 25, so not evidence on its own. Ranking candidates beat random
  order in both segments (H15 inconclusive); delta caps reduced drawdown (H12 inconclusive); position counts showed no
  consistent optimum (H11 rejected).
* **Survivorship:** point-in-time membership vs today's list changed Sharpe by −0.32 to +0.19 — material, in both
  directions.

Registry after stage 4: rejected H01, H03, H04, H05, H07, H10, H11, H14; inconclusive H02, H06, H08, H09, H12, H13, H15;
**none survived**. (Relative hypotheses were first labelled by a single validation comparison; after the run that rule
was tightened to require agreement in development and validation — and "survived" is not assigned without a
significance test. The result file records this.)

**Recommendation:** nothing from this research should be promoted to the Quant Algorithm. The next step that could
change the conclusion is real historical option quotes (single-stock bid/ask especially) — the binding cost — followed by
a re-run of stage 4 on observed prices.

## 5. Registry and hand-off

Fifteen hypotheses (H01–H15) seeded from the earlier research notes are tracked in the registry with method, data,
configuration, results and limitations; "survived" requires stage 4. Configurations are exported as versioned JSON
candidates (`config/quant_algo/candidates/`), promoted only by an administrator typing `APPROVE <strategy>-v<N>` (and
acknowledging any failed test or missing stage-4 validation), immutable once approved, with rollback to the previous
approved version. The Quant Algorithm reads `GET /api/v1/quant/options-research/configs/production`. Nothing has been
approved.

## 6. Backtest performance (the 10-year, ~3,100-stock global Code Lab run)

Measured, not estimated. Profile of `quant_lab_global_research.py` (GLOBAL universe, 6-set walk-forward, research
checks; `scripts/profile_global_backtest.py`): **786 s, 5.9 GB peak** — data load 261 s, one strategy() call 36 s
(× 6 in the walk-forward), the ledger 14 backtests × ~16 s, research checks 80 s.

Like-for-like A/B (same machine, warm caches, no profiler, alternating runs; `scripts/ab_load_data.py`,
`scripts/ab_backtest.py`):

| What | Before | After | Check |
|---|---|---|---|
| Data load, 3,110 × 5,807 | 182 / 178 s, 7.1 GB | 78 / 82 s, 6.3 GB (**2.2×**) | identical frames and provenance |
| One ledger backtest, 4,669 × 3,110 | 22.1 / 21.8 s | 19.7 / 20.7 s (unchanged) | identical returns (≤ 1e-12) |
| Your strategy() call (`_fast` copy in the notes folder) | 15.8–19.2 s | 9.9–13.8 s (**1.5×**) | identical weights (max |Δ| 0) |

How: the loader assembles arrays positionally (one index lookup per symbol instead of per-field pandas alignment),
reads the 6,000 Parquet caches in parallel, converts FX once per currency and masks listing ends in one vectorised
step. The research panel for options is built once per data day and cached (`data/processed/quant/research/panel`),
so stages and experiments never re-read per-symbol files; option paths are simulated once per structure and every exit
rule is evaluated on the stored paths; runs execute in their own process with progress, checkpoints per strategy,
runtime and peak memory recorded.

The second whole-pipeline profile (705 s) was taken on another day when unchanged functions ran ~1.5× slower, so it is
not a clean before/after — the A/B rows are. Not done: removing the six fresh-start backtests the walk-forward grid
table re-runs (≈ 6 × 20 s) would change how that table defines each parameter set's statistics — a decision for you.
