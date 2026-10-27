# DCF — method, calibration and known limits (Oct 2026)

Code: `api/marketdata/dcf.py` (model), `api/marketdata/dcf_excel.py` (the same model as live Excel formulas),
`api/marketdata/security.py` (`comps`, peer multiples). Tests: `api/tests/test_dcf_three_stage.py`,
`test_dcf_refinements.py`, `test_dcf_excel.py`. UI: Markets → VAL.

## How the professionals do it, and what the platform now copies

| Firm / source | Practice | Here |
|---|---|---|
| **Morningstar** (Equity Research Methodology, Oct 2020) | Three stages: explicit forecast (5–10 years); a **fade** in which the return on new invested capital (RONIC) moves to the cost of capital over a period set by the **economic moat** (~1 year no moat, 10–15+ wide; a wide moat = excess returns likely for 20 years, narrow 10); **perpetuity with RONIC = WACC** — growth adds no value | `VALUATION_METHOD = "three_stage"`, `EXPLICIT_YEARS = 10`, `MOAT_FADE_YEARS = 1 / 10 / 20` |
| Morningstar | Cost of equity by **building blocks**: 6.5–7.0% real market return + 2.0–2.5% inflation (9% for average risk) + a systematic-risk step (−1.5 / 0 / +2.0 / +4.5 points) + country risk — not a regression beta on today's bond yield | "Building blocks" lens (`ke_method="building_block"`) |
| Morningstar | **Margin of safety by uncertainty**: buy at a 20 / 30 / 40 / 50 / 75% discount (low → extreme); sell at the midpoint of the symmetric and log-normal premiums (1.25 / 1.35 / 1.55 / 1.75 / 4.0×) | `uncertainty()`: rating from 1-year volatility (one notch up when > 85% of value is terminal) → buy / sell prices on the VAL screen |
| Credit Suisse / UBS **HOLT** | Returns fade toward the corporate average at empirically derived rates; discount rate implied from market prices | Damodaran's market-implied ERP stays the default discount basis |
| McKinsey (*Valuation*) | ROIC **excluding goodwill** measures the underlying business; value-driver formula | Moat and fade start use ROIC ex goodwill |
| Baker & Ruback (1999); Liu, Nissim & Thomas (2002) | Combine peer multiples with the **harmonic mean**; forward P/E is the most accurate multiple | Peer value: harmonic mean of peers inside NM bounds (P/E ≤ 60, EV/EBITDA ≤ 40), ≥ 3 peers |
| Chan, Karceski & Lakonishok (2003); Mauboussin, *Base Rate Book* (2016) | High revenue growth rarely persists | After the consensus years, growth decays with a **2-year half-life** |

## The model (three-stage, default)

1. **Explicit stage — 10 years.** Year 1 and years 2–3 use analyst consensus revenue growth; then growth decays
   toward the long-run rate with a 2-year half-life. Margins move to their target (cyclicals to the through-cycle
   margin in 3 years). Reinvestment blends actual net capex (year 1) with the sales-to-capital rule (by year 5).
   Tax moves from the effective to the long-run rate.
2. **Fade stage — 1 / 10 / 20 years by moat.** NOPAT grows at the long-run rate; reinvestment = growth ÷ RONIC; RONIC
   moves from the firm's median ROIC ex goodwill (capped at 60%) to the cost of capital.
3. **Perpetuity.** NOPAT(N+1) ÷ WACC: new investment earns its cost of capital.

Moat from the data: **wide** — median ROIC − WACC ≥ 10 points and ≥ 3 points in every year but the worst (≥ 3 years);
**narrow** — median spread ≥ 2 points, above WACC in ≥ 60% of years; **none** otherwise; cyclicals at most narrow.

