# Data connections (Oct 2026)

Every connection is **read-only** and **optional**: without it, the platform falls back to its free sources (Yahoo,
FRED, SEC EDGAR, Finnhub). Their state is shown under **FEEDS → Connections** in the top bar. Keys live only in `.env`
(gitignored) and are never logged.

| Connection | Setup | What it adds | Limits |
|---|---|---|---|
| **Massive** (Polygon) | `MASSIVE_API_KEY` | Store of daily bars for every US stock (`data/processed/massive/`): two-year backfill in the background, one request a day after; the US heat map (≈1 s instead of ≈25 s) and breadth read it | Free plan: 5 requests/min, end-of-day, 2 years |
| **Futu OpenAPI** | Run **FutuOpenD**, log in, keep it open (minimise, don't close) | FUTU screen: live order book, ticks with exchange direction, capital flow by order size; real-time HK quotes on DES; real ticks on TAPE; Futu holdings in the Position Manager | Entitlements of the account: US LV3, HK LV1 (broker queue needs LV2), no A-shares |
| **IBKR TWS** | TWS (or IB Gateway) open, API → *Enable ActiveX and Socket Clients* and **Read-Only API** ticked; port 7496 (`IBKR_TWS_PORT` to change) | Quotes on 19 exchanges and historical bars; real-time overlay on DES where the account subscribes | No real-time subscriptions on the account yet → delayed feed; no HK |
| **Benzinga** | `BENZINGA_API_KEY` | ANR: rating actions with the named analyst; ACTN: market-wide rating and guidance changes; news headlines | Market-wide ratings appear to be a sample on this plan |
| **FMP** | `FMP_API_KEY` | ANR: grade consensus and price-target trend; EVTS: revenue estimates, fallback calendar | US only; 250 requests/day (capped at 230, counter and cache on disk) |
| **SEC bulk files** | Unpack `companyfacts.zip` / `submissions.zip` (SEC_BULK_DIR, `data/sec_bulk` or `~/Downloads`) | Company facts read from disk when they include the latest 10-Q/10-K (88% of the S&P 500 in Oct 2026); offline fallback for filings | Refresh the archives every few months to keep more companies on the disk path |
| Alpha Vantage | `ALPHAVANTAGE_API_KEY` | Not wired: the free plan's quotes and top movers are already covered; news sentiment and fundamentals are premium | 25 requests/day |

Safety: neither the Futu nor the IBKR module contains an order call (tests scan their source); TWS's Read-Only API
setting blocks orders at the gateway as well. Order routing would need separate, explicit authorisation.
