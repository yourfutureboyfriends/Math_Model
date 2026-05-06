# MACRO OSv8.0 — Institutional Terminal Frontend

A production-grade, Bloomberg Terminal-style React frontend for macro research and portfolio analytics.

## Overview

MACRO OSv8.0 is a comprehensive institutional-grade terminal that provides real-time macro analysis, regime classification, risk analytics, and trade recommendations. Built with modern React patterns, TypeScript, and optimized for performance.

## Features

- **Bloomberg Terminal Aesthetic**: Dark theme with amber accents, monospace fonts, and professional financial styling
- **Real-time Data**: WebSocket integration for live price updates with auto-reconnection
- **Regime Classification**: Bridgewater 2x2 growth × inflation regime model
- **Signal Stack**: Multi-factor ensemble signals with model agreement tracking
- **Risk Analytics**: Credit impulse, recession probability, LEI composite, financial conditions
- **Portfolio Analytics**: Risk parity, factor decomposition, performance attribution
- **Business Layer**: Investment committee recommendations, position sizing, expected returns
- **Code Splitting**: Lazy-loaded sections for optimal bundle size

## Technology Stack

- **React 18** - UI framework with Suspense for lazy loading
- **TypeScript** - Type safety with strict mode
- **Vite** - Build tool with optimal chunking
- **Tailwind CSS** - Utility-first styling
- **Zustand** - Lightweight state management
- **Recharts** - Interactive charts and visualizations
- **Vitest** - Unit testing with jsdom environment

## Quick Start

### Prerequisites

- Node.js 18+
- Backend API running on port 8000

### Installation

```bash
cd frontend
npm install
```

### Development

```bash
npm run dev
```

Starts dev server on http://localhost:5173 with API proxy to backend.

### Production Build

```bash
npm run build
```

Generates optimized build with code-split chunks in `dist/`.

### Testing

```bash
npm run test          # Run tests
npm run test:coverage # Run with coverage
```

## Architecture

```
frontend/
├── src/
│   ├── components/
│   │   ├── ui/           # Reusable UI components
│   │   │   ├── Card.tsx
│   │   │   ├── Badge.tsx
│   │   │   ├── SectionSkeleton.tsx  # Lazy loading fallback
│   │   │   └── LoadingState.tsx
│   │   ├── sections/     # Dashboard sections (50+ modules)
│   │   │   ├── index.ts  # Lazy loading barrel
│   │   │   ├── MorningBriefSection.tsx      # Critical (eager)
│   │   │   ├── MasterSignalSection.tsx      # Critical (eager)
│   │   │   ├── BusinessLayerSection.tsx     # Lazy loaded
│   │   │   └── ...
│   │   └── layout/       # Layout components
│   ├── store/
│   │   └── macroStore.ts  # Zustand single source of truth
│   ├── hooks/
│   │   ├── useRealtime.ts      # WebSocket with auto-reconnect
│   │   ├── useBusinessLayer.ts # Business API integration
│   │   ├── useVirtualList.ts   # Performance optimization
│   │   └── useHealthCheck.ts   # System health monitoring
│   ├── utils/
│   │   ├── format.ts      # Centralized format library
│   │   └── formatRules.ts # ESLint rules for format enforcement
│   ├── config/
│   │   └── env.ts         # Environment configuration
│   ├── test/
│   │   └── setup.ts       # Vitest configuration
│   └── App.tsx            # Suspense boundaries for lazy sections
├── .env.production        # Production environment
├── vitest.config.ts       # Test configuration
├── .eslintrc.cjs          # Linting with format enforcement
└── tailwind.config.js     # Bloomberg Terminal theme
```

## Data Architecture

### Store Pattern

Single Zustand store (`macroStore.ts`) is the source of truth:

```typescript
interface MacroState {
  prices: Record<string, number | null>;
  changes: Record<string, number>;
  regime: { current: string | null; confidence: number };
  signals: Signal[];
  ensemble: EnsembleData;
  meta: MetaState;
}
```

**Rule**: Components read from the store. Props are for section-specific overrides only.

### Format Library

All number formatting goes through `utils/format.ts`:

```typescript
import { fmtPrice, fmtChange, fmtProbability } from '@/utils/format';

fmtPrice(123.456, 'SPY');      // → "123.46"
fmtChange(0.025);              // → "+2.50%"
fmtProbability(0.85);           // → "85%"
```

**ESLint Rule**: Direct `.toFixed()` calls are blocked via `no-restricted-syntax`.

## Code Splitting

Sections are split into critical and lazy-loaded:

**Critical (Eager Load)**:
- MorningBriefSection
- MasterSignalSection
- KeyMetricsSection
- RegimeSection
- RegimePlaybookSection
- MarketClockSection

**Lazy Loaded**:
- All other 45+ sections load on-demand

Bundle impact: 564KB → 288KB initial (49% reduction)

## API Integration

### REST Endpoints

```
GET  /api/dashboard           # Full dashboard data
GET  /api/business/recommendations
GET  /api/business/decision-log
GET  /api/business/ic-pack
GET  /api/business/expected-returns
GET  /api/business/position-sizing
GET  /api/health              # System health check
```

### WebSocket

```
WS /ws/prices                # Real-time price updates
```

Auto-reconnection with exponential backoff via `useRealtime` hook.

## Environment Configuration

Production environment variables (`.env.production`):

```
VITE_API_URL=/api
VITE_WS_URL=wss://host/ws
VITE_ENABLE_WEBSOCKET=true
VITE_API_TIMEOUT=30000
```

Access via `config/env.ts` for type safety and validation.

## Testing

### Format Library Tests

```typescript
// All formatters have unit tests
expect(fmtChange(0.025)).toBe('+2.50%');
expect(fmtPrice(123.456, 'SPY')).toBe('123.46');
```

### Store Tests

```typescript
// State updates and selectors
const { updatePrices, selectMeta } = useMacroStore.getState();
```

## Security

- XSS Prevention: React escapes by default
- CSP Headers: Configured in production
- CORS: Restricted to allowed origins
- No secrets in frontend bundle

## Performance

- Code splitting: 288KB initial bundle
- Lazy loading: Sections load on demand
- React.memo: Section-level memoization
- Virtual lists: For large datasets
- WebSocket batching: Price updates batched

## Customization

### Adding a New Section

1. Create section in `src/components/sections/NewSection.tsx`
2. Add to lazy loading barrel in `sections/index.ts`
3. Add Suspense boundary in `App.tsx`
4. Add to sidebar navigation

### Theme Customization

Edit `tailwind.config.js`:

```javascript
colors: {
  bg: '#0d1117',
  surface: '#161b22',
  bloomberg: '#ff9900',
}
```

## Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## License

Proprietary - All rights reserved.
