# MACRO OS v8.0 Architecture

This document describes the system architecture after the Phase 1-6 refactoring.

***

## System Overview

MACRO OS v8.0 is a quantitative finance platform that combines:
- **Macro regime classification** (4 regimes: Goldilocks, Reflation, Stagflation, Slowdown)
- **Recession forecasting** (probability-based with multiple indicators)
- **Signal generation** (multi-layer signal stack with conviction scoring)
- **Portfolio construction** (sector allocation and trade recommendations)
- **Risk analytics** (volatility, drawdown, VaR, positioning)

**Tech Stack:**
- **Backend:** FastAPI, Python 3.11+, PostgreSQL
- **Frontend:** React, TypeScript, Tailwind CSS
- **Data:** FRED API, Finnhub, Groq (real-time streaming)

***

## Architecture Principles

1. **Separation of Concerns:** Routing → Handlers → Services → Data Layer
2. **Domain-Driven Design:** Code organized by business domain (signals, risk, market)
3. **Explicit Dependencies:** Dependency injection over global state
4. **Defensive Programming:** Validation, logging, and fallback at every boundary
5. **Performance:** TTL caching, lazy evaluation, streaming where appropriate

***

## Backend Architecture

### Layer Breakdown

```
┌─────────────────────────────────────────────────────────────┐
│                         main.py                             │
│              (App startup, CORS, router includes)           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        Routers                              │
│   (Endpoint definitions — routing logic only)               │
│                                                             │
│   • dashboard.py    — /api/dashboard, /api/v2, /api/v3     │
│   • market.py       — /api/rates, /api/fx, /api/commodities│
│   • signals.py      — /api/signals, /api/momentum-veto     │
│   • risk.py         — /api/recession, /api/risk/full       │
│   • business.py     — /api/business-layer, /api/trade-ideas│
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       Handlers                              │
│   (Business logic orchestration)                            │
│                                                             │
│   • dashboard_handler.py  — Compose dashboard from services│
│   • signal_handler.py     — Signal stack calculation       │
│   • risk_handler.py       — Risk analytics and recession   │
│   • market_handler.py     — Rates, FX, commodities         │
│   • business_handler.py   — Trade ideas and recommendations│
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       Services                              │
│   (Reusable business services)                              │
│                                                             │
│   • validation_orchestrator.py  — Runtime validation       │
│   • event_logger.py             — Forecast/signal logging  │
│   • runtime_status.py           — Diagnostics and health   │
│   • [14 validation services]    — Domain validators        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Domain Modules                           │
│   (Core calculation and data logic)                         │
│                                                             │
│   • signalling/         — Signal generation algorithms     │
│   • models_ml/          — ML models (recession, regime)    │
│   • brokerage/          — Trading integration              │
│   • backtesting/        — Historical performance           │
│   • performance/        — Analytics and metrics            │
│   • normalization/      — Data normalization               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Data & Persistence                        │
│                                                             │
│   • repository/         — Data access abstractions         │
│   • database/           — ORM models, migrations           │
│   • providers/          — External data sources (FRED, etc)│
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Utilities                              │
│                                                             │
│   • utils/cache.py       — TTLCache for all cached data    │
│   • utils/validators.py  — NaN/Inf cleaning, type coercion │
│   • utils/formatting.py  — FORMAT_* constants              │
│   • utils/helpers.py     — safe_float, scrub_nans, etc.    │
│   • utils/errors.py      — Exception handling utilities    │
└─────────────────────────────────────────────────────────────┘
```

### Request Flow

```
HTTP Request
    │
    ▼
┌─────────────┐
│   Router    │  — Validates input, calls handler
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Handler   │  — Orchestrates business logic
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Services   │  — Validation, logging, caching
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Domain    │  — Calculations, ML models
└──────┬──────┘
       │
       ▼
┌─────────────┐
│    Data     │  — Repositories, database
└─────────────┘
```

***

## Frontend Architecture

### Component Hierarchy

```
App.tsx
    │
    ├── TerminalShell (layout)
    │       ├── Topbar (market data, navigation)
    │       ├── Sidebar (section navigation)
    │       └── DashboardPage
    │               ├── sections/macro/
    │               │       ├── RegimeSection
    │               │       ├── KeyMetricsSection
    │               │       └── NowcastSection
    │               ├── sections/signals/
    │               │       ├── SignalStackSection
    │               │       ├── MomentumSection
    │               │       └── FactorsSection
    │               ├── sections/rates/
    │               │       ├── RatesMonitorSection
    │               │       └── FXMonitorSection
    │               ├── sections/risk/
    │               │       ├── RiskAnalyticsSection
    │               │       └── AlertsSection
    │               └── sections/equity/
    │                       ├── SectorAllocationSection
    │                       └── ExpectedReturnsSection
    └── stores/
            └── macroStore (Zustand state management)
```

### State Management

