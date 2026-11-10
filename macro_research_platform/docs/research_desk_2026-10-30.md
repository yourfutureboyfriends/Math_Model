# Research Desk — 30 October 2026

Open Markets → My tools → Research desk, or enter RDESK. Journal links to this desk, and the valuation hub has a Save valuation snapshot button.

## Implemented workflows

1. **What changed:** choose a watchlist or entered portfolio and scan up to 20 names for earnings estimates and SEC filing samples. Successful responses are captured with local observation timestamps. Changes compare with the previous successful capture; the first observation creates a baseline. Fiscal periods are matched by identity, not array order. Filings are matched by document URL. The desk also shows the existing triggered-alert count and links to alert management.
2. **Valuation snapshots:** save the computed primary/dividend models, peer data, selected driver assumptions, methods, currency and supplied source/input-date metadata. Pending selected inputs cannot be saved. Compare two saved runs for the same instrument and currency; inspect full payloads and numeric differences. Differences are not a causal decomposition of fair-value changes, and old snapshots are not rerun against today's inputs.
3. **Thesis tracking:** save evidence URLs, catalysts, invalidation conditions and review dates; edit/reschedule existing theses, record review dates and show overdue reviews. Journal remains the trade/outcome record rather than being replaced.
4. **Portfolio look-through:** enter long-only weights or import the current fund's priced positions read-only. Imports use gross invested base-currency weights, not NAV weights, and reject shorts/unpriced positions. Users review stock/fund classifications. Aggregate direct and published fund holdings; show uncovered fund weight and unallocated weight without renormalizing missing holdings. Source coverage is shown per fund.
5. **Observation archive:** manual captures start at actual collection time. Retain up to 200 observations locally and export observations plus theses. This establishes a prospective collection trail; it is not a pre-existing point-in-time database.
6. **Exposure-aware company calendar:** upcoming reports from the selected watchlist/portfolio appear with known company weights, including published fund look-through when available. Existing ECO remains the economic calendar; automatic causal mapping of macro events to securities is not claimed.

## Data and storage limits

- Records are local browser storage, separated by account and fund keys. They are not server-synchronized, access-controlled server records, or a secure document vault. Clearing browser storage removes them; use export for backups.
- Captures are user-triggered; no unattended monitoring or historical backfill is installed. Capture timestamp indicates response observation, not the original publisher's availability timestamp. Upstream restatements and delayed feeds remain possible.
- SEC filing coverage is incomplete for non-US issuers. Estimate snapshots use current providers and are not broker-level point-in-time consensus histories.
- Fund data generally contains top holdings only. Look-through is one level; nested funds, shorts and derivatives require different analytics. Incomplete holdings are explicitly uncovered.
- Portfolio imports do not modify positions, submit orders or change permissions. Weight classifications may require correction by the user. Events show direct/known exposure rather than inferred investment impact.
- Valuation payloads retain supplied methodology metadata. A pinned executable backend revision and offline historical revaluation engine are not included.
- Scans are cancellable and requests have deadlines; individual feed failures do not erase earlier captures. Browser quota failures are reported.

## Validation

Unit and behavior tests cover missing fund coverage, exposure aggregation, input validation, archive-key separation, timestamps, fiscal-period alignment, numeric comparisons, thesis editing/persistence and saving only completed valuation payloads. Registry-wide pending/unavailable page checks include RDESK. No authenticated business mutations were exercised and no populated browser visual review is claimed.

Final frontend suite: **420 tests passed across 42 files**. Production Vite build passed with existing chunk-size warnings. `git diff --check` passed. The final `tsc --noEmit` check passed.
