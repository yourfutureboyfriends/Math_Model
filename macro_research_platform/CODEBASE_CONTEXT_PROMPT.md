# MACRO TERMINAL v8.0 — Full Codebase Context Prompt

Use this document to orient any model or engineer to the complete structure, intent, and conventions of this codebase. Read it in full before making any changes.

---

## What This Project Is

**Macro Terminal v8.0** is a professional macro research and portfolio intelligence platform styled after a Bloomberg Terminal. It is designed for regime-based investing and quantitative research. The UI is a single-page React dashboard with a Bloomberg orange (`#f07030`) aesthetic, a 2-row topbar (main bar + live market ticker strip), a collapsible sidebar, and ~40 content sections.

The system ingests macroeconomic data (primarily from FRED), runs a suite of quantitative models, and surfaces actionable investment signals, regime classifications, risk metrics, and portfolio analysis in real time.

---

## Repository Layout

```
macro_research_platform/
├── api/                          # FastAPI Python backend
│   ├── main.py                   # THE monolithic core (14,000+ lines)
│   ├── config.py                 # JWT, DB, CORS, permissions config
│   ├── asgi.py                   # Production ASGI entry point
│   ├── celery_app.py             # Celery task queue config
│   ├── core/auth.py              # JWT auth, password hashing, RBAC
│   ├── models/schemas.py         # Pydantic request/response schemas
│   ├── data_fetcher.py           # FRED + Alpha Vantage raw fetch
│   ├── data_pipeline.py          # ETL pipeline
│   ├── data_freshness.py         # Staleness detection
│   ├── websocket_manager.py      # Socket.IO real-time broadcasting
│   ├── signal_router.py          # Trading signal endpoints
│   ├── equity_router.py          # Equity research endpoints
│   ├── equity/                   # 7-module equity research engine
│   │   ├── sector_rotation.py
│   │   ├── factor_rotation.py
│   │   ├── macro_valuation.py
│   │   ├── country_ranking.py
│   │   ├── earnings_revision.py
│   │   ├── stock_screener.py
│   │   └── event_calendar.py
│   ├── signalling/               # Quantitative signal modules
│   │   ├── bayesian_aggregator.py
│   │   ├── hmm_regime.py
│   │   ├── kalman_filter.py
│   │   ├── multifactor_alpha.py
│   │   └── news_sentiment.py
│   ├── backtesting/router.py     # Strategy backtesting
│   ├── performance/              # Signal performance tracking
│   ├── reports/                  # PDF report generation
│   ├── brokerage/                # Alpaca brokerage integration
│   ├── tasks/                    # Celery background tasks
│   │   ├── pipeline_tasks.py
│   │   ├── signal_tasks.py
│   │   ├── report_tasks.py
│   │   └── llm_tasks.py
│   └── database/                 # SQLAlchemy models + Alembic
├── frontend/                     # React + TypeScript + Vite frontend
│   └── src/
│       ├── App.tsx               # Root component, data fetching, section render order
│       ├── main.tsx              # React entry point
│       ├── index.css             # ALL design tokens + component classes (Tailwind + custom)
│       ├── types/index.ts        # TypeScript interfaces for ALL API shapes
│       ├── components/
│       │   ├── layout/           # Shell, Topbar, Sidebar, DetailPanel, AlertsPanel
│       │   ├── sections/         # ~40 dashboard section components
│       │   └── ui/               # Reusable primitives (AnimatedValue, Skeleton, etc.)
│       ├── hooks/
│       │   ├── useMarketStream.ts  # Socket.IO real-time feed
│       │   └── useAnimatedNumber.ts
│       ├── api/client.ts         # Typed fetch wrapper
│       └── context/AuthContext.tsx
├── config/                       # YAML config files
│   ├── data_sources.yaml
│   ├── global_macro_weights.yaml
│   ├── indicator_mapping.yaml
│   ├── model_settings.yaml
│   └── sector_rules.yaml
├── data/connectors/              # FRED connector, manual overrides
├── docker-compose.yml
└── ARCHITECTURE.md
```

---

## Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, Uvicorn, Pydantic v2 |
| Data | Pandas, NumPy, SciPy, scikit-learn |
| Task Queue | Celery + Redis |
| Database | PostgreSQL/TimescaleDB (prod), SQLite (dev) |
| Auth | JWT (HS256), bcrypt, RBAC |
| Frontend | React 18, TypeScript, Vite |
| Styling | Tailwind CSS + custom CSS variables |
| Charts | Recharts (inline SVG sparklines also used) |
| Real-time | Socket.IO (WebSocket via `useMarketStream`) |

