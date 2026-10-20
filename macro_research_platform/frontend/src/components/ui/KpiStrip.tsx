// A row of stat tiles — the numbers a panel leads with. Tone colours the value only when it
// carries a sign (gain / loss); labels and context stay in text tokens.

import { cn } from '@/lib/utils';

export interface Kpi { label: string; value: string; sub?: string; tone?: 'up' | 'down' | 'warn' | null; accent?: boolean }

export function KpiStrip({ items, cols = 6, compact = false }: { items: Kpi[]; cols?: number; compact?: boolean }) {
  const grid = compact ? '' : cols >= 6 ? 'xl:grid-cols-6' : cols === 5 ? 'xl:grid-cols-5' : cols === 4 ? 'xl:grid-cols-4' : 'xl:grid-cols-3';
  return (
    <div className={cn('grid gap-2 grid-cols-2', !compact && 'md:grid-cols-3', grid)}>
      {items.map((k) => (
        <div key={k.label} className={cn('px-3 py-2 bg-surface-1 border', k.accent ? 'border-bloomberg/50' : 'border-border')}>
          <div className="text-[10px] uppercase tracking-wide text-text-tertiary truncate">{k.label}</div>
          <div className={cn('font-mono text-sm mt-0.5', k.tone === 'up' ? 'text-green' : k.tone === 'down' ? 'text-red' : k.tone === 'warn' ? 'text-amber' : 'text-text-primary')}>{k.value}</div>
          {k.sub && <div className="text-[10px] text-text-tertiary truncate">{k.sub}</div>}
        </div>
      ))}
    </div>
  );
}
