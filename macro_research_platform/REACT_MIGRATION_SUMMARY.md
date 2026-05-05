# React Migration Summary

## Overview

The Macro Research Platform has been overhauled with a modern React frontend while maintaining the Bloomberg Terminal aesthetic.

## New Architecture

### Frontend (React + TypeScript)
```
frontend/
├── src/
│   ├── components/
│   │   ├── ui/              # Reusable components
│   │   │   ├── Card.tsx     # Terminal-styled cards
│   │   │   ├── Badge.tsx    # Status badges
│   │   │   ├── Table.tsx    # Data tables
│   │   │   ├── Sparkline.tsx # Mini charts
│   │   │   └── MetricCard.tsx # Metric cards
│   │   ├── sections/        # Dashboard sections
│   │   │   ├── KeyMetricsSection.tsx
│   │   │   ├── RegimeSection.tsx
│   │   │   ├── SignalsSection.tsx
│   │   │   ├── SectorAllocationSection.tsx
│   │   │   └── RiskIndicatorsSection.tsx
│   │   └── layout/
│   │       └── Header.tsx
│   ├── hooks/
│   │   └── useDashboard.ts
│   ├── api/
│   │   └── client.ts
│   ├── types/
│   │   └── index.ts
│   ├── lib/
│   │   └── utils.ts
│   ├── App.tsx
│   └── main.tsx
├── package.json
├── tailwind.config.js       # Bloomberg Terminal theme
└── vite.config.ts
```

### Backend (FastAPI)
```
api/
├── main.py                  # FastAPI application
└── requirements.txt
```

## Bloomberg Terminal Styling

### Colors
- **Background**: `#0d1117` (deep dark)
- **Cards**: `#161b22`
- **Elevated**: `#21262d`
- **Borders**: `#30363d`
- **Amber**: `#ff9900` (Bloomberg accent)
- **Green**: `#238636` (success)
- **Red**: `#da3633` (danger)
- **Blue**: `#58a6ff` (info)

### Typography
- **Primary**: Inter (clean, modern)
- **Monospace**: JetBrains Mono (data/numbers)

### UI Patterns
- Uppercase labels with tracking
- Monospace numbers
- Subtle borders and shadows
- Zebra-striped tables
- Sparklines for metrics
- Status badges

## Running the Application

### 1. Start the FastAPI Backend
```bash
cd api
pip install -r requirements.txt
python main.py
```

Or with uvicorn:
```bash
uvicorn main:app --reload --port 8000
```

### 2. Start the React Frontend
```bash
cd frontend
npm install
npm run dev
```

### 3. Access the Dashboard
Open http://localhost:3000 in your browser.

## Features Implemented

### Key Metrics Section
- 6 metric cards with sparklines
- Growth, Inflation, Liquidity, Risk, Recession, Regime Duration
- Direction indicators (up/down/neutral)
- Color-coded based on values

### Regime Classification
- Current regime display with color coding
- Confidence score with progress bar
- Model agreement table

### Signal Interpretation
- Table with latest scores, 3M change, state, direction
- Direction icons (trending up/down/stable)
- Color-coded changes

### Sector Allocation
- Bar chart with threshold lines
- Sector table with signals and conviction
- Color-coded bars based on scores

### Risk Indicators
- Composite risk score
- Risk regime indicator
- Indicators table with levels
- Warning note

## Data Flow

1. React app loads and calls `/api/dashboard`
2. FastAPI backend loads processed data from `data/processed/live/`
3. Backend transforms data into dashboard format
4. React displays components with Bloomberg Terminal styling
5. Auto-refresh every 5 minutes

## Migration Notes

- The original Streamlit dashboard (`dashboard.py`) remains functional
- The React frontend provides a more modern, responsive experience
- Both use the same data sources
- The React frontend is optional and can be used alongside Streamlit

## Future Enhancements

Potential additions to the React frontend:
- WebSocket support for real-time updates
- Advanced Indicators section
- Business Layer outputs
- Historical data viewer
- Export functionality
- User preferences
- Dark/light theme toggle
