// Phase 8 — Sector Allocation Section with Earnings Revision Overlay + Phase 1E Store Integration
// Terminal-style table using format library

import { cn } from '@/lib/utils';
import { Zap, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { useMacroStore } from '@/store/macroStore';
import { useApiData } from '@/hooks/useApiData';
import { fmtSignal, fmtChange } from '@/utils/format';
import { BarList } from '@/components/ui/BarList';
import { KpiStrip } from '@/components/ui/KpiStrip';
import type { SectorAllocationData } from '@/types';

interface EnhancedSector {
  name: string;
  macro_score: number | null;
  earnings_addon: number;
  enhanced_score: number | null;   // relative-strength rank -1..+1; null without price data
  signal: string;
  conviction: string;
  rationale: string;
  eps_revision_pct: number | null;
  direction: 'UP' | 'DOWN' | 'FLAT';
  beats_rate: number | null;
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
  available?: boolean;
  reason?: string;
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
  const _fullDash = useMacroStore((s) => s.fullDashboard);
  if (!data) data = (_fullDash as any)?.["sectorAllocation"] as any;

  const { data: earningsData } = useApiData<EarningsData>('/api/earnings/revisions');

  // Use macro store for regime context
  const regime = useMacroStore((state) => state.regime);

  if (!data?.sectors?.length) return null;

  // Is the EPS-revision overlay actually available? (Requires the Finnhub feed; when absent the
  // backend returns available:false with no sectors — we must NOT fabricate a 0.0% in that case.)
  const epsAvailable = earningsData?.available !== false
    && !!earningsData?.sectors
    && Object.keys(earningsData.sectors).length > 0;

  // Merge sector allocation (real, regime-based) with the earnings overlay when present.
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
      eps_revision_pct: epsAvailable ? (earnings?.eps_revision_pct ?? null) : null,
      direction: earnings?.direction ?? 'FLAT',
      beats_rate: earnings?.beats_rate ?? null,
      divergence: earnings?.divergence ?? false,
      divergence_type: earnings?.divergence_type ?? null,
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

  const scores = enhancedSectors.map(s => s.enhanced_score).filter((v): v is number => v != null);
  const avgScore: number | null = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null;
  const maxScore: number | null = scores.length ? Math.max(...scores) : null;
  const minScore: number | null = scores.length ? Math.min(...scores) : null;

  // Check for divergences
  const hasDivergences = (earningsData?.divergences?.length ?? 0) > 0;

  return (
    <div id="sector-allocation" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">◆</span>
          <h2 className="section-title">Sector Allocation</h2>
          <span className="section-meta">Regime: {regime.current ? regime.current.toUpperCase() : '—'} | Avg: {fmtSignal(avgScore)}</span>
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
                      {' '}{fmtChange(div.revision_pct / 100)}
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

        {/* Ranking + stance counts */}
        <div className="grid gap-2 lg:grid-cols-3">
          <div className="px-3 py-2 bg-surface-1 border border-border lg:col-span-2">
            <BarList title="Sector scores, ranked (relative strength in this regime)" diverging max={1} labelWidth="9rem"
              fmt={(v) => fmtSignal(v)}
              data={[...enhancedSectors].sort((a, b) => (b.enhanced_score ?? -9) - (a.enhanced_score ?? -9)).map((sct) => ({
                label: sct.name, value: sct.enhanced_score, note: `${sct.signal} · ${sct.conviction} conviction — ${sct.rationale}`,
                color: sct.signal.includes('Overweight') ? '#199e70' : sct.signal.includes('Underweight') ? '#e66767' : '#6b7280',
              }))} />
          </div>
          <KpiStrip compact items={[
            { label: 'Overweight', value: String(enhancedSectors.filter((x) => x.signal.includes('Overweight')).length), tone: 'up',
              sub: enhancedSectors.filter((x) => x.signal.includes('Overweight')).map((x) => x.name).slice(0, 3).join(', ') || '—' },
            { label: 'Neutral', value: String(enhancedSectors.filter((x) => !x.signal.includes('weight')).length) },
            { label: 'Underweight', value: String(enhancedSectors.filter((x) => x.signal.includes('Underweight')).length), tone: 'down',
              sub: enhancedSectors.filter((x) => x.signal.includes('Underweight')).map((x) => x.name).slice(0, 3).join(', ') || '—' },
            { label: 'Average score', value: fmtSignal(avgScore), sub: `range ${fmtSignal(minScore)} to ${fmtSignal(maxScore)}` },
          ]} />
        </div>

        {/* Sector Table with EPS Revisions */}
        <div className="border border-border bg-surface-1 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border bg-surface-2">
                <th className="text-left py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Sector</th>
                <th className="text-left py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Signal</th>
                <th className="text-right py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Score</th>
                <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium" title={epsAvailable ? undefined : (earningsData?.reason || 'EPS-revision feed unavailable')}>
                  EPS Rev{!epsAvailable && <span className="text-amber ml-0.5" aria-label="feed unavailable">*</span>}
                </th>
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
                      {sector.signal}
                    </span>
                  </td>
                  <td className="py-2 px-2 text-right">
                    <span className={cn(
                      'font-mono text-sm tabular-nums',
                      (sector.enhanced_score ?? 0) > 0 ? 'text-green' : (sector.enhanced_score ?? 0) < 0 ? 'text-red' : 'text-text-secondary'
                    )}>
                      {fmtSignal(sector.enhanced_score)}
                    </span>
                    {sector.earnings_addon !== 0 && (
                      <span className={cn(
                        'text-2xs ml-1',
                        sector.earnings_addon > 0 ? 'text-green' : 'text-red'
                      )}>
                        {fmtSignal(sector.earnings_addon)}
                      </span>
                    )}
                  </td>
                  <td className="py-2 px-2 text-center">
                    {sector.eps_revision_pct == null ? (
                      <span className="text-xs text-text-tertiary" title="EPS-revision feed unavailable">—</span>
                    ) : (
                      <div className={cn(
                        'flex items-center justify-center gap-1 text-xs font-mono',
                        getEpsRevColor(sector.eps_revision_pct)
                      )}>
                        {getEpsRevIcon(sector.direction)}
                        {fmtChange(sector.eps_revision_pct / 100)}
                      </div>
                    )}
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
                      {sector.enhanced_score != null && (
                      <div
                        className={cn('h-full absolute', getScoreBarColor(sector.enhanced_score))}
                        style={{
                          width: `${Math.min(100, Math.abs(sector.enhanced_score) * 50)}%`,
                          left: sector.enhanced_score >= 0 ? '50%' : `${50 - Math.abs(sector.enhanced_score) * 50}%`,
                        }}
                      />
                      )}
                      <div className="absolute top-0 bottom-0 left-1/2 w-px bg-text-tertiary/30" />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!epsAvailable && (
          <div className="text-2xs text-text-tertiary">
            <span className="text-amber">*</span> {earningsData?.reason || 'EPS-revision feed unavailable'} — the sector Score/Signal below is the live regime-based allocation and is unaffected.
          </div>
        )}

        {/* Rationale Section */}
        <div className="p-3 border border-border bg-surface-1">
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Top Picks Rationale</div>
          <div className="space-y-1">
            {enhancedSectors.slice(0, 3).map((sector) => (
              <div key={sector.name} className="flex items-start gap-2 text-sm">
                <span className={cn(
                  'w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0',
                  sector.enhanced_score == null ? 'bg-text-tertiary' : sector.enhanced_score > 0 ? 'bg-green' : 'bg-red'
                )} />
                <span className="text-text-secondary">
                  <span className="text-text-primary font-medium">{sector.name}</span>: {sector.rationale}
                  {sector.divergence && (
                    <span className="text-amber ml-1">Divergence</span>
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
