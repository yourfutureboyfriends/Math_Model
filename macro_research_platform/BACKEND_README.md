# Bridgewater-Inspired Macro Research Platform - Backend

A systematic macro research system inspired by Bridgewater Associates' principles.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Macro Research Platform                  │
├─────────────────────────────────────────────────────────────┤
│  Stage 1: Point-in-Time Data Engine                         │
│  Stage 2: Economic Machine Layer                             │
│  Stage 3: Nowcasting Engine                                  │
│  Stage 4: Signal Registry                                    │
│  Stage 5: Portfolio Engine                                 │
│  Stage 6: Scenario Stress Engine                           │
│  Stage 7: Research Validation                              │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

```python
from src.core import create_platform

# Initialize platform
platform = create_platform(environment="development")

# Check platform status
status = platform.get_platform_status()
print(f"Platform: {status['name']} v{status['version']}")

# Analyze economic regime
macro_data = {
    "growth": 2.5,
    "inflation": 3.2,
    "policy_rate": 5.25,
}
regime = platform.get_economic_regime(macro_data)
print(f"Current Regime: {regime['regime']}")
```

## Module Details

### Stage 1: Point-in-Time Data Engine (`src/data/pit/`)

Ensures all backtests use data that was actually available at each point in time.

- **PointInTimeStore**: Core PIT data storage
- **ReleaseCalendar**: Tracks macro release schedules
- **VintageDataManager**: ALFRED integration for true backtesting
- **FredMDLoader**: FRED-MD loader with PCA factor extraction
- **DataQualityEngine**: Data validation and lineage tracking

Key concepts:
- `observation_date`: When the data represents
- `release_date`: When the data was published
- `vintage_date`: Which revision of the data

### Stage 2: Economic Machine Layer (`src/economic_machine/`)

Implements Bridgewater's "Economic Machine" framework.

**Causal Graph** (`causal_graph.py`):
- 32 macro nodes (growth, inflation, policy, etc.)
- 25+ causal relationships with empirical strengths
- Methods: `simulate_shock()`, `get_downstream_effects()`

**Transmission Channels** (`transmission_channels.py`):
- 9 channels: rates, credit, earnings, margin, currency, commodity, liquidity, risk appetite, policy reaction
- Channel activation analysis
- Asset impact estimation

**Policy Reaction Function** (`policy_reaction_function.py`):
- Taylor rule with regime variations
- Policy stance assessment
- Central bank reaction modeling

**Debt Cycle Tracker** (`debt_cycle_tracker.py`):
- Long-term and short-term debt cycle monitoring
- Deleveraging type classification
- Credit availability assessment

### Stage 3: Nowcasting Engine (`src/nowcasting/`)

Real-time macroeconomic estimation.

**Diffusion Index Model** (`diffusion_index_model.py`):
- Business conditions diffusion index
- Turning point identification
- Leading indicator analysis

**Business Conditions Nowcast** (`business_conditions_nowcast.py`):
- Bridge equations for GDP nowcasting
- Factor models
- Recession probability estimation

**Surprise Tracker** (`surprise_tracker.py`):
- Macro surprise vs consensus
- Surprise indices by category
- Expectation bias detection

### Stage 4: Signal Registry (`src/signals/`)

Systematic trading signals with lifecycle management.

**Base Classes** (`signal_base.py`):
- Signal, MacroSignal, TechnicalSignal, CrossAssetSignal
- SignalOutput with direction, strength, confidence
- SignalPerformance tracking

**Regime Signals** (`regime_signals.py`):
- GrowthInflationRegimeSignal
- BusinessCyclePhaseSignal
- PolicyStanceSignal

**Macro Rate Signals** (`macro_rate_signals.py`):
- InflationExpectationsSignal
- YieldCurveSteepenerSignal
- CreditCycleSignal
- TermPremiumSignal

**Cross-Asset Signals** (`cross_asset_signals.py`):
- RatesFXSignal
- CommodityInflationSignal
- CreditEquitySignal
- DollarEMSignal
- RealRatesGoldSignal

### Stage 5: Portfolio Engine (`src/portfolio/`)

Portfolio construction and risk management.

**Expected Return Engine** (`expected_return_engine.py`):
- Signal combination
- Alpha factor construction
- Return forecasting

**Risk Budgeting** (`risk_budgeting.py`):
- Risk parity weights
- Risk budgeting allocation
- Hierarchical Risk Parity (HRP)
- Diversification ratio calculation

