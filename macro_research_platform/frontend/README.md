# Macro Research Platform - React Frontend

A Bloomberg Terminal-style React frontend for the Macro Research Platform.

## Features

- **Bloomberg Terminal Aesthetic**: Dark theme with amber accents, monospace fonts, and professional financial styling
- **Real-time Dashboard**: Key metrics, regime classification, signals, sector allocation, and risk indicators
- **Interactive Charts**: Sparklines, bar charts, and trend visualizations using Recharts
- **Auto-refresh**: Data refreshes every 5 minutes automatically
- **Responsive Design**: Works on desktop and tablet devices

## Technology Stack

- **React 18** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool
- **Tailwind CSS** - Styling
- **Recharts** - Charts and visualizations
- **Axios** - HTTP client

## Getting Started

### Prerequisites

- Node.js 18+
- The FastAPI backend running on port 8000

### Installation

```bash
cd frontend
npm install
```

### Development

```bash
npm run dev
```

This starts the dev server on http://localhost:3000 with proxy to backend.

### Build for Production

```bash
npm run build
```

## Architecture

```
frontend/
├── src/
│   ├── components/
│   │   ├── ui/           # Reusable UI components (Card, Badge, Table, Sparkline)
│   │   ├── sections/     # Dashboard sections (KeyMetrics, Regime, etc.)
│   │   └── layout/       # Layout components (Header)
│   ├── hooks/            # React hooks (useDashboard)
│   ├── api/              # API client
│   ├── types/            # TypeScript types
│   ├── lib/              # Utilities
│   ├── App.tsx           # Main app component
│   └── main.tsx          # Entry point
├── package.json
├── tailwind.config.js    # Bloomberg Terminal theme
└── vite.config.ts
```

## Component Library

### Card
Terminal-styled card component with optional title.

### Badge
Status badges with variants: success, warning, danger, info, neutral.

### Table
Data table with zebra striping and hover effects.

### Sparkline
Mini area charts for metrics.

### MetricCard
Card displaying a metric value with optional sparkline.

## Styling

The theme is defined in `tailwind.config.js`:

- **Background**: `#0d1117` (dark)
- **Cards**: `#161b22`
- **Borders**: `#30363d`
- **Amber Accent**: `#ff9900` (Bloomberg style)
- **Green**: `#238636` (positive)
- **Red**: `#da3633` (negative)
- **Blue**: `#58a6ff` (info)

## API Integration

The frontend communicates with the FastAPI backend at `http://localhost:8000/api`.

### Endpoints

- `GET /api/health` - Health check
- `GET /api/dashboard` - Full dashboard data

## Customization

### Adding New Sections

1. Create a new section component in `src/components/sections/`
2. Add the data type to `src/types/index.ts`
3. Update the API in `api/main.py` to serve the data
4. Import and use in `App.tsx`

### Changing Theme

Edit `tailwind.config.js` and `src/index.css` to customize colors.
