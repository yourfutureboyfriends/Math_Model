# Architecture Overview

## System Design

### Backend (FastAPI)

#### Entry Points
- `main.py` - FastAPI application with lifespan management
- `asgi.py` - ASGI entry point for production
- `celery_app.py` - Celery task queue configuration

#### Core Modules

| Module | Purpose |
|--------|---------|
| `config.py` | Centralized configuration (JWT, DB, CORS, permissions) |
| `core/auth.py` | JWT authentication, password hashing, RBAC |
| `models/` | Pydantic schemas for request/response validation |
| `websocket_manager.py` | Socket.IO real-time broadcasting |
| `data_pipeline.py` | ETL pipeline for macro data |

#### Routers (Modular Endpoints)
- `signal_router.py` - Trading signals and ensemble
- `equity_router.py` - Equity research endpoints
- `backtesting/router.py` - Strategy backtesting
- `performance/router.py` - Performance analytics
- `reports/router.py` - Report generation
- `brokerage/router.py` - Brokerage integration

#### Background Tasks (Celery)
- `tasks/pipeline_tasks.py` - Data pipeline automation
- `tasks/signal_tasks.py` - Signal calculation jobs
- `tasks/report_tasks.py` - Scheduled report generation

### Frontend (React + TypeScript)

#### Structure
```
src/
├── App.tsx                 # Root component with routing
├── main.tsx               # React entry point
├── index.css              # Global styles, Tailwind
├── components/
│   ├── sections/          # Dashboard sections
│   ├── ui/                # Reusable UI components
│   └── layout/            # Layout components
├── hooks/                 # Custom React hooks
├── types/                 # TypeScript type definitions
├── api/                   # API client
└── context/               # React context providers
```

#### Key Components

| Component | Purpose |
|-----------|---------|
| `Topbar.tsx` | Navigation, live clock, data status |
| `MasterSignalSection.tsx` | Ensemble signal display |
| `SignalStackSection.tsx` | Layered signal visualization |
| `RiskIndicatorsSection.tsx` | Risk metrics and alerts |
| `AnimatedValue.tsx` | Animated number displays |
| `Skeleton.tsx` | Loading placeholders |

#### Hooks
- `useMarketStream.ts` - Socket.IO real-time price feed
- `useAnimatedNumber.ts` - Number animation utility

### Database

#### PostgreSQL/TimescaleDB (Production)
- Time-series data with TimescaleDB hypertables
- Async SQLAlchemy with connection pooling
- Alembic migrations

#### SQLite (Development)
- Single-file database for local development
- Auto-creates tables on startup

### Authentication Flow

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Login   │────▶│  Verify  │────▶│  JWT     │────▶│  Client  │
│  Request │     │  Password│     │  Token   │     │  Storage │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
                                                        │
                                                        ▼
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Access  │◄────│  Decode  │◀────│  Bearer  │◀────│  Request │
│  Granted │     │  Token   │     │  Header  │     │  API     │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
```

### Data Flow

1. **Ingestion**: FRED API, Alpha Vantage, Polygon
2. **Processing**: Pandas/numpy calculations
3. **Storage**: TimescaleDB for time-series, PostgreSQL for metadata
4. **Serving**: FastAPI endpoints with caching
5. **Display**: React components with real-time updates

### WebSocket Broadcasting

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Price   │────▶│  Backend │────▶│  Redis   │────▶│  All     │
│  Update  │     │  Socket  │     │  Pub/Sub │     │  Clients │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
```

## Configuration

All configuration is centralized in `api/config.py`:
- Database URLs
- JWT settings
- CORS origins
- Role permissions
- API keys

## Security

- JWT tokens with 8-hour expiry
- bcrypt password hashing (pre-hashed for 72-byte limit)
- RBAC with role-based permissions
- CORS restricted to localhost in dev
