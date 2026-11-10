# Quant corrections — disposition of the October 2026 handoff

Engine version after this work: `2026.10-ledger.1` (`api/quant/codelab.py`, `ENGINE_VERSION`).
Every Code Lab / library result now carries a provenance record with this version; library results
were regenerated under it. Results produced before it are superseded, and are no longer served from the library cache.

The uncommitted `rates.py` / `robust.py` / `backtest.py` / `trader.py` changes the handoff mentions were this
same work in progress (Sharpe on returns above T-bills); they were kept and extended, not overwritten.

## Disposition

| # | Finding | Reproduced | Disposition | Where | Tests |
|---|---|---|---|---|---|
| 1 | Walk-forward stitched standalone paths | Yes: a switch between disjoint holdings charged 0 instead of 2×10 bp | **Fixed.** Parameters are chosen from data before each 1 January; one continuous account then trades from current holdings to the new set's targets on the switch day and pays the costs. Standalone paths are used only for scoring. A `HOLDOUT` year range never enters selection | `codelab.select_walk_forward`, `continuous_walk_forward`, `evaluate` | `test_switching_parameter_sets_…`, `test_switch_to_same_holdings_…`, `test_evaluate_is_prefix_stable_…` |
| 2 | Not self-financing; cash inferred | Yes: 10% fee → NAV 0.9 but holdings still "1.0 of NAV", cash 0 | **Fixed.** Ledger in units + cash; NAV = Σ units × mark + cash every day; fills, costs, borrow and interest settle into cash; orders sized to post-cost NAV (no hidden margin loan); explicit reconciliation flag | `codelab.backtest` | fee, round-trip/gap, financing, dividend-adjusted fixtures |
| 3 | Missing open filled at the close; stale marks; delistings | Yes: 100% turnover on a day with no open | **Fixed.** Fills only at observed opens of assets that traded (volume > 0); unfillable orders stay pending; stale marks are counted, never tradable; a held listing that ends is settled at its last close × (1 − `delist_haircut`), logged as an event. Server data are now raw observations with an `observed` mask (`data.panel(fill=False)`) | `codelab.backtest`, `codeserver.load_data`, `data.panel` | missing open, zero-volume/suspension, ended listing, holiday vs unexplained gap |
| 4 | `_hold` used future rows; no explicit decisions | Yes: prefix made a decision the full history did not | **Fixed.** Helpers decide on the first observed trading day of each period (causal); non-decision rows are blank (NaN). Any row with values is an explicit decision, including an identical target. Execution is exactly one lag (next open) | `codelab._hold`, `decision_mask`, `backtest` | causal prefix, identical-target rebalance, one-lag |
| 5 | No FX / instrument metadata | Limitation confirmed | **Partly addressed.** The Code Lab account is explicitly USD. Foreign listings (exchange suffix), indices (`^`) and FX/futures (`=`) are refused with a clear message instead of being mixed. Full multi-currency accounting (FX marks, GBp/GBP units, venue calendars, broker eligibility) is **not implemented** | `codeserver.check_tradable` | covered by load checks |
| 6 | Hindsight universe; no provenance | Limitation confirmed | **Addressed where the data allow.** Every run carries provenance (engine/cost-schema versions, code/data/config hashes, data range, stale symbols, adjustment, universe-selection disclaimer) and is registered as a trial (`code_runs`). The UI shows the trial count, the deflated Sharpe over the family's trials, the record type (exploratory / walk-forward) and holdout status ("first look — untouched" vs "viewed N times"). An equal-weight universe baseline under the same costs is reported. **Point-in-time membership is not available** from free data: today's lists stay labelled retrospective | `codelab.evaluate`, `store.register_code_run`, `codeserver.analyze`, Code Lab UI | baseline/holdout/provenance fixture |
| 7 | Rates and metric definitions duplicated | Yes | **Fixed for the quant stack.** One rate service (`api/quant/rates.py`): as-of only (no later observation, `annual()` fixed), one trading-day convention (`daily`, `accrue`), `known()` flag shown in the UI. Sharpe/Sortino/PSR/DSR on returns above the reference rate in `robust.metrics`, `deep.report` and `codelab.metrics`, with identical formulas (CAGR in calendar years, max drawdown including starting capital), proven by a parity test. Cash remuneration is configurable (`cash_spread` in the Code Lab; `cash_yield`/`cash_spread` in the Macro Trader, default unchanged) | `rates.py`, `robust.py`, `deep.py`, `codelab.metrics`, `macro_trader.py` | `test_rates.py`, `test_metrics_match_robust`, deep-report test |
| 8 | Cost units ambiguous; benchmark unfair | Yes (`Spread ×` read as bp) | **Fixed.** Versioned `COST_SCHEMA` with units; every UI field shows its unit ("multiplier (×), not bp", "annual, decimal", "fraction of NAV"). The benchmark is labelled frictionless; the equal-weight universe baseline (same costs, same start) is shown beside it | `codelab.COST_SCHEMA`, Code Lab UI | — |
| 9 | 80-symbol cap; no large jobs | Confirmed | **Addressed for one case.** One limit constant (`UNIVERSE_LIMIT`, shared by loader, sandbox and UI). `TRADABLE_UNIVERSE = "US"` (~700 US-listed USD stocks) runs as a sandboxed background job: one global cross-section (no batching), progress, cancellation (kills the process), bounded concurrency, missing names reported. Jobs are in memory; a restart drops them | `jobs.py`, `sandbox.run`, `codeserver.tradable_universe`, `/api/v1/quant/code/jobs` | runtime-verified (698 names, 115 s first run) |
| 10 | Cache compatibility, staleness, parity | Partly | **Partly addressed.** Stale cache fallbacks are recorded and shown in results; each newly cached series gets a JSON manifest (fetch time, rows, range, adjustment, hash, pandas/numpy versions). Unreadable pickles are treated as missing and re-downloaded. Browser and sandbox report their runtime versions; sandbox and in-process results matched exactly (max difference 0.0). Pickles are still the storage format (trusted, server-written) | `data._write_manifest`, `LAST_REPORT.stale` | — |

