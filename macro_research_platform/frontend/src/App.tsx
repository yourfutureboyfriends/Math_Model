// App.tsx — Root component with auth and routing
// Phase 4 Step 5: Dashboard content extracted to pages/DashboardPage.tsx

import { useEffect, useState } from 'react';
import { TerminalShell } from './components/layout/TerminalShell';
import { LoginScreen } from './components/LoginScreen';
import { DiagnosticsPanel } from './components/dev/DiagnosticsPanel';
import { useAuth } from './context/AuthContext';
import { DashboardPage } from './pages';
import { useMacroStore, selectMeta, selectIsLoading, selectRegime } from './store/macroStore';

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
    <>
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
        <DashboardPage />
      </TerminalShell>

      {/* Developer diagnostics panel (dev mode only) */}
      {import.meta.env.DEV && <DiagnosticsPanel />}
    </>
  );
}

export default App;
