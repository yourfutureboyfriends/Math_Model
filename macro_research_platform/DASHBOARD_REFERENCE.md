# Macro Terminal Dashboard Reference

## Overview

This document provides a comprehensive reference for the Macro Terminal dashboard, including data sources, calculation methodologies, and troubleshooting guidance.

---

## Data Sources

### Primary Sources

| Source | Type | Data Retrieved | Update Frequency |
|--------|------|----------------|------------------|
| **FRED API** | Economic Data | GDP, Inflation, Employment, Interest Rates, Debt | Monthly/Quarterly |
| **yfinance** | Market Data | Stock prices, ETFs (SPY, VIX, sector ETFs) | Real-time (15min) |
| **FRED CSV** | Local Data | `us_economic_data.csv` (fallback) | Static |

### Key FRED Series Used

| Series ID | Description | Used In |
|-----------|-------------|---------|
| `GDPC1` | Real GDP | GDP Nowcast, Regime Classification |
| `CPIAUCSL` | CPI (All Urban) | Inflation tracking |
| `FEDFUNDS` | Fed Funds Rate | Monetary Policy |
| `UNRATE` | Unemployment Rate | Labor Market |
| `T10Y2Y` | Yield Curve (10Y-2Y) | Recession Probability |
| `GFDEGDQ188S` | Federal Debt to GDP | Debt Cycle Monitor |
| `TDSP` | Debt Service Payments | Debt Cycle Monitor |
| `M2SL` | M2 Money Supply | Liquidity Conditions |
| `VIXCLS` | VIX Index | Risk/Sentiment |
| `WTI` | Oil Prices | Commodities/Inflation |

---

## Dashboard Sections

### 1. Regime Classification

**Purpose**: Identify current macroeconomic regime using Bridgewater's 2×2 framework

**Methodology**:
- **Growth Dimension**: Compares current GDP growth to potential (2%)
  - Uses 3-month industrial production growth
  - 12-month retail sales growth
  - Employment payrolls growth
- **Inflation Dimension**: Compares CPI to Fed target (2%)
  - Uses CPI YoY change
  - Core PCE when available
- **Regimes**:
  - **Goldilocks**: High growth, low inflation
  - **Reflation**: High growth, high inflation
  - **Stagflation**: Low growth, high inflation
  - **Slowdown**: Low growth, low inflation

**Data Structure**:
```typescript
{
  current: "Stagflation",
  confidence: "High",
  confidenceScore: 0.8,
  duration: 1,
  history: [...],
  interpretations: [...]
}
```

**Troubleshooting**:
- If regime shows "Unknown": Check CSV has GDP and CPI data
- Confidence stuck at 0: Verify data is not stale (>30 days old)

---

### 2. GDP Nowcast

**Purpose**: Real-time estimate of current quarter GDP growth

**Methodology**: DFM (Dynamic Factor Model) / MIDAS
- Academic basis: Mariano & Murasawa (2010), Ghysels et al. (2004)
- **Components**:
  - Industrial Production (35% weight)
  - Retail Sales (25% weight)
  - Nonfarm Payrolls (25% weight)
  - Housing Starts (15% weight)
- Calculates annualized QoQ growth
- Confidence intervals based on historical RMSE

**Data Structure**:
```typescript
{
  nowcastQoQ: 0.74,
  nowcastYoY: 2.96,
  confidenceInterval: { lower: 1.46, upper: 4.46, rmse: "N/A" },
  components: [...],
  methodology: "DFM/MIDAS"
}
```

**Troubleshooting**:
- "N/A" RMSE: Normal - requires 6+ months of backtest data
- Components empty: Check industrial_production column in CSV

---

### 3. Signal Stack

**Purpose**: 10-layer signal hierarchy with override logic

**Methodology**: Layered approach with precedence:
1. **Recession** (Layer 0): Binary trigger (>60% probability)
2. **Regime** (Layer 1): Bridgewater 2×2 classification
3. **Debt Cycle** (Layer 2): Dalio long-term debt cycle position
4. **Geopolitical Risk** (Layer 3): Composite risk score
5. **Liquidity** (Layer 4): Financial conditions index
6. **Options Intelligence** (Layer 5): Market positioning
7. **Trend Following** (Layer 6): CTA momentum signals
8. **Sentiment** (Layer 7): VIX + risk appetite
9. **Momentum** (Layer 8): Cross-asset momentum
10. **Valuation** (Layer 9): Z-score based adjustment

**Final Stance Calculation**:
```
Base Stance = Regime-derived position
+ Adjustments from each layer (-0.15 to +0.15)
Final Stance = clamp(Base + sum(adjustments), -1, +1)
```

**Data Structure**:
```typescript
{
  finalStance: "DEFENSIVE_REAL",
  riskBudget: 0.9,
  activeLayer: 2,
  layerOutputs: {
    regime: { regime: "Stagflation", baseStance: "Defensive-Real", ... },
    liquidity: { score: -0.57, adjustment: -0.15 },
    trendFollowing: { ctaSignal: "BULLISH", adjustment: -0.04 },
    ...
  }
}
```

