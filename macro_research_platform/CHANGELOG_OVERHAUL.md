# MACRO OS — Institutional Overhaul Changelog

Honest record of what was rebuilt, hardened, and added — and what is **not yet**
institutional-grade. Work is on branch `fix/macro-os-repair` (open PR #1 covers the
correctness fixes; the overhaul increments below are additional local commits).

Every item marked ✅ was verified in the live UI (backend on :8000, Vite on :5173)
after a clean restart, not just via curl.

---

## 1. Correctness rebuilt (PR #1 — 14 commits)

Fixed real, capital-relevant data bugs and eliminated every crashing/placeholder panel:

- **Recession probability** returned 100% at a normal curve → NY-Fed Estrella-Mishkin
  probit on the 3m10y spread in percentage points (~correct). ✅
- **Yield curve** long-end corruption (30Y 10.49%) → realistic term premium. ✅
- **Live FRED** restored (`CPIAUCSL_PC1` 400 → `units=pc1`); killed `ALL SOURCES FAILED`
  spam; live fed funds (was hardcoded 5.25). ✅
- **Live market data**: commodities / FX / index prices with real 1d/1m/3m changes +
  52w percentiles; live ICE BofA credit spreads with 1-week change; prices no longer
  flip to a fake `5800` on rate-limit. ✅
- **Dashboard latency** 15-20s → ~2ms via TTL cache + startup warm loop (was blocking
  the entire UI from loading within the 8s frontend timeout). ✅
- **12 sections** that crashed into their ErrorBoundary on backend/frontend shape
  mismatch now render the real data (Regime Playbook, Equity Research, Trade Recs,
  Debt Cycle, Advanced Indicators, Risk Indicators, Liquidity, Valuation, Factor
  Decomposition, CTA Trends, GMO Forecasts, International Macro). ✅
- Morning Brief ensemble (Neutral/Static/0% → Strong Risk-On/Dynamic/81%), Recession
  Risk (0%→13%), Regime confidence (1%→76%), momentum (+1820%→+18%), FX +0.00% → real
  changes. ✅

## 2. Data-trust layer hardened

- **Per-source feed health** — `/api/v1/health/sources` actively probes FRED, market
  data, and the DB with latency; header **`● FEEDS n/total`** indicator with per-source
  hover tooltip (status/latency/detail/last-checked), 30s poll. Correctly flips
  green↔amber as feeds degrade. ✅
- **Panel provenance tags** — reusable `SourceTag` ("SOURCE · age", amber/dashed when
  STALE) on 17 panels: market panels from real `lastUpdated`, 14 computed panels via
  `ComputedTag` ("Computed · Nm ago"). ✅
- **No fake numbers** — Expected Returns "NaN%" → real value; broken-number guards. ✅

## 3. Calculation rigor

- **`api/calculations/models.py`** — core formulas as pure, documented, clamped
  functions (recession probit, yield spread, copper/gold ratio, 12-1 momentum,
  ensemble agreement, inverse-vol risk parity), each with formula/inputs/units/range/
  citation. `market_handler` calls these, so **live code == tested code**. ✅
- **34 bounds-check unit tests** (`api/tests/test_calculations.py`) — the checks that
  would have caught the historical bugs (recession ∈ [0,1] and ~0.45 at −0.66pp;
  momentum ∈ [−100%,+300%]; agreement/weights ∈ [0,1]; rejects bps-as-pp). All pass,
  incl. an end-to-end TestClient hit on the methodology endpoint. ✅
- **`/api/v1/methodology`** + in-app **Model Info panel** (header ƒ button) showing
  each model's formula, inputs, range, and citation — auditable before trusting
  capital. ✅

## 4. Workflow / reporting

- **Per-table CSV export** — RFC-4180 util + `CsvButton` building CSVs from real
  underlying values (not scraped DOM) on GMO Forecasts, Factor Decomposition,
  Commodities, FX. ✅
- **Pin panels** — per-user, localStorage-persisted "★ PINNED" group in the sidebar
  for one-click access to most-watched panels (capped at 8). ✅
- **Keyboard navigation** — number keys 1-9 already jump to main sections (verified);
  F1-F7 section groups; letter shortcuts; ⌘K palette. ✅

---

## Known limitations — NOT yet institutional-grade

Being explicit rather than overstating completion:

- **Per-field staleness** — provenance is currently at panel granularity. An
  *individual* metric that is stale (vs its whole panel) does not yet get isolated
  amber treatment; that needs `value/source/last_updated/staleness` metadata threaded
  through every field in the backend response schema.
- **Some panels still serve synthetic data** — e.g. sector-allocation EPS-revision
  figures, parts of the risk/attribution sub-tabs, and non-US yield curves are
  plausible-but-synthetic. These should be wired to real sources or marked
  `{available:false, reason}` before capital use.
- **Density / IA redesign not done** — the layout is still a long scroll, not the
  Monitor/Decide/Manage multi-panel grid the brief envisions. Deliberately deferred
  as a large, opinionated change.
- **Charting** — Recharts is the single library, but axis/tooltip/palette conventions
  are not yet standardized across all charts, and there are no two-series overlays.
- **"Copy as image" & Morning Brief PDF** — CSV export exists; image capture (needs a
  new dependency) and a dedicated one-click Morning Brief PDF snapshot do not.
- **Auth & audit** — demo auth exists; there is no `decision_log` recording user
  state changes (position sizing, overrides) with user/timestamp/reason, nor API
  rate-limiting/request-logging for reproducibility.
- **API versioning** — `/api/v1/health*` and `/api/v1/methodology` are versioned; the
  bulk of endpoints remain unversioned `/api/*`.
- **Repo hygiene** — `node_modules` is committed to git history (not gitignored),
  which bloats clones/pushes and should be purged separately.

---

_Generated as an honest state-of-work summary. See branch `fix/macro-os-repair`._
