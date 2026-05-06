import { useEffect, useState, Suspense } from 'react';
import { TerminalShell } from './components/layout/TerminalShell';
import { LoginScreen } from './components/LoginScreen';
import { useAuth } from './context/AuthContext';
import { ErrorBoundary } from './components/ErrorBoundary';
import { useMacroStore, selectMeta, selectIsLoading, selectRegime } from './store/macroStore';
import { SectionSkeleton } from './components/ui/SectionSkeleton';
import {
  MorningBriefSection,
  MasterSignalSection,
  KeyMetricsSection,
  RegimeSection,
  RegimePlaybookSection,
  SignalStackSection,
  SectorAllocationSection,
  FactorRotationSection,
  RiskIndicatorsSection,
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
  CTATrendSection,
  BusinessLayerSection,
  EnsembleSection,
  PerformanceAttributionSection,
  SystemHealthSection,
  DataExplorerSection,
  DataToWatchSection,
  InvestmentMemoSection,
  ModelAgreementSection,
  ExpectedReturnsSection,
  InternationalMacroSection,
  RegimeTransitionSection,
  MomentumVetoSection,
  ValuationSection,
  NewsSentimentSection,
  SignalsSection,
  TransmissionSection,
  CorrelationRegimeSection,
  RiskParitySection,
  EquityResearchSection,
  COTPositioningSection,
  RiskAnalyticsSection,
  EventCalendarSection,
  TradeIdeasSection,
  ScenarioAnalysisSection,
  YieldCurveSection,
  FXMonitorSection,
  CommoditiesDashboardSection,
  FixedIncomeDashboardSection,
  MarketClockSection,
  TradeRecommendationsSection,
} from './components/sections';
function App() {
  const { isAuthenticated } = useAuth();
  const [activeSection, setActiveSection] = useState('master-signal');

  // Initialize macro store
  const fetchDashboard = useMacroStore((state) => state.fetchDashboard);
  const startWebSocket = useMacroStore((state) => state.startWebSocket);
  const stopWebSocket = useMacroStore((state) => state.stopWebSocket);
  const reconnectWebSocket = useMacroStore((state) => state.reconnectWebSocket);
  const meta = useMacroStore(selectMeta);
  const isLoading = useMacroStore(selectIsLoading);
  const wsError = useMacroStore((state) => state.wsError);
  const regime = useMacroStore(selectRegime);

  // Initialize store on mount
  useEffect(() => {
    fetchDashboard();
    startWebSocket();

    return () => {
      stopWebSocket();
    };
  }, [fetchDashboard, startWebSocket, stopWebSocket]);

  // Poll for dashboard updates every 60 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      fetchDashboard();
    }, 60000);
    return () => clearInterval(interval);
  }, [fetchDashboard]);

  // Highlight the active section in the sidebar as the user scrolls
  useEffect(() => {
    const sections = document.querySelectorAll('[id]');
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) setActiveSection(entry.target.id);
        });
      },
      { threshold: 0.2, rootMargin: '-80px 0px 0px 0px' }
    );
    sections.forEach((s) => observer.observe(s));
    return () => observer.disconnect();
  }, []);

  const handleNavigate = (sectionId: string) => {
    const el = document.getElementById(sectionId);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      setActiveSection(sectionId);
    }
  };

  const handleRefresh = () => {
    fetchDashboard();
    reconnectWebSocket();
  };

  if (!isAuthenticated) return <LoginScreen />;

  if (isLoading) {
    return (
      <div className="min-h-screen bg-bg flex items-center justify-center">
        <div className="text-text-secondary font-mono">Initializing Terminal...</div>
      </div>
    );
  }

  if (meta.dataStatus === 'error') {
    return (
      <div className="min-h-screen bg-bg flex items-center justify-center">
        <div className="text-center">
          <div className="text-red font-mono mb-4">Failed to load dashboard</div>
          {wsError && <div className="text-text-secondary text-xs mb-4">{wsError}</div>}
          <button
            onClick={handleRefresh}
            className="px-4 py-2 bg-bloomberg text-bg border border-bloomberg font-mono text-xs"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <TerminalShell
      latestDate={meta.latestDate || undefined}
      dataStatus={meta.dataStatus === 'live' ? 'current' : meta.dataStatus === 'stale' ? 'stale' : 'unknown'}
      mode="LIVE"
      currentRegime={regime.current || undefined}
      alertCount={0}
      onRefresh={handleRefresh}
      loading={isLoading}
      activeSection={activeSection}
      onNavigate={handleNavigate}
    >
      {/* ── Morning Brief ─────────────────────────────────────────────────── */}
      <div id="morning-brief">
        <ErrorBoundary sectionName="Morning Brief">
          <MorningBriefSection />
        </ErrorBoundary>
      </div>

      {/* ── Overview ──────────────────────────────────────────────────────── */}
      <div id="master-signal">
        <ErrorBoundary sectionName="Master Signal">
          <MasterSignalSection />
        </ErrorBoundary>
      </div>
      <div id="key-metrics">
        <ErrorBoundary sectionName="Key Metrics">
          <KeyMetricsSection />
        </ErrorBoundary>
      </div>
      <div id="regime">
        <ErrorBoundary sectionName="Regime">
          <RegimeSection />
        </ErrorBoundary>
      </div>
      <div id="regime-playbook">
        <ErrorBoundary sectionName="Regime Playbook">
          <RegimePlaybookSection />
        </ErrorBoundary>
      </div>
      <div id="market-clock">
        <ErrorBoundary sectionName="Market Clock">
          <MarketClockSection />
        </ErrorBoundary>
      </div>

      {/* ── Signals ───────────────────────────────────────────────────────── */}
      <div id="signals">
        <ErrorBoundary sectionName="Signals">
          <Suspense fallback={<SectionSkeleton />}>
            <SignalsSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="ensemble">
        <ErrorBoundary sectionName="Ensemble">
          <Suspense fallback={<SectionSkeleton />}>
            <EnsembleSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="signal-stack">
        <ErrorBoundary sectionName="Signal Stack">
          <Suspense fallback={<SectionSkeleton />}>
            <SignalStackSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="sector-allocation">
        <ErrorBoundary sectionName="Sector Allocation">
          <Suspense fallback={<SectionSkeleton />}>
            <SectorAllocationSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="factor-rotation">
        <ErrorBoundary sectionName="Factor Rotation">
          <Suspense fallback={<SectionSkeleton />}>
            <FactorRotationSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="cot-positioning">
        <ErrorBoundary sectionName="COT Positioning">
          <Suspense fallback={<SectionSkeleton />}>
            <COTPositioningSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="model-agreement">
        <ErrorBoundary sectionName="Model Agreement">
          <Suspense fallback={<SectionSkeleton />}>
            <ModelAgreementSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="cta-trend">
        <ErrorBoundary sectionName="CTA Trend">
          <Suspense fallback={<SectionSkeleton />}>
            <CTATrendSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="news-sentiment">
        <ErrorBoundary sectionName="News Sentiment">
          <Suspense fallback={<SectionSkeleton />}>
            <NewsSentimentSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      {/* ── Risk ──────────────────────────────────────────────────────────── */}
      <div id="risk-indicators">
        <ErrorBoundary sectionName="Risk Indicators">
          <Suspense fallback={<SectionSkeleton />}>
            <RiskIndicatorsSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="risk-analytics">
        <ErrorBoundary sectionName="Risk Analytics">
          <Suspense fallback={<SectionSkeleton />}>
            <RiskAnalyticsSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="debt-cycle">
        <ErrorBoundary sectionName="Debt Cycle">
          <Suspense fallback={<SectionSkeleton />}>
            <DebtCycleSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="advanced">
        <ErrorBoundary sectionName="Advanced Indicators">
          <Suspense fallback={<SectionSkeleton />}>
            <AdvancedIndicatorsSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="correlation">
        <ErrorBoundary sectionName="Correlation Regime">
          <Suspense fallback={<SectionSkeleton />}>
            <CorrelationRegimeSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="factor-decomposition">
        <ErrorBoundary sectionName="Factor Decomposition">
          <Suspense fallback={<SectionSkeleton />}>
            <FactorDecompositionSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="risk-parity">
        <ErrorBoundary sectionName="Risk Parity">
          <Suspense fallback={<SectionSkeleton />}>
            <RiskParitySection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="horizon-tension">
        <ErrorBoundary sectionName="Horizon Tension">
          <Suspense fallback={<SectionSkeleton />}>
            <HorizonTensionSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      {/* ── Forecasts ─────────────────────────────────────────────────────── */}
      <div id="nowcast">
        <ErrorBoundary sectionName="Nowcast">
          <Suspense fallback={<SectionSkeleton />}>
            <NowcastSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="liquidity">
        <ErrorBoundary sectionName="Liquidity">
          <Suspense fallback={<SectionSkeleton />}>
            <LiquiditySection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="sentiment">
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
      <div id="valuation">
        <ErrorBoundary sectionName="Valuation">
          <Suspense fallback={<SectionSkeleton />}>
            <ValuationSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="expected-returns">
        <ErrorBoundary sectionName="Expected Returns">
          <Suspense fallback={<SectionSkeleton />}>
            <ExpectedReturnsSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      {/* ── Strategy ──────────────────────────────────────────────────────── */}
      <div id="fx-monitor">
        <ErrorBoundary sectionName="FX Monitor">
          <Suspense fallback={<SectionSkeleton />}>
            <FXMonitorSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="commodities-dashboard">
        <ErrorBoundary sectionName="Commodities Dashboard">
          <Suspense fallback={<SectionSkeleton />}>
            <CommoditiesDashboardSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="fixed-income-dashboard">
        <ErrorBoundary sectionName="Fixed Income Dashboard">
          <Suspense fallback={<SectionSkeleton />}>
            <FixedIncomeDashboardSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="gmo-forecasts">
        <ErrorBoundary sectionName="GMO Forecasts">
          <Suspense fallback={<SectionSkeleton />}>
            <GMOForecastsSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="international">
        <ErrorBoundary sectionName="International Macro">
          <Suspense fallback={<SectionSkeleton />}>
            <InternationalMacroSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="reflexivity">
        <ErrorBoundary sectionName="Reflexivity">
          <Suspense fallback={<SectionSkeleton />}>
            <ReflexivitySection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="transmission">
        <ErrorBoundary sectionName="Transmission">
          <Suspense fallback={<SectionSkeleton />}>
            <TransmissionSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="regime-transition">
        <ErrorBoundary sectionName="Regime Transition">
          <Suspense fallback={<SectionSkeleton />}>
            <RegimeTransitionSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="momentum-veto">
        <ErrorBoundary sectionName="Momentum Veto">
          <Suspense fallback={<SectionSkeleton />}>
            <MomentumVetoSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="trade-ideas">
        <ErrorBoundary sectionName="Trade Ideas">
          <Suspense fallback={<SectionSkeleton />}>
            <TradeIdeasSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="trade-recommendations">
        <ErrorBoundary sectionName="Trade Recommendations">
          <Suspense fallback={<SectionSkeleton />}>
            <TradeRecommendationsSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="scenario-analysis">
        <ErrorBoundary sectionName="Scenario Analysis">
          <Suspense fallback={<SectionSkeleton />}>
            <ScenarioAnalysisSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      {/* ── Equity Research ───────────────────────────────────────────────── */}
      <div id="equity-research">
        <ErrorBoundary sectionName="Equity Research">
          <Suspense fallback={<SectionSkeleton />}>
            <EquityResearchSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      {/* ── Portfolio ─────────────────────────────────────────────────────── */}
      <div id="portfolio">
        <ErrorBoundary sectionName="Portfolio Analyser">
          <Suspense fallback={<SectionSkeleton />}>
            <PortfolioAnalyserSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="performance-attribution">
        <ErrorBoundary sectionName="Performance Attribution">
          <Suspense fallback={<SectionSkeleton />}>
            <PerformanceAttributionSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="data-to-watch">
        <ErrorBoundary sectionName="Data to Watch">
          <Suspense fallback={<SectionSkeleton />}>
            <DataToWatchSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="investment-memo">
        <ErrorBoundary sectionName="Investment Memo">
          <Suspense fallback={<SectionSkeleton />}>
            <InvestmentMemoSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="business-layer">
        <ErrorBoundary sectionName="Business Layer">
          <Suspense fallback={<SectionSkeleton />}>
            <BusinessLayerSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div id="economic-calendar">
        <ErrorBoundary sectionName="Event Calendar">
          <Suspense fallback={<SectionSkeleton />}>
            <EventCalendarSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      {/* ── System ────────────────────────────────────────────────────────── */}
      <div id="system-health">
        <ErrorBoundary sectionName="System Health">
          <Suspense fallback={<SectionSkeleton />}>
            <SystemHealthSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      {/* ── Developer Tools ───────────────────────────────────────────────── */}
      <div id="data-explorer">
        <ErrorBoundary sectionName="Data Explorer">
          <Suspense fallback={<SectionSkeleton />}>
            <DataExplorerSection />
          </Suspense>
        </ErrorBoundary>
      </div>
    </TerminalShell>
  );
}

export default App;
