# SWEEP_REPORT — scoped bug-class sweeps + regression locking

Process change from prior "find all bugs" sessions: (1) detection split into narrow bug-class
sweeps, (2) every fix locked behind a permanent automated test so it cannot silently regress.

## Part C first — the permanent regression suite (the durable fix)

**Location:** `api/tests/regression/` — 13 tests, run in-process via FastAPI `TestClient`
(exercises the real endpoints + the app's own data layer; assertions are structural so they hold
whether live feeds are up or the bundled sample-data fallback is used).

**Run it:** `pytest api/tests/regression/ -v`

**Final run this session: 13 passed.** Full suite (existing + regression): **267 passed, 0 failed.**

| Test file | Locks (sweep) |
|---|---|
| `test_no_fabricated_data.py` | Earnings EPS table + legacy attribution table never return fabricated numbers again (Sweep 4) |
| `test_error_paths.py` | `/api/ask` returns a valid response (numeric confidence), never 503; growth framed as "/100" not "% vs trend" (Sweep 3) |
| `test_numeric_bounds.py` | Dashboard scores 0–100, probabilities/confidence 0–1, VaR ≥ 0 (Sweep 1) |
| `test_cross_panel_consistency.py` | Same CPI date across horizon/calendar/event-vol; recommendations use "Risk Appetite" + an unambiguous position label (Sweep 7) |
| `test_regime_and_labels.py` | Regime-transition current = z-score history (stable, valid quadrant, carries `cycle_regime`); forecasts methodology not falsely "GMO Model" |

> **The regression suite at `api/tests/regression/` must be run before any future bug-fixing
> session. Any bug it does not catch is a genuinely new bug, not a recurrence of something
> already fixed.** Future sessions should run it FIRST; a failure there is a true regression.

## Part B — the scoped sweeps

| # | Sweep | Coverage | Instances found → fixed |
|---|---|---|---|
| 1 | **Impossible numeric values** | Sampled (dashboard scores, probabilities, confidence, VaR) via regression asserts | 0 current violations; **bounds now asserted** by `test_numeric_bounds.py`. Not exhaustive across all ~180 endpoints. |
| 2 | **Unit mismatches (bps/pct/$)** | Sampled (rates/credit spreads, yield-curve, commodities) | 0 found — conversions carry explicit `*100` + comments; frontend consumes bps consistently. Not exhaustive. |
| 3 | **Silent / swallowed errors** | Full grep, backend + frontend | 68 backend silent `except` — **triaged**: the large majority are intentional best-effort fallbacks (warm loops, optional enrichment, snapshot loops) that correctly degrade; not mechanically "fixed" to avoid log-noise churn (the vague-sweep trap). **1 frontend empty `catch {}`** (`useMarketStream`) → now logs. |
| 4 | **Stale/static placeholder text** | Full grep, backend + frontend | Triaged all matches; genuine ones (`rmse=0.8`, TradeIdeas "awaiting data") are **honestly handled** (display "N/A" + tooltip / explicit empty state, no fabricated value). The two true fabricated-data endpoints were already fixed in the prior loop (earnings, attribution) and are now **locked by tests**. |
| 5 | **Infinite/unbounded loading** | Full — audited both fetch patterns | The 9 self-fetch panels already had an 8 s timeout+retry. **`useApiData` (12 consumers) had NO timeout** → could spin forever. **Fixed**: added a 12 s `AbortController` timeout **+ one self-heal retry**. Verified in UI (Scenario Analysis self-heals, Sector Allocation loads). |
| 6 | **Frontend/backend field mismatches** | Sampled (CorrelationMatrix, Anomalies, AltData — read-vs-key compared) | 0 in the sample; all fields matched. The known `factorRotation` mismatch was fixed earlier. Not exhaustive across all self-fetch components. |
| 7 | **Inconsistent metric labeling** | Sampled ("Risk"/"score"/"confidence") | The "Risk Score" vs header "Risk" collision + ambiguous "HIGH RISK" were fixed in the prior loop and are now **locked** by `test_cross_panel_consistency.py`. Not an exhaustive audit of every label. |
| 8 | **Hardcoded symbol/data lists** | Grep, frontend | No problematic hardcoded ticker lists surfaced in components (asset universes come from API responses). |

## Part D — verification standard applied

- `tsc --noEmit` clean and production `vite build` ✓ after the hook changes.
- Frontend fixes confirmed in the **live running UI** (Scenario Analysis + Sector Allocation
  both populate; the useApiData retry self-heals a transient mount-storm failure).
- Backend + regression suites: **267 passed**, 0 failed (no collateral breakage).
- Committed with root cause + sweep category in each message.

## Honest coverage statement

- **Fully swept:** 3 (silent errors), 4 (placeholders), 5 (unbounded loading), plus every prior
  fix now locked by a regression test.
- **Sampled, NOT exhaustive** (codebase is ~180 endpoints + ~70 components — too large for a
  per-instance review of every file in one session): 1 (numeric bounds beyond the dashboard),
  2 (units), 6 (field mismatches across all components), 7 (every label site), 8.
- For the sampled sweeps, no violations were found in the samples examined, but I do **not**
  claim 100% instance coverage. The correct next step is to run each sampled sweep again in its
  own bounded session and extend `api/tests/regression/` with any new instance found — the
  suite is structured so each new lock is a one-file addition.