**Zustand Store (macroStore):**
- `prices`: Real-time price data
- `regime`: Current macro regime classification
- `signals`: Multi-layer signal stack
- `meta`: Dashboard metadata (last update, data status)
- WebSocket connection management

**Custom Hooks:**
- `useApiData<T>`: Standardized API fetching
- `useHealthCheck`: System health monitoring
- `useMarketStream`: Real-time WebSocket data

***

## Data Flow

### Real-time Data Pipeline

```
External APIs
    │ (FRED, Finnhub, etc.)
    ▼
┌─────────────┐
│   Providers │  api/providers/
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Refresh    │  api/services/refresh_coordinator.py
│ Coordinator │  (scheduled updates, caching)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Repository │  api/repository/
│   Layer     │  (data access abstraction)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Cache     │  api/utils/cache.py
│   (TTL)     │  (price_cache, etc.)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  WebSocket  │  api/websocket_manager.py
│   Server    │  (broadcasts to clients)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Frontend  │  frontend/src/hooks/useMarketStream.ts
│   Clients   │  (real-time updates)
└─────────────┘
```

### Dashboard Request Flow

```
User Request
    │
    ▼
GET /api/dashboard
    │
    ▼
Dashboard Router
    │
    ├── Handler calls:
    │       ├── Regime service
    │       ├── Key metrics service
    │       ├── Signal stack service
    │       └── Risk analytics service
    │
    ▼
Validation (if enabled)
    │
    ▼
Event Logging (if enabled)
    │
    ▼
Return DashboardData
```

***

## Key Design Patterns

### 1. Router-Handler Separation

Routers handle HTTP concerns (routing, input validation via Pydantic).
Handlers contain business logic and orchestrate service calls.

```python
# Router — api/routers/dashboard.py
@router.get("/api/dashboard")
async def get_dashboard(mode: str = "live") -> DashboardData:
    """Get complete dashboard data."""
    from api.handlers.dashboard_handler import get_dashboard_data
    return await get_dashboard_data(mode=mode)

# Handler — api/handlers/dashboard_handler.py
async def get_dashboard_data(mode: str) -> DashboardData:
    """Build dashboard with validation and logging."""
    # ... orchestrate services
    # ... validation
    # ... event logging
    return dashboard
```

### 2. Service Layer

Reusable business services shared across handlers.

```python
# Validation service
from api.services.validation_orchestrator import validate_dashboard_payload
validation = validate_dashboard_payload(dashboard_dict)

# Event logging service
from api.services.event_logger import log_dashboard_event
log_dashboard_event(dashboard_dict, metadata={"mode": mode})
```

### 3. Defensive Programming

Every boundary has error handling and fallbacks.

```python
from api.utils.errors import safe_execute

result = safe_execute(
    lambda: risky_calculation(),
    default={"error": "Calculation failed"},
    error_msg="Risk calculation failed"
)
```

### 4. TTL Caching

Centralized cache management.

```python
from api.utils.cache import TTLCache

price_cache = TTLCache(ttl_seconds=300, name="prices")

# Get with auto-refresh
data = price_cache.get(fetch_function)
```

***

## Environment Configuration

### Feature Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_RUNTIME_VALIDATION` | `true` | Enable payload validation |
| `ENABLE_EVENT_LOGGING` | `true` | Enable event logging |
| `ENABLE_DIAGNOSTICS` | `true` | Enable diagnostics endpoints |
| `ENABLE_WEBSOCKET` | `true` | Enable WebSocket server |

### Data Sources

| Source | Purpose | Refresh |
|--------|---------|---------|
| FRED API | Economic indicators | Daily |
| Finnhub | Market prices | Real-time |
| Groq | AI/LLM features | On-demand |

***

## Performance Considerations

1. **Caching Strategy:** TTL-based with automatic refresh
2. **WebSocket Updates:** Push only changed data
3. **Lazy Loading:** Components fetch data on mount
4. **Memoization:** Expensive calculations cached
5. **Bundle Splitting:** Code-split by route

***

## Security Model

1. **Input Validation:** Pydantic models at API boundary
2. **Runtime Validation:** Optional payload validation
3. **Error Handling:** Generic error messages to clients
4. **Logging:** Audit trail for critical operations
5. **Dependencies:** Automated security auditing with pip-audit

***

## Monitoring & Observability

### Health Endpoints

- `GET /api/health` — Basic health check
- `GET /api/diagnostics/runtime` — Full system diagnostics

### Metrics

- Request latency
- Cache hit rates
- Validation failure rates
- Event log throughput

### Logging

Structured JSON logging with context:
- Request IDs
- User actions
- System events
- Validation results

***

## Future Improvements

1. **GraphQL API:** Flexible data fetching
2. **Redis Cache:** Distributed caching
3. **Kubernetes:** Container orchestration
4. **Feature Flags:** LaunchDarkly integration
5. **A/B Testing:** Experiment framework

***

**Last Updated:** 2026-05-07  
**Version:** 8.0.0
