# Connected investment workflows — 30 October 2026

Open **Markets → Research desk (RDESK) → Open tools**. Existing Research Desk tabs remain available. The connected tools load as a separate frontend chunk.

## Feature coverage

| Area | Implementation | Practical limits |
|---|---|---|
| Server-backed research | SQLite records scoped to verified account and fund; immutable revision rows, optimistic version checks, restoration as a new revision, current-record export and displayed-history export. Research and valuation saves now use the server. Explicit browser-record migration retains local backups and reports failures. | Current records are limited to 2,000 and 50 MB per account/fund, individual records to 1 MB. History UI shows the latest 200 revisions. Exports are user downloads, not an off-site disaster-recovery service; back up the application database operationally. |
| Valuation change attribution | Ordered substitution of captured FCFF revenue, margin/tax, reinvestment, explicit discounts, terminal value, equity bridge and share/FX/listing-unit factor. Contributions reconcile to saved per-share values with residual checks. No fresh quotes are fetched. | Same instrument, listing currency and projection years are required. Other valuation models retain numeric comparison. Attribution is path-dependent, not a unique causal decomposition; terminal discount effects remain within the terminal group, and share/FX/listing-unit effects are combined. |
| Security identities | Persistent provider/exchange/listing IDs, issuer identifiers when supplied, trading/reporting currencies, share class/ADR ratio when supplied, canonical listing and corporate-action links. Admin-only evidence-backed aliases are audited and used by reconciliation. | Unknown identifiers stay unknown. No issuer merging by name. This is a provider-backed listing registry, not a licensed global security master. Aliases cannot be silently redirected to another listing. |
| Earnings quality | Period-matched cash conversion, cash/earnings gap, SBC intensity, cash after capex/SBC and review flags. User-entered after-tax adjustments require evidence URLs and the same reported period, and produce a reported-to-adjusted income/EPS bridge. | User adjustments are not audited provider consensus and do not change valuation inputs. Missing or mismatched evidence withholds ratios. No automatic adjusted-earnings or dilution history is fabricated. |
| Connected portfolio risk | Current fund positions feed a uniform price/FX stress, indicative margin and stressed-account-equity view; existing exit-liquidity analytics are linked and improved with bounded parallel volume fetching and shared hourly volume caches. Full PORT risk/factor/attribution views remain linked. | Price/FX shocks and margin rates are explicit user assumptions. Unrealized P&L does not become cash; the buffer uses net cash plus signed stressed position values, and is withheld when prices are missing. This layer is linear mark-to-market, not derivative full repricing or a broker margin quote. Missing quotes/volumes stay unavailable. |
| Reconciliation | Broker CSV/text import, grouping by listing and currency, quantity/cash/value/price/FX breaks, split/share-class review hints, export and server save. CASH rows use the existing fund cash calculation where cost-basis evidence is complete. | Market values and FX rates require compatible explicit value currencies. Pricing dates may differ. No positions, cash, corporate actions or orders are modified. GBp and GBP remain distinct. |
| Model validation | Existing tracked forecast/outcome metrics plus user-supplied probability evaluation: training/issuance/outcome timestamp checks, duplicate exclusion, Brier score and benchmark, calibration bins and recent-vs-earlier drift when at least 20 outcomes exist. | Timestamp consistency does not independently verify provenance or certify out-of-sample validity. A 0.5 reference is used when a benchmark probability is not supplied. Missing tracked outcomes are reported honestly. |
| Performance visibility | Bounded process-local route-template request counts, mean/recent p95/max latency, error counts, cache/worker counters, in-flight capacity and background-refresh status; sampled every 15 seconds while the diagnostics panel is open. | Administrator-only because these are process-wide diagnostics. Counters reset on restart; no queries, security symbols, usernames or request bodies are retained by telemetry. |

## Scheduled monitoring

Monitoring is opt-in per account and fund, with 1–10 explicit symbols and an interval from 60 minutes to one week. A one-minute scheduler tick claims due configurations; a maximum of two configurations are considered per tick, with one scheduler job instance per process. No email, chat message or trade is sent.

Users must enable the configuration before queuing a scan. Scans recheck account status, fund membership and the person's current fund position. Read-only or disabled access stops the monitor. Stale responses do not replace baselines. Changed estimates and filing samples create versioned records and events in one transaction; unchanged repeats are skipped, while a genuine return to an earlier estimate is still recorded. Latest baselines use fixed record IDs and retain earlier observations as revisions.

Run a single active scheduler for this local deployment. Multi-worker/distributed deployments need a dedicated job coordinator and stronger long-running leases. Vendor-level timeouts and rate limits still apply. Missed intervals are coalesced; no retrospective history is invented.

## Permissions and migration

All workflow reads are included in the existing protected-read middleware, including password/MFA onboarding checks. Route handlers independently require a verified member role. Writes retain existing read-only-position restrictions; global listing aliases and process diagnostics require administrators.

Previously saved browser records are **not deleted or silently migrated**. Use the import button in Records & monitoring. Existing server IDs are left unchanged. Conflicting updates receive HTTP 409 and require reloading; the UI does not silently overwrite colleagues' or other devices' edits.

## Verification

Coverage includes storage isolation and revisions, conflicts, actual authentication/fund middleware, read-only and onboarding restrictions, monitor deduplication and role changes, stale evidence, valuation reconciliation, currency compatibility, forecast timing/calibration boundaries, CSV parsing, thesis persistence, server capture writes and registry-wide page mounts. See final results below.

A missing Request import in the metrics middleware was caught during startup verification and corrected before the successful API restart. Live unauthenticated research/performance requests return 401; public model metadata responds successfully. A fresh browser preview reaches the existing login screen; authenticated browser walkthroughs are not claimed. No real broker holdings were imported and no trades or monitor configurations were created on behalf of the user.


Scenario account-equity reference: [Federal Reserve Regulation T definitions](https://www.federalreserve.gov/frrs/regulations/section-2202-definitions.htm). The app uses a user-defined stress and margin model, not a claim that its assumed rates reproduce regulatory or broker requirements.

## Final checks

- Backend regression run: **146 passed, 1 live-network test deselected**. Includes real JWT/fund middleware tests on isolated temporary databases.
- Frontend suite: **425 passed across 44 files**, using four workers to avoid resource-contention timeouts. An earlier parallel build/test run exceeded two existing five-second mount-test limits; the bounded run passed without increasing test timeouts.
- Production Vite build passed; existing large-chunk warnings remain.
- Python compilation and `git diff --check` passed.
- Server-side monitor queue writes are offloaded from the API event loop and checked transactionally.
- Final TypeScript `tsc --noEmit` check passed.
- The enabled/disabled monitor queue and administrator diagnostics path were rechecked through the real HTTP middleware after the queue-write refactor.
- The final API was reloaded; protected research/diagnostics endpoints return 401 without a token through both direct API and app-proxy access.
