# Macro Regime Model

A clean, explainable macro dashboard and regime model built for a university investment fund.
The model classifies the macro environment into one of four regimes and generates sector
allocation signals with plain-English investment memos.

Built to be **learned from, not just used**.

---

## Quick start

```bash
# 1. Clone and navigate to the project
cd macro_model/

# 2. Install dependencies
pip install -r requirements.txt

# 3. Generate sample data (only needed once)
python3 scripts/generate_sample_data.py

# 4. Launch the dashboard
streamlit run dashboard.py
```

The dashboard will be available at http://localhost:8501

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      DATA LAYER                                  │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │
│  │ Sample CSV  │  │ FRED API    │  │ Manual Override     │   │
│  │ (default)   │  │ (real data) │  │ (supplemental)      │   │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘   │
│         │                │                      │               │
│         └────────────────┴──────────────────────┘               │
│                          │                                      │
│                   ┌──────┴──────┐                               │
│                   │ DataPipeline │                              │
│                   └──────┬──────┘                               │
└──────────────────────────┼──────────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────────┐
│              TRANSFORMATION LAYER                                  │
├──────────────────────────┼────────────────────────────────────────┤
│                   ┌──────┴──────┐                               │
│                   │ Transform   │  • MoM/YoY changes            │
│                   │ Engine      │  • Rolling z-scores (36M)       │
│                   └──────┬──────┘  • Momentum scores               │
│                        │         • Diffusion indices              │
│                        │                                       │
└────────────────────────┼─────────────────────────────────────────┘
                         │
┌────────────────────────┼─────────────────────────────────────────┐
│                 SCORING LAYER                                     │
├────────────────────────┼─────────────────────────────────────────┤
│                   ┌────┴────┐                                    │
│                   │ Scoring │   • Equal-weight scores            │
│                   │ Engine  │   • PCA-based scores                 │
│                   └────┬────┘   • Composite scores                │
│                        │        • Signal quality metrics          │
│                        │                                       │
│  Growth    Inflation   Liquidity   Risk                          │
│    ↓           ↓           ↓         ↓                           │
│  [0.5]      [1.2]      [-0.8]    [0.3]                         │
└────────────────────────┼─────────────────────────────────────────┘
                         │
┌────────────────────────┼─────────────────────────────────────────┐
│              REGIME CLASSIFICATION                                │
├────────────────────────┼─────────────────────────────────────────┤
│                   ┌────┴────┐                                    │
│                   │ Regime  │                                    │
│                   │ Classifier │  Growth ↑ × Inflation ↓         │
│                   └────┬────┘   → Goldilocks                     │
│                        │                                       │
│  ┌─────────────────────┼─────────────────────┐                   │
│  │                     │                     │                   │
│  ▼                     ▼                     ▼                   │
│  Reflation        Goldilocks            Stagflation              │
│  (G↑, I↑)        (G↑, I↓)              (G↓, I↑)                 │
│                             Slowdown                             │
│                            (G↓, I↓)                              │
└──────────────────────────────────────────────────────────────────┘
```

---

## Enhanced Quick Start

### Option A: Sample Data (No API Key Required)

```bash
# Install dependencies
pip install -r requirements.txt

# Generate sample data
python scripts/generate_sample_data.py

# Run dashboard
streamlit run dashboard.py
```

### Option B: FRED API (Real Data)

1. **Get a FRED API key** (free):
   - Visit https://fred.stlouisfred.org/docs/api/api_key.html
   - Sign up and copy your API key

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env and add your FRED_API_KEY
   ```

3. **Run with real data:**
   ```bash
   # In .env, set: MACRO_DATA_SOURCE=mixed
   streamlit run dashboard.py
   ```

### Using the Makefile

```bash
# Run tests
make test

# Run dashboard
make run

# Generate/regenerate sample data
make data

# Export results
make export
```

---

## What the model does

### Step 1 — Load data
Reads a CSV of macro indicators (growth, inflation, liquidity, market risk) from
`data/raw/sample_macro_data.csv`.

