// Phase 8 — Advanced Indicators Section (Redesigned)
// 2x2 compact grid, 120px card height max

import { cn } from '@/lib/utils';
import type { AdvancedIndicatorsData } from '@/types';

interface AdvancedIndicatorsSectionProps {
  data?: AdvancedIndicatorsData;
}

export function AdvancedIndicatorsSection({ data }: AdvancedIndicatorsSectionProps) {
  if (!data) return null;

  const getTrendSymbol = (trend: string) => {
    switch (trend) {
      case 'improving':
      case 'steepening':
        return '↑';
      case 'deteriorating':
      case 'flattening':
        return '↓';
      default:
        return '—';
    }
  };

  const getTrendColor = (trend: string) => {
    switch (trend) {
      case 'improving':
      case 'steepening':
        return 'text-green';
      case 'deteriorating':
      case 'flattening':
        return 'text-red';
      default:
        return 'text-text-tertiary';
    }
  };

  const getSignalTag = (status: string) => {
    switch (status.toLowerCase()) {
      case 'normal':
      case 'expanding':
        return 'signal-tag bullish';
      case 'inverted':
      case 'contracting':
        return 'signal-tag bearish';
      default:
        return 'signal-tag neutral';
    }
  };

  const indicators = [
    { key: 'sahmRule', data: data.sahmRule },
    { key: 'creditImpulse', data: data.creditImpulse },
    { key: 'leiComposite', data: data.leiComposite },
    { key: 'riskParity', data: data.riskParity },
  ];

  return (
    <div id="advanced" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">15</span>
          <h2 className="section-title">Advanced Indicators</h2>
        </div>
      </div>

      {/* 2x2 Grid */}
      <div className="grid grid-cols-2 gap-3">
        {indicators.map(({ key, data: indicator }) => (
          <div
            key={key}
            className="p-3 bg-surface-1 border border-border"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-text-primary">
                {indicator.name}
              </span>
              <span className={getSignalTag(indicator.status)}>
                {indicator.status.toUpperCase()}
              </span>
            </div>

            <div className="flex items-baseline gap-2 mb-1">
              <span className="text-lg font-mono font-bold text-text-primary">
                {indicator.value}
              </span>
              <span className={cn('text-sm', getTrendColor(indicator.trend))}>
                {getTrendSymbol(indicator.trend)}
              </span>
            </div>

            <p className="text-2xs text-text-secondary leading-relaxed">
              {indicator.description}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
