// UPGRADE-6: Terminal Shell with Keyboard Shortcuts — Analyst Workflow
// Comprehensive keyboard navigation for power users

import { useState, useEffect, useCallback, useRef } from 'react';
import { Topbar } from './Topbar';
import { Sidebar } from './Sidebar';
import { DetailPanel } from './DetailPanel';
import { CommandPalette } from './CommandPalette';
import { AlertsPanel } from './AlertsPanel';
import { KeyboardShortcutsHelp } from './KeyboardShortcutsHelp';
import { BlackoutBanner } from '../EconomicCalendar';
import { cn } from '@/lib/utils';
import { ErrorBoundary } from '../ErrorBoundary';

interface TerminalShellProps {
  children: React.ReactNode;
  latestDate?: string;
  dataStatus?: 'current' | 'acceptable' | 'stale' | 'unknown';
  mode?: string;
  currentRegime?: string;
  alertCount?: number;
  onRefresh?: () => void;
  loading?: boolean;
  data?: any;
  activeSection?: string;
  onNavigate?: (sectionId: string) => void;
}

export function TerminalShell({
  children,
  latestDate,
  dataStatus,
  mode,
  currentRegime,
  alertCount = 0,
  onRefresh,
  loading,
  data,
  activeSection: externalActiveSection,
  onNavigate: externalOnNavigate,
}: TerminalShellProps) {
  const [internalActiveSection, setInternalActiveSection] = useState('master-signal');
  const [detailPanelOpen, setDetailPanelOpen] = useState(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [alertsPanelOpen, setAlertsPanelOpen] = useState(false);
  // FIXED (BUG 2): Ensure sidebar is never undefined/null - always boolean
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(false);
  const [shortcutsHelpOpen, setShortcutsHelpOpen] = useState(false);
  const keyTimeoutRef = useRef<NodeJS.Timeout>();

  // Use external state if provided, otherwise internal
  const activeSection = externalActiveSection ?? internalActiveSection;
  const setActiveSection = externalActiveSection ? () => {} : setInternalActiveSection;

  // UPGRADE-6: Enhanced Keyboard Shortcuts — Analyst Workflow
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      // Skip if user is typing in an input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }

      const key = e.key.toLowerCase();

      // Cmd/Ctrl modifiers
      if (e.metaKey || e.ctrlKey) {
        switch (key) {
          case 'k':
            e.preventDefault();
            setCommandPaletteOpen((prev) => !prev);
            return;
          case 'r':
            e.preventDefault();
            onRefresh?.();
            return;
          case 'b':
            e.preventDefault();
            setSidebarCollapsed((prev) => !prev);
            return;
          case 'd':
            e.preventDefault();
            setDetailPanelOpen((prev) => !prev);
            return;
          case 'e':
            e.preventDefault();
            // Export data
            window.dispatchEvent(new CustomEvent('export-data'));
            return;
          case 's':
            e.preventDefault();
            // Save snapshot
            window.dispatchEvent(new CustomEvent('save-snapshot'));
            return;
        }
      }

      // Escape to close panels
      if (e.key === 'Escape') {
        setCommandPaletteOpen(false);
        setAlertsPanelOpen(false);
        setShortcutsHelpOpen(false);
        return;
      }

      // ? for help
      if (key === '?') {
        e.preventDefault();
        setShortcutsHelpOpen(true);
        return;
      }

      // Single key navigation
      const sectionMap: Record<string, string> = {
        'm': 'morning-brief',      // M = Morning Brief
        'g': 'master-signal',      // G = Master Signal (existing)
        'k': 'key-metrics',        // K = Key Metrics
        'r': 'regime',             // R = Regime (existing)
        'p': 'regime-playbook',    // P = Playbook
        's': 'signals',            // S = ML Signals
        'e': 'ensemble',           // E = Ensemble
        't': 'trade-ideas',         // T = Trade Ideas
        'f': 'factor-rotation',    // F = Factor Rotation (existing)
        'c': 'cot-positioning',    // C = COT Positioning
        'v': 'risk-indicators',    // V = Risk (V for Volatility)
        'a': 'risk-analytics',     // A = Risk Analytics
        'd': 'debt-cycle',         // D = Debt Cycle
        'n': 'nowcast',            // N = Nowcast
        'l': 'liquidity',          // L = Liquidity
        'i': 'sentiment',          // I = Sentiment
        'y': 'gmo-forecasts',     // Y = GMO (Yield forecasts)
        'u': 'valuation',           // U = Valuation
        'x': 'expected-returns',  // X = Expected Returns
        'o': 'portfolio-analyser', // O = Portfolio
        'z': 'system-health',      // Z = System Health (instead of H)
        'h': 'horizon-tension',    // H = Horizon Tension
        'w': 'news-sentiment',    // W = News
        'q': 'model-agreement',   // Q = Model Agreement
        'j': 'economic-calendar', // J = Calendar
      };

      if (sectionMap[key] && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        const sectionId = sectionMap[key];
        setActiveSection(sectionId);
        document.getElementById(sectionId)?.scrollIntoView({ behavior: 'smooth' });
        return;
      }

      // Number keys for quick access (1-9)
      if (/^[1-9]$/.test(e.key)) {
        e.preventDefault();
        const numSections = [
          'morning-brief',
          'master-signal',
          'regime',
          'signals',
          'risk-analytics',
          'trade-ideas',
          'nowcast',
          'expected-returns',
          'system-health',
        ];
        const index = parseInt(e.key) - 1;
        if (numSections[index]) {
          const sectionId = numSections[index];
          setActiveSection(sectionId);
          document.getElementById(sectionId)?.scrollIntoView({ behavior: 'smooth' });
        }
        return;
      }

      // Arrow keys for section navigation
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        const sections = document.querySelectorAll('section[id]');
        const currentIndex = Array.from(sections).findIndex(
          (s) => s.id === activeSection
        );

        if (e.key === 'ArrowDown' && currentIndex < sections.length - 1) {
          e.preventDefault();
          const nextSection = sections[currentIndex + 1];
          setActiveSection(nextSection.id);
          nextSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } else if (e.key === 'ArrowUp' && currentIndex > 0) {
          e.preventDefault();
          const prevSection = sections[currentIndex - 1];
          setActiveSection(prevSection.id);
          prevSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
        return;
      }

      if (keyTimeoutRef.current) {
        clearTimeout(keyTimeoutRef.current);
      }
    },
    [activeSection, onRefresh]
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  // Track scroll position to update active section
  // FIXED: Order matches App.tsx and Sidebar exactly
  useEffect(() => {
    const handleScroll = () => {
      const sections = [
        'master-signal',
        'key-metrics',
        'regime',
        'signals',
        'ensemble',
        'signal-stack',
        'sector-allocation',
        'factor-rotation',
        'cot-positioning',
        'risk-indicators',
        'risk-analytics',
        'debt-cycle',
        'advanced',
        'nowcast',
        'liquidity',
        'sentiment',
        'gmo-forecasts',
        'valuation',
        'expected-returns',
        'international',
        'reflexivity',
        'transmission',
        'regime-transition',
        'correlation',
        'factor-decomposition',
        'risk-parity',
        'momentum-veto',
        'horizon-tension',
        'model-agreement',
        'cta-trend',
        'news-sentiment',
        'lstm',
        'performance',
        'anomaly-detection',
        'portfolio',
        'equity-research',
        'trade-ideas',
        'portfolio-fit',
        'economic-calendar',
        'data-to-watch',
        'investment-memo',
        'business-layer',
        'system-health',
      ];

      const scrollPosition = window.scrollY + 200;

      for (const sectionId of sections) {
        const element = document.getElementById(sectionId);
        if (element) {
          const { offsetTop, offsetHeight } = element;
          if (scrollPosition >= offsetTop && scrollPosition < offsetTop + offsetHeight) {
            setActiveSection(sectionId);
            break;
          }
        }
      }
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const handleNavigate = (sectionId: string) => {
    setActiveSection(sectionId);
    const element = document.getElementById(sectionId);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    // Call external handler if provided
    externalOnNavigate?.(sectionId);
  };

  return (
    <div className="min-h-screen bg-bg">
      {/* Economic Calendar Blackout Banner */}
      <BlackoutBanner />

      {/* Topbar */}
      <Topbar
        latestDate={latestDate}
        dataStatus={dataStatus}
        mode={mode}
        alertCount={alertCount}
        onRefresh={onRefresh}
        loading={loading}
        onCommandPalette={() => setCommandPaletteOpen(true)}
        onAlertsPanel={() => setAlertsPanelOpen(true)}
        currentRegime={currentRegime}
        data={data}
      />

      {/* Sidebar */}
      <aside
        className={cn(
          'fixed left-0 top-16 bottom-0 z-40 flex flex-col transition-all duration-200 bg-surface-1 border-r border-border overflow-hidden',
          sidebarCollapsed ? 'w-[48px] min-w-[48px]' : 'w-[224px] min-w-[224px]'
        )}
      >
        <ErrorBoundary sectionName="Sidebar">
          <Sidebar
            activeSection={activeSection}
            onNavigate={handleNavigate}
            currentRegime={currentRegime}
            collapsed={sidebarCollapsed}
            onCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
          />
        </ErrorBoundary>
      </aside>

      {/* Main Content */}
      <main
        className={cn(
          'pt-16 transition-all duration-200 min-h-screen',
          sidebarCollapsed ? 'pl-[48px]' : 'pl-[224px]',
          detailPanelOpen ? 'lg:pr-72' : 'pr-0'
        )}
      >
        <div className="min-h-[calc(100vh-64px)]">
          {children}
        </div>
      </main>

      {/* Detail Panel */}
      <DetailPanel
        isOpen={detailPanelOpen}
        onClose={() => setDetailPanelOpen(false)}
        activeSection={activeSection}
        data={data}
      />

      {/* Command Palette */}
      <CommandPalette
        isOpen={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
        onNavigate={handleNavigate}
        onExport={() => {}}
        onRefresh={onRefresh}
        onToggleFullscreen={() => {
          if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen();
          } else {
            document.exitFullscreen();
          }
        }}
        onViewHealth={() => handleNavigate('system-health')}
        currentRegime={currentRegime}
      />

      {/* Alerts Panel */}
      <AlertsPanel
        isOpen={alertsPanelOpen}
        onClose={() => setAlertsPanelOpen(false)}
        onViewSection={handleNavigate}
      />

      {/* UPGRADE-6: Keyboard Shortcuts Help */}
      <KeyboardShortcutsHelp
        isOpen={shortcutsHelpOpen}
        onClose={() => setShortcutsHelpOpen(false)}
      />
    </div>
  );
}
