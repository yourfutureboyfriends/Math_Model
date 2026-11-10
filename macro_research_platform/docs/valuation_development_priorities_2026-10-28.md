# Valuation development priorities — 28 October 2026

## Assessment

The operating DCF, financial excess-return, dividend and PE engines provide a useful
research/screening foundation with tested mathematical identities. Passing those tests
does not establish forecast accuracy or deal readiness. The largest gains now come
from improving the economic inputs and validating forecasts, rather than adding more
decimal places or averaging more methods.

## Highest-impact work

| Priority | Work | Why it matters | Validation target |
|---|---|---|---|
| 1 | Issuer/accounting reconciliation | SEC/provider depreciation conflict already observed live for MSFT | Trace matched period/currency/component definitions to filings |
| 2 | Driver-based forecasts | Aggregate growth and margin assumptions hide capacity and cash needs | Holdout revenue, margin and reinvestment error by sector/size |
| 3 | Funding and dilution | A positive terminal equity value cannot fund an interim cash deficit | Quarterly cash, maturity, interest and share-count identities |
| 4 | Sector-specific valuation | Property, holding-company, resources and financial firms differ economically | NAV, look-through, reserve and regulatory-capital reconciliations |
| 5 | Currency and country exposure | Listing location is not the same as operating risk | Currency-consistent cash flows/rates and dated revenue exposure |
| 6 | Historical validation | Restated histories and present prices cannot prove investment value | Publication-time data, delistings, untouched holdouts and costs |

Discount-rate/scenario assumptions should remain transparent. More scenarios do not
create empirical probabilities. Use forecast-error distributions only after obtaining
adequate historical samples, and keep economic uncertainty distinct from missing data.

## PE work completed in this pass

Corrected mezzanine maturity, zero-IRR weighting, invalid scenario weights, duplicate
source names and excess closing revolver draws. Exposed interest-solver convergence and
funding eligibility; prevented unfunded cases from clearing the hurdle or producing a
maximum bid. Added the IRR of weighted cash flows alongside the scenario-average IRR.
See [PE documentation](private_equity.md) for remaining development and primary sources.

The PE section is still an annual screening model. Generic tax rules, quoted-company
EBITDA, simplified covenants and value-only Excel exports require further development
before describing it as a complete transaction underwriting model.
