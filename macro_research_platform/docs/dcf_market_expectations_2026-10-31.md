# DCF market expectations improvements — 31 October 2026

The fundamental estimate now defaults to a normalized 5% mature-market equity risk premium plus country risk. This is an editable research assumption, not a certified current US or European recommendation. A current market-implied premium remains selectable and visible alongside the fundamental lens. Explicit total ERP and discount-rate overrides take precedence. Currency risk-free rates and existing currency perpetual-growth limits remain in place. Geography is not evidence that every security is overvalued.

Market-implied ERP is sourced from Damodaran's US series and is a mature-market proxy for other regions; the new panel exposes its source and observation date, and flags missing observations. It must not be described as a directly observed European ERP. Price proximity is no longer described as a calibration objective. Peer multiples are excluded from the valuation hub's default blend because they import market pricing; users may still opt in.

The FCFF pages now show reverse growth under selected and normalized premium assumptions, a bounded reverse operating-margin calculation, a nine-cell growth/margin grid, terminal-value dependence and parallel +1/+2 percentage-point discount-rate shocks. Rate shocks reprice the captured cash flows along the full rate curve while holding the equity bridge and listing-currency conversion fixed. They are deterministic sensitivities, not confidence intervals. Reverse growth and reverse margin are alternative single-driver explanations, not jointly required operating targets. Missing solutions mean an unbracketed root or unavailable inputs, not zero growth.

The grid preserves the selected first-year growth and cyclical margin-fade path at its centre. Banks and insurers retain their excess-return framework; the new operating-margin panel is specific to FCFF. Excel exports accept the same premium basis and normalized premium as the API.

## Research basis

- [Damodaran current datasets](https://pages.stern.nyu.edu/adamodar/New_Home_Page/datacurrent.html): separate risk-free rates, country risk and implied premiums; keep observation provenance.
- [McKinsey: how companies are valued](https://www.mckinsey.com/featured-insights/mckinsey-explainers/how-are-companies-valued): cash-flow valuation depends on growth, investment and returns on capital.
- [McKinsey: measuring stock-market performance](https://www.mckinsey.com/capabilities/strategy-and-corporate-finance/our-insights/measuring-stock-market-performance): inspect expectations embedded in prices rather than assuming price validates intrinsic value.
- [Kroll cost-of-capital recommendations](https://www.kroll.com/en/reports/cost-of-capital/recommended-us-equity-risk-premium-and-corresponding-risk-free-rates): premiums and risk-free conventions require context and dates. The application's 5% assumption is not presented as Kroll's current recommendation.

## Validation

64 backend tests passed across expectations, refinements, market views, fundamentals, statement basis, three-stage valuation and Excel suites. Added tests reconcile zero-shift values under both discount conventions and stage models, verify monotonic positive-rate shocks, recover reverse drivers at model prices and preserve central-grid assumptions. Two focused frontend tests passed, including missing-root labels. Production build passed; existing large-chunk warning remains. Additional frontend and public-data smoke-check results are recorded below when complete.

This pass improves internal consistency and transparency. It does not establish out-of-sample valuation accuracy or turn provider estimates into audited forecasts.

Final checks: 426 frontend tests across 45 files passed; TypeScript passed; `git diff --check` passed. Live local API smoke checks returned FCFF analyses for MSFT (USD) and SAP.DE (EUR); their grid centres exactly matched selected values, and positive rate shocks reduced both values. Existing research gates correctly remained closed: MSFT lacked a matching cash-flow period, and SAP showed forecast incremental returns above the review threshold. These are successful response/consistency checks, not validated investment conclusions. Local API is running on 127.0.0.1:8000.
