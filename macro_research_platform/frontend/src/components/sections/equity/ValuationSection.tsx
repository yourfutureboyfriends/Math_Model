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
    // A metric without history has no z-score: keep it null (shown as '—'), not 0σ.
    const z: number | null = typeof m.zScore === 'number' ? m.zScore : null;
    return {
      name: m.name,
      signal: m.signal ?? (z == null ? 'n/a' : z > 1 ? 'expensive' : z < -1 ? 'cheap' : 'fair'),
      currentValue: m.currentValue ?? m.value,
      historicalMean: m.historicalMean,
      zScore: z,
      percentile: typeof m.percentile === 'number' ? m.percentile : undefined,
      interpretation: m.interpretation ?? '',
    };
  });
  // A composite needs at least two scored inputs; with one (only the real yield has
  // history) the "composite" was that single z-score relabelled as equity "Expensive".
  const scored = metrics.filter((m: any) => m.zScore != null);
  const compositeScore: number | null = anyData.compositeScore
    ?? (scored.length >= 2 ? scored.reduce((s: number, m: any) => s + m.zScore, 0) / scored.length : null);
  const regime = anyData.regime ?? (compositeScore == null ? (scored.length === 1 ? 'Single input' : 'N/A')
    : compositeScore > 1 ? 'Expensive' : compositeScore < -1 ? 'Cheap' : 'Fair');
  const num = (v: any, d = 2) => (typeof v === 'number' && isFinite(v) ? v.toFixed(d) : '—');

  const getSignalIcon = (signal: string) => {
    switch (signal.toLowerCase()) {
      case 'cheap':
      case 'bonds cheap':
      case 'attractive':
        return <ArrowDown className="w-3 h-3 text-green" />;
      case 'expensive':
      case 'bonds rich':
      case 'unattractive':
        return <ArrowUp className="w-3 h-3 text-red" />;
      default:
        return <Minus className="w-3 h-3 text-text-tertiary" />;
    }
  };

  const getSignalTag = (signal: string) => {
    switch (signal.toLowerCase()) {
      case 'cheap':
      case 'bonds cheap':
      case 'attractive':
        return 'signal-tag bullish';
      case 'expensive':
      case 'bonds rich':
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
          <span className="section-tag">◆</span>
          <h2 className="section-title">Valuation</h2>
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
              <div className={`text-xl font-mono font-bold text-text-primary`}>
                {compositeScore == null ? '—' : `${compositeScore >= 0 ? '+' : ''}${compositeScore.toFixed(2)}σ`}
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
                  <div className={`font-mono text-xs ${metric.zScore == null ? 'text-text-tertiary' : 'text-text-primary'}`}>
                    {metric.zScore == null ? '—' : `${metric.zScore >= 0 ? '+' : ''}${num(metric.zScore)}σ`}
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
        {data.expectedReturns && Object.keys(data.expectedReturns).length > 0 && (
        <div className="p-3 bg-surface-1 border border-border">
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Expected Returns (Annual)</div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
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
        )}
      </div>
    </div>
  );
}
