/**
 * MetricCard — the single, standard metric card (Phase 5).
 *
 * Composes the primitives so every metric looks and behaves the same:
 *   • dominant monospace headline number (visual hierarchy)
 *   • inline sparkline
 *   • storytelling subtitle (Phase 2)          — `explanation`
 *   • anomaly badge, top-right (Phase 3)        — `zScore` / `isAnomalous`
 *   • data-lineage "i", top-right (Phase 1)     — `lineage`
 *   • staleness treatment: dashed amber border replaces the card styling (Phase 1) — `stale`
 *
 * All composition props are optional, so existing `<MetricCard label value sparklineData />`
 * call sites keep working unchanged.
 */
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { Sparkline } from './Sparkline';
import { AnomalyBadge } from './AnomalyBadge';
import { DataLineagePopover, type Lineage } from './DataLineagePopover';
import { cn, getDirectionColor } from '@/lib/utils';

interface MetricCardProps {
  label: string;
  value: string;
  direction?: 'up' | 'down' | 'neutral';
  sparklineData?: number[];
  color?: string;
  /** Phase 2 — one-line explanation of the move, shown as a muted subtitle. */
  explanation?: string;
  /** Phase 3 — anomaly flagging. */
  zScore?: number | null;
  isAnomalous?: boolean;
  /** Phase 1 — lineage popover ("i"). */
  lineage?: Lineage;
  /** Phase 1 — staleness: dashed amber border + label. */
  stale?: boolean;
  staleLabel?: string;
  className?: string;
}

export function MetricCard({
  label, value, direction = 'neutral', sparklineData, color,
  explanation, zScore, isAnomalous, lineage, stale, staleLabel, className,
}: MetricCardProps) {
  const valueColor = color || getDirectionColor(direction);
  const DirIcon = direction === 'up' ? TrendingUp : direction === 'down' ? TrendingDown : Minus;
  const dirTone = direction === 'up' ? 'text-green' : direction === 'down' ? 'text-red' : 'text-text-tertiary';

  return (
    <div
      className={cn(
        'relative bg-surface-1 p-3 flex flex-col min-h-20',
        stale ? 'border border-dashed border-amber/50 bg-amber-dim' : 'border border-border',
        className,
      )}
    >
      {/* Top accent — amber when stale, else brand */}
      <div className={cn('absolute top-0 left-0 right-0 h-px', stale ? 'bg-amber' : 'bg-bloomberg')} />

      {/* Header: label · [stale] on the left; anomaly badge + lineage "i" on the right */}
      <div className="flex items-start justify-between mb-1 gap-1">
        <span className="text-2xs text-text-secondary uppercase tracking-wider flex items-center gap-1">
          {label}
          {stale && <span className="text-amber font-bold">{staleLabel || 'STALE'}</span>}
        </span>
        <span className="flex items-center gap-1 shrink-0">
          {zScore !== undefined && zScore !== null && (isAnomalous ?? Math.abs(zScore) > 2) && (
            <AnomalyBadge zScore={zScore} isAnomalous={isAnomalous} />
          )}
          {lineage && <DataLineagePopover lineage={lineage} />}
        </span>
      </div>

      {/* Headline value — dominant */}
      <div className="flex items-center gap-2">
        <span className="text-2xl font-mono font-bold tabular-nums leading-none" style={{ color: valueColor }}>
          {value}
        </span>
        <span className={cn('flex items-center gap-0.5 text-2xs uppercase ml-auto', dirTone)}>
          <DirIcon className="w-3 h-3" /> {direction}
        </span>
      </div>

      {/* Inline sparkline */}
      {sparklineData && sparklineData.length > 1 && (
        <div className="mt-2">
          <Sparkline data={sparklineData} direction={direction} height={28} />
        </div>
      )}

      {/* Storytelling subtitle (Phase 2) */}
      {explanation && (
        <div className="mt-1.5 text-2xs text-text-tertiary leading-snug line-clamp-2" title={explanation}>
          {explanation}
        </div>
      )}
    </div>
  );
}