---

## Backend: `api/main.py` — The Core Engine

This single file is ~14,200 lines and contains essentially the entire analytical engine. It is structured as follows:

### 1. Pydantic Data Models (lines ~243–835)
All response shapes are defined here as Pydantic `BaseModel` classes. The root model is:

```python
class DashboardData(BaseModel):
    # Required fields (always present)
    regime: RegimeData
    keyMetrics: KeyMetrics
    signals: SignalsData
    sectorAllocation: SectorAllocationData
    riskIndicators: RiskIndicatorsData
    advancedIndicators: AdvancedIndicatorsData
    recession: RecessionData
    businessLayer: BusinessLayerData
    modelAgreement: ModelAgreementData
    transmissionAnalysis: TransmissionAnalysisData
    investmentMemo: InvestmentMemoData
    dataToWatch: List[DataToWatchItem]
    metadata: DataMetadata

    # Optional computed fields (None if data unavailable)
    nowcast: Optional[Dict[str, Any]] = None
    liquidity: Optional[Dict[str, Any]] = None
    sentiment: Optional[Dict[str, Any]] = None
    valuation: Optional[Dict[str, Any]] = None
    momentumVeto: Optional[Dict[str, Any]] = None
    correlationRegime: Optional[Dict[str, Any]] = None
    signalStack: Optional[Dict[str, Any]] = None
    riskParityAllocation: Optional[RiskParityAllocationData] = None
    regimeTransitions: Optional[RegimeTransitionProbabilities] = None
    debtCycle: Optional[DebtCycleResult] = None
    expectedReturns: Optional[Dict[str, Any]] = None
    alerts: Optional[AlertsData] = None
    internationalMacro: Optional[InternationalMacroResult] = None
    geopoliticalRisk: Optional[Dict[str, Any]] = None
    optionsIntelligence: Optional[Dict[str, Any]] = None
    trendSignals: Optional[Dict[str, Any]] = None
    factorRotation: Optional[Dict[str, Any]] = None
    gmoForecasts: Optional[Dict[str, Any]] = None
    reflexivity: Optional[Dict[str, Any]] = None
    factorDecomposition: Optional[Dict[str, Any]] = None
    horizonAnalysis: Optional[Dict[str, Any]] = None
    anomalyDetection: Optional[Dict[str, Any]] = None
    lstmPrediction: Optional[Dict[str, Any]] = None
    ensembleSignal: Optional[Dict[str, Any]] = None
    performanceTracking: Optional[Dict[str, Any]] = None
    portfolioSimulation: Optional[Dict[str, Any]] = None   # NOTE: NOT portfolioAnalytics
    newsSentiment: Optional[Dict[str, Any]] = None
    equityResearch: Optional[Dict[str, Any]] = None
    systemHealth: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
```

**CRITICAL naming note**: The portfolio simulation field is `portfolioSimulation` in both the backend Pydantic model AND the frontend `DashboardData` type. The `PortfolioAnalyserSection` component accepts a prop named `simulationData`, not `data`. Always pass `simulationData={data.portfolioSimulation}`.

### 2. Data Loading (lines ~836–1087)
- `load_processed_data()` — loads the primary DataFrame from parquet/CSV cache
- `load_sample_data()` — fallback synthetic data
- `load_business_outputs()` — loads business layer JSON outputs
- `_fetch_fresh_fred_value(series_id)` — fetches a single FRED series live
- `_fetch_cpi_yoy_from_fred()` — dedicated CPI fetcher

The primary DataFrame `df` is a time-indexed Pandas DataFrame where each column is a macro indicator (FRED series or derived). Rows are monthly observations.

### 3. Analytical Functions (lines ~1088–8579)
Every metric is computed by a pure function that takes `df: pd.DataFrame` (and sometimes `fred_api_key`) and returns a typed Pydantic model or dict. Key functions:

