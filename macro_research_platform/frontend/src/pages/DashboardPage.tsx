// Dashboard Page — Main terminal dashboard with all sections
// Uses REAL data from macroStore (fetched from backend API)

import { Suspense } from 'react';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { SectionSkeleton } from '@/components/ui/SectionSkeleton';
import { useMacroStore } from '@/store/macroStore';
import {
  MorningBriefSection,
  AnomaliesStripSection,
  MasterSignalSection,
  KeyMetricsSection,
  RegimeSection,
  RegimePlaybookSection,
  SignalStackSection,
  SignalScorecardSection,
  AltDataSection,
  SectorAllocationSection,
  FactorRotationSection,
  RiskIndicatorsSection,
  FactorExposureSection,
  VaRStressSection,
  NowcastSection,
  LiquiditySection,
  SentimentSection,
  DebtCycleSection,
  AdvancedIndicatorsSection,
  GMOForecastsSection,
  ReflexivitySection,
  FactorDecompositionSection,
  HorizonTensionSection,
  PortfolioAnalyserSection,
  PositionsSection,
  TradeWorkflowSection,
  CTATrendSection,
  BusinessLayerSection,
  EnsembleSection,
  SignalStorySection,
  PerformanceAttributionSection,
  SystemHealthSection,
  DataProvidersSection,
  SystemAuditSection,
  DataExplorerSection,
  DataToWatchSection,
  InvestmentMemoSection,
  ModelAgreementSection,
  ExpectedReturnsSection,
  InternationalMacroSection,
  RegimeTransitionSection,
  RegimeOutlookSection,
  MomentumVetoSection,
  ValuationSection,
  NewsSentimentSection,
  SignalsSection,
  TransmissionSection,
  CorrelationRegimeSection,
  CorrelationMatrixSection,
  RiskParitySection,
  EquityResearchSection,
  RiskAnalyticsSection,
  EventCalendarSection,
  EventVolSection,
  TradeIdeasSection,
  ScenarioAnalysisSection,
  YieldCurveSection,
  FXMonitorSection,
  CommoditiesDashboardSection,
  FixedIncomeDashboardSection,
  MarketClockSection,
  TradeRecommendationsSection,
} from '@/components/sections';

