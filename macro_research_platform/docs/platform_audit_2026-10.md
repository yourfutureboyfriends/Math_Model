# Macro Terminal — page-by-page audit against professional platforms (19 October 2026)

Method: every panel of the eight Research & Trading tabs and all 66 Markets functions (plus a security page) was opened
in the running app, its content read and checked for errors, staleness and internal contradictions, and compared with
the professional tool that does the same job (Bloomberg Terminal functions, Refinitiv/LSEG Workspace, FactSet, MSCI
Barra/RiskMetrics, Macrobond, Koyfin, QuantConnect). **Fixed** = changed and tested in commit 4a5bf46c;
**open** = still to do. Data limits are stated where the gap is the free-data ceiling rather than the software.

## Bugs found and fixed

| Where | Problem | Fix |
|---|---|---|
| Test suite | Tests wrote to the live database: 297 "Test trend" deploy/stop rows in the audit log (9–19 Oct) | tests use a throwaway database (verified: audit log 435 → 435 rows across a full run) |
| Branch | A pushed commit imported an uncommitted module (`api.routers.options_engine`) — a clean checkout failed to start | import made optional (48059e8f) |
| My Desk, Fund Overview | Track record "Sharpe 14.79" from 7 daily NAVs | ratios need 60 daily returns; returns annualised only after a year (GIPS) |
| Fund NAV | No snapshots 14–16 Oct: the daily snapshot ran only if the server was up at 21:30 UTC | catch-up on start after the close (no back-dated snapshots — they would use later prices) |
| Macro Model | Header "run —" | shows when the model was computed |
| FX Monitor | Majors "NY close 2026-10-16" during Monday's session while DXY was live | live 5-minute spot with the change from the last NY close; both times shown |
| RISK, RRG, curves, research pages | "As of 2026-10-23" on 19 Oct — weekly resampling dated the week in progress with the coming Friday | weekly series end on the last real observation (8 call sites) |
| AUCT | Auction dates "None", bidder shares blank (TreasuryDirect renamed its fields) | current fields read; indirect/direct/dealer shares of competitive awards restored |
| MEMB | Sector column empty (SSGA's file now has "-") | filled from instrument data (463/504 S&P names) |
| Sector Allocation | 7 of 11 GICS sectors; "Overweight" Financials at a −0.08 score beside "Neutral" Healthcare at +0.42 with no explanation | all 11 sectors; playbook stance and signal shown as separate columns |
| CFTC Positioning | "EXTREME SHORT" euro with signal "NEUTRAL" (the backend never set the contrarian signal) | crowded short → fade-short, crowded long → fade-long |
| Signals | Growth "deteriorating" (attribution) vs "BULLISH 69%" (breakdown) for the same reading | text states level and direction: "strong but slowing" |
| Pre-trade ideas | Each idea twice; "SHORT ^VIX" (an index — not tradable) | open duplicates merged (orders never); volatility ideas use VIXY with the reason |
| Security pages (DES) | Quote grid labels overlapped in the docked pane; P/E, market cap, EPS shown for FX pairs | grid fills by the pane's width; company fields hidden for FX, indices, crypto |
| Quant Lab (QuantConnect layer) | EMA, ADX, MAX/MIN differed from LEAN; long-only rotation went short (order ids lost) | matched to LEAN's reference data (16 tests); ids recorded before clearing |

## Open findings, by page

### MY FOCUS
| Page | vs professional | Missing / open |
|---|---|---|
| My Desk | Bloomberg LAUNCHPAD / a PM dashboard | P&L by book and by strategy today; limit headroom bars; one-click to the items in "Your queue"; **4 accounts on default passwords** is shown as a queue item but nothing forces a change |
| Daily Brief | Bloomberg morning note (BN/First Word), sell-side morning call | Priorities are generic and all "Action required"; no overnight moves, earnings, positioning or what changed since yesterday |
| Composite Signal | — (house model) | No history chart of the composite or its hit rate in this panel |
| Fund Overview | Bloomberg PORT / Enfusion | NAV is 99.8% cash with four positions created within one minute on 8 Jul (look like test/demo — **your call**); no benchmark, no fees/accruals, no subscriptions/redemptions |
| Trade Ideas | Bloomberg IDEA / sell-side idea trackers | "Last updated: Real-time" (no timestamp); no idea P&L tracking after entry |

### OVERVIEW
| Page | vs professional | Missing / open |
|---|---|---|
| Macro Indicators | Bloomberg ECST, Citi Economic Surprise | "Growth" is the S&P's momentum, not economic data — label it market-implied growth, or add an activity composite |
| Anomalies | Bloomberg ANOM | fine; add a click-through to the series |
| Regime Allocation | house playbook | static playbook text — no link to the portfolio's actual exposures |
| Market Hours / Global Equity Markets / Correlations | WEI, CDR | no sparklines or valuation (P/E, earnings yield) per market |
| Global Macro | Bloomberg ECWB / WECO | good coverage; add consensus for the next decision per central bank |
| Economic Calendar | **Bloomberg ECO** | **no consensus (survey median), no actual-vs-consensus surprise, no revisions** — the defining columns of ECO; free consensus is scarce (the Markets ECST page rebuilds first-release surprises and could feed this) |

### SIGNALS
| Page | vs professional | Missing / open |
|---|---|---|
| Model Ensemble / Model Agreement | model governance (inventory, validation, decay) | "100% agreement" counts inputs that are mostly equity-price driven — report independence-adjusted agreement |
| Signal Performance | factor/IC monitoring (Barra, FactSet Alpha Testing) | the VIX vol-regime signal shows 50% hit rate, Sharpe −0.32, −27% total yet keeps full weight in the ensemble — weight inputs by out-of-sample evidence or retire failing ones |
| Signal Breakdown / Attribution / Detail | — | labels mix stances ("OVERWEIGHT" for inflation, "RISK ON" for liquidity) — one vocabulary |
| Factor Out-of-Sample Tests | Barra factor diagnostics | 4 of 5 factors flagged unstable — no consequence downstream |
| Sector Allocation | sell-side sector strategy, FactSet | EPS-revision feed unavailable (the column stays blank) |
| CFTC / Trend-Following / News | Bloomberg COT, CTA trackers, BN sentiment | news covers 4 RSS feeds; no entity tagging, no story links per holding |

### RISK
| Page | vs professional | Missing / open |
|---|---|---|
| Risk Analytics | MSCI RiskMetrics / Bloomberg PORT risk | does not say which portfolio its Sharpe 0.42 / +9.0% / beta 0.18 describe (the fund is 1.2% invested) |
| VaR & Stress | RiskMetrics | good (historical, parametric, Monte Carlo, contributions, scenarios); add liquidity-adjusted VaR and days-to-liquidate |
| Factor Exposure / Decomposition | Barra, Axioma | good with confidence intervals; add ex-ante tracking error vs a benchmark |
| Risk Parity / Comparison | — | comparison Sharpe 1.56 vs 1.04 has no stated period or costs; "Balanced" here while Leading Indicators says "Risk Parity STRESS"; 1.35× leverage not reflected in the weights |
| Leading Indicators | Conference Board LEI | LEI "unavailable" — free substitutes exist on FRED: Chicago Fed National Activity Index (CFNAI) and the NY Fed Weekly Economic Index (already used on the Markets NOW page) |
| Cycle & Systemic Risk, Debt cycle, Stock–bond correlation | — | strong, well sourced |

### FORECASTS
| Page | vs professional | Missing / open |
|---|---|---|
| Valuation | Bloomberg EQRV, Yardeni | single input (10Y real yield); S&P P/E has no history → no z-score; add CAPE / earnings yield history (Shiller data is free) |
| GDP Nowcast | Atlanta + NY Fed nowcasts | only GDPNow; add the NY Fed Staff Nowcast and a band |
| Market Sentiment | AAII, put/call, fund flows | AAII not sourced; put/call missing |
| Expected Returns / Scenario | — | intervals honest but wide (reflation 0.5–14.1%); scenario probabilities from a 465-month transition matrix — state sample per cell |
| Yield Curve / Financial Conditions / Event vol | Bloomberg GC, FCON | good |

### TRADING
| Page | vs professional | Missing / open |
|---|---|---|
| Portfolios (paper traders) | Bloomberg EMSX / AIM paper books | intraday live chart added; no order-level blotter per algo in this view (Quant Lab has it) |
| Strategy Lab | — | research models on today's universe — show survivorship status on the headline Sharpes (resid. momentum 1.23) |
| Quant Lab | QuantConnect / LEAN | QuantConnect-compatible API added (daily); intraday data, option/futures chains remain unavailable free |
| Stock Ideas / Entry Signals / Entry Backtest | sell-side screens, FactSet | entry backtest is candid about survivors; no earnings-date awareness in entries |
| Pre-Trade & Orders | Bloomberg EMSX/TOMS compliance | four-eyes approval works; no TCA after execution, no broker routing (by policy) |
| Scenario Analysis / Momentum Filter / Allocation Recs | — | fine |

### PORTFOLIO
| Page | vs professional | Missing / open |
|---|---|---|
| Positions | Bloomberg PORT / OMS | no lots, no corporate actions applied, no FX for non-USD books |
| Model Portfolio | — | sleeve holds nothing; targets staged from the Macro Model only |
| Performance Attribution | Bloomberg PORT attribution, FactSet PA | factor attribution of hypothetical held-throughout returns; no Brinson vs a benchmark on actual trades |
| Equity Research | sell-side ratings | sector ratings by relative strength contradict Sector Allocation's regime view on the same screen (Healthcare overweight here, neutral there) — label or reconcile |
| FX / Commodities / Fixed Income | Bloomberg FXIP, CMDTY, FIT | WTI 97.79 here vs 100.99 front month on CMDTY — say which contract; header ticker EUR/USD +0.16% vs board −0.27% (different reference closes) |

### SYSTEM
| Page | Missing / open |
|---|---|
| System Health | "17/17 series current" while FX majors were a session stale — freshness checks cover FRED series, not market quotes |
| Data Explorer | "Strategy Summary 0 items" |
| Audit & Compliance | the audit log should be append-only in a separate store; 297 test-generated rows remain (**your call** to remove) |

### MARKETS mode (66 functions)
Strong breadth for free data: WEI, RMON, CTRY, MOST, IMAP, CRYPTO, CMDTY (curves), MAP, CORR, RRG, EDGE, RISK, VOL,
BRDT, IMPM, UOA, COT, ENVR/AWP/DCYC/HGRL/WPWR, CHART, DATA (BDP/BDH), YAS, ILBE, FXCA, MRGR, MEMB, FSRC, DVDC, CDR,
ETFA, SPRD, CBRT, ECOS, CRED, PORT, PRED, NOW, FLOW, SHIP, FLY, QUAK, EIA, WETR, COMP, GC, BTMM, FRD, WIRP, AUCT,
WCRS, EQS, 13F, IPO, EVTS, ECO, ECST, ALRT, AI, JRNL, LP, and security pages (DES, GP, FA, ERN, ANR, HDS, DVD, OMON,
HP, BETA).

Open items listed here on 18 Oct (IPO coverage, cold ECO/ECST/RMON/MRGR loads, price-only alerts, uncited AI
answers) were closed on 19 Oct — see below.

## What professionals have that the platform lacks (priority order)

1. **Consensus and surprises on the calendar** (Bloomberg ECO/ECST, Citi surprise indices) — the single most used
   macro function; wire the existing ECST first-release data into ECO and keep survey medians where any free source
   exists.
2. **Signal governance** — a model inventory with validation status, out-of-sample decay alerts and automatic
   down-weighting of failing inputs (today a failing VIX signal keeps full weight).
3. **Benchmark-relative portfolio analytics** — tracking error, active risk, Brinson attribution on actual trades
   (Bloomberg PORT, FactSet PA); the fund has no benchmark set.
4. **Real-time news with entity tagging** and per-holding news (Bloomberg BN/NI, Refinitiv News).
5. **Field-based alerts** across any data, news and model output, with delivery (email/push) — not price only.
6. **Data quality operations** — freshness monitoring of every feed (quotes included), separated test/production
   environments, an append-only audit store.
7. **Estimates depth** — consensus EPS/revenue revisions by company (the EPS-revision feed is unavailable).
8. **Excel / API access** — Bloomberg's BDP/BDH in spreadsheets; the DATA grid exists in the app, an export API or
   add-in does not.
9. **Collaboration** — notes, shared watchlists and chat (Bloomberg IB).
10. **Intraday and derivatives data** — tick/minute history, option chains, futures curves history: the free-data
    ceiling; the paid options listed earlier (ThetaData, Polygon, ORATS) close it.

## Closed on 19 Oct 2026

| Item | What was done |
|---|---|
| Labels | WTI shown as the continuous contract (CL=F rolls ahead of the CMDTY front month); header EUR/USD change measured from the last NY close like the FX board; Data Explorer no longer shows "0 items"; scenario probabilities carry their sample (n of N months) |
| Signal governance | Ensemble weights follow out-of-sample evidence (PASS 1, WEAK ½, untested ½, FAIL 0) — the VIX vol-regime input (Sharpe −0.30, −26%) is retired from the score; agreement counts each data driver once (3 drivers, raw share shown too); factors that fail their out-of-sample test drop out of the rotation call |
| Data monitoring | Quote-freshness check per market's hours (SPY, VIX, EUR/USD, WTI) in System Health; decision log append-only by database trigger; the 297 test rows removed (backup `api/backups/macro_terminal_2026-10-19_pre_audit_cleanup.db`); ECO / ECST / RMON / MRGR, the free series and EPS revisions warmed at start |
| Free data added | Calendar consensus + actual vs forecast (weekly feed, ALFRED actuals); Shiller CAPE with history (95.7th pct since 1990); NY Fed Staff Nowcast beside GDPNow (their range as the band); AAII; CBOE put/call; Nasdaq IPO calendar; sector EPS revisions (Yahoo estimates, top-10 holdings); next central-bank decisions (fed funds futures; survey consensus when listed) |
| Portfolio | Brinson–Fachler (Carino-linked) vs SPY on the holdings actually held; ex-ante / ex-post tracking error; liquidity-adjusted VaR and days to liquidate; FIFO lots; FX on non-USD positions; TCA of all fills; trade-idea P&L; book sector exposure beside the regime targets; news per holding with tone vs the position |
| Features | Data-driven Daily Brief (overnight moves in σ, changes since the last brief, today's releases with consensus, earnings, positioning, ranked priorities); 2-year composite-signal history; My Desk P&L by book and strategy with limit headroom; field / news alerts with webhook or email delivery (opt-in in .env); AI answers cite numbered sources that open the screen; CSV / JSON data API with an Excel link builder; team notes and shared watchlists; anomaly click-through; WEI sparklines and valuation; earnings-aware entries (wait inside 5 days, half size inside 10) |

### Follow-up (19 Oct, later)
* Each composite input is now tested exactly as it votes, walk-forward since 2000 (S&P buy-and-hold Sharpe 0.42),
  and must beat holding the index to PASS: growth, liquidity and 1 − recession are WEAK (½ weight each, ⅓ after
  normalising), risk appetite FAILS (−35% long/short) and is retired. The 5-year window had failed liquidity and
  recession on the 2022–24 inversion alone.
* Agreement groups are measured, not assigned: votes correlating at |ρ| ≥ 0.5 since 2000 form one driver — equity
  prices (growth, risk, momentum, trend) and rates/curve (liquidity, recession): 2 independent drivers, not 6.
* The composite history uses point-in-time weights (evidence available before each date, refreshed monthly).
* `MACRO_TEST_OFFLINE=1` runs the suite with all outside traffic refused (sockets and libcurl); the 6 tests that read
  live data are marked `network` and skipped there.
* Still open: an on-screen check of the new panels needs a signed-in session.

## Decisions (19 Oct 2026)
* The four 8-Jul positions (AAPL 150, SPY −50, MSFT 40, GLD 30) were removed at the owner's request, logged in the
  decision log; backup `api/backups/macro_terminal_2026-10-19_pre_position_removal.db`.
* Default passwords on the analyst, pm, quant and risk accounts: left as they are by the owner's choice (a change is
  still forced at first sign-in).
