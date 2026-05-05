// Phase 8 — Regime Classification Section (Redesigned)
// Dense panel with current regime, factor impacts, and history

import { cn } from '@/lib/utils';
import type { RegimeData } from '@/types';

interface RegimeSectionProps {
  data?: RegimeData;
}

export function RegimeSection({ data }: RegimeSectionProps) {
  if (!data) return null;

  const getRegimeColor = (regime: string) => {
    const normalized = regime.toLowerCase();
    if (normalized.includes('goldilocks') || normalized.includes('risk-on')) return 'text-green';
    if (normalized.includes('reflation') || normalized.includes('recovery')) return 'text-blue';
    if (normalized.includes('slowdown')) return 'text-amber';
    if (normalized.includes('stagflation') || normalized.includes('risk-off')) return 'text-red';
    return 'text-text-primary';
  };

  const getRegimeBg = (regime: string) => {
    const normalized = regime.toLowerCase();
    if (normalized.includes('goldilocks') || normalized.includes('risk-on')) return 'bg-green-dim border-green';
    if (normalized.includes('reflation') || normalized.includes('recovery')) return 'bg-blue-dim border-blue';
    if (normalized.includes('slowdown')) return 'bg-amber-dim border-amber';
    if (normalized.includes('stagflation') || normalized.includes('risk-off')) return 'bg-red-dim border-red';
    return 'bg-surface-2 border-border';
  };

  const getConfidenceBadge = (confidence: string) => {
    switch (confidence.toLowerCase()) {
      case 'high':
        return 'signal-tag bullish';
      case 'medium':
        return 'signal-tag warning';
      case 'low':
        return 'signal-tag bearish';
      default:
        return 'signal-tag neutral';
    }
  };


  return (
    <div id="regime" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">03</span>
          <h2 className="section-title">Regime Classification</h2>
          <span className="section-meta">{data.current.toUpperCase()} · {data.confidence.toUpperCase()} CONFIDENCE</span>
        </div>
      </div>

      <div className="space-y-3">
        {/* Current Regime Card */}
        <div className={cn('p-3 border', getRegimeBg(data.current))}>
          <div className="flex items-center justify-between mb-2">
            <div>
              <div className="text-2xs text-text-secondary uppercase tracking-wider mb-0.5">
                Current Regime
              </div>
              <div className={cn('text-lg font-mono font-bold', getRegimeColor(data.current))}>
                {data.current}
              </div>
            </div>
            <div className="text-right">
              <div className="text-2xs text-text-secondary uppercase tracking-wider mb-0.5">
                Duration
              </div>
              <div className="text-sm font-mono text-text-primary">
                {data.duration} months
              </div>
            </div>
          </div>

          {/* Confidence Score Bar */}
          <div className="mt-3">
            <div className="flex items-center justify-between text-2xs mb-1">
              <span className="text-text-tertiary">Confidence</span>
              <span className="font-mono text-text-primary">{(data.confidenceScore * 100).toFixed(0)}%</span>
            </div>
            <div className="h-1 bg-surface-4">
              <div
                className="h-full bg-accent transition-all duration-500"
                style={{ width: `${data.confidenceScore * 100}%` }}
              />
            </div>
          </div>
        </div>

        {/* Factor Impacts Table */}
        {data.interpretations && data.interpretations.length > 0 && (
          <div className="border border-border bg-surface-1">
            <div className="px-3 py-2 border-b border-border-subtle bg-surface-2">
              <span className="text-2xs text-text-tertiary uppercase tracking-wider">Factor Impacts</span>
            </div>
            <table className="w-full">
              <thead>
                <tr className="border-b border-border-subtle">
                  <th className="text-left py-1.5 px-3 text-2xs text-text-tertiary uppercase font-medium">Factor</th>
                  <th className="text-left py-1.5 px-3 text-2xs text-text-tertiary uppercase font-medium">Impact</th>
                  <th className="text-right py-1.5 px-3 text-2xs text-text-tertiary uppercase font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {data.interpretations.map((interp) => (
                  <tr key={interp.factor} className="border-b border-border-subtle last:border-0">
                    <td className="py-2 px-3 text-sm text-text-primary">{interp.factor}</td>
                    <td className="py-2 px-3 text-sm text-text-secondary">{interp.impact}</td>
                    <td className="py-2 px-3 text-right">
                      <span className={getConfidenceBadge(interp.color === 'success' ? 'High' : interp.color === 'warning' ? 'Medium' : 'Low')}>
                        {interp.color === 'success' ? 'UP' : interp.color === 'danger' ? 'DOWN' : 'NEUTRAL'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Regime History */}
        {data.history && data.history.length > 0 && (
          <div className="p-3 border border-border bg-surface-1">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">History</div>
            <div className="flex flex-wrap gap-1">
              {data.history.slice(-6).map((h, idx) => {
                const regimeColor = getRegimeColor(h.regime);
                return (
                  <div
                    key={idx}
                    className={cn(
                      'px-2 py-1 text-2xs font-mono',
                      regimeColor === 'text-green' ? 'text-green bg-green-dim' :
                      regimeColor === 'text-amber' ? 'text-amber bg-amber-dim' :
                      regimeColor === 'text-red' ? 'text-red bg-red-dim' :
                      regimeColor === 'text-blue' ? 'text-blue bg-blue-dim' :
                      'text-text-secondary bg-surface-2'
                    )}
                  >
                    {h.date}: {h.regime.slice(0, 4)}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
