import { useState, useEffect } from 'react';
import { TerminalShell } from './components/layout/TerminalShell';
import { LoginScreen } from './components/LoginScreen';
import { useAuth } from './context/AuthContext';
import { ErrorBoundary } from './components/ErrorBoundary';
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
import type { DashboardData } from './types';

function App() {
  const { isAuthenticated } = useAuth();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState('master-signal');

  const fetchData = async () => {
    try {
      const response = await fetch('/api/dashboard');
      if (!response.ok) {
        let errorMsg = `HTTP ${response.status}`;
        try {
          const errorData = await response.json();
          if (errorData.detail) errorMsg += `: ${errorData.detail}`;
        } catch (e) {
          // Ignore JSON parsing errors for error responses
        }
        throw new Error(errorMsg);
      }
      const contentType = response.headers.get('content-type');
      if (!contentType || !contentType.includes('application/json')) {
        throw new Error('Response is not JSON');
      }
      const result = await response.json();
      setData(result);
      setError(null);
    } catch (err) {
      console.error('Dashboard fetch error:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch');
    } finally {
      setLoading(false);
    }
  };

  // Poll dashboard data every 30 seconds
  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  // Highlight the active section in the sidebar as the user scrolls
  useEffect(() => {
    const sections = document.querySelectorAll('section[id]');
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
  }, [data]);

  const handleNavigate = (sectionId: string) => {
    const el = document.getElementById(sectionId);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      setActiveSection(sectionId);
    }
  };

  if (!isAuthenticated) return <LoginScreen />;

  if (loading) {
    return (
      <div className="min-h-screen bg-bg flex items-center justify-center">
        <div className="text-text-secondary font-mono">Initializing Terminal...</div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-bg flex items-center justify-center">
        <div className="text-center">
          <div className="text-red font-mono mb-4">Failed to load dashboard</div>
          <button
            onClick={fetchData}
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
      latestDate={data.metadata?.latestDate}
      dataStatus={data.metadata?.dataStatus || 'unknown'}
      mode="LIVE"
      currentRegime={data.regime?.current}
      alertCount={0}
      onRefresh={fetchData}
      loading={loading}
      data={data}
      activeSection={activeSection}
      onNavigate={handleNavigate}
    >
      {/* ── Morning Brief ─────────────────────────────────────────────────── */}
      <div id="morning-brief">
        <ErrorBoundary sectionName="Morning Brief">
          <MorningBriefSection data={data.morningBrief} />
        </ErrorBoundary>
      </div>

      {/* ── Overview ──────────────────────────────────────────────────────── */}
      <div id="master-signal">
        <ErrorBoundary sectionName="Master Signal">
          <MasterSignalSection data={data.ensembleSignal} />
        </ErrorBoundary>
      </div>
      <div id="key-metrics">
        <ErrorBoundary sectionName="Key Metrics">
          <KeyMetricsSection data={data.keyMetrics} />
        </ErrorBoundary>
      </div>
      <div id="regime">
        <ErrorBoundary sectionName="Regime">
          <RegimeSection data={data.regime} />
        </ErrorBoundary>
      </div>
      <div id="regime-playbook">
        <ErrorBoundary sectionName="Regime Playbook">
          <RegimePlaybookSection data={data.regime?.playbook} currentRegime={data.regime?.current} />
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
          <SignalsSection data={data.signals} />
        </ErrorBoundary>
      </div>
      <div id="ensemble">
        <ErrorBoundary sectionName="Ensemble">
          <EnsembleSection data={data.ensembleSignal} />
        </ErrorBoundary>
      </div>
      <div id="signal-stack">
        <ErrorBoundary sectionName="Signal Stack">
          <SignalStackSection data={data.signalStack} />
        </ErrorBoundary>
      </div>
      <div id="sector-allocation">
        <ErrorBoundary sectionName="Sector Allocation">
          <SectorAllocationSection data={data.sectorAllocation} />
        </ErrorBoundary>
      </div>
      <div id="factor-rotation">
        <ErrorBoundary sectionName="Factor Rotation">
          <FactorRotationSection data={data.factorRotation} />
        </ErrorBoundary>
      </div>
      <div id="cot-positioning">
        <ErrorBoundary sectionName="COT Positioning">
          <COTPositioningSection />
        </ErrorBoundary>
      </div>

      {/* ── Risk ──────────────────────────────────────────────────────────── */}
      <div id="risk-indicators">
        <ErrorBoundary sectionName="Risk Indicators">
          <RiskIndicatorsSection data={data.riskIndicators} />
        </ErrorBoundary>
      </div>
      <div id="risk-analytics">
        <ErrorBoundary sectionName="Risk Analytics">
          <RiskAnalyticsSection />
        </ErrorBoundary>
      </div>
      <div id="debt-cycle">
        <ErrorBoundary sectionName="Debt Cycle">
          <DebtCycleSection data={data.debtCycle} />
        </ErrorBoundary>
      </div>
      <div id="advanced">
        <ErrorBoundary sectionName="Advanced Indicators">
          <AdvancedIndicatorsSection data={data.advancedIndicators} />
        </ErrorBoundary>
      </div>

      {/* ── Forecasts ─────────────────────────────────────────────────────── */}
      <div id="nowcast">
        <ErrorBoundary sectionName="Nowcast">
          <NowcastSection data={data.nowcast} />
        </ErrorBoundary>
      </div>
      <div id="liquidity">
        <ErrorBoundary sectionName="Liquidity">
          <LiquiditySection data={data.liquidity} />
        </ErrorBoundary>
      </div>
      <div id="sentiment">
        <ErrorBoundary sectionName="Sentiment">
          <SentimentSection data={data.sentiment} />
        </ErrorBoundary>
      </div>
      <div id="yield-curve">
        <ErrorBoundary sectionName="Yield Curve">
          <YieldCurveSection />
        </ErrorBoundary>
      </div>

      {/* ── Strategy ──────────────────────────────────────────────────────── */}
      <div id="fx-monitor">
        <ErrorBoundary sectionName="FX Monitor">
          <FXMonitorSection />
        </ErrorBoundary>
      </div>
      <div id="commodities-dashboard">
        <ErrorBoundary sectionName="Commodities Dashboard">
          <CommoditiesDashboardSection />
        </ErrorBoundary>
      </div>
      <div id="fixed-income-dashboard">
        <ErrorBoundary sectionName="Fixed Income Dashboard">
          <FixedIncomeDashboardSection />
        </ErrorBoundary>
      </div>
      <div id="gmo-forecasts">
        <ErrorBoundary sectionName="GMO Forecasts">
          <GMOForecastsSection data={data.gmoForecasts} />
        </ErrorBoundary>
      </div>
      <div id="valuation">
        <ErrorBoundary sectionName="Valuation">
          <ValuationSection data={data.valuation} />
        </ErrorBoundary>
      </div>
      <div id="expected-returns">
        <ErrorBoundary sectionName="Expected Returns">
          <ExpectedReturnsSection data={data.expectedReturns} />
        </ErrorBoundary>
      </div>
      <div id="international">
        <ErrorBoundary sectionName="International Macro">
          <InternationalMacroSection data={data.internationalMacro} />
        </ErrorBoundary>
      </div>
      <div id="reflexivity">
        <ErrorBoundary sectionName="Reflexivity">
          <ReflexivitySection data={data.reflexivity} />
        </ErrorBoundary>
      </div>
      <div id="transmission">
        <ErrorBoundary sectionName="Transmission">
          <TransmissionSection data={data.transmissionAnalysis} />
        </ErrorBoundary>
      </div>
      <div id="regime-transition">
        <ErrorBoundary sectionName="Regime Transition">
          <RegimeTransitionSection data={data.regimeTransitions} />
        </ErrorBoundary>
      </div>
      <div id="correlation">
        <ErrorBoundary sectionName="Correlation Regime">
          <CorrelationRegimeSection data={data.correlationRegime} />
        </ErrorBoundary>
      </div>
      <div id="factor-decomposition">
        <ErrorBoundary sectionName="Factor Decomposition">
          <FactorDecompositionSection data={data.factorDecomposition} />
        </ErrorBoundary>
      </div>
      <div id="risk-parity">
        <ErrorBoundary sectionName="Risk Parity">
          <RiskParitySection data={data.riskParityAllocation} />
        </ErrorBoundary>
      </div>
      <div id="momentum-veto">
        <ErrorBoundary sectionName="Momentum Veto">
          <MomentumVetoSection data={data.momentumVeto} />
        </ErrorBoundary>
      </div>
      <div id="horizon-tension">
        <ErrorBoundary sectionName="Horizon Tension">
          <HorizonTensionSection />
        </ErrorBoundary>
      </div>
      <div id="model-agreement">
        <ErrorBoundary sectionName="Model Agreement">
          <ModelAgreementSection data={data.modelAgreement} />
        </ErrorBoundary>
      </div>
      <div id="cta-trend">
        <ErrorBoundary sectionName="CTA Trend">
          <CTATrendSection data={data.trendSignals} />
        </ErrorBoundary>
      </div>
      <div id="news-sentiment">
        <ErrorBoundary sectionName="News Sentiment">
          <NewsSentimentSection data={data.newsSentiment} />
        </ErrorBoundary>
      </div>
      <div id="trade-ideas">
        <ErrorBoundary sectionName="Trade Ideas">
          <TradeIdeasSection data={data.tradeIdeas} />
        </ErrorBoundary>
      </div>
      <div id="trade-recommendations">
        <ErrorBoundary sectionName="Trade Recommendations">
          <TradeRecommendationsSection data={{ tradeRecommendations: data.tradeRecommendations }} />
        </ErrorBoundary>
      </div>
      <div id="scenario-analysis">
        <ErrorBoundary sectionName="Scenario Analysis">
          <ScenarioAnalysisSection data={data.scenarioAnalysis} />
        </ErrorBoundary>
      </div>
      <div id="performance-attribution">
        <ErrorBoundary sectionName="Performance Attribution">
          <PerformanceAttributionSection />
        </ErrorBoundary>
      </div>

      {/* ── Equity Research ───────────────────────────────────────────────── */}
      <div id="equity-research">
        <ErrorBoundary sectionName="Equity Research">
          <EquityResearchSection data={{ equityResearch: data.equityResearch }} />
        </ErrorBoundary>
      </div>

      {/* ── Portfolio ─────────────────────────────────────────────────────── */}
      <div id="portfolio">
        <ErrorBoundary sectionName="Portfolio Analyser">
          <PortfolioAnalyserSection simulationData={data.portfolioSimulation} />
        </ErrorBoundary>
      </div>
      {/* FIXED (BUG 6): Removed duplicate PortfolioAnalyserSection */}
      <div id="data-to-watch">
        <ErrorBoundary sectionName="Data to Watch">
          <DataToWatchSection data={data.dataToWatch} />
        </ErrorBoundary>
      </div>
      <div id="investment-memo">
        <ErrorBoundary sectionName="Investment Memo">
          <InvestmentMemoSection data={data.investmentMemo} />
        </ErrorBoundary>
      </div>
      <div id="business-layer">
        <ErrorBoundary sectionName="Business Layer">
          <BusinessLayerSection data={data.businessLayer} />
        </ErrorBoundary>
      </div>
      <div id="economic-calendar">
        <ErrorBoundary sectionName="Event Calendar">
          <EventCalendarSection data={data.eventCalendar} />
        </ErrorBoundary>
      </div>

      {/* ── System ────────────────────────────────────────────────────────── */}
      <div id="system-health">
        <ErrorBoundary sectionName="System Health">
          <SystemHealthSection data={data.systemHealth} />
        </ErrorBoundary>
      </div>

      {/* ── Developer Tools ───────────────────────────────────────────────── */}
      <div id="data-explorer">
        <ErrorBoundary sectionName="Data Explorer">
          <DataExplorerSection data={data} />
        </ErrorBoundary>
      </div>
    </TerminalShell>
  );
}

export default App;
