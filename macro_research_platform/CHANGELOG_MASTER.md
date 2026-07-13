# MACRO OS v8.0 — MASTER CHANGELOG

**Single source of truth for all changes.** This consolidates every prior report
(`CHANGELOG.md`, `CHANGELOG_OVERHAUL.md`, `IMPROVEMENT_LOG.md`, `SWEEP_REPORT.md`,
`METHODOLOGY_UPGRADE_REPORT.md`, `BUGFIX_ROUND_REPORT.md`, `FULL_VERIFICATION_REPORT.md`,
`OVERHAUL_REPORT.md`, `UI_OVERHAUL_REPORT.md`, `PERFORMANCE_REPORT.md`, `CLEANUP_REPORT.md`,
`DATA_LAYER_REPORT.md`, `DATA_COVERAGE_AUDIT.md`, and the audit MDs) into one document.

Guiding principle throughout: **real data or an explicit, reasoned "unavailable" state — never a
plausible-looking fabricated value.** Everything is verified against the live running system, not
just code review.

---

## 1. Current data-integrity & global-coverage status

### Data integrity (hardcoded / fabricated-data sweep)
Fabricated-data-served-as-live is the highest-severity class and has been removed wherever found:

| Was fabricated | Fixed to |
|---|---|
| `/api/earnings/revisions` hardcoded per-sector EPS table (stamped `now()`) | Structured absence (`available:false` + reason); frontend shows "—" |
| `/api/portfolio/attribution` (legacy) hardcoded factor/sector table | Structured absence; real attribution lives at `/api/v1/portfolio/attribution` |
| News Sentiment = a VIX stub | Real RSS-headline sentiment (`news_sentiment.py`) |
| Transmission channels = empty stub | 6 real monetary-transmission channels from live rates/curve/credit |
| `calculate_trend_signals` / `_get_sample_trend_signals` (238 lines) fake CTA table | **Deleted** (dead code; live CTA reads the dashboard handler) |
| Market-clock holidays hardcoded per-year | `python-holidays` library — per-region, any year, lunar-aware |

**Remaining hardcoded values are legitimate defensive fallbacks** (e.g. `ten_yr or 4.5` when a
live feed momentarily fails, `data_pipeline.py` fallbacks which are **dead/unused**), not values
presented as live. The verification suite (`api/tests/regression/`) asserts the fabricated tables
can never return.

### Global vs US-centric coverage
The market / price / FX / correlation layer is now genuinely **global**:

| Global (real, multi-region) | Endpoint |
|---|---|
| 10 world equity indices / 9 regions (S&P, Nasdaq, FTSE, DAX, Euro Stoxx, Nikkei, Hang Seng, Shanghai, ASX 200, Nifty) | `/api/global-markets` |
| 20 FX pairs, region-grouped (G10 + Asia CNY/INR/KRW/SGD/HKD/TWD + EMEA/LatAm BRL/MXN/ZAR/TRY) | `/api/fx-rates` |
| 16-market cross-correlation matrix (indices + FX + Gold/WTI/UST) | `/api/global-correlation` |
| Cross-country macro (US, Euro Area, UK, Japan, Canada, Australia — CPI/unemployment/10Y) | `/api/regional-macro` |
| Market clock — 6–7 global exchanges w/ real per-region holidays | `/api/market-hours` |
| International macro (EA/UK/JP GDP+CPI), FX, commodities | pre-existing |

**Legitimately US-specific by design** (not gaps): the US recession probit, Fed policy path, and
US yield-curve model — these are US *models*; a parallel ECB/BoJ version is a new feature, not a
fix. **Honest remaining frontier:** ~51 macro-signal panels (regime, nowcast, liquidity, factor
rotation) compute on US FRED series; truly regionalizing each needs its own regional feed — a
scoped, one-panel-at-a-time project (the Regional Macro panel is the template). See §4.

---

## 2. Changelog by theme (chronological within each)

### Foundation & data-truth layer
- Live data everywhere: replaced synthetic commodity/FX/price data with live **yfinance**; live
  **FRED** growth/inflation/fed-funds; live **ICE BofA** credit spreads; stopped prices flipping
  to fake fallbacks on rate-limit.
- Fixed the recession probit + yield-curve long-end extrapolation; corrected Recession Risk
  (0%→13%) and Regime confidence (1%→76%) display bugs.
- **Data-trust layer:** per-source health endpoint + header indicator; provenance/source +
  freshness tags on dashboard-computed panels; per-field staleness flags; Data Integrity indicator.
- **Universal data layer:** provider-agnostic registry with automatic failover.
- Structural: extracted 63 Pydantic models + routers/utils from `main.py`; removed 291 unused
  imports; killed the `dict.price` crash class; eliminated all 12 runtime 500s; repaired the
  production build.

