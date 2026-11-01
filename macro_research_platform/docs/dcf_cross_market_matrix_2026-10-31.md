# Cross-market, cross-sector DCF audit — 31 October 2026

This audit checks the existing valuation engines using public-provider observations. It is a mechanical and data-readiness audit, not an accuracy backtest or an endorsement of the resulting investment values. US or European securities are not assigned a blanket valuation haircut.

## Scope and selection

Every one of the platform's 50 configured markets and all 11 equity sectors has an explicit coverage cell: 550 combinations. Discovery identifies sector membership using the public screener but selects primary listings already present in the platform universe, avoiding foreign cross-listings used to fill otherwise empty cells. It targets at least two distinct issuers per supported cell and adds missing small/mid/large company size bands. Identical normalized issuer names do not count as separate companies. The saved universe is concentrated in larger companies; empty cells are coverage gaps, not proof that a country's economy lacks a sector.

The combined manifest includes 760 companies: the current matrix selection and additional issuers from the prior audit. Fresh snapshots and replays of earlier snapshots have separate provenance and capture dates. Prior input records are not overwritten or represented as fresh observations. Provider cooldowns, statement-currency conflicts and model limitations are reported separately from calculation failures.

## Checks

- All models: finite comparable per-share values, model suitability, source/period readiness and terminal dependence.
- FCFF: discounted cash flows plus terminal value reconcile to enterprise value; the debt/cash/investments/minority-interest bridge reconciles to floored equity value; equity divided by shares reconciles to reporting-currency value.
- FCFF: a hypothetical 10-for-1 split preserves total equity value and scales per-share value consistently, including differing quote/reporting units.
- FCFF: the central operating scenario reproduces the selected case, preserving first-year consensus growth and cyclical margin fade; a zero parallel rate shock reproduces the original value.
- FCFF: positive rate shocks reduce value when all underlying operating and terminal cash flows are nonnegative. Negative-cash-flow cases are not forced to satisfy this condition.
- Reverse growth and margin are alternative single-driver explanations, not jointly necessary targets. Unbracketed solutions remain unavailable.

Banks and insurers use excess-return valuation. REITs and utilities use the existing dividend-model suitability rule with the existing FCFF fallback where a dividend model cannot be built. The audit does not force an operating DCF onto every sector.

## Improvements from the audit

1. Unconfigured cash-flow currencies now require explicit review of long-run nominal growth and inflation. A high current local yield is not an unqualified perpetual-growth forecast.
2. Missing pre-revenue operating data produces a suitable data/model explanation, rather than incorrectly identifying the company as an ETF or other non-equity instrument.
3. Government-yield persistence merges concurrent currency updates under a lock and writes atomically. A regression test checks that all concurrent updates survive and remain available when the source is unreachable.
4. The audit checkpoints observations, stops submitting work on provider cooldown, labels deferred work separately and supports explicit bounded retries. Country round-robin ordering spreads request budgets across markets. Request pacing is confined to the audit process.
5. Dividend-model readiness now blocks automatic valuation labels for unsupported default growth, unmatched dividend-currency rates, and uncovered payouts outside the REIT accounting exception. Manual growth assumptions remain distinguishable from automatic defaults.
6. Historical in-sample price comparisons in the methodology are labelled as diagnostics, not validation or a target for fitting assumptions.

The audit encountered statement-currency conflicts for VALE3.SA, PETR4.SA, EBO.NZ and 241560.KS; no automatic FX restatement is made without a verified statement bridge. CVH.BA's default perpetual-growth assumption failed the terminal discount-spread guard. TUB.BR and PAMPA.SN lacked the revenue/operating-profit inputs required for FCFF. The audit was corrected to preserve the application's non-lender financial/FCFF and dividend fallbacks; fallback results are recorded separately, with missing dividend history requiring review. These are blocked/review cases, not evidence that the companies have zero intrinsic value.

## Reproduction

From `macro_research_platform` using the project Python environment:

```sh
../.venv/bin/python scripts/audit_dcf_matrix.py --workers 2 --request-rate 2
../.venv/bin/python scripts/audit_dcf_matrix.py --offline --prior-snapshots data/processed/dcf_audit_2026-10-28/snapshots
../.venv/bin/python scripts/audit_dcf_matrix.py --retry-provider --workers 1 --request-rate 1 --prior-snapshots data/processed/dcf_audit_2026-10-28/snapshots
```

`--max-fetch N` bounds an individual retry. Successful captured observations are retained. The report is generated under `data/processed/dcf_matrix_2026-10-31/`: `manifest.json`, `summary.json`, company-level `results.csv`, complete country/sector `coverage.csv`, detailed JSON results, raw company snapshots and sector-discovery evidence.

## Regression validation

78 focused backend tests passed across DCF, statement basis, Excel, the audit runner and yield-cache concurrency. A separate 59 adjacent market-function/valuation tests passed. Existing Pydantic deprecation warnings remain. No frontend code changed in this audit pass.

A model check passing is not independent verification of filings or an out-of-sample accuracy result.

## Final empirical results

