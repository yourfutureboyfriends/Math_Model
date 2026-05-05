# Data Lineage Report

**Generated:** 2026-04-26T20:00:54.213847
**System Date:** 2026-04-26
**Data Mode:** live
**Total Metrics Tracked:** 21
**Issues Found:** 14

---

## Executive Summary

### ⚠️ Data Issues Requiring Attention

- **Financial Conditions Ease**: needs_clarification
  - Flag: `NEEDS_LEVEL_VS_DIRECTION_SEPARATION`
  - Note: Level shows easy/tight, direction shows easing/tightening. Both must be displayed.
- **Risk Appetite**: needs_clarification
  - Flag: `NEEDS_LEVEL_VS_DIRECTION_SEPARATION`
- **Recession Risk (Top Level)**: needs_hierarchy_clarification
  - Flag: `MISMATCH_WITH_US_RECESSION_RISK`
  - Note: Top-level recession risk may differ from country-specific. Need clear separation.
- **Sector Signal: Technology**: PLACEHOLDER
  - Flag: `DEFAULT_NEUTRAL_SIGNAL`
- **Sector Signal: Financials**: PLACEHOLDER
  - Flag: `DEFAULT_NEUTRAL_SIGNAL`
- **Sector Signal: Energy**: PLACEHOLDER
  - Flag: `DEFAULT_NEUTRAL_SIGNAL`
- **Sector Signal: Consumer Discretionary**: PLACEHOLDER
  - Flag: `DEFAULT_NEUTRAL_SIGNAL`
- **Sector Signal: Consumer Staples**: PLACEHOLDER
  - Flag: `DEFAULT_NEUTRAL_SIGNAL`
- **Sector Signal: Healthcare**: PLACEHOLDER
  - Flag: `DEFAULT_NEUTRAL_SIGNAL`
- **Sector Signal: Industrials**: PLACEHOLDER
  - Flag: `DEFAULT_NEUTRAL_SIGNAL`
- **Sector Signal: Materials**: PLACEHOLDER
  - Flag: `DEFAULT_NEUTRAL_SIGNAL`
- **Sector Signal: Utilities**: PLACEHOLDER
  - Flag: `DEFAULT_NEUTRAL_SIGNAL`
- **Sector Signal: Communication Services**: PLACEHOLDER
  - Flag: `DEFAULT_NEUTRAL_SIGNAL`
- **Sector Signal: Real Estate**: PLACEHOLDER
  - Flag: `DEFAULT_NEUTRAL_SIGNAL`

## Metrics by Category

### Macro Scores

| Metric | Value | Source | Status |
|--------|-------|--------|--------|
| Growth Score | +0.08 | enhanced_macro_classifier.py | ❌ derived |
| Inflation Score | +1.07 (elevated) | enhanced_macro_classifier.py | ✅ ok |
| Financial Conditions Ease | +0.64 | enhanced_macro_classifier.py | ⚠️ needs_clarification |
| Risk Appetite | -0.20 | enhanced_macro_classifier.py | ⚠️ needs_clarification |

### Risk Metrics

| Metric | Value | Source | Status |
|--------|-------|--------|--------|
| Recession Risk (Top Level) | 5.3% | enhanced_macro_classifier.py | ⚠️ needs_hierarchy_clarification |

### Data Quality

| Metric | Value | Source | Status |
|--------|-------|--------|--------|
| Latest Data Date | 2026-03-31 00:00:00 | data_loader_live.py | ✅ ok |
| Live Series Available | 17 | data_loader_live.py | ✅ ok |

### Sector Signals

| Metric | Value | Source | Status |
|--------|-------|--------|--------|
| Sector Signal: Technology | Neutral | enhanced_macro_classifier.py | ❌ PLACEHOLDER |
| Sector Signal: Financials | Neutral | enhanced_macro_classifier.py | ❌ PLACEHOLDER |
| Sector Signal: Energy | Neutral | enhanced_macro_classifier.py | ❌ PLACEHOLDER |
| Sector Signal: Consumer Discretionary | Neutral | enhanced_macro_classifier.py | ❌ PLACEHOLDER |
| Sector Signal: Consumer Staples | Neutral | enhanced_macro_classifier.py | ❌ PLACEHOLDER |
| Sector Signal: Healthcare | Neutral | enhanced_macro_classifier.py | ❌ PLACEHOLDER |
| Sector Signal: Industrials | Neutral | enhanced_macro_classifier.py | ❌ PLACEHOLDER |
| Sector Signal: Materials | Neutral | enhanced_macro_classifier.py | ❌ PLACEHOLDER |
| Sector Signal: Utilities | Neutral | enhanced_macro_classifier.py | ❌ PLACEHOLDER |
| Sector Signal: Communication Services | Neutral | enhanced_macro_classifier.py | ❌ PLACEHOLDER |
| Sector Signal: Real Estate | Neutral | enhanced_macro_classifier.py | ❌ PLACEHOLDER |

### Business Layer

| Metric | Value | Source | Status |
|--------|-------|--------|--------|
| Business Layer: expected_returns | Generated |  | ✅ ok |
| Business Layer: position_sizing | Generated |  | ✅ ok |
| Business Layer: decision_log | Generated |  | ✅ ok |

## Complete Lineage Details

| Metric | Value | Transformation | Data Mode | Status |
|--------|-------|----------------|-----------|--------|
| Growth Score | +0.08 | ensemble_weighted_average -> z... | live | derived |
| Inflation Score | +1.07 (elevated) | ensemble_weighted_average -> z... | live | ok |
| Financial Conditions Ease | +0.64 | yield_spread_calculation -> cr... | live | needs_clarification |
| Risk Appetite | -0.20 | vix_inversion -> spread_compos... | live | needs_clarification |
| Recession Risk (Top Level) | 5.3% | yield_curve_inversion + unempl... | live | needs_hierarchy_clarification |
| Latest Data Date | 2026-03-31 00:00:00 | resample('ME').last() -> forwa... | live | ok |
| Live Series Available | 17 | count_columns... | live | ok |
| Sector Signal: Technology | Neutral | macro_regime_mapping -> sector... | live | PLACEHOLDER |
| Sector Signal: Financials | Neutral | macro_regime_mapping -> sector... | live | PLACEHOLDER |
| Sector Signal: Energy | Neutral | macro_regime_mapping -> sector... | live | PLACEHOLDER |
| Sector Signal: Consumer Discretionary | Neutral | macro_regime_mapping -> sector... | live | PLACEHOLDER |
| Sector Signal: Consumer Staples | Neutral | macro_regime_mapping -> sector... | live | PLACEHOLDER |
| Sector Signal: Healthcare | Neutral | macro_regime_mapping -> sector... | live | PLACEHOLDER |
| Sector Signal: Industrials | Neutral | macro_regime_mapping -> sector... | live | PLACEHOLDER |
| Sector Signal: Materials | Neutral | macro_regime_mapping -> sector... | live | PLACEHOLDER |
| Sector Signal: Utilities | Neutral | macro_regime_mapping -> sector... | live | PLACEHOLDER |
| Sector Signal: Communication Services | Neutral | macro_regime_mapping -> sector... | live | PLACEHOLDER |
| Sector Signal: Real Estate | Neutral | macro_regime_mapping -> sector... | live | PLACEHOLDER |
| Business Layer: expected_returns | Generated | signal_registry -> expected_re... | live | ok |
| Business Layer: position_sizing | Generated | signal_registry -> expected_re... | live | ok |
| Business Layer: decision_log | Generated | signal_registry -> expected_re... | live | ok |
