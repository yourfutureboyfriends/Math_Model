// Phase 8 Terminal Sidebar
// 220px fixed, collapsible to 48px
// FIXED: Order matches App.tsx dashboard flow exactly

import { useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Logo } from './Logo';
import { cn } from '@/lib/utils';

interface NavItem {
  id: string;
  label: string;
  icon: string;
}

interface NavSection {
  title: string;
  items: NavItem[];
}

// FIXED: Navigation order matches App.tsx section order exactly
const navigation: NavSection[] = [
  {
    title: 'OVERVIEW',
    items: [
      { id: 'master-signal', label: 'Master Signal', icon: '◉' },
      { id: 'key-metrics', label: 'Key Metrics', icon: '◆' },
      { id: 'regime', label: 'Regime Engine', icon: '◇' },
    ],
  },
  {
    title: 'SIGNALS',
    items: [
      { id: 'ml-signals', label: 'ML Signals', icon: '◆' },
      { id: 'ensemble', label: 'Ensemble', icon: '◆' },
      { id: 'signal-stack', label: 'Signal Stack', icon: '◆' },
      { id: 'sector-allocation', label: 'Sector Allocation', icon: '◆' },
      { id: 'factor-rotation', label: 'Factor Rotation', icon: '◆' },
    ],
  },
  {
    title: 'RISK',
    items: [
      { id: 'risk-indicators', label: 'Risk Indicators', icon: '◆' },
      { id: 'debt-cycle', label: 'Debt Cycle', icon: '◆' },
      { id: 'advanced', label: 'Advanced Indicators', icon: '◆' },
    ],
  },
  {
    title: 'FORECASTS',
    items: [
      { id: 'nowcast', label: 'GDP Nowcast', icon: '◆' },
      { id: 'liquidity', label: 'Liquidity', icon: '◆' },
      { id: 'sentiment', label: 'Sentiment', icon: '◆' },
    ],
  },
  {
    title: 'STRATEGY',
    items: [
      { id: 'gmo', label: 'GMO 7-Year', icon: '◆' },
      { id: 'valuation', label: 'Valuation', icon: '◆' },
      { id: 'expected-returns', label: 'Expected Returns', icon: '◆' },
      { id: 'international-macro', label: 'International Macro', icon: '◆' },
      { id: 'reflexivity', label: 'Reflexivity', icon: '◆' },
      { id: 'transmission', label: 'Transmission', icon: '◆' },
      { id: 'regime-transition', label: 'Regime Transition', icon: '◆' },
      { id: 'correlation-regime', label: 'Correlation Regime', icon: '◆' },
      { id: 'factor-decomp', label: 'Factor Decomp', icon: '◆' },
      { id: 'risk-parity', label: 'Risk Parity', icon: '◆' },
      { id: 'momentum-veto', label: 'Momentum Veto', icon: '◆' },
      { id: 'horizon', label: 'Horizon Tensions', icon: '◆' },
      { id: 'model-agreement', label: 'Model Agreement', icon: '◆' },
      { id: 'cta-trends', label: 'CTA Trends', icon: '◆' },
      { id: 'news-sentiment', label: 'News Sentiment', icon: '◆' },
    ],
  },
  {
    title: 'PORTFOLIO',
    items: [
      { id: 'portfolio-fit', label: 'Portfolio Fit', icon: '◆' },
      { id: 'data-to-watch', label: 'Data to Watch', icon: '◆' },
      { id: 'investment-memo', label: 'Investment Memo', icon: '◆' },
      { id: 'business-layer', label: 'Business Layer', icon: '◆' },
    ],
  },
  {
    title: 'SYSTEM',
    items: [
      { id: 'system-health', label: 'System Health', icon: '◆' },
    ],
  },
];

interface SidebarProps {
  activeSection?: string;
  onNavigate?: (section: string) => void;
  currentRegime?: string;
}

export function Sidebar({ activeSection = 'master-signal', onNavigate, currentRegime }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={cn(
        'fixed left-0 top-12 bottom-0 bg-surface-1 border-r border-border z-40',
        'flex flex-col transition-all duration-200',
        collapsed ? 'w-12' : 'w-56'
      )}
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
        {navigation.map((section) => (
          <div key={section.title} className="mb-1">
            {!collapsed && (
              <div className="px-4 py-1.5 text-2xs text-text-tertiary font-medium tracking-wider">
                {section.title}
              </div>
            )}
            <div className="space-y-px">
              {section.items.map((item) => {
                const isActive = activeSection === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => onNavigate?.(item.id)}
                    className={cn(
                      'w-full h-7 flex items-center transition-all duration-120',
                      collapsed ? 'justify-center px-0' : 'px-4',
                      isActive
                        ? 'bg-accent-muted text-accent border-l-2 border-accent'
                        : 'text-text-secondary hover:bg-surface-3 hover:text-text-primary'
                    )}
                  >
                    <span className={cn(
                      'font-mono text-xs',
                      isActive ? 'text-accent' : 'text-text-secondary'
                    )}>
                      {item.icon}
                    </span>
                    {!collapsed && (
                      <span className="ml-2 text-xs">{item.label}</span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Collapse button */}
      <button
        onClick={() => setCollapsed(!collapsed)}
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
    </aside>
  );
}
