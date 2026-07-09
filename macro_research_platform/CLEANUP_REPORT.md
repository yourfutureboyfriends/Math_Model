# CLEANUP REPORT — MACRO OS v8.0 runtime verification & cleanup

Session goal: run the app end-to-end, exercise every endpoint, fix what's broken, then
clean and standardize. Everything below was **re-verified in this session** (endpoint
re-hit / test re-run / build re-run) — not asserted from a single earlier pass.

## 1. Bugs found and fixed (with before/after evidence)

Full detail + severity table in [RUNTIME_AUDIT.md](RUNTIME_AUDIT.md). Summary:

### CRITICAL — backend crashes (13 endpoints) — commit `441f5d5`, `b134b61`
Found by a live sweep of **141 GET operations** (`scratchpad/sweep.py`, pulled from
`openapi.json`). Before: 15 non-200. After: **4 non-200, all correct `method=1` validation
400s; zero 500s.**

| Class | Endpoints | Root cause | Fix (layer) |
|---|---|---|---|
| DataFrame truthiness | `/api/data-debug`, `/api/data-freshness` | `load_processed_data() or load_sample_data()` | explicit `if df is None` (handler) |
| `numpy.bool_` not serializable | conviction `monotonicity-test`, `calibration-recommendations` | `passed = … spearman > 0` | `bool(...)` (service) |
| bad kwarg | conviction `history` | `limit=` unsupported | `df.tail(limit)` (endpoint) |
| `None` comparison | momentum `formation-comparison` + `calibration-recommendations`, portfolio `method-comparison` + `calibration-recommendations` | `max()/sorted()` over `None` Sharpes (`.get(k,-999)` keeps stored `None`) | coerce `None`→sentinel (service) |
| response-model mismatch | `/api/business/expected-returns`, `/api/business/position-sizing` | handler emitted `forecasts`/`allocations`; strict `response_model` requires `returns`/`recommendations` w/ different item fields | conform handler to schema |
| `dict.price` on missing key | `/api/equity-research`, `/api/portfolio/attribution` (+6 latent sites) | `result.data.get(K, {}).price` → `{}.price` when a provider omits a symbol (intermittent) | shared `_rec_price()` helper (handler) |

### CRITICAL — frontend production build broken (8 tsc errors) — commit `840ad81`
`npm run build` failed under `tsc` (the app only ran because the Vite dev server skips
typechecking). Fixed 3 implicit-any callbacks + added the optional interface fields the
components already read (`TradeIdea.asset`, `InternationalMacroData.globalSync`/`interpretation`).
After: `npm run build` → ✓ built in ~3.3s.

### Verified NOT bugs
`/api/diagnostics/portfolio/{drawdown-analysis,factor-exposure,method-metrics,turnover-analysis}`
return 400 only for an invalid `method` — correct validation (200 with `method=risk_parity`).
All POST endpoints return **422**, not 500, on malformed bodies (Phase 1D).

## 2. Files deleted (justification + commit)
See [FILE_INVENTORY.md](FILE_INVENTORY.md). Headline: 291 unused imports (`b134b61`), 2
shadowed duplicate model classes + 2 zero-consumer hooks (`c03aa31`), stray tracked `*.pyc`
(`757478f`). Each verified by full test suite + build after removal.

## 3. Files merged / consolidated
- 8 copies of the `result.data.get(K,{}).price` anti-pattern → one shared `_rec_price()`
  helper in `business_handler.py` (+ safe `getattr` inline in `market_handler.py`).
- `.gitignore` consolidated to absorb all session-scratch patterns.

## 4. Standardization applied
- **Backend imports**: `ruff --select F401` clean across `api/`.
- **Response-contract integrity**: business endpoints now conform to their declared
  `response_model` (single source of truth), removing 3-way handler/schema/frontend drift.
- **Safe-accessor pattern** for provider records (units documented in the helper docstring).
- **Baseline hygiene**: runtime-critical packages that were untracked are now committed, so a
  fresh clone builds; scratch artifacts gitignored.
