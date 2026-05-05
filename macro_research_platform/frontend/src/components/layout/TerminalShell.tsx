// TerminalShell — 3-panel institutional trading terminal layout
// Topbar + Sidebar + Main + Detail Panel

import { useState, useEffect, useCallback } from 'react';
import { Topbar } from './Topbar';
import { Sidebar } from './Sidebar';
import { DetailPanel } from './DetailPanel';
import { CommandPalette } from './CommandPalette';
import { AlertsPanel } from './AlertsPanel';
import { cn } from '@/lib/utils';

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
}: TerminalShellProps) {
  const [activeSection, setActiveSection] = useState('master-signal');
  const [detailPanelOpen, setDetailPanelOpen] = useState(true);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [alertsPanelOpen, setAlertsPanelOpen] = useState(false);
  const [sidebarCollapsed] = useState(false);

  // Keyboard shortcuts
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      // Cmd+K / Ctrl+K for command palette
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setCommandPaletteOpen((prev) => !prev);
      }
      // Escape to close panels
      if (e.key === 'Escape') {
        setCommandPaletteOpen(false);
        setAlertsPanelOpen(false);
      }
      // G for master signal
      if (e.key === 'g' && !e.metaKey && !e.ctrlKey) {
        setActiveSection('master-signal');
        document.getElementById('master-signal')?.scrollIntoView({ behavior: 'smooth' });
      }
      // R for regime
      if (e.key === 'r' && !e.metaKey && !e.ctrlKey) {
        setActiveSection('regime');
        document.getElementById('regime')?.scrollIntoView({ behavior: 'smooth' });
      }
      // F for factor rotation
      if (e.key === 'f' && !e.metaKey && !e.ctrlKey) {
        setActiveSection('factor-rotation');
        document.getElementById('factor-rotation')?.scrollIntoView({ behavior: 'smooth' });
      }
      // H for system health
      if (e.key === 'h' && !e.metaKey && !e.ctrlKey) {
        setActiveSection('system-health');
        document.getElementById('system-health')?.scrollIntoView({ behavior: 'smooth' });
      }
    },
    []
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
        'ml-signals',
        'ensemble',
        'signal-stack',
        'sector-allocation',
        'factor-rotation',
        'risk-indicators',
        'debt-cycle',
        'advanced',
        'nowcast',
        'liquidity',
        'sentiment',
        'gmo',
        'valuation',
        'expected-returns',
        'international-macro',
        'reflexivity',
        'transmission',
        'regime-transition',
        'correlation-regime',
        'factor-decomp',
        'risk-parity',
        'momentum-veto',
        'horizon',
        'model-agreement',
        'cta-trends',
        'news-sentiment',
        'portfolio-fit',
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
  };

  return (
    <div className="min-h-screen bg-bg">
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
      />

      {/* Sidebar */}
      <div
        className={cn(
          'fixed left-0 top-12 bottom-0 z-40 transition-all duration-200',
          sidebarCollapsed ? 'w-12' : 'w-56'
        )}
      >
        <Sidebar
          activeSection={activeSection}
          onNavigate={handleNavigate}
          currentRegime={currentRegime}
        />
      </div>

      {/* Main Content */}
      <main
        className={cn(
          'pt-12 transition-all duration-200',
          sidebarCollapsed ? 'pl-12' : 'pl-56',
          detailPanelOpen ? 'lg:pr-72' : 'pr-0'
        )}
      >
        <div className="min-h-[calc(100vh-48px)]">
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
      />

      {/* Alerts Panel */}
      <AlertsPanel
        isOpen={alertsPanelOpen}
        onClose={() => setAlertsPanelOpen(false)}
        onViewSection={handleNavigate}
      />
    </div>
  );
}
