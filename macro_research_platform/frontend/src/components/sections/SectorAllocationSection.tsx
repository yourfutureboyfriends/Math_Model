// Phase 8 — Sector Allocation Section with Earnings Revision Overlay
// Terminal-style table with score bars, EPS revisions, and divergence detection

import { useState, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { Zap, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { SectorAllocationData } from '@/types';

interface EnhancedSector {
  name: string;
  macro_score: number;
  earnings_addon: number;
  enhanced_score: number;
  signal: string;
  conviction: string;
  rationale: string;
  eps_revision_pct: number;
  direction: 'UP' | 'DOWN' | 'FLAT';
  beats_rate: number;
  divergence: boolean;
  divergence_type: string | null;
}

interface Divergence {
  sector: string;
  type: string;
  revision_pct: number;
  macro_signal: string;
}

interface EarningsData {
  sectors: Record<string, {
    eps_revision_pct: number;
    direction: 'UP' | 'DOWN' | 'FLAT';
    beats_rate: number;
    macro_signal: string;
    divergence: boolean;
    divergence_type: string | null;
    enhanced_sector_score: number;
    macro_score: number;
    earnings_addon: number;
  }>;
  divergences: Divergence[];
  strongest_positive_revision: string;
  strongest_negative_revision: string;
  updated_at: string;
}

interface SectorAllocationSectionProps {
  data?: SectorAllocationData;
}

export function SectorAllocationSection({ data }: SectorAllocationSectionProps) {
  const [earningsData, setEarningsData] = useState<EarningsData | null>(null);
  const [, setLoading] = useState(true);

  useEffect(() => {
    const fetchEarnings = async () => {
      try {
        const response = await fetch('/api/earnings/revisions');
        if (response.ok) {
          const result = await response.json();
          setEarningsData(result);
        }
      } catch (err) {
        // Earnings fetch error handled silently
      } finally {
        setLoading(false);
      }
    };

    fetchEarnings();
  }, []);

  if (!data?.sectors?.length) return null;

  // Merge sector allocation with earnings data
  const enhancedSectors: EnhancedSector[] = data.sectors.map(sector => {
    const earnings = earningsData?.sectors?.[sector.name];
    return {
      name: sector.name,
      macro_score: earnings?.macro_score ?? sector.score,
      earnings_addon: earnings?.earnings_addon ?? 0,
      enhanced_score: earnings?.enhanced_sector_score ?? sector.score,
      signal: sector.signal,
      conviction: sector.conviction,
      rationale: sector.rationale,
      eps_revision_pct: earnings?.eps_revision_pct ?? 0,
      direction: earnings?.direction ?? 'FLAT',
      beats_rate: earnings?.beats_rate ?? 0.5,
      divergence: earnings?.divergence ?? false,
      divergence_type: earnings?.divergence_type ?? null,
      // color: '#7d8590',  // Removed: Sector type doesn't include color
    };
  });

  const getSignalTag = (signal: string) => {
    if (signal.includes('Overweight')) return 'signal-tag overweight';
    if (signal.includes('Underweight')) return 'signal-tag underweight';
    return 'signal-tag neutral';
  };

  const getScoreBarColor = (score: number) => {
    if (score >= 0.4) return 'bg-green';
    if (score >= 0) return 'bg-bloomberg';
    if (score >= -0.4) return 'bg-amber';
    return 'bg-red';
  };

  const getEpsRevColor = (pct: number) => {
    if (pct > 2) return 'text-green';
    if (pct < -2) return 'text-red';
    return 'text-text-tertiary';
  };

  const getEpsRevIcon = (direction: string) => {
    if (direction === 'UP') return <TrendingUp className="w-3 h-3" />;
    if (direction === 'DOWN') return <TrendingDown className="w-3 h-3" />;
    return <Minus className="w-3 h-3" />;
  };

  const avgScore = enhancedSectors.reduce((acc, s) => acc + s.enhanced_score, 0) / enhancedSectors.length;
  const maxScore = Math.max(...enhancedSectors.map(s => s.enhanced_score));
  const minScore = Math.min(...enhancedSectors.map(s => s.enhanced_score));

  // Check for divergences
  const hasDivergences = (earningsData?.divergences?.length ?? 0) > 0;

  return (
    <div id="sector-allocation" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">09</span>
          <h2 className="section-title">Sector Allocation</h2>
          <span className="section-meta">Avg: {avgScore.toFixed(2)}</span>
        </div>
      </div>

      <div className="space-y-3">
        {/* Divergence Alert Box */}
        {hasDivergences && (
          <div className="p-3 border border-amber bg-amber-dim">
            <div className="flex items-start gap-2">
              <Zap className="w-4 h-4 text-amber flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <div className="text-sm font-medium text-amber mb-1">
                  MACRO-MICRO DIVERGENCE DETECTED
                </div>
                <div className="space-y-1">
                  {earningsData?.divergences?.map((div, idx) => (
                    <div key={idx} className="text-xs text-text-secondary">
                      {div.sector}: Macro {div.macro_signal} but EPS revisions
                      {div.revision_pct > 0 ? ' UP' : ' DOWN'}
                      {' '}{div.revision_pct > 0 ? '+' : ''}{div.revision_pct.toFixed(1)}%
                    </div>
                  ))}
                </div>
                <div className="text-2xs text-text-tertiary mt-2">
                  These divergences may signal regime transition risk.
                </div>
              </div>
            </div>
          </div>
        )}

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

        {/* Sector Table with EPS Revisions */}
        <div className="border border-border bg-surface-1 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border bg-surface-2">
                <th className="text-left py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Sector</th>
                <th className="text-left py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Signal</th>
                <th className="text-right py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Score</th>
                <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">EPS Rev</th>
                <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Divergence</th>
                <th className="text-left py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Bar</th>
              </tr>
            </thead>
            <tbody>
              {enhancedSectors.map((sector) => (
                <tr
                  key={sector.name}
                  className={cn(
                    "border-b border-border-subtle last:border-0 hover:bg-surface-3 transition-colors",
                    sector.divergence && "bg-amber-dim/30"
                  )}
                >
                  <td className="py-2 px-2 text-sm text-text-primary">{sector.name}</td>
                  <td className="py-2 px-2">
                    <span className={getSignalTag(sector.signal)}>
                      {sector.signal.replace('Slight ', 'SL ')}
                    </span>
                  </td>
                  <td className="py-2 px-2 text-right">
                    <span className={cn(
                      'font-mono text-sm tabular-nums',
                      sector.enhanced_score > 0 ? 'text-green' : sector.enhanced_score < 0 ? 'text-red' : 'text-text-secondary'
                    )}>
                      {sector.enhanced_score > 0 ? '+' : ''}{sector.enhanced_score.toFixed(2)}
                    </span>
                    {sector.earnings_addon !== 0 && (
                      <span className={cn(
                        'text-2xs ml-1',
                        sector.earnings_addon > 0 ? 'text-green' : 'text-red'
                      )}>
                        {sector.earnings_addon > 0 ? '+' : ''}{sector.earnings_addon.toFixed(2)}
                      </span>
                    )}
                  </td>
                  <td className="py-2 px-2 text-center">
                    <div className={cn(
                      'flex items-center justify-center gap-1 text-xs font-mono',
                      getEpsRevColor(sector.eps_revision_pct)
                    )}>
                      {getEpsRevIcon(sector.direction)}
                      {sector.eps_revision_pct > 0 ? '+' : ''}{sector.eps_revision_pct.toFixed(1)}%
                    </div>
                  </td>
                  <td className="py-2 px-2 text-center">
                    {sector.divergence ? (
                      <span className="flex items-center justify-center gap-1 text-xs font-medium text-amber">
                        <Zap className="w-3 h-3" />
                        DIVERGENCE
                      </span>
                    ) : (
                      <span className="text-xs text-text-tertiary">—</span>
                    )}
                  </td>
                  <td className="py-2 px-2 w-24">
                    <div className="h-1.5 bg-surface-4 relative">
                      <div
                        className={cn('h-full absolute', getScoreBarColor(sector.enhanced_score))}
                        style={{
                          width: `${Math.min(100, Math.abs(sector.enhanced_score) * 50)}%`,
                          left: sector.enhanced_score >= 0 ? '50%' : `${50 - Math.abs(sector.enhanced_score) * 50}%`,
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
            {enhancedSectors.slice(0, 3).map((sector) => (
              <div key={sector.name} className="flex items-start gap-2 text-sm">
                <span className={cn(
                  'w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0',
                  sector.enhanced_score > 0 ? 'bg-green' : 'bg-red'
                )} />
                <span className="text-text-secondary">
                  <span className="text-text-primary font-medium">{sector.name}</span>: {sector.rationale}
                  {sector.divergence && (
                    <span className="text-amber ml-1">⚡ Divergence detected</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 text-2xs text-text-tertiary">
          <div className="flex items-center gap-1">
            <TrendingUp className="w-3 h-3 text-green" />
            <span>EPS Rev {'>'} +2%</span>
          </div>
          <div className="flex items-center gap-1">
            <Minus className="w-3 h-3 text-text-tertiary" />
            <span>Flat (-2% to +2%)</span>
          </div>
          <div className="flex items-center gap-1">
            <TrendingDown className="w-3 h-3 text-red" />
            <span>EPS Rev {'<'} -2%</span>
          </div>
        </div>
      </div>
    </div>
  );
}
