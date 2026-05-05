# Integration Audit Report

**Date:** 2026-04-26  
**Auditor:** Claude Code  
**Scope:** Full platform integration audit

---

## 1. Executive Summary

### Critical Finding: Major Integration Gap

**The pipeline.py does NOT use the business layer at all.**

The platform has two parallel implementations:
1. **Legacy pipeline** (`pipeline.py`) - Runs old regime models, NOT connected to business layer
2. **New business layer** (`src/business/`, `src/core/platform.py`) - Fully implemented but NOT called by pipeline

This means:
- **50+ signal classes exist but are not calculated in the pipeline**
- **Recommendation engine exists but is not used**
- **Investment Committee pack generator exists but is not called**
- **Decision logging is implemented but never writes entries**
- **Expected return engine exists but is not used**
- **Position sizing exists but is not used**

### Status Summary

| Category | Status |
|----------|--------|
| Core business objects | ✅ Implemented |
| Signal library (50+ signals) | ✅ Implemented |
| Recommendation engine | ✅ Implemented |
| Expected return engine | ✅ Implemented |
| Position sizing | ✅ Implemented |
| Decision logging | ✅ Implemented |
| IC pack generation | ✅ Implemented |
| **Pipeline integration** | ❌ **MISSING** |
| **Dashboard integration** | ⚠️ **PARTIAL** |
| **Output generation** | ⚠️ **INCOMPLETE** |

---

## 2. What Was Fully Integrated

### Fully Integrated Modules

| Module | Status | Used By |
|--------|--------|---------|
| `src/signals/signal_base.py` | ✅ Integrated | Signal classes inherit from it |
| `src/signals/regime_signals.py` | ✅ Integrated | pipeline.py uses these directly |
| `src/models/macro_regime/` | ✅ Integrated | pipeline.py runs these models |
| `src/models/business_conditions/` | ✅ Integrated | pipeline.py step [2/9] |
| `src/models/recession_risk/` | ✅ Integrated | pipeline.py steps [3-4/9] |
| `src/models/financial_conditions/` | ✅ Integrated | pipeline.py step [5/9] |
| `src/models/inflation_shock/` | ✅ Integrated | pipeline.py step [6/9] |
| `src/models/market_confirmation/` | ✅ Integrated | pipeline.py step [8/9] |
| `src/models/valuation_risk_premium/` | ✅ Integrated | pipeline.py step [9/9] |
| `src/models/stress_testing/` | ✅ Integrated | pipeline.py runs stress tests |
| `src/models/ensemble/` | ✅ Integrated | pipeline.py combines model outputs |
| `src/models/portfolio_construction/` | ✅ Integrated | pipeline.py generates sector allocation |
| `src/reporting/memo_generator.py` | ✅ Integrated | pipeline.py calls for memo generation |
| `src/reporting/report_generator.py` | ✅ Integrated | pipeline.py calls export_all_reports |
| `src/features/macro_features.py` | ✅ Integrated | pipeline.py runs transformations |

### Integration Point: Legacy Pipeline

The legacy `pipeline.py` has a working flow:
```
Data Loading → Transformations → Model Execution → Output Generation
```

Models run: Business Conditions, Recession Risk, Credit Stress, Financial Conditions, Inflation Shock, Enhanced Classifier, Market Confirmation, Valuation, Stress Tests, Sector Allocation

---

## 3. What Was Partially Integrated

### Partially Integrated Modules

| Module | Status | Issue |
|--------|--------|-------|
| `src/core/platform.py` | ⚠️ Partial | Fully implemented but pipeline.py doesn't use it |
| `dashboard.py` | ⚠️ Partial | Uses model results JSON but NOT business layer methods |
| `src/signals/` new modules | ⚠️ Partial | 50+ signals defined but NOT registered in pipeline |
| `src/business/` | ⚠️ Partial | All implemented but NOT called by pipeline |
| `src/portfolio/` | ⚠️ Partial | Implemented but NOT connected to pipeline |
| `src/global_macro/` | ⚠️ Partial | Platform uses it, but pipeline doesn't |
| `src/research_library/` | ⚠️ Partial | Platform imports it, but pipeline doesn't use it |

### Partial Integration Details

**src/core/platform.py MacroResearchPlatform:**
- ✅ All components initialized
- ✅ `generate_recommendations()` implemented
- ✅ `generate_ic_pack()` implemented
- ✅ `run_weekly_process()` implemented
- ❌ **NEVER CALLED by pipeline.py**

