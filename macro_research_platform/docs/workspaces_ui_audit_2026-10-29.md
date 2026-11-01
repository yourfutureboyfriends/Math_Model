# Workspace UI audit — 29 October 2026

Registry coverage spans all five workspaces. This records UI coverage, not financial model certification or visual verification of every populated live-data flow.

| Workspace | Registered panels/pages |
|---|---:|
| Macro | 47 |
| Trading | 28 |
| Quant | 10 |
| Markets | 94 |
| Pe | 4 |

No unmapped registry entries remain. See the separate [Markets audit](markets_ui_audit_2026-10-29.md) and [full machine-readable coverage](workspace_page_inventory_2026-10-29.json).

## Improvements

Searchable workspace navigation, registry-derived counts and a shared density preference now accompany consistent cards, metrics, controls, loading and empty states. The inner-surface pass touched 51 files: 62 control groups, 34 chart areas, 71 scrollable table wrappers, 8 keyboard-accessible rows and 15 tab groups.

Nested tabs support arrow keys, Home and End. Dashboard fold controls are native buttons and preserve mounted form state. PE stage summaries filter deals, filtered empty results can be reset, and the pipeline fills available width until details open.

An unstable Equity Research selector was fixed: its fresh empty-array fallback could trigger repeated rendering when dashboard data was unavailable.

## Verification limits

New component checks mount 89 registered Macro, Trading, Quant and PE views with pending requests. Behavior checks cover navigation, tabs, panel folding and PE filtering. Existing Markets checks cover loading/unavailable states. Authenticated trading, deployment and deal mutations were not exercised. Browser verification of this pass was blocked by browser network/navigation errors. Existing large-bundle build warnings remain. These UI checks do not certify valuation accuracy.

## Non-Markets panel matrix