### Institutional research methodology (Bridgewater / AQR / risk-parity)
- **Four Quadrants** (growth-surprise × inflation-surprise) + playbook + cross-validation —
  `quadrants.py`, `/api/v1/quadrants`.
- **Risk-parity overhaul:** Traditional/Return-overlay/HRP/CVaR vs 60/40, honest backtest;
  bootstrapped risk-contribution fragility bands — `risk_parity.py`, `/api/v1/risk-parity-compare`.
- **3-stream signal agreement** (macro/intermarket/flows → sizing) — `/api/v1/stream-agreement`.
- **Factor OOS validation** (in- vs out-of-sample R², flags unstable factors) —
  `/api/v1/factor-validation`; flagged Momentum unstable (0.71→0.30).
- Citations + Model Confidence on `/api/v1/methodology`. All with known-answer tests.

### UI overhaul (9 phases)
Data-lineage popover; signal storytelling (auto-explanations + change attribution); system-wide
anomaly strip; regime-transition early-warning; event-driven vol forecast; unified MetricCard;
cross-asset correlation heatmap; command-palette NL routing; Data Integrity header indicator.

### Portfolio / risk / audit (Phases 1–9)
Position ingestion; multi-factor risk model; VaR / stress / concentration / liquidity;
walk-forward signal backtesting + scorecard; performance attribution; trade-idea workflow +
what-if; alt-data (VIX term structure, correlation breakdowns, credit stress); decision log +
point-in-time snapshots; automated data-quality / bad-tick detection.

### Bug-fix & verification rounds
- COT panel was orphaned (rendered nowhere) → wired in; transmission stub → real channels.
- **Regime contradiction:** `/api/v1/regime-transition` showed Stagflation/Slowdown (flip-flopping)
  vs the app's "expansion" — root cause: current classified by a raw-level classifier while its
  own history used z-scores; fixed to derive current from the z-score history (stable Goldilocks,
  labelled as a complementary growth×inflation quadrant lens).
- `/api/ask` 503 → rewired to canonical dashboard data + numeric confidence.
- Calendar/horizon CPI dates disagreed → unified on the FRED release-date source.
- Risk-label collision ("Risk Score" vs header "Risk") → "Risk Appetite" + clear position stance.
- Factor Rotation empty panel → schema mismatch fixed (renders real 4 factor scores).

### Regression-locking (structural fix for recurring bugs)
`api/tests/regression/` — 13 in-process `TestClient` tests locking every fix above so it cannot
silently regress. Scoped bug-class sweeps (impossible values, unit mismatches, silent catches,
placeholders, unbounded loading, field mismatches, labels, hardcoded lists). `useApiData` given a
bounded 12s timeout + one retry (was unbounded — could spin forever).

### Performance & polish
Short-TTL response cache on slow endpoints; background warm loop threading heavy analytics
(cold-start mount-storm eliminated); narrowed store selectors + batched WebSocket updates;
removed 4 unused frontend deps; design tokens + icon-button a11y.

### Global data expansion (this frontier)
Global markets panel; broad FX board; global correlation matrix; regional macro comparison;
real per-region market-clock holidays; **section render order aligned to the sidebar** (68→70
sections, validated 1:1); dedup of the long-term CMA forecast builder; disambiguated the two
regime panels ("Transition Matrix" vs "Shift Outlook").

---

## 3. Full commit history (authoritative record)

The complete chronological record is `git log`. Regenerate the one-line list any time with:

```
git log --oneline --reverse
```

126 commits from `Initial commit: Macro Terminal v8.0` through the global-data expansion. Key
milestones are summarised by theme in §2; every commit message states its own root cause.

---

## 4. Honest known limitations / remaining work

1. **Per-region macro-signal engine** — the biggest frontier. ~51 signal panels compute on US
   FRED series. Regionalizing each (regime, nowcast, liquidity, factor rotation per region) needs
   a curated regional data feed per indicator + a region selector. The Regional Macro Comparison
   panel is the first bounded piece / template; the rest is a scoped follow-on project.
2. **US-specific models stay US** by design (recession probit, Fed path, US curve) — correct as-is.
3. **Holiday calendars** now come from `python-holidays` (any year); Asian lunar calendars depend
   on that library staying current.
4. **Sampled, not exhaustive** sweeps (per `SWEEP_REPORT`): numeric-bounds beyond the dashboard,
   units, field-mismatches across all ~70 components — spot-checked clean, not 100% per-instance.
5. `data_pipeline.py` is dead/unused legacy (hardcoded fallbacks) — safe to delete in a future
   cleanup; left in place to avoid churn this round.

_Run the regression suite before any future bug-fixing session:_ `pytest api/tests/regression/ -v`.
A failure there is a true regression, not a re-discovery.
