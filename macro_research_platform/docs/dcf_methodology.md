# DCF — method, calibration and known limits (Oct 2026)

Code: `api/marketdata/dcf.py`; tests `api/tests/test_dcf_refinements.py`. UI: Markets → Valuation.

## Method

| Piece | Rule | Why |
|---|---|---|
| Model | FCFF for operating companies; excess-return / dividend model for banks and insurers | Damodaran |
| Starting point | **Trailing twelve months** from the last four quarterly statements (revenue, operating income, capex, D&A) | Yahoo's `operatingMargins` is the latest quarter only |
| Equity risk premium | Damodaran's monthly **implied** ERP + country risk premium (default); Kroll's 5.0% appraisal standard as a switch in the UI | see calibration |
| Beta | Bottom-up industry unlevered beta, relevered; banks and insurers take the higher of the industry beta and a Blume-adjusted regression | Damodaran's European regional-bank beta (0.39) gave BNP a 5.1% cost of equity; the EBA sees 8–12% |
| Margins | Fade from TTM to a target over the forecast; for cyclicals (cyclical industry *and* margins swinging ≥ 40% of their median, or no history) the target is the mid-point of the company's long-run median and the industry margin, reached in 3 years when today's is 25% above it | Samsung, ExxonMobil peak margins were being capitalised |
| Reinvestment | Years 1–5 blend the company's actual net capex / revenue with the sales-to-capital rule, moving to the rule by year 5 | Oracle's capex boom was ignored |
| Terminal growth | The risk-free rate (≥ 0), the pairing Damodaran's implied ERP assumes; the "gdp" rule caps it at long-run nominal growth by currency (USD 4.0%, EUR 3.2%, GBP 3.5%, JPY 2.5%, CHF 2.2%) | Delaware Chancery: inflation floor, nominal GDP ceiling |
| Terminal return on new capital | Cyclicals earn their cost of capital; others keep half of their excess return, capped at 30% | McKinsey: top-ROIC firms stay above WACC |

## Calibration — 58 operating companies, 7 financials (value / price)

| | Median | Median miss | Within ±30% | Within ±50% | Off by 2× or more |
|---|---|---|---|---|---|
| Operating, before | 1.01 | 0.37 | 43% | 67% | 9 |
| Operating, after | 0.92 | 0.36 | 40% | 78% | 7 |
| Financials | 0.99 | 0.15 | | | |

The Kroll 5% ERP put the median at 0.69–0.77, which is why the implied premium stays the default. A market-price
median near 1 is not proof of accuracy; it shows the inputs are not biased as a whole.

**Still far from the price:** TSMC 2.39, Oracle 2.32, BP 2.27, Adobe 1.78, BNP 1.76, Nestlé 1.74 above;
Tesla 0.04, Linde 0.39, Boeing 0.40, Walmart 0.48 below. These are quality premia, turnarounds and option value
that a mechanical DCF cannot see — the cases where your own assumptions (the overrides in the UI) matter most.

## Sources

- Damodaran implied ERP and country risk: <https://www.bvresources.com/articles/bvwire/damodaran-unveils-his-annual-erp-update>,
  <https://bvresources.com/articles/bvwire/damodaran-posts-his-first-data-update-for-2026>
- Kroll recommended US ERP 5.0%: <https://www.bvresources.com/articles/bvwire/kroll-reaffirms-50-us-erp-sticks-with-treasury-risk-free-rate>,
  executive summary <https://edge.sitecorecloud.io/krollllc17bf0-kroll6fee-proda464-0e9b/media/Cost-of-Capital/kroll-cost-of-capital-updates-jan26-executive-summary.pdf>
- EU bank cost of equity (EBA): <https://en.paperjam.lu/article/resilient-profits-tighter-margins-at-eu-banks-eba>;
  Alvarez & Marsal banking valuation newsletter: <https://www.alvarezandmarsal.com/sites/default/files/2025-12/477648-55909_VAL_GER_Banking%20Newsletter%20V2.pdf>
- Return on capital persistence: <https://moiglobal.com/looking-for-the-next-roic-machine/>;
  value-driver formula: <https://edbodmer.com/mckinsey-value-driver-formula-distortions/>

Not investment advice.