| Function | Output | Description |
|---|---|---|
| `_compute_regime_scores(df)` | `Dict[str, float]` | Computes growth/inflation/liquidity/risk composite scores |
| `_classify_regime_from_scores(scores)` | `str` | Classifies into Goldilocks/Reflation/Slowdown/Stagflation etc. |
| `get_regime_data(df)` | `RegimeData` | Full regime with history, confidence, interpretations |
| `calculate_signal_stack(df)` | `SignalStackResult` | Multi-layer signal with override tracking |
| `get_key_metrics(df)` | `KeyMetrics` | Growth/inflation/liquidity/risk KPI cards with sparklines |
| `get_signals(df)` | `SignalsData` | Per-factor signal scores with 3-month change |
| `get_sector_allocation(df)` | `SectorAllocationData` | Regime-conditional sector weights |
| `get_risk_indicators(df)` | `RiskIndicatorsData` | VIX, HY spreads, yield curve, divergence scores |
| `get_nowcast_data(df)` | `Dict` | DFM/PCA GDP nowcast with CI and components |
| `get_liquidity_conditions(df)` | `Dict` | M2, TGA, repo, credit impulse |
| `get_sentiment_risk_data(df)` | `Dict` | Fear/greed, positioning, put/call |
| `calculate_debt_cycle(df)` | `DebtCycleResult` | Debt-to-GDP cycle phase |
| `calculate_risk_parity_weights(df)` | `RiskParityAllocationData` | Risk parity portfolio weights |
| `calculate_international_macro(df)` | `InternationalMacroResult` | US/EU/EM/AS regional comparison |
| `calculate_gmo_forecasts(df)` | `Dict` | GMO-style 7-year real return forecasts |
| `calculate_factor_decomposition(df)` | `Dict` | Return decomposition by factor |
| `_compute_portfolio_simulation()` | `Dict` | Terminal vs 60/40 vs SPY comparison |
| `_compute_equity_research_data(df, regime)` | `Dict` | 7-module equity research output |
| `get_correlation_regime(df)` | `Dict` | Stock/bond correlation regime detection |
| `calculate_geopolitical_risk(df)` | `Dict` | Geopolitical risk composite |
| `calculate_trend_signals(df)` | `Dict` | CTA/momentum trend signals |

### 4. Sign Convention for Risk Indicators
In `get_risk_indicators()`, `trend_scores` uses: **+1 = improving (risk falling), −1 = deteriorating (risk rising)**. This means for HY spreads, VIX, and BBB spreads, a LOWER reading vs the prior period = positive trend = `+1`.

### 5. Main Dashboard Endpoint (line ~8726)
```python
@app.get("/api/dashboard")
async def get_dashboard():
```
This endpoint builds the full `DashboardData` object by calling every analytical function in sequence. It uses `model_dump_json()` for serialization (not `jsonable_encoder`) to avoid NaN issues.

### 6. All API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/dashboard` | Full dashboard payload (all modules) |
| GET | `/api/health` | Health check |
| POST | `/api/auth/login` | JWT login |
| POST | `/api/auth/logout` | Logout |
| GET | `/api/auth/me` | Current user |
| GET | `/api/nowcast` | GDP nowcast standalone |
| GET | `/api/liquidity` | Liquidity conditions standalone |
| GET | `/api/sentiment` | Sentiment/risk standalone |
| GET | `/api/valuation` | Valuation filter standalone |
| GET | `/api/momentum-veto` | Momentum veto standalone |
| GET | `/api/correlation-regime` | Correlation regime standalone |
| GET | `/api/signal-stack` | Signal stack standalone |
| GET | `/api/signals` | ML signals standalone |
| GET | `/api/regime` | Regime standalone |
| GET | `/api/regime/history` | Regime history |
| GET | `/api/alerts` | Active alerts |
| GET | `/api/expected-returns` | Expected returns |
| GET | `/api/gmo-forecasts` | GMO long-run forecasts |
| GET | `/api/debt-cycle` | Debt cycle indicators |
| GET | `/api/factors` | Factor exposures |
| GET | `/api/factors/decomposition` | Factor return decomposition |
| GET | `/api/geopolitical-risk` | Geopolitical risk |
| GET | `/api/options-intelligence` | Options flow/skew |
| GET | `/api/trends` | CTA trend signals |
| GET | `/api/news-sentiment` | NLP news sentiment |
| GET | `/api/forecasts/longterm` | Long-run forecasts |
| GET | `/api/reflexivity` | Soros reflexivity model |
| GET | `/api/cot` | CFTC COT positioning |
| GET | `/api/risk/full` | Full risk analytics (VaR, drawdown, stress) |
| GET | `/api/risk/var` | VaR standalone |
| GET | `/api/risk/drawdown` | Drawdown standalone |
| GET | `/api/risk/stress-tests` | Stress scenarios |
| GET | `/api/horizon` | Horizon tension analysis |
| GET | `/api/trade-ideas` | Trade idea pipeline |
| GET | `/api/calendar` | Economic calendar |
| GET | `/api/performance/signals` | Signal performance metrics |
| GET | `/api/report/generate` | Generate PDF report |
| POST | `/api/ask` | AI chat endpoint |
| POST | `/api/data/refresh` | Force data refresh |