**Troubleshooting**:
- Stance "NEUTRAL": Check all layer outputs are calculating
- Layer not triggering: Verify data source (e.g., VIX for sentiment)

---

### 4. Risk Parity Allocation

**Purpose**: Risk-balanced portfolio allocation across asset classes

**Methodology**:
- **Inverse Volatility Weighting**: Lower vol assets get higher weight
- **Target Volatility**: Typically 10-15% annualized
- **Leverage Calculation**: target_vol / portfolio_vol
- **Regime Adjustment**: Shift allocations based on current regime
- **Sector ETFs**: XLF, XLE, XLI, XLK, XLP, XLU, XLY, XLB

**Data Structure**:
```typescript
{
  holdings: [
    { ticker: "XLF", sector: "Financials", annualisedVol: 0.1475, 
      baseWeight: 0.0959, signalScore: 0.297, targetAllocationPct: 11.69 }
  ],
  totalHoldings: 11,
  portfolioVol: 0.142,
  diversificationRatio: 1.23,
  lastRebalanced: "2026-05-01T20:50:15"
}
```

**Troubleshooting**:
- All weights zero: Check sector ETF price data in CSV
- Volatility = 0: Insufficient price history (need 30+ days)

---

### 5. Regime Transitions

**Purpose**: Estimate probability of regime changes

**Methodology**:
- Historical transition matrix (Markov chain)
- Calculates transition probabilities from current regime
- Identifies most likely next regime

**Data Structure**:
```typescript
{
  currentRegime: "Stagflation",
  transitions: {
    "Stagflation": { "Goldilocks": 0.27, "Reflation": 0.21, ... },
    "Slowdown": { "Goldilocks": 0.1975, ... }
  },
  mostLikelyNext: "Slowdown",
  nextRegimeProbability: 0.33,
  warning: "Elevated transition risk to Goldilocks (27%)"
}
```

---

### 6. GMO 7-Year Forecasts

**Purpose**: Long-term (7-year) return projections (GMO methodology)

**Methodology**:
- **Mean Reversion**: Asset classes revert to historical valuations
- **Key Inputs**:
  - Current valuations (P/E, P/B, yields)
  - Historical mean valuations
  - Growth assumptions (2% real GDP)
- **Calculation**:
  ```
  Expected Return = (Current Yield × 7) + Growth - (Valuation Change)
  ```

**Data Structure**:
```typescript
{
  currentRegimeReturn: 0.042,
  next12Months: [
    { scenario: "Base Case", probability: 0.5, expectedReturn: 0.04, 
      confidenceInterval: [-0.05, 0.15] }
  ],
  byAssetClass: { "S&P 500": 0.045, "Bonds": 0.02, ... },
  riskAdjustedReturns: { "S&P 500": 0.3, "Bonds": 0.15, ... }
}
```

**Troubleshooting**:
- All zeros: Check valuation data (P/E ratios)
- Extreme values (>50%): Verify annualized returns, not cumulative

---

### 7. Debt Cycle Monitor

**Purpose**: Track position in Dalio's long-term debt cycle

**Methodology**:
- **Debt/GDP Ratio**: Track federal debt to GDP
- **Debt Service Ratio**: Interest payments to income
- **M2 Growth**: Money supply growth
- **Credit Impulse**: Change in credit growth

**Phases**:
1. Early Cycle: Debt growing, incomes rising
2. Bubble: Asset prices inflated, leverage high
3. Peak: Debt service costs exceed income growth
4. Deleveraging: Debt reduction via default/restructuring
5. Depression: Economic contraction
6. Recovery: Debt burdens reduced

**Data Structure**:
```typescript
{
  phase: "Mid Cycle",
  description: "Debt growing at moderate pace...",
  debtToGDP: 125.4,
  debtServiceRatio: 9.8,
  creditImpulse: -0.5,
  riskLevel: "moderate",
  indicators: [...]
}
```

---

### 8. Recession Probability

**Purpose**: Estimate 12-month recession probability

**Methodology**:
- **Yield Curve** (40%): 10Y-2Y spread (Estrella-Mishkin)
- **Sahm Rule** (30%): Unemployment increase from low
- **Leading Indicators** (20%): Conference Board LEI
- **Credit Spreads** (10%): Corporate bond spreads

**Trigger**: >60% probability = Recession warning

**Data Structure**:
```typescript
{
  probability: 0.123,
  riskLevel: "low",
  sahmenRule: { triggered: false, value: 0.3 },
  yieldCurve: { spread: -0.45, inverted: true },
  leadingIndicators: { momentum: -0.02, trend: "declining" }
}
```

---

### 9. Expected Returns

**Purpose**: Forward-looking return projections

