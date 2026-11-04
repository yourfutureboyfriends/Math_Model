# DCF developed-market audit — 28 October 2026

## Conclusion

The implementation is useful as a transparent valuation screen and scenario tool, but the automatic defaults are **not uniformly reasonable across all businesses**. Correcting statement periods and currency integrity improves the evidential basis; it does not validate every estimated price. The largest remaining gaps require business-specific work rather than a geographic multiplier fitted to prices.

The audit selected 115 stocks across all 23 MSCI developed-market listing markets and all 11 sectors: 44 large, 48 mid, 22 small and one micro cap. It calculated the primary model and both four-scenario comparison lenses. It also calculated reverse growth/discount rates for operating companies and reverse ROE for financial firms. This is a cross-sectional audit of current inputs, **not** a point-in-time historical backtest, a return forecast, or a buy list.

## Reproducibility and selection

`data/processed/dcf_audit_2026-10-28/` contains:

- `manifest.json`: stock selection and saved-universe timestamp.
- `snapshots/`: immutable original inputs, quote-summary fields, dividend histories and FX.
- `statement_evidence/`: separately captured dated statement totals and currency metadata.
- `baseline.json` / `baseline.csv`: original results before this audit's model changes.
- `corrected.json` / `corrected.csv`: corrected results, scenarios, projections, flags and reverse valuations.
- `comparison.csv`: compact before/after comparison for every selected stock.
- `baseline_summary.json` / `corrected_summary.json`: grouped diagnostics.
- `parex_country_sensitivity.json`: operating-exposure sensitivity supported by issuer evidence.
- `live_smoke.json`: six end-to-end checks of the corrected live input path.

The sample was selected before reading valuation outcomes: largest, a mid-cap (or median available), and smallest available company in each country; sector/size coverage; a small-cap supplement; and familiar diagnostic anchors. Size thresholds are USD market capitalization at selection: micro below $300m, small $300m–$2bn, mid $2bn–$10bn, large at least $10bn. These are practical audit buckets, not MSCI size-index definitions.

The platform's existing liquid-stock universe is large-cap-heavy. This sample covers every market and sector collectively; it does not cover every country × sector × size cell. Country means listing-market classification: some companies listed in a developed market operate mainly in emerging markets. The sample is not random, index-weighted, survivor-free, or representative of every listed small company.

Matched reruns hold the original prices, FX, beta, ERP and consensus growth assumptions fixed. Statement evidence supplies coherent replacement periods; the terminal-growth rule changes as described below. Reproduce the corrected run without fetching company data, from the repository directory:

```sh
../.venv/bin/python scripts/audit_dcf_markets.py --evaluate --aligned --label corrected
```

A fresh fetch/evidence run uses the same script with `--workers 2`, followed by `--supplement-statements`. It checkpoints each stock. Fresh data will not reproduce historical prices; use the saved snapshots for this audit.

## Before and after

A value/price ratio of 1 means agreement with the observed price; 2 means twice the price. Agreement is a diagnostic and is **not a scoring target or proof of correctness**.

| Diagnostic | Before | Corrected |
|---|---:|---:|
| Selected stocks | 115 | 115 |
| Numerical primary valuations | 114 | 114 |
| Median value / price | 1.12× | 1.07× |
| Within ±30% of price | 38.6% | 36.8% |
| Outside 0.5–2.0× price | 28 | 26 |
| Mixed-period margin fallbacks | 63 | 16 |
| Statement date unavailable | 99 | 16 |
| Negative modeled equity, displayed as zero | 2 | 5 |

The excluded cases differ: the original model could not value 0017.HK because terminal growth was too close to WACC; the corrected model values it at zero but flags the property/accounting limitations. The corrected input path blocks 9911.HK because its annual statements and current financial-currency label conflict. For the **113 stocks numerical in both runs**, the median changes from 1.13× to 1.08×; the number outside 0.5–2× changes from 28 to 25.

Price proximity within ±30% did not improve. This is deliberately reported: the corrections were selected for accounting and model consistency, not to minimize gaps to the price. Five corrected equity estimates are zero; that is not a claim that those shares should trade at zero, especially where property assets, financing or recovery options need a different model.

## Implemented corrections