### 7. Sections That Self-Fetch (do not get props from App.tsx)
- `COTPositioningSection` → fetches `/api/cot`
- `RiskAnalyticsSection` → fetches `/api/risk/full`
- `HorizonTensionSection` → fetches `/api/horizon`

---

## Frontend Architecture

### Data Flow
```
App.tsx
  └─ fetchData() polls GET /api/dashboard every 30s
       └─ setData(result) → DashboardData state
            └─ passed as props to each section component
                 └─ each section renders from its slice of DashboardData
```

Self-fetching sections (COT, RiskAnalytics, HorizonTension) manage their own `useState` + `useEffect` internally.

### Layout Stack
```
<TerminalShell>          ← fixed topbar (64px), fixed sidebar (200px), scrollable main
  <Topbar />             ← Row 1: branding, F1-F7 fn keys, session badges, clock, tools
                         ← Row 2: SPX/NDX/VIX/10Y/2Y/DXY/EUR-USD/GLD/WTI/FED ticker strip
  <Sidebar />            ← fixed left nav with ~40 section links
  <main>
    <AlertsBanner />     ← dismissible alert strip
    {children}           ← all section components rendered in order
  </main>
  <DetailPanel />        ← right slide-in detail panel
  <AlertsPanel />        ← right slide-in alerts panel
  <CommandPalette />     ← ⌘K modal
</TerminalShell>
```

### Complete Section Render Order in App.tsx

```tsx
<MasterSignalSection    data={data.ensembleSignal} />
<KeyMetricsSection      data={data.keyMetrics} />
<RegimeSection          data={data.regime} />
<SignalsSection         data={data.signals} />
<EnsembleSection        data={data.ensembleSignal} />
<SignalStackSection     data={data.signalStack} />
<SectorAllocationSection data={data.sectorAllocation} />
<FactorRotationSection  data={data.factorRotation} />
<RiskIndicatorsSection  data={data.riskIndicators} />
<DebtCycleSection       data={data.debtCycle} />
<AdvancedIndicatorsSection data={data.advancedIndicators} />
<NowcastSection         data={data.nowcast} />
<LiquiditySection       data={data.liquidity} />
<SentimentSection       data={data.sentiment} />
<GMOForecastsSection    data={data.gmoForecasts} />
<ValuationSection       data={data.valuation} />
<ExpectedReturnsSection data={data.expectedReturns} />
<InternationalMacroSection data={data.internationalMacro} />
<ReflexivitySection     data={data.reflexivity} />
<RegimeTransitionSection data={data.regimeTransitions} />
<CorrelationRegimeSection data={data.correlationRegime} />
<TransmissionSection    data={data.transmissionAnalysis} />
<FactorDecompositionSection data={data.factorDecomposition} />
<MomentumVetoSection    data={data.momentumVeto} />
<HorizonTensionSection  />                              {/* self-fetches /api/horizon */}
<ModelAgreementSection  data={data.modelAgreement} />
<CTATrendSection        data={data.trendSignals} />
<NewsSentimentSection   data={data.newsSentiment} />
<LSTMSection            data={data.lstmPrediction} />
<PerformanceTrackingSection data={data.performanceTracking} />
<AnomalyDetectionSection data={data.anomalyDetection} />
<PortfolioAnalyserSection simulationData={data.portfolioSimulation} />  {/* NOT data.portfolioAnalytics */}
<RiskParitySection      data={data.riskParityAllocation} />
<EquityResearchSection  data={{ equityResearch: data.equityResearch }} />
<COTPositioningSection  />                              {/* self-fetches /api/cot */}
<RiskAnalyticsSection   />                              {/* self-fetches /api/risk/full */}
<BusinessLayerSection   data={data.businessLayer} />
<InvestmentMemoSection  data={data.investmentMemo} />
<DataToWatchSection     data={data.dataToWatch} />
<SystemHealthSection    data={data.systemHealth} performanceData={data.performanceTracking} />
```

