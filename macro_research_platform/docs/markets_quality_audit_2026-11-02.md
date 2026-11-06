# Markets data and usability audit — 2 November 2026

## Coverage and meaning

The current registry contains **122 functions**: 37 security pages, 34 market pages, 17 rates/FX pages, 12 economy/policy pages, 8 alternative-data pages, 9 research pages and 5 personal tools. The regenerated inventory resolves every function to its route and local component graph, scanning 67 source files. Existing page-state tests mount all non-launchpad functions in pending and unavailable states and exercise malformed launchpad state (243 cases). These are structural and recovery checks, not proof that every populated panel or live provider value is correct.

All pages receive the shared provenance/freshness improvements. Full-sized pages also expose interpretation guidance appropriate to their function; launchpad panes keep their individual source scopes. Some guidance is shared by page family. This is not a claim of a bespoke visual redesign or full numerical certification of all 122 pages.

## Implemented accuracy fixes

- Provider names, source lists, dates (including month periods and Unix timestamps), coverage notes and methodology remain inspectable. Successful responses without metadata are explicitly counted as unidentified/undated. Date-field basis is shown separately from browser receipt time; no inferred quality score or assumed live status.
- Numeric sorting puts non-finite/missing values last instead of treating them as comparable observations.
- **FLY:** position time is not replaced with last radio-contact time; expired, future and invalid-coordinate fixes are withheld. Outage snapshots age against wall clock. Area fixes need a known age of at most 120 seconds. Projection defaults off and is bounded to 120 seconds. Regional observations do not claim complete global coverage. Typical capacity is not an actual load; distance from origin is not actual track distance.
- **SHIP:** unset/stationary navigation status stays unknown rather than implying at anchor. Explicit anchor and moored statuses remain separate. Historical AIS cells are labelled as approximate presence; they can be satellite or terrestrial, not necessarily satellite fixes. Recent receiver reports expire. Port circles show observed presence, not verified berth queues, congestion, occupancy or throughput. Nearby circles can overlap.
- **Chokepoints:** seven-day means require seven unique dated, non-missing observations in the calendar window. Missing activity is never replaced with zero. The prior-year comparison uses a seven-date window shifted 365 days; the annual mean requires at least 330 of 365 days. Provider-down disk fallbacks carry a stale flag. Charts use the same full-window/no-zero rule. Removed an unsupported specific geopolitical assertion from explanatory copy.
- **CORR:** positive finite prices only, no forward-fill zero returns, at least 20 paired observations for a cell, pairwise counts available on hover, missing symbols listed, currency/return-window basis disclosed. Pairwise matrices need not be positive semidefinite and should not be used unmodified as optimizer covariance inputs.
- **COMP:** deduplicated symbols, bounded chart filling, observed-return risk/correlation, arithmetic-return Sharpe with zero cash-rate assumption, weekend-crypto annualization where detected, missing sparse risk left unavailable. Drawdowns use each security's observed path. Local-currency returns are not investor-currency returns.
- **RRG:** removed unlimited daily forward fill; four-week changes need an actual complete five-point weekly window; stale endpoints do not receive a current quadrant.
- **SEAS:** missing monthly prices no longer create implicit zero returns.

## Tracker usability and performance

New observation-quality summaries, counts and response age distinguish real observations from estimates. Both maps have rounded containers, keyboard pan/zoom and visible basemap retry. High-detail coastline requests share a promise across concurrent maps. Shipping avoids reconstructing historical-cell objects on every clock tick; aircraft clock redraws slow to 30 seconds when projection is off. No claim of measured FPS improvement is made.

## Verification and limits

Validation completed and development services rechecked on 3 November 2026. TypeScript and the production Vite build passed; Vite still reports a large-chunk warning. Live SPY/TLT/GLD checks returned 125 paired two-day observations for each correlation cell and 250 daily observations per comparison risk series. These are sample-specific results, not a guarantee for every market/provider.