export function DashboardPage() {
  // P3: subscribe to ONLY the fields this component reads, so the whole 50-section tree
  // doesn't re-render on every WebSocket price tick (was `useMacroStore((s) => s)`).
  const dataStatus = useMacroStore((s) => s.meta.dataStatus);
  const wsError = useMacroStore((s) => s.wsError);
  const fetchDashboard = useMacroStore((s) => s.fetchDashboard);
  const isLoading = dataStatus === 'loading';
  const isError = dataStatus === 'error';

  if (isLoading) {
    return (
      <div className="space-y-4 p-4">
        <SectionSkeleton />
        <SectionSkeleton />
        <SectionSkeleton />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex items-center justify-center p-12">
        <div className="text-center space-y-2">
          <p className="text-text-primary font-mono text-sm">Data unavailable — service did not respond in time</p>
          <p className="text-text-tertiary font-mono text-xs">{wsError || 'Backend unreachable'}</p>
          <button
            onClick={() => fetchDashboard()}
            className="mt-4 px-4 py-2 text-xs font-mono border border-border text-text-secondary hover:text-text-primary hover:border-text-primary transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <>
      {/* ── Morning Brief ─────────────────────────────────────────────────── */}
      <div id="morning-brief" className="terminal-section">
        <ErrorBoundary sectionName="Morning Brief">
          <MorningBriefSection />
        </ErrorBoundary>
      </div>

      {/* ── Anomalies strip (pinned top of Overview) ──────────────────────── */}
      <div id="anomalies-wrap" className="terminal-section">
        <ErrorBoundary sectionName="Anomalies">
          <AnomaliesStripSection />
        </ErrorBoundary>
      </div>

      {/* ── Overview ──────────────────────────────────────────────────────── */}
      <div id="master-signal" className="terminal-section">
        <ErrorBoundary sectionName="Master Signal">
          <MasterSignalSection />
        </ErrorBoundary>
      </div>

      <div id="key-metrics" className="terminal-section">
        <ErrorBoundary sectionName="Key Metrics">
          <KeyMetricsSection />
        </ErrorBoundary>
      </div>

      <div id="regime" className="terminal-section">
        <ErrorBoundary sectionName="Regime">
          <RegimeSection />
        </ErrorBoundary>
      </div>

      <div id="regime-playbook" className="terminal-section">
        <ErrorBoundary sectionName="Regime Playbook">
          <RegimePlaybookSection />
        </ErrorBoundary>
      </div>

      <div id="market-clock" className="terminal-section">
        <ErrorBoundary sectionName="Market Clock">
          <MarketClockSection />
        </ErrorBoundary>
      </div>

      {/* ── Signals ───────────────────────────────────────────────────────── */}
      <div id="signals" className="terminal-section">
        <ErrorBoundary sectionName="Signals">
          <Suspense fallback={<SectionSkeleton />}>
            <SignalsSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="ensemble" className="terminal-section">
        <ErrorBoundary sectionName="Ensemble">
          <Suspense fallback={<SectionSkeleton />}>
            <EnsembleSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="signal-stack" className="terminal-section">
        <ErrorBoundary sectionName="Signal Stack">
          <Suspense fallback={<SectionSkeleton />}>
            <SignalStackSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="signal-story-wrap" className="terminal-section">
        <ErrorBoundary sectionName="Signal Storytelling">
          <Suspense fallback={<SectionSkeleton />}>
            <SignalStorySection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div className="terminal-section">
        <ErrorBoundary sectionName="Signal Scorecard">
          <Suspense fallback={<SectionSkeleton />}>
            <SignalScorecardSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div className="terminal-section">
        <ErrorBoundary sectionName="Alt-Data Positioning">
          <Suspense fallback={<SectionSkeleton />}>
            <AltDataSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="sector-allocation" className="terminal-section">
        <ErrorBoundary sectionName="Sector Allocation">
          <Suspense fallback={<SectionSkeleton />}>
            <SectorAllocationSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="factor-rotation" className="terminal-section">
        <ErrorBoundary sectionName="Factor Rotation">
          <Suspense fallback={<SectionSkeleton />}>
            <FactorRotationSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="model-agreement" className="terminal-section">
        <ErrorBoundary sectionName="Model Agreement">
          <Suspense fallback={<SectionSkeleton />}>
            <ModelAgreementSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="cta-trend" className="terminal-section">
        <ErrorBoundary sectionName="CTA Trend">
          <Suspense fallback={<SectionSkeleton />}>
            <CTATrendSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="news-sentiment" className="terminal-section">
        <ErrorBoundary sectionName="News Sentiment">
          <Suspense fallback={<SectionSkeleton />}>
            <NewsSentimentSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      {/* ── Risk ──────────────────────────────────────────────────────────── */}
      <div id="risk-indicators" className="terminal-section">
        <ErrorBoundary sectionName="Risk Indicators">
          <Suspense fallback={<SectionSkeleton />}>
            <RiskIndicatorsSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="risk-analytics" className="terminal-section">
        <ErrorBoundary sectionName="Risk Analytics">
          <Suspense fallback={<SectionSkeleton />}>
            <RiskAnalyticsSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div className="terminal-section">
        <ErrorBoundary sectionName="Factor Exposure">
          <Suspense fallback={<SectionSkeleton />}>
            <FactorExposureSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div className="terminal-section">
        <ErrorBoundary sectionName="VaR & Stress">
          <Suspense fallback={<SectionSkeleton />}>
            <VaRStressSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="debt-cycle" className="terminal-section">
        <ErrorBoundary sectionName="Debt Cycle">
          <Suspense fallback={<SectionSkeleton />}>
            <DebtCycleSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="advanced" className="terminal-section">
        <ErrorBoundary sectionName="Advanced Indicators">
          <Suspense fallback={<SectionSkeleton />}>
            <AdvancedIndicatorsSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="correlation" className="terminal-section">
        <ErrorBoundary sectionName="Correlation Regime">
          <Suspense fallback={<SectionSkeleton />}>
            <CorrelationRegimeSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="correlation-matrix-wrap" className="terminal-section">
        <ErrorBoundary sectionName="Correlation Matrix">
          <Suspense fallback={<SectionSkeleton />}>
            <CorrelationMatrixSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="factor-decomposition" className="terminal-section">
        <ErrorBoundary sectionName="Factor Decomposition">
          <Suspense fallback={<SectionSkeleton />}>
            <FactorDecompositionSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="risk-parity" className="terminal-section">
        <ErrorBoundary sectionName="Risk Parity">
          <Suspense fallback={<SectionSkeleton />}>
            <RiskParitySection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="horizon-tension" className="terminal-section">
        <ErrorBoundary sectionName="Horizon Tension">
          <Suspense fallback={<SectionSkeleton />}>
            <HorizonTensionSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      {/* ── Forecasts ─────────────────────────────────────────────────────── */}
      <div id="nowcast" className="terminal-section">
        <ErrorBoundary sectionName="Nowcast">
          <Suspense fallback={<SectionSkeleton />}>
            <NowcastSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="liquidity" className="terminal-section">
        <ErrorBoundary sectionName="Liquidity">
          <Suspense fallback={<SectionSkeleton />}>
            <LiquiditySection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="sentiment" className="terminal-section">
        <ErrorBoundary sectionName="Sentiment">
          <Suspense fallback={<SectionSkeleton />}>
            <SentimentSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="yield-curve">
        <ErrorBoundary sectionName="Yield Curve">
          <Suspense fallback={<SectionSkeleton />}>
            <YieldCurveSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="valuation" className="terminal-section">
        <ErrorBoundary sectionName="Valuation">
          <Suspense fallback={<SectionSkeleton />}>
            <ValuationSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="expected-returns" className="terminal-section">
        <ErrorBoundary sectionName="Expected Returns">
          <Suspense fallback={<SectionSkeleton />}>
            <ExpectedReturnsSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      {/* ── Strategy ──────────────────────────────────────────────────────── */}
      <div id="fx-monitor" className="terminal-section">
        <ErrorBoundary sectionName="FX Monitor">
          <Suspense fallback={<SectionSkeleton />}>
            <FXMonitorSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="commodities-dashboard" className="terminal-section">
        <ErrorBoundary sectionName="Commodities Dashboard">
          <Suspense fallback={<SectionSkeleton />}>
            <CommoditiesDashboardSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="fixed-income-dashboard" className="terminal-section">
        <ErrorBoundary sectionName="Fixed Income Dashboard">
          <Suspense fallback={<SectionSkeleton />}>
            <FixedIncomeDashboardSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="gmo-forecasts" className="terminal-section">
        <ErrorBoundary sectionName="GMO Forecasts">
          <Suspense fallback={<SectionSkeleton />}>
            <GMOForecastsSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="international" className="terminal-section">
        <ErrorBoundary sectionName="International Macro">
          <Suspense fallback={<SectionSkeleton />}>
            <InternationalMacroSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="reflexivity" className="terminal-section">
        <ErrorBoundary sectionName="Reflexivity">
          <Suspense fallback={<SectionSkeleton />}>
            <ReflexivitySection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="transmission" className="terminal-section">
        <ErrorBoundary sectionName="Transmission">
          <Suspense fallback={<SectionSkeleton />}>
            <TransmissionSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="regime-transition" className="terminal-section">
        <ErrorBoundary sectionName="Regime Transition">
          <Suspense fallback={<SectionSkeleton />}>
            <RegimeTransitionSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="regime-outlook-wrap" className="terminal-section">
        <ErrorBoundary sectionName="Regime Outlook">
          <Suspense fallback={<SectionSkeleton />}>
            <RegimeOutlookSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="momentum-veto" className="terminal-section">
        <ErrorBoundary sectionName="Momentum Veto">
          <Suspense fallback={<SectionSkeleton />}>
            <MomentumVetoSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div className="terminal-section">
        <ErrorBoundary sectionName="Positions">
          <Suspense fallback={<SectionSkeleton />}>
            <PositionsSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div className="terminal-section">
        <ErrorBoundary sectionName="Trade Workflow">
          <Suspense fallback={<SectionSkeleton />}>
            <TradeWorkflowSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="trade-ideas" className="terminal-section">
        <ErrorBoundary sectionName="Trade Ideas">
          <Suspense fallback={<SectionSkeleton />}>
            <TradeIdeasSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="trade-recommendations" className="terminal-section">
        <ErrorBoundary sectionName="Trade Recommendations">
          <Suspense fallback={<SectionSkeleton />}>
            <TradeRecommendationsSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="scenario-analysis" className="terminal-section">
        <ErrorBoundary sectionName="Scenario Analysis">
          <Suspense fallback={<SectionSkeleton />}>
            <ScenarioAnalysisSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      {/* ── Equity Research ───────────────────────────────────────────────── */}
      <div id="equity-research" className="terminal-section">
        <ErrorBoundary sectionName="Equity Research">
          <Suspense fallback={<SectionSkeleton />}>
            <EquityResearchSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      {/* ── Portfolio ─────────────────────────────────────────────────────── */}
      <div id="portfolio" className="terminal-section">
        <ErrorBoundary sectionName="Portfolio Analyser">
          <Suspense fallback={<SectionSkeleton />}>
            <PortfolioAnalyserSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="performance-attribution" className="terminal-section">
        <ErrorBoundary sectionName="Performance Attribution">
          <Suspense fallback={<SectionSkeleton />}>
            <PerformanceAttributionSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="data-to-watch" className="terminal-section">
        <ErrorBoundary sectionName="Data to Watch">
          <Suspense fallback={<SectionSkeleton />}>
            <DataToWatchSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="investment-memo" className="terminal-section">
        <ErrorBoundary sectionName="Investment Memo">
          <Suspense fallback={<SectionSkeleton />}>
            <InvestmentMemoSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="business-layer" className="terminal-section">
        <ErrorBoundary sectionName="Business Layer">
          <Suspense fallback={<SectionSkeleton />}>
            <BusinessLayerSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="economic-calendar" className="terminal-section">
        <ErrorBoundary sectionName="Event Calendar">
          <Suspense fallback={<SectionSkeleton />}>
            <EventCalendarSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="event-vol-wrap" className="terminal-section">
        <ErrorBoundary sectionName="Event Volatility">
          <Suspense fallback={<SectionSkeleton />}>
            <EventVolSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      {/* ── System ────────────────────────────────────────────────────────── */}
      <div id="system-health" className="terminal-section">
        <ErrorBoundary sectionName="System Health">
          <Suspense fallback={<SectionSkeleton />}>
            <SystemHealthSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="data-providers-wrap" className="terminal-section">
        <ErrorBoundary sectionName="Data Providers">
          <Suspense fallback={<SectionSkeleton />}>
            <DataProvidersSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div className="terminal-section">
        <ErrorBoundary sectionName="Audit & Compliance">
          <Suspense fallback={<SectionSkeleton />}>
            <SystemAuditSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      {/* ── Developer Tools ───────────────────────────────────────────────── */}
      <div id="data-explorer" className="terminal-section">
        <ErrorBoundary sectionName="Data Explorer">
          <Suspense fallback={<SectionSkeleton />}>
            <DataExplorerSection />
          </Suspense>
        </ErrorBoundary>
      </div>
    </>
  );
}
