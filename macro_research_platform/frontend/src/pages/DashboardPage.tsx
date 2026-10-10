// Dashboard Page — Main terminal dashboard with all sections
// Uses REAL data from macroStore (fetched from backend API)

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/context/AuthContext';
import { useDesk } from '@/hooks/useDesk';
import { applyFocus, getCollapsed, panelId, saveCollapsed, setDeskPanels, useWorkspace, workspacePanels } from '@/lib/focusMode';
import { WorkspaceBar } from '@/components/layout/WorkspaceBar';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { SectionSkeleton } from '@/components/ui/SectionSkeleton';
import { useMacroStore } from '@/store/macroStore';
import { PANEL_HELP } from '@/lib/panelHelp';
import { PanelHelpPopover, type HelpAnchor } from '@/components/ui/PanelHelpPopover';
import {
  MyDeskSection,
  MacroModelSection,
  CycleRiskSection,
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
  FundCockpitSection,
  NowcastSection,
  LiquiditySection,
  SentimentSection,
  DebtCycleSection,
  AdvancedIndicatorsSection,
  GMOForecastsSection,
  ReflexivitySection,
  FactorDecompositionSection,
  HorizonTensionSection,
  ModelSleeveSection,
  StockIdeasSection,
  StockTimingSection,
  StockBacktestSection,
  PortfoliosSection,
  StrategyLabSection,
  QuantLabSection,
  PositionsSection,
  TradeWorkflowSection,
  CTATrendSection,
  COTPositioningSection,
  BusinessLayerSection,
  EnsembleSection,
  SignalStorySection,
  PerformanceAttributionSection,
  SystemHealthSection,
  DataProvidersSection,
  SystemAuditSection,
  DataExplorerSection,
  InvestmentMemoSection,
  ModelAgreementSection,
  ExpectedReturnsSection,
  InternationalMacroSection,
  RegimeTransitionSection,
  RegimeOutlookSection,
  QuadrantsSection,
  StreamAgreementSection,
  FactorValidationSection,
  RiskParityCompareSection,
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
  GlobalMarketsSection,
  GlobalCorrelationSection,
  RegionalMacroSection,
  TradeRecommendationsSection,
} from '@/components/sections';

/** Fold a top-level panel to its header (the first .section-header): every node off the
 *  path from the panel to its header is hidden while folded. */
function foldPanel(sec: HTMLElement, fold: boolean) {
  // The panel's own header: the first .section-header, else a card/brief header that leads
  // the panel (a card header further down belongs to a sub-card, not the panel).
  let head = sec.querySelector<HTMLElement>('.section-header');
  if (!head) {
    const alt = sec.querySelector<HTMLElement>('[data-panel-header]');
    let leading = !!alt;
    for (let n = alt; leading && n && n !== sec; n = n.parentElement) leading = n.parentElement?.firstElementChild === n;
    head = leading ? alt : null;
  }
  sec.querySelectorAll<HTMLElement>('[data-fold]').forEach((n) => n.removeAttribute('data-fold'));
  if (!head) { sec.removeAttribute('data-collapsed'); return; }
  head.setAttribute('data-panel-head', '');
  ensureHelpButton(head, panelId(sec));
  if (!fold) { sec.removeAttribute('data-collapsed'); return; }
  sec.setAttribute('data-collapsed', '');
  for (let node: HTMLElement = head; node !== sec && node.parentElement; node = node.parentElement) {
    for (const sib of Array.from(node.parentElement.children) as HTMLElement[]) {
      if (sib !== node) sib.setAttribute('data-fold', '');
    }
  }
}

// Every panel with an entry in PANEL_HELP gets a "?" in its header (beside the fold chevron).
// Re-applied by the mutation observer, so it survives a panel re-rendering its header.
function ensureHelpButton(head: HTMLElement, id: string | null) {
  if (!id || !PANEL_HELP[id] || head.querySelector(':scope > [data-help-btn]')) return;
  const b = document.createElement('button');
  b.type = 'button';
  b.dataset.helpBtn = id;
  b.className = 'panel-help-btn';
  b.textContent = '?';
  b.title = 'What is this panel and how do I read it?';
  b.setAttribute('aria-label', 'How to read this panel');
  head.appendChild(b);
}

