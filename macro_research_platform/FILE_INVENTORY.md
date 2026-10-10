# FILE INVENTORY — dead-code evidence (Phase 4)

Evidence gathered with `ruff` (F401/F811/F841) and reference-counting. Only items acted on
or explicitly deferred are listed; the bulk of the tree is live and referenced.

## Acted on (deleted / cleaned) — see commits

| Item | Evidence | Verdict | Commit |
|---|---|---|---|
| 291 unused imports across `api/` | `ruff F401` (no `__init__` re-exports flagged) | DELETE (auto) | `b134b61` |
| `DataMetadata` (first def, `models.py:780`) | `ruff F811` + 0 refs between the two defs; second def wins at runtime | DELETE (dead/shadowed) | `c03aa31` |
| `YieldCurveData` (first def, `models.py:1082`) | `ruff F811` + 0 refs between defs | DELETE (dead/shadowed) | `c03aa31` |
| `useExpectedReturns`, `usePositionSizing` (`useBusinessLayer.ts`) | reference count = 0 (UI reads `/api/business/recommendations`) | DELETE | `c03aa31` |
| tracked `*.pyc` under `api/utils/__pycache__` | build artifact, ignored | DELETE (untrack) | `757478f` |
| scratch docs (`*_SUMMARY/_COMPLETE/_PROGRESS/_TRIAGE.md`, `audit_reports/`, `1`), vite `*.timestamp-*.mjs` | session artifacts | GITIGNORE | `757478f` |

## Deferred (evidence gathered, not acted on) — with reason

| Item | Evidence | Verdict | Reason deferred |
|---|---|---|---|
| ~80 `F841` unused local vars | `ruff F841` | CLEAN later | Autofix is "unsafe" (RHS may have side effects); needs per-site review, low risk. |
| 2 local re-imports in `main.py` (`get_freshness_summary`, `validate_dashboard_snapshot`) | `ruff F811` | MERGE (use top import) | Cosmetic; harmless shadowing. |
| `get_validation_status` redef (`services/__init__.py:47`) | `ruff F811` | REVIEW | Needs confirming which impl is intended. |
| Whole-file orphans | reference scan clean — no zero-reference runtime modules found after baseline commit | KEEP | The Phase-0 "untracked but imported" packages are now tracked; nothing is a true orphan. |

## Not deleted — confirmed live despite looking removable
`api/routers/*`, `api/services/*`, `api/calculations/{regime,signals,metrics}` — flagged as
untracked in Phase 0 but **imported by `main.py`/handlers**; committed rather than deleted.