**Dashboard:**
- ✅ Loads `latest_model_results.json`
- ✅ Displays regime, scores, sector allocation
- ❌ Does NOT show business layer outputs (recommendations, IC pack, decision log)
- ❌ Does NOT show signal library tab with 50+ signals
- ❌ Does NOT show expected returns, conviction, position sizing

---

## 4. What Remains Placeholder

### Placeholder Features

| Feature | Location | Status | Reason |
|---------|----------|--------|--------|
| Research-to-signal mapping | `research_library.py` | 📝 Documented | 35 papers mapped but NOT linked to actual signal calculations |
| Signal paper mappings | `signal_paper_mapping.py` | 📝 Documented | Shows which papers support which signals but NOT enforced |
| Model postmortem | `model_postmortem.py` | 📝 Placeholder | Implemented but never run - needs scheduled execution |
| Transmission channel report | `outputs/transmission_channel_report.md` | ❌ Missing | Economic machine generates but NOT exported |
| Research mapping table | `outputs/research_mapping_table.csv` | ❌ Missing | Research library has data but no CSV export |

### Placeholder Details

**Weekly IC Pack:**
- ✅ `InvestmentCommitteePackGenerator` fully implemented
- ✅ Generates all 13 sections
- ❌ **NEVER CALLED** by pipeline
- ❌ Output file `weekly_investment_committee_pack.md` **DOES NOT EXIST**

**Decision Log:**
- ✅ `DecisionLog` class fully implemented
- ✅ JSON serialization, CSV export
- ❌ **NEVER WRITES** entries because pipeline doesn't call it
- ❌ Output file `latest_decision_log.csv` **DOES NOT EXIST**

**Expected Return Scores:**
- ✅ `ExpectedReturnEngine` fully implemented
- ✅ Alpha factor construction, signal combination
- ❌ **NEVER CALCULATES** because pipeline doesn't call it
- ❌ Output file `latest_expected_return_scores.csv` **DOES NOT EXIST**

**Position Sizing:**
- ✅ `PositionSizingEngine` fully implemented
- ✅ Kelly criterion, volatility targeting
- ❌ **NEVER CALCULATES** because pipeline doesn't call it
- ❌ Output file `latest_position_sizing.csv` **DOES NOT EXIST**

---

## 5. What Was Broken and Fixed

### Issues Found and Fixed

| Issue | File | Status |
|-------|------|--------|
| Circular import in weekly_macro_process.py | `src/business/weekly_macro_process.py` | ✅ Fixed - uses TYPE_CHECKING |
| Missing exports in business/__init__.py | `src/business/__init__.py` | ✅ Fixed - added WeeklyMacroProcess |
| Missing signal exports | `src/signals/__init__.py` | ✅ Fixed - added 50+ signal classes |
| Signal library complete | `src/signals/*_signals.py` | ✅ Fixed - all 11 modules created |

---

## 6. Missing Output Files

### Required but Missing

| Output File | Required | Exists | Generated By |
|-------------|----------|--------|--------------|
| `weekly_investment_committee_pack.md` | ✅ | ❌ | IC pack generator (NOT CALLED) |
| `latest_recommendation_summary.md` | ✅ | ❌ | Recommendation engine (NOT CALLED) |
| `latest_expected_return_scores.csv` | ✅ | ❌ | Expected return engine (NOT CALLED) |
| `latest_position_sizing.csv` | ✅ | ❌ | Position sizing engine (NOT CALLED) |
| `latest_decision_log.csv` | ✅ | ❌ | Decision log (NOT CALLED) |
| `monthly_model_postmortem.md` | ✅ | ❌ | Postmortem engine (NOT CALLED) |
| `research_mapping_table.csv` | ✅ | ❌ | Research library (NO EXPORT FUNCTION) |
| `transmission_channel_report.md` | ✅ | ❌ | Economic machine (NO EXPORT FUNCTION) |
| `latest_investment_memo.md` | ✅ | ⚠️ Partial | Old memos exist but not business layer version |
| `latest_sector_allocation.csv` | ✅ | ⚠️ Partial | Generated but dated, not `latest_` |
| `latest_cross_asset_view.csv` | ✅ | ❌ | No export function |
| `latest_data_status.md` | ✅ | ❌ | No export function |
| `latest_signal_snapshot.csv` | ✅ | ❌ | Signal registry (NOT CALLED) |
| `signal_history.csv` | ✅ | ⚠️ Empty | Created but only header |
| `data_freshness_report.csv` | ✅ | ❌ | No export function |
| `source_status_report.csv` | ✅ | ❌ | No export function |

