# Markets section audit (27 Oct 2026)

Every Markets endpoint (128 routes, 252 calls) was run in-process for a spread of instruments — Apple, Toyota, SAP,
HSBC (quoted in pence), Tencent, Bitcoin, EUR/USD, the S&P 500, gold — and checked against independent sources:
ECB reference rates, the US Treasury par curve, CoinGecko, and internal consistency (the same number on every screen;
price × shares = market cap; units of the price = units of every per-share figure).

## Wrong numbers found and fixed

| Area | What was wrong | Fix |
|---|---|---|
| FX day changes (overview, country, world map, watchlists, WCRS) | Measured from Yahoo's previous **daily bar**, which is stale at the day boundary: USD/BRL showed **+7.5%** (Monday's bar 4.96 while the market traded 5.40–5.59); the euro showed 0.6% on the country and FX screens vs 0.26–0.36% in reality, with the two screens disagreeing | Previous close = the previous business day's **ECB reference fixing** everywhere (`core.fx_last_prev`); all screens now agree |
| FX levels / USD conversions | No second source: a bad Yahoo rate flowed into market caps in USD, DCF conversions and the cross-rate matrix | Levels checked against the latest ECB fixing; > 10% away (wrong units, dead feed) the fixing is used and flagged (`core.fx_checked`) |
| US data-surprise index | Month-on-month changes were taken across **different vintages**: September retail sales (+0.77% as released, with August revised down in the annual benchmark) was scored as −3.7% → a −4σ "collapse"; the index read −3.1 | Change = the release's own pair (this month and the prior month from the same vintage, ALFRED all-vintages) → −0.3 |
| Dividends (London, Johannesburg lines) | Payments in pence but the "forward rate" in pounds/dollars ("0.56 GBp / yr") | Trailing-12-month dividends and yield from the payment record in the price's units; Yahoo's indicated rate kept only when consistent |
| Holders (non-US companies) | US 13F filers shown as "top holders" of HSBC/Toyota (often ADR holders, ADR share counts), values in **pence** | Values in the major unit, sorted by size, and a clear note that the list is US filers, not the share register |
| Management pay | Hard-coded "$": Toyota's CFO showed **$268M** (it is ¥268M) | Pay in the company's reporting currency |
| Technicals (Tokyo, Hong Kong) | Indicators a session behind (Yahoo's 10-year daily history omits the latest Asian session for hours) | Latest session stitched from the quote when the history lags |
| 10-year yields (world map / country) | Iceland showed **1.0% from August 2022** (discontinued series) | Series older than 150 days left out; monthly OECD averages labelled as such |
| Central-bank rates | Croatia's pre-euro HNB rate (2022) and stale series in the table and the easing/tightening breadth; Kuwait and Morocco unnamed | Series older than 120 days left out; names added |
| Peer multiples (RV, VAL) | Median of unbounded multiples — Microsoft's peers (Palantir 158×, CrowdStrike, Cloudflare) implied $1,476 | NM bounds + harmonic mean (see `docs/dcf_methodology.md`) |
| Earnings card (DES) | "In line" test treated a percent as a decimal (±0.05%) | ±1% |

## Checked and correct

Quotes vs CoinGecko and ECB; market cap = price × shares (US, Japan, UK pence, Hong Kong); US Treasury curve = the
official par curve to the basis point; Bund, euro-area AAA, JGB, Canada curves; Fed-meeting probabilities (CME FedWatch
method); credit spreads and derived ratios; options greeks and expected move; beta of the index on itself = 1;
exchange calendar statuses; Apple's dividend record (1987–95, then 2012 on); non-US movers' USD market caps.

## Known limits (data, not bugs)

- SEC-based functions (CF filings, DDIS debt ladder, PGEO segments, SI short interest, INSD Form 4) cover US filers
  only; non-US companies get a clear message. Free non-US equivalents exist for some markets (UK FCA net short
  positions, Japan EDINET, HKEXnews) and are the next coverage step.
- Euro-area country 10-year yields other than Germany are OECD monthly averages (1–3 months old); daily free series
  per country are not available without keys.
- Yahoo's quarterly EPS estimates for some Japanese companies are on a different basis from reported EPS (Toyota's
  "beats" of 20–47% every quarter).
