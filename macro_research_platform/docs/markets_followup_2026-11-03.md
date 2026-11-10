# Markets follow-up — 3 November 2026

This pass addresses mixed trading calendars and retained tracker responses. Existing page structure and provider integrations are retained.

## Analytics

Correlation no longer drops weekday instruments because a weekend-traded asset expands the date index. Mixed calendars use weekday price endpoints without filling absent quotes; weekend moves are included in the Friday-to-Monday interval. All-weekend-traded samples use calendar days and a 365-day annualization basis. Weekly calculations retain 52 periods. Each cell still requires 20 paired return observations; the matrix exposes its calendar and sample counts. Non-synchronous closes and partial latest periods remain limitations.

Comparison risk uses each instrument's native observed daily series, preserving valid Friday-to-Monday returns. Gaps beyond one business day (weekday series) or calendar day (weekend-traded series) are omitted conservatively, including holidays that cannot be distinguished from unavailable observations. Risk sample counts and annualization are inspectable. Correlations use shared calendar endpoints and their own paired counts. Currency conversion is not implied; returns remain in listing currency. Sharpe still explicitly assumes a zero cash rate.

The shared heatmap now treats non-finite, out-of-range and absent coefficients as unavailable. A near-zero coefficient describes little linear co-movement in the sample, not statistical independence. Negative correlation is not labelled as a guaranteed hedge. Tooltips can display paired sample counts.

## Trackers

Vessel freshness is checked before deduplication. A valid recent receiver report wins; once it expires, a historical AIS cell can reappear if available, with historical styling and unknown navigation state. Counts and type filters now use the same valid observations as the map. Unchanged selection arrays are reused to avoid clock-only map redraws. An Unknown navigation-state filter is available.

Aircraft military/emergency counts likewise follow current valid positions. Traffic history shows an explicit observation timestamp and UTC chart labels. Tracker overview age is labelled snapshot age rather than response age.

## Validation

- Backend selected regression suites: 118 passed (two existing Pydantic deprecation warnings).
- Frontend suite excluding live API integration: 534 passed across 60 files.
- Final focused tracker/provenance/heatmap run: seven passed.
- Live SPY/BTC-USD correlation: both symbols retained, weekdays basis, 114 cross-paired observations in the verification sample.
- Final TypeScript check and production build passed after the last edits. Vite retains the existing large-chunk warning.

A passing deterministic test is not independent verification of provider accuracy. Licensed feeds, historical receiver coverage metrics, base-currency analytics and release-vintage metadata remain separate integrations.