- Final deterministic backend regression run: **124 passed** across tracker quality, Markets functions/follow-ups/audit, disclosure evidence, marketdata, market stats and bars. Two existing Pydantic deprecation warnings remain.
- A cross-listing test used a live FX lookup unnecessarily; its external dependency is replaced with a fixed fixture rate so classification can be checked offline without changing production logic.
- Full frontend run: **545 passed across 59 files**, including the 243 Markets page-state cases and live API integration tests. Two additional populated tracker tests passed in a focused run (11 tests including provenance/hook regressions). One map timeout during a busy concurrent build prompted a successful run with two workers rather than increasing assertion timeouts.
- Live API samples returned 11,590 aircraft rows and 53 port areas. These counts are observations at verification time, not a coverage guarantee.
- Browser inspection confirmed the running Markets shell and ship-page controls/chokepoint data. Subsequent browser transport timeouts prevented final visual screenshots and fully populated end-to-end verification. No authentication bypass or private feed was added.
- Not every provider/market/inner tab has been independently reconciled against official publications in this pass. Missing provider dates, revision histories, licensing and coverage remain visible rather than guessed.

## Remaining data work

Highest-value follow-up is per-field observation/release/vintage metadata across older endpoints, independent reconciliation fixtures for all provider families, stable point-in-time constituent histories, explicit base-currency return conversion, licensed primary ETF issuance and historical global AIS/ADS-B coverage metrics. Credentials/entitlements are not created by this audit. Private flows, actual aircraft cargo, verified port waiting times and complete worldwide traffic cannot be inferred from current public feeds.

## Primary methodology references

