// Phase 8 — Sector Allocation Section (Redesigned)
// Terminal-style table with score bars

import { cn } from '@/lib/utils';
import type { SectorAllocationData } from '@/types';

interface SectorAllocationSectionProps {
  data?: SectorAllocationData;
}

export function SectorAllocationSection({ data }: SectorAllocationSectionProps) {
  if (!data?.sectors?.length) return null;

  const getSignalTag = (signal: string) => {
    if (signal.includes('Overweight')) return 'signal-tag overweight';
    if (signal.includes('Underweight')) return 'signal-tag underweight';
    return 'signal-tag neutral';
  };

  const getScoreBarColor = (score: number) => {
    if (score >= 0.4) return 'bg-green';
    if (score >= 0) return 'bg-accent';
    if (score >= -0.4) return 'bg-amber';
    return 'bg-red';
  };

  const avgScore = data.sectors.reduce((acc, s) => acc + s.score, 0) / data.sectors.length;
  const maxScore = Math.max(...data.sectors.map(s => s.score));
  const minScore = Math.min(...data.sectors.map(s => s.score));

  return (
    <div id="sector-allocation" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">07</span>
          <h2 className="section-title">Sector Allocation</h2>
          <span className="section-meta">Avg: {avgScore.toFixed(2)}</span>
        </div>
      </div>

      <div className="space-y-3">
        {/* Stats Row */}
        <div className="grid grid-cols-3 gap-3">
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider">Avg Score</div>
            <div className="text-base font-mono font-bold text-text-primary">{avgScore.toFixed(2)}</div>
          </div>
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider">Max</div>
            <div className="text-base font-mono font-bold text-green">+{maxScore.toFixed(2)}</div>
          </div>
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider">Min</div>
            <div className="text-base font-mono font-bold text-red">{minScore.toFixed(2)}</div>
          </div>
        </div>

        {/* Sector Table */}
        <div className="border border-border bg-surface-1 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border bg-surface-2">
                <th className="text-left py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Sector</th>
                <th className="text-left py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Signal</th>
                <th className="text-right py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Score</th>
                <th className="text-center py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Conv</th>
                <th className="text-left py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Bar</th>
              </tr>
            </thead>
            <tbody>
              {data.sectors.map((sector) => (
                <tr key={sector.name} className="border-b border-border-subtle last:border-0 hover:bg-surface-3 transition-colors">
                  <td className="py-2 px-3 text-sm text-text-primary">{sector.name}</td>
                  <td className="py-2 px-3">
                    <span className={getSignalTag(sector.signal)}>
                      {sector.signal.replace('Slight ', 'SL ')}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right">
                    <span className={cn(
                      'font-mono text-sm tabular-nums',
                      sector.score > 0 ? 'text-green' : sector.score < 0 ? 'text-red' : 'text-text-secondary'
                    )}>
                      {sector.score > 0 ? '+' : ''}{sector.score.toFixed(2)}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-center">
                    <span className={cn(
                      'text-xs',
                      sector.conviction === 'High' ? 'text-green' :
                      sector.conviction === 'Medium' ? 'text-amber' : 'text-text-tertiary'
                    )}>
                      {sector.conviction.charAt(0)}
                    </span>
                  </td>
                  <td className="py-2 px-3 w-32">
                    <div className="h-1.5 bg-surface-4 relative">
                      <div
                        className={cn('h-full absolute', getScoreBarColor(sector.score))}
                        style={{
                          width: `${Math.min(100, Math.abs(sector.score) * 50)}%`,
                          left: sector.score >= 0 ? '50%' : `${50 - Math.abs(sector.score) * 50}%`,
                        }}
                      />
                      <div className="absolute top-0 bottom-0 left-1/2 w-px bg-text-tertiary/30" />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Rationale Section */}
        <div className="p-3 border border-border bg-surface-1">
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Top Picks Rationale</div>
          <div className="space-y-1">
            {data.sectors.slice(0, 3).map((sector) => (
              <div key={sector.name} className="flex items-start gap-2 text-sm">
                <span className={cn(
                  'w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0',
                  sector.score > 0 ? 'bg-green' : 'bg-red'
                )} />
                <span className="text-text-secondary">
                  <span className="text-text-primary font-medium">{sector.name}</span>: {sector.rationale}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
