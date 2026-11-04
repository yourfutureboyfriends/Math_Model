# MACRO OS v8.0 API Reference

Complete API endpoint documentation.

**Base URL:** `http://localhost:8000`  
**Format:** JSON  
**Authentication:** None (to be added in future versions)

***

## Endpoints

### Dashboard

#### GET /api/dashboard

Get complete dashboard with regime, metrics, signals, and analytics.

**Query Parameters:**
- `mode` (optional): Data mode
  - `live` (default) — Real-time data
  - `sample` — Demo/sample data

**Response:**
```json
{
  "regime": {
    "active": "Goldilocks",
    "confidenceScore": 0.78,
    "latestScore": 0.82,
    "duration": 45,
    "description": "Strong growth, low inflation",
    "chartData": [...],
    "volatility": 0.12
  },
  "keyMetrics": {
    "gdpGrowth": {
      "value": 3.2,
      "change": 0.5,
      "sparklineData": [2.8, 2.9, 3.0, 3.1, 3.2]
    },
    ...
  },
  "signals": {
    "finalSignal": "RISK_ON",
    "conviction": 0.82,
    "layers": {...},
    "risk_budget": 0.75
  },
  ...
}
```

**Example:**
```bash
curl http://localhost:8000/api/dashboard
curl http://localhost:8000/api/dashboard?mode=sample
```

***

### Signals

#### GET /api/signals

Get signal stack with conviction and layers.

**Response:**
```json
{
  "finalSignal": "RISK_ON",
  "conviction": 0.82,
  "layers": {
    "macro": {"score": 0.85, "weight": 0.4},
    "momentum": {"score": 0.78, "weight": 0.3},
    "risk": {"score": 0.80, "weight": 0.3}
  },
  "risk_budget": 0.75,
  "regime": "Goldilocks"
}
```

***

#### GET /api/signal-stack

Get detailed signal hierarchy with override logic.

**Response:**
```json
{
  "finalSignal": "Neutral",
  "conviction": 0.7,
  "layers": [
    {"layer": "Regime", "priority": 1, "signal": "Neutral", "conviction": 0.7},
    {"layer": "Recession", "priority": 2, "signal": "Low Risk", "conviction": 0.8},
    {"layer": "Momentum", "priority": 3, "signal": "Positive", "conviction": 0.6}
  ],
  "overridesApplied": [],
  "reasoning": "No overrides active. Standard signal aggregation."
}
```

***

#### GET /api/momentum-veto

Get momentum veto status.

**Response:**
```json
{
  "veto": false,
  "score": 0.68,
  "trend": "up",
  "reason": null
}
```

***

#### GET /api/nowcast

GDP Nowcast using DFM/PCA methodology.

**Response:**
```json
{
  "gdpNowcast": 2.5,
  "nowcastQoQ": 0.625,
  "nowcastYoY": 2.5,
  "confidenceInterval": {"lower": 1.8, "upper": 3.2},
  "components": [],
  "revisionHistory": [],
  "methodology": "DFM/PCA (Mariano & Murasawa 2010)"
}
```

***

### Risk & Recession

#### GET /api/recession

Get recession probability and indicators.

**Response:**
```json
{
  "probability": 0.23,
  "regime": "Low Risk",
  "models": {
    "logistic": {"probability": 0.22, "signal": "Low"},
    "sahm": {"probability": 0.18, "signal": "Low"},
    "estrella_mishkin": {"probability": 0.35, "signal": "Medium"}
  },
  "indicators": {
    "yield_curve": -0.45,
    "credit_spreads": 120,
    "unemployment": 3.8
  },
  "lastUpdated": "2026-05-07T01:30:00Z"
}
```

***

#### GET /api/risk/full

Get comprehensive risk analytics.

**Response:**
```json
{
  "sharpe": 0.85,
  "sortino": 1.02,
  "calmar": 0.65,
  "informationRatio": 0.42,
  "var95": 0.0125,
  "cvar95": 0.015,
  "maxDrawdown": -8.5,
  "status": "Using S&P 500 as benchmark proxy",
  "drawdown": {
    "currentSeverity": "mild",
    "daysInDrawdown": 0,
    "recoveryTimeEstimate": "N/A"
  },
  "riskAdjustedReturns": {
    "sharpeRatio": 0.85,
    "sortinoRatio": 1.02,
    "annualReturn": 0.08,
    "annualVolatility": 0.15
  },
  "correlation": {
    "assets": ["SPY", "TLT", "GLD", "HYG"],
    "matrix3m": [...],
    "diversificationScore": 65
  },
  "stressTests": [
    {"name": "2008 Crisis", "status": "passed"},
    {"name": "2020 COVID", "status": "passed"},
    {"name": "2022 Inflation", "status": "warning"}
  ],
  "lastUpdated": "2026-05-07T01:30:00Z"
}
```

