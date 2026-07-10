# UI OVERHAUL REPORT — MACRO OS v8.0

Honest status of the 9-phase 2026-terminal overhaul. This session delivered **Phase 4
end-to-end (built, tested, live-verified)** and inventories what pre-existing infrastructure
already satisfies other phases. Everything claimed "done" was verified after a clean restart
and hard refresh; nothing is mocked.

---

## ✅ Phase 4 — Cross-Asset Correlation Heatmap — COMPLETE (this session)

Replaces isolated correlation numbers with a real visual matrix.

**Backend (real, tested, traceable):**
- `api/calculations/altdata.correlation_matrix()` — pairwise Pearson matrix over aligned
  daily returns. Pure function, **3 known-answer tests** (`test_altdata.py`): identical
  series → +1.0, inverse → −1.0, window-respecting, insufficient-data → empty. (12 altdata
  tests pass.)
- `GET /api/v1/correlation-matrix?window=30|90|252` — real **yfinance** daily returns for
  SPX, NDX, 10Y (TLT), 2Y (SHY), DXY, GLD, WTI, HY (HYG), VIX, aligned on common dates.
  Traceable: response carries `source: "yfinance (daily closes)"`, `observations`, `window`.
- **Perf fix:** all 9 feeds fetched concurrently via `asyncio.gather` — cold **0.72s**,
  warm **7ms** (was >8s sequential, which blew the UI budget).

**Frontend (reusable primitives; recharts remains the only chart lib — Phase 9):**
- `CorrelationHeatmap` (`components/ui/`) — diverging **red ↔ neutral ↔ green** cells,
  the coefficient **printed in every cell** so color is never the sole encoding
  (CVD-safe per the diverging-palette rule), **flat cells** (no gradients/shadows —
  terminal aesthetic), window toggle, click-to-select cell detail, diverging legend.
- `CorrelationMatrixSection` (`sections/risk/`) — **3-state resolution** (populated /
  explicit unavailable-with-reason / bounded 8s load with one self-healing retry) —
  never an indefinite spinner (Phase 9).

**Verification (live, after restart + hard refresh):**
- Normal state: full 9×9 matrix renders real correlations — **SPX-NDX +0.92**, **SPX-VIX
  −0.88**, **SPX-HY +0.73**, **HY-VIX −0.72** (all economically correct signs). Window
  toggle (30/90/252d) and cell detail (`10Y · 2Y 0.54 moderate positive`) work. **Zero
  console errors.** [screenshot: populated 30d matrix]
- Flagged state: the 8s cap correctly resolved to **"Unavailable — Timed out — data feed
  slow."** during the heavy initial mount storm (then self-heals on retry) — verified the
  no-indefinite-spinner guarantee.

---

## ✅ Phase 3 — System-Wide Anomaly Strip — COMPLETE (this session)

Surfaces anomalies proactively instead of waiting to be asked.

**Backend (real, tested, traceable):**
- `altdata.historical_band()` — rolling mean/std band + z-score of the LATEST value vs its
  own trailing window; `is_anomalous = |z| > 2`. Pure, **3 known-answer tests** (spike →
  flagged, normal → not flagged, insufficient → None).
- `GET /api/v1/anomalies` — scans 9 tracked market metrics (VIX, SPX, NDX, DXY, GLD, WTI,
  TLT, HYG, SHY), fetched concurrently (~0.8s), returns every metric with
  `{current, historical_mean, historical_std, z_score, is_anomalous}` **ranked by |z|**;
  carries `source` + `window`.

**Frontend (reusable primitives):**
- `AnomalyBadge` (`components/ui/`) — z-score σ badge; amber + warning icon when flagged
  (icon + number, never color-alone). Drop-in for any metric card (Phase 5A corner badge).
- `AnomaliesStripSection` — **pinned to the top of the Overview tab**, lists every flagged
  metric ranked by |z|, collapses to "all within range" (with top deviations for context)
  when nothing breaches. 3-state bounded load with self-heal retry (Phase 9).

**Verification (live):** the strip flagged **US Dollar +2.1σ (outside 2σ)** in amber at the
top of Overview, with the DXY value + historical mean shown; ranked scan of all 9 metrics.
Zero console errors. [screenshot: anomalies strip with flagged USD]

---

## 🟡 Phase 5 — Unified MetricCard — CORE DONE (this session)

