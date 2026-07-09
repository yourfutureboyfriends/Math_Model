# RUNTIME AUDIT — MACRO OS v8.0

Live end-to-end verification session. Findings logged as discovered; fixes tracked to
re-verification. Severity: **CRITICAL** (wrong data / crash) · **HIGH** (missing data) ·
**MEDIUM** (UX / latency) · **LOW** (cosmetic).

## Phase 0 — Baseline

**Git baseline was badly incomplete (fixed).** Runtime-critical backend packages
(`api/routers/*`, `api/services/*`, `api/calculations/{regime,signals,metrics,__init__}`,
`api/handlers/*`, `api/normalization/*`, `api/repository/*`, `api/validation/*`,
`api/providers/*`, `api/diagnostics.py`) and ~40 relocated frontend section files were
**untracked** despite being imported by committed code — a fresh clone would not build.
Committed as baseline: `757478f` (backend), `b453223` (frontend reorg), + docs/CI/config.
Scratch session docs and vite temp files added to `.gitignore`; stray `*.pyc` untracked.
Remaining known-debt: `node_modules/` is committed to the repo (309 churn entries, push
bloat) — scheduled for Phase 5.

App starts: backend (uvicorn :8000) and frontend (vite :5173) both run.

### Findings

| # | Endpoint/Function | Input | Expected | Actual | Severity | Status |
|---|---|---|---|---|---|---|
| 1 | `GET /api/equity-research` | default | 200 + data | 500 `AttributeError: 'dict' object has no attribute 'price'` (seen at startup; later calls 200 — likely cache-warm race or a specific branch) | CRITICAL | 🔍 investigating |
| 2 | `GET /api/health` | default | <1s | **17.7s** response time | MEDIUM | 🔍 investigating |
| 3 | FRED `FEDFUNDS` fetch | live | data or graceful fallback | `Read timed out (8s)` — external; app kept serving (graceful) | LOW | ✅ acceptable (external, degrades gracefully) |

## Phase 1 — Backend sweep (141 GET operations)

Route parity: 140 decorators in code ≈ 175 openapi operations (diff = methods sharing a
path + non-decorator routes; no orphan routes found). GET sweep hit 141 ops:
**12 CRITICAL 500s**, 4 *correct* 400s (validation working — re-verified 200 with valid
params), 12 slow (>3s, mostly live-data-bound).

### CRITICAL — 500 crashes

| # | Endpoint | Root cause (one sentence) | Fix (layer) | Status |
|---|---|---|---|---|
| 4 | `GET /api/equity-research` | `result.data.get('SPX', {}).price` — a missing key yields `{}`, and `{}.price` raises when Yahoo omits SPX/VIX (live-data-dependent). | `_price()` guard handling missing/object/dict (handler). | ✅ FIXED & RE-VERIFIED (200) |
| 5 | `GET /api/business/expected-returns` | Handler emitted `forecasts` with wrong item fields; strict `response_model` requires `returns:[{asset,expectedReturn,confidence,components}]`. | Handler now conforms to schema (handler). | ✅ FIXED & RE-VERIFIED (200, 6 items) |
| 6 | `GET /api/business/position-sizing` | Handler emitted `allocations`; schema requires `recommendations:[{asset,size,maxSize,confidence}]`. | Handler conforms to schema (handler). | ✅ FIXED & RE-VERIFIED (200, 6 items) |
| 7 | `GET /api/data-debug` | `df = load_processed_data() or load_sample_data()` evaluates a DataFrame's ambiguous truthiness. | Explicit `if df is None` (handler). | ✅ FIXED & RE-VERIFIED (200) |
| 8 | `GET /api/data-freshness` | Same `X or Y` DataFrame-truthiness bug. | Explicit None check (handler). | ✅ FIXED & RE-VERIFIED (200) |
| 9 | `GET /api/diagnostics/conviction/calibration-recommendations` | Embeds `test_monotonicity` whose `passed` is `numpy.bool_` (from `spearman_sharpe > 0`), not JSON-serializable. | `bool(...)` at source (service). | ✅ FIXED & RE-VERIFIED (200) |
| 10 | `GET /api/diagnostics/conviction/monotonicity-test` | Same `numpy.bool_` `passed`. | `bool(...)` (service). | ✅ FIXED & RE-VERIFIED (200, passed=True native bool) |
| 11 | `GET /api/diagnostics/conviction/history` | Endpoint passed `limit=` to a service method that has no such kwarg. | Apply limit via `df.tail(limit)` at endpoint. | ✅ FIXED & RE-VERIFIED (200) |
| 12 | `GET /api/diagnostics/momentum/calibration-recommendations` | Routes through `compare_formation_periods`, which `max()`-compares `None` Sharpes (`.get(k,-999)` keeps stored None). | Coerce None→sentinel (service); harden `.get()>thr`. | ✅ FIXED & RE-VERIFIED (200) |
| 13 | `GET /api/diagnostics/momentum/formation-comparison` | Same `max()` over `None` Sharpes. | Coerce None→sentinel (service). | ✅ FIXED & RE-VERIFIED (200, recommended=3M) |
| 14 | `GET /api/diagnostics/portfolio/calibration-recommendations` | Routes through `compare_methods`, which `sorted()`-compares `None` Sharpes. | Coerce None→sentinel (service). | ✅ FIXED & RE-VERIFIED (200) |
| 15 | `GET /api/diagnostics/portfolio/method-comparison` | Same `sorted()` over `None` Sharpes. | Coerce None→sentinel (service). | ✅ FIXED & RE-VERIFIED (200) |

**Re-swept all 141 GET ops after fixes: NON-200 = 4 (all correct `method=1` validation 400s), zero 500s, no regressions.**

### HIGH / notes surfaced during fixes
| # | Item | Detail | Status |
|---|---|---|---|
| 16 | `/api/business/{expected-returns,position-sizing}` serve **illustrative (non-live) values** | Capital-market assumptions, not computed from live data. Now schema-valid but not "real data". | ⚠️ documented — needs a real returns model (out of scope this pass) |
| 17 | Dead frontend hooks | `useExpectedReturns`, `usePositionSizing` in `useBusinessLayer.ts` have **zero consumers** (UI reads `/api/business/recommendations`). | 📌 flagged for Phase 4/5 deletion |
| 18 | `/api/data-freshness` returns only 1 series | Processed DataFrame has few FRED columns populated; loop finds 1. Not a crash. | ⚠️ data-coverage, low priority |

### NOT bugs (verified correct)
`/api/diagnostics/portfolio/{drawdown-analysis,factor-exposure,method-metrics,turnover-analysis}`
returned 400 only because the sweep passed `method=1`; with `method=risk_parity` all 200. Proper validation.

### MEDIUM — latency (>3s), mostly live-data-bound
`/api/cot` 7.3s, `/api/prices` 5.8s, `/api/market-stream` 5.8s, `/api/market` 4.4s,
`/api/rates` 3.7s, `/api/health` 3.7s (17.7s cold), `/api/calendar` 3.3s,
`/api/portfolio/attribution` 3.3s, `/api/signals/yield-curve` 3.2s, `/api/v1/risk/liquidity` 3.1s.
