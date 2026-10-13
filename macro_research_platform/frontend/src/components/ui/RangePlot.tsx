// Range (forest) plot — point estimates with their uncertainty interval on one shared axis,
// so outcomes and their spread compare at a glance (scenarios, forecasts, model estimates).
// Zero line marked; values in text tokens; hover shows the exact interval.

import { useState } from 'react';

export interface RangeDatum { label: string; value: number; lo: number; hi: number; note?: string }

export function RangePlot({ data, fmt = (v) => v.toFixed(2), title, labelWidth = '9rem' }:
  { data: RangeDatum[]; fmt?: (v: number) => string; title?: string; labelWidth?: string }) {
  const [hover, setHover] = useState<string | null>(null);
  if (!data.length) return null;
  const lo = Math.min(0, ...data.map((d) => d.lo)), hi = Math.max(0, ...data.map((d) => d.hi));
  const span = hi - lo || 1;
  const x = (v: number) => `${((v - lo) / span) * 100}%`;
  return (
    <div>
      {title && <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">{title}</div>}
      <ul className="space-y-1.5">
        {data.map((d) => {
          const on = hover === d.label;
          const c = d.value >= 0 ? '#199e70' : '#e66767';
          return (
            <li key={d.label} className="grid items-center gap-2 text-2xs" style={{ gridTemplateColumns: `${labelWidth} 1fr 9rem` }}
              onMouseEnter={() => setHover(d.label)} onMouseLeave={() => setHover(null)} title={d.note}>
              <span className={`truncate ${on ? 'text-text-primary' : 'text-text-secondary'}`}>{d.label}</span>
              <span className="relative h-4 block" aria-hidden="true">
                <span className="absolute top-0 bottom-0 w-px bg-border" style={{ left: x(0) }} />
                <span className="absolute top-1/2 h-px" style={{ left: x(d.lo), width: `calc(${x(d.hi)} - ${x(d.lo)})`, background: c, opacity: 0.7 }} />
                <span className="absolute top-1 bottom-1 w-px" style={{ left: x(d.lo), background: c }} />
                <span className="absolute top-1 bottom-1 w-px" style={{ left: x(d.hi), background: c }} />
                <span className="absolute top-1/2 w-2.5 h-2.5 rounded-full -translate-x-1/2 -translate-y-1/2 border-2"
                  style={{ left: x(d.value), background: c, borderColor: 'var(--surface-1, #0d1117)' }} />
              </span>
              <span className={`text-right font-mono tabular-nums ${on ? 'text-text-primary' : 'text-text-secondary'}`}>
                {fmt(d.value)} <span className="text-text-tertiary">[{fmt(d.lo)}, {fmt(d.hi)}]</span>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
