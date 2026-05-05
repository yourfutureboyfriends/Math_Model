# Research Library

This document maps 35 research papers to specific signals and implementation files in the macro research platform.

## Overview

**Total Papers:** 35
**Categories:** 6
**Implemented:** TBD
**Partial:** TBD
**Not Implemented:** TBD

## Categories

### A. Macro Data and Nowcasting (7 papers)

| Paper | Authors | Signal | Status |
|-------|---------|--------|--------|
| FRED-MD | McCracken & Ng | macro_breadth_score | Not Implemented |
| FRED-QD | McCracken & Ng | quarterly_macro_cycle | Not Implemented |
| Diffusion Indexes | Stock & Watson | business_conditions_diffusion_index | Partial |
| Real-Time Business Conditions | Aruoba, Diebold, Scotti | real_time_business_conditions | Not Implemented |
| Nowcasting GDP | Giannone, Reichlin, Small | gdp_nowcast | Not Implemented |
| Big Data Nowcasting | Bok et al | big_data_macro_signal | Not Implemented |
| PCA | Stock & Watson | pca_macro_factor | Not Implemented |

### B. Global Liquidity and World Macro (5 papers)

| Paper | Authors | Signal | Status |
|-------|---------|--------|--------|
| Dilemma Not Trilemma | Helene Rey | global_liquidity_pressure | Not Implemented |
| US Policy and Global Cycle | Miranda-Agrippino & Rey | us_policy_global_transmission_signal | Not Implemented |
| CIP Deviations | Du, Tepper, Verdelhan | dollar_funding_stress | Not Implemented |
| World Uncertainty Index | Ahir, Bloom, Furceri | global_uncertainty_risk | Not Implemented |
| Economic Policy Uncertainty | Baker, Bloom, Davis | policy_uncertainty_risk | Not Implemented |

### C. Business Cycle, Recession, and Credit (6 papers)

| Paper | Authors | Signal | Status |
|-------|---------|--------|--------|
| Predicting US Recessions | Estrella & Mishkin | recession_probability_combined | Partial |
| Term Structure | Estrella & Hardouvelis | yield_curve_recession_signal | Partial |
| Financial Cycle vs Term Spread | Borio, Drehmann, Xia | financial_cycle_recession_signal | Not Implemented |
| Credit Spreads | Gilchrist & Zakrajsek | credit_stress_signal | Partial |
| Credit Sentiment | Lopez-Salido, Stein, Zakrajsek | credit_impulse_signal | Not Implemented |
| Vulnerable Growth | Adrian, Boyarchenko, Giannone | growth_at_risk | Not Implemented |

### D. Macro Regimes and Asset Allocation (5 papers)

| Paper | Authors | Signal | Status |
|-------|---------|--------|--------|
| All Weather | Bridgewater | environment_balance_score | Partial |
| Regime Switching | Hamilton | regime_probability | Partial |
| Regime Changes | Ang & Timmermann | regime_transition_risk | Not Implemented |
| Insight Macro AA | Insight Investment | macro_regime_allocation | Partial |
| EIB Macro AA | European Investment Bank | macro_financial_cycle_signal | Not Implemented |

### E. Cross-Asset Momentum, Value, Carry (5 papers)

| Paper | Authors | Signal | Status |
|-------|---------|--------|--------|
| Time Series Momentum | Moskowitz, Ooi, Pedersen | cross_asset_momentum_confirmation | Partial |
| Trend Following | Hurst, Ooi, Pedersen | trend_following_overlay | Not Implemented |
| Value and Momentum | Asness, Moskowitz, Pedersen | cross_asset_value_score | Partial |
| Carry | Koijen, Moskowitz, Pedersen | carry_score | Not Implemented |
| Bond Risk Premia | Cochrane & Piazzesi | bond_risk_premium | Not Implemented |

### F. Portfolio Construction (7 papers)

| Paper | Authors | Signal | Status |
|-------|---------|--------|--------|
| Black-Litterman | Black & Litterman | black_litterman_weights | Partial |
| Volatility-Managed | Moreira & Muir | volatility_managed_position | Partial |
| Momentum Risk | Barroso & Santa-Clara | risk_managed_momentum | Not Implemented |
| Betting Against Beta | Frazzini & Pedersen | beta_arbitrage | Not Implemented |
| Leverage Aversion | Asness, Frazzini, Pedersen | risk_parity_allocation | Partial |
| Portfolio Selection | Markowitz | mean_variance_optimal | Partial |

## Usage

```python
from src.research_library import get_paper, get_papers_by_category, ResearchCategory

# Get a specific paper
paper = get_paper("mop_tsmom")
print(paper.business_use)

# Get papers by category
papers = get_papers_by_category(ResearchCategory.MACRO_REGIMES)

# Get implementation status
from src.research_library import get_implementation_status
status = get_implementation_status()
```

## Implementation Priority

### High Priority (Core Business)
1. FRED-MD data backbone
2. Recession prediction (Estrella & Mishkin)
3. Credit spreads (Gilchrist & Zakrajsek)
4. Time series momentum (Moskowitz, Ooi, Pedersen)
5. Black-Litterman allocation

### Medium Priority (Enhancement)
1. Global liquidity (Rey)
2. Regime switching (Hamilton)
3. Value and momentum (Asness)
4. Volatility targeting (Moreira & Muir)

### Lower Priority (Advanced)
1. Nowcasting with big data
2. CIP deviations
3. Growth at risk
4. Risk parity optimization
