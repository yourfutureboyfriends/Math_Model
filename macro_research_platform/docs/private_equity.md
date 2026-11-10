# Private equity area (PE)

Top-bar mode **PE**. Four tools; the backend is `api/pe/` and `api/routers/pe.py` (`/api/v1/pe/...`), tests in
`api/tests/test_pe.py` (hand-built deals and closed forms). Modelled returns are analysis — never a fund track record.

## LBO workbench (`api/pe/lbo.py`, `api/pe/market.py`)

**Load a listed company** (`/pe/company/{symbol}`) or start from the illustrative case; every assumption is editable
and the model re-runs on each change.

| Block | What it does | Default source |
|---|---|---|
| Target | LTM revenue, EBITDA (= operating income + D&A), existing debt (refinanced) and cash | SEC filings / Yahoo via the DCF inputs |
| Entry | EV = multiple × LTM EBITDA; transaction fees (% EV), financing fees (% debt, amortised over each tranche's tenor), minimum cash, rollover equity | Price + 30% take-private premium |
| Financing | Tranches in seniority: TLA (amortising), TLB (1% a year + cash sweep), senior notes (bullet), mezzanine (PIK); a revolver that funds shortfalls; floating at base + spread with a floor, or fixed | Base rate SOFR / SONIA / €STR (FRED); TLB spread = ICE BofA single-B OAS (≥ 2.75%); notes = 5-yr Treasury + BB/B OAS; leverage = min(6.0×, interest cover ≥ 2.25×, 55% of price) |
| Plan | Revenue growth and EBITDA margin by year, D&A / capex (% revenue), working capital (% of the change in revenue) | Analyst growth fading to the long-run rate; today's margin |
| Tax | Interest deductible up to 30% of EBITDA (US §163(j), UK CIR, EU ATAD) with the excess carried forward; losses carried forward | Marginal rate |
| Exit | Multiple × exit-year EBITDA, exit fees, management incentive plan (% of the equity gain) | Entry multiple (no expansion); industry EV/EBITDA (Damodaran, by region) shown as a reference |

**Mechanics.** Annual periods. Interest on the average balance, solved by iteration (the circular reference a
spreadsheet handles with iterative calculation), or on opening balances. Cash waterfall each year: levered FCF
(EBITDA − cash interest − tax − capex − ΔNWC) → mandatory amortisation → revolver repaid (or drawn for a shortfall) →
cash sweep of the excess into sweepable tranches in seniority order. A shortfall beyond the revolver is flagged as a
liquidity gap.

**Outputs.**
- Sponsor IRR and MOIC for the base, upside and downside cases, plus the probability-weighted IRR.
- Sources & uses.
- The value-creation bridge: EBITDA growth × entry multiple, multiple expansion × exit EBITDA, debt paydown, fees,
  MIP. It sums exactly to the equity gain.
- The debt paydown.
- Credit statistics: total, senior and net leverage, interest cover, FCCR, FCF / debt.
- Covenant tests: maximum net leverage stepping down 0.25× a year from closing + 1.0×, and minimum interest cover
  2.0×.
- IRR grids: entry × exit multiple, leverage × growth, exit year × multiple.
- **The maximum entry multiple (and price per share) that still earns the hurdle IRR.** The financing is held in
  turns of EBITDA.
- **The EBITDA cushion:** the permanent EBITDA cut that first breaches a covenant, and the cut that runs out of cash.

**Excel model** (`/pe/lbo/excel`): an investment-committee workbook with these sheets: Summary, Operating model, Debt
schedule, Credit & covenants, Sensitivities, and Assumptions (with sources). The figures are values, not formulas.

## Deal pipeline (`api/pe/deals.py`)

Saved deals live in the current fund's own database. Each deal keeps:

- its stage (Sourcing → Screening → First-round bid → Due diligence → Final bid / IC → Signed → Closed, or Passed);
- its full inputs and the headline results of its last run;
- an activity log of stage changes and notes, with who made them and when.

Open any deal back in the workbench.

## Carry waterfall (`api/pe/fundmath.py · waterfall`)

The European (whole-fund) waterfall pays out in this order:

1. return of capital;
2. the preferred return, compounded annually from each contribution's date;
3. the GP catch-up at any rate: the GP takes `catch_up` of each unit until it holds `carry` of all profit, i.e.
   x = (carry·(LP+GP) − GP) / (catch_up − carry);
4. the carried-interest split.

It reports each distribution's split, LP net vs gross IRR, the LP net multiple, and any capital or preferred return
still owed.

## Fund performance (`api/pe/fundmath.py · performance`)

From dated cash flows plus the NAV:

- XIRR (actual/365), TVPI, DPI, RVPI;
- against a public index (default `^SP500TR`, Yahoo Finance):
  - **KS-PME** (Kaplan & Schoar 2005);
  - **Direct Alpha** (Gredil, Griffiths & Stucke 2014);
  - the **Long-Nickels PME IRR**. This one is reported as undefined when the replicating index portfolio goes
    negative, its known flaw.

## Calculation improvements — 28 October 2026

- Mezzanine principal becomes due at its stated tenor, including that year's final
  PIK coupon. Previously only non-mezzanine tranches reached the maturity waterfall.
- Exact zero scenario IRRs remain zero. Finite, nonnegative scenario weights are
  normalized and an all-zero set is rejected.
- `weighted.irr` is the arithmetic scenario-average IRR. The separate
  `weighted.expected_cashflow_irr` is the IRR of weighted scenario cash flows; these
  are different measures. Weights are assumptions, not calibrated probabilities.
- `calculation_checks` exposes interest convergence and funding through exit.
  Unfunded or unconverged cases cannot clear the hurdle; the maximum-bid result is
  withheld until those issues are resolved. Numerical returns remain visible as
  conditional model outputs.
- Duplicate debt/source names and closing revolver draws above commitment are rejected.
- Company-source labels distinguish fiscal-year bases from TTM. The 30%-of-EBITDA
  interest cap is explicitly a generic modeling assumption, not a complete local tax engine.

### Next development priorities

1. Deal diligence: reported → adjusted → underwritten EBITDA, with individual add-backs,
   supporting sources, recurring cash costs and an explicit lease-accounting basis.
2. Financing: quarterly liquidity, minimum cash, revolver tenor/borrowing base, refinancing
   terms/fees, lender commitments and downside capital injections; no assumed rescue funding.
3. Jurisdiction/date-specific tax: taxable-income reconciliation, interest income,
   exemptions/group rules, NOL utilization limits and carryforwards; do not treat US,
   UK and EU regimes as one 30% EBITDA rule.
4. Valuation: comparable transactions with source dates, entry-to-exit multiple changes,
   working-capital peg, debt-like liabilities, purchase-price allocation and exit recovery.
5. Deliverables: an editable Excel model with formula parity checks; current PE exports
   contain calculated values. Add IC readiness and a diligence checklist linked to the pipeline.
6. Validation: reject nonfinite/out-of-domain inputs throughout, test all debt/maturity
   combinations and extend independent cash/debt/tax reconciliation coverage. The current
   improvements are useful but do not certify every input combination.

Public research context: [IRS Form 8990 instructions](https://www.irs.gov/instructions/i8990)
show why tax adjustments and effective dates matter. [OCC/FDIC's December 2025 statement](https://occ.treas.gov/news-issuances/news-releases/2025/nr-ia-2025-119.html)
emphasizes projection comparisons and refinancing availability. It also withdrew those
agencies' prior interagency leveraged-lending guidance; historical leverage benchmarks
must not be presented as universal current regulatory requirements.

## Workbench development — platform usability pass

The workbench now groups inputs into Deal, Financing, Plan & exit and Diligence, with
headline results above the input panels. Undo/redo keeps up to 40 input edits, a
manual comparison baseline captures the current run, and Keep/Restore draft uses
session storage scoped to the signed-in user and fund. Drafts are not automatically
saved to the deal database. Stale results do not mix with a new input set; failed
calculations clear the old result. Adding a tranche creates a distinct name.

### EBITDA and diligence

`ebitda` remains the reported base. Signed `ebitda_adjustments` enter the model only
when `approved` and supported by a `label` and `source`. Entry EBITDA becomes reported
plus accepted adjustments. Forecast margins remain independent unless
`apply_adjustments_to_plan` is set, in which case accepted adjustments / base revenue
is added to the provided margin path. This explicit switch prevents double-counting
an already normalized business plan. Evidence is user-provided, not automatically verified.

The `diligence` input persists six review areas in the existing saved deal. The
pipeline summary shows progress and seasonal funding issues. Checklist completion
means user-attested screening progress, never IC or lender approval.

### Tax and lender terms

Added opening NOL and disallowed-interest balances, EBITDA/EBIT interest-cap basis,
interest income, taxable-income adjustment, deduction floor, NOL utilization share and
an optional annual NOL amount limit. Closing NOL and interest carryforwards are
visible in API schedules. These parameters implement explicit assumptions; they do
not implement a complete national tax code. The UI's US-style and GBP-only UK-style
screening presets set selected parameters. They exclude group allocations, worldwide
debt caps, exemptions, vintage-specific losses and ownership-change restrictions.
Primary references: [IRS Form 8990](https://www.irs.gov/instructions/i8990),
[IRS corporation guidance](https://www.irs.gov/publications/p542),
[HMRC interest restriction](https://www.gov.uk/guidance/restriction-on-corporation-tax-relief-for-interest-deductions).

Lender settings expose leverage/interest-cover covenants, annual step-down, opening
revolver draw and revolver maturity. Matured revolvers cannot silently redraw. Custom
zero leverage limits are preserved rather than overwritten by defaults.

### Quarterly cash timing

Annual FCF and mandatory debt repayment are allocated to four quarters with explicit
weights summing to 100%. Cash sweeps occur in Q4; revolver draws/repayments cover
interim timing. Results show peak revolver and reserve shortfalls. Seasonal shortfalls
prevent a maximum bid and a hurdle pass. This is a diagnostic, not an integrated
quarterly debt/tax underwriting engine: incremental seasonal interest, quarterly tax
true-ups, refinancing, covenant cures and rescue equity are excluded.

### Editable Excel sheets

The six snapshot sheets retain the API's selected interest convention. `Live inputs`,
`Live model` and `Live returns` add an editable annual model with opening-balance
interest, a full debt/cash/tax waterfall and formula-driven exit returns. Blue cells
are editable and Excel recalculates on opening. The original number of forecast years
and tranche slots is structural; changes to those require a new export. Formula/reference
differences compare against the opening-method API result, which is not necessarily
the average-interest snapshot. Native currency units are used on live sheets; snapshot
sheets choose native units or millions for the deal size. Diligence and cash timing
are exported separately. Eight independently evaluated formula cases check annual
cash, debt, taxes, carryforwards, IRR and MOIC against the Python engine, including
maturities, PIK, working capital, adjustments and floating-rate paths.

Remaining transaction work includes integrated quarterly interest/tax, committed
refinancing and rescue funding, purchase-price allocation, lender-specific covenants,
automatic issuer add-back verification and complete jurisdictional tax treatment.

## Market evidence — loan pricing and comparables (1 November 2026)

**Term loan B pricing from the loan market** (`api/pe/market.py · loan_market`).
- No free source publishes loan quotes. The proxy is the two largest US senior-loan ETFs, BKLN and SRLN.
- Each fund's latest three monthly distributions are annualised over the price, the expense ratio is added back, and
  SOFR is subtracted. The result is the average spread of the floating-rate loans the funds hold. The trailing
  12-month yield isn't used because it lags rate changes.
- The default TLB spread uses this figure (floor 2.75%, rounded to ⅛%), and falls back to the single-B bond spread
  when the ETFs are unavailable.
- On 1 November 2026 it gave SOFR + 3.44% (BKLN) and + 4.15% (SRLN, which holds lower-rated loans), so the default
  was SOFR + 3.75%.
- This is market evidence, not a quote for a specific credit. Non-US deals still use the US loan market.

**Comparables** (`api/pe/comps.py`; Comparables card in the workbench, Precedents tab). Three sources:
- **Trading comps:** listed peers' EV/EBITDA today, from the platform's peer engine (same industry, by region).
  Multiples above 40× or at or below zero are listed but left out of the statistics.
- **Precedent transactions:** the fund's own book in its database. Each deal needs a date, target, positive EV and
  EBITDA, and a **source**. Deal multiples aren't published free, so every one must be traceable.
- **Industry:** Damodaran EV/EBITDA for the industry and region.

The benchmark shows where the deal's entry and exit sit against each source (quartiles, median, a range chart). It
says how far entry is above trading levels (the control premium). It offers one-click exit at the trading or
precedent median, or entry at the precedent median.

**From Markets:** an **LBO** button on any stock's security page opens the workbench already loaded with that
company.