***

#### GET /api/alerts

Get active alerts.

**Response:**
```json
{
  "alerts": [
    {
      "id": "alert-1",
      "type": "Recession",
      "severity": "Medium",
      "message": "Yield curve remains inverted - recession risk elevated",
      "timestamp": "2026-05-07T01:30:00Z",
      "active": true
    }
  ],
  "count": 1,
  "lastUpdated": "2026-05-07T01:30:00Z"
}
```

***

### Market Data

#### GET /api/rates

Get interest rates data.

**Response:**
```json
{
  "US10Y": {"value": 4.25, "change": 0.05},
  "US2Y": {"value": 4.15, "change": 0.03},
  "DE10Y": {"value": 2.45, "change": 0.02},
  "UK10Y": {"value": 4.35, "change": 0.04},
  "JP10Y": {"value": 0.85, "change": 0.01}
}
```

***

#### GET /api/fx

Get FX rates.

**Response:**
```json
{
  "EURUSD": {"rate": 1.085, "change": 0.002},
  "USDJPY": {"rate": 150.25, "change": -0.50},
  "GBPUSD": {"rate": 1.265, "change": 0.001}
}
```

***

#### GET /api/commodities

Get commodities prices.

**Response:**
```json
{
  "gold": {"price": 2050, "change": 15.5, "unit": "USD/oz"},
  "oil": {"price": 78.50, "change": -1.2, "unit": "USD/barrel"},
  "copper": {"price": 4.25, "change": 0.05, "unit": "USD/lb"}
}
```

***

#### GET /api/prices

Get current prices for key assets.

**Response:**
```json
{
  "SPY": {"price": 450.25, "change": 2.35, "volume": 85000000},
  "QQQ": {"price": 380.50, "change": 1.85, "volume": 42000000},
  "IWM": {"price": 195.30, "change": 0.95, "volume": 28000000}
}
```

***

### Business Layer

#### GET /api/business-layer

Get trade ideas and market outlook.

**Response:**
```json
{
  "tradeIdeas": [
    {
      "asset": "SPY",
      "direction": "LONG",
      "conviction": 0.82,
      "rationale": "Strong macro regime supports equities",
      "entry": 450.00,
      "stop": 445.00,
      "target": 460.00
    }
  ],
  "marketOutlook": "Constructive - favor risk assets",
  "riskLevel": "moderate"
}
```

***

#### GET /api/trade-ideas

Get simplified trade recommendations.

**Response:**
```json
{
  "ideas": [
    {
      "asset": "SPY",
      "action": "BUY",
      "conviction": "HIGH"
    }
  ]
}
```

***

### Monitoring & Diagnostics

#### GET /api/health

Basic health check.

**Response:**
```json
{
  "status": "healthy",
  "version": "8.0.0",
  "timestamp": "2026-05-07T01:30:00Z"
}
```

***

#### GET /api/diagnostics/runtime

Detailed runtime diagnostics.

**Response:**
```json
{
  "status": {
    "status": "healthy",
    "timestamp": "2026-05-07T01:30:00Z",
    "components": {
      "cache": {"valid": true},
      "validation": {"enabled": true},
      "logging": {"enabled": true},
      "scheduler": {"valid": true}
    }
  },
  "validation": {
    "enabled": true,
    "validators_available": {...}
  },
  "caches": {
    "valid": true,
    "caches": {...}
  },
  "scheduler": {
    "valid": true,
    "scheduler": {...}
  },
  "logging": {
    "enabled": true,
    "loggers_available": {...}
  },
  "timestamp": "2026-05-07T01:30:00Z"
}
```

***

## Error Responses

All errors follow this format:

```json
{
  "error": "Error message",
  "detail": "Detailed error information",
  "timestamp": "2026-05-07T01:30:00Z",
  "endpoint": "/api/dashboard"
}
```

**Status Codes:**
- `200` — Success
- `400` — Bad Request (invalid parameters)
- `404` — Not Found
- `500` — Internal Server Error

***

## Rate Limiting

Not currently implemented. Planned for future versions.

***

## Versioning

API version is returned in `/api/health` response.

Current version: **8.0.0**

***

## OpenAPI Documentation

Interactive API docs available at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

***

## SDK / Client Libraries

No official SDKs yet. Use standard HTTP clients:

**Python:**
```python
import requests

response = requests.get('http://localhost:8000/api/dashboard')
data = response.json()
```

**JavaScript:**
```javascript
const response = await fetch('http://localhost:8000/api/dashboard');
const data = await response.json();
```

**cURL:**
```bash
curl http://localhost:8000/api/dashboard | jq
```

***

**API version:** 8.0  
**Last updated:** 2026-05-07
