// Horizontal bar list — magnitude by label, or a diverging comparison around zero
// (over/underweights, long/short, positive/negative scores). Thin bars (≤ 12px) with a
// rounded data end and a square baseline; values in text tokens, never in the bar colour;
// hover highlights the row and shows its note.

import { useState } from 'react';

export interface BarDatum { label: string; value: number | null; note?: string; color?: string; sub?: string }

interface Props {
  data: BarDatum[];
  diverging?: boolean;                 // centre baseline at 0, negatives to the left
  fmt?: (v: number) => string;
  color?: string;                      // single-series colour
  posColor?: string;
  negColor?: string;
  max?: number;                        // fixed scale (e.g. 1 for weights) — else the data's max |value|
  labelWidth?: string;                 // CSS width of the label column
  onSelect?: (label: string) => void;
  title?: string;
}

export function BarList({ data, diverging = false, fmt = (v) => v.toFixed(2), color = '#3987e5',
                          posColor = '#199e70', negColor = '#e66767', max, labelWidth = '8rem', onSelect, title }: Props) {
  const [hover, setHover] = useState<string | null>(null);
  const vals = data.map((d) => d.value).filter((v): v is number => v != null && Number.isFinite(v));
  const scale = max ?? Math.max(1e-9, ...vals.map((v) => Math.abs(v)));
  return (
    <div>
      {title && <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">{title}</div>}
      <ul className="space-y-1">
        {data.map((d) => {
          const v = d.value;
          const w = v == null ? 0 : Math.min(1, Math.abs(v) / scale);
          const c = d.color ?? (diverging ? (v != null && v < 0 ? negColor : posColor) : color);
          const on = hover === d.label;
          return (
            <li key={d.label} onMouseEnter={() => setHover(d.label)} onMouseLeave={() => setHover(null)}
              onClick={() => onSelect?.(d.label)} title={d.note ? `${d.label}: ${d.note}` : d.label}
              className={`grid items-center gap-2 text-2xs ${onSelect ? 'cursor-pointer' : ''}`}
              style={{ gridTemplateColumns: `${labelWidth} 1fr 4.5rem` }}>
              <span className={`truncate ${on ? 'text-text-primary' : 'text-text-secondary'}`}>{d.label}
                {d.sub && <span className="text-text-tertiary"> · {d.sub}</span>}</span>
              <span className="relative h-3 block" aria-hidden="true">
                {diverging && <span className="absolute left-1/2 top-[-2px] bottom-[-2px] w-px bg-border" />}
                {v != null && (
                  <span className="absolute top-0.5 h-2"
                    style={diverging
                      ? (v >= 0 ? { left: '50%', width: `${w * 50}%`, background: c, borderRadius: '0 3px 3px 0', opacity: on ? 1 : 0.85 }
                                : { right: '50%', width: `${w * 50}%`, background: c, borderRadius: '3px 0 0 3px', opacity: on ? 1 : 0.85 })
                      : { left: 0, width: `${w * 100}%`, background: c, borderRadius: '0 3px 3px 0', opacity: on ? 1 : 0.85 }} />
                )}
              </span>
              <span className={`text-right font-mono tabular-nums ${on ? 'text-text-primary' : 'text-text-secondary'}`}>{v == null ? '—' : fmt(v)}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
