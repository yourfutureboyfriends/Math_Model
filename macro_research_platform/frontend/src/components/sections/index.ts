// Section component barrel — Phase 4 Domain Organization + Phase 5A Code Splitting
// Components organized by domain: macro, equity, rates, risk, signals, market, business
// Critical sections load eagerly, rest are lazy-loaded
// Import sections from this file; never import a section file directly.

import { lazy } from 'react';

// ── Domain Re-exports ─────────────────────────────────────────────────────────
// Import from specific domains for tree-shaking benefits
// Example: import { RegimeSection } from '@/components/sections/macro'

export * from './macro';
export * from './equity';
export * from './rates';
export * from './risk';
export * from './signals';
export * from './market';
export * from './business';

// ── Critical Sections (Eager Load) ───────────────────────────────────────────
// These sections are above the fold and load immediately
export { MorningBriefSection } from './macro/MorningBriefSection';
export { MasterSignalSection } from './signals/MasterSignalSection';
export { KeyMetricsSection } from './macro/KeyMetricsSection';
export { RegimeSection } from './macro/RegimeSection';
export { RegimePlaybookSection } from './macro/RegimePlaybookSection';
export { MarketClockSection } from './market/MarketClockSection';

// ── Lazy Loaded Sections ─────────────────────────────────────────────────────
// These sections are loaded on-demand to reduce initial bundle size
// Organized by domain for clarity

// Macro Domain
export const SignalScorecardSection = lazy(() =>
  import('./signals/SignalScorecardSection').then(m => ({ default: m.SignalScorecardSection }))
);

export const SignalStackSection = lazy(() =>
  import('./signals/SignalStackSection').then(m => ({ default: m.SignalStackSection }))
);

export const NowcastSection = lazy(() =>
  import('./macro/NowcastSection').then(m => ({ default: m.NowcastSection }))
);

export const LiquiditySection = lazy(() =>
  import('./macro/LiquiditySection').then(m => ({ default: m.LiquiditySection }))
);

export const DebtCycleSection = lazy(() =>
  import('./macro/DebtCycleSection').then(m => ({ default: m.DebtCycleSection }))
);

export const AdvancedIndicatorsSection = lazy(() =>
  import('./macro/AdvancedIndicatorsSection').then(m => ({ default: m.AdvancedIndicatorsSection }))
);

export const GMOForecastsSection = lazy(() =>
  import('./macro/GMOForecastsSection').then(m => ({ default: m.GMOForecastsSection }))
);

export const InternationalMacroSection = lazy(() =>
  import('./macro/InternationalMacroSection').then(m => ({ default: m.InternationalMacroSection }))
);

export const RegimeTransitionSection = lazy(() =>
  import('./macro/RegimeTransitionSection').then(m => ({ default: m.RegimeTransitionSection }))
);

export const SystemHealthSection = lazy(() =>
  import('./macro/SystemHealthSection').then(m => ({ default: m.SystemHealthSection }))
);

export const DataExplorerSection = lazy(() =>
  import('./macro/DataExplorerSection').then(m => ({ default: m.DataExplorerSection }))
);

export const DataToWatchSection = lazy(() =>
  import('./macro/DataToWatchSection').then(m => ({ default: m.DataToWatchSection }))
);

export const InvestmentMemoSection = lazy(() =>
  import('./macro/InvestmentMemoSection').then(m => ({ default: m.InvestmentMemoSection }))
);

export const TransmissionSection = lazy(() =>
  import('./macro/TransmissionSection').then(m => ({ default: m.TransmissionSection }))
);

export const ModelAgreementSection = lazy(() =>
  import('./macro/ModelAgreementSection').then(m => ({ default: m.ModelAgreementSection }))
);

// Equity Domain
export const SectorAllocationSection = lazy(() =>
  import('./equity/SectorAllocationSection').then(m => ({ default: m.SectorAllocationSection }))
);

export const FactorRotationSection = lazy(() =>
  import('./equity/FactorRotationSection').then(m => ({ default: m.FactorRotationSection }))
);

export const ExpectedReturnsSection = lazy(() =>
  import('./equity/ExpectedReturnsSection').then(m => ({ default: m.ExpectedReturnsSection }))
);

export const PureAlphaSection = lazy(() =>
  import('./equity/PureAlphaSection').then(m => ({ default: m.PureAlphaSection }))
);

export const PerformanceAttributionSection = lazy(() =>
  import('./equity/PerformanceAttributionSection').then(m => ({ default: m.PerformanceAttributionSection }))
);

export const EquityResearchSection = lazy(() =>
  import('./equity/EquityResearchSection').then(m => ({ default: m.EquityResearchSection }))
);

export const TradeIdeasSection = lazy(() =>
  import('./equity/TradeIdeasSection').then(m => ({ default: m.TradeIdeasSection }))
);

export const TradeRecommendationsSection = lazy(() =>
  import('./equity/TradeRecommendationsSection').then(m => ({ default: m.TradeRecommendationsSection }))
);

export const ValuationSection = lazy(() =>
  import('./equity/ValuationSection').then(m => ({ default: m.ValuationSection }))
);