export function DashboardPage() {
  // Workspaces: show one navigation group (or the role's focus set) at a time, re-applied
  // as lazy panels mount. Panels fold to their header on a header click (remembered).
  const rootRef = useRef<HTMLDivElement>(null);
  const ws = useWorkspace();
  const { user } = useAuth();
  const desk = useDesk(user?.username);
  const [collapsed, setCollapsed] = useState<Set<string>>(getCollapsed);
  const [visibleCount, setVisibleCount] = useState(0);
  // P3: subscribe to ONLY the fields this component reads, so the whole 50-section tree
  // doesn't re-render on every WebSocket price tick (was `useMacroStore((s) => s)`).
  const dataStatus = useMacroStore((s) => s.meta.dataStatus);
  const wsError = useMacroStore((s) => s.wsError);
  const fetchDashboard = useMacroStore((s) => s.fetchDashboard);
  // Skeleton / error screens only before the first payload. A background refresh used to
  // swap all 50 panels for skeletons every minute, unmounting them (lost tab/input state,
  // scroll reset, every panel refetching).
  const hasData = useMacroStore((s) => s.fullDashboard !== null);
  const isLoading = dataStatus === 'loading' && !hasData;
  const isError = dataStatus === 'error' && !hasData;
  const refreshFailed = dataStatus === 'error' && hasData;


  useEffect(() => { setDeskPanels(desk?.focus.panels ?? []); }, [desk]);
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const allowed = workspacePanels(ws, desk?.focus.panels ?? []);
    const run = () => {
      applyFocus(root, allowed);
      let n = 0;
      root.querySelectorAll<HTMLElement>(':scope > .terminal-section').forEach((sec) => {
        if (!sec.hidden) n++;
        foldPanel(sec, collapsed.has(panelId(sec) ?? ''));
      });
      setVisibleCount(n);
    };
    run();
    let t: ReturnType<typeof setTimeout> | undefined;
    const obs = new MutationObserver(() => { clearTimeout(t); t = setTimeout(run, 150); });
    obs.observe(root, { childList: true, subtree: true });
    return () => { obs.disconnect(); clearTimeout(t); };
  }, [ws, desk, collapsed, hasData]);

  const [help, setHelp] = useState<HelpAnchor | null>(null);
  const closeHelp = useCallback(() => setHelp(null), []);

  const toggleFold = useCallback((e: { target: EventTarget }) => {
    const el = e.target as HTMLElement;
    const helpBtn = el.closest<HTMLElement>('[data-help-btn]');
    if (helpBtn) {
      const id = helpBtn.dataset.helpBtn!;
      const head = helpBtn.closest<HTMLElement>('[data-panel-head]');
      const title = head?.querySelector('.section-title, h2, h3')?.textContent?.trim() || id;
      const r = helpBtn.getBoundingClientRect();
      setHelp((cur) => (cur?.id === id ? null : { id, title: String(title), rect: { left: r.left, right: r.right, top: r.top, bottom: r.bottom } }));
      return;
    }
    const head = el.closest<HTMLElement>('[data-panel-head]');
    if (!head || el.closest('button, a, input, select, textarea, label, [role="button"], [role="tab"]')) return;
    let sec: HTMLElement | null = head;
    while (sec && sec.parentElement !== rootRef.current) sec = sec.parentElement;
    const id = sec ? panelId(sec) : null;
    if (!id) return;
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      saveCollapsed(next);
      return next;
    });
  }, []);

  const collapseAll = useCallback((fold: boolean) => {
    const root = rootRef.current;
    if (!root) return;
    setCollapsed((prev) => {
      const next = new Set(prev);
      root.querySelectorAll<HTMLElement>(':scope > .terminal-section').forEach((sec) => {
        const id = panelId(sec);
        if (!id || sec.hidden || id === 'my-desk') return;
        fold ? next.add(id) : next.delete(id);
      });
      saveCollapsed(next);
      return next;
    });
  }, []);

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
    <WorkspaceBar onCollapseAll={collapseAll} visibleCount={visibleCount} />
    {help && <PanelHelpPopover anchor={help} onClose={closeHelp} />}
    <div ref={rootRef} onClick={toggleFold}>
      {refreshFailed && (
        <div className="mx-4 mt-2 px-3 py-1.5 text-2xs font-mono border border-amber/40 text-amber bg-amber/5 flex items-center gap-2">
          Refresh failed — showing the last successful data. {wsError}
          <button onClick={() => fetchDashboard()} className="ml-auto underline hover:text-text-primary">Retry</button>
        </div>
      )}
      {/* ── My Desk: role-tailored queue + key numbers ─────────────────────── */}
      <div id="my-desk" className="terminal-section">
        <ErrorBoundary sectionName="My Desk">
          <MyDeskSection />
        </ErrorBoundary>
      </div>

      {/* ── Macro Model: the systematic model as one workflow ──────────────── */}
      <div className="terminal-section">
        <ErrorBoundary sectionName="Macro Model">
          <MacroModelSection />
        </ErrorBoundary>
      </div>

      {/* ── Morning Brief ─────────────────────────────────────────────────── */}
      <div id="morning-brief" className="terminal-section">
        <ErrorBoundary sectionName="Morning Brief">
          <MorningBriefSection />
        </ErrorBoundary>
      </div>

      {/* ── Overview ──────────────────────────────────────────────────────── */}
      <div id="master-signal" className="terminal-section">
        <ErrorBoundary sectionName="Master Signal">
          <MasterSignalSection />
        </ErrorBoundary>
      </div>

      <div id="key-metrics" className="terminal-section">
        <ErrorBoundary sectionName="Macro Indicators">
          <KeyMetricsSection />
        </ErrorBoundary>
      </div>

      {/* ── Anomalies strip (pinned top of Overview) ──────────────────────── */}
      <div id="anomalies-wrap" className="terminal-section">
        <ErrorBoundary sectionName="Anomalies">
          <AnomaliesStripSection />
        </ErrorBoundary>
      </div>

      <div id="regime" className="terminal-section">
        <ErrorBoundary sectionName="Regime">
          <RegimeSection />
        </ErrorBoundary>
      </div>

      <div id="regime-playbook" className="terminal-section">
        <ErrorBoundary sectionName="Regime Allocation">
          <RegimePlaybookSection />
        </ErrorBoundary>
      </div>

      <div id="market-clock" className="terminal-section">
        <ErrorBoundary sectionName="Market Hours">
          <MarketClockSection />
        </ErrorBoundary>
      </div>

      <div className="terminal-section">
        <ErrorBoundary sectionName="Global Equity Markets">
          <Suspense fallback={<SectionSkeleton />}>
            <GlobalMarketsSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div className="terminal-section">
        <ErrorBoundary sectionName="Global Correlations">
          <Suspense fallback={<SectionSkeleton />}>
            <GlobalCorrelationSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div className="terminal-section">
        <ErrorBoundary sectionName="Regional Macro">
          <Suspense fallback={<SectionSkeleton />}>
            <RegionalMacroSection />
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
        <ErrorBoundary sectionName="Signal Breakdown">
          <Suspense fallback={<SectionSkeleton />}>
            <SignalStackSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div className="terminal-section">
        <ErrorBoundary sectionName="Signal Performance">
          <Suspense fallback={<SectionSkeleton />}>
            <SignalScorecardSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="signal-story-wrap" className="terminal-section">
        <ErrorBoundary sectionName="Signal Attribution">
          <Suspense fallback={<SectionSkeleton />}>
            <SignalStorySection />
          </Suspense>
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

      <div className="terminal-section">
        <ErrorBoundary sectionName="Alternative Data">
          <Suspense fallback={<SectionSkeleton />}>
            <AltDataSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div className="terminal-section">
        <ErrorBoundary sectionName="Signal Agreement">
          <Suspense fallback={<SectionSkeleton />}>
            <StreamAgreementSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div className="terminal-section">
        <ErrorBoundary sectionName="Factor OOS Validation">
          <Suspense fallback={<SectionSkeleton />}>
            <FactorValidationSection />
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

      <div id="sector-allocation" className="terminal-section">
        <ErrorBoundary sectionName="Sector Allocation">
          <Suspense fallback={<SectionSkeleton />}>
            <SectorAllocationSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="factor-rotation" className="terminal-section">
        <ErrorBoundary sectionName="Factor Performance">
          <Suspense fallback={<SectionSkeleton />}>
            <FactorRotationSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div className="terminal-section">
        <ErrorBoundary sectionName="COT Positioning">
          <Suspense fallback={<SectionSkeleton />}>
            <COTPositioningSection />
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

      <div className="terminal-section">
        <ErrorBoundary sectionName="Fund Overview">
          <Suspense fallback={<SectionSkeleton />}>
            <FundCockpitSection />
          </Suspense>
        </ErrorBoundary>
      </div>
      <div className="terminal-section">
        <ErrorBoundary sectionName="Cycle & Systemic Risk">
          <CycleRiskSection />
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
        <ErrorBoundary sectionName="VaR & Stress">
          <Suspense fallback={<SectionSkeleton />}>
            <VaRStressSection />
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

      <div id="horizon-tension" className="terminal-section">
        <ErrorBoundary sectionName="Horizon Tension">
          <Suspense fallback={<SectionSkeleton />}>
            <HorizonTensionSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="correlation" className="terminal-section">
        <ErrorBoundary sectionName="Stock–Bond Correlation">
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

      <div id="debt-cycle" className="terminal-section">
        <ErrorBoundary sectionName="Debt Cycle">
          <Suspense fallback={<SectionSkeleton />}>
            <DebtCycleSection />
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

      <div className="terminal-section">
        <ErrorBoundary sectionName="Risk Parity Comparison">
          <Suspense fallback={<SectionSkeleton />}>
            <RiskParityCompareSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="advanced" className="terminal-section">
        <ErrorBoundary sectionName="Leading Indicators">
          <Suspense fallback={<SectionSkeleton />}>
            <AdvancedIndicatorsSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      {/* ── Forecasts ─────────────────────────────────────────────────────── */}
      <div id="valuation" className="terminal-section">
        <ErrorBoundary sectionName="Valuation">
          <Suspense fallback={<SectionSkeleton />}>
            <ValuationSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="nowcast" className="terminal-section">
        <ErrorBoundary sectionName="Nowcast">
          <Suspense fallback={<SectionSkeleton />}>
            <NowcastSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="yield-curve" className="terminal-section">
        <ErrorBoundary sectionName="Yield Curve">
          <Suspense fallback={<SectionSkeleton />}>
            <YieldCurveSection />
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
        <ErrorBoundary sectionName="Market Sentiment">
          <Suspense fallback={<SectionSkeleton />}>
            <SentimentSection />
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

      <div id="gmo-forecasts" className="terminal-section">
        <ErrorBoundary sectionName="Long-Run Return Assumptions">
          <Suspense fallback={<SectionSkeleton />}>
            <GMOForecastsSection />
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

      <div className="terminal-section">
        <ErrorBoundary sectionName="Four Quadrants">
          <Suspense fallback={<SectionSkeleton />}>
            <QuadrantsSection />
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
      {/* ── Portfolios: my picks, auto (paper) book, optimiser ────────────── */}
      <div id="portfolios" className="terminal-section">
        <ErrorBoundary sectionName="Portfolios">
          <PortfoliosSection />
        </ErrorBoundary>
      </div>

      {/* ── Strategy Lab: research models, combination, positions ─────────── */}
      <div id="strategy-lab" className="terminal-section">
        <ErrorBoundary sectionName="Strategy Lab">
          <StrategyLabSection />
        </ErrorBoundary>
      </div>

      {/* ── Quant Lab: build / backtest / deploy your own quant algos ─────────── */}
      <div id="quant-lab" className="terminal-section">
        <ErrorBoundary sectionName="Quant Lab">
          <QuantLabSection />
        </ErrorBoundary>
      </div>

      {/* ── Stock ideas (system suggestions) ──────────────────────────────── */}
      <div id="stock-ideas" className="terminal-section">
        <ErrorBoundary sectionName="Stock Ideas">
          <StockIdeasSection />
        </ErrorBoundary>
      </div>

      {/* ── Stock entry signals ───────────────────────────────────────────── */}
      <div id="stock-timing" className="terminal-section">
        <ErrorBoundary sectionName="Stock Entry Signals">
          <StockTimingSection />
        </ErrorBoundary>
      </div>

      {/* ── Entry model backtest ──────────────────────────────────────────── */}
      <div id="stock-backtest" className="terminal-section">
        <ErrorBoundary sectionName="Entry Model Backtest">
          <StockBacktestSection />
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
        <ErrorBoundary sectionName="Allocation Recommendations">
          <Suspense fallback={<SectionSkeleton />}>
            <TradeRecommendationsSection />
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

      <div id="scenario-analysis" className="terminal-section">
        <ErrorBoundary sectionName="Scenario Analysis">
          <Suspense fallback={<SectionSkeleton />}>
            <ScenarioAnalysisSection />
          </Suspense>
        </ErrorBoundary>
      </div>

      <div id="momentum-veto" className="terminal-section">
        <ErrorBoundary sectionName="Momentum Filter">
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

      {/* ── Portfolio ─────────────────────────────────────────────────────── */}
      <div id="portfolio" className="terminal-section">
        <ErrorBoundary sectionName="Model Portfolio">
          <ModelSleeveSection />
        </ErrorBoundary>
      </div>

      <div id="performance-attribution" className="terminal-section">
        <ErrorBoundary sectionName="Performance Attribution">
          <Suspense fallback={<SectionSkeleton />}>
            <PerformanceAttributionSection />
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

      <div id="business-layer" className="terminal-section">
        <ErrorBoundary sectionName="Strategy Summary">
          <Suspense fallback={<SectionSkeleton />}>
            <BusinessLayerSection />
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

      <div id="international" className="terminal-section">
        <ErrorBoundary sectionName="Regional Equity Regimes">
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

      <div id="economic-calendar" className="terminal-section">
        <ErrorBoundary sectionName="Event Calendar">
          <Suspense fallback={<SectionSkeleton />}>
            <EventCalendarSection />
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
    </div>
    </>
  );
}
