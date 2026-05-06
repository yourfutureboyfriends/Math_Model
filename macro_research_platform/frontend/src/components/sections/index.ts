// Section component barrel — Phase 5A Code Splitting
// Critical sections load eagerly, rest are lazy-loaded
// Import sections from this file; never import a section file directly.

import { lazy } from 'react';

// ── Critical Sections (Eager Load) ──────────────────────────────────────────
// These sections are above the fold and load immediately
export { MorningBriefSection } from './MorningBriefSection';
export { MasterSignalSection } from './MasterSignalSection';
export { KeyMetricsSection } from './KeyMetricsSection';
export { RegimeSection } from './RegimeSection';
export { RegimePlaybookSection } from './RegimePlaybookSection';
export { MarketClockSection } from './MarketClockSection';

// ── Lazy Loaded Sections ────────────────────────────────────────────────────
// These sections are loaded on-demand to reduce initial bundle size

export const SignalStackSection = lazy(() =>
  import('./SignalStackSection').then(m => ({ default: m.SignalStackSection }))
);

export const SectorAllocationSection = lazy(() =>
  import('./SectorAllocationSection').then(m => ({ default: m.SectorAllocationSection }))
);

export const FactorRotationSection = lazy(() =>
  import('./FactorRotationSection').then(m => ({ default: m.FactorRotationSection }))
);

export const RiskIndicatorsSection = lazy(() =>
  import('./RiskIndicatorsSection').then(m => ({ default: m.RiskIndicatorsSection }))
);

export const NowcastSection = lazy(() =>
  import('./NowcastSection').then(m => ({ default: m.NowcastSection }))
);

export const LiquiditySection = lazy(() =>
  import('./LiquiditySection').then(m => ({ default: m.LiquiditySection }))
);

export const SentimentSection = lazy(() =>
  import('./SentimentSection').then(m => ({ default: m.SentimentSection }))
);

export const DebtCycleSection = lazy(() =>
  import('./DebtCycleSection').then(m => ({ default: m.DebtCycleSection }))
);

export const AdvancedIndicatorsSection = lazy(() =>
  import('./AdvancedIndicatorsSection').then(m => ({ default: m.AdvancedIndicatorsSection }))
);

export const GMOForecastsSection = lazy(() =>
  import('./GMOForecastsSection').then(m => ({ default: m.GMOForecastsSection }))
);

export const ReflexivitySection = lazy(() =>
  import('./ReflexivitySection').then(m => ({ default: m.ReflexivitySection }))
);

export const FactorDecompositionSection = lazy(() =>
  import('./FactorDecompositionSection').then(m => ({ default: m.FactorDecompositionSection }))
);

export const HorizonTensionSection = lazy(() =>
  import('./HorizonTensionSection').then(m => ({ default: m.HorizonTensionSection }))
);

export const PortfolioAnalyserSection = lazy(() =>
  import('./PortfolioAnalyserSection').then(m => ({ default: m.PortfolioAnalyserSection }))
);

export const CTATrendSection = lazy(() =>
  import('./CTATrendSection').then(m => ({ default: m.CTATrendSection }))
);

export const BusinessLayerSection = lazy(() =>
  import('./BusinessLayerSection').then(m => ({ default: m.BusinessLayerSection }))
);

export const EnsembleSection = lazy(() =>
  import('./EnsembleSection').then(m => ({ default: m.EnsembleSection }))
);

export const PerformanceAttributionSection = lazy(() =>
  import('./PerformanceAttributionSection').then(m => ({ default: m.PerformanceAttributionSection }))
);

export const SystemHealthSection = lazy(() =>
  import('./SystemHealthSection').then(m => ({ default: m.SystemHealthSection }))
);

export const DataExplorerSection = lazy(() =>
  import('./DataExplorerSection').then(m => ({ default: m.DataExplorerSection }))
);

export const DataToWatchSection = lazy(() =>
  import('./DataToWatchSection').then(m => ({ default: m.DataToWatchSection }))
);

export const InvestmentMemoSection = lazy(() =>
  import('./InvestmentMemoSection').then(m => ({ default: m.InvestmentMemoSection }))
);

export const TransmissionSection = lazy(() =>
  import('./TransmissionSection').then(m => ({ default: m.TransmissionSection }))
);

