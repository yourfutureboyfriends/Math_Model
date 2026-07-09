// Phase 8 — Valuation Filter Section (Redesigned)
// Valuation metrics with terminal aesthetic

import { Scale, ArrowUp, ArrowDown, Minus } from 'lucide-react';
import { ComputedTag } from '@/components/ui/ComputedTag';
import type { ValuationFilterData } from '@/types';
import { useMacroStore } from '@/store/macroStore';

interface ValuationSectionProps {
  data?: ValuationFilterData;
}

export function ValuationSection({ data }: ValuationSectionProps) {
  const _fullDash = useMacroStore((s) => s.fullDashboard);
  if (!data) data = (_fullDash as any)?.["valuation"] as any;

  if (!data) return null;

  // Backend payload is {metrics:[{name,value,zScore,percentile}], summary}; derive the
  // composite/regime/signal fields this view expects so it renders the real valuation
  // metrics instead of crashing on data.regime / data.compositeScore.
  const anyData = data as any;
  const metrics = (anyData.metrics ?? []).map((m: any) => {
    const z = typeof m.zScore === 'number' ? m.zScore : 0;
    return {
      name: m.name,
      signal: m.signal ?? (z > 1 ? 'expensive' : z < -1 ? 'cheap' : 'fair'),
      currentValue: m.currentValue ?? m.value,
      historicalMean: m.historicalMean,
      zScore: z,
      percentile: typeof m.percentile === 'number' ? m.percentile : undefined,
      interpretation: m.interpretation ?? '',
    };
  });
  const compositeScore = anyData.compositeScore
    ?? (metrics.length ? metrics.reduce((s: number, m: any) => s + m.zScore, 0) / metrics.length : 0);
  const regime = anyData.regime ?? (compositeScore > 1 ? 'Expensive' : compositeScore < -1 ? 'Cheap' : 'Fair');
  const num = (v: any, d = 2) => (typeof v === 'number' && isFinite(v) ? v.toFixed(d) : '—');

  const getSignalIcon = (signal: string) => {
    switch (signal.toLowerCase()) {
      case 'cheap':
      case 'attractive':
        return <ArrowDown className="w-3 h-3 text-green" />;
      case 'expensive':
      case 'unattractive':
        return <ArrowUp className="w-3 h-3 text-red" />;
      default:
        return <Minus className="w-3 h-3 text-text-tertiary" />;
    }
  };

  const getSignalTag = (signal: string) => {
    switch (signal.toLowerCase()) {
      case 'cheap':
      case 'attractive':
        return 'signal-tag bullish';
      case 'expensive':
      case 'unattractive':
        return 'signal-tag bearish';
      default:
        return 'signal-tag neutral';
    }
  };

  const getPercentileColor = (percentile: number) => {
    if (percentile > 75) return 'bg-red';
    if (percentile > 50) return 'bg-amber';
    if (percentile > 25) return 'bg-bloomberg';
    return 'bg-green';
  };

  return (
    <div id="valuation" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">20</span>
          <h2 className="section-title">Valuation Filter</h2>
          <span className="section-meta">{String(regime).toUpperCase()}</span>
        </div>
        <ComputedTag section="valuation" />
      </div>

      <div className="space-y-3">
        {/* Composite Score Header */}
        <div className="flex items-center justify-between p-3 bg-surface-1 border border-border">
          <div className="flex items-center gap-2">
            <Scale className="w-3 h-3 text-text-secondary" />
            <div>
              <div className="text-2xs text-text-tertiary">Composite Z-Score</div>
              <div className={`text-xl font-mono font-bold ${compositeScore > 0 ? 'text-green' : compositeScore < 0 ? 'text-red' : 'text-text-secondary'}`}>
                {compositeScore >= 0 ? '+' : ''}{Number(compositeScore).toFixed(2)}σ
              </div>
            </div>
          </div>
          <span className={getSignalTag(regime)}>
            {regime}
          </span>
        </div>

        {/* Metrics */}
        <div className="space-y-2">
          {metrics.map((metric: any) => (
            <div key={metric.name} className="p-2 bg-surface-1 border border-border">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-text-primary">{metric.name}</span>
                <div className="flex items-center gap-1">
                  {getSignalIcon(metric.signal)}
                  <span className={getSignalTag(metric.signal)}>{metric.signal}</span>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2 mb-1">
                <div>
                  <div className="text-2xs text-text-tertiary">Current</div>
                  <div className="font-mono text-xs text-text-primary">{num(metric.currentValue)}</div>
                </div>
                <div>
                  <div className="text-2xs text-text-tertiary">Mean</div>
                  <div className="font-mono text-xs text-text-secondary">{num(metric.historicalMean)}</div>
                </div>
                <div>
                  <div className="text-2xs text-text-tertiary">Z-Score</div>
                  <div className={`font-mono text-xs ${metric.zScore > 0 ? 'text-green' : metric.zScore < 0 ? 'text-red' : 'text-text-tertiary'}`}>
                    {metric.zScore >= 0 ? '+' : ''}{num(metric.zScore)}σ
                  </div>
                </div>
              </div>

              {typeof metric.percentile === 'number' && (
                <div className="flex items-center gap-2">
                  <span className="text-2xs text-text-tertiary w-12">Pct</span>
                  <div className="flex-1 h-1 bg-surface-4">
                    <div className={`h-full ${getPercentileColor(metric.percentile)}`} style={{ width: `${metric.percentile}%` }} />
                  </div>
                  <span className="text-2xs font-mono text-text-secondary w-8 text-right">{metric.percentile.toFixed(0)}%</span>
                </div>
              )}

              <p className="text-2xs text-text-secondary mt-1">{metric.interpretation}</p>
            </div>
          ))}
        </div>

        {/* Expected Returns */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Expected Returns (Annual)</div>
          <div className="grid grid-cols-3 gap-2">
            {Object.entries(data.expectedReturns ?? {}).map(([asset, ret]) => (
              <div key={asset} className="text-center p-2 bg-surface-2">
                <div className="text-2xs text-text-tertiary capitalize">{asset}</div>
                <div className={`font-mono text-sm font-medium ${ret != null && ret >= 5 ? 'text-green' : ret != null && ret >= 3 ? 'text-text-primary' : 'text-amber'}`}>
                  {ret != null ? `${ret.toFixed(1)}%` : '—'}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
