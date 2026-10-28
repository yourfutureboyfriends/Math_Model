// App.tsx — Root component with auth and routing
// Phase 4 Step 5: Dashboard content extracted to pages/DashboardPage.tsx

import { MfaEnrollScreen } from '@/components/account/TwoFactor';
import { applyBrand, loadFunds } from '@/lib/fundBrand';
import { currentFund } from '@/lib/fund';
import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { TerminalShell } from './components/layout/TerminalShell';
import { LoginScreen } from './components/LoginScreen';
import { ChangePasswordScreen } from './components/account/AccountPanels';
import { DiagnosticsPanel } from './components/dev/DiagnosticsPanel';
import { ChartModal } from './components/ui/ChartModal';
import { useAuth } from './context/AuthContext';
// each mode loads on first use: the sign-in screen and the Research view no longer download Markets mode (and vice versa)
const DashboardPage = lazy(() => import('./pages/DashboardPage').then((m) => ({ default: m.DashboardPage })));
const MarketsPage = lazy(() => import('./pages/MarketsPage').then((m) => ({ default: m.MarketsPage })));
const PrivateEquityPage = lazy(() => import('./pages/PrivateEquityPage').then((m) => ({ default: m.PrivateEquityPage })));
import { MarketsSidebar } from './components/markets/MarketsSidebar';
import { HUB_MODES, useHubMode } from './lib/hubMode';
import { PE_TABS, setPeTab, usePeTab } from './components/pe/peShared';
import { applySkin, useMarketsSkin } from './lib/theme';
import { useMacroStore, selectMeta, selectIsLoading, selectRegime, selectFullDashboard } from './store/macroStore';

function App() {
  const { isAuthenticated, mustChangePassword, mfaEnrollmentRequired } = useAuth();
  const hubMode = useHubMode();
  const skin = useMarketsSkin();
  useEffect(() => { applySkin(hubMode === 'markets' && skin === 'classic'); }, [hubMode, skin]);
  useEffect(() => {                                  // the current fund's brand colours (after sign-in)
    if (isAuthenticated) loadFunds(true).then((fs) => applyBrand(fs.find((f) => f.id === currentFund())?.brand));
  }, [isAuthenticated]);
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
  // True once any dashboard payload has loaded. Background refreshes must not tear the
  // terminal down: replacing it with a loading/error screen unmounted every panel each
  // minute (lost tabs and inputs, scroll jumped to top, ~50 panels refetched).
  const hasData = useMacroStore(selectFullDashboard) !== null;

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

  // Highlight the active section in the sidebar as the user scrolls. Re-attach once the
  // terminal is rendered (it used to run once on the login screen and observe nothing).
  useEffect(() => {
    if (!isAuthenticated || !hasData) return;
    const sections = document.querySelectorAll('.terminal-section[id], section[id]');
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
  }, [isAuthenticated, hasData]);

  // Live alert count for the topbar badge (was hard-coded to 0, hiding real alerts).
  const [alertCount, setAlertCount] = useState(0);
  useEffect(() => {
    if (!isAuthenticated) return;
    const load = () => fetch('/api/alerts').then((r) => (r.ok ? r.json() : null))
      .then((j) => j && setAlertCount((j.alerts ?? []).filter((a: any) => a.active !== false && a.id !== 'alert-normal').length))
      .catch(() => { /* keep last count */ });
    load();
    const t = setInterval(load, 300_000);
    return () => clearInterval(t);
  }, [isAuthenticated]);

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

  // One stable page element: changing the highlighted section while scrolling must not re-render the whole dashboard
  // (only the sidebar and detail panel read it).
  const page = useMemo(() => (
    <Suspense fallback={<div className="p-6 text-xs text-text-tertiary">Loading {HUB_MODES.find((m) => m.id === hubMode)?.label}…</div>}>
      {hubMode === 'markets' ? <MarketsPage /> : hubMode === 'pe' ? <PrivateEquityPage /> : <DashboardPage />}
    </Suspense>), [hubMode]);

  if (!isAuthenticated) return <LoginScreen />;
  if (mustChangePassword) return <ChangePasswordScreen />;
  if (mfaEnrollmentRequired) return <MfaEnrollScreen />;

  if (isLoading && !hasData) {
    return (
      <div className="min-h-screen bg-bg flex items-center justify-center">
        <div className="text-text-secondary font-mono">Initializing Terminal...</div>
      </div>
    );
  }

  if (meta.dataStatus === 'error' && !hasData) {
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
    <>
      <TerminalShell
        latestDate={meta.latestDate || undefined}
        dataStatus={meta.dataStatus === 'live' ? 'current' : meta.dataStatus === 'stale' ? 'stale' : 'unknown'}
        mode="LIVE"
        currentRegime={regime.current || undefined}
        alertCount={alertCount}
        onRefresh={handleRefresh}
        loading={isLoading}
        activeSection={activeSection}
        onNavigate={handleNavigate}
        sidebar={hubMode === 'markets' ? (collapsed) => <MarketsSidebar collapsed={collapsed} />
          : hubMode === 'pe' ? (collapsed) => <PeSidebar collapsed={collapsed} /> : undefined}
      >
        {page}
      </TerminalShell>

      {/* Click-to-chart: any panel opens a full interactive chart (openChart) */}
      <ChartModal />

      {/* Developer diagnostics panel (dev mode only) */}
      {import.meta.env.DEV && <DiagnosticsPanel />}
    </>
  );
}

export default App;

/** PE area sidebar: the four tools. */
function PeSidebar({ collapsed }: { collapsed: boolean }) {
  const tab = usePeTab();
  if (collapsed) return null;
  return (
    <nav aria-label="Private equity" className="py-3 space-y-px">
      <div className="px-5 pb-1.5 text-[10px] uppercase tracking-[0.08em] font-semibold text-text-tertiary">Private equity</div>
      {PE_TABS.map((t) => (
        <button key={t.id} onClick={() => setPeTab(t.id)} title={t.desc}
          className={`w-[calc(100%-1rem)] mx-2 px-3 h-7 flex items-center gap-2.5 rounded-md text-xs transition-colors ${tab === t.id ? 'bg-bloomberg/10 text-text-primary font-medium' : 'text-text-secondary hover:bg-text-primary/5 hover:text-text-primary'}`}>
          <span className={`nav-dot is-key ${tab === t.id ? 'is-active' : ''}`} />{t.label}
        </button>))}
    </nav>
  );
}