1. **Consecutive periods.** Four quarterly observations must be 60–120 days apart. Four semiannual observations or a missing quarter cannot be treated as one year.
2. **Matched cash-flow dates.** Capex and depreciation must match the income-statement dates; zero depreciation is retained.
3. **Coherent annual fallback.** If four quarters are unavailable, use reported fiscal-year revenue and operating profit, matching annual capex/depreciation where available. Recalculate capital intensity, ROIC and the existing margin rules. Explicitly label annual data; do not combine trailing sales with a single-quarter margin.
4. **Statement dates.** Preserve actual dates rather than dropping them from Yahoo-sourced inputs.
5. **Currency validation.** Retain the period-specific `currencyCode` that yfinance discards. A conflict with the current financial-currency label blocks valuation pending reconciliation; converting only EBIT would leave balance-sheet amounts on an uncertain basis. Missing currency metadata remains a review flag.
6. **Sustainable terminal growth.** Enable the existing currency-specific nominal-growth ceiling: default growth is the lower of the risk-free rate and that ceiling. The existing ceilings are static model assumptions, not newly estimated macro forecasts. Explicit overrides and guardrails remain. The earlier `rf` setting remains available for replication.
7. **Model suitability.** Show review reasons in VAL and the API for holding/asset-management companies, property firms, resource producers, losses, missing reinvestment/balance-sheet data and unverified statement currency. A clear check does not certify fair value.

The same FCFF, excess-return and dividend models remain in use. No country or sector multiplier was optimized to prices; no new scenario probabilities or live sentiment forecasts were invented.

## Investigated cases

| Stock | Before value / price | Corrected value / price | Interpretation |
|---|---:|---:|---|
| VGP.BR | 2.61× | 0.96× | Matched annual operating profit replaces a mismatched-period margin. Property cash flows/NAV still require review. |
| GN.CO | 0.37× | 0.83× | Reported annual operating basis and capex materially change the estimate; not evidence that the resulting value is correct. |
| KMR.IR | 1.95× | 0.67× | Including matching annual capital expenditure materially reduces value; resource assumptions still need review. |
| PXT.TO | 6.29× | 4.84× | Still a large gap after period correction; Colombia exposure and acquisition/capital guidance matter. |
| INVE-B.ST | 4.53× | 4.53× | Investment-holding company: a bank-style ROE extrapolation is not a substitute for look-through NAV. |
| 0590.HK | 4.47× | 5.26× | Still a large gap; issuer operating profit differs from the provider-defined operating-income line. |
| 9911.HK | 1.06× | not available | Annual statements are in CNY while the current financial-currency label is USD; block instead of mixing bases. |
| 0017.HK | not available | 0.00× | Numerical terminal-rate failure resolved, but zero equity from an operating DCF is not a property NAV valuation. |

Research behind these interpretations:

