// POLISH-1: Keyboard shortcuts hook
// F1-F7: Navigate to sidebar sections
// Ctrl+R: Force refresh
// Ctrl+A: Alerts panel
// Ctrl+M: Investment memo

import { useEffect, useCallback } from 'react';

interface KeyboardActions {
  refresh: () => void;
  openAlerts: () => void;
  openMemo: () => void;
}

export const useKeyboardShortcuts = (actions: KeyboardActions) => {
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    // F1-F7: navigate to sidebar sections
    const fnMap: Record<string, string> = {
      F1: 'morning-brief',
      F2: 'signals',
      F3: 'risk',
      F4: 'forecasts',
      F5: 'strategy',
      F6: 'portfolio',
      F7: 'system-health',
    };

    if (fnMap[e.key]) {
      e.preventDefault();
      const element = document.getElementById(fnMap[e.key]);
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
      return;
    }

    // Ctrl+R: force refresh
    if (e.ctrlKey && e.key === 'r') {
      e.preventDefault();
      actions.refresh();
      return;
    }

    // Ctrl+A: alerts panel
    if (e.ctrlKey && e.key === 'a') {
      e.preventDefault();
      actions.openAlerts();
      return;
    }

    // Ctrl+M: investment memo
    if (e.ctrlKey && e.key === 'm') {
      e.preventDefault();
      actions.openMemo();
      return;
    }
  }, [actions]);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);
};

// Helper to format keyboard shortcuts for display
export const formatShortcut = (key: string): string => {
  const isMac = navigator.platform.toLowerCase().includes('mac');
  const modifier = isMac ? '⌘' : 'Ctrl';

  const shortcuts: Record<string, string> = {
    refresh: `${modifier}+R`,
    alerts: `${modifier}+A`,
    memo: `${modifier}+M`,
    overview: 'F1',
    signals: 'F2',
    risk: 'F3',
    forecasts: 'F4',
    strategy: 'F5',
    portfolio: 'F6',
    system: 'F7',
  };

  return shortcuts[key] || key;
};