- 760 distinct selected issuers have audit records; 756 produced comparable valuations across 46 markets.
- 754 company records use fresh captured inputs; two use explicitly labelled 28 October snapshots because current statement currencies could not be reconciled. Four further currency-conflict records remain unvalued. These total six fresh currency conflicts; none was repaired by an unverified FX assumption.
- No mechanical failures were found in the valued sample. There is no remaining provider-deferred work in this manifest.
- 298 of 550 country/sector cells have at least two valued companies; 98 have one; 154 have none. Full multiple-company coverage has **not** been achieved.
- The Philippines, Kuwait, Egypt and Vietnam have no eligible company sample from the current platform universe/provider discovery. Other gaps are documented cell by cell; they do not prove that no companies exist in those sectors. Extending the primary-listing universe and verified financial-data coverage is needed to close them.
- Models used: 549 FCFF, 114 dividend models and 93 excess-return models. Model fallbacks and their reasons are retained in the company results.
- 577 valued cases require further research; 179 clear the implemented data/model checks. Those 179 are not certified investment values.
- Sample sizes: 329 large, 366 mid, 63 small and two micro companies. This tests size diversity across the sample, not every size band in every market/sector.

[Company results](../data/processed/dcf_matrix_2026-10-31/results.csv) · [Complete 550-cell coverage](../data/processed/dcf_matrix_2026-10-31/coverage.csv) · [Detailed results](../data/processed/dcf_matrix_2026-10-31/results.json)

## Sector coverage

| Sector | Valued companies | Markets with ≥2 valued companies |
|---|---:|---:|
| Communication Services | 65 | 24 |
| Consumer Discretionary | 66 | 25 |
| Consumer Staples | 72 | 32 |
| Energy | 62 | 22 |
| Financials | 95 | 43 |
| Health Care | 53 | 22 |
| Industrials | 91 | 35 |
| Information Technology | 52 | 19 |
| Materials | 71 | 30 |
| Real Estate | 62 | 21 |
| Utilities | 67 | 25 |

## Market coverage

| Market | Valued companies | Sectors with ≥2 / 11 | Sectors with one | Sectors with none |
|---|---:|---:|---:|---:|
| Argentina | 11 | 4 | 3 | 4 |
| Australia | 24 | 11 | 0 | 0 |
| Austria | 13 | 5 | 3 | 3 |
| Belgium | 15 | 6 | 3 | 2 |
| Brazil | 22 | 9 | 2 | 0 |
| Canada | 25 | 11 | 0 | 0 |
| Chile | 12 | 4 | 4 | 3 |
| China (A-shares) | 20 | 10 | 0 | 1 |
| Czech Republic | 5 | 1 | 3 | 7 |
| Denmark | 14 | 4 | 5 | 2 |
| Egypt | 0 | 0 | 0 | 11 |
| Estonia | 5 | 2 | 1 | 8 |
| Finland | 16 | 5 | 6 | 0 |
| France | 22 | 10 | 1 | 0 |
| Germany | 21 | 10 | 0 | 1 |
| Greece | 10 | 4 | 2 | 5 |
| Hong Kong | 42 | 11 | 0 | 0 |
| Hungary | 5 | 1 | 3 | 7 |
| Iceland | 6 | 2 | 2 | 7 |
| India | 22 | 11 | 0 | 0 |
| Indonesia | 14 | 6 | 2 | 3 |
| Ireland | 12 | 5 | 2 | 4 |
| Israel | 16 | 6 | 3 | 2 |
| Italy | 21 | 9 | 2 | 0 |
| Japan | 25 | 11 | 0 | 0 |
| Kuwait | 0 | 0 | 0 | 11 |
| Lithuania | 5 | 1 | 3 | 7 |
| Malaysia | 19 | 8 | 3 | 0 |
| Mexico | 13 | 6 | 1 | 4 |
| Netherlands | 18 | 7 | 3 | 1 |
| New Zealand | 11 | 4 | 2 | 5 |
| Norway | 15 | 6 | 1 | 4 |
| Philippines | 0 | 0 | 0 | 11 |
| Poland | 13 | 4 | 5 | 2 |
| Portugal | 10 | 3 | 4 | 4 |
| Qatar | 8 | 1 | 6 | 4 |
| Romania | 7 | 3 | 0 | 8 |
| Saudi Arabia | 19 | 8 | 3 | 0 |
| Singapore | 13 | 4 | 4 | 3 |
| South Africa | 16 | 7 | 2 | 2 |
| South Korea | 19 | 8 | 3 | 0 |
| Spain | 20 | 8 | 3 | 0 |
| Sweden | 20 | 9 | 1 | 1 |
| Switzerland | 19 | 8 | 2 | 1 |
| Taiwan | 16 | 7 | 2 | 2 |
| Thailand | 19 | 9 | 1 | 1 |
| Turkey | 17 | 7 | 2 | 2 |
| United Kingdom | 23 | 11 | 0 | 0 |
| United States | 38 | 11 | 0 | 0 |
| Vietnam | 0 | 0 | 0 | 11 |

The updated local API was restarted and its model-parameters endpoint returned HTTP 200. `git diff --check` passed. No frontend changes were needed for this audit; existing research-status handling displays the stricter readiness outcomes.
