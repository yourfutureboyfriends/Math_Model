// Phase 8 — Debt Cycle Monitor Section (Redesigned)
// Dalio/Bridgewater debt cycle framework with terminal aesthetic

import { cn } from '@/lib/utils';
import { TrendingUp, TrendingDown, Minus, Clock, History } from 'lucide-react';
import type { DebtCycleData, CyclePosition } from '@/types';

interface DebtCycleSectionProps {
  data?: DebtCycleData;
}

export function DebtCycleSection({ data }: DebtCycleSectionProps) {
  if (!data) return null;

  const cyclePositions: CyclePosition[] = ['Early Expansion', 'Mid Cycle', 'Late Cycle', 'Deleveraging'];
  const currentIndex = cyclePositions.indexOf(data.cyclePosition);

  const cycleColors: Record<CyclePosition, string> = {
    'Early Expansion': 'text-green',
    'Mid Cycle': 'text-blue',
    'Late Cycle': 'text-amber',
    'Deleveraging': 'text-red',
  };

  const getSeverityTag = (severity: string) => {
    switch (severity) {
      case 'mild':
        return 'signal-tag bullish';
      case 'moderate':
        return 'signal-tag warning';
      case 'severe':
        return 'signal-tag bearish';
      default:
        return 'signal-tag neutral';
    }
  };

  const getSignalIcon = (signal: string) => {
    switch (signal) {
      case 'expansion':
        return <TrendingUp className="w-3 h-3 text-green" />;
      case 'contraction':
        return <TrendingDown className="w-3 h-3 text-red" />;
      default:
        return <Minus className="w-3 h-3 text-text-tertiary" />;
    }
  };

  const indicatorsList = [
    { key: 'Real Rate', ...data.indicators.realRate },
    { key: 'Debt/GDP', ...data.indicators.debtGDP },
    { key: 'Debt Service', ...data.indicators.debtServiceRatio },
    { key: 'Credit Impulse', ...data.indicators.creditImpulse },
    { key: 'M2 Growth', ...data.indicators.m2Growth },
  ];

  return (
    <div id="debt-cycle" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">10</span>
          <h2 className="section-title">Debt Cycle Monitor</h2>
          <span className={cn('section-meta', cycleColors[data.cyclePosition])}>
            {data.cyclePosition.toUpperCase()}
          </span>
        </div>
      </div>

      <div className="space-y-3">
        {/* Cycle Position Header */}
        <div className="flex items-center justify-between p-3 bg-surface-1 border border-border">
          <div>
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-0.5">
              Cycle Position
            </div>
            <div className={cn('text-xl font-mono font-bold', cycleColors[data.cyclePosition])}>
              {data.cyclePosition}
            </div>
          </div>
          <span className={getSeverityTag(data.severity)}>
            {data.severity.toUpperCase()}
          </span>
        </div>

        {/* Cycle Progress */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="flex items-center gap-2 mb-2">
            <Clock className="w-3 h-3 text-text-secondary" />
            <span className="text-xs font-medium text-text-primary">Cycle Progression</span>
          </div>
          <div className="relative">
            <div className="flex gap-px h-1">
              {cyclePositions.map((pos, idx) => {
                const isActive = idx <= currentIndex;
                const isCurrent = idx === currentIndex;
                return (
                  <div
                    key={pos}
                    className={cn(
                      'flex-1',
                      isCurrent
                        ? 'bg-accent'
                        : isActive
                        ? pos === 'Early Expansion'
                          ? 'bg-green'
                          : pos === 'Mid Cycle'
                          ? 'bg-blue'
                          : pos === 'Late Cycle'
                          ? 'bg-amber'
                          : 'bg-red'
                        : 'bg-surface-4'
                    )}
                  />
                );
              })}
            </div>
            <div className="flex justify-between mt-1 text-2xs text-text-tertiary">
              {cyclePositions.map((pos) => (
                <span
                  key={pos}
                  className={cn(pos === data.cyclePosition && cycleColors[pos])}
                >
                  {pos.replace(' ', '\n')}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Cycle Score */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-medium text-text-primary">Cycle Score</span>
            <span
              className={cn(
                'font-mono text-base font-bold',
                data.cycleScore > 0 ? 'text-green' : data.cycleScore < 0 ? 'text-red' : 'text-text-secondary'
              )}
            >
              {data.cycleScore > 0 ? '+' : ''}
              {data.cycleScore}
            </span>
          </div>
          <div className="h-1 bg-surface-4 relative">
            <div
              className="absolute top-0 bottom-0 bg-accent"
              style={{ width: `${((data.cycleScore + 5) / 10) * 100}%` }}
            />
            <div className="absolute top-0 bottom-0 left-1/2 w-px bg-text-tertiary/30" />
          </div>
          <div className="flex justify-between text-2xs text-text-tertiary mt-1">
            <span>Deleveraging</span>
            <span>Expansion</span>
          </div>
        </div>

        {/* Historical Analog */}
        {data.historicalAnalog && (
          <div className="p-3 bg-surface-1 border border-border">
            <div className="flex items-center gap-2 mb-1">
              <History className="w-3 h-3 text-text-secondary" />
              <span className="text-xs font-medium text-text-primary">Historical Analog</span>
            </div>
            <p className="text-xs text-text-secondary">{data.historicalAnalog}</p>
          </div>
        )}

        {/* Indicators Table */}
        <div className="border border-border bg-surface-1 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border bg-surface-2">
                <th className="text-left py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Indicator</th>
                <th className="text-right py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Value</th>
                <th className="text-center py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Signal</th>
              </tr>
            </thead>
            <tbody>
              {indicatorsList.map((item) => (
                <tr key={item.key} className="border-b border-border-subtle last:border-0 hover:bg-surface-3 transition-colors">
                  <td className="py-2 px-3 text-sm text-text-primary">
                    <div className="flex items-center gap-1.5">
                      {getSignalIcon(item.signal)}
                      {item.key}
                    </div>
                  </td>
                  <td className="py-2 px-3 text-right font-mono text-sm text-text-primary">{item.formatted}</td>
                  <td className="py-2 px-3 text-center">
                    <span
                      className={cn(
                        'text-xs font-medium capitalize',
                        item.signal === 'expansion' ? 'text-green' : item.signal === 'contraction' ? 'text-red' : 'text-text-secondary'
                      )}
                    >
                      {item.signal}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Implication */}
        {data.implication && (
          <div className="p-3 border border-amber bg-amber-dim">
            <div className="text-xs font-medium text-amber mb-1">Investment Implication</div>
            <p className="text-xs text-text-secondary">{data.implication}</p>
          </div>
        )}
      </div>
    </div>
  );
}