### Step 2 — Transform
Computes four transforms for each indicator:
- **MoM change** — month-on-month difference
- **YoY change** — year-on-year difference
- **3M moving average** — smooths noise
- **36M rolling z-score** — standardises to a common scale ("is this high or low
  relative to its recent history?")

### Step 3 — Score
Groups indicators into four themes, adjusting for direction conventions:
- **Growth score** — PMI, GDP, industrial production, retail sales, unemployment
- **Inflation score** — CPI, core CPI, PPI, wages, oil price
- **Liquidity score** — policy rate, yield curve, credit spreads, money supply
- **Risk score** — VIX, equity momentum, dollar index, HY spreads

### Step 4 — Classify regime
Looks at the 3-month direction of growth and inflation scores:

| | Inflation RISING | Inflation FALLING |
|---|---|---|
| **Growth RISING** | Reflation | Goldilocks |
| **Growth FALLING** | Stagflation | Slowdown |

### Step 5 — Sector signals
Scores each sector based on regime fit, liquidity, and risk conditions:
- **Overweight** (score > 0.5)
- **Neutral** (score -0.5 to 0.5)
- **Underweight** (score < -0.5)

### Step 6 — Generate memo
Produces a brief one-paragraph memo and a detailed four-section investment memo
with: what changed, why it matters, portfolio implications, and what would
invalidate the view.

---

## Project structure

```
macro_model/
├── config.py                        ← central configuration
├── dashboard.py                     ← Streamlit app (main entry point)
├── requirements.txt
├── Makefile                         ← build automation
├── .env.example                     ← environment variables template
├── .gitignore
│
├── data/
│   ├── connectors/                  ← FRED API, manual data loaders
│   │   ├── __init__.py
│   │   ├── fred_connector.py
│   │   ├── manual_override.py
│   │   └── data_pipeline.py
│   ├── raw/
│   │   └── sample_macro_data.csv    ← all indicators, 2018-2024
│   └── processed/                   ← cached data, backtest results
│
├── scripts/
│   └── generate_sample_data.py      ← regenerate synthetic CSV
│
├── src/
│   ├── data_loader.py               ← indicator configuration
│   ├── transformations.py           ← MoM, YoY, MA, z-scores
│   ├── scoring.py                   ← group scores + PCA
│   ├── regimes.py                   ← 4-quadrant regime classification
│   ├── sector_model.py              ← sector OW/N/UW logic
│   ├── memo_generator.py            ← investment memo generation
│   ├── learning_explainer.py        ← educational output
│   ├── recession_model.py           ← recession probability model
│   ├── inflation_nowcast.py         ← CPI nowcast model
│   ├── portfolio_constructor.py     ← portfolio weight construction
│   └── risk_monitor.py              ← risk flag detection
│
├── backtesting/
│   ├── __init__.py
│   ├── backtest_sectors.py          ← sector signal backtest
│   └── regime_backtest.py           ← regime analysis
│
├── tests/                           ← pytest test suite
│   ├── test_transformations.py
│   ├── test_scoring.py
│   ├── test_regimes.py
│   └── test_sector_model.py
│
├── README.md                        ← this file
├── learning_notes.md                ← conceptual notes + reading list
└── METHODOLOGY.md                   ← technical documentation with formulas
```

---

## Indicators used

### Growth
| Indicator | Rationale |
|---|---|
| PMI | Best leading indicator; survey-based; released monthly |
| GDP growth (YoY) | Broadest output measure; lagged |
| Industrial production (MoM) | Factory activity |
| Retail sales (MoM) | Consumer spending proxy |
| Unemployment rate | Labour market tightness; LAGGING |

### Inflation
| Indicator | Rationale |
|---|---|
| CPI (YoY) | Headline inflation; central bank target |
| Core CPI (YoY) | Ex-food/energy; preferred Fed focus |
| PPI (YoY) | Upstream pricing; leads CPI by 3-6 months |
| Wage growth (YoY) | Key driver of services inflation |
| Oil price | Energy costs; global demand signal |

### Liquidity
| Indicator | Rationale |
|---|---|
| Policy rate | Price of money |
| 10Y yield | Benchmark discount rate for equities |
| 2Y yield | Tracks expected policy rates |
| Yield curve (10Y-2Y) | Recession signal; bank margin indicator |
| IG credit spreads | Financial conditions; credit stress |
| M2 growth (YoY) | Liquidity in the system |

### Market risk
| Indicator | Rationale |
|---|---|
| VIX | Fear gauge; implied equity volatility |
| Equity momentum (12M) | Trend confirmation; risk-on/risk-off |
| Dollar index (DXY) | Global financial conditions |
| HY spreads | Sensitive credit risk indicator |

---

## Sector allocation logic

| Sector | Key macro drivers | Positive when | Negative when |
|---|---|---|---|
| Banks | Yield curve, rates, credit | Rates rising, curve steep, growth stable | Recession, credit stress |
| Energy | Oil, inflation, global demand | Inflation and oil rising | Growth collapses |
| Technology | Rates, liquidity, growth | Low rates, loose liquidity | Real yields and rates rise |
| Consumer Disc | Employment, real wages | Strong labour market, low inflation | Inflation squeezes consumers |
| Utilities | Rates (inverse), defensiveness | Falling rates, Slowdown | Rising rates |
| Industrials | PMI, capex, manufacturing | PMIs and activity improve | Slowdown regimes |
| Healthcare | Defensive, stable demand | Risk-off environments | Rarely negative |

---

## Adding real data

The model is designed so you can replace the sample CSV with real data from any of
these sources:

| Source | What it provides | Notes |
|---|---|---|
| [FRED](https://fred.stlouisfed.org) | US macro: GDP, CPI, yields, spreads, VIX | Free API via `fredapi` Python package |
| [ONS](https://www.ons.gov.uk/generator) | UK macro data | CSV download or API |
| [Bank of England](https://www.bankofengland.co.uk/statistics) | UK rates, money supply | CSV download |
| [OECD](https://data.oecd.org) | Multi-country macro data | API or CSV |
| [IMF](https://www.imf.org/en/Data) | Global macro | WEO dataset |
| [Yahoo Finance / yfinance](https://pypi.org/project/yfinance/) | VIX, equity index, oil | Free Python library |
| [FRED via fredapi](https://pypi.org/project/fredapi/) | Full FRED database in Python | Free API key required |

**Steps to connect real data:**
1. Pull each indicator series into a DataFrame.
2. Align to monthly frequency (use end-of-month values for market data).
3. Ensure column names match the names in `INDICATOR_CONFIG` in `src/data_loader.py`.
4. Save to `data/raw/` and update the path in the dashboard sidebar.

---

## Model limitations

This model is a **framework for investment discussion**, not a prediction machine.

1. **Macro data is lagged.** GDP data arrives 30+ days after quarter-end.
2. **Markets move on expectations, not current data.** A weak PMI that beats
   expectations can cause markets to rally.  The model scores actual data, not surprises.
3. **Valuation is not captured.** An overweight signal in a sector at 30× earnings
   is different from the same signal at 12× earnings.
4. **Positioning and sentiment matter.** Crowded trades revert sharply.
5. **Regime changes happen faster than monthly data.** COVID and SVB shifted regimes
   in days; the model would have lagged significantly.
6. **US-centric data.** A global fund needs separate models per region.

---

## Future improvements roadmap

1. **Real data APIs** — Connect to FRED, ONS, OECD via Python APIs.
2. **Backtesting** — Test historical sector allocation returns by regime.
3. **Valuation overlay** — Add P/E ratios, price-to-book, EV/EBITDA by sector.
4. **Earnings revisions** — Add analyst upgrade/downgrade momentum.
5. **Momentum refinement** — Cross-asset momentum scores (bond, FX, commodity).
6. **Probabilistic regimes** — Hamilton (1989) Markov-switching model.
7. **Recession probability** — Formal model using yield curve + credit spreads.
8. **Inflation nowcast** — Predict CPI 1-2 months ahead using PPI + oil price.
9. **Country allocation model** — Separate growth/inflation scoring per country.
10. **Risk management** — Volatility targeting, maximum drawdown controls.

---

## Reading list

See [`learning_notes.md`](learning_notes.md) for the full annotated reading list,
covering both textbooks and research papers with notes on:
- What each work teaches
- How it improves the model
- What variable or signal it would add

---

## Testing

The project includes a comprehensive test suite using pytest.

### Running Tests

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run specific test file
pytest tests/test_transformations.py -v
```

### Test Coverage

- **test_transformations.py**: Z-score computation, edge cases, rolling windows
- **test_scoring.py**: Group score ranges, PCA computation, signal quality
- **test_regimes.py**: All four regime classifications, boundary conditions
- **test_sector_model.py**: OW/UW threshold tests, portfolio construction

### Adding a New Test

```python
# tests/test_new_feature.py
def test_new_feature():
    """Test description."""
    from src.new_module import new_function
    result = new_function(input_data)
    assert result == expected_output
```

---

## Adding a New Indicator (5 Steps)

1. **Update `src/data_loader.py`**: Add the indicator to `INDICATOR_CONFIG`:
   ```python
   "new_indicator": {
       "group": "growth",  # or "inflation", "liquidity", "risk"
       "higher_is_positive": True,
       "description": "What this indicator measures",
   },
   ```

2. **Add to data source**: Include the new column in your CSV or configure
   the FRED connector in `config.py` to fetch it.

3. **Test**: Run `pytest tests/test_data_loader.py` to verify the indicator loads.

4. **Document**: Add a row to the indicator table in this README.

5. **Re-train**: If using PCA-based scoring, the model will automatically
   incorporate the new indicator. Monitor the first principal component
   to ensure it captures the expected variation.

---

---

## Production Deployment (Docker)

The platform can be deployed as a containerized application using Docker Compose.

### Quick Start

```bash
# 1. Clone repository
git clone <repo-url>
cd macro_research_platform/

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys (FRED, SMTP, Slack webhook)

# 3. Start the platform
make start
# Or: docker-compose up -d

# 4. Open http://localhost:3002
```

### Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  Nginx (Port 3002)                                                    │
│  ├─ /           → React Frontend                                     │
│  ├─ /api/       → Flask Backend (Port 5000)                         │
│  └─ /socket.io/ → WebSocket Streaming                                 │
└──────────────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────────────┐
│  Backend Container (Python/Flask + SocketIO)                         │
│  ├─ API endpoints (/api/*)                                            │
│  ├─ WebSocket server                                                  │
│  ├─ SQLite database (persistent volume)                                │
│  └─ Scheduled report generation                                       │
└──────────────────────────────────────────────────────────────────────┘
```

### Operations

```bash
# Check status
make status

# View logs
make logs

# Backup database
make backup

# Access database shell
make db

# Update to latest version
make update

# Stop platform
make stop
```

### Features

- **15 analytical models** — Bridgewater regime, AQR factors, Soros reflexivity, LSTM
- **80+ data series** — FRED, yfinance, CFTC positioning
- **20 dashboard panels** — Real-time signals, risk analytics, portfolio tools
- **WebSocket streaming** — Live price updates every 5 seconds
- **Alert delivery** — Email, Slack, browser notifications
- **Report generation** — Automated morning briefings, PDF export
- **SQLite database** — Persistent storage for signal history, regime log

---

## Design principles

- **Explainability first.** Every number can be traced back to raw data.
- **Modularity.** Each step (transform → score → regime → signal → memo) is
  a separate module that can be improved independently.
- **No black boxes.** The scoring weights are hard-coded and visible — change them
  to reflect your views.
- **Educational.** Code comments explain the financial logic, not just the syntax.
- **Testable.** Each component has unit tests for validation.