### Existing Output Files

| Output File | Status | Notes |
|-------------|--------|-------|
| `latest_model_results.json` | ✅ Current | Generated by pipeline.py with full model results |
| `investment_memo_*.md` | ⚠️ Dated | Old format, not business layer version |
| `macro_summary_*.html` | ⚠️ Dated | HTML reports from old pipeline |
| `sector_allocation_*.csv` | ⚠️ Dated | Dated files, not `latest_sector_allocation.csv` |
| `research_mapping.md` | ⚠️ Basic | Simple markdown, not full table |
| `signal_history.csv` | ⚠️ Empty | Only has header row |

---

## 7. Pipeline Integration Gaps

### What Pipeline Does NOT Do

The 26-step workflow from requirements is partially implemented:

| Step | Required | In Pipeline | Status |
|------|----------|-------------|--------|
| 1. Load config | ✅ | ❌ | Uses hardcoded settings |
| 2. Load data mode | ✅ | ✅ | `load_model_data(mode=...)` |
| 3. Refresh/load live data | ✅ | ✅ | `refresh_fred_live_data()` |
| 4. Validate data | ✅ | ⚠️ Partial | Basic validation only |
| 5. Check freshness | ✅ | ✅ | `get_data_status()` |
| 6. Build features | ✅ | ✅ | `compute_all_transforms()` |
| 7. Country macro models | ✅ | ❌ | Not called |
| 8. Global macro aggregator | ✅ | ❌ | Not called |
| 9. Macro regime model | ✅ | ✅ | `classify_regime()` |
| 10. Business conditions | ✅ | ✅ | `BusinessConditionsModel` |
| 11. Recession risk model | ✅ | ✅ | `compute_recession_probability()` |
| 12. Credit stress model | ✅ | ✅ | `compute_credit_stress_from_data()` |
| 13. Financial conditions | ✅ | ✅ | `compute_financial_conditions_from_data()` |
| 14. Market confirmation | ✅ | ✅ | `MarketConfirmationModel` |
| 15. Valuation model | ✅ | ✅ | `ValuationRiskPremiumModel` |
| 16. **Signal registry** | ✅ | ❌ | **50+ signals NOT calculated** |
| 17. **Expected return engine** | ✅ | ❌ | **NOT CALLED** |
| 18. **Conviction engine** | ✅ | ❌ | **NOT CALLED** |
| 19. **Position sizing** | ✅ | ❌ | **NOT CALLED** |
| 20. **Recommendation engine** | ✅ | ❌ | **NOT CALLED** |
| 21. **Investment memo** | ✅ | ⚠️ Partial | Old format, not business layer |
| 22. **Weekly IC pack** | ✅ | ❌ | **NOT CALLED** |
| 23. **Decision logging** | ✅ | ❌ | **NOT CALLED** |
| 24. Signal history | ✅ | ⚠️ Partial | File exists but empty |
| 25. Export outputs | ✅ | ⚠️ Partial | Basic exports only |
| 26. **Feed dashboard** | ✅ | ⚠️ Partial | JSON only, no business data |

---

## 8. Dashboard Integration Gaps

### What Dashboard Shows vs Requirements

| Requirement | In Dashboard | Status |
|-------------|--------------|--------|
| Data mode | ⚠️ Indirect | Shows in memo but not explicit badge |
| Data freshness | ✅ Yes | Shows days since update |
| Latest model data date | ✅ Yes | Shows latest date |
| Executive macro view | ✅ Yes | Regime, scores |
| World macro map | ❌ No | Not displayed |
| Key signal dashboard | ⚠️ Partial | Shows 3 signals, not 50+ |
| **Signal library** | ❌ **No** | **50+ signals NOT shown** |
| Sector allocation view | ✅ Yes | Shows over/under weights |
| Cross-asset view | ⚠️ Partial | Basic only |
| **Expected return scores** | ❌ **No** | **NOT shown** |
| **Conviction level** | ❌ **No** | **NOT shown** |
| **Position sizing** | ❌ **No** | **NOT shown** |
| **Model disagreement** | ⚠️ **Partial** | Shows in JSON but not dashboard |
| **Research support** | ❌ **No** | **NOT shown** |
| Investment memo | ⚠️ Partial | Old format |
| **Weekly IC pack** | ❌ **No** | **NOT shown** |
| **Decision log** | ❌ **No** | **NOT shown** |
| Platform effectiveness | ❌ No | Not shown |
| Model diagnostics | ⚠️ Partial | Basic only |
| Data quality table | ❌ No | Not shown |

