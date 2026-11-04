# Macro model and data improvements — 31 October 2026

The program is running at http://127.0.0.1:5173 with API http://127.0.0.1:8000. The US, euro-area and rest-of-world views were computed using the configured data loaders and served as model version 1.2. All three produce current monthly decisions and complete historical backtests after correcting the gold proxy. Saved audit output: `data/processed/macro_audit_2026-10-31.json`.

## Findings and changes

1. **Missing monthly prices and cash rates.** Price histories now use a complete monthly calendar and explicit `pct_change(fill_method=None)`. A missing month is not interpreted as a flat month, and a multi-month price change is not labelled a one-month return. The cash-rate carry is bounded at two missing months rather than extended indefinitely.
2. **Historical information sets.** Stale input exclusion applies independently at each decision date, including every walk-forward iteration and the US model. It is not selected once using today's final data endpoint and then applied retrospectively. Transformed series are clipped to the decision cutoff. Reported input membership reflects actual factor loadings, not just initial eligibility.
3. **Factors and targets.** Nonpositive log-growth inputs, nonfinite observations and zero-variance columns are excluded from the relevant calculations. Calendar-month direction changes preserve gaps; missing target endpoints remain unknown. Growth/inflation factors must be synchronized to the decision month before an allocation is generated. If the normal sign anchor is unavailable, orientation is deterministic and explicitly flagged.
4. **Honest performance evaluation.** A historical held-asset return gap makes the backtest unscorable with the affected month/assets identified. It is not filled with zero. Brier scoring ignores missing realized targets and reports the number scored. Target labels are still based on ex-post revised factor histories; this is explicitly identified as a limitation.
5. **Gold proxy corrected.** The audit found missing February/March/November 2015 observations in the shared generic gold-futures price history. Gold estimation now uses GLD adjusted closes, consistent with the US sleeve's actual instrument and available history from 2004 onward. The history is not extended backward using invented returns. This also avoids presenting generic futures quote changes as a collateralized, rolled total-return investment. Cache namespaces were changed so legacy futures history cannot silently masquerade as the new proxy. Non-US price-cache keys include the requested ticker set.
6. **Useful model explanation.** A new data-readiness panel shows the decision/target months, actual input coverage, excluded/ragged inputs and the strongest growth/inflation factor associations. Loadings are described as associations, not causal contributions or forecast GDP/CPI numbers. The input table separates the latest raw observation from the transformed availability month used at the decision cutoff. Unavailable backtests show their reason and affected assets.
7. **Loading and freshness.** Current-version disk runs within the existing six-hour TTL are promoted into memory without another cold fit. Older-version runs are labelled while refreshing. Background refresh errors are captured and shown, with a retry cooldown. Snapshot views poll for their replacement; economy-switch and rerun responses are protected against stale initial-load responses overwriting a newer view.

## Actual run

| Economy | Decision base | Inputs used | Assets used | Backtest period | Scored return months | Latest-data status |
|---|---|---:|---:|---|---:|---|
| US | September 2026 | 17 / 17 | 10 / 10 | February 1995 – September 2026 | 380 | Availability checks clear |
| Euro area | September 2026 | 16 / 16 | 8 / 8 | January 2004 – September 2026 | 273 | Availability checks clear |
| Rest of world | September 2026 | 26 / 26 | 8 / 8 | June 2004 – September 2026 | 268 | Review: one inflation input absent at the latest factor month |

The model's target allocation month is October 2026. The policy intentionally uses completed-month returns. In the rest-of-world inflation block, 10 of 11 used series have an observation in the latest factor month; the other contributes its standardized mean under the existing PCA missing-value method. That is now disclosed rather than treated as a new observation.

The API world-summary check returned HTTP 200 with all three version-1.2 results, no refreshing-snapshot flag, in approximately 42 ms on this local check. This is a single cached response measurement, not a general performance benchmark.

## Validation

- 41 backend tests passed across macro models, data-quality checks, global macro, model migration and regime transitions.
- 427 frontend tests across 46 files passed.
- TypeScript passed and the final production build passed. Existing large-chunk and Pydantic deprecation warnings remain.
- Python compilation and `git diff --check` passed.
- Reproduction: `../.venv/bin/python scripts/audit_macro_models.py` from the platform directory. The runner computes research views and records readiness results.

## Limits and next data priorities

An early command-line initialization warning reported a missing FRED key, but the running API explicitly confirms that a key is configured. That warning alone is not reliable evidence of a source outage or cached-data use. A completed calculation is likewise not evidence that every upstream source was freshly retrieved: loaders may serve saved observations, and source-fetch provenance is not yet uniform across all providers. Coverage dates and the decision cutoff are shown.

Publication timing still uses approximate monthly lags. Historical observations are revised; this pass does not implement ALFRED point-in-time vintages. Consequently, backtests and regime-probability scores are research diagnostics, not proof of executable real-time investment accuracy. The euro-area equity proxy remains DAX-based and government bond histories remain synthetic constant-maturity estimates, as disclosed in the existing economy configurations. The rest-of-world factor is a pooled nine-economy cycle, not an individual-country forecast.

The next high-value data work is uniform retrieval/cache provenance and revision tracking, verified release timestamps and vintage-aware validation. New predictive algorithms should be judged against those controls rather than selected for better historical Sharpe ratios.

## Primary sources used

- [FRED real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html) and [ALFRED](https://fred.stlouisfed.org/docs/api/fred/alfred.html): current/revised observations and historical vintages are different information sets.
- [SPDR Gold Shares](https://www.spdrgoldshares.com/usa/gld/): the instrument tracks gold bullion less trust expenses, supporting its use as the investment proxy for the existing US sleeve.
- [J.P. Morgan commodity-index methodology](https://www.jpmorgan.com/content/dam/jpm/global/disclosures/us/jpmcci_qa.pdf): futures total returns include price, roll and collateral components; generic futures quotes are not a substitute for the full return process.
- [pandas percentage-change documentation](https://pandas.pydata.org/pandas-docs/version/2.0/reference/api/pandas.Series.pct_change.html): explicit missing-value handling avoids dependence on implicit fill conventions.