**Methodology**:
- **Regime-Based**: Returns conditioned on current regime
- **Asset Class**: Stocks, Bonds, Commodities, Real Estate
- **Scenarios**: Base case, bull, bear with probabilities
- **Risk-Adjusted**: Sharpe ratios by asset class

---

### 10. Business Layer

**Purpose**: Investment recommendations and position sizing

**Methodology**:
- **Position Sizing Engine**: Kelly Criterion + Conviction scoring
- **Recommendation Types**:
  - Research: Long-term thematic views
  - Portfolio: Asset allocation changes
  - Action: Tactical trades
- **Position Sizes**:
  - High Conviction: 1.5%
  - Medium Conviction: 1.0%
  - Low Conviction: 0.5%

**Data Structure**:
```typescript
{
  recommendations: "markdown text with structured data",
  expectedReturns: [...],
  positionSizing: [...],
  signalScorecard: [...],
  decisionLog: [...]
}
```

---

## Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Data Sources                            │
├─────────────┬──────────────┬──────────────┬─────────────────┤
│  FRED API   │  yfinance    │  CSV Files   │  Calculated     │
│  (Econ)     │  (Markets)   │  (Fallback)│  (Models)       │
└──────┬──────┴──────┬───────┴──────┬───────┴────────┬────────┘
       │             │              │                │
       └─────────────┴──────────────┴────────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │   DataFrame (df)    │
              │  Combined dataset   │
              └──────────┬──────────┘
                         │
       ┌─────────────────┼─────────────────┐
       ▼                 ▼                 ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│   Models     │ │  Indicators  │ │  Signals     │
├──────────────┤ ├──────────────┤ ├──────────────┤
│ Regime       │ │ Key Metrics  │ │ Signal Stack │
│ Recession    │ │ Risk         │ │ Trend        │
│ GMO          │ │ Liquidity    │ │ Momentum     │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                │
       └────────────────┴────────────────┘
                          │
                          ▼
              ┌─────────────────────┐
              │   Dashboard API     │
              │   /api/dashboard    │
              └──────────┬──────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │  React Frontend     │
              │  (Sections)         │
              └─────────────────────┘
```

---

## Troubleshooting Guide

### Data Not Loading

| Symptom | Cause | Fix |
|---------|-------|-----|
| All sections show "—" | CSV file missing | Check `data/us_economic_data.csv` exists |
| Sections show "No data" | Date parsing issue | Check CSV date format is YYYY-MM-DD |
| Stale timestamp | Data too old | Refresh with FRED API key or update CSV |

### Calculation Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| Signal Stack all neutral | Layer outputs empty | Check VIX, liquidity data available |
| GMO forecasts = 0% | Missing valuation data | Add P/E ratios to CSV |
| Risk Parity weights = 0 | Missing price data | Add sector ETF prices to CSV |
| Nowcast "N/A" | Insufficient history | Normal - needs 6+ months of data |

### WebSocket Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| "WebSocket error" in console | python-socketio not installed | `pip install python-socketio` |
| Duplicate regime events | Multiple socket connections | Normal in React StrictMode |
| No live price updates | Socket not connected | Falls back to REST polling (normal) |

### Performance Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| Slow dashboard load | Too many API calls | Use cached CSV data instead of FRED API |
| High memory usage | DataFrame not cleared | Restart backend periodically |
| Frontend lag | Too many re-renders | Check React DevTools Profiler |

---

## Enhancement Ideas

### Data Sources to Add

1. **CFTC Commitment of Traders**: Positioning data
2. **EPFR Fund Flows**: Mutual fund/ETF flows
3. **Credit Default Swaps**: Corporate credit risk
4. **Real-time News**: NLP sentiment analysis
5. **Satellite Data**: Economic activity indicators

### Models to Implement

1. **Dynamic Asset Allocation**: Black-Litterman framework
2. **Volatility Targeting**: Constant volatility portfolio
3. **Risk Budgeting**: Equal risk contribution
4. **Machine Learning**: XGBoost for regime prediction
5. **NLP Analysis**: Fed statement sentiment analysis

### Features to Add

1. **Backtesting Engine**: Test strategies on historical data
2. **Scenario Analysis**: What-if stress testing
3. **Correlation Breakdown**: Explain correlation changes
4. **Alert System**: Push notifications for regime changes
5. **Export Reports**: PDF/Excel generation

---

## Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `FRED_API_KEY` | Access FRED economic data | No (falls back to CSV) |
| `VITE_SOCKET_URL` | WebSocket server URL | No (defaults to localhost:8000) |

---

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `/api/dashboard` | Full dashboard data (GET) |
| `/api/nowcast` | GDP Nowcast only |
| `/api/liquidity` | Liquidity conditions |
| `/api/sentiment` | Sentiment risk data |
| `/api/valuation` | Valuation filter |
| `/api/signal-stack` | Signal stack V2 |

---

## Last Updated

This document was generated on 2026-05-01.

For questions or issues, check the backend logs:
```bash
tail -f backend.log
```
