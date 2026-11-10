# Global maritime and aviation coverage — 4 November 2026

## Diagnosis in this program

The recent ship view consumes AISStream community receiver reports. More requests cannot manufacture coverage where the network has no reception. The separate GFW historical layer can extend geographic reach, but it is delayed presence on a grid, not live satellite fixes. The saved snapshot inspected locally was dated 2026-10-30 (221,381 vessel records); old snapshot metadata did not record failed areas. The preceding overhaul now preserves cell centres and records partial build coverage.

Flight positions combine OpenSky with community receiver queries around 60 hubs. Project .env has OPENSKY_CLIENT_ID but no OPENSKY_CLIENT_SECRET; the code requires both for authenticated access. This is a file-configuration observation, not an inspection of the running process's environment. More OpenSky quota would improve cadence, not its physical receiver footprint.

Found and fixed two concrete regional aviation defects: the background sweep accepted only `aircraft` arrays whereas the local-area path already supported `aircraft` and `ac`; and a failed world baseline could prevent fresh regional results from being returned. The sweep now accepts either envelope, requires an actual position-age field, rejects invalid/expired fixes, and expires retained results on read. Baseline outages now return explicitly partial regional data without recording it as a comparable global activity history.

Sequential hub requests can also produce uneven revisit times when individual requests time out. Broadening the hub list alone is not a coverage solution. A later acquisition scheduler should expose per-hub request success, last successful position time, returned unique aircraft and revisit delay, and use bounded concurrency within each provider's limits.

## Primary-source findings

- Kpler documents a maritime feed combining terrestrial, roaming/dynamic and satellite AIS. Its message documentation exposes collection type. Trial actual latency and completeness around Chinese ports and open-ocean corridors before choosing a contract.
  https://www.kpler.com/product/maritime
  https://servicedocs-sm.kpler.com/messages-api/
- Shipxy's official API describes shore, satellite and BeiDou data integration, geographic queries, port information and vessel tracking. It is a relevant China-focused candidate, not yet independently benchmarked against our regions.
  https://api.shipxy.com/
  https://apidocs.shipxy.com/
- VesselFinder documents terrestrial and separately priced satellite AIS records, plus area and vessel-list products. Targeted port/fleet subscriptions may be more economical than repeatedly buying worldwide records; exact economics depend on the trial and commercial terms.
  https://www.vesselfinder.com/vessel-positions-api
  https://api.vesselfinder.com/docs/
- Aireon documents global space-based ADS-B for compatible aircraft. FlightAware Firehose documents streaming tracking from multiple source types. Evaluate source entitlements, geographic permissions, latency and redistribution/storage rights explicitly.
  https://aireon.com/wp-content/uploads/2024/01/AireonINSIGHTS.pdf
  https://www.flightaware.com/commercial/firehose/documentation
- Flightradar24's website combines satellite and terrestrial sources. Its API FAQ explicitly cautions that website data/features are not necessarily included in the public API. Do not infer satellite API access from the consumer map.
  https://www.flightradar24.com/how-it-works/
  https://fr24api.flightradar24.com/docs/faq
- GFW presence is delayed (approximately 96 hours per its key-concepts documentation), not current global ship positions. Its commercial-use FAQ says ordinary terms are insufficient for commercial products and private internal uses supporting commercial services; permission must be resolved for a fund deployment.
  https://api-doc.globalfishingwatch.org/our-apis/documentation/docs/v3/general-api-doc/key-concepts
  https://globalfishingwatch.org/faqs/can-i-use-global-fishing-watch-apis-for-commercial-purposes/
- IMF PortWatch supports satellite-based maritime trade estimation. Use port calls and import/export volume estimates for economic monitoring, with model/source/date labels, rather than equating visible markers with trade.
  https://www.imf.org/en/publications/wp/issues/2026/05/19/nowcasting-country-level-trade-estimates-using-imf-portwatch-576176

## Recommended implementation sequence

1. Retain separate recent-observation and delayed-history views; add regional source-health and report-age summaries. Unknown coverage must remain unknown, never a zero-traffic signal.
2. Restore complete OpenSky credentials through normal configuration and verify successful authentication; show actual refresh times. Do not assume the missing project-file secret proves it is absent from the process environment.
3. Benchmark Kpler and/or Shipxy, plus a lower-volume VesselFinder offer, for Shanghai/Ningbo, Qingdao, Tianjin, Shenzhen/Guangzhou, Singapore, Malacca, Hormuz, the Indian Ocean, southern Africa and South America.
4. Benchmark FlightAware/Aireon-backed commercial data and, if useful, another terrestrial network for Shanghai, Beijing, Guangzhou/Shenzhen, Hong Kong, Zhengzhou, Singapore, Delhi/Mumbai, Gulf hubs, East/West/South Africa and South America. A public API with an impressive website must still demonstrate the required data-source entitlement.
5. Integrate the winning providers server-side with source/observation/receipt timestamps, source-type and accuracy metadata, MMSI/IMO or ICAO24 identity matching, age-aware merging, budget caps and recorded outages. Store conflicting observations rather than silently choosing the geographically plausible one.
6. Evaluate at least two weeks of samples: median and 95th-percentile report age, unique identities against an independently sourced reference, dropout duration, false jumps, port/airport arrivals and departures captured, cost per usable observation, and seasonal/time-of-day differences. No source has been independently benchmarked yet.
7. Build trade indicators separately: Chinese port calls and estimated import/export tonnage; freighter movements and airport cargo tonnage/capacity. Raw aircraft counts include passengers, and neither aircraft nor vessel counts establish the cargo actually carried.

No paid feed was purchased, no vendor contacted, and no API credentials were changed. Paid-provider integration depends on access and demonstrated coverage. Remaining live Quant/PE page checks and final tracker screenshots are still interrupted by the in-app browser transport failure; automated rendering is not a substitute for that verification.

## Validation of the accompanying fixes

The final backend tracker and market-function suite passed 78 cases. Frontend ship/flight evidence fixtures passed six cases; an earlier wider Markets rendering run passed 243 cases. The updated UI production build passed before the final small type annotation and additional test fixture corrections; final TypeScript validation is recorded separately when complete. No paid-source coverage has been asserted or simulated.

Final TypeScript check passed. Server-side changes require the running backend to reload before they affect live responses; the existing backend was launched outside this session and was not restarted during this research. Browser verification remains incomplete because the browser transport disconnected.
