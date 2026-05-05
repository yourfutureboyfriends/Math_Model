# MACRO TERMINAL v8.0

A professional macro research platform for regime-based investing, portfolio construction, and quantitative research.

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL/TimescaleDB (optional, SQLite works for dev)
- Redis (for Celery tasks)

### Backend Setup

```bash
cd api
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Start the API
uvicorn main:app --reload --port 3002
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The application will be available at `http://localhost:3000`.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   React/Vite    │────▶│   FastAPI       │────▶│   PostgreSQL    │
│   Frontend      │◄────│   Backend       │◄────│   TimescaleDB   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │   Celery/Redis  │
                        │   Task Queue    │
                        └─────────────────┘
```

## Key Features

- **Regime Detection**: Bridgewater-style 2x2 regime classifier
- **Recession Models**: Sahm Rule + Estrella-Mishkin Probit
- **Portfolio Construction**: Risk parity with regime adjustments
- **Signal Stack**: Multi-layer ensemble with override tracking
- **Live Data**: WebSocket real-time updates

## Project Structure

```
macro_research_platform/
├── api/                    # FastAPI backend
│   ├── main.py            # Application entry point
│   ├── config.py          # Centralized configuration
│   ├── core/              # Auth utilities
│   ├── models/            # Pydantic schemas
│   ├── tasks/             # Celery background tasks
│   └── requirements.txt   # Python dependencies
├── frontend/              # React frontend
│   ├── src/
│   │   ├── components/    # React components
│   │   ├── hooks/         # Custom hooks
│   │   ├── types/         # TypeScript types
│   │   └── api/           # API client
│   └── package.json       # Node dependencies
└── README.md
```

## Development

### Running Tests

```bash
cd api
pytest
```

### Code Style

- Python: Black, Ruff
- TypeScript: ESLint, Prettier

## License

Proprietary - All rights reserved.