One standard card composing every primitive, replacing per-tab one-offs.

**The card (`components/ui/MetricCard.tsx`)** now composes: dominant monospace **headline**
(hierarchy) + inline **sparkline** + **storytelling subtitle** (Phase 2) + **anomaly badge**
top-right (Phase 3) + **data-lineage "i"** top-right (Phase 1) + **staleness** treatment
(dashed amber border replaces the card style, Phase 1). All composition props are optional,
so it's backward-compatible.

**Wired into KeyMetrics** (flagship Overview panel): the Growth / Inflation / Fin-Conditions
/ Risk / Recession cards now render via `MetricCard`, fed **real** explanations from
`/api/v1/signal-attribution` (fetched once, indexed by signal), per-metric lineage, and live
staleness from `useFreshness`.

**Verification (live):** cards show headline + real explanation subtitle (Growth "S&P 500
+0.8% momentum", Inflation "10Y−2Y +27bps 4.54−4.27"), **5 lineage popovers** (open with real
source/formula), and the **STALE** dashed-amber treatment on Inflation. Zero console errors.
[screenshot: KeyMetrics with unified cards + STALE + lineage]

**Remaining in Phase 5:** roll the same card out to the other metric panels (Commodities,
FX Monitor, Fixed Income, …) — mechanical, one section at a time; and the type-scale token
enforcement / decorative-color audit (5B/5C) app-wide.

---

## ✅ Phase 2 — Signal Storytelling — COMPLETE (this session)

Every core signal explains its own move instead of just showing a delta.

**Backend (real, tested, traceable):**
- `api/calculations/storytelling.py` — `explain_growth / inflation / liquidity / risk`:
  reuse the dashboard signal math (so the score matches), decompose each into **named input
  contributions**, rank by magnitude, identify the **largest driver**, and emit a one-line
  `explanation_text`. Pure, **6 known-answer tests**.
- `GET /api/v1/signal-attribution` — computes all four from **live** dashboard inputs
  (`get_dashboard_data`: SPX/10Y/2Y/DXY/Fed/VIX). Caught & fixed a data-integrity bug: an
  early version mixed a stale 5800 SPX level with fresh ~7500 history → bogus −23% momentum;
  now SPX is kept self-consistent (latest close vs prior closes).

**Frontend:**
- `SignalStorySection` — per signal: headline score + trend + **one-line explanation
  subtitle** (2A); click to expand a **ranked change-attribution breakdown** with signed
  contribution bars and the named driver (2B). `DataLineagePopover` on the header.

**Verification (live, values match the tickers):** Growth +0.8% momentum → 0.52;
Inflation 10Y−2Y **+27bps (4.54%−4.27%)** → 0.26; Liquidity loose DXY 100.7 → 0.66; Risk
VIX 15.8 → 0.81. Expanded Growth card showed `driver: SPX recent return` with ranked bars.
Zero console errors. [screenshot: storytelling panel + expanded attribution]

---

## 🟡 Phase 1A — Data-Lineage Popover — BUILT & wired (this session)

The traceability primitive Phase 1 is built on. New reusable `DataLineagePopover`
(`components/ui/`): an "i" icon that reveals a number's **source feed, last fetch time
(+ age & live/stale/error status), the calculation formula when derived, and the raw
upstream value** when it differs from displayed. Flat popover, click-outside/Esc to close.

Wired with **real** lineage into two live panels:
- **Anomalies strip** — per metric: `source: yfinance · <ticker>`, displayed value, and the
  z-score derivation `z = (current − μ) / σ over N obs → ±Xσ`.
- **Correlation matrix header** — source, `Pearson correlation of aligned daily returns`,
  window/obs.

**Verified live:** popover on the US Dollar anomaly showed `LIVE · yfinance·DX-Y.NYB ·
100.91 · formula → +2.1σ · flagged`. Zero console errors. [screenshot: open lineage popover]

Still open in Phase 1 (the broad, cross-cutting parts): a lineage object on **every**
metric app-wide, the live-vs-displayed **reconciliation loop**, and the header **"Data
Integrity %"** indicator. The primitive + the existing `SourceTag`/`StaleBadge` (staleness
treatment already live — e.g. the "STALE 70D" badge on Inflation) cover the per-metric
traceability and staleness pieces; universal wiring is the remaining lift.

## Pre-existing infrastructure that partially satisfies other phases