- **Logging standardized** (`2a810e4`): new `api/logging_config.setup_logging()` installs one
  formatter — `time | LEVEL | module | message` — on the root logger at lifespan startup, so
  every app + third-party log line shares one structure (verified live). `LOG_LEVEL`
  env-driven. The module name now carries the context that ad-hoc `[PREFIX]` tags used to;
  removed the only app-code `print()`/`__import__('logging')` hack (DB layer). CLI `__main__`
  scripts keep `print()` (correct stdout output).

## 4b. Second fresh-clone bug fixed (`2a810e4`)
The over-broad `database/` gitignore rule hid a **source** package: top-level `database/db.py`
(1230 lines) is imported by 20 modules as `from database.db` but was untracked — a clone would
fail. (Phase 0 missed it because gitignored files don't show as untracked.) Narrowed the ignore
to runtime data only; committed the source. `api/database/` identified as a **dead duplicate**
(0 importers) and explicitly ignored.

## 4c. Useless files removed (`2a810e4`)
Deleted dead `api/models_ml/integration_test.py` (209 `print()`s, 0 importers); untracked +
ignored generated `outputs/` (24 stale reports) and `reports/archive/`; deleted ~28 gitignored
scratch docs, stray `1` files, and vite `*.timestamp-*.mjs` temp files.

## 5. Final state (re-verified this session, Phase 7 gate)
- ✅ Clean backend restart: **0 ERROR/Traceback** in startup log.
- ✅ Endpoint sweep: 141 GET ops, **zero 500s**, only 4 correct validation 400s.
- ✅ Backend tests: **193 passed** (warm; the 37 integration tests hit the live server).
- ✅ Frontend production build: **✓ built** (1489 modules, ~3.3s), bundle `index` 342 kB (gzip 95 kB).
- ✅ Frontend UI walkthrough: sections render real live data, **zero console errors**, no failed network requests.

## 6. Honest list of what was NOT done / NOT fully cleaned

| Item | Reason |
|---|---|
| **Remaining Phase 6** (custom exception classes, one `{data, meta}` envelope across all 175 ops, `black` reformat, docstrings on every function, `~80 F841` unused-local removal, frontend `<AsyncState>` + one number-formatter, ad-hoc `[PREFIX]` tag removal now that logging carries the module name) | Large multi-day refactor across ~175 endpoints / ~90 components; high regression risk late in one session. **Done this pass:** imports (F401), response-model integrity, crash classes, **logging standardization**, dead-code removal. Remainder flagged for a dedicated pass. |
| **`node_modules/` is committed to git** (309 churn entries; forces `http.postBuffer` on push) | Untracking it (`git rm -r --cached`) is a large, history-affecting change — deliberately deferred; needs a decision on whether to rewrite history vs. a forward-only ignore. |
| **`~80 F841` unused locals, `black` autoformat** | Not applied — `black`/`F841` autofix would touch hundreds of files and swamp review; low risk, deferred. |
| **`/api/health` latency (6–17s cold), `/api/signals/yield-curve` ~10s** | Real MEDIUM perf issue (health should be sub-second; also makes the 5s-timeout integration tests flaky when cold). Needs endpoint profiling — out of scope for a bug-fix pass. |
| **`/api/business/{expected-returns,position-sizing}` serve illustrative (non-live) values** | Now schema-valid and non-crashing, but the numbers are capital-market assumptions, not computed from live data. Needs a real returns/sizing model. |
| **`npx depcheck` / requirements cross-ref for unused deps** | Not run this session. |
| **Frontend `eslint --fix` / `prettier`** | Not run; pre-existing type-loose sections (`anyData` casts) remain. |

## Commits this session (on `fix/macro-os-repair`)
`757478f` baseline backend + ignore · `b453223` frontend reorg baseline · `b66829e` docs/CI/config ·
`441f5d5` 12 backend 500s · `840ad81` frontend build · `b134b61` F401 + dict.price ·
`c03aa31` dead-code deletions · `efadba9` audit/inventory/report docs ·
`2a810e4` track database/ source + standardize logging + remove junk.
