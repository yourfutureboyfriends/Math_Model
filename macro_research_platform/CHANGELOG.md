# Changelog

All notable changes to MACRO OS will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

***

## [8.0.0] - 2026-05-07

### Major Refactoring (6-Phase Cleanup)

This release represents a comprehensive refactoring of the entire codebase
based on a 9-report audit. The goal was to improve maintainability,
testability, and code quality without changing external behavior.

### Added

**Phase 1: De-duplication & Quick Wins**
- `api/utils/cache.py` — Thread-safe TTLCache class (replaces 12 duplicate cache implementations)
- `api/utils/validators.py` — Reusable NaN/Inf cleaning utilities (replaces 39 duplicate validators)
- `api/utils/formatting.py` — FORMAT_* constants for consistent number formatting
- `frontend/src/hooks/useApiData.ts` — Standardized data fetching hook (replaces 13 direct fetch() calls)
- `frontend/src/lib/constants.ts` — Frontend FORMAT_* constants (mirrors backend)

**Phase 2: Critical Fixes**
- `api/utils/errors.py` — Standard exception handling utilities
- `api/utils/responses.py` — Standard API error/success response format
- Custom exceptions: DataValidationError, DataFetchError, CalculationError
- Utilities: safe_execute(), safe_endpoint(), log_and_return()
- Comprehensive error handling tests

**Phase 3: Main.py Refactor**
- `api/schemas/models.py` — Extracted 63 Pydantic models
- `api/routers/` — 5 focused routers (dashboard, market, signals, risk, business)
- `api/handlers/` — 5 handler modules for business logic
- `api/utils/helpers.py` — Extracted utility functions

**Phase 4: Frontend Cleanup**
- `frontend/src/types/` — Split into 4 domain files (dashboard, signals, market, risk)
- `frontend/src/pages/` — Page components (DashboardPage, AnalyticsPage, MarketsPage)
- `frontend/src/components/ui/FormattedNumber.tsx` — Consistent number formatting
- Organized 45 section components by feature domain (macro, equity, rates, risk)

**Phase 5: Validation Integration**
- `api/services/validation_orchestrator.py` — Centralized validation
- `api/services/event_logger.py` — Production event logging
- `api/services/runtime_status.py` — Real diagnostics and health data
- `frontend/src/components/SystemStatusBadge.tsx` — Frontend health visibility
- Integration tests for production flows

**Phase 6: Documentation & Polish**
- CONTRIBUTING.md — Coding standards and workflow
- ARCHITECTURE.md — System design documentation
- API.md — Complete endpoint reference
- CHANGELOG.md — This file
- Docstrings for 79 critical functions (43% → 95% coverage)
- requirements.lock — Pinned dependencies
- Pre-commit hooks for code quality
- Upgraded react-query v3 → @tanstack/react-query v5

### Changed

**Code Organization**
- main.py: 14,555 lines → ~150 lines (99% reduction)
- Endpoints moved from main.py to 5 focused routers
- Pydantic models extracted to schemas/models.py
- Utilities extracted to utils/ directory

**Error Handling**
- Fixed 2 bare `except:` clauses (CRITICAL)
- Converted 217 broad exceptions to specific types
- Added context to all exception logs
- Exception handling coverage: 30% → 90%+

**Frontend Organization**
- types/index.ts: 1,520 lines → ~50 lines (re-exports only)
- App.tsx: 520 lines → ~50 lines (90% reduction)
- 13 components refactored to use useApiData hook
- 161 .toFixed() calls replaced with FORMAT_* constants
- Section components organized by domain

**Validation & Monitoring**
- Runtime validation wired into core handlers
- Forecast/signal/risk event logging activated
- Diagnostics endpoints return real runtime data
- Environment flags for validation/logging/diagnostics

### Removed

- ~2,400 LOC of duplicate code across backend and frontend
- 58 "FIXED" comment markers
- Unused imports and dead code
- Debug console.log statements

### Fixed

- Bare except clauses that masked errors
- Broad exception catches that prevented debugging
- VIX TODO (line 14403)
- Inconsistent number formatting
- Components bypassing state management

### Security

- Added pip-audit to CI/CD for dependency scanning
- Specific exception types prevent information leakage
- Input validation at API boundary

### Performance

- Consolidated 12 caches into TTLCache for consistent performance
- Removed duplicate validators and fetch patterns
- Optimized frontend bundle size

### Removed

- `/api/v2/dashboard` — Legacy endpoint removed, use `/api/dashboard`
- `/api/v3/dashboard` — Legacy endpoint removed, use `/api/dashboard`

### Migration Guide

**For developers:**
1. Update imports if using internal APIs
2. Use new routers instead of calling handlers directly
3. Use TTLCache for all caching needs
4. Use useApiData hook for all API calls in frontend
5. Apply FORMAT_* constants for number formatting
6. Follow new CONTRIBUTING.md standards

**For users:**
- **BREAKING CHANGE:** Legacy `/api/v2/dashboard` and `/api/v3/dashboard` removed
- Use `/api/dashboard` (same response format)
- Update any client code still referencing v2/v3 endpoints

***

## [7.0.0] - 2026-03-15

### Added
- Initial regime classification system
- Recession forecasting module
- Signal stack generation
- Basic dashboard UI

### Changed
- Migrated from Flask to FastAPI
- Upgraded frontend to React 18

***

## [6.0.0] - 2025-12-01

### Added
- Multi-factor signal generation
- Sector allocation recommendations

***

**Full changelog:** https://github.com/your-org/macro-os/blob/main/CHANGELOG.md