The two-stage Damodaran model (g∞ = risk-free rate, RONIC keeps half of today's excess return) remains a switch.

## Bugs found and fixed in this pass

- **Effective tax missing for 40 of 65 test companies** (every Yahoo-sourced company and some SEC filings): the model
  used a 25% statutory rate. Now the median effective rate of the last three years; a rate persistently ≥ 5 points
  above statutory (oil majors: ExxonMobil 28%, Chevron 35%, Shell 40%, BP 50%) is kept in the long run.
- **Peer multiples**: Microsoft's peers included Palantir (158× earnings), CrowdStrike and Cloudflare; the median
  forward P/E (~65×) implied $1,476 a share and pulled the blended fair value to +65%. Now NM bounds + harmonic mean
  (≈ $488).
- **Growth persistence**: TSMC's and Oracle's 35–40% AI-cycle growth faded linearly over ten years (revenue ×6).

## Calibration — 58 operating companies (US, Europe, UK, Japan, Korea, Taiwan, Hong Kong), value ÷ price

| Model | Median | Median miss | Within ±30% | Within ±50% | Off 2× or more |
|---|---|---|---|---|---|
| Before (two-stage, missing taxes) | 1.02 | 0.33 | 45% | 78% | 7 |
| Two-stage, taxes fixed | 1.07 | 0.32 | 48% | 81% | 5 |
| **Three-stage (default)** | **0.90** | **0.28** | **50%** | **81%** | 6 |
| Three-stage, building-block cost of equity | 0.84 | 0.29 | 50% | 84% | 6 |
| Three-stage, Kroll 5% ERP | 0.76 | 0.36 | 47% | 71% | 15 |

Tried and rejected: 5-year explicit stage (more 2× misses), 3- and 4-year growth half-lives (wider misses), a
concave RONIC fade (no difference), capping the fade's starting RONIC at the explicit stage's incremental return
(hurt Costco, Walmart, Linde — the sales-to-capital rule understates their returns).

**Reading the level.** Morningstar reads the US market as close to fair value in Q4 2026, with seven mega-caps
undervalued. Here the median company is valued 10% below its price, and Nvidia (1.38), Meta (1.13), Alphabet (1.01),
Broadcom (1.02) and Microsoft (0.93) come out at or above their prices — the same direction.

**Still far from the price:** above — Oracle 2.88, TSMC 2.01, BP 1.96, Adobe 1.74, Toyota 1.64 (cross-holdings),
Samsung 1.51; below — Tesla 0.04, Boeing 0.34, Linde 0.46, Walmart 0.47, Costco 0.51, Coca-Cola 0.58. These are the
cases where the market prices something a mechanical model cannot see (option value, a turnaround, decades of
compounding) or disagrees with consensus — adjust the drivers (growth, margin, moat years) for them.

## Sources

- Morningstar, *Equity Research Methodology* (23 Oct 2020): <https://advisor.morningstar.com/Enterprise/VTC/MasterEquityResearchMethodology_Oct2020.pdf>
- Morningstar Q4 2026 US market outlook: <https://www.morningstar.com.au/markets/q4-us-2026-stock-market-outlook-individual-stock-selection-looks-increasingly-important>
- UBS HOLT disclosures (empirically derived fade): <https://research.ibb.ubs.com/openaccess/compliance/HOLT_Disclaimers.pdf>
- Fernandez, 2025 survey of market risk premiums (US 5.5%): <https://www.bvresources.com/articles/bvwire/global-fernandezs-survey-of-2025-risk-premiums-and-risk-free-rates>
- Damodaran implied ERP: <https://www.bvresources.com/articles/bvwire/damodaran-unveils-his-annual-erp-update>
- Kroll recommended US ERP 5.0%: <https://www.bvresources.com/articles/bvwire/kroll-reaffirms-50-us-erp-sticks-with-treasury-risk-free-rate>
- Imam, Barker & Clubb, "The use of valuation models by UK investment analysts", *European Accounting Review* (2008): <https://ideas.repec.org/a/taf/euract/v17y2008i3p503-535.html>
- EU bank cost of equity (EBA): <https://en.paperjam.lu/article/resilient-profits-tighter-margins-at-eu-banks-eba>
- Baker & Ruback (1999), "Estimating industry multiples"; Liu, Nissim & Thomas (2002), "Equity valuation using multiples",
  *Journal of Accounting Research*; Chan, Karceski & Lakonishok (2003), "The level and persistence of growth rates",
  *Journal of Finance*; Koller, Goedhart & Wessels, *Valuation* (McKinsey).

Not investment advice.
