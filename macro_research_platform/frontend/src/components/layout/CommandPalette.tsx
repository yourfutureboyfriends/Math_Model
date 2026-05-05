// Command Palette — keyboard-driven navigation with per-session favorites and recent history.

import { useState, useEffect, useRef, useCallback } from 'react';
import { Search, CornerDownLeft, Star, Clock, Zap, TrendingUp, AlertTriangle, Target } from 'lucide-react';
import { cn } from '@/lib/utils';

interface CommandItem {
  id: string;
  label: string;
  shortcut?: string;
  category: 'section' | 'action' | 'filter' | 'recent' | 'favorite';
  icon?: React.ReactNode;
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
  currentRegime?: string;
}

const sections = [
  // Morning & Overview
  { id: 'morning-brief', label: 'Morning Brief', icon: '🌅', priority: 'high' },
  { id: 'master-signal', label: 'Master Signal', icon: '◆', priority: 'high' },
  { id: 'key-metrics', label: 'Key Metrics', icon: '📊', priority: 'high' },

  // Regime
  { id: 'regime', label: 'Regime Classification', icon: '🎯', priority: 'high' },
  { id: 'regime-playbook', label: 'Regime Playbook', icon: '📖', priority: 'high' },
  { id: 'regime-transition', label: 'Regime Transition', icon: '↔️', priority: 'medium' },

  // Signals
  { id: 'signals', label: 'ML Signals', icon: '🤖', priority: 'high' },
  { id: 'ensemble', label: 'Ensemble', icon: '🔀', priority: 'high' },
  { id: 'signal-stack', label: 'Signal Stack', icon: '📚', priority: 'medium' },
  { id: 'sector-allocation', label: 'Sector Allocation', icon: '📈', priority: 'medium' },
  { id: 'factor-rotation', label: 'Factor Rotation', icon: '🔄', priority: 'medium' },
  { id: 'cot-positioning', label: 'COT Positioning', icon: '📉', priority: 'medium' },
  { id: 'model-agreement', label: 'Model Agreement', icon: '✓', priority: 'medium' },

  // Risk
  { id: 'risk-indicators', label: 'Risk Indicators', icon: '⚠️', priority: 'high' },
  { id: 'risk-analytics', label: 'Risk Analytics', icon: '🛡️', priority: 'high' },
  { id: 'debt-cycle', label: 'Debt Cycle', icon: '📉', priority: 'medium' },
  { id: 'advanced', label: 'Advanced Indicators', icon: '🔬', priority: 'low' },
  { id: 'correlation', label: 'Correlation Regime', icon: '📊', priority: 'medium' },

  // Forecasts
  { id: 'nowcast', label: 'GDP Nowcast', icon: '📍', priority: 'medium' },
  { id: 'liquidity', label: 'Liquidity', icon: '💧', priority: 'medium' },
  { id: 'sentiment', label: 'Sentiment', icon: '😊', priority: 'medium' },

  // Strategy
  { id: 'gmo-forecasts', label: 'GMO 7-Year Forecasts', icon: '🔮', priority: 'medium' },
  { id: 'valuation', label: 'Valuation', icon: '💰', priority: 'medium' },
  { id: 'expected-returns', label: 'Expected Returns', icon: '📈', priority: 'high' },
  { id: 'international', label: 'International Macro', icon: '🌍', priority: 'low' },
  { id: 'reflexivity', label: 'Reflexivity Monitor', icon: '🪞', priority: 'low' },
  { id: 'transmission', label: 'Transmission', icon: '📡', priority: 'low' },
  { id: 'factor-decomposition', label: 'Factor Decomp', icon: '🧮', priority: 'low' },
  { id: 'risk-parity', label: 'Risk Parity', icon: '⚖️', priority: 'low' },
  { id: 'momentum-veto', label: 'Momentum Veto', icon: '✋', priority: 'medium' },
  { id: 'horizon-tension', label: 'Horizon Tensions', icon: '⏳', priority: 'medium' },
  { id: 'cta-trend', label: 'CTA Trends', icon: '📊', priority: 'low' },
  { id: 'news-sentiment', label: 'News Sentiment', icon: '📰', priority: 'low' },
  { id: 'trade-ideas', label: 'Trade Ideas', icon: '💡', priority: 'high' },

  // Portfolio
  { id: 'portfolio', label: 'Portfolio Analyser', icon: '💼', priority: 'high' },
  { id: 'equity-research', label: 'Equity Research', icon: '🔍', priority: 'medium' },
  { id: 'data-to-watch', label: 'Data to Watch', icon: '👀', priority: 'low' },
  { id: 'investment-memo', label: 'Investment Memo', icon: '📝', priority: 'low' },
  { id: 'business-layer', label: 'Business Layer', icon: '🏢', priority: 'low' },
  { id: 'economic-calendar', label: 'Economic Calendar', icon: '📅', priority: 'medium' },

  // System
  { id: 'system-health', label: 'System Health', icon: '🔧', priority: 'medium' },
];

