# Research priorities for the platform — 3 November 2026

## Conclusion

Prioritize data lineage, historical reproducibility and decision workflows before adding more standalone pages. The platform already exposes 122 Markets functions plus macro, trading, quant and PE capabilities. Feature labels alone understate what is missing: several existing tools need stronger evidence and less approximate inputs.

This review compared current source files and audit notes with official Bloomberg, LSEG, S&P Global, SEC, OpenFIGI, Global Fishing Watch, EUROCONTROL and US Bureau of Transportation Statistics documentation. Vendor product pages establish advertised capabilities, not independently proven accuracy. The priorities below are engineering judgments from those comparisons, not measured investment alpha.

## Existing capabilities to extend, not duplicate

- Portfolio analytics already includes Brinson attribution, base-currency benchmark analysis, liquidity risk, FIFO lots, TCA and idea tracking (`api/handlers/portfolio_analytics.py`).
- Research Desk now loads and saves versioned server records (`frontend/src/lib/serverResearch.ts`, `ResearchDesk.tsx`). The older October 30 document's browser-only-storage description is no longer the complete implementation.
- Financial statements, estimate revisions, Form 4/13F, filing search, valuation snapshots and reverse expectations already exist.
- Vessel intelligence already includes sanctions, registry information and some completed port calls; the map is not merely anonymous position dots.
- OpenFIGI is already used for selected CUSIP/ISIN mappings. A cross-platform, historically effective security master is a larger requirement than adding another mapping call.

## Ranked work packages

### 1. A consistent observation and calculation record

**Gap:** source/freshness fields vary by endpoint; response capture timestamps do not establish original information availability. Public/provider financial histories can be revised.

**Add:** a standard record with provider, source document/field, instrument identity, units, quote/report currency, fiscal period, observation time, release/filing time where available, retrieval time, revision version, transformation and quality flags. Store immutable raw responses with retention rights and bounded storage. Record model/code version and input IDs for saved calculations.

**Acceptance:** a saved valuation or macro signal can be rerun with exactly its saved inputs and model version; source/availability dates remain unknown when not supplied. A corrected value creates a new version rather than silently overwriting history.

**Feasibility:** largely internal engineering. Historical availability cannot be manufactured by backfilling today's response.

### 2. Permanent security identities and corporate-action continuity

**Gap:** ticker/provider-specific mappings are distributed. Tickers can change, and one issuer can have multiple exchanges, currencies, share classes and depositary receipts.

**Add:** issuer → share class → listing hierarchy; FIGI/ISIN/MIC and existing provider IDs; currency/minor-unit rules; ADR ratios where sourced; dated symbol changes and corporate actions. Preserve discontinued listings and historical index membership where available.

**Acceptance:** one issuer is not counted twice in exposure; a delisting or ticker change does not detach its earlier financials/trades; splits do not create false returns or share-issuance signals.

**Feasibility:** mapping can start with existing OpenFIGI integration; comprehensive action histories and point-in-time universes may require licensed sources.

### 3. Reconciliation and coverage controls on important fields

**Gap:** successful provider responses and passing unit tests do not establish externally correct values.

**Add:** compare selected financial/price fields against filings or an independent source after matching dates, units, accounting basis and currency. Classify disagreements, show evidence and maintain a correction history. Measure expected-versus-observed universe coverage and provider error/freshness trends.

**Acceptance:** a financial discrepancy explains both source values and their bases; unresolved conflicts are visible. Real price jumps are not automatically overwritten by a simplistic outlier rule.

**Feasibility:** start with a representative US/UK/Europe/Japan/Hong Kong universe and core fields; scale only after unit/fiscal mapping works.

### 4. Point-in-time fundamentals and estimate research

**Gap:** current estimates and prospectively captured observations are not a broker-level historical consensus database. Coverage outside SEC filings is uneven.

**Add:** scheduled prospective estimate snapshots with fiscal-period identity, contributor counts/dispersion when supplied, revision breadth, guidance changes and filing/publication timestamps. Separate original financial statements from restatements. Provide an explicit historical availability cutoff for research and backtests.

**Acceptance:** a backtest cannot read a forecast or financial restatement before its availability date. Fiscal-year rollovers cannot appear as estimate revisions. Prospective history is labelled from its actual collection start.

**Feasibility:** prospective capture is implementable; deep global consensus history such as I/B/E/S is a data entitlement/purchasing decision. SEC APIs cover US filer submissions/XBRL, not complete worldwide comparable fundamentals or consensus.

### 5. Explain changes in valuations and measure forecast skill

**Gap:** saved model outputs and numeric differences are not a causal explanation of a change in fair value.

**Add:** a value bridge separating financial updates, growth/margins, reinvestment, discount rates, FX and share count. Use a disclosed decomposition method with an interaction/residual term or order-independent allocation. Add walk-forward model evaluation by sector/region with naive baselines, sample counts and forecast-horizon matching.

**Acceptance:** bridge components reconcile to total value change; decomposition assumptions are visible. Scenario ranges are not called statistical confidence intervals without calibration. Report poor/out-of-sample performance rather than silently fitting new rules to the test sample.

