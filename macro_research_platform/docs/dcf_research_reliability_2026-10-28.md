# DCF research and reliability review — 28 October 2026

## Outcome

The existing FCFF, financial excess-return and dividend engines are retained. Improvements focus on accounting consistency, inspectable calculations, method suitability and testable forecast assumptions. No claim of universal valuation accuracy follows from this work.

The original audit covers 115 companies across all 23 developed listing markets, all 11 sectors and four company-size groups. A further 41 previously unused stocks were selected before fetching their financial outcomes. This is research across 156 stocks, not 156 successful historical investment backtests.

## Research and implementation decisions

[UBS HOLT](https://www.ubs.com/global/en/investment-bank/insights-and-data/global-research/holt.html) emphasizes comparable accounting and return fade. We strengthened period/currency matching and expose the existing fade assumptions. This does not reproduce HOLT's proprietary accounting adjustments or algorithms.

[Morgan Stanley Counterpoint Global's reinvestment research](https://www.morganstanley.com/im/publication/insights/articles/article_theneglectedvaluedriver_ltr.pdf) informed separate capex, working-capital, acquisition and stock-compensation diagnostics. Counterpoint Global is investment-management research; these are public research principles, not a private investment-banking model. [Its ROIC paper](https://www.morganstanley.com/im/publication/insights/articles/article_returnoninvestedcapital.pdf) also supports checking growth against capital requirements and incremental returns.

[AQR's value research](https://www.aqr.com/-/media/AQR/Documents/Journal-Articles/JPM-Fact-Fiction-and-Value-Investing.pdf?sc_lang=en) and [Robeco's value-factor discussion](https://www.robeco.com/en-int/glossary/quantitative-investing/value-factor) support using multiple valuation perspectives and investigating cheapness alongside business quality and risk. They do not justify a sentiment multiplier on intrinsic value. Existing market/normalized discount-rate comparisons remain separate lenses, with no assigned scenario probabilities.

## Calculation breakdown

For an ordinary operating company:

- NOPAT = EBIT × (1 − modeled tax rate).
- Net capital expenditure = capital expenditure − depreciation and amortization.
- Working-capital investment = negative of the reported cash-flow change in working capital.
- Reconstructed period FCFF = NOPAT − net capital expenditure − working-capital investment.
- Forecast FCFF = forecast NOPAT − forecast reinvestment.
- Enterprise value = discounted explicit FCFF + discounted terminal value.
- Equity value follows the existing cash, debt and nonoperating-asset bridge; per-share value uses the existing share/currency conversion.

Reconstructed FCFF uses a modeled tax charge, not verified cash taxes. CFO minus capex minus SBC is displayed separately as a cash-generation proxy; it is not FCFF. EBIT already expenses SBC, so FCFF does not deduct it again. The model does not yet forecast a complete dilution schedule.

Matched evidence requires the same period/date and currency and a consistent revenue base. Capex/depreciation discrepancies are rejected rather than silently combined. Historical medians exclude future periods. Missing components remain missing. Acquisitions, weak cash conversion, unusually high incremental returns, cumulative projected cash deficits and terminal dependence generate review reasons.

Optional forecast working capital uses a balance-sheet intensity proxy:

`NWC = current assets − cash and short-term investments − current liabilities + current debt`

`working-capital investment = NWC/sales × change in forecast sales`

This proxy is imperfect: tax balances, leases and other classifications may require issuer-specific adjustments. During the existing early-year anchor, net capex and optional working capital fade into aggregate growth/sales-to-capital reinvestment. Working capital is not added again after that fade. An explicit aggregate sales-to-capital override cannot be combined with an explicit working-capital override.

## Forecast evidence: accepted and rejected changes

Saved inputs and evaluation files are under `data/processed/dcf_research_2026-10-28/`.

| Reinvestment component check | Usable pairs | Baseline median absolute error / revenue | Candidate median | Baseline mean | Candidate mean |
|---|---:|---:|---:|---:|---:|
| Development: growth-linked NWC | 79 | 3.040% | 3.045% | 5.080% | 5.263% |
| Separate 41-stock selection: growth-linked NWC | 28 | 3.167% | 2.795% | 5.375% | 5.196% |

The separate selection lowered median component error by about 11.7% and mean error by about 3.3%, but improved only 13 of 28 individual pairs. Development results were worse. This mixed evidence does not establish a reliable general improvement; automatic working-capital forecasting remains disabled. Users may inspect and explicitly apply the assumption.

An earlier candidate that charged a historical cash-working-capital/revenue ratio annually also worsened development error: median 3.624% to 4.218% across 94 pairs. It was rejected.

These checks use prior annual observations to forecast a later annual reinvestment component, holding the revenue forecasting rule constant. Statements are currently available/restated histories, not archived publication-time vintages. This is not an out-of-sample stock-return test. [A backtesting protocol](https://people.duke.edu/~charvey/Research/Published_Papers/P138_A_backtesting_protocol.pdf) explains why repeatedly tuning against held-out outcomes undermines validation; the mixed result is preserved rather than tuned away.

## Verified issuer reconciliations

The dated, source-linked registry is `config/valuation_evidence.json`.

- Lukfook FY ended 31 March 2026: [issuer results](https://www.lukfook.com/en/category/news-press-releases/post/lukfook-group-0590-announces-annual-results-for-the-year-ended-31-march-2026) report HKD17.205242bn revenue and HKD2.648054bn operating profit. The provider supplied HKD3.441521bn operating income. A tightly guarded period/currency/revenue reconciliation retains both values and the source. In the frozen audit, value/price falls from 5.26 to 3.88; this remaining extreme requires research, not an automatic buy label.
- Investor AB: [September 2026 reporting](https://www.investorab.com/investors-media/reports-presentations/2026) gives adjusted NAV of SEK411 per share. The bank-style model remains flagged as unsuitable for a holding-company conclusion; the dated NAV is a separate reference.
- VGP: [H1 2026 reporting](https://www.vgpparks.eu/content/uploads/2026/08/VGP_Press_Release_H1-26_ENG-1-1.pdf) gives EPRA NTA EUR97.1 and IFRS NAV EUR105.33 per share. These dated references are displayed separately and excluded from automatic blending.

These are specific verified facts, not comprehensive issuer normalization. Asset values can change after publication. NAV references are not price targets.

## Final audit and verification

Frozen v2 outputs are `data/processed/dcf_audit_2026-10-28/fundamental_v2.json`, `.csv` and `_summary.json`.

- 114 numerical results; one reporting-currency transition blocked pending reconciliation.
- Median value/price 1.072; 26 numerical estimates outside 0.5–2 times price. Market-price proximity is not ground-truth valuation accuracy.
- 83 results require research; 31 pass the implemented model/data checks; one is blocked. Passing checks is not investment approval or a correctness probability.
- Cash-flow evidence matches 86 periods, with complete FCFF reconstruction available in fewer cases. Missing evidence remains visible.
- Funding deficits are checks against reported cash, not a full financing forecast; credit access, covenants, minimum cash and refinancing terms remain unmodeled.
- Dividend discount rates now follow dividend/trading currency when reporting currency differs. Explicit zero tax and zero risk-free inputs remain valid.
- Excel exports now reproduce early capex anchoring, optional working capital and accelerated cyclical margin fade. The earlier export could disagree with the API on these paths.
- 65 targeted Python tests pass. Frontend TypeScript validation (`tsc --noEmit`) also passes. Live input smoke checks covered MSFT, Lukfook, Investor AB and VGP.

The platform now withholds automatic undervalued/overvalued and buy/sell thresholds when research eligibility fails, while retaining the numerical estimate and explaining the reason. Forecast traces, source evidence and issuer references are visible in the valuation screen and the Excel evidence sheet.

Reliable investment validation still requires archived financial vintages, delisted companies, publication lags, corporate actions, FX consistency, transaction costs and a precommitted return-evaluation protocol. Resource reserves, property NAV and holding-company look-through analysis remain specialist tasks rather than silently interchangeable DCF methods.
