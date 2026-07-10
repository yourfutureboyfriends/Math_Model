// UPGRADE-9: Terminal Sidebar — Hedge Fund Workflow Organization
// Optimized navigation for PM daily workflow: Morning → Signals → Trades → Risk → Strategy

import { useState } from 'react';
import { ChevronLeft, ChevronRight, LogOut, Star } from 'lucide-react';
import { Logo } from './Logo';
import { cn } from '@/lib/utils';
import { useAuth } from '@/context/AuthContext';
import { usePinnedSections } from '@/hooks/usePinnedSections';

interface NavItem {
  id: string;
  label: string;
  icon: string;
  permission: string;
  highlight?: boolean;
}

interface NavSection {
  title: string;
  items: NavItem[];
}

// UPGRADE-9: Reorganized navigation for hedge fund workflow
// FIXED (PART 3): Sidebar reorganized per user spec
const navigation: NavSection[] = [
  {
    title: 'MORNING BRIEF',
    items: [
      { id: 'morning-brief', label: 'Morning Brief', icon: '☀', permission: 'master_signal', highlight: true },
    ],
  },
  {
    title: 'OVERVIEW',
    items: [
      { id: 'anomalies', label: 'Anomalies', icon: '◆', permission: 'master_signal' },
      { id: 'master-signal', label: 'Master Ensemble', icon: '◆', permission: 'master_signal', highlight: true },
      { id: 'key-metrics', label: 'Key Metrics', icon: '◆', permission: 'key_metrics' },
      { id: 'regime', label: 'Regime Engine', icon: '◇', permission: 'regime_engine', highlight: true },
      { id: 'regime-playbook', label: 'Regime Playbook', icon: '◇', permission: 'regime_engine', highlight: true },
      { id: 'market-clock', label: 'Market Clock', icon: '◆', permission: 'master_signal' },
    ],
  },
  {
    title: 'SIGNALS',
    items: [
      { id: 'signals', label: 'Signal Interpretation', icon: '◆', permission: 'ml_signals' },
      { id: 'ensemble', label: 'Ensemble', icon: '◆', permission: 'ensemble', highlight: true },
      { id: 'signal-stack', label: 'Signal Stack', icon: '◆', permission: 'signal_stack' },
      { id: 'signal-story', label: 'Signal Storytelling', icon: '◆', permission: 'signal_stack' },
      { id: 'signal-scorecard', label: 'Signal Scorecard', icon: '◆', permission: 'signal_stack', highlight: true },
      { id: 'alt-data', label: 'Alt-Data Positioning', icon: '◈', permission: 'signal_stack', highlight: true },
      { id: 'sector-allocation', label: 'Sector Allocation', icon: '◆', permission: 'sector_allocation' },
      { id: 'factor-rotation', label: 'Factor Rotation', icon: '◆', permission: 'factor_rotation' },
      { id: 'cot-positioning', label: 'COT Positioning', icon: '◆', permission: 'signal_stack' },
      // FIXED (PART 3): Moved from STRATEGY to SIGNALS
      { id: 'model-agreement', label: 'Model Agreement', icon: '◆', permission: 'model_agreement' },
      { id: 'cta-trend', label: 'CTA Trends', icon: '◆', permission: 'cta_trends' },
      { id: 'news-sentiment', label: 'News Sentiment', icon: '◆', permission: 'news_sentiment' },
    ],
  },
  {
    title: 'RISK',
    items: [
      { id: 'risk-indicators', label: 'Risk Indicators', icon: '◆', permission: 'risk_indicators', highlight: true },
      { id: 'risk-analytics', label: 'Risk Analytics', icon: '◆', permission: 'var_drawdown', highlight: true },
      { id: 'factor-exposure', label: 'Factor Exposure', icon: '◆', permission: 'factor_decomp', highlight: true },
      { id: 'var-stress', label: 'VaR & Stress', icon: '◆', permission: 'var_drawdown', highlight: true },
      { id: 'debt-cycle', label: 'Debt Cycle', icon: '◆', permission: 'debt_cycle' },
      { id: 'advanced', label: 'Advanced Indicators', icon: '◆', permission: 'advanced_indicators' },
      // FIXED (PART 3): Moved from STRATEGY to RISK
      { id: 'correlation', label: 'Correlation Regime', icon: '◆', permission: 'correlation' },
      { id: 'correlation-matrix', label: 'Correlation Matrix', icon: '◆', permission: 'correlation' },
      { id: 'factor-decomposition', label: 'Factor Decomposition', icon: '◆', permission: 'factor_decomp' },
      { id: 'risk-parity', label: 'Risk Parity', icon: '◆', permission: 'risk_parity' },
      { id: 'horizon-tension', label: 'Horizon Tensions', icon: '◆', permission: 'horizon_tensions', highlight: true },
    ],
  },
  {
    title: 'FORECASTS',
    items: [
      { id: 'nowcast', label: 'GDP Nowcast', icon: '◆', permission: 'gdp_nowcast' },
      { id: 'liquidity', label: 'Liquidity Conditions', icon: '◆', permission: 'liquidity' },
      { id: 'sentiment', label: 'Sentiment', icon: '◆', permission: 'sentiment' },
      { id: 'yield-curve', label: 'Yield Curve', icon: '◆', permission: 'master_signal' },
      // FIXED (PART 3): Moved from STRATEGY to FORECASTS
      { id: 'valuation', label: 'Valuation Filter', icon: '◆', permission: 'valuation' },
    ],
  },
  {
    title: 'STRATEGY',
    items: [
      { id: 'expected-returns', label: 'Expected Returns', icon: '◆', permission: 'expected_returns', highlight: true },
      { id: 'gmo-forecasts', label: 'GMO 7-Year', icon: '◆', permission: 'gmo_7year' },
      { id: 'fx-monitor', label: 'FX Monitor', icon: '◆', permission: 'master_signal' },
      { id: 'commodities-dashboard', label: 'Commodities', icon: '◆', permission: 'master_signal' },
      { id: 'fixed-income-dashboard', label: 'Fixed Income', icon: '◆', permission: 'master_signal' },
      { id: 'international', label: 'International Macro', icon: '◆', permission: 'international_macro' },
      { id: 'reflexivity', label: 'Reflexivity', icon: '◆', permission: 'reflexivity' },
      { id: 'transmission', label: 'Transmission', icon: '◆', permission: 'transmission' },
      { id: 'regime-transition', label: 'Regime Transition', icon: '◆', permission: 'regime_transition' },
      { id: 'regime-outlook', label: 'Regime Outlook', icon: '◆', permission: 'regime_transition' },
      { id: 'momentum-veto', label: 'Momentum Veto', icon: '◆', permission: 'momentum_veto' },
    ],
  },
  {
    title: 'RESEARCH',
    items: [
      { id: 'equity-research', label: 'Equity Research', icon: '◆', permission: 'equity_research', highlight: true },
    ],
  },
  {
    title: 'PORTFOLIO',
    items: [
      { id: 'portfolio-positions', label: 'Positions', icon: '▦', permission: 'portfolio_fit', highlight: true },
      { id: 'trade-workflow', label: 'Trade Workflow', icon: '⚗', permission: 'trade_ideas', highlight: true },
      { id: 'trade-ideas', label: 'Trade Ideas', icon: '◆', permission: 'trade_ideas', highlight: true },
      { id: 'trade-recommendations', label: 'Trade Recommendations', icon: '◆', permission: 'trade_recommendations', highlight: true },
      { id: 'scenario-analysis', label: 'Scenario Analysis', icon: '◆', permission: 'master_signal' },
      { id: 'portfolio', label: 'Model Portfolio', icon: '◆', permission: 'portfolio_fit', highlight: true },
      // FIXED (PART 3): Moved from RESEARCH to PORTFOLIO
      { id: 'performance-attribution', label: 'Performance Attribution', icon: '◆', permission: 'performance_tracking', highlight: true },
      { id: 'data-to-watch', label: 'Data to Watch', icon: '◆', permission: 'investment_memo' },
      { id: 'investment-memo', label: 'Investment Memo', icon: '◆', permission: 'investment_memo' },
      { id: 'business-layer', label: 'Business Layer', icon: '◆', permission: 'business_layer' },
      { id: 'economic-calendar', label: 'Economic Calendar', icon: '◆', permission: 'economic_calendar' },
      { id: 'event-vol', label: 'Event Volatility', icon: '◆', permission: 'economic_calendar' },
    ],
  },
  {
    title: 'SYSTEM',
    items: [
      { id: 'system-health', label: 'System Health', icon: '◆', permission: 'system_health' },
      { id: 'data-providers', label: 'Data Providers', icon: '◆', permission: 'system_health' },
      { id: 'system-audit', label: 'Audit & Compliance', icon: '◆', permission: 'system_health', highlight: true },
      { id: 'data-explorer', label: 'Data Explorer', icon: '◆', permission: 'system_health' },
    ],
  },
];

