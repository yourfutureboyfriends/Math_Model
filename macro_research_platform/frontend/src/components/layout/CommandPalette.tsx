// Phase 8 Command Palette (Cmd+K)
// Bloomberg-style command interface

import { useState, useEffect, useRef, useCallback } from 'react';
import { Search, CornerDownLeft } from 'lucide-react';
import { cn } from '@/lib/utils';

interface CommandItem {
  id: string;
  label: string;
  shortcut?: string;
  category: 'section' | 'action';
  action: () => void;
}

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  onNavigate: (section: string) => void;
  onExport?: () => void;
  onRefresh?: () => void;
  onToggleFullscreen?: () => void;
  onViewHealth?: () => void;
}

const sections = [
  { id: 'master-signal', label: 'Master Signal' },
  { id: 'key-metrics', label: 'Key Metrics' },
  { id: 'regime', label: 'Regime Classification' },
  { id: 'signal-stack', label: 'Signal Stack' },
  { id: 'sector-allocation', label: 'Sector Allocation' },
  { id: 'factor-rotation', label: 'Factor Rotation' },
  { id: 'cta-trends', label: 'CTA Trends' },
  { id: 'risk-indicators', label: 'Risk Indicators' },
  { id: 'geopolitical', label: 'Geopolitical Risk' },
  { id: 'options', label: 'Options Intelligence' },
  { id: 'reflexivity', label: 'Reflexivity Monitor' },
  { id: 'nowcast', label: 'GDP Nowcast' },
  { id: 'gmo', label: 'GMO 7-Year Forecasts' },
  { id: 'horizon', label: 'Horizon Tensions' },
  { id: 'portfolio-fit', label: 'Portfolio Fit' },
  { id: 'factor-decomp', label: 'Factor Decomposition' },
  { id: 'alpha', label: 'Alpha Scanner' },
  { id: 'sentiment', label: 'Sentiment' },
  { id: 'debt-cycle', label: 'Debt Cycle' },
  { id: 'ml-signals', label: 'ML Signals' },
  { id: 'performance', label: 'Performance Tracking' },
  { id: 'system-health', label: 'System Health' },
  { id: 'methodology', label: 'Methodology' },
];

export function CommandPalette({
  isOpen,
  onClose,
  onNavigate,
  onExport,
  onRefresh,
  onToggleFullscreen,
  onViewHealth,
}: CommandPaletteProps) {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Build command list
  const commands: CommandItem[] = [
    // Sections
    ...sections.map((section) => ({
      id: section.id,
      label: section.label,
      category: 'section' as const,
      action: () => {
        onNavigate(section.id);
        onClose();
      },
    })),
    // Actions
    {
      id: 'export',
      label: 'Export PDF Report',
      shortcut: 'E',
      category: 'action' as const,
      action: () => {
        onExport?.();
        onClose();
      },
    },
    {
      id: 'refresh',
      label: 'Refresh All Data',
      shortcut: 'R',
      category: 'action' as const,
      action: () => {
        onRefresh?.();
        onClose();
      },
    },
    {
      id: 'fullscreen',
      label: 'Toggle Fullscreen',
      shortcut: 'F',
      category: 'action' as const,
      action: () => {
        onToggleFullscreen?.();
        onClose();
      },
    },
    {
      id: 'health',
      label: 'View System Health',
      shortcut: 'H',
      category: 'action' as const,
      action: () => {
        onViewHealth?.();
        onClose();
      },
    },
  ];

  // Filter commands based on query
  const filteredCommands = commands.filter((cmd) =>
    cmd.label.toLowerCase().includes(query.toLowerCase())
  );

  const sectionCommands = filteredCommands.filter((c) => c.category === 'section');
  const actionCommands = filteredCommands.filter((c) => c.category === 'action');

  // Reset selection when query changes
  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  // Focus input when opened
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!isOpen) return;

      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          setSelectedIndex((prev) =>
            Math.min(prev + 1, filteredCommands.length - 1)
          );
          break;
        case 'ArrowUp':
          e.preventDefault();
          setSelectedIndex((prev) => Math.max(prev - 1, 0));
          break;
        case 'Enter':
          e.preventDefault();
          if (filteredCommands[selectedIndex]) {
            filteredCommands[selectedIndex].action();
          }
          break;
        case 'Escape':
          e.preventDefault();
          onClose();
          break;
      }
    },
    [isOpen, filteredCommands, selectedIndex, onClose]
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[600px] bg-surface-2 border border-border shadow-md overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border-subtle">
          <Search className="w-4 h-4 text-text-tertiary" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Jump to section..."
            className="flex-1 bg-transparent border-none outline-none text-sm text-text-primary placeholder:text-text-tertiary font-mono"
          />
          <div className="flex items-center gap-1 text-text-tertiary">
            <span className="text-2xs">Esc</span>
          </div>
        </div>

        {/* Commands */}
        <div className="max-h-[400px] overflow-y-auto">
          {/* Sections */}
          {sectionCommands.length > 0 && (
            <div>
              <div className="px-4 py-2 text-2xs text-text-tertiary uppercase tracking-wider bg-surface-1">
                Sections
              </div>
              <div>
                {sectionCommands.map((cmd) => {
                  const globalIndex = filteredCommands.indexOf(cmd);
                  const isSelected = globalIndex === selectedIndex;
                  return (
                    <button
                      key={cmd.id}
                      onClick={cmd.action}
                      className={cn(
                        'w-full flex items-center gap-3 px-4 py-2 text-left transition-colors',
                        isSelected ? 'bg-surface-3 text-accent' : 'text-text-primary hover:bg-surface-3'
                      )}
                    >
                      <span className="text-text-tertiary">↵</span>
                      <span className="text-sm">{cmd.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Actions */}
          {actionCommands.length > 0 && (
            <div>
              <div className="px-4 py-2 text-2xs text-text-tertiary uppercase tracking-wider bg-surface-1 border-t border-border-subtle">
                Actions
              </div>
              <div>
                {actionCommands.map((cmd) => {
                  const globalIndex = filteredCommands.indexOf(cmd);
                  const isSelected = globalIndex === selectedIndex;
                  return (
                    <button
                      key={cmd.id}
                      onClick={cmd.action}
                      className={cn(
                        'w-full flex items-center gap-3 px-4 py-2 text-left transition-colors',
                        isSelected ? 'bg-surface-3 text-accent' : 'text-text-primary hover:bg-surface-3'
                      )}
                    >
                      <span className="text-text-tertiary">↵</span>
                      <span className="text-sm">{cmd.label}</span>
                      {cmd.shortcut && (
                        <span className="ml-auto text-2xs text-text-tertiary font-mono">
                          {cmd.shortcut}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* No results */}
          {filteredCommands.length === 0 && (
            <div className="px-4 py-8 text-center text-text-tertiary text-sm">
              No results for &quot;{query}&quot;
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-4 py-2 border-t border-border-subtle bg-surface-1 text-2xs text-text-tertiary">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1">
              <CornerDownLeft className="w-3 h-3" />
              select
            </span>
            <span>↑↓ navigate</span>
            <span>esc close</span>
          </div>
          <span>{filteredCommands.length} results</span>
        </div>
      </div>
    </div>
  );
}
