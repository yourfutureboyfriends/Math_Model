# FUNCTIONAL_AUDIT — MACRO OS v8.0 (Phase 1)

Ran the whole app fresh and exercised it — not guessed.

## Method
- **Backend:** fresh uvicorn restart (clean startup, **0 errors**), then a full GET sweep of
  **149 operations** (`scratchpad/sweep.py`, pulled from `openapi.json`).
- **Frontend:** logged in, scrolled every section to force lazy-load, then classified all
  **56 sections** by state (OK / blank / stuck-loading / error) and captured console + network.

## Results

**Backend — healthy.** Zero 500s. 4 non-200 are *correct* validation 400s
(`/api/diagnostics/portfolio/{drawdown,factor-exposure,method-metrics,turnover}` reject a bad
`method=` param). SLOW>3s down to 5 (the P1 warm loop). No console/network 4xx/5xx during the walkthrough.

**Frontend — 50/56 OK; 4 genuinely broken (all fixed), 2 false positives.**

| # | Panel | Element | Expected | Actual | Severity | Root cause | Status |
|---|---|---|---|---|---|---|---|
| 1 | Model Agreement | whole panel | consensus table | **completely blank** (0 DOM children) | NON-FUNCTIONAL | **contract mismatch** — backend sends `{agreementScore, agreementLabel, disagreements}`, component read `data.items?.length` → `return null` | ✅ FIXED — renders `0.81 HIGH AGREEMENT` + disagreements/"all agree" state |
| 2 | Policy Transmission | whole panel | channel table | blank (0 children) | NON-FUNCTIONAL | backend sends `channels: []` → `return null` on empty | ✅ FIXED — explicit "Transmission-channel data unavailable" empty state |
| 3 | Model Portfolio | whole panel | holdings | blank (0 children) | NON-FUNCTIONAL | no data source threaded → `return null` | ✅ FIXED — empty state pointing to the Positions panel |
| 4 | System Health | whole panel | health status | **perpetual skeleton** (data prop never passed) | DEGRADED (loads forever) | `<SystemHealthSection />` rendered with no `data` prop → infinite skeleton | ✅ FIXED — honest resolved state → header Data-Integrity indicator + Data Providers panel |
| — | Equity Research | panel | — | flagged ERROR by classifier | *false positive* — real content ("Sector Ratings / Stock Picks"); regex matched "RISK" | not a bug |
| — | Scenario / Trade Rec / Yield Curve / Fixed Income | panels | — | flagged | *false positives* — all render real content | not a bug |

## Fixes (Phase 2) — committed `7129ad1`
All 4 traced to the correct layer (frontend render/contract, not a symptom patch), re-tested
live, and confirmed rendering real data / honest empty states. Zero console errors after.

The headline fix is **Model Agreement**: the backend was producing valid consensus data the
whole time; the panel just couldn't read it (legacy `items` shape). Now visible.