| Workspace | Panel | Component source |
|---|---|---|
| macro | macro-model | src/components/sections/model/MacroModelSection.tsx, src/components/sections/model/MacroModelSection.tsx, src/components/sections/model/MacroModelSection.tsx, src/components/ui/LineChart.tsx, src/components/ui/LineChart.tsx, src/components/sections/model/TimeMachine.tsx, src/components/sections/model/TimeMachine.tsx |
| macro | morning-brief | src/components/sections/macro/MorningBriefSection.tsx, src/components/sections/macro/MorningBriefSection.tsx, src/components/sections/macro/MorningBriefSection.tsx |
| macro | economic-calendar | src/components/sections/market/EventCalendarSection.tsx, src/components/ui/Badge.tsx, src/components/ui/Card.tsx, src/components/markets/DataViews.tsx, src/components/markets/shared.tsx, src/components/markets/shared.tsx |
| macro | master-signal | src/components/sections/signals/MasterSignalSection.tsx, src/components/ui/AnimatedValue.tsx |
| macro | key-metrics | src/components/sections/macro/KeyMetricsSection.tsx, src/components/ui/MetricCard.tsx, src/components/ui/AnomalyBadge.tsx, src/components/ui/DataLineagePopover.tsx, src/components/ui/DataLineagePopover.tsx, src/components/ui/Sparkline.tsx |
| macro | event-dataset | src/components/sections/macro/EventDatasetSection.tsx |
| macro | anomalies | src/components/sections/macro/AnomaliesStripSection.tsx, src/components/ui/AnomalyBadge.tsx, src/components/ui/DataLineagePopover.tsx, src/components/ui/DataLineagePopover.tsx |
| macro | regime | src/components/sections/macro/RegimeSection.tsx, src/components/ui/Skeleton.tsx, src/components/ui/Skeleton.tsx, src/components/ui/Skeleton.tsx, src/components/ui/ComputedTag.tsx, src/components/ui/SourceTag.tsx |
| macro | regime-playbook | src/components/sections/macro/RegimePlaybookSection.tsx, src/components/ui/Badge.tsx, src/components/ui/Card.tsx, src/components/ui/HeatGrid.tsx |
| macro | market-clock | src/components/sections/market/MarketClockSection.tsx |
| macro | global-markets | src/components/sections/market/GlobalMarketsSection.tsx, src/components/ui/DataLineagePopover.tsx, src/components/ui/DataLineagePopover.tsx, src/components/ui/Sparkline.tsx |
| macro | global-correlation | src/components/sections/market/GlobalCorrelationSection.tsx, src/components/ui/DataLineagePopover.tsx, src/components/ui/DataLineagePopover.tsx, src/components/ui/CorrelationHeatmap.tsx |
| macro | regional-macro | src/components/sections/macro/RegionalMacroSection.tsx, src/components/sections/macro/RegionalMacroSection.tsx, src/components/ui/BarList.tsx, src/components/sections/macro/RegionalMacroSection.tsx, src/components/sections/macro/RegionalMacroSection.tsx |
| macro | ensemble | src/components/sections/signals/EnsembleSection.tsx |
| macro | signal-stack | src/components/sections/signals/SignalStackSection.tsx, src/components/ui/Skeleton.tsx, src/components/ui/Skeleton.tsx, src/components/ui/ComputedTag.tsx, src/components/ui/SourceTag.tsx, src/components/ui/AnimatedValue.tsx |
| macro | signal-story | src/components/sections/signals/SignalStorySection.tsx, src/components/ui/DataLineagePopover.tsx, src/components/ui/DataLineagePopover.tsx |
| macro | signals | src/components/sections/signals/SignalsSection.tsx |
| macro | alt-data | src/components/sections/signals/AltDataSection.tsx |
| macro | stream-agreement | src/components/sections/signals/StreamAgreementSection.tsx, src/components/ui/DataLineagePopover.tsx, src/components/ui/DataLineagePopover.tsx, src/components/sections/signals/StreamAgreementSection.tsx |
| macro | sector-allocation | src/components/sections/equity/SectorAllocationSection.tsx, src/components/ui/BarList.tsx, src/components/ui/KpiStrip.tsx |
| macro | factor-rotation | src/components/sections/equity/FactorRotationSection.tsx |
| macro | cot-positioning | src/components/sections/risk/COTPositioningSection.tsx, src/components/ui/BarList.tsx |
| macro | cta-trend | src/components/sections/signals/CTATrendSection.tsx, src/components/ui/ComputedTag.tsx, src/components/ui/SourceTag.tsx, src/components/ui/HeatGrid.tsx |
| macro | news-sentiment | src/components/sections/signals/NewsSentimentSection.tsx |
| macro | valuation | src/components/sections/equity/ValuationSection.tsx, src/components/ui/ComputedTag.tsx, src/components/ui/SourceTag.tsx |
| macro | nowcast | src/components/sections/macro/NowcastSection.tsx, src/components/ui/ComputedTag.tsx, src/components/ui/SourceTag.tsx |
| macro | yield-curve | src/components/sections/rates/YieldCurveSection.tsx, src/components/ui/Card.tsx, src/components/sections/rates/YieldCurveSection.tsx |
| macro | liquidity | src/components/sections/macro/LiquiditySection.tsx, src/components/ui/ComputedTag.tsx, src/components/ui/SourceTag.tsx, src/components/ui/Donut.tsx |
| macro | sentiment | src/components/sections/signals/SentimentSection.tsx, src/components/ui/Card.tsx |
| macro | expected-returns | src/components/sections/equity/ExpectedReturnsSection.tsx, src/components/ui/BarList.tsx |
| macro | gmo-forecasts | src/components/sections/macro/GMOForecastsSection.tsx, src/components/ui/CsvButton.tsx, src/components/ui/ComputedTag.tsx, src/components/ui/SourceTag.tsx |
| macro | regime-transition | src/components/sections/macro/RegimeTransitionSection.tsx, src/components/sections/macro/RegimeTransitionSection.tsx, src/components/ui/HeatGrid.tsx |
| macro | regime-outlook | src/components/sections/macro/RegimeOutlookSection.tsx, src/components/ui/DataLineagePopover.tsx, src/components/ui/DataLineagePopover.tsx |
| macro | quadrants | src/components/sections/macro/QuadrantsSection.tsx, src/components/ui/DataLineagePopover.tsx, src/components/ui/DataLineagePopover.tsx |
| macro | event-vol | src/components/sections/market/EventVolSection.tsx, src/components/ui/DataLineagePopover.tsx, src/components/ui/DataLineagePopover.tsx, src/components/ui/BarList.tsx |
| macro | cycle-risk | src/components/sections/risk/CycleRiskSection.tsx, src/components/sections/risk/CycleRiskSection.tsx, src/components/sections/risk/CycleRiskSection.tsx |
| macro | risk-indicators | src/components/sections/risk/RiskIndicatorsSection.tsx, src/components/ui/Skeleton.tsx, src/components/ui/Skeleton.tsx, src/components/ui/Skeleton.tsx, src/components/ui/ComputedTag.tsx, src/components/ui/SourceTag.tsx, src/components/ui/AnimatedValue.tsx |
| macro | debt-cycle | src/components/sections/macro/DebtCycleSection.tsx, src/components/ui/ComputedTag.tsx, src/components/ui/SourceTag.tsx, src/components/markets/BridgewaterViews.tsx, src/components/markets/BridgewaterViews.tsx, src/components/markets/shared.tsx, src/components/markets/shared.tsx, src/components/markets/shared.tsx, src/components/markets/BridgewaterViews.tsx, src/components/ui/LineChart.tsx, src/components/ui/LineChart.tsx, src/components/markets/BridgewaterViews.tsx |
| macro | correlation | src/components/sections/risk/CorrelationRegimeSection.tsx, src/components/ui/ComputedTag.tsx, src/components/ui/SourceTag.tsx, src/components/ui/BarList.tsx |
| macro | correlation-matrix | src/components/sections/risk/CorrelationMatrixSection.tsx, src/components/ui/DataLineagePopover.tsx, src/components/ui/DataLineagePopover.tsx, src/components/ui/CorrelationHeatmap.tsx |
| macro | advanced | src/components/sections/macro/AdvancedIndicatorsSection.tsx, src/components/ui/ComputedTag.tsx, src/components/ui/SourceTag.tsx |
| macro | fx-monitor | src/components/sections/rates/FXMonitorSection.tsx, src/components/ui/Card.tsx, src/components/ui/CsvButton.tsx, src/components/ui/SourceTag.tsx, src/components/ui/Table.tsx |
| macro | commodities-dashboard | src/components/sections/rates/CommoditiesDashboardSection.tsx, src/components/ui/Card.tsx, src/components/ui/LoadingState.tsx, src/components/ui/ErrorState.tsx, src/components/ui/CsvButton.tsx, src/components/ui/SourceTag.tsx, src/components/ui/Badge.tsx |
| macro | fixed-income-dashboard | src/components/sections/rates/FixedIncomeDashboardSection.tsx, src/components/ui/Badge.tsx, src/components/ui/Card.tsx, src/components/ui/SourceTag.tsx, src/components/ui/Table.tsx |
| macro | international | src/components/sections/macro/InternationalMacroSection.tsx, src/components/ui/ComputedTag.tsx, src/components/ui/SourceTag.tsx |
| macro | reflexivity | src/components/sections/signals/ReflexivitySection.tsx, src/components/sections/signals/ReflexivitySection.tsx |
| macro | transmission | src/components/sections/macro/TransmissionSection.tsx |
| trading | trade-ideas | src/components/sections/equity/TradeIdeasSection.tsx, src/components/ui/Badge.tsx, src/components/ui/Card.tsx |
| trading | trade-recommendations | src/components/sections/equity/TradeRecommendationsSection.tsx, src/components/ui/Card.tsx, src/components/ui/Badge.tsx, src/components/ui/Card.tsx, src/components/ui/Card.tsx, src/components/ui/Card.tsx |
| trading | stock-ideas | src/components/sections/equity/StockIdeasSection.tsx, src/components/sections/equity/StockIdeasSection.tsx, src/components/sections/equity/StockIdeasSection.tsx |
| trading | stock-timing | src/components/sections/equity/StockTimingSection.tsx, src/components/sections/equity/StockTimingSection.tsx, src/components/ui/PriceChart.tsx, src/components/ui/PriceChart.tsx |
| trading | pretrade-desk | src/components/sections/equity/PreTradeDeskSection.tsx, src/components/sections/equity/PreTradeDeskSection.tsx, src/components/sections/equity/PreTradeDeskSection.tsx |
| trading | pitch-review | src/components/sections/equity/PitchReviewSection.tsx |
| trading | trade-workflow | src/components/sections/equity/TradeWorkflowSection.tsx |
| trading | trade-lifecycle | src/components/sections/equity/TradeLifecycleSection.tsx, src/components/sections/equity/TradeLifecycleSection.tsx, src/components/sections/equity/TradeLifecycleSection.tsx, src/components/sections/equity/TradeLifecycleSection.tsx |
| trading | scenario-analysis | src/components/sections/risk/ScenarioAnalysisSection.tsx, src/components/ui/Badge.tsx, src/components/ui/RangePlot.tsx, src/components/ui/Donut.tsx, src/components/ui/Card.tsx |
| trading | momentum-veto | src/components/sections/signals/MomentumVetoSection.tsx, src/components/ui/BarList.tsx |
| trading | portfolio-positions | src/components/sections/equity/PositionsSection.tsx, src/components/ui/KpiStrip.tsx, src/components/ui/Donut.tsx, src/components/ui/BarList.tsx, src/components/sections/equity/PositionsSection.tsx |
| trading | portfolios | src/components/sections/equity/PortfoliosSection.tsx, src/components/sections/equity/PortfoliosSection.tsx, src/components/sections/equity/PortfoliosSection.tsx, src/components/ui/Donut.tsx, src/components/sections/equity/QuantTrader.tsx, src/components/sections/model/quant/shared.tsx, src/components/sections/equity/QuantTrader.tsx, src/components/sections/model/quant/shared.tsx, src/components/ui/KpiStrip.tsx, src/components/sections/equity/LivePerformance.tsx, src/components/ui/LineChart.tsx, src/components/ui/LineChart.tsx, src/components/sections/equity/QuantTrader.tsx, src/components/sections/model/quant/DeepReport.tsx, src/components/sections/model/quant/DeepReport.tsx, src/components/sections/model/quant/DeepReport.tsx, src/components/sections/model/quant/DeepReport.tsx, src/components/sections/equity/MacroTrader.tsx, src/components/sections/equity/MacroTrader.tsx, src/components/sections/equity/MacroTrader.tsx, src/components/sections/model/quant/shared.tsx, src/components/sections/equity/MacroTrader.tsx, src/components/sections/equity/QuantTrader.tsx, src/components/sections/equity/QuantTrader.tsx, src/components/sections/equity/PortfoliosSection.tsx, src/components/sections/equity/PortfoliosSection.tsx, src/components/sections/equity/PortfoliosSection.tsx, src/components/sections/equity/PortfoliosSection.tsx |
| trading | portfolio | src/components/sections/model/ModelSleeveSection.tsx, src/components/ui/Donut.tsx, src/components/ui/BarList.tsx |
| trading | position-manager | src/components/sections/equity/PositionManagerSection.tsx, src/components/sections/equity/PositionManagerSection.tsx, src/components/sections/equity/PositionManagerSection.tsx, src/components/sections/equity/PositionManagerSection.tsx, src/components/sections/equity/PositionManagerSection.tsx, src/components/sections/equity/PositionManagerSection.tsx, src/components/sections/equity/PositionManagerSection.tsx |
| trading | performance-attribution | src/components/sections/equity/PerformanceAttributionSection.tsx, src/components/sections/equity/PortfolioAnalyticsSection.tsx, src/components/sections/equity/PortfolioAnalyticsSection.tsx, src/components/sections/equity/PortfolioAnalyticsSection.tsx, src/components/sections/equity/PortfolioAnalyticsSection.tsx, src/components/sections/equity/PortfolioAnalyticsSection.tsx, src/components/sections/equity/PortfolioAnalyticsSection.tsx, src/components/sections/equity/PortfolioAnalyticsSection.tsx, src/components/sections/equity/PortfolioAnalyticsSection.tsx, src/components/sections/equity/PortfolioAnalyticsSection.tsx |
| trading | equity-research | src/components/sections/equity/EquityResearchSection.tsx, src/components/ui/Card.tsx, src/components/ui/Badge.tsx, src/components/ui/Card.tsx, src/components/ui/Card.tsx, src/components/ui/Card.tsx |
| trading | business-layer | src/components/sections/business/BusinessLayerSection.tsx, src/components/ui/LoadingState.tsx |
| trading | fund-cockpit | src/components/sections/risk/FundCockpitSection.tsx, src/components/sections/risk/FundCockpitSection.tsx, src/components/sections/risk/FundCockpitSection.tsx, src/components/ui/LineChart.tsx, src/components/ui/LineChart.tsx, src/components/ui/BarList.tsx, src/components/sections/risk/FundCockpitSection.tsx, src/components/sections/risk/FundCockpitSection.tsx, src/components/sections/risk/FundCockpitSection.tsx, src/components/sections/risk/FundCockpitSection.tsx |
| trading | risk-analytics | src/components/sections/risk/RiskAnalyticsSection.tsx, src/components/ui/Card.tsx, src/components/ui/FormattedNumber.tsx, src/components/ui/FormattedNumber.tsx, src/components/ui/FormattedNumber.tsx, src/components/ui/Badge.tsx, src/components/ui/FormattedNumber.tsx, src/components/ui/CorrelationHeatmap.tsx |
| trading | var-stress | src/components/sections/risk/VaRStressSection.tsx, src/components/ui/BarList.tsx |
| trading | what-if | src/components/sections/risk/WhatIfSection.tsx, src/components/sections/risk/WhatIfSection.tsx |
| trading | factor-exposure | src/components/sections/risk/FactorExposureSection.tsx |
| trading | horizon-tension | src/components/sections/signals/HorizonTensionSection.tsx |
| trading | risk-parity | src/components/sections/risk/RiskParitySection.tsx, src/components/ui/Donut.tsx, src/components/ui/BarList.tsx, src/components/markets/BridgewaterViews.tsx, src/components/markets/BridgewaterViews.tsx, src/components/markets/shared.tsx, src/components/markets/shared.tsx, src/components/markets/shared.tsx, src/components/markets/BridgewaterViews.tsx, src/components/ui/LineChart.tsx, src/components/ui/LineChart.tsx, src/components/markets/BridgewaterViews.tsx |
| trading | risk-parity-compare | src/components/sections/risk/RiskParityCompareSection.tsx, src/components/ui/DataLineagePopover.tsx, src/components/ui/DataLineagePopover.tsx, src/components/ui/BarList.tsx |
| trading | fund-governance | src/components/sections/equity/GovernanceSection.tsx, src/components/sections/equity/GovernanceSection.tsx, src/components/layout/FundIdentity.tsx, src/components/sections/equity/GovernanceSection.tsx, src/components/sections/equity/GovernanceSection.tsx, src/components/sections/equity/GovernanceSection.tsx, src/components/sections/equity/GovernanceSection.tsx, src/components/sections/equity/TeamPositions.tsx, src/components/sections/equity/TeamPositions.tsx, src/components/sections/equity/BrokerLink.tsx, src/components/sections/equity/GovernanceSection.tsx, src/components/sections/equity/GovernanceSection.tsx, src/components/sections/equity/GovernanceSection.tsx, src/components/sections/equity/GovernanceSection.tsx, src/components/sections/equity/GovernanceSection.tsx, src/components/layout/FundIdentity.tsx, src/components/sections/equity/GovernanceSection.tsx, src/components/sections/equity/GovernanceSection.tsx, src/components/sections/equity/GovernanceSection.tsx, src/components/sections/equity/GovernanceSection.tsx |
| trading | system-audit | src/components/sections/macro/SystemAuditSection.tsx |
| trading | investment-memo | src/components/sections/macro/InvestmentMemoSection.tsx |
| quant | quant-lab | src/components/sections/model/QuantLabSection.tsx, src/components/sections/model/quant/CodeLab.tsx, src/components/sections/model/quant/shared.tsx, src/components/sections/model/quant/CodeLab.tsx, src/components/sections/model/quant/CodeLab.tsx, src/components/sections/model/quant/CodeLab.tsx, src/components/ui/LineChart.tsx, src/components/ui/LineChart.tsx, src/components/sections/model/quant/LeanOptimizer.tsx, src/components/sections/model/quant/shared.tsx, src/components/sections/model/quant/CodeLab.tsx, src/components/sections/model/quant/CodeLab.tsx, src/components/sections/model/quant/CodeLab.tsx, src/components/sections/model/quant/CodeLab.tsx, src/components/ui/KpiStrip.tsx, src/components/sections/model/quant/CodeLab.tsx, src/components/ui/BarList.tsx, src/components/sections/model/quant/CodeLab.tsx, src/components/sections/model/quant/ResearchPanels.tsx, src/components/sections/model/quant/ResearchPanels.tsx, src/components/sections/model/quant/CodeLab.tsx, src/components/sections/model/quant/ResearchPanels.tsx, src/components/sections/model/quant/CodeLab.tsx, src/components/sections/model/quant/ResearchPanels.tsx, src/components/sections/model/quant/ResearchPanels.tsx, src/components/sections/model/quant/CodeLab.tsx, src/components/sections/model/quant/CodeLab.tsx, src/components/sections/model/quant/ResearchPanels.tsx, src/components/sections/model/quant/ResearchPanels.tsx, src/components/sections/model/quant/ResearchPanels.tsx, src/components/sections/model/quant/ResearchPanels.tsx, src/components/sections/model/quant/DeepReport.tsx, src/components/sections/model/quant/shared.tsx, src/components/sections/model/quant/DeepReport.tsx, src/components/sections/model/quant/DeepReport.tsx, src/components/sections/model/quant/Runs.tsx, src/components/sections/model/quant/Runs.tsx, src/components/sections/model/quant/Library.tsx, src/components/sections/model/quant/Library.tsx, src/components/sections/model/QuantLabSection.tsx, src/components/sections/model/quant/RelValue.tsx, src/components/sections/model/quant/RelValue.tsx, src/components/sections/model/quant/RelValue.tsx, src/components/sections/model/quant/RelValue.tsx, src/components/sections/model/quant/RelValue.tsx, src/components/sections/model/QuantLabSection.tsx, src/components/sections/model/quant/OptionsResearch.tsx, src/components/sections/model/quant/OptionsResearch.tsx, src/components/sections/model/quant/OptionsResearch.tsx, src/components/sections/model/quant/OptionsResearch.tsx, src/components/sections/model/quant/OptionsResearch.tsx, src/components/sections/model/quant/OptionsResearch.tsx, src/components/sections/model/quant/OptionsResearch.tsx, src/components/sections/model/quant/OptionsResearch.tsx, src/components/sections/model/quant/OptionsResearch.tsx, src/components/sections/model/quant/OptionsResearch.tsx, src/components/sections/model/quant/OptionsResearch.tsx, src/components/sections/model/quant/OptionsResearch.tsx, src/components/sections/model/quant/OptionsResearch.tsx, src/components/sections/model/quant/OptionsResearch.tsx, src/components/sections/model/quant/OptionsResearch.tsx |
| quant | strategy-lab | src/components/sections/model/StrategyLabSection.tsx, src/components/ui/LineChart.tsx, src/components/ui/LineChart.tsx, src/components/ui/Donut.tsx, src/components/ui/CorrelationHeatmap.tsx |
| quant | stock-backtest | src/components/sections/equity/StockBacktestSection.tsx, src/components/ui/LineChart.tsx, src/components/ui/LineChart.tsx, src/components/sections/model/quant/DeepReport.tsx, src/components/sections/model/quant/shared.tsx, src/components/sections/model/quant/DeepReport.tsx, src/components/sections/model/quant/shared.tsx, src/components/sections/model/quant/DeepReport.tsx, src/components/sections/model/quant/DeepReport.tsx |
| quant | signal-scorecard | src/components/sections/signals/SignalScorecardSection.tsx, src/components/ui/BarList.tsx |
| quant | factor-validation | src/components/sections/signals/FactorValidationSection.tsx, src/components/ui/DataLineagePopover.tsx, src/components/ui/DataLineagePopover.tsx |
| quant | model-agreement | src/components/sections/macro/ModelAgreementSection.tsx, src/components/ui/ComputedTag.tsx, src/components/ui/SourceTag.tsx, src/components/sections/macro/ModelAgreementSection.tsx, src/components/ui/LineChart.tsx, src/components/ui/LineChart.tsx |
| quant | factor-decomposition | src/components/sections/signals/FactorDecompositionSection.tsx, src/components/ui/CsvButton.tsx, src/components/ui/ComputedTag.tsx, src/components/ui/SourceTag.tsx, src/components/ui/RangePlot.tsx |
| quant | data-explorer | src/components/sections/macro/DataExplorerSection.tsx, src/components/sections/macro/DataExplorerSection.tsx, src/components/sections/macro/DataExplorerSection.tsx, src/components/sections/macro/DataExplorerSection.tsx |
| quant | data-providers | src/components/sections/macro/DataProvidersSection.tsx |
| quant | system-health | src/components/sections/macro/SystemHealthSection.tsx |
| pe | workbench | src/components/pe/Workbench.tsx, src/components/pe/peShared.tsx, src/components/pe/peShared.tsx, src/components/pe/peShared.tsx, src/components/pe/DealDevelopment.tsx, src/components/pe/Workbench.tsx, src/components/pe/DealDevelopment.tsx, src/components/pe/peShared.tsx |
| pe | pipeline | src/components/pe/Pipeline.tsx |
| pe | waterfall | src/components/pe/FundTools.tsx, src/components/pe/peShared.tsx, src/components/pe/FundTools.tsx, src/components/pe/peShared.tsx, src/components/pe/peShared.tsx |
| pe | performance | src/components/pe/FundTools.tsx, src/components/pe/peShared.tsx, src/components/pe/FundTools.tsx, src/components/pe/peShared.tsx, src/components/pe/peShared.tsx |

## Final checks

- Full frontend suite: 401 tests passed across 36 files.
- TypeScript: `npx tsc --noEmit` passed.
- Production Vite build passed; chunk-size warnings remain.
- `git diff --check` passed.
- Temporary visual harness removed.
