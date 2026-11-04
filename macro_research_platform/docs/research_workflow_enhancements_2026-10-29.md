# Research workflow enhancements — 29 October 2026

Implemented on the existing Markets architecture, preserving provider coverage and trading permissions.

- Every Markets source bar can expand into dataset details: provider, observation date, app retrieval time and supplied delay/stale status. Direct read-only response links make payloads inspectable. Unknown freshness is explicitly unknown; retrieval timestamps are not presented as market timestamps.
- ERN adds per-period 30-day EPS revision direction, up/down revision balance, estimate dispersion and analyst coverage warnings. Denominators use absolute EPS, handle losses, and return unavailable for zero/missing values. Formulas and limitations appear alongside the figures.
- Report history is explicitly sorted; beat-rate sample labels count only reports with surprise data. Backend responses include sample size and retrieval timestamp.
- Launchpad offers linked company research (chart, earnings, filings, valuation) and earnings (earnings, analyst ratings, company news, financials) layouts. Presets retain the first existing security or default to AAPL, use the existing colour-group linkage, and persist through the existing layout storage.

These changes do not add licensed consensus histories or a point-in-time archive. Source details only expose metadata actually supplied. Cross-workspace context outside Markets remains a further integration task. Populated browser visual verification has not been completed for this pass.

Validation: seven focused tests pass; production Vite build passes with existing chunk-size warnings; Python syntax check and git diff whitespace checks pass.