Also found and fixed while doing this:
- The no-trade band blocked new positions in large books (700 names × 0.14%): it now only suppresses small adjustments to positions that stay open.
- The Monte Carlo recommended 2× leverage for a Sharpe-0.08 book: leverage is now capped at 1× when the excess-return Sharpe is below 0.3.
- 13F tickers from OpenFIGI included a convertible bond and `*` lines: only common-stock tickers are accepted.
- Deploy and delete silently did nothing where the browser suppresses `window.confirm`/`prompt`: all quant and portfolio actions now use an in-app dialog (`components/ui/ConfirmDialog.tsx`).

## Not done (migration plan)

1. **Multi-currency accounting.** Instrument metadata (currency, quote unit, venue calendar, multiplier, broker eligibility), FX marks and cash by currency. Until then, non-USD listings are rejected.
2. **Point-in-time universes.** Needs a membership source with delisted names (not free). The equal-weight baseline and the retrospective label are the current mitigations.
3. **Other engines onto the ledger.**
   - Shadow-reconcile the legacy formula engine (`quant/engine.py`, still used by older deployments), `stock_backtest`, `auto_backtest` and the auto-trader against `codelab.backtest` on fixed fixtures, then switch each one.
   - Order/fill idempotency keys and a persistent job store come with that step.
4. **Portable cache format.** Parquet + manifest once `pyarrow` is a dependency; then stop reading pickles.

## Effect on results (same data, old engine → new engine)

| Strategy | Old CAGR | New CAGR | Notes |
|---|---|---|---|
| Risk parity | 4.41% | 4.55% | barely changed |
| VRP timing | 12.1% | 14.7% | Sharpe 0.91 |
| Following the quant giants' buying | — | 19.4% | alpha t = 2.14 |
| Robeco conservative | — | 13.6% | equal-weight baseline 18.5% |
| Sector momentum | — | 9.7% | equal-weight baseline 12.8% |

- **Several strategies lose to their own equal-weight universe baseline** under identical costs, most notably Robeco and sector momentum.
- **User strategy, hand-picked 80 names:** 21.0% CAGR (sandbox).
- **The same strategy on the full 698-name tradable US universe:** 17.1% CAGR, Sharpe 0.98, max drawdown −29.8%, with 22 listings ending while held. The hand-picked list flattered the result by about 4 points a year.
- **None of these is a validated edge:** the universe is today's list (retrospective), and the trials were sequential.

## Follow-up (same day): remaining items