interface SidebarProps {
  activeSection?: string;
  onNavigate?: (section: string) => void;
  currentRegime?: string;
  collapsed?: boolean;
  onCollapse?: () => void;
}

export function Sidebar({ activeSection = 'master-signal', onNavigate, currentRegime, collapsed: externalCollapsed, onCollapse }: SidebarProps) {
  const [internalCollapsed, setInternalCollapsed] = useState(false);
  const { user, logout } = useAuth();

  // Use external state if provided, otherwise internal
  const collapsed = externalCollapsed ?? internalCollapsed;
  const handleCollapse = () => {
    if (onCollapse) {
      onCollapse();
    } else {
      setInternalCollapsed(!internalCollapsed);
    }
  };

  // FIXED: Navigation always renders — unconditional, no permission filtering
  // All users see all navigation items; permission-based feature hiding is deprecated
  const filteredNavigation = navigation;

  // Per-user pinned panels for one-click access.
  const pinKey = user?.username || user?.display_name || 'default';
  const { pinned, toggle: togglePin, isPinned } = usePinnedSections(pinKey);
  const itemById: Record<string, NavItem> = Object.fromEntries(
    navigation.flatMap((s) => s.items).map((i) => [i.id, i])
  );
  const pinnedItems = pinned.map((id) => itemById[id]).filter(Boolean) as NavItem[];

  const renderNavItem = (item: NavItem) => {
    const isActive = activeSection === item.id;
    const pinnedNow = isPinned(item.id);
    return (
      <div key={item.id} className="group relative flex items-center">
        <button
          onClick={() => onNavigate?.(item.id)}
          className={cn(
            'flex-1 h-7 flex items-center transition-all duration-120 min-w-0',
            collapsed ? 'justify-center px-0' : 'px-4',
            isActive
              ? 'bg-bloomberg-muted text-bloomberg border-l-2 border-bloomberg'
              : item.highlight
                ? 'text-amber hover:bg-amber-dim hover:text-amber border-l-2 border-transparent hover:border-amber'
                : 'text-text-secondary hover:bg-surface-3 hover:text-text-primary'
          )}
        >
          <span className={cn('font-mono text-xs',
            isActive ? 'text-bloomberg' : item.highlight ? 'text-amber' : 'text-text-secondary')}>
            {item.icon}
          </span>
          {!collapsed && (
            <span className={cn('ml-2 text-xs truncate', item.highlight && !isActive && 'font-medium')}>
              {item.label}
            </span>
          )}
        </button>
        {!collapsed && (
          <button
            onClick={(e) => { e.stopPropagation(); togglePin(item.id); }}
            title={pinnedNow ? 'Unpin panel' : 'Pin panel'}
            className={cn(
              'absolute right-1.5 p-1 transition-opacity',
              pinnedNow
                ? 'opacity-100 text-amber'
                : 'opacity-0 group-hover:opacity-100 text-text-tertiary hover:text-amber'
            )}
          >
            <Star className="w-3 h-3" fill={pinnedNow ? 'currentColor' : 'none'} />
          </button>
        )}
      </div>
    );
  };

  const handleLogout = async () => {
    await logout();
  };

  return (
    <div
      className={cn(
        'h-full flex flex-col bg-surface-1',
        collapsed ? 'w-[48px] min-w-[48px]' : 'w-[224px] min-w-[224px]'
      )}
      style={{ display: 'flex', flexDirection: 'column' }}
    >
      {/* Platform ID */}
      <div className="h-10 flex items-center px-3 border-b border-border-subtle">
        <Logo currentRegime={currentRegime} />
        {!collapsed && (
          <>
            <span className="ml-2 font-mono text-sm text-text-secondary">MACRO OS</span>
            <span className="ml-1.5 text-2xs text-text-tertiary">v8.0</span>
          </>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-2">
        {/* Pinned panels — user's most-watched, one-click access */}
        {pinnedItems.length > 0 && (
          <div className="mb-1">
            {!collapsed && (
              <div className="px-4 py-1.5 text-2xs text-amber font-medium tracking-wider flex items-center gap-1">
                <Star className="w-3 h-3" fill="currentColor" /> PINNED
              </div>
            )}
            <div className="space-y-px">
              {pinnedItems.map(renderNavItem)}
            </div>
            <div className="mx-4 my-1.5 border-t border-border-subtle" />
          </div>
        )}

        {filteredNavigation.map((section) => (
          <div key={section.title} className="mb-1">
            {!collapsed && (
              <div className="px-4 py-1.5 text-2xs text-text-tertiary font-medium tracking-wider">
                {section.title}
              </div>
            )}
            <div className="space-y-px">
              {section.items.map(renderNavItem)}
            </div>
          </div>
        ))}
      </nav>

      {/* Role Badge & Logout */}
      {!collapsed && user && (
        <div className="px-3 py-2 border-t border-border-subtle">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-bloomberg" />
              <span className="text-xs text-text-secondary">
                {user.role.toUpperCase()} — {user.display_name}
              </span>
            </div>
            <button
              onClick={handleLogout}
              className="p-1 text-text-tertiary hover:text-text-primary transition-colors"
              title="Logout"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* Collapse button */}
      <button
        onClick={handleCollapse}
        className="h-8 flex items-center justify-center border-t border-border-subtle text-text-tertiary hover:text-text-primary hover:bg-surface-3 transition-colors"
      >
        {collapsed ? (
          <ChevronRight className="w-4 h-4" />
        ) : (
          <div className="flex items-center gap-1">
            <ChevronLeft className="w-4 h-4" />
            <span className="text-2xs">Collapse</span>
          </div>
        )}
      </button>
    </div>
  );
}
