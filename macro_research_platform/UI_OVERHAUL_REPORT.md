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
| **1 — full lineage layer** | Partial (primitives exist) | The reconciliation loop + per-metric lineage object is a cross-cutting change to **every** metric-producing endpoint and the store — large, high-regression; needs its own pass. |
| **2 — storytelling / explanation strings** | Not started | Requires each calculation to expose **sub-component contributions** (which series moved, by how much) — a backend change across growth/inflation/liquidity/regime calcs, then an `explanation_text` field + hover attribution. Substantial. |
| **3 — anomaly strip + badges** | Backend math exists; UI not built | Tractable next: aggregate z-scores into one `/api/v1/anomalies` endpoint + an Anomalies strip + `AnomalyBadge`. Deferred for scope. |
| **4b — regime-conditional correlation** | Not done | Needs historical regime-labelled periods to filter the matrix; the regime history store isn't wired to the correlation endpoint. |
| **5 — unify MetricCard everywhere** | Not done | Mechanical but wide (dozens of sections); risk of visual regressions without a screenshot pass per section. |
| **6 — predictive panels** | Not done | Event-vol forecasting needs historical realized-vol-around-events series; regime-transition matrix exists in backend but isn't surfaced as a forward panel. |
| **7 — command palette NL routing** | Not done | Palette exists; needs a `{keywords,route,filter}` registry + fuzzy router. |
| **8 — transparent personalization** | N/A | No smart-ordering added, so nothing to explain — compliant by absence. |
| **9 — standards** | Partial | ✅ new backend field tested; ✅ reusable primitives (`CorrelationHeatmap`); ✅ one chart lib (recharts); ✅ 3-state resolution. Applies to Phase-4 work only. |

---

## Recommended next pass (highest value first)
1. **Phase 3 Anomalies strip** — backend z-score math already exists; wrap into `/api/v1/anomalies` + a pinned strip + `AnomalyBadge`. Small, high-signal.
2. **Phase 4b** regime-conditional filter on the heatmap (connects regime engine to correlations).
3. **Phase 1** lineage popover on the existing `SourceTag` (the primitive is already there).
