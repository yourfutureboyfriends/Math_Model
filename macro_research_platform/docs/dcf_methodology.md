# DCF — method, assumptions and known limits (Oct 2026)

Code: `api/marketdata/dcf.py` (model), `api/marketdata/dcf_excel.py` (the same model as live Excel formulas),
`api/marketdata/security.py` (`comps`, peer multiples). Tests: `api/tests/test_dcf_three_stage.py`,
`test_dcf_refinements.py`, `test_dcf_excel.py`. UI: Markets → VAL.

## How the professionals do it, and what the platform now copies

| Firm / source | Practice | Here |
|---|---|---|
| **Morningstar** (Equity Research Methodology, Oct 2020) | Three stages: explicit forecast (5–10 years); a **fade** in which the return on new invested capital (RONIC) moves to the cost of capital over a period set by the **economic moat** (~1 year no moat, 10–15+ wide; a wide moat = excess returns likely for 20 years, narrow 10); **perpetuity with RONIC = WACC** — growth adds no value | `VALUATION_METHOD = "three_stage"`, `EXPLICIT_YEARS = 10`, `MOAT_FADE_YEARS = 1 / 10 / 20` |
| Morningstar | Cost of equity by **building blocks**: 6.5–7.0% real market return + 2.0–2.5% inflation (9% for average risk) + a systematic-risk step (−1.5 / 0 / +2.0 / +4.5 points) + country risk — not a regression beta on today's bond yield | "Building blocks" lens (`ke_method="building_block"`) |
| Morningstar | **Margin of safety by uncertainty**: buy at a 20 / 30 / 40 / 50 / 75% discount (low → extreme); sell at the midpoint of the symmetric and log-normal premiums (1.25 / 1.35 / 1.55 / 1.75 / 4.0×) | `uncertainty()`: rating from 1-year volatility (one notch up when > 85% of value is terminal) → buy / sell prices on the VAL screen |
| Credit Suisse / UBS **HOLT** | Returns fade toward the corporate average at empirically derived rates; discount rate implied from market prices | Current market-implied ERP remains a comparison lens; the primary default is an editable normalized premium |
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