export const PortfolioAnalyserSection = lazy(() =>
  import('./equity/PortfolioAnalyserSection').then(m => ({ default: m.PortfolioAnalyserSection }))
);

export const PositionsSection = lazy(() =>
  import('./equity/PositionsSection').then(m => ({ default: m.PositionsSection }))
);

export const TradeWorkflowSection = lazy(() =>
  import('./equity/TradeWorkflowSection').then(m => ({ default: m.TradeWorkflowSection }))
);

export const PortfolioFitSection = lazy(() =>
  import('./equity/PortfolioFitSection').then(m => ({ default: m.PortfolioFitSection }))
);

// Rates Domain
export const YieldCurveSection = lazy(() =>
  import('./rates/YieldCurveSection').then(m => ({ default: m.YieldCurveSection }))
);

export const FixedIncomeDashboardSection = lazy(() =>
  import('./rates/FixedIncomeDashboardSection').then(m => ({ default: m.FixedIncomeDashboardSection }))
);

export const CommoditiesDashboardSection = lazy(() =>
  import('./rates/CommoditiesDashboardSection').then(m => ({ default: m.CommoditiesDashboardSection }))
);

export const CentralBankDivergenceSection = lazy(() =>
  import('./rates/CentralBankDivergenceSection').then(m => ({ default: m.CentralBankDivergenceSection }))
);

export const FXMonitorSection = lazy(() =>
  import('./rates/FXMonitorSection').then(m => ({ default: m.FXMonitorSection }))
);

// Risk Domain
export const RiskIndicatorsSection = lazy(() =>
  import('./risk/RiskIndicatorsSection').then(m => ({ default: m.RiskIndicatorsSection }))
);

export const RiskParitySection = lazy(() =>
  import('./risk/RiskParitySection').then(m => ({ default: m.RiskParitySection }))
);

export const CorrelationRegimeSection = lazy(() =>
  import('./risk/CorrelationRegimeSection').then(m => ({ default: m.CorrelationRegimeSection }))
);

export const FactorExposureSection = lazy(() =>
  import('./risk/FactorExposureSection').then(m => ({ default: m.FactorExposureSection }))
);

export const VaRStressSection = lazy(() =>
  import('./risk/VaRStressSection').then(m => ({ default: m.VaRStressSection }))
);

export const COTPositioningSection = lazy(() =>
  import('./risk/COTPositioningSection').then(m => ({ default: m.COTPositioningSection }))
);

export const RiskAnalyticsSection = lazy(() =>
  import('./risk/RiskAnalyticsSection').then(m => ({ default: m.RiskAnalyticsSection }))
);

export const ScenarioAnalysisSection = lazy(() =>
  import('./risk/ScenarioAnalysisSection').then(m => ({ default: m.ScenarioAnalysisSection }))
);

export const AnomalyDetectionSection = lazy(() =>
  import('./risk/AnomalyDetectionSection').then(m => ({ default: m.AnomalyDetectionSection }))
);

export const LSTMSection = lazy(() =>
  import('./risk/LSTMSection').then(m => ({ default: m.LSTMSection }))
);

export const PositioningSection = lazy(() =>
  import('./risk/PositioningSection').then(m => ({ default: m.PositioningSection }))
);

// Signals Domain
export const SentimentSection = lazy(() =>
  import('./signals/SentimentSection').then(m => ({ default: m.SentimentSection }))
);

export const ReflexivitySection = lazy(() =>
  import('./signals/ReflexivitySection').then(m => ({ default: m.ReflexivitySection }))
);

export const FactorDecompositionSection = lazy(() =>
  import('./signals/FactorDecompositionSection').then(m => ({ default: m.FactorDecompositionSection }))
);

export const HorizonTensionSection = lazy(() =>
  import('./signals/HorizonTensionSection').then(m => ({ default: m.HorizonTensionSection }))
);

export const BusinessLayerSection = lazy(() =>
  import('./business/BusinessLayerSection').then(m => ({ default: m.BusinessLayerSection }))
);

export const EnsembleSection = lazy(() =>
  import('./signals/EnsembleSection').then(m => ({ default: m.EnsembleSection }))
);

export const CTATrendSection = lazy(() =>
  import('./signals/CTATrendSection').then(m => ({ default: m.CTATrendSection }))
);

export const MomentumVetoSection = lazy(() =>
  import('./signals/MomentumVetoSection').then(m => ({ default: m.MomentumVetoSection }))
);

export const NewsSentimentSection = lazy(() =>
  import('./signals/NewsSentimentSection').then(m => ({ default: m.NewsSentimentSection }))
);

export const SignalsSection = lazy(() =>
  import('./signals/SignalsSection').then(m => ({ default: m.SignalsSection }))
);

export const PerformanceTrackingSection = lazy(() =>
  import('./signals/PerformanceTrackingSection').then(m => ({ default: m.PerformanceTrackingSection }))
);

// Market Domain
export const EventCalendarSection = lazy(() =>
  import('./market/EventCalendarSection').then(m => ({ default: m.EventCalendarSection }))
);

// Utility Components
export { MemoizedSection } from './MemoizedSection';
