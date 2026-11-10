# Institutional macro research and implementation proposals

Researched 3 November 2026. Scope: public first-party material from Bloomberg, Bridgewater, Goldman Sachs, AQR, BlackRock, PIMCO and J.P. Morgan Asset Management, compared with the current program. These sources describe public frameworks or advertised capabilities, not complete internal production models. Proposed designs below are our engineering judgments, not statements that these firms use those exact designs. No runtime calculations, allocations or subscriptions were changed.

## Main conclusion

Retain the existing model as a transparent baseline. Build a comparison framework around economic expectations, financial transmission, distinct forecast horizons and independently tested alternative models. Famous branding is not evidence that a copied signal will work with our data, universe or costs.

The current core has two principal-component factors, logistic direction forecasts, independent growth/inflation quadrant probabilities, shrunk conditional asset returns, Black–Litterman views and constrained allocation. The recent release added a bounded US vintage comparison and probability diagnostics. It did not turn the live model into a fully vintage-correct GDP nowcast or replicate an institutional firm's process.

## What the firms publish, and what we should build

### Bloomberg: connect the whole economic-release workflow

Bloomberg advertises contributor forecasts and consensus, report-component analysis, release surprises, market reactions, policy probabilities and interactive economics tools. Its distinctive lesson for this program is the connection between evidence and decisions, rather than another indicator screen. [Bloomberg Economics](https://professional.bloomberg.com/products/bloomberg-terminal/research/economics/).

**Proposal:** extend the existing calendar/surprise tools into a release workspace: forecast cutoff and contributors → first actual → revisions and components → change in our forecast → observed market response. Show fiscal/reference period, units, seasonal adjustment and transformation. Store the consensus snapshot before release; a later import must not become a supposedly contemporaneous expectation.

Use precisely timestamped returns for event windows only where observations support them. Separate immediate reaction, later drift and other overlapping announcements. Daily closes cannot establish an intraday announcement effect. Historical contributor-level consensus and low-latency feeds need appropriate entitlements; no freely sourced substitute should be labelled Bloomberg consensus.

### Bridgewater: unexpected growth/inflation and environmental risk

Bridgewater's All Weather account emphasizes economic conditions relative to expectations and balanced risk across environments. This is a strategic diversification framework, not an instruction to make every asset bet from a predicted quadrant. [The All Weather Story](https://www.bridgewater.com/research-and-insights/the-all-weather-story).

**Proposal:** retain our existing direction quadrant and add a separate expectations view. Examples: growth slowing but exceeding prior expectations; inflation falling but less than anticipated. Estimate exposure to documented macro innovations rather than assuming asset-class names give exact economic sensitivities. Report cash return, systematic market exposure and tactical excess return separately.

The existing environment prior uses class mappings and inverse volatility. It is a useful approximation, not Bridgewater's portfolio or verified neutrality to growth/inflation surprises. Test exposure balance, stock–bond correlation instability and concentration under several covariance windows. Expectations, surprises and factor direction must remain separately labelled.

### Goldman Sachs: financial conditions as a growth-transmission mechanism

Goldman's public methodology appendix describes G10 financial-condition inputs including rates, credit spreads, equities and exchange rates; weights reflect modeled effects on growth over a one-year horizon. Euro-area coverage also accounts for sovereign spreads. [Public research appendix, page 22](https://www.goldmansachs.com/pdfs/insights/goldman-sachs-research/americas-first/report.pdf).

**Proposal:** extend financial conditions from a displayed level to an explanation of changes and lagged headwinds/tailwinds. Reconcile contributions from rates, mortgage financing, credit, equities, housing and FX, as supported by each methodology. Keep model output units explicit: an index standard deviation is not a percentage-point GDP contribution.

The Federal Reserve publishes FCI-G data, definitions and code, making it a stronger initial reproducible benchmark than guessing Goldman's coefficients. FCI-G explicitly models lagged growth effects and is not the Goldman index. [Federal Reserve FCI-G methodology](https://www.federalreserve.gov/econres/notes/feds-notes/a-new-index-to-measure-us-financial-conditions-20230630.html).

Use NFCI/ANFCI and FCI-G as separate views with their own sign conventions. The program already displays NFCI; adding another copy of it would not close the gap. Evaluate incremental forecast information after controlling for existing growth/inflation features and avoid double-counting the same rates/spreads in several composite scores.

### AQR: test economic momentum alongside price momentum

AQR's Economic Trend research studies positioning from changes in macro fundamentals and its combination with price trend. Its published strategy results are hypothetical research, not expected results for our program. [Economic Trend](https://www.aqr.com/Insights/Research/White-Papers/Economic-Trend).

**Proposal:** build an economic-momentum research sleeve using independently timestamped growth, inflation, policy and external-demand signals. Compare price-only, economic-only and combined sleeves at the same risk budget and after the same costs. Test directional and cross-country relative signals separately. Mapping economic news into bond/FX/equity positions needs explicit economic hypotheses, not a universal positive sign.

The first implementation should be simple, with frozen horizons and standardized inputs estimated on training history. Do not choose lookbacks from the final evaluation period. Record all searches in the existing experiment registry. Free ETF histories are not identical to institutional futures/forward returns; account for roll, financing, hedging and instrument availability before interpreting a replication.

### BlackRock: make scenario uncertainty part of allocation

BlackRock's public capital-market-assumption material describes scenario-dependent return paths and uncertainty-aware portfolio construction. It also distinguishes currency/hedging bases. [BlackRock capital market assumptions](https://www.blackrock.com/us/financial-professionals/insights/capital-market-assumptions).

**Proposal:** maintain named scenarios with macro paths, input assumptions, horizon, revision date and evidence. Compare the current model allocation with allocations robust to plausible return/covariance estimates. Display what would change if a scenario weight or assumption changes. Analyst probabilities and estimated model probabilities are different objects; neither should be presented as empirically calibrated without evaluation.

Use a small scenario set first: demand slowdown, supply-driven inflation, productivity-led expansion and financing stress. Ensure GDP, inflation, rates and earnings paths are mutually intelligible, while acknowledging that deterministic shocks are not a structural causal model. Connect these scenarios to the existing position-level stress engine and avoid counting factor shocks and derived asset shocks twice.

### PIMCO: separate the structural view from cyclical decisions

PIMCO describes an annual secular forum, three cyclical forums, an investment committee translating macro views into risk targets, bottom-up research and bias-challenging practices. This is a documented investment process, not a disclosed forecasting equation. [PIMCO investment process](https://www.pimco.com/us/en/about-us/our-process).

**Proposal:** introduce a view hierarchy: structural assumptions; cyclical forecasts; scheduled-release expectations; tactical implementation. Each view should have an owner, horizon, evidence, review date and invalidation conditions. An analyst override should be saved alongside the original quantitative forecast with a rationale, so subsequent outcomes can assess whether judgment helped.

The existing thesis records and review inbox can support this without new parallel storage. Evaluate forecasts at their stated horizon. A weak payroll report should not silently rewrite a long-run productivity assumption, and a secular growth view should not mechanically create a short-term trade.

### J.P. Morgan Asset Management: transparent long-run return building blocks

J.P. Morgan's long-term assumptions distinguish strategic estimates over 10–15 years from short-term allocation signals and publish supporting methodology. [Long-Term Capital Market Assumptions](https://am.jpmorgan.com/us/en/asset-management/liq/insights/portfolio-insights/ltcma/), [methodology handbook](https://am.jpmorgan.com/content/dam/jpm-am-aem/global/en/insights/portfolio-insights/ltcma/noindex/ltcma-methodology-handbook.pdf).

**Proposal:** add an independent strategic-return layer: equity income, per-share earnings growth and valuation change; bond carry, roll, yield movement and losses; explicit FX/hedging assumptions. Document reinvestment, inflation and horizon conventions. Keep arithmetic/geometric return differences and nominal/real returns visible. Avoid double-counting buybacks in both earnings-per-share growth and a separate yield component.

Use this as a reasonableness anchor beside the current regime-conditional return estimates, not a replacement for a next-month forecast. Show the contribution of each assumption and how the strategic view changes across currencies. Importing public assumptions does not establish rights to redistribute proprietary downloadable matrices.

## Important findings in our own model

### 1. Direction is not an economic surprise

`api/model/core.py:direction_probability` predicts the sign of a factor's recent change. It does not predict a release relative to a saved consensus. `api/marketdata/econ.py` already distinguishes trend-based surprise proxies from prospectively collected consensus. The proposed expectation layer must preserve that distinction; renaming current quadrants would misrepresent the calculation.

### 2. Growth/inflation independence needs an explicit challenger

`quadrant_probabilities` multiplies separate marginal probabilities. The assumption is disclosed, but it can misstate joint tail scenarios. Compare it with a regularized multinomial or another simple joint-probability model using the same vintage-selected sample. Evaluate multiclass log loss/Brier scores, calibration and rare-state counts. Retain independence if alternatives do not demonstrate stable out-of-sample gains. This is our proposed test, not a claim about any firm's hidden classifier.

### 3. The tau control cancels out of current posterior mean calculations

In `black_litterman`, the prior covariance is tau × Sigma and view uncertainty is diag(tau × Sigma) divided by confidence. Both precision terms scale by 1/tau, so tau cancels from the posterior expected-return vector when other settings are fixed. A read-only two-asset check with tau 0.01 versus 0.20 produced identical posterior means, with maximum difference 0.0.

This is a mathematical consequence of the chosen convention, not automatically an invalid Black–Litterman model. However, the UI should not imply this control independently changes mean-based allocations. Either explain/remove the redundant control for this convention, or estimate view-error uncertainty independently using training-only forecast errors. Posterior/model uncertainty also needs a deliberate treatment in portfolio risk; a parameter slider alone does not provide it.

### 4. Missing-data handling and forecast targets need development

`diffusion_factor` replaces missing standardized observations with zero after a coverage threshold. It is transparent but does not model differing release frequencies or stale information explicitly. Test a bridge-regression nowcast first, followed by a state-space/dynamic-factor challenger where justified. Define a real target such as quarterly GDP growth separately from the current standardized growth factor. Public nowcasts offer useful benchmarks: the [New York Fed Staff Nowcast](https://www.newyorkfed.org/research/policy/nowcast/) tracks GDP and the effect of new information.

### 5. Current research coverage does not establish production accuracy

The bounded US vintage tool is a useful foundation, not complete real-time historical investment validation. Asset/cash/FX histories, changing universes, forecast target definitions and calibration windows still matter. The earlier two-month source exercise established operation only. Model acceptance needs substantially longer, historically valid evaluation across expansion, contraction, inflation and disinflation periods.

## Proposed implementation sequence and acceptance

| Work package | Extend | Minimum acceptance |
|---|---|---|
| M1: Forecast/expectation ledger | Existing calendar, captures, inbox | Pre-release forecasts are frozen by information time; period/units match first actuals; revisions remain separate. |
| M2: Model specification audit | Core, parameter UI, tests | Explain tau cancellation; verify monthly/annual units and neutral cases; prevent unsupported confidence claims. |
| M3: Conditions and growth impulse | Existing NFCI/liquidity screens | Official FCI-G adapter with source/revision dates; contributions reconcile under its published method; signs and units remain explicit. |
| M4: Economic-trend challenger | Quant registry, vintage panel | Locked specification; price/economic/combined comparisons share dates, costs and risk; all searches recorded. |
| M5: Joint regimes and target nowcasts | Core, calibration, backtest | Compare with independence/simple baselines on rolling unseen samples; report forecast errors and missing coverage. |
| M6: Strategic/scenario allocation | Current Black–Litterman and stress tools | Separate horizons and return building blocks; position effects reconcile; uncertainty/currency bases remain inspectable. |
| M7: Institutional-style release desk | Existing research/markets UI | One workflow links source → expectation → actual/revision → forecast change → portfolio exposure, without causal market-impact claims. |

M1–M3 should come first. Then test M4/M5 before allowing them to influence allocation; M6/M7 connect the results to decisions. Evaluation should include forecast error/log scores, calibration, turnover, net costs, concentration and parameter stability. Model complexity should earn its place against simpler alternatives.

## What not to claim or prioritize

- No exact replication of Bloomberg, Bridgewater, Goldman or other proprietary engines from public marketing/research summaries.
- No manufactured historical economist consensus or intraday announcement reactions from daily prices.
- No adoption of a firm's current macro outlook as a permanent parameter setting.
- No assumption that more indicators, larger neural networks or a famous firm's name make outputs more accurate.
- No change in live portfolio allocations from this research review.