Work was split with another tool editing the engine and Code Lab files at the same time (it replaced the
inferred-delisting rule with explicit dated delisting events — the better policy, now the engine's). This
follow-up only touches other files.

| Item | Status | Where |
|---|---|---|
| Deploy failing (400) from the Strategy library | **Fixed.** Server-computed entries (multi-manager, multi-strategy, 13F) have no code; deploy assumed they did. They now deploy from the server's own result. Routing: 13F → Fundamental trader, portfolios → Macro, TRADABLE_UNIVERSE code → Technical (it was being sent to Macro because its literal UNIVERSE is just SPY) | `trader.code_universe`, `eval_code_spec`, `classify` |
| Point-in-time universe | **Done for the S&P 500.** `TRADABLE_UNIVERSE = "SP500_PIT"`: every name that was a member since START, membership snapshots since 1996 plus Wikipedia's current list after the history ends; `data.members` (dates × tickers) gives who was a member each day; renames mapped; removed names without free prices reported; explicit delisting events generated only when a name had left the index *and* stopped trading | `membership.py`, `sandbox.run`, `sandbox_child.py` |
| Older formula engine onto the ledger | **Done.** `engine.simulate` now runs on `codelab.backtest` (same decisions/schedule; outputs unchanged in shape). Shadow reconciliation: identical to the legacy simulator at zero cost (next-open and next-close), within 0.2–0.5% with costs (fees paid from cash instead of from weights). Cash now earns the T-bill rate per the shared contract | `engine.py`, `test_engine_migration.py` |
| Persistent jobs | **Done.** Jobs are stored in `quant_jobs`; results survive restarts; jobs running during a restart are marked *interrupted* | `jobs.py` |
| Portable caches | **Done.** Parquet (pyarrow), atomic writes, a manifest per series; legacy pickles are read once and migrated; unreadable files count as missing | `data.py`, `cachefmt.py`, `stock_backtest.py`, `strategy_lab.py`, `factor_library.py` |
| Multi-currency | **Done in the data layer** (minor units, FX as of each bar, opens at the previous FX close, venue transaction taxes in the engine) — those edits sit in the other tool's files (`codeserver.py`, `codelab.py`) for it to integrate; `instruments.py` is committed here | `instruments.py` |

Your strategy under each universe (same code, same costs): hand-picked 80 → 21.0% CAGR; today's 700
tradable US names → 17.1%; point-in-time S&P 500 → 13.2% (Sharpe 0.71, max drawdown −37.7%; 151 former
members without free prices). Each step that removes hindsight lowers the result.

Still open: the stock auto-trader (`auto_trader.py`) keeps its own trade-based paper book (with FX); it was not
moved onto the shared ledger in this pass.

## Follow-up (13 Oct): any listing, any account currency — engine `2026.10-ledger.3`

| Item | Status | Where |
|---|---|---|
| Account currency | **Done.** `ACCOUNT_CURRENCY = "EUR"` (38 currencies; default USD). Every listing is converted local → USD → account at as-of FX (closes at that day's FX closes, opens at the previous closes); a listing already in the account currency is not converted; a missing account-currency FX history is an error, never a silent USD account. Prices, NAV, costs, capital and the benchmark are all in the account currency | `codeserver._to_account_currency`, `benchmark_series`, `instruments.ACCOUNT_CURRENCIES` |
| Cash rate per currency | **Done.** As-of only: OECD 3-month interbank rates (monthly averages, usable from the 15th of the next month), spliced with €STR (EUR) and SONIA (GBP) where the OECD series ends; central-bank discount rates for INR/BRL/TRY; the US T-bill for USD pegs (HKD, SAR, QAR, AED, BHD, OMR), labelled a proxy; otherwise unknown (cash earns 0, flagged). Sharpe, the deep report and the Monte Carlo use the account currency's rate; the factor lens converts to USD first | `rates.py` (`daily(…, ccy)`, `describe`), `deep.report(…, ccy)`, `codeserver.analyze` |
| FX conversion cost | **Added.** `fx_cost_bps` (default 2 bp of traded value) on trades in a listing whose currency differs from the account's — broker FX fee plus dealing spread; retail platforms charge 25–100 bp, so set it to your broker's | `codelab.backtest`, `COST_SCHEMA` |
| Cost model in other currencies | **Done.** The spread model is calibrated on US dollar volume; traded value is scaled to USD (`usd_per_unit`) so a stock costs the same whatever the account currency (tested) | `codelab.half_spread_bps` |
| Venue taxes in the sandbox | **Bug fixed.** The sandbox child (which runs every TRADABLE_UNIVERSE job and every deployment) did not receive instrument metadata: stamp duties / FTTs were never charged there and the SEC fee was charged on every sale. The browser payload had the same gap. Both now carry it (regression test) | `sandbox.run`, `sandbox_child.py`, `data_payload`, `quant-py-worker.js` |
| Universe selection | **Done.** `TRADABLE_UNIVERSE` takes a named universe, a region (`EUROPE`, `ASIA_PACIFIC`, `AMERICAS`, `MIDDLE_EAST_AFRICA`), any listing country (`"JP"`) or a combination (`"JP+HK"`, `["GB", "DE"]`). A literal `UNIVERSE` of up to 4,000 tickers runs as a server job (≤ 80 still run in the browser) | `codeserver.tradable_universe`, `/api/v1/quant/code/universes` |
| Instrument data for strategies | **Done.** `data.info` (country, currency, sector, region, market class), `data.account_currency`; results report holdings by currency, country and sector | `codelab.Data.info`, `exposure_breakdown` |
| Paper traders | **Done.** A code deployment keeps its account currency (NAV shown in it); books add deployments up in USD at as-of FX; deploy capital is checked as $1k–$1bn equivalent | `trader._one`, `book`, `_deploy_code` |

The four items first listed as not modelled are now modelled — see the next section.

Your global strategy after this follow-up (same code, sandbox, 3,100 names): USD account 19.3% CAGR, Sharpe 0.98,
max drawdown −33.5% (was 19.5% before stamp duties and FX costs were charged in the sandbox); the same strategy in
a EUR account 20.3%, Sharpe 1.02 (the dollar rose against the euro over the period). About 21% of the book is in
Taiwan-dollar stocks — a concentrated currency and country bet the new exposure panel makes visible.

## Follow-up (13 Oct, later): market rules and options — engine `2026.10-ledger.4`

| Item | Status | Where |
|---|---|---|
| Board lots | **Modelled.** Orders round to whole lots at the run's `capital` (JP 100, CN 100, TW 1,000, TH/MY/ID/SG/BR 100, PH by price band, **Hong Kong per stock from HKEX's published list of securities**, single shares elsewhere); a full exit may sell an odd lot; the untraded remainder is reported. `board_lots` 0/1 | `market_rules.py`, `codelab.backtest` |
| Tick sizes | **Modelled.** Exchange tick tables (JP, HK, CN, TW, KR, IN, ASEAN, AU, Americas, SA, TR; MiFID II liquid band elsewhere) on the traded (not dividend-adjusted) price: half a tick floors the spread model | `market_rules.half_tick_bps`, `half_spread_bps(tick_bps=)` |
| Dividend withholding | **Modelled.** Yahoo cash dividends (cached weekly) give ex-date yields; long holdings of listings in another currency than the account's lose the listing country's statutory non-resident rate, capped at a treaty rate (`wht_treaty_cap`, default 15%) | `corpactions.py`, `market_rules.WHT` |
| FX hedging | **Modelled.** `FX_HEDGE = 0…1` (or the UI field): daily-settled forwards on each currency's exposure — the hedged share of currency moves is given back, the interest differential (account − foreign short rate) is earned or paid, roll costs `fx_hedge_cost_bps` (15 bp/yr). Currencies without a free rate history stay unhedged and are listed | `codelab.backtest` (step 6) |
| Options | **New.** `OPTIONS = [...]` declares synthetic listed options (call/put; strike by moneyness or delta; monthly / weekly / quarterly / fixed-tenor expiries). Black–Scholes–Merton on the traded price, dividend yield and the currency's short rate, with implied vol from CBOE's indices where they exist (VIX term structure 9D–6M for S&P 500 ETFs, VXN, VXD, GVZ, OVX) or realised vol × the market's implied/realised ratio, plus skew. A weight on an option is the **underlying notional** (−1.0 = write on 100% of NAV). Expiring contracts settle at intrinsic value; standing weights roll. Option spreads (0.75–2.5% of premium, ≥ half a tick) + $0.65/contract; 100-share contracts as board lots; no stock-borrow on written options | `options.py`, `codelab.backtest`, `data.opt`, `on_rolls` |
| Option library | **New.** CBOE PutWrite, BuyWrite, 95-110 Collar, delta-hedged short straddle (variance risk premium) | `library.py` |

Model check against a real index — CBOE S&P 500 PutWrite (^PUT), 2008–2026, synthetic SPY version with costs:
monthly correlation 0.96; 8.1% vs 7.2% a year; worst drawdown −36.7% vs −37.1%; 2008 −27.6% vs −26.2%;
2022 −7.3% vs −7.7%; 2020 −3.1% vs +2.1% (the index sells at mid-day on expiry Friday, the model at the next
open — after a crash that gap matters). Library results (with costs): BuyWrite 8.0% (≈ PutWrite, as put–call
parity says), Collar 7.7% with a −22% worst drawdown (S&P −52%), delta-hedged straddle 3.6% at 2.9% volatility.

Option prices are a model, not quotes: crash-day skew, spreads that widen in stress, early exercise of American
options and pin risk are not in it.
