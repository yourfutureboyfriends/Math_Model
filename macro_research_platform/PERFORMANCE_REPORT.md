# PERFORMANCE + POLISH REPORT — MACRO OS v8.0

Optimization-only pass (no new features). Every number below was measured in this session.

## 1. Performance Report — before / after

### P1 — Backend response time
| Endpoint | Before (per call) | After (warm / repeat) |
|---|---|---|
| `/api/dashboard` | **already <2ms** (5-min cache) — target met | 1.5ms |
| `/api/health` | 3.5s (live FRED fetch every poll) | **1.4ms** |
| `/api/cot` | 8.1s | **1.6ms** |
| `/api/market` | 3.3s | **1.6ms** |
| `/api/rates` | 3.1s | **1.6ms** |
| `/api/signals/yield-curve` | 3.0s | **1.2ms** |
| `/api/calendar` | 2.2s | **1.2ms** |

**How:** a reusable async `ttl_cache` decorator (`api/utils/cache.py`) applied per-endpoint
with a TTL matched to how often each source actually moves (health 30s, cot 300s, market 15s,
rates 30s, yield-curve 60s, calendar 600s, event-vol 600s). Cold (first live fetch per TTL)
is unchanged; every repeat within the window is now instant. **This is the root fix for the
dashboard mount-storm saturation** that had been timing out the compute-heavy panels.
`/api/dashboard` target (<100ms) was already met by its existing 5-min cache. No N+1 DB loops
in the hot path (SQLite portfolio/audit use single queries); heavy sections already lazy-load
via their own `/api/v1/*` endpoints.

### P2 — Frontend bundle
| Metric | Before | After |
|---|---|---|
| Main bundle (gzip) | 98.86 KB | 98.85 KB (target <300KB ✅ already met) |
| Lazy chunks | 75 | 75 (sections already code-split) |
| Unused deps | recharts, @tanstack/react-query, date-fns, marked | **removed (−46MB node_modules)** |

All charts are custom SVG/CSS (no chart lib). No raster images (icons are lucide SVG), so no
image optimization needed.

### P3 — React re-renders
Found **3 components** subscribing to the entire Zustand store (`useMacroStore((s) => s)`),
re-rendering on **every WebSocket price tick**. Worst was `DashboardPage` — the root that
renders all ~50 sections. Converted all three (DashboardPage, KeyMetricsSection,
MomentumVetoSection) to field-level selectors → they re-render only when their specific values
change. No list >50 items exists, so no virtualization needed.

### P4 — WebSocket
Backend already broadcasts on a 2s interval (throttled). Frontend now **buffers price ticks
and flushes once per 500ms** in a single `set()` (was `set()` per message), and the
per-message `console.log` was removed.

## 2. Files Modified
```
Performance:
  api/utils/cache.py            (ttl_cache decorator)
  api/main.py                   (@ttl_cache on health/cot/calendar)
  api/routers/market.py         (@ttl_cache on rates/market)
  api/routers/signals.py        (@ttl_cache on yield-curve)
  frontend/package.json         (removed 4 unused deps)
  frontend/src/pages/DashboardPage.tsx          (narrow selectors)
  frontend/src/components/sections/macro/KeyMetricsSection.tsx
  frontend/src/components/sections/signals/MomentumVetoSection.tsx
  frontend/src/store/macroStore.ts              (WS batching)
Polish:
  frontend/src/styles/tokens.ts                 (created — UI1 design tokens)
  frontend/src/components/ui/DataLineagePopover.tsx  (aria)
  frontend/src/components/sections/**           (aria-label on 12 icon buttons)
```

## 3. UI Polish status
| Item | Status |
|---|---|
| UI1 tokens | ✅ `tokens.ts` created; CSS-var scale already enforced app-wide |
| UI2 interaction states | ✅ already present — 46 files use `hover:` + `transition`, `disabled:` states on buttons |
| UI3 loading/empty/error | ✅ `SectionSkeleton` + 3-state (populated / unavailable-with-reason / bounded load) on every new panel |
| UI4 micro-interactions | ✅ via existing `AnimatedValue` (number transitions) + CSS `animate-*`. **Declined framer-motion** — a heavy dep would undo P2 and the terminal aesthetic favours subtle CSS. |
| UI5 responsive | ✅ 29 files use responsive Tailwind grids (`md:`/`lg:`) |
| UI6 accessibility | ✅ global `*:focus-visible` ring already present; added `aria-label` to icon buttons + `aria-expanded` to lineage trigger |

## 4. Remaining issues (honest)
- [ ] **Cold-start latency** — the *first* call to a live-data endpoint per TTL window is still
  2–8s (real yahoo/FRED fetch). The right deeper fix is moving blocking `requests.get` calls
  onto threads (`asyncio.to_thread`) so they don't block the event loop, and/or a background
  pre-warm loop for all of them. Caching mitigates the repeat cost; this addresses the first.
- [ ] **`node_modules/` committed to git** (7,600+ tracked files) — the dep removal produced a
  large unstaged deletion set. Untracking `node_modules` is the correct fix but is a
  history-affecting change deferred for a decision.
- [ ] **UI4** — no spring/physics animations added (deliberate; CSS transitions only).
- [ ] Full **WCAG audit** (axe/Lighthouse) not run in this environment — the concrete fixes
  (focus ring, aria-labels) are done; a formal audit is recommended.

## 5. Recommended next phase
The foundation is fast and consistent. Highest-value next steps:
1. **Backend concurrency** — move the remaining blocking FRED/yahoo fetches to threads +
  a single background warm loop, so even *cold* endpoints never block the event loop
  (eliminates the last of the mount-storm latency).
2. **Export/reporting** — the audit trail + IC-pack primitives exist; a scheduled PDF/CSV
  export of the morning brief + risk + attribution would be a natural, high-value feature.
3. **Persist user state** — favourites/pins/recent are in-session only; a small per-user store
  would make the terminal feel owned.
