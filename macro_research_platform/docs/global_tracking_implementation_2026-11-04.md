# Global tracking implementation — 4 November 2026

The ship/flight pages now separate observations, source availability and trade estimates. No new licensed vendor is enabled by default, and no satellite entitlement is implied.

## Implemented

- Regional ADS-B sweeps query hubs concurrently while retaining each provider's request interval. Position age is required; stale local records expire. A regional supplement survives failure of the OpenSky world snapshot.
- Optional Shipxy v3 regional polygon requests, Kpler Maritime 2.0 GraphQL queries and VesselFinder contracted-area queries. Small port catchments, bounded pagination, acquisition time budget, cached snapshots and persistent atomic daily request caps. Opening the map does not purchase ship observations.
- Optional TLS FlightAware Firehose position stream with validated regional bounds. Requires Firehose entitlement; Aireon access requires the appropriate vendor subscription. Estimated/unknown source codes are excluded from the observed-position layer. Daily cap counts stream connections, not messages or monetary cost.
- Deduplication selects the newest valid report by vessel/aircraft identifier, retaining report time and source. No inferred cargo manifest or coverage-completeness percentage.
- Coverage panel includes China, Southeast Asia, India, the Gulf, Africa and Latin America, report-age statistics and provider readiness. Empty catchments mean unknown coverage. Flight coverage counts retained supplement reports, not an extra OpenSky world query.
- Acquisition evidence retains 14 days of sample results. These are acquisition diagnostics, not independently benchmarked detection rates.
- PortWatch trade panel separates estimated imports, exports and port calls. Full 28-calendar-day windows, dated 364-day comparisons, duplicate suppression and null-preserving terminal aggregation. Partial responses suppress comparisons. Terminal inventory completeness is unverified.

## Configuration

Use the commented section in `.env.example`; keep actual credentials server-side. For each licensed feed set its credentials, `TRACKING_<PROVIDER>_ENABLED=true`, and a positive `TRACKING_<PROVIDER>_DAILY_REQUESTS`. Default budgets are zero. Request count caps do not guarantee a monetary spending cap: vendor contracts may charge by vessel, message, bandwidth or area. Confirm entitlements and rates with the vendor before enabling.

Ship observations are acquired only through the explicit regional sample control. VesselFinder uses the area configured in its subscription, regardless of the selected port. Firehose starts on demand when the flight snapshot/coverage is requested; defaults to bounds `5 60 55 145` and can be changed server-side. The community feeds continue independently.

OpenSky needs both OAuth client ID and secret for authenticated access. Provider readiness reports credential completeness and whether authentication actually succeeded in this process; it never exposes credentials.

## Public documentation used

- [Shipxy area search v3](https://apidocs.shipxy.com/475744022e0)
- [Kpler Maritime 2.0](https://servicedocs-sm.kpler.com/maritime-2-0/)
- [VesselFinder live data](https://api.vesselfinder.com/docs/livedata.html)
- [FlightAware Firehose](https://www.flightaware.com/commercial/firehose/documentation)
- [IMF PortWatch](https://portwatch.imf.org/)

## Validation and limits

88 focused backend tests, 8 tracker/coverage frontend tests and 333 page-render checks passed. TypeScript and production build passed; existing large-chunk warnings remain. Vendor adapters were tested using contract-shaped fixtures, not licensed live accounts. Live community AIS verified around Hong Kong/Shenzhen, Singapore, Cape Town and Santos; Shanghai/Ningbo remained unknown. Broader coverage needs an entitled vendor feed and subsequent real-data benchmarking.

Live flight verification: the page displayed 523 regional updates across 60 hubs, including 420 aircraft absent from that OpenSky snapshot. Regional observations included Beijing, Tianjin, Hong Kong/Shenzhen, Singapore, Dubai, India, Cape Town, Johannesburg, Sao Paulo and Panama. These are one-session sample counts, not stable coverage rates. No browser console errors were recorded during the flight check. The public PortWatch query timed out in live validation; its data remains unverified live. Quant navigation and five PE tools were checked for page-level horizontal overflow at 915px; none was detected. Some asynchronous PE results were still loading, so this does not claim complete visual validation of every loaded result.