### Design System (`frontend/src/index.css`)

All colours are CSS custom properties. Key tokens:

```css
/* Bloomberg orange — primary accent */
--bloomberg:        #f07030;
--bloomberg-dim:    rgba(240, 112, 48, 0.12);
--bloomberg-muted:  rgba(240, 112, 48, 0.08);
--bloomberg-border: rgba(240, 112, 48, 0.35);
--bloomberg-hover:  rgba(240, 112, 48, 0.18);

/* Background layers */
--bg:          #06090c;   /* page background */
--surface-1:   #0d1117;
--surface-2:   #111820;
--surface-3:   #151d28;
--surface-4:   #1a2332;

/* Text */
--text-primary:   #e8eaed;
--text-secondary: #8b949e;
--text-tertiary:  #484f58;

/* Signal colours */
--green: #3fb950;
--red:   #f85149;
--amber: #d29922;
--blue:  #58a6ff;

/* Layout */
--topbar-height: 64px;   /* 2-row topbar: 40px main + 24px ticker */
--sidebar-width: 200px;
```

Tailwind custom colour names: `bloomberg`, `bloomberg-dim`, `bloomberg-muted`, `bloomberg-border`. Used as `text-bloomberg`, `bg-bloomberg-muted`, `border-bloomberg`, etc.

Key component classes defined in `index.css`:
- `.terminal-section` — each dashboard card/panel
- `.section-header`, `.section-tag`, `.section-title`, `.section-meta`
- `.signal-tag.bullish/.bearish/.warning/.neutral` — badge pills
- `.topbar-main-row`, `.ticker-strip`, `.ticker-item`, `.ticker-sym`, `.ticker-val`, `.ticker-chg-pos/.neg`
- `.fn-key`, `.fn-key-num` — Bloomberg function key buttons
- `.session-badge.open/.closed/.pre` — US/EU/AS session indicators
- `.kpi-panel`, `.data-cell` — KPI display blocks
- `.icon-btn` — small icon button
- `.live-dot` — pulsing status dot

### TypeScript Types (`frontend/src/types/index.ts`)

The `DashboardData` interface mirrors the backend Pydantic model exactly. All optional backend fields are `?` optional in the frontend type. Section components always use optional chaining (`data?.field`) because any field can be `undefined`.

---

## Authentication

- JWT HS256 tokens, 24h expiry
- Login: `POST /api/auth/login` with `{ username, password }` → returns `{ access_token, token_type }`
- Token stored in React context (`AuthContext`), sent as `Authorization: Bearer <token>` header
- RBAC: permissions checked per sidebar item and per endpoint
- Default dev credentials are in `.env` / `.env.example`

---

## Data Pipeline

1. **Primary source**: FRED API (via `data/connectors/fred_connector.py`)
2. **Data is cached** as a parquet file in `data/raw/live/`
3. **`load_processed_data()`** loads the parquet; if unavailable, falls back to `load_sample_data()` (synthetic data)
4. **DataFrame structure**: time-indexed, one row per month, columns = FRED series IDs and derived indicators
5. **Key FRED series used**:
   - `GDP`, `GDPC1` — real GDP
   - `CPIAUCSL`, `CPILFESL` — CPI headline + core
   - `FEDFUNDS`, `DFF` — Fed funds rate
   - `T10Y2Y`, `T10YFF` — yield curve spreads
   - `BAMLH0A0HYM2`, `BAMLC0A4CBBB` — HY and BBB spreads
   - `VIXCLS` — VIX
   - `M2SL` — M2 money supply
   - `ICSA` — initial jobless claims
   - `UNRATE` — unemployment

---

## Known Architectural Decisions & Conventions

1. **`main.py` is monolithic by design** — all computation lives in one file for portability. Do not refactor into separate modules without understanding the entire call graph.

2. **`model_dump_json()` not `jsonable_encoder()`** — The dashboard endpoint uses Pydantic's native serializer to avoid NaN/Infinity JSON serialization errors from Pandas.

3. **`Optional[Dict[str, Any]]` for most fields** — Many fields are typed as generic dicts rather than specific Pydantic models. This is intentional for flexibility during iterative development.