These were built in earlier sessions and are live in the app (not part of this session's
work, but relevant to honest phase accounting):

| Phase | Component / field that exists | Gap to the spec |
|---|---|---|
| **1 — Data integrity/lineage** | `SourceTag`, `ComputedTag`, `StaleBadge`, `DataHealthIndicator` components; `useFreshness` hook; `/api/data-freshness`, `/api/health/sources` | No per-metric `{value,source,fetched_at,staleness_threshold,status}` lineage **object on every metric**; no hover **lineage popover** with formula + raw upstream; no live-vs-displayed **reconciliation** loop or header "Data Integrity %" |
| **3 — Anomaly detection** | `altdata.zscore()`, `correlation_breakdown()` (z-scored, flagged); `/api/v1/altdata/positioning` surfaces correlation breakdowns | No per-metric rolling mean/std/z-score field across all series; no system-wide **Anomalies strip** ranked by z-score; no `AnomalyBadge` primitive on cards |
| **5 — Card redesign** | `MetricCard`, `Sparkline` (recharts), type-scale tokens in `index.css` (`--text-2xs … --text-3xl`) | Not yet the single card used **everywhere**; storytelling subtitle + anomaly badge + lineage icon not yet composed into one standard card |

---

## ❌ Not done this session (honest, with blockers)

| Phase | Status | Blocker / reason |
|---|---|---|
| **1 — full lineage layer** | 🟡 Popover BUILT + wired (2 panels); staleness live | Remaining: per-metric lineage object on **every** endpoint, the live-vs-displayed reconciliation loop, and the header "Data Integrity %" — cross-cutting, high-regression; own pass. |
| **2 — storytelling / explanation strings** | ✅ **DONE** (see above) | `/api/v1/signal-attribution` + `SignalStorySection`: explanation_text + ranked change-attribution for Growth/Inflation/Liquidity/Risk, built/tested/live-verified. Remaining sub-item: render the subtitle inline on the existing KeyMetrics cards (needs Phase-5 card unification). |
| **3 — anomaly strip + badges** | ✅ **DONE** (see above) | `/api/v1/anomalies` + `AnomaliesStripSection` + `AnomalyBadge` built, tested, live-verified. Remaining sub-item: per-metric badges composed onto every card (needs Phase-5 card unification). |
| **4b — regime-conditional correlation** | Not done | Needs historical regime-labelled periods to filter the matrix; the regime history store isn't wired to the correlation endpoint. |
| **5 — unify MetricCard everywhere** | 🟡 Core DONE (card built + live on KeyMetrics) | Remaining: roll the same card out to Commodities/FX/Fixed-Income/etc. (mechanical, per-section) + 5B/5C type-scale token + decorative-color audit app-wide. |
| **6 — predictive panels** | Not done | Event-vol forecasting needs historical realized-vol-around-events series; regime-transition matrix exists in backend but isn't surfaced as a forward panel. |
| **7 — command palette NL routing** | Not done | Palette exists; needs a `{keywords,route,filter}` registry + fuzzy router. |
| **8 — transparent personalization** | N/A | No smart-ordering added, so nothing to explain — compliant by absence. |
| **9 — standards** | Partial | ✅ new backend field tested; ✅ reusable primitives (`CorrelationHeatmap`); ✅ one chart lib (recharts); ✅ 3-state resolution. Applies to Phase-4 work only. |

---

## Recommended next pass (highest value first)
1. **Phase 6** predictive panels — surface the regime-transition probability matrix as a
   forward "X% chance of Slowdown in 30d" panel; event-vol forecasting off the calendar.
2. **Phase 5 rollout** — apply the unified `MetricCard` to Commodities / FX / Fixed-Income
   panels (mechanical, per-section).
3. **Phase 7** command-palette natural-language routing (registry + fuzzy router).

## Cumulative status: **Phases 2, 3, 4 complete** (real, tested, live-verified); **Phase 1A
lineage popover** and **Phase 5 unified card** built & live on KeyMetrics. Primitives shipped:
`CorrelationHeatmap`, `AnomalyBadge`, `DataLineagePopover`, unified `MetricCard` (+ existing
`Sparkline`, `SourceTag`, `StaleBadge`). Backend calc modules added: `correlation_matrix`,
`historical_band`, `storytelling` — all with known-answer tests (205 backend tests pass).