The two-stage Damodaran model (RONIC keeps half of today's excess return) remains a switch. The October 28 audit changed the default terminal-growth rule to the lower of the risk-free rate and the existing currency-specific nominal-growth ceiling; `TERMINAL_RULE = "rf"` reproduces the earlier calibration.

## Bugs found and fixed in this pass

- **Effective tax missing for 40 of 65 test companies** (every Yahoo-sourced company and some SEC filings): the model
  used a 25% statutory rate. Now the median effective rate of the last three years; a rate persistently ≥ 5 points
  above statutory (oil majors: ExxonMobil 28%, Chevron 35%, Shell 40%, BP 50%) is kept in the long run.
- **Peer multiples**: Microsoft's peers included Palantir (158× earnings), CrowdStrike and Cloudflare; the median
  forward P/E (~65×) implied $1,476 a share and pulled the blended fair value to +65%. Now NM bounds + harmonic mean
  (≈ $488).
- **Growth persistence**: TSMC's and Oracle's 35–40% AI-cycle growth faded linearly over ten years (revenue ×6).

## Historical in-sample price comparisons — not accuracy validation

The following earlier exploration used 58 operating companies. Price proximity cannot establish intrinsic-value accuracy, and these statistics must not be used to tune a valuation toward expensive market prices. They are retained as historical diagnostics, not current forecasts or out-of-sample results.

| Model | Median value/price | Median absolute price gap | Within ±30% | Within ±50% | Off 2× or more |
|---|---|---|---|---|---|
| Before (two-stage, missing taxes) | 1.02 | 0.33 | 45% | 78% | 7 |
| Two-stage, taxes fixed | 1.07 | 0.32 | 48% | 81% | 5 |
| **Three-stage (default)** | **0.90** | **0.28** | **50%** | **81%** | 6 |
| Three-stage, building-block cost of equity | 0.84 | 0.29 | 50% | 84% | 6 |
| Three-stage, illustrative 5% ERP | 0.76 | 0.36 | 47% | 71% | 15 |

Earlier experiments compared explicit horizons, growth half-lives and RONIC fade shapes. Those in-sample price comparisons do not establish which assumptions are economically correct. The current research framework requires independent operating assumptions, source checks, normalized and market-pricing lenses, and transparent sensitivities.

**Still far from the price:** above — Oracle 2.88, TSMC 2.01, BP 1.96, Adobe 1.74, Toyota 1.64 (cross-holdings),
Samsung 1.51; below — Tesla 0.04, Boeing 0.34, Linde 0.46, Walmart 0.47, Costco 0.51, Coca-Cola 0.58. These historical gaps may reflect data defects, unmodeled economics, different operating expectations or market mispricing. Investigate their drivers; do not adjust assumptions solely to match the share price.

## Sources

- Morningstar, *Equity Research Methodology* (23 Oct 2020): <https://advisor.morningstar.com/Enterprise/VTC/MasterEquityResearchMethodology_Oct2020.pdf>
- Morningstar Q4 2026 US market outlook: <https://www.morningstar.com.au/markets/q4-us-2026-stock-market-outlook-individual-stock-selection-looks-increasingly-important>
- UBS HOLT disclosures (empirically derived fade): <https://research.ibb.ubs.com/openaccess/compliance/HOLT_Disclaimers.pdf>
- Fernandez, 2025 survey of market risk premiums (US 5.5%): <https://www.bvresources.com/articles/bvwire/global-fernandezs-survey-of-2025-risk-premiums-and-risk-free-rates>
- Damodaran implied ERP: <https://www.bvresources.com/articles/bvwire/damodaran-unveils-his-annual-erp-update>
- [Kroll current cost-of-capital publications](https://www.kroll.com/en/reports/cost-of-capital/recommended-us-equity-risk-premium-and-corresponding-risk-free-rates). The application's 5% normalized assumption is not represented as a verified current Kroll recommendation.
- Imam, Barker & Clubb, "The use of valuation models by UK investment analysts", *European Accounting Review* (2008): <https://ideas.repec.org/a/taf/euract/v17y2008i3p503-535.html>
- EU bank cost of equity (EBA): <https://en.paperjam.lu/article/resilient-profits-tighter-margins-at-eu-banks-eba>
- Baker & Ruback (1999), "Estimating industry multiples"; Liu, Nissim & Thomas (2002), "Equity valuation using multiples",
  *Journal of Accounting Research*; Chan, Karceski & Lakonishok (2003), "The level and persistence of growth rates",
  *Journal of Finance*; Koller, Goedhart & Wessels, *Valuation* (McKinsey).

Not investment advice.


## Fundamental and current-market comparisons

The VAL screen and `GET /api/v1/mkt/dcf/{symbol}` now expose `market_views` alongside
all existing valuation, sensitivity, reverse-valuation and outlook fields. The primary
model and Excel export share the normalized/default or explicitly selected premium basis; manual total ERP and discount overrides take precedence. Comparisons reuse the FCFF,
excess-return or dividend engine selected by the primary response.

- Fundamental lens: normalized mature-market ERP, default 5%, configurable with
  `normalized_erp` (decimal, 0–0.15), plus country risk.
- Current-market lens: the available implied mature-market ERP plus country risk.
- Both comparisons use CAPM, retaining currency, industry inputs and explicit operating
  overrides. Manual discount/ERP overrides and building-block selections continue to
  apply to the primary valuation; they do not override these explicitly labeled lenses.
- Optional `country_weights` is a JSON object of operating-country shares summing to one,
  e.g. `{"United States":0.75,"Brazil":0.25}`. Country premiums are weighted relative to
  the US using the existing provider. Missing/unknown country records are rejected.
  Without exposure data the existing home-country premium remains, explicitly labeled.
  These weights affect the comparison only; they do not alter the primary model.

Illustrative scenarios (percentage-point shifts, not fitted predictions):

| Scenario | Growth | Target margin | ERP | Debt cost | ROE (financial firms) |
|---|---:|---:|---:|---:|---:|
| Base | 0 | 0 | 0 | 0 | 0 |
| Expansion | +2 | +1 | −0.5 | −0.25 | +1 |
| Recession | −4 | −3 | +1.5 | +1.5 | −3 |
| Inflation shock | −1 | −2 | +1 | +1 | −1 |

FCFF stresses preserve separate year-one consensus and pass through the existing
reinvestment calculation. Financial models stress ROE rather than operating margins;
dividend models stress dividend growth. Failed cases return an error rather than a
fabricated price. Ranges are scenario extrema, not probability/confidence intervals.
The inflation scenario is a margin/credit stress, not a forecast of inflation or FX.
No arbitrary sentiment multiplier is applied to intrinsic value.

The normalized premium, universal scenario shifts, sector growth persistence and
price-gap convergence still require historical, point-in-time validation. Agreement
with today's price is a diagnostic, not a validation target. These comparisons do
not infer live sentiment, assign scenario probabilities or predict convergence timing.


## Developed-market audit corrections — 28 October 2026

See `docs/dcf_developed_market_audit_2026-10-28.md` for the 115-stock run, saved
before/after outputs, selection rules, research and limits. This was a cross-sectional
input/model audit, not a historical return backtest or optimization to market prices.

- Four quarterly statements must be consecutive (60–120 days apart). Semiannual
  observations cannot be summed as if they were quarters.
- Cash-flow dates must match the income-statement dates. Zero depreciation stays zero.
- If quarterly income is unavailable, use reported annual revenue and EBIT, with
  matching annual capex/depreciation where available. Recalculate capital intensity,
  ROIC and the existing margin assumptions on that base; label it fiscal-year data.
- Preserve the actual statement date. Missing dates remain missing.
- Check period-specific `currencyCode` from Yahoo's raw statement response, which
  yfinance drops when building its DataFrame. Reject a conflict with the quote-summary
  financial currency; converting only the income statement would leave the balance
  sheet on an uncertain basis. Missing metadata is explicitly flagged.
- Default terminal growth now uses the existing sustainable nominal-growth ceiling
  (`TERMINAL_RULE = "gdp"`). These are documented static assumptions, not live GDP
  forecasts. Explicit growth overrides and the existing guardrails remain available.
- `market_views.suitability` exposes accounting/data review requirements for asset
  managers/holding companies, property companies, resource producers, missing
  reinvestment/balance-sheet data, losses and unverified currency metadata. A clear
  check is not a certification of fair value. The VAL screen displays review reasons.

These changes retain the existing FCFF, excess-return and dividend engines. They do
not supply a reserve-based commodity model, a property NAV model, or a full look-through
holding-company valuation. Those cases are flagged for explicit research rather than
silently treated as ordinary recurring operating earnings.

## Cash-flow evidence and research controls — 28 October 2026

The valuation API exposes `calculation_details` and `research_status`: matched historical
capex, depreciation, working capital, SBC and operating cash flow; a reconstructed
period FCFF using modeled taxes; explicit forecast traces; and financing/model review
reasons. Ineligible results retain their numerical estimate but withhold automatic
valuation labels and buy/sell thresholds. Eligibility is not an accuracy probability.

An optional `working_capital_ratio` applies balance-sheet NWC/sales to changes in
forecast sales during the existing net-capex anchor. It cannot be combined with an
explicit aggregate sales-to-capital assumption. Automatic use remains disabled because
development and separate-sample component checks gave mixed results. The Excel export
now reproduces this anchor and the existing cyclical margin fade.

Dated issuer corrections require matching publication, period, currency and revenue
checks. Dated NAV/NTA references remain separate from model blends. See
[research review](dcf_research_reliability_2026-10-28.md) for equations, institutional
sources, rejected hypotheses, sample results and material validation limits.


## Cross-market regression audit — 31 October 2026

`scripts/audit_dcf_matrix.py` selects multiple distinct issuers per country/sector where supported, varies company size and tests present-value/equity/share reconciliation, split invariance, scenario-grid centres and rate stresses. All 50 configured markets and 11 sectors have explicit coverage records. Empty or deferred cells are not passes. Cached observations retain their original capture dates and are distinguished from fresh data. The audit stops submitting work on provider cooldown; `--retry-provider` resumes deferred observations at a conservative request rate.

See `docs/dcf_cross_market_matrix_2026-10-31.md` for the actual run results and coverage limits. Currencies without a configured sustainable nominal-growth ceiling require review; current local yields must not be treated as unqualified perpetual-growth forecasts. Missing pre-revenue financials are described as a model/data limitation rather than misidentifying the company as a non-equity instrument. Government-yield persistence now merges concurrent currency updates and writes atomically.
