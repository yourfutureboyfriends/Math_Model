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
