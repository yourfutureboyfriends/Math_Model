// Heat grid — rows × columns of signed values (returns by horizon, returns by regime).
// Diverging encoding: red ↔ neutral surface ↔ green, intensity ∝ |value| / scale; the value
// is printed in each cell, so colour is never the only carrier. Row labels can be buttons.

import { cn } from '@/lib/utils';

interface Props {
  rows: { label: string; sub?: string; values: (number | null)[]; onClick?: () => void; highlight?: boolean }[];
  columns: string[];
  fmt?: (v: number) => string;
  scale?: number;                      // |value| that maps to full intensity (default: max |value|)
  title?: string;
  labelWidth?: string;
}

function bg(v: number | null, scale: number): string {
  if (v == null || !Number.isFinite(v)) return 'transparent';
  const a = Math.min(1, Math.abs(v) / scale) * 0.55 + 0.06;
  return v >= 0 ? `rgba(25, 158, 112, ${a})` : `rgba(230, 103, 103, ${a})`;
}

export function HeatGrid({ rows, columns, fmt = (v) => v.toFixed(1), scale, title, labelWidth = '8rem' }: Props) {
  const all = rows.flatMap((r) => r.values).filter((v): v is number => v != null && Number.isFinite(v));
  const s = scale ?? Math.max(1e-9, ...all.map((v) => Math.abs(v)));
  const template = `${labelWidth} repeat(${columns.length}, minmax(3.5rem, 1fr))`;
  return (
    <div className="overflow-x-auto">
      {title && <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">{title}</div>}
      <div className="grid gap-px text-2xs min-w-fit" style={{ gridTemplateColumns: template }}>
        <div />
        {columns.map((c) => <div key={c} className="text-center text-text-tertiary py-1 uppercase">{c}</div>)}
        {rows.map((r) => (
          <div key={r.label} className="contents">
            <div className={cn('flex items-center gap-1 pr-2 truncate', r.highlight && 'text-amber')}>
              {r.onClick ? (
                <button type="button" onClick={r.onClick} className="text-text-primary hover:text-bloomberg font-mono truncate">{r.label}</button>
              ) : <span className="text-text-primary truncate">{r.label}</span>}
              {r.sub && <span className="text-text-tertiary truncate">{r.sub}</span>}
            </div>
            {r.values.map((v, i) => (
              <div key={i} className="text-center font-mono tabular-nums py-1.5 text-text-primary" style={{ background: bg(v, s) }}
                title={`${r.label} · ${columns[i]}: ${v == null ? 'n/a' : fmt(v)}`}>
                {v == null || !Number.isFinite(v) ? '—' : fmt(v)}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
