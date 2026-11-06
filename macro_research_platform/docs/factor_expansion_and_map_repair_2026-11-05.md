# Research map repair and expanded factors

## User-facing changes

The primary workspace now has two views: **Research map** for provenance and **Live model** for measured network state. Architecture and shallow baseline inspection are retained inside advanced diagnostics. Specialist encoders are parts of one shared model, not eleven unrelated neural networks. Statistical and shallow baselines remain necessary comparators for detecting when additional complexity fails to improve forecasts.

The research map now uses explicit SVG node/edge identities and a fixed scene rather than a stateful merged graph series. Default grouping removes individual-feature clutter and conventional-task shortcut paths. Individual factors remain searchable, inspectable and expandable; large detailed scenes scroll instead of shrinking every label into an unreadable overview. Keyboard selection, zoom, fit, reset, source links and publication-lag metadata are retained. Configured links and saved measurements stay distinct.

The map now includes the broad panel's individual declared inputs, rather than hiding them all behind an unlabeled PCA connection. Cached panel status is not a claim that every declared series passed the current model's eligibility rules. Expanded factors have their own coverage and missing-data display. Global country fundamentals, company financials/flows, positioning, geopolitics, supply-chain ingestion and historical release vintages remain explicit gaps.

## Research translated into implementation

### Financial conditions and transformations

Kiley's [Federal Reserve paper, FEDS 2020-095](https://www.federalreserve.gov/econres/feds/files/2020095pap.pdf), especially sections on variable transformations and Table 1, compares transformations of rates, spreads and equity variables and uses tree-based methods to select predictors of future unemployment. Its implementation lesson is that transformations and prediction targets matter, not merely the number of variables. We added explicit transformation specifications and stress/expectations blocks; we did not reproduce its fitted FCI or claim its results transfer to our six targets.

The [Chicago Fed NFCI documentation](https://www.chicagofed.org/research/data/nfci/current-data) decomposes financial conditions across risk, credit and leverage using a large indicator set. This motivates including a broad conditions measure alongside narrower stress proxies. Correlated composites can duplicate information, so validation must include leave-one-family-out tests.

### Credit supply and debt-service burden

The BIS [2018 early-warning study](https://www.bis.org/publications/qr-201803/early-warning-indicators-banking-crises-expanding-family) compares credit categories, debt-service ratios and credit gaps across warning horizons. It supports testing financing burdens as distinct from interest rates alone. Our additions include household debt-service burden and the Federal Reserve bank-lending-standards survey, with conservative quarterly publication lags. Household TDSP is not a substitute for the BIS's internationally harmonized total private-sector debt-service series, and banking-crisis results do not establish recession or equity-forecast accuracy.

### Supply chains and international coverage

The New York Fed [GSCPI paper, Staff Report 1017](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr1017.pdf), section 3, first removes demand components from transport/PMI measures using regressions, then extracts a common component with missing-data handling. Its inflation analysis uses local projections. This is why raw ship counts or freight rates should not automatically be labelled supply shocks. GSCPI ingestion and demand-adjusted transport factors remain a clearly labelled gap; the new US import/export price and broad-dollar factors are only partial international transmission proxies.

## Implemented research factor block

Seventeen fixed-schema specifications now cover:

- Financial conditions, stress, high-yield spreads and implied volatility.
- Bank lending standards and household debt-service burdens.
- Central-bank assets, reverse repos and Treasury cash balances.
- Inflation compensation and real Treasury yields.
- Broad-dollar growth, import and export prices.
- Job openings, jobless claims and house prices.

Each specification records its FRED series, transformation and conservative lag. Monthly series use one to three months; the quarterly lending survey uses four months and household debt service six months. These are deliberately conservative approximations, not exact historical release calendars. Revised-history bias is still present. Carry-forward is bounded to two months before lagging, future feature timestamps are excluded, and stale/short optional series are omitted from accepted payloads.

A real refresh accepted **16 series / 6,301 monthly observations**, all with lagged input timestamps through November 2026. `BAMLH0A0HYM2` failed the freshness/history gate and remains missing. It was not replaced with a fabricated value or a weaker threshold. The fixed schema retains every specification and assigns missing-value flags, so provider availability cannot silently reorder model inputs.

The context provider joins the existing six-hour supervisor. The sequence model joins these optional values with the existing missing-aware input matrix and routes each family into the appropriate specialist. Preprocessing still fits on training data only. A new model fingerprint separates the expanded schema from prior checkpoints and prospective forecast cohorts. Existing production promotion gates remain; this is a research expansion, not automatic production adoption.

## Validation and limits

Seventeen backend tests and eleven frontend tests passed, covering causal lags, missing optional inputs, correct value/flag routing, finite preprocessing, graph provenance, grouping, keyboard node selection, zoom/fit and evidence inspection. Type checking and a production build also passed. A bounded real-data inspection fit completed with eleven specialist modules and finite saved outputs. Full chronological research training continues separately; the preview is explicitly labelled and is not a served forecast.

Accuracy is not established by the inspection fit. Before promotion, compare the expanded model with the prior model and simpler baselines on identical purged chronological folds, then run family ablations and prospective evaluation. Report Brier score, log loss, calibration, uncertainty and sample coverage by task/regime. The current targets are US-centric; adding global proxies does not create a globally validated model or eliminate unobservable shocks.