- **VGP/property:** [IAS 40](https://www.ifrs.org/issued-standards/list-of-standards/ias-40-investment-property/) permits property fair-value changes in profit or loss; recurring cash earnings must be reconciled. [VGP reports](https://www.vgpparks.eu/investors/reports/) provide the appropriate issuer documents. Merely obtaining a value close to price does not resolve that accounting problem.
- **Investor AB:** the [issuer's portfolio and NAV reporting](https://www.investorab.com/) supports a NAV/look-through approach. The audit flags its automatic excess-return result rather than presenting the large apparent upside as a stock recommendation.
- **Newborn Town:** the [issuer's 2025 annual report](https://newsfile.futunn.com/public/NN-PersistNoticeAttachment/7781/20260423/12117423-0.PDF) reports RMB financial statements. Raw statement metadata confirms CNY for the annual period. This can reflect a reporting-currency transition; it is not necessarily a mislabeled current quote. Historical and current bases must be reconciled together.
- **Lukfook:** [FY2026 issuer results](https://www.lukfook.com/en/category/news-press-releases/post/lukfook-group-0590-announces-annual-results-for-the-year-ended-31-march-2026) report HK$17.21bn revenue and HK$2.65bn operating profit, whereas the provider's annual operating-income line is HK$3.44bn. The code cannot infer the bridge automatically. The issuer also identifies record gold-related profitability; treat current margins cautiously.
- **Parex:** [issuer operations](https://www.parexresources.com/operations/) identify its Colombian focus and material capex, while [transaction/guidance disclosures](https://www.parexresources.com/press-releases/parex-resources-positioned-to-become-colombias-largest-independent-oil-gas-producer-provides-step-change-guidance-reports-q1-2026-results-and-declares-q2-2026-dividend-2/) show a changing asset base. Replacing the Canadian home-country premium with 100% Colombia operating exposure adds about 2.61 percentage points of country premium in the saved provider table and reduces the current-market comparison from roughly 4.84× price to 3.41×. That is a sensitivity test, not a completed issuer valuation.
- **Methodology:** [Damodaran on terminal assumptions](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/project/prques.htm), [normalizing earnings](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/normearn.htm), and [commodity-company characteristics](https://pages.stern.nyu.edu/adamodar/New_Home_Page/littlebook/commoditycompanies.htm) support growth limits, cycle normalization and explicit treatment of finite resources. Short histories may not span a full cycle.

## Sector diagnostics — corrected

Small cell counts preclude broad conclusions about a whole sector. These ratios show where further research is needed.

| Sector | Attempted | Valued | Median value / price | Outside 0.5–2× |
|---|---:|---:|---:|---:|
| Communication Services | 6 | 6 | 1.21× | 4 |
| Consumer Discretionary | 11 | 11 | 1.06× | 3 |
| Consumer Staples | 7 | 7 | 0.77× | 0 |
| Energy | 9 | 9 | 1.23× | 4 |
| Financials | 18 | 18 | 1.26× | 1 |
| Health Care | 8 | 8 | 0.50× | 4 |
| Industrials | 18 | 18 | 1.14× | 4 |
| Information Technology | 12 | 11 | 1.03× | 2 |
| Materials | 8 | 8 | 0.91× | 2 |
| Real Estate | 12 | 12 | 1.26× | 2 |
| Utilities | 6 | 6 | 0.93× | 0 |

## Size diagnostics — corrected

| Size | Attempted | Valued | Median value / price | Outside 0.5–2× |
|---|---:|---:|---:|---:|
| micro | 1 | 1 | 0.67× | 0 |
| small | 22 | 21 | 1.25× | 8 |
| mid | 48 | 48 | 1.11× | 10 |
| large | 44 | 44 | 1.04× | 8 |

## Country coverage — corrected

Market definitions follow [MSCI's May 2026 methodology](https://www.msci.com/eqb/methodology/meth_docs/MSCI_GIMIMethodology_May2026.pdf). Korea and Taiwan are not included in this developed-market definition. All selected stocks are listed in developed markets; operating exposure can differ.

| Listing market | Attempted | Valued | Median value / price |
|---|---:|---:|---:|
| Australia (AU) | 4 | 4 | 0.65× |
| Austria (AT) | 3 | 3 | 1.59× |
| Belgium (BE) | 3 | 3 | 1.00× |
| Canada (CA) | 4 | 4 | 0.75× |
| Denmark (DK) | 3 | 3 | 1.34× |
| Finland (FI) | 3 | 3 | 1.37× |
| France (FR) | 4 | 4 | 1.04× |
| Germany (DE) | 3 | 3 | 1.03× |
| Hong Kong (HK) | 20 | 19 | 1.23× |
| Ireland (IE) | 5 | 5 | 0.67× |
| Israel (IL) | 4 | 4 | 0.87× |
| Italy (IT) | 3 | 3 | 1.02× |
| Japan (JP) | 6 | 6 | 1.14× |
| Netherlands (NL) | 3 | 3 | 1.35× |
| New Zealand (NZ) | 3 | 3 | 1.30× |
| Norway (NO) | 4 | 4 | 1.17× |
| Portugal (PT) | 4 | 4 | 0.88× |
| Singapore (SG) | 3 | 3 | 1.08× |
| Spain (ES) | 3 | 3 | 0.95× |
| Sweden (SE) | 3 | 3 | 1.57× |
| Switzerland (CH) | 5 | 5 | 1.10× |
| United Kingdom (GB) | 3 | 3 | 1.43× |
| United States (US) | 19 | 19 | 0.86× |

## Remaining limits and validation

- 52 numerical outputs have explicit model/data review requirements. In addition, one currency conflict is blocked. These flags are independent of the distance from market price.
- Sixteen inputs still lack a usable statement date. Missing provider data is not filled with an invented value.
- The commodity model still lacks explicit reserves, production decline, realized-price curves, maintenance capex and consistently measured operating-country exposure. The property model needs NAV/FFO and development accounting; investment holding companies need portfolio-level valuation.
- Forecast growth and margins may depend on analyst expectations, short historical windows or provider definitions of EBIT. The forecast does not yet validate acquisition funding, future share dilution or financing under each scenario.
- Annual fallback data can be older than TTM data. It is more coherent, not automatically more timely. Working capital in the reinvestment anchor and sector-specific growth persistence need further work.
- Scenario shifts are illustrative. Their ranges are not confidence intervals; no probabilities are assigned. The three-year outlook convergence assumption is not validated by this cross-section.
- Validation here comprises 50 tests (35 targeted route/statement/currency/model/Excel tests and 15 existing DCF/financial-engine checks), a TypeScript type check, and six live input-path smoke checks. One smoke case deliberately fails the currency guard. It does not establish out-of-sample investment performance.

Use the full comparison CSV to identify cases for manual research. Do not rank stocks solely by the largest automatic upside: several of the largest gaps are exactly where the economic model or accounting basis needs the most work.