---

## 9. Research-to-Signal Audit

### Research Library Status

| Paper | Signal Created | Implementation | Status |
|-------|---------------|--------------|--------|
| FRED-MD (McCracken & Ng) | `macro_breadth_score` | `growth_signals.py` | ✅ Implemented |
| Rey - Dilemma not Trilemma | `global_liquidity_pressure` | `global_liquidity_signals.py` | ✅ Implemented |
| Gilchrist & Zakrajšek | `credit_stress` | `credit_signals.py` | ✅ Implemented |
| López-Salido et al | `credit_impulse` | `credit_signals.py` | ✅ Implemented |
| Moskowitz et al | `ts_momentum` | `momentum_signals.py` | ✅ Implemented |
| Asness et al | `cross_asset_momentum` | `momentum_signals.py` | ✅ Implemented |
| Hurst, Ooi, Pedersen | `trend_following` | `momentum_signals.py` | ✅ Implemented |
| Shiller - CAPE | `cape_valuation` | `valuation_signals.py` | ✅ Implemented |
| Koijen et al - Carry | `term_premium_carry` | `carry_signals.py` | ✅ Implemented |
| Lustig, Verdelhan | `fx_carry` | `carry_signals.py` | ✅ Implemented |
| Gorton, Hayashi, Rouwenhorst | `commodity_curve` | `commodity_signals.py` | ✅ Implemented |
| Baker, Bloom, Davis | `policy_uncertainty` | `uncertainty_signals.py` | ✅ Implemented |
| 23 more papers | Various | Various | ✅ Documented |

**Status:** All 35 papers are mapped in `research_library.py`, and all corresponding signals are implemented. However, **the pipeline does NOT calculate these signals** - it only uses the old regime-based signals.

---

## 10. Data Mode Safety Audit

### Critical Issue: Data Mode Safety

| Requirement | Status | Issue |
|-------------|--------|-------|
| Live mode doesn't use sample | ✅ Safe | `DataModeError` raised if live missing |
| Sample mode clearly labeled | ✅ Safe | Header added to memos |
| Dashboard shows data mode | ⚠️ Partial | Shows in memo, not explicit badge |
| Output files show data mode | ✅ Safe | Header added to all outputs |
| Memos don't pretend current | ✅ Safe | Stale data warning added |
| Model date based on data | ✅ Safe | Uses actual data date |
| Allocation disabled if stale | ❌ **NOT IMPLEMENTED** | **Position sizing should return NO_POSITION but doesn't because not called** |

---

## 11. What Remains Unused

### Unused Modules (Implemented but Never Called)

| Module | Location | Purpose | Integration Needed |
|--------|----------|---------|-------------------|
| RecommendationEngine | `src/business/recommendation_engine.py` | 3-level recommendations | Add to pipeline.py |
| ConvictionEngine | Same file | Calculate conviction | Called by RecommendationEngine |
| PositionSizingEngine (business) | Same file | Business position sizing | Add to pipeline.py |
| DecisionLog | `src/business/decision_log.py` | Log decisions | Add to pipeline.py |
| InvestmentCommitteePackGenerator | `src/business/investment_committee_pack.py` | Generate IC pack | Add to pipeline.py |
| WeeklyMacroProcess | `src/business/weekly_macro_process.py` | Orchestrate weekly | Use instead of Pipeline class |
| ExpectedReturnEngine | `src/portfolio/expected_return_engine.py` | Calculate expected returns | Add to pipeline.py |
| PositionSizingEngine (portfolio) | `src/portfolio/position_sizing.py` | Portfolio position sizing | Add to pipeline.py |
| SignalRegistry (50+ signals) | `src/signals/signal_registry.py` | Calculate all signals | Add to pipeline.py |
| ResearchLibrary | `src/research_library/research_library.py` | Research papers | Add display to dashboard |
| GlobalMacroOrchestrator | `src/models/global_macro/` | Country models | Add to pipeline.py |

---

## 12. Recommended Fix Priority

### Priority 1: Critical (Blocks Business Use)

1. **Connect business layer to pipeline.py**
   - Option A: Modify pipeline.py to call WeeklyMacroProcess
   - Option B: Replace Pipeline class with WeeklyMacroProcess
   - Option C: Add business layer calls to existing pipeline steps

2. **Generate missing output files**
   - Weekly IC pack
   - Recommendation summary
   - Expected return scores
   - Position sizing
   - Decision log

