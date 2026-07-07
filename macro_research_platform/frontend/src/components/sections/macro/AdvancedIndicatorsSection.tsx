// Phase 8 — Advanced Indicators Section (Redesigned)
// 2x2 compact grid, 120px card height max

import { cn } from '@/lib/utils';
import { ComputedTag } from '@/components/ui/ComputedTag';
import type { AdvancedIndicatorsData } from '@/types';
import { useMacroStore } from '@/store/macroStore';

interface AdvancedIndicatorsSectionProps {
  data?: AdvancedIndicatorsData;
}

export function AdvancedIndicatorsSection({ data }: AdvancedIndicatorsSectionProps) {
  const _fullDash = useMacroStore((s) => s.fullDashboard);
  if (!data) data = (_fullDash as any)?.["advancedIndicators"] as any;

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

  // Backend sub-objects use {value, signal, ...} (and lei/riskParity have their own
  // shapes); normalize each to the {name, status, value, trend, description} this grid
  // renders, skipping any that are absent, so it shows real values instead of crashing.
  const anyData = data as any;
  const rawIndicators: Array<[string, any]> = [
    ['Sahm Rule', anyData.sahmRule],
    ['Credit Impulse', anyData.creditImpulse],
    ['LEI Composite', anyData.leiComposite ?? anyData.lei],
    ['Risk Parity', anyData.riskParity],
  ];
  const indicators = rawIndicators
    .filter(([, v]) => v)
    .map(([name, v]) => {
      const status = v.status ?? v.signal ?? v.regime ?? 'Neutral';
      let value: any = v.value;
      let description: string = v.description ?? '';
      if (name === 'Risk Parity' && v.allocations) {
        const a = v.allocations;
        value = `S${Math.round((a.stocks ?? 0) * 100)}/B${Math.round((a.bonds ?? 0) * 100)}/C${Math.round((a.commodities ?? 0) * 100)}`;
        description = description || `Regime: ${v.regime ?? '—'}`;
      }
      const trend = v.trend ?? (typeof v.change === 'number'
        ? (v.change > 0 ? 'improving' : v.change < 0 ? 'deteriorating' : 'stable') : 'stable');
      return { key: name, data: { name, status, value: value ?? '—', trend, description } };
    });

  return (
    <div id="advanced" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">15</span>
          <h2 className="section-title">Advanced Indicators</h2>
        </div>
        <ComputedTag section="advancedIndicators" />
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
              <span className={getSignalTag(String(indicator.status))}>
                {String(indicator.status).toUpperCase()}
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