export function CommandPalette({
  isOpen,
  onClose,
  onNavigate,
  onExport,
  onRefresh,
  onToggleFullscreen,
  onViewHealth,
  currentRegime = 'Goldilocks',
}: CommandPaletteProps) {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [activeTab, setActiveTab] = useState<'all' | 'favorites' | 'recent'>('all');
  // Favorites start empty each session (no persistent storage in sandboxed environment).
  // Destructure only the getter; a future toggle-star feature can add the setter back.
  const [favorites] = useState<string[]>([]);
  const [recent, setRecent] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  // Add a section to the in-session recent list (capped at 5)
  const addToRecent = useCallback((sectionId: string) => {
    setRecent((prev) => [sectionId, ...prev.filter((id) => id !== sectionId)].slice(0, 5));
  }, []);

  const commands: CommandItem[] = [
    // Favorites (pinned for the session)
    ...favorites
      .filter(id => sections.find(s => s.id === id))
      .map(id => sections.find(s => s.id === id)!)
      .map((section) => ({
        id: `fav-${section.id}`,
        label: section.label,
        category: 'favorite' as const,
        icon: <Star className="w-4 h-4 text-amber" />,
        action: () => {
          addToRecent(section.id);
          onNavigate(section.id);
          onClose();
        },
      })),

    // Recently visited (in-session only)
    ...recent
      .filter(id => sections.find(s => s.id === id))
      .map(id => sections.find(s => s.id === id)!)
      .map((section) => ({
        id: `recent-${section.id}`,
        label: section.label,
        category: 'recent' as const,
        icon: <Clock className="w-4 h-4 text-text-tertiary" />,
        action: () => {
          addToRecent(section.id);
          onNavigate(section.id);
          onClose();
        },
      })),

    // All sections
    ...sections.map((section) => ({
      id: section.id,
      label: section.label,
      category: 'section' as const,
      icon: section.icon ? <span className="text-sm">{section.icon}</span> : null,
      action: () => {
        addToRecent(section.id);
        onNavigate(section.id);
        onClose();
      },
    })),

    // Quick Actions
    {
      id: 'quick-trade-ideas',
      label: 'Generate Trade Ideas',
      shortcut: 'T',
      category: 'action' as const,
      icon: <Zap className="w-4 h-4 text-bloomberg" />,
      action: () => {
        onNavigate('trade-ideas');
        onClose();
      },
    },
    {
      id: 'quick-risk-check',
      label: 'Risk Scenario Check',
      shortcut: '',
      category: 'action' as const,
      icon: <AlertTriangle className="w-4 h-4 text-red" />,
      action: () => {
        onNavigate('risk-analytics');
        onClose();
      },
    },
    {
      id: 'quick-playbook',
      label: 'View Regime Playbook',
      shortcut: '',
      category: 'action' as const,
      icon: <Target className="w-4 h-4 text-amber" />,
      action: () => {
        onNavigate('regime-playbook');
        onClose();
      },
    },
    {
      id: 'quick-morning',
      label: 'Open Morning Brief',
      shortcut: 'M',
      category: 'action' as const,
      icon: <TrendingUp className="w-4 h-4 text-green" />,
      action: () => {
        onNavigate('morning-brief');
        onClose();
      },
    },

    // Standard Actions
    {
      id: 'export',
      label: 'Export PDF Report',
      shortcut: '⌘E',
      category: 'action' as const,
      action: () => {
        onExport?.();
        onClose();
      },
    },
    {
      id: 'refresh',
      label: 'Refresh All Data',
      shortcut: '⌘R',
      category: 'action' as const,
      action: () => {
        onRefresh?.();
        onClose();
      },
    },
    {
      id: 'fullscreen',
      label: 'Toggle Fullscreen',
      shortcut: '⌘F',
      category: 'action' as const,
      action: () => {
        onToggleFullscreen?.();
        onClose();
      },
    },
    {
      id: 'health',
      label: 'View System Health',
      shortcut: '',
      category: 'action' as const,
      action: () => {
        onViewHealth?.();
        onClose();
      },
    },
  ];

  // UPGRADE-7: Filter commands based on query and active tab
  const filteredCommands = commands.filter((cmd) => {
    if (query) return cmd.label.toLowerCase().includes(query.toLowerCase());
    if (activeTab === 'favorites') return cmd.category === 'favorite';
    if (activeTab === 'recent') return cmd.category === 'recent';
    return true;
  });

  const favoriteCommands = filteredCommands.filter((c) => c.category === 'favorite');
  const recentCommands = filteredCommands.filter((c) => c.category === 'recent');
  const sectionCommands = filteredCommands.filter((c) => c.category === 'section');
  const actionCommands = filteredCommands.filter((c) => c.category === 'action');

  // Reset selection when query or tab changes
  useEffect(() => {
    setSelectedIndex(0);
  }, [query, activeTab]);

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
        case 'Tab':
          e.preventDefault();
          // Cycle through tabs
          const tabs: ('all' | 'favorites' | 'recent')[] = ['all', 'favorites', 'recent'];
          const currentIndex = tabs.indexOf(activeTab);
          setActiveTab(tabs[(currentIndex + 1) % tabs.length]);
          break;
      }
    },
    [isOpen, filteredCommands, selectedIndex, onClose, activeTab]
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
        className="w-full max-w-[640px] bg-surface-2 border border-border shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search input + tab bar */}
        <div className="border-b border-border-subtle">
          {/* Search Input */}
          <div className="flex items-center gap-3 px-4 py-3">
            <Search className="w-4 h-4 text-text-tertiary" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Type to search sections, actions..."
              className="flex-1 bg-transparent border-none outline-none text-sm text-text-primary placeholder:text-text-tertiary font-mono"
            />
            {!query && (
              <div className="flex items-center gap-2 text-text-tertiary">
                <span className="text-2xs">{currentRegime}</span>
              </div>
            )}
          </div>

          {/* Tabs */}
          {!query && (
            <div className="flex border-t border-border-subtle">
              {[
                { id: 'all', label: 'All', count: sections.length },
                { id: 'favorites', label: 'Favorites', count: favorites.length },
                { id: 'recent', label: 'Recent', count: recent.length },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as typeof activeTab)}
                  className={cn(
                    'flex-1 px-4 py-2 text-xs font-medium border-b-2 transition-colors',
                    activeTab === tab.id
                      ? 'border-bloomberg text-bloomberg bg-bloomberg/5'
                      : 'border-transparent text-text-tertiary hover:text-text-primary hover:bg-surface-1'
                  )}
                >
                  {tab.label}
                  {tab.count > 0 && (
                    <span className="ml-1.5 text-2xs text-text-tertiary">
                      ({tab.count})
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Command list */}
        <div className="max-h-[400px] overflow-y-auto">
          {/* Favorites */}
          {favoriteCommands.length > 0 && !query && (
            <div>
              <div className="px-4 py-2 text-2xs text-amber uppercase tracking-wider bg-surface-1 flex items-center gap-2">
                <Star className="w-3 h-3" />
                Favorites
              </div>
              <div>
                {favoriteCommands.map((cmd) => {
                  const globalIndex = filteredCommands.indexOf(cmd);
                  const isSelected = globalIndex === selectedIndex;
                  return (
                    <CommandRow
                      key={cmd.id}
                      cmd={cmd}
                      isSelected={isSelected}
                    />
                  );
                })}
              </div>
            </div>
          )}

          {/* Recent */}
          {recentCommands.length > 0 && !query && activeTab !== 'favorites' && (
            <div>
              <div className="px-4 py-2 text-2xs text-text-tertiary uppercase tracking-wider bg-surface-1 border-t border-border-subtle flex items-center gap-2">
                <Clock className="w-3 h-3" />
                Recently Used
              </div>
              <div>
                {recentCommands.map((cmd) => {
                  const globalIndex = filteredCommands.indexOf(cmd);
                  const isSelected = globalIndex === selectedIndex;
                  return (
                    <CommandRow
                      key={cmd.id}
                      cmd={cmd}
                      isSelected={isSelected}
                    />
                  );
                })}
              </div>
            </div>
          )}

          {/* Sections */}
          {sectionCommands.length > 0 && activeTab !== 'favorites' && (
            <div>
              <div className={cn(
                "px-4 py-2 text-2xs text-text-tertiary uppercase tracking-wider bg-surface-1 border-t border-border-subtle",
                recentCommands.length === 0 && favoriteCommands.length === 0 && "border-t-0"
              )}>
                Sections
              </div>
              <div>
                {sectionCommands.slice(0, query ? undefined : 15).map((cmd) => {
                  const globalIndex = filteredCommands.indexOf(cmd);
                  const isSelected = globalIndex === selectedIndex;
                  return (
                    <CommandRow
                      key={cmd.id}
                      cmd={cmd}
                      isSelected={isSelected}
                    />
                  );
                })}
                {!query && sectionCommands.length > 15 && (
                  <div className="px-4 py-2 text-xs text-text-tertiary text-center italic">
                    +{sectionCommands.length - 15} more sections (type to search)
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Actions */}
          {actionCommands.length > 0 && (
            <div>
              <div className="px-4 py-2 text-2xs text-text-tertiary uppercase tracking-wider bg-surface-1 border-t border-border-subtle">
                Quick Actions
              </div>
              <div>
                {actionCommands.map((cmd) => {
                  const globalIndex = filteredCommands.indexOf(cmd);
                  const isSelected = globalIndex === selectedIndex;
                  return (
                    <CommandRow
                      key={cmd.id}
                      cmd={cmd}
                      isSelected={isSelected}
                    />
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

        {/* Footer hints */}
        <div className="flex items-center justify-between px-4 py-2 border-t border-border-subtle bg-surface-1 text-2xs text-text-tertiary">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1">
              <CornerDownLeft className="w-3 h-3" />
              select
            </span>
            <span>↑↓ navigate</span>
            <span>Tab switch</span>
            <span>? help</span>
          </div>
          <span>
            {filteredCommands.length} {query ? 'results' : 'commands'}
          </span>
        </div>
      </div>
    </div>
  );
}

function CommandRow({
  cmd,
  isSelected,
}: {
  cmd: CommandItem;
  isSelected: boolean;
}) {
  return (
    <button
      onClick={cmd.action}
      className={cn(
        'w-full flex items-center gap-3 px-4 py-2 text-left transition-colors',
        isSelected ? 'bg-surface-3 text-bloomberg' : 'text-text-primary hover:bg-surface-3'
      )}
    >
      <span className="text-text-tertiary">↵</span>
      {cmd.icon && (
        <span className="flex-shrink-0 w-5 h-5 flex items-center justify-center">{cmd.icon}</span>
      )}
      <span className="text-sm flex-1">{cmd.label}</span>
      {cmd.shortcut && (
        <kbd className="px-1.5 py-0.5 text-2xs text-text-tertiary font-mono bg-surface-1 border border-border-subtle rounded">
          {cmd.shortcut}
        </kbd>
      )}
    </button>
  );
}