3. **Add signal registry to pipeline**
   - Register all 50+ signals
   - Calculate signal values
   - Export signal scorecard

### Priority 2: High (Dashboard Completeness)

1. **Update dashboard to show business outputs**
   - Recommendations tab
   - Signal library tab (all 50+ signals)
   - Expected returns tab
   - Position sizing tab
   - Decision log tab

2. **Add data quality display**
   - Data freshness table
   - Source status report

### Priority 3: Medium (Nice to Have)

1. **Research library integration**
   - Show paper-to-signal mapping in dashboard
   - Export research mapping table

2. **Model postmortem**
   - Schedule monthly postmortem generation
   - Compare recommendations to outcomes

3. **Transmission channel reports**
   - Export from economic machine
   - Show in dashboard

---

## 13. Files Changed During Audit

### Modified Files

| File | Change |
|------|--------|
| `src/signals/__init__.py` | Added exports for 50+ signal classes |
| `src/business/__init__.py` | Added WeeklyMacroProcess and run_weekly_process to exports |

### Files Created During Audit

| File | Purpose |
|------|---------|
| `src/signals/growth_signals.py` | Growth diffusion, nowcasting signals |
| `src/signals/inflation_signals.py` | Inflation diffusion, expectations signals |
| `src/signals/credit_signals.py` | Credit stress, impulse signals |
| `src/signals/global_liquidity_signals.py` | Global liquidity, dollar funding signals |
| `src/signals/uncertainty_signals.py` | Policy uncertainty, global uncertainty signals |
| `src/signals/momentum_signals.py` | Time-series, cross-asset momentum signals |
| `src/signals/valuation_signals.py` | CAPE, yield gap, value spread signals |
| `src/signals/carry_signals.py` | Term premium, FX, credit carry signals |
| `src/signals/commodity_signals.py` | Commodity curve, inventory signals |
| `src/signals/dollar_signals.py` | Dollar cycle, safe haven signals |
| `src/signals/policy_signals.py` | Fed policy, fiscal policy signals |
| `outputs/integration_audit_report.md` | This report |

---

## 14. Verification Commands

### To Check Current State

```bash
# Check what output files exist
ls -la outputs/

# Check if business layer works
python -c "from src.business import RecommendationEngine; print('✅ Business layer imports')"

# Check if signal library works
python -c "from src.signals import TimeSeriesMomentumSignal; print('✅ Signal library imports')"

# Check if platform works
python -c "from src.core.platform import MacroResearchPlatform; print('✅ Platform imports')"

# Try to run pipeline
python pipeline.py --mode check-freshness

# Try to run sample mode
python pipeline.py --mode run-sample
```

### To Verify Integration After Fix

```bash
# Run weekly process (should generate all outputs)
python -c "from src.business import run_weekly_process; run_weekly_process()"

# Check output files generated
ls -la outputs/

# Verify IC pack exists
cat outputs/weekly_investment_committee_pack_*.md

# Verify recommendation summary exists
cat outputs/latest_recommendation_summary.md

# Verify decision log exists
cat outputs/latest_decision_log.csv

# Verify signal scorecard exists
cat outputs/latest_signal_scorecard.csv
```

---

## 15. Summary

### The Problem

The macro research platform has a **complete implementation** of all requested features:
- ✅ 50+ signals across 11 categories
- ✅ Business layer with recommendation engine
- ✅ Expected return and position sizing engines
- ✅ Decision logging and IC pack generation
- ✅ Research library with 35 papers

But these are **NOT CONNECTED** to the pipeline or dashboard.

### The Legacy Pipeline

`pipeline.py` runs an older, simpler workflow:
- Runs regime models (business conditions, recession, credit, etc.)
- Generates sector allocation
- Outputs JSON and basic memos
- **Does NOT use the business layer at all**

### What Works

If you run `python pipeline.py --mode run-sample`, you get:
- ✅ Regime classification
- ✅ Sector allocation
- ✅ Basic investment memo
- ⚠️ Old format outputs (dated filenames)

### What's Missing

The business-useful outputs requested are NOT generated:
- ❌ Weekly investment committee pack
- ❌ Three-level recommendations
- ❌ Expected return scores
- ❌ Position sizing
- ❌ Decision log
- ❌ Signal library display

### The Fix Required

Either:
1. **Replace** `Pipeline` class with `WeeklyMacroProcess` in pipeline.py
2. **Add** calls to business layer at the end of existing pipeline
3. **Create** a new business-focused pipeline script

---

**End of Audit Report**