**Feasibility:** extend valuation snapshots and existing model-validation workflows. More scenarios alone do not prove improved valuation accuracy.

### 6. Tracker events linked to relevant exposures

**Gap:** position counts and inferred cargo are not measured throughput or issuer revenue. Existing port calls/sanctions need a longitudinal event workflow and reliable baselines.

**Add — shipping:** route/port arrival and departure histories, dwell-time distributions where data supports them, rerouting, vessel identity changes and AIS-gap review. Compare a port/route with its own seasonally comparable history. Link events to documented terminal/operator/commodity/portfolio exposures.

**Add — aviation:** official regional flight statistics and monthly carrier/route passenger/freight data to complement receiver counts; compare observed traffic with stable-region baselines. Distinguish operated flights, scheduled capacity and actual passengers/cargo.

**Acceptance:** event alerts show observation windows, sample coverage, source and the evidence for the company link. AIS gaps are not labelled intentional concealment; aircraft payload capacity is not labelled actual cargo.

**Feasibility:** GFW Events supports port visits, loitering, certain encounter types and gaps, subject to datasets/access/caveats. EUROCONTROL offers European traffic statistics. BTS T-100 supplies monthly reported traffic with geographic/reporting limits. Complete global real-time cargo manifests and ownership require other data sources, often licensed.

### 7. Upgrade existing execution and liquidity analytics

**Gap verified in code:** current TCA describes its VWAP proxy as session (high + low + close)/3 and converts shortfall using the latest FX rate. These are useful approximations but are not trade-time VWAP or historical-FX execution analysis.

**Add:** timestamped decision/arrival marks, contemporaneous quotes and spread, actual intraday volume-weighted benchmarks, historical FX, commissions/fees and participation. Break out spread, timing and market impact only when the observations support that separation.

**Acceptance:** TCA labels observed versus proxy marks per fill; costs reconcile in trade currency and fund base currency; missing historical inputs do not become zero costs.

**Feasibility:** historical FX and internal decision timestamps first; accurate global intraday/order-book coverage requires appropriate feed entitlements or prospectively recorded entitled data. Existing liquidity estimates should not be advertised as full-depth liquidation capacity.

### 8. Exposure-aware, evidence-linked change inbox

**Gap:** price alerts, thesis tracking, earnings calendars and captures exist separately; a change still requires manual interpretation across pages.

**Add:** an inbox joining material source changes, portfolio exposure, thesis invalidation rules and review status. Examples: a filed debt maturity changed, earnings guidance fell, or a documented supply route experienced a disruption. De-duplicate related headlines and let analysts mark evidence reviewed or reject the inferred link.

**Acceptance:** every alert links to original evidence, before/after facts and the rule that fired. It does not claim an event caused a price move merely because the dates coincide. No automatic trading or outbound messaging is implied.

**Feasibility:** internal workflow work after standard event/observation IDs; relevance is more important than increasing alert volume.

## Suggested sequence

1. Establish observation contracts, identities and reconciliation for a bounded representative universe.
2. Add reproducible valuation/estimate history and explicit model versions.
3. Deliver the exposure/change inbox and company-linked tracker events.
4. Expand licensed consensus/intraday/global filings only after testing coverage, redistribution/storage rights and workflow value on a small sample.

Do not prioritize another large dashboard catalogue, universal sentiment scores, inferred hidden institutional transfers or additional decorative map animation. These do not address the main reliability gaps identified here.

## Primary references

- Bloomberg PORT: https://professional.bloomberg.com/products/bloomberg-terminal/portfolio-analytics/
- LSEG company data: https://www.lseg.com/en/data-catalogue/company-data
- LSEG quant-research data brochure (I/B/E/S point-in-time snapshots): https://www.lseg.com/content/dam/data-analytics/en_us/documents/brochures/lseg-data-for-quant-research-brochure.pdf
- LSEG corporate actions and identifier continuity: https://developers.lseg.com/en/article-catalog/article/workspace-corporate-actions-content-set-guide
- S&P Capital IQ Pro document intelligence: https://press.spglobal.com/2024-11-12-S-P-Global-Transforms-S-P-Capital-IQ-Pro-Experience-with-the-Launch-of-New-Generative-AI-Powered-Capabilities
- OpenFIGI mapping documentation: https://www.openfigi.com/api/documentation
- SEC submissions and XBRL APIs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- GFW Events API: https://globalfishingwatch.org/our-apis/documentation/docs/v3/events
- EUROCONTROL Aviation Intelligence: https://www.eurocontrol.int/prudata/
- BTS T-100 overview: https://www.transtats.bts.gov/DatabaseInfo.asp?QO_VQ=EEE
- LSEG market-depth extraction: https://developers.lseg.com/en/api-catalog/refinitiv-tick-history/refinitiv-tick-history-rth-rest-api/tutorials/rest-api-tutorials/rest-api-tutorial-5--on-demand-market-depth-extraction

Research only: no vendor subscription, new integration, external communication or automated monitoring was activated.