export const ModelAgreementSection = lazy(() =>
  import('./ModelAgreementSection').then(m => ({ default: m.ModelAgreementSection }))
);

export const ExpectedReturnsSection = lazy(() =>
  import('./ExpectedReturnsSection').then(m => ({ default: m.ExpectedReturnsSection }))
);

export const PureAlphaSection = lazy(() =>
  import('./PureAlphaSection').then(m => ({ default: m.PureAlphaSection }))
);

export const InternationalMacroSection = lazy(() =>
  import('./InternationalMacroSection').then(m => ({ default: m.InternationalMacroSection }))
);

export const RegimeTransitionSection = lazy(() =>
  import('./RegimeTransitionSection').then(m => ({ default: m.RegimeTransitionSection }))
);

export const RiskParitySection = lazy(() =>
  import('./RiskParitySection').then(m => ({ default: m.RiskParitySection }))
);

export const CorrelationRegimeSection = lazy(() =>
  import('./CorrelationRegimeSection').then(m => ({ default: m.CorrelationRegimeSection }))
);

export const MomentumVetoSection = lazy(() =>
  import('./MomentumVetoSection').then(m => ({ default: m.MomentumVetoSection }))
);

export const ValuationSection = lazy(() =>
  import('./ValuationSection').then(m => ({ default: m.ValuationSection }))
);

export const NewsSentimentSection = lazy(() =>
  import('./NewsSentimentSection').then(m => ({ default: m.NewsSentimentSection }))
);

export const SignalsSection = lazy(() =>
  import('./SignalsSection').then(m => ({ default: m.SignalsSection }))
);

export const EquityResearchSection = lazy(() =>
  import('./EquityResearchSection').then(m => ({ default: m.EquityResearchSection }))
);

export const COTPositioningSection = lazy(() =>
  import('./COTPositioningSection').then(m => ({ default: m.COTPositioningSection }))
);

export const RiskAnalyticsSection = lazy(() =>
  import('./RiskAnalyticsSection').then(m => ({ default: m.RiskAnalyticsSection }))
);

export const EventCalendarSection = lazy(() =>
  import('./EventCalendarSection').then(m => ({ default: m.EventCalendarSection }))
);

export const TradeIdeasSection = lazy(() =>
  import('./TradeIdeasSection').then(m => ({ default: m.TradeIdeasSection }))
);

export const ScenarioAnalysisSection = lazy(() =>
  import('./ScenarioAnalysisSection').then(m => ({ default: m.ScenarioAnalysisSection }))
);

export const YieldCurveSection = lazy(() =>
  import('./YieldCurveSection').then(m => ({ default: m.YieldCurveSection }))
);

export const FXMonitorSection = lazy(() =>
  import('./FXMonitorSection').then(m => ({ default: m.FXMonitorSection }))
);

export const CommoditiesDashboardSection = lazy(() =>
  import('./CommoditiesDashboardSection').then(m => ({ default: m.CommoditiesDashboardSection }))
);

export const FixedIncomeDashboardSection = lazy(() =>
  import('./FixedIncomeDashboardSection').then(m => ({ default: m.FixedIncomeDashboardSection }))
);

export const TradeRecommendationsSection = lazy(() =>
  import('./TradeRecommendationsSection').then(m => ({ default: m.TradeRecommendationsSection }))
);

// ── Additional Sections (Not in main nav but available) ─────────────────────
export const AnomalyDetectionSection = lazy(() =>
  import('./AnomalyDetectionSection').then(m => ({ default: m.AnomalyDetectionSection }))
);

export const CentralBankDivergenceSection = lazy(() =>
  import('./CentralBankDivergenceSection').then(m => ({ default: m.CentralBankDivergenceSection }))
);

export const LSTMSection = lazy(() =>
  import('./LSTMSection').then(m => ({ default: m.LSTMSection }))
);

export const PerformanceTrackingSection = lazy(() =>
  import('./PerformanceTrackingSection').then(m => ({ default: m.PerformanceTrackingSection }))
);

export const PortfolioFitSection = lazy(() =>
  import('./PortfolioFitSection').then(m => ({ default: m.PortfolioFitSection }))
);

export const PositioningSection = lazy(() =>
  import('./PositioningSection').then(m => ({ default: m.PositioningSection }))
);
