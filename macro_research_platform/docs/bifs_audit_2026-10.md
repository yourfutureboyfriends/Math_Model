# BIFS fit audit — Macro Terminal as a buy-side trading platform (25 Oct 2026)

**Fund profile audited against.** Long-only, bottom-up global equity, MSCI World (developed markets) universe; benchmark
50% MSCI World + 50% MSCI World Equal Weighted, **GBP net total return**; 1–5 year horizons; paper portfolio; PMC
approves, Head of Trading implements.

**Method.** Every status below was verified by running code (temporary databases and accounts; never the live book),
not by the existence of a button. "Evidence" names the test or the file and what it showed.

## 1. Feature audit

| # | Feature | Current implementation | Status | Evidence | Importance (trading desk) | Recommended improvement | Priority |
|---|---|---|---|---|---|---|---|
| 1 | Fund cash with non-USD holdings | `cash_balance()` sums quantity × avg_cost in **local units** | **Broken** | Throwaway book (100 AAPL $200, 100 AZN.L 11,000p, 100 7203.T ¥2,500, capital $1m) → **cash −$370,000** (should be ≈ +$963,800) | Critical — every weight, limit and NAV figure for a global fund | Cost basis in base currency at entry-date FX; cash from it | Critical |
| 2 | Base currency (GBP) | `base_currency` setting exists | **Broken** (label only) | `grep base_currency`: only stored and echoed; NAV, P&L, risk all USD | Critical — BIFS reports in GBP | Value the book, cash, P&L in the fund's base currency at as-of FX | Critical |
| 3 | Blotter / realised P&L across currencies | Fills, commissions and realised P&L stored in the listing's units (pence, yen) and summed | **Broken** | `execute_order` → `book_fill(price=close)`; `blotter_totals` adds raw amounts | Critical once non-USD trades exist | Store currency + FX at fill; totals in base | Critical |
| 4 | FX P&L vs local P&L | Unrealised P&L converts cost at **today's** FX | Partial | `_enrich_positions` multiplies local P&L by current `usd_per_unit` | High — GBP fund holding USD/EUR/JPY stocks | Cost at entry FX; split local and FX P&L | High |
| 5 | BIFS benchmark (50% MSCI World + 50% MSCI World EW, GBP NTR) | Analytics benchmark = SPY | **Missing** | `portfolio_analytics.brinson/tracking_error(benchmark="SPY")` | Critical — the fund is judged against it | Daily-rebalanced 50/50 blend of accumulating UCITS ETF proxies in GBP (SWDA.L from 2009; MWEQ.L from 4 Sep 2024 — no free EW series before); limits stated | Critical |
| 6 | Pre-trade compliance (limits) | `/api/v1/risk/pretrade`: limit metrics before/after → PASS/WARN/BLOCK | Working (USD, limits only) | `_run_pretrade`; tests in test_fund | High | Extend into a full feasibility assessment (#7) | — |
| 7 | Pre-trade **feasibility** (liquidity, costs, taxes, FX, events, hours, technicals, mandate, portfolio impact, fair value) | Pieces exist separately (impact model in Code Lab, tax table, CDR hours, earnings calendar, LVaR) | **Missing** as a desk tool | No endpoint combines them for one order | Critical — the Head of Trading's core decision | One assessment per proposed order, every estimate labelled as an estimate | Critical |
| 8 | Simulated fills | Fill at the last close; commission bps only | Partial | `execution.simulated_fill(signed, closes[-1])` | High — overstates execution quality | Fill at close ± modelled half-spread + impact, plus stamp duty/FTT; recorded as estimates | High |
| 9 | Analyst pitch review (thesis, bull/base/bear values, horizon, catalysts, kill criteria, versions, PMC status) | — | **Missing** | No module, table or screen (`grep pitch\|kill_criteria` → nothing) | Critical for BIFS workflow | Versioned pitch records, PMC decision, fair value feeding pre-trade, kill-criteria checks | Critical |
| 10 | Mandate constraints (long-only, developed markets only, max position, sector cap, cash band) | Generic risk limits (gross, single name, top-5, VaR, drawdown …) | Partial | `calculations/limits.py`; no long-only / DM-universe / sector rule | High | Mandate rules in the pre-trade check | High |
| 11 | Fundamentals: revenue, operating income, net income, FCF, margins, ROE/ROA, leverage | `core.statements()` (Yahoo; global listings) | Working | statements fields incl. Free Cash Flow, fcf_margin, operating_margin, roe, debt_to_equity | High | Add ROIC and FCF yield to the per-stock snapshot | Medium |
| 12 | Valuation multiples (P/E, forward P/E, EV/EBITDA, P/B, P/S) and peers | `security.comps()` | Working | `ev_ebitda` computed from EV and EBITDA with sanity bounds | High | P/FCF | Low |
| 13 | DCF (FCFF / FCFE / residual income) | `DcfView` | Working (single case) | SecurityFunctions.tsx DcfView | High | Bull / base / bear scenarios live in the pitch (#9) | Medium |
| 14 | Earnings and surprises; analyst targets and revisions | `security.earnings()`, `security.analysts()`; index EPS revisions | Working | ERN / ANR functions; eps_revisions module | High | Show next earnings in pre-trade (#7) | — |
| 15 | Management guidance changes | — | Missing (data) | No free structured guidance feed | Medium | Recorded manually in pitch updates; paid feed otherwise | Low |
| 16 | Technical snapshot per stock (RSI14, SMA 20/50/200, MACD, Bollinger, ATR, hist. vol, volume anomaly, support/resistance, RS vs benchmark, max drawdown) | Charts in the security page; indicators not computed server-side | Partial | No backend function returns them for a stock | High — timing of entry/exit | One server-side snapshot used by pre-trade | High |
| 17 | Liquidity: ADV, 20/30-day ADTV, participation, days to execute | Portfolio LVaR + days-to-liquidate | Partial (portfolio only) | `risk_liquidity_v1` | Critical for sizing orders | Per-order in pre-trade (#7) | Critical |
| 18 | Spreads | Live bid/ask from Yahoo when the market is open | Partial | `_quote_extras` bid/ask (stale crossed books blanked) | High | Observed spread when available, else a labelled model estimate | High |
| 19 | Transaction taxes | `instruments.TAXES` (UK SDRT 0.5%, FR 0.4%, IT 0.1%, IE 1% …) | Working | instruments.py | High | Use in pre-trade and simulated fills | High |
| 20 | Exchange hours and holidays | CDR (22 exchanges, `holidays` package) | Working | workbench.exchanges | Medium | Next session / closed-today flag in pre-trade | Medium |
| 21 | Economic calendar with consensus, central-bank decisions | ECO (Forex Factory feed + ALFRED), central-bank next decisions | Working | econ_calendar; cb_decisions | High | Country-relevant releases in pre-trade | Medium |
| 22 | Corporate events (earnings dates, dividends, splits) | EVTS, CACS, DVDC | Working | earnings_calendar, corporate.actions_calendar | High | Per-stock next events, scheduled vs estimated | High |
| 23 | Regulatory / product / contract announcements | News per holding | Partial | headline news only, no event typing | Low | Keep as news; not a calendar (no reliable dates) | Low |
| 24 | Portfolio risk (VaR, stress, factor, correlation, drawdown) | Multiple panels | Working (USD) | portfolio analytics, VaR & Stress | High | Base currency (#2) | High |
| 25 | Benchmark-relative (active weights, TE, Brinson) | vs SPY | Partial | `brinson(benchmark="SPY")` | High | vs the BIFS benchmark; active weights at country/sector level only where proxy data allow | High |
| 26 | Order lifecycle with four-eyes approval | Orders: Pending → Approved → Executed / Rejected; audit log | Working | fund router orders + audit_store | High | Link orders to pitches and pre-trade assessments | Medium |
| 27 | Trade journal | JRNL (Markets), blotter, decision log | Working | usertools journal; blotter_store | Medium | — | — |
| 28 | TCA after execution | Fills vs arrival/close | Working | portfolio_analytics TCA | Medium | Compare with the pre-trade estimate | Medium |
| 29 | Audit log | Append-only (DB trigger) | Working | audit_store | High | — | — |
| 30 | Data lineage / freshness / source monitoring | Freshness for FRED + quotes; source monitor (14 sources) | Working | source_monitor tests | High | — | — |
| 31 | Quant Lab / LEAN / options engine | Built-in layer, real LEAN, research checks | Working | 1,014 tests | Medium for BIFS | Preserved as is | — |
| 32 | Access control on internal data | Sensitive-read prefixes | Working (fixed today) | test_access_sensitive_reads | High | — | — |
| 33 | Reporting / export | Daily brief e-mail, PDF/CSV report, CSV/JSON data API | Working | brief_delivery, report endpoint | Medium | Pre-trade assessment export | Low |

## 2. Data limits (stated, not worked around)

* **MSCI index levels and constituents are licensed.** The benchmark is proxied by accumulating UCITS ETFs (net of
  their fees, ~0.2–0.3% a year); index constituents and official weights are not available, so active weights are
  limited to what the ETF proxies disclose. The equal-weighted half exists only from **4 Sep 2024** (MWEQ.L launch).
* **Spreads and market impact are estimates** unless a live bid/ask is present; they are labelled as such.
* **Fundamentals** come from Yahoo (company filings as reported there); point-in-time history is SEC-only (US).
* **Guidance changes** have no free structured source.

## 3. Upgrade plan (implemented in this order)

1. Multi-currency accounting: entry-date FX cost basis, cash, local/FX P&L split, blotter currency, base-currency
   (GBP) valuation. (#1–#4)
2. BIFS benchmark series (GBP NTR proxy blend) and benchmark-relative performance. (#5, #25)
3. Pre-trade feasibility assessment: technical snapshot, liquidity, observed/estimated spread, impact, commission,
   taxes, FX conversion cost, hours, events, mandate rules, portfolio impact, pitch fair value → feasibility flags and
   a staging suggestion. (#7, #10, #16–#22)
4. Analyst pitch review: versioned pitches, scenarios, kill criteria with automatic checks, PMC decision. (#9)
5. Simulated fills with modelled spread, impact and taxes. (#8)
