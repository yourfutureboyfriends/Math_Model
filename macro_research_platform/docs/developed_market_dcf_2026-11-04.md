# Developed-market DCF implementation — 4 November 2026

Coverage follows the FTSE classification snapshot dated 6 October 2026: 27 company domiciles, counting Belgium and Luxembourg separately. It includes Greece, Poland and South Korea; other index providers use different classifications.

The engine matches risk-free rates and terminal nominal-growth ceilings to financial-statement currency. Government yields are adjusted for issuer default spread. HKD uses a disclosed USD currency-peg proxy; SGD can use an inflation-differential proxy. Missing local data remains an explicitly labelled estimate. Growth ceilings are research assumptions, not central-bank forecasts.

Cost of equity is risk-free + beta × mature-market premium + country premium + governance premium. Country premiums are additive rather than multiplied by beta. Documented operating-country weights can replace domicile exposure and must sum to one. No country receives a forced share-price valuation, blanket governance haircut or fixed WACC merely because it is developed.

Published marginal tax rates are taken from Damodaran's January 2026 country-tax workbook (Tax Foundation reference). Current rows take precedence over a historical appendix. The global minimum-tax alternative is separate: it is not automatically imposed on every company. Sustainable company tax, state taxes and international profit mix still require review.

Existing sector engines remain: operating FCFF, financial excess-return and dividend models. Cyclical normalization, reinvestment, capital intensity and terminal returns remain company/industry dependent. Country context highlights resource cycles, low-yield currencies, cross-holdings and international tax considerations without automatically changing company economics.

The valuation UI displays local assumptions, source/fallback basis and review notes. Bear/base/bull probabilities must sum to one; invalid positive-probability cases withhold expected value. Reverse DCF solves one assumption at a time, with other cash flows fixed where indicated.

## Standalone scenario engine

Run from the project directory:

    ../.venv/bin/python -m api.marketdata.dcf_scenarios

This prints a synthetic demonstration, not researched company valuations. `FCFModel`, `RiskAssumptions`, `Scenario`, `scenario_matrix` and `reverse_dcf` are reusable Python interfaces. Optional Western-tech/China profiles are analyst scenarios; advisory WACC bands do not silently override calculated rates.

## Validation and limits

Deterministic tests cover all 27 countries and both cyclical modes, currency configuration, additive premiums, operating-exposure weighting, country aliases and tax-table duplicate protection. These validate calculation behavior, not the quality of every live company's statements. Forecasts remain sensitive to normalized free cash flow, dilution, ADR/quote units, terminal assumptions and source freshness.

Sources:
- https://www.lseg.com/content/dam/ftse-russell/en_us/documents/country-classification/matrix-of-markets.pdf
- https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/ctryprem.html
- https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/countrytaxrates.html
- https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/CountryRisk.htm
- https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/a17.htm