4. **`ConfigDict(populate_by_name=True, serialize_by_alias=True)`** — `DashboardData` uses field aliases for some fields (`_dataErrors`, `_dataHealthy`). Always use `populate_by_name=True` when constructing.

5. **Section tag numbers are cosmetic** — The `<span className="section-tag">03</span>` numbers in section headers are display labels, not indices. They do not need to be sequential and can be changed freely.

6. **Self-fetching sections** — Three sections (`COTPositioningSection`, `RiskAnalyticsSection`, `HorizonTensionSection`) fetch their own data independently. They do not receive props from App.tsx. Their fetch URLs are `/api/cot`, `/api/risk/full`, and `/api/horizon` respectively.

7. **`PortfolioAnalyserSection` prop name** — This component has TWO render modes:
   - `data?: PortfolioAnalytics` — for live portfolio data (not currently populated)
   - `simulationData?: PortfolioSimulationData` — for strategy comparison (Terminal vs 60/40 vs SPY)
   The backend field is `portfolioSimulation`. Always pass: `<PortfolioAnalyserSection simulationData={data.portfolioSimulation} />`

8. **Trend sign convention** — In `get_risk_indicators()`, `trend_scores` uses: `+1 = improving = risk FALLING`, `-1 = deteriorating = risk RISING`. For spread/volatility indicators, a lower reading vs prior = `+1`.

9. **Nowcast units** — `contribution` values in nowcast components are already in GDP percentage-point units (not decimals). `weight` is a 0–1 decimal (display as `weight * 100` to get %). RMSE is in pp units, not a percentage.

10. **Cash Sharpe in `_calculate_asset_class_returns()`** — Cash volatility is set to `0.06` (6% annualised, appropriate for money market). Do not use values near `0.005` which produce absurdly high Sharpe ratios.

---

## Sections Not Yet in App.tsx (built but not rendered)

The following section components exist in `frontend/src/components/sections/` but are NOT currently in the sidebar navigation or App.tsx render tree — they were built for future use:

- `CentralBankDivergenceSection.tsx`
- `CommoditiesDashboardSection.tsx`
- `FXMonitorSection.tsx`
- `FixedIncomeDashboardSection.tsx`
- `PositioningSection.tsx`
- `YieldCurveSection.tsx`
- `MarketClockSection.tsx`
- `PureAlphaSection.tsx` (exported but not rendered)

---

## Running the Project

```bash
# Backend (port 3002)
cd api
uvicorn main:app --reload --port 3002

# Frontend (port 5173, proxied to 3002)
cd frontend
npm install
npm run dev
```

Vite proxy in `vite.config.ts` routes `/api/*` to `http://localhost:3002`.

The app is served at `http://localhost:5173`.

---

## Recent Changes (Session History)

The following bugs were identified and fixed across multiple sessions:

| File | Fix |
|---|---|
| `api/main.py` | Inverted trend sign for HY spreads, VIX, BBB spreads in `get_risk_indicators()` |
| `api/main.py` | Cash Sharpe ratio: volatility corrected from `0.005` to `0.06` in `_calculate_asset_class_returns()` |
| `frontend/src/components/sections/NowcastSection.tsx` | RMSE suffix fixed from `%` to `pp`; weight display fixed from raw decimal to `* 100 + %` |
| `frontend/src/components/sections/RegimeSection.tsx` | Confidence bar colour changed from `bg-accent` (teal) to `bg-bloomberg` (orange) |
| `frontend/src/components/sections/RiskAnalyticsSection.tsx` | Fetch URL fixed from `/api/risk/analytics` (404) to `/api/risk/full` |
| `frontend/src/App.tsx` | Fixed `PortfolioAnalyserSection` prop: was `data={data.portfolioAnalytics}` (always undefined), now `simulationData={data.portfolioSimulation}` |
| `frontend/src/App.tsx` | Added 6 previously missing sections: `TransmissionSection`, `CorrelationRegimeSection`, `RiskParitySection`, `EquityResearchSection`, `COTPositioningSection`, `RiskAnalyticsSection` |
| `frontend/src/components/sections/index.ts` | Added exports for `EquityResearchSection`, `COTPositioningSection`, `RiskAnalyticsSection` |
| `frontend/src/index.css` | Full Bloomberg Terminal redesign: orange accent, 2-row 64px topbar, fn-key section tags, session badges, ticker strip |
| All layout components | `top-12` → `top-16` to account for new 64px topbar height |