**Position Sizing** (`position_sizing.py`):
- Kelly Criterion sizing
- Volatility targeting
- Correlation adjustments
- Drawdown-based sizing

### Stage 6: Scenario Stress Engine (`src/scenarios/`)

Stress testing and scenario analysis.

**ScenarioStressEngine** (`scenario_stress_engine.py`):
- Historical scenarios (2008, 2020, etc.)
- Hypothetical macro shocks
- Expected Shortfall (CVaR)
- Reverse stress testing

### Stage 7: Research Validation (`src/research/`)

Research hypothesis tracking and validation.

**HypothesisRegistry** (`hypothesis_registry.py`):
- Hypothesis lifecycle management
- Status tracking (proposed → validated → production)
- Research lineage

**SignalValidator** (`signal_validation.py`):
- Sharpe ratio validation
- Information coefficient
- Cross-validation
- Regime consistency

**PostmortemEngine** (`postmortem_engine.py`):
- Failure mode analysis
- Root cause identification
- Parameter adjustment recommendations

## Configuration

The platform supports different configurations for development, research, and production:

```python
from src.core import PlatformConfig

# Default configuration
config = PlatformConfig()

# Production configuration (stricter validation)
from src.core.config import get_production_config
config = get_production_config()

# Research configuration (more permissive)
from src.core.config import get_research_config
config = get_research_config()

# Save/load configuration
config.save(Path("config.json"))
config = PlatformConfig.from_file(Path("config.json"))
```

## Dependencies

Core dependencies:
```
pandas >= 1.5.0
numpy >= 1.21.0
scipy >= 1.9.0
```

Optional dependencies (with fallbacks):
```
networkx >= 3.0        # Graph analysis (fallback to adjacency lists)
scikit-learn >= 1.2.0  # Factor extraction (optional)
requests >= 2.28.0     # API clients (optional)
```

Install all dependencies:
```bash
pip install -r requirements-backend.txt
```

## Usage Examples

### Economic Regime Analysis

```python
from src.core import create_platform

platform = create_platform()

# Current macro conditions
macro_data = {
    "growth": 2.5,
    "inflation": 3.2,
    "unemployment": 4.1,
    "policy_rate": 5.25,
}

regime = platform.get_economic_regime(macro_data)
print(f"Regime: {regime['regime']}")
print(f"Implications: {regime['implications']}")
```

### Causal Graph Shock Analysis

```python
from src.economic_machine import CausalGraph

cg = CausalGraph()

# Simulate inflation shock
results = cg.simulate_shock("headline_inflation", shock_magnitude=1.0)
for node, impact in results.items():
    print(f"{node}: {impact['predicted_change']:+.2f} "
          f"(lag: {impact['typical_lag_months']}mo)")
```

### Signal Validation

```python
from src.core import create_platform

platform = create_platform()

# Validate a new signal before production
result = platform.validate_signal(
    signal_name="my_signal",
    signal_series=signal_values,
    returns=asset_returns,
)

if result['validated']:
    print(f"Sharpe: {result['sharpe_ratio']}")
else:
    print(f"Failed: {result['failure_reasons']}")
```

### Risk Budgeting Portfolio

```python
import pandas as pd
from src.portfolio import RiskBudgetingEngine

# Calculate risk parity weights
rb = RiskBudgetingEngine()
weights = rb.calculate_risk_parity_weights(
    cov_matrix=cov_matrix.values,
    asset_names=list(cov_matrix.index),
)

# Generate risk report
risk_report = rb.generate_risk_report(weights, cov_matrix)
print(f"Portfolio volatility: {risk_report['annualized_volatility']:.1%}")
```

### Stress Testing

```python
from src.core import create_platform

platform = create_platform()

# Run stress tests
results = platform.run_stress_test(
    portfolio_weights=weights,
    scenario_names=["2008_financial_crisis", "inflation_shock"]
)

for scenario, result in results.items():
    print(f"{scenario}: {result.portfolio_loss:.1%} loss")
```

## Testing

Run the quickstart example:
```bash
python examples/quickstart.py
```

## Architecture Principles

1. **Point-in-Time Discipline**: All data must respect observation_date vs release_date
2. **Systematic Process**: Research hypotheses → validation → production → postmortem
3. **Macro-to-Assets**: Trace causal chains from macro to asset prices
4. **Risk-First**: Risk budgeting before return optimization
5. **Regime Awareness**: Different behaviors in different macro environments

## License

MIT License - See LICENSE file for details.