- [OpenSky state vectors: position time versus last contact](https://openskynetwork.github.io/opensky-api/rest.html)
- [US Coast Guard AIS navigation-status and unavailable-field definitions](https://www.navcen.uscg.gov/ais-class-a-reports)
- [AISStream messages and metadata](https://www.aisstream.io/documentation)
- [Digitraffic marine data and timestamp units](https://www.digitraffic.fi/en/marine-traffic/)
- [CFTC reporting and publication dates](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm)
- [ALFRED revision vintages](https://fred.stlouisfed.org/docs/api/fred/alfred.html)

## Per-page inventory

All rows inherit shared provenance/recovery changes. “Detailed fixes” identifies changes beyond those shared controls; other rows retain their existing specialist functionality. Endpoints/internal sections and static review signals are in the accompanying JSON inventory.

| Function | Page | Family | Detailed fixes this pass |
|---|---|---|---|
| RDESK | Research desk | My tools | Shared evidence controls and interpretation guidance |
| DES | Description | Security | Shared evidence controls and interpretation guidance |
| GP | Price chart | Security | Shared evidence controls and interpretation guidance |
| FA | Financials | Security | Shared evidence controls and interpretation guidance |
| ERN | Earnings & estimates | Security | Shared evidence controls and interpretation guidance |
| ANR | Analyst ratings | Security | Shared evidence controls and interpretation guidance |
| HDS | Holders | Security | Shared evidence controls and interpretation guidance |
| DVD | Dividends | Security | Shared evidence controls and interpretation guidance |
| OMON | Options | Security | Shared evidence controls and interpretation guidance |
| RV | Peer comparison | Security | Shared evidence controls and interpretation guidance |
| HP | Price history | Security | Shared evidence controls and interpretation guidance |
| VAP | Volume at price | Security | Shared evidence controls and interpretation guidance |
| OVME | Option calculator | Security | Shared evidence controls and interpretation guidance |
| GE | P/E history | Security | Shared evidence controls and interpretation guidance |
| DS | Filing search | Security | Shared evidence controls and interpretation guidance |
| EM | Earnings matrix | Security | Shared evidence controls and interpretation guidance |
| CRPR | Credit profile | Security | Shared evidence controls and interpretation guidance |
| PROB | Probability lab | Security | Shared evidence controls and interpretation guidance |
| DARK | Off-exchange volume | Security | Shared evidence controls and interpretation guidance |
| TRAN | Earnings-call transcripts | Security | Shared evidence controls and interpretation guidance |
| BETA | Beta | Security | Shared evidence controls and interpretation guidance |
| TECH | Technical analysis | Security | Shared evidence controls and interpretation guidance |
| OVDV | Volatility surface | Security | Shared evidence controls and interpretation guidance |
| CACS | Corporate actions | Security | Shared evidence controls and interpretation guidance |
| MGMT | Management | Security | Shared evidence controls and interpretation guidance |
| PGEO | Segments & regions | Security | Shared evidence controls and interpretation guidance |
| DDIS | Debt maturities | Security | Shared evidence controls and interpretation guidance |
| CF | Company filings | Security | Shared evidence controls and interpretation guidance |
| FAC | Factor exposures | Security | Shared evidence controls and interpretation guidance |
| VAL | Valuation hub | Security | Shared evidence controls and interpretation guidance |
| DCF | DCF valuation | Security | Shared evidence controls and interpretation guidance |
| SEAS | Seasonality | Security | No implicit monthly-price fill |
| OSA | Option strategies | Security | Shared evidence controls and interpretation guidance |
| FUTU | Futu live market depth | Security | Shared evidence controls and interpretation guidance |
| SI | Short selling | Security | Shared evidence controls and interpretation guidance |
| SPLC | Supply chain | Security | Shared evidence controls and interpretation guidance |
| INSD | Insider trades | Security | Shared evidence controls and interpretation guidance |
| CN | Company news | Security | Shared evidence controls and interpretation guidance |
| WEI | World markets | Markets | Shared evidence controls and interpretation guidance |
| RMON | Regional monitor | Markets | Shared evidence controls and interpretation guidance |
| CTRY | Country page | Markets | Shared evidence controls and interpretation guidance |
| LP | Launchpad (multi-window) | Markets | Shared evidence guidance; individual pane provenance |
| MOST | Movers | Markets | Shared evidence controls and interpretation guidance |
| IMAP | Market heatmap | Markets | Shared evidence controls and interpretation guidance |
| CRYPTO | Crypto | Markets | Shared evidence controls and interpretation guidance |
| CMDTY | Commodities & curves | Markets | Shared evidence controls and interpretation guidance |
| MAP | World map | Markets | Shared evidence controls and interpretation guidance |
| CORR | Correlation matrix | Markets | No price filling; paired counts; invalid-price guards |
| RRG | Relative rotation | Markets | Actual weekly windows; current endpoints |
| EDGE | Signal board | Alternative data | Shared evidence controls and interpretation guidance |
| RISK | Risk regime | Markets | Shared evidence controls and interpretation guidance |
| VOL | Volatility | Markets | Shared evidence controls and interpretation guidance |
| BRDT | Market breadth | Markets | Shared evidence controls and interpretation guidance |
| IMPM | Earnings implied moves | Markets | Shared evidence controls and interpretation guidance |
| UOA | Unusual options | Markets | Shared evidence controls and interpretation guidance |
| COT | Positioning (COT) | Alternative data | Shared evidence controls and interpretation guidance |
| ENVR | All Weather environments | Economy & policy | Shared evidence controls and interpretation guidance |
| AWP | All Weather portfolio | Economy & policy | Shared evidence controls and interpretation guidance |
| DCYC | Debt cycles | Economy & policy | Shared evidence controls and interpretation guidance |
| HGRL | Holy Grail diversification | Economy & policy | Shared evidence controls and interpretation guidance |
| WPWR | World power index | Economy & policy | Shared evidence controls and interpretation guidance |
| CHART | Formula charts | Markets | Shared evidence controls and interpretation guidance |
| DATA | Data grid (BDP / BDH) | Markets | Shared evidence controls and interpretation guidance |
| YAS | Treasuries & bond calculator | Rates & FX | Shared evidence controls and interpretation guidance |
| ILBE | Inflation expectations | Rates & FX | Shared evidence controls and interpretation guidance |
| FXCA | FX carry | Rates & FX | Shared evidence controls and interpretation guidance |
| MRGR | Merger arbitrage | Markets | Shared evidence controls and interpretation guidance |
| MEMB | Index members | Markets | Shared evidence controls and interpretation guidance |
| FSRC | ETF screener | Markets | Shared evidence controls and interpretation guidance |
| DVDC | Dividend & split calendar | Markets | Shared evidence controls and interpretation guidance |
| CDR | Exchange hours | Markets | Shared evidence controls and interpretation guidance |
| ETFA | ETF premium / discount | Markets | Shared evidence controls and interpretation guidance |
| SPRD | Pairs & spreads | Markets | Shared evidence controls and interpretation guidance |
| IMOV | Index movers | Markets | Shared evidence controls and interpretation guidance |
| TRA | Total returns | Markets | Shared evidence controls and interpretation guidance |
| WPE | World valuations | Markets | Shared evidence controls and interpretation guidance |
| MRR | Member returns | Markets | Shared evidence controls and interpretation guidance |
| EARN | Earnings season | Markets | Shared evidence controls and interpretation guidance |
| ECFC | Economic forecasts | Economy & policy | Shared evidence controls and interpretation guidance |
| BORROW | Short borrow | Markets | Shared evidence controls and interpretation guidance |
| PROOF | What actually works | Research | Shared evidence controls and interpretation guidance |
| ALPHA | Stock signal lab | Research | Shared evidence controls and interpretation guidance |
| LEAG | M&A adviser league | Research | Shared evidence controls and interpretation guidance |
| EXTH | Pre-market & after hours | Markets | Shared evidence controls and interpretation guidance |
| CBRT | Central bank rates | Economy & policy | Shared evidence controls and interpretation guidance |
| ECOS | Economic data explorer | Economy & policy | Shared evidence controls and interpretation guidance |
| CRED | Credit spreads | Rates & FX | Shared evidence controls and interpretation guidance |
| PORT | Portfolio risk | Markets | Shared evidence controls and interpretation guidance |
| PRED | Prediction markets | Economy & policy | Shared evidence controls and interpretation guidance |
| NOW | Nowcasts & trade | Economy & policy | Shared evidence controls and interpretation guidance |
| FLOW | Money flow map | Alternative data | Shared evidence controls and interpretation guidance |
| SHIP | Shipping tracker | Alternative data | Position/status guards; port presence; calendar-window transits; map UI |
| FLY | Flight tracker | Alternative data | Fix age/coordinates; bounded projection; load/route semantics; map UI |
| QUAK | Earthquakes | Alternative data | Shared evidence controls and interpretation guidance |
| EIA | Oil & gas inventories | Alternative data | Shared evidence controls and interpretation guidance |
| WETR | Weather & energy demand | Alternative data | Shared evidence controls and interpretation guidance |
| COMP | Compare | Markets | Observed-return risk; Sharpe; sparse data; bounded chart fill |
| GC | Yield curves | Rates & FX | Shared evidence controls and interpretation guidance |
| BTMM | Money markets | Rates & FX | Shared evidence controls and interpretation guidance |
| FRD | FX forwards | Rates & FX | Shared evidence controls and interpretation guidance |
| WB | World bonds | Rates & FX | Shared evidence controls and interpretation guidance |
| FOMC | Fed portal | Rates & FX | Shared evidence controls and interpretation guidance |
| FWCV | Forward curves | Rates & FX | Shared evidence controls and interpretation guidance |
| SWAP | Swap curves | Rates & FX | Shared evidence controls and interpretation guidance |
| CDSX | Credit indices (CDS) | Rates & FX | Shared evidence controls and interpretation guidance |
| CDSA | Single-name CDS activity | Rates & FX | Shared evidence controls and interpretation guidance |
| TRACE | Corporate bond market | Rates & FX | Shared evidence controls and interpretation guidance |
| WIRP | Fed rate probabilities | Rates & FX | Shared evidence controls and interpretation guidance |
| AUCT | Treasury auctions | Rates & FX | Shared evidence controls and interpretation guidance |
| WCRS | FX cross rates | Rates & FX | Shared evidence controls and interpretation guidance |
| EQS | Equity screener | Research | Shared evidence controls and interpretation guidance |
| 13F | Investor holdings (13F) | Research | Shared evidence controls and interpretation guidance |
| IPO | IPO calendar | Research | Shared evidence controls and interpretation guidance |
| ACTN | Analyst & company actions | Research | Shared evidence controls and interpretation guidance |
| EVTS | Earnings calendar | Research | Shared evidence controls and interpretation guidance |
| ECO | Economic calendar | Economy & policy | Shared evidence controls and interpretation guidance |
| ECST | Economic surprises | Economy & policy | Shared evidence controls and interpretation guidance |
| N | News | Research | Shared evidence controls and interpretation guidance |
| W | Watchlists | My tools | Shared evidence controls and interpretation guidance |
| ALRT | Alerts | My tools | Shared evidence controls and interpretation guidance |
| AI | AI research assistant | My tools | Shared evidence controls and interpretation guidance |
| JRNL | Trading journal | My tools | Shared evidence controls and interpretation guidance |
