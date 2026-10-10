// Donut chart for part-to-whole (allocations, sector / country mix, exit mix).
//
// Conventions (kept deliberately strict so composition reads at a glance):
//   * at most `maxSlices` segments (default 6); the smallest fold into a gray "Other";
//   * categorical hues in fixed order (CATEGORICAL), never cycled; a slice keeps its color
//     by label (`colorFor`) so a filter never repaints survivors;
//   * a 2px surface-colored gap between segments; thin ring; no 3-D, no explode;
//   * a legend always (label, share, value), so identity never relies on color alone, and
//     a hover / focus tooltip on each segment.
// Values must be ≥ 0 (pass gross / absolute exposure for long-short books).

import { useMemo, useState } from 'react';
import { CATEGORICAL, OTHER_GRAY } from '@/lib/chartPalette';

export interface DonutDatum { label: string; value: number; sub?: string }

interface Props {
  data: DonutDatum[];
  title?: string;
  centerValue?: string;
  centerLabel?: string;
  size?: number;
  maxSlices?: number;
  fmt?: (v: number) => string;
  colorFor?: (label: string, index: number) => string;
  onSelect?: (label: string) => void;
}

const TAU = Math.PI * 2;

function arc(cx: number, cy: number, r0: number, r1: number, a0: number, a1: number): string {
  const large = a1 - a0 > Math.PI ? 1 : 0;
  const p = (r: number, a: number) => `${cx + r * Math.sin(a)},${cy - r * Math.cos(a)}`;
  if (a1 - a0 >= TAU - 1e-6) {           // full ring: two half arcs
    const m = a0 + Math.PI;
    return `M${p(r1, a0)}A${r1},${r1} 0 1 1 ${p(r1, m)}A${r1},${r1} 0 1 1 ${p(r1, a0)}`
      + `M${p(r0, a0)}A${r0},${r0} 0 1 0 ${p(r0, m)}A${r0},${r0} 0 1 0 ${p(r0, a0)}Z`;
  }
  return `M${p(r1, a0)}A${r1},${r1} 0 ${large} 1 ${p(r1, a1)}L${p(r0, a1)}A${r0},${r0} 0 ${large} 0 ${p(r0, a0)}Z`;
}

export function Donut({ data, title, centerValue, centerLabel, size = 132, maxSlices = 6,
                        fmt = (v) => v.toLocaleString(undefined, { maximumFractionDigits: 0 }), colorFor, onSelect }: Props) {
  const [hover, setHover] = useState<number | null>(null);

  const slices = useMemo(() => {
    const clean = data.filter((d) => Number.isFinite(d.value) && d.value > 0).sort((a, b) => b.value - a.value);
    const keep = clean.length > maxSlices ? clean.slice(0, maxSlices - 1) : clean;
    const rest = clean.slice(keep.length);
    const all = rest.length ? [...keep, { label: `Other (${rest.length})`, value: rest.reduce((s, d) => s + d.value, 0), other: true }] : keep;
    const total = all.reduce((s, d) => s + d.value, 0);
    let a = 0;
    return all.map((d: any, i) => {
      const share = total > 0 ? d.value / total : 0;
      const s = { ...d, share, a0: a, a1: a + share * TAU,
                  color: d.other ? OTHER_GRAY : (colorFor ? colorFor(d.label, i) : CATEGORICAL[i % CATEGORICAL.length]) };
      a += share * TAU;
      return s;
    });
  }, [data, maxSlices, colorFor]);

  if (!slices.length) return <div className="text-2xs text-text-tertiary p-2">No data</div>;
  if (slices.length === 1) {
    // One category is not a composition — a ring of one slice says less than the number.
    return (
      <div className="min-w-0">
        {title && <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">{title}</div>}
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-lg text-text-primary">100%</span>
          <span className="text-xs text-text-secondary truncate">{slices[0].label}</span>
        </div>
        <div className="text-[10px] text-text-tertiary font-mono">{fmt(slices[0].value)}</div>
      </div>
    );
  }
  const r1 = size / 2 - 2, r0 = r1 * 0.66, cx = size / 2, cy = size / 2;
  const h = hover != null ? slices[hover] : null;

  return (
    <div className="flex items-center gap-3 min-w-0">
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img"
          aria-label={`${title ?? 'Composition'}: ${slices.map((s) => `${s.label} ${(s.share * 100).toFixed(0)}%`).join(', ')}`}>
          {slices.map((s, i) => (
            <path key={s.label} d={arc(cx, cy, r0, hover === i ? r1 + 1.5 : r1, s.a0, s.a1)} fill={s.color}
              stroke="var(--surface-1, #0d1117)" strokeWidth={slices.length > 1 ? 2 : 0} strokeLinejoin="round"
              opacity={hover == null || hover === i ? 1 : 0.45} tabIndex={0}
              onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(i)} onBlur={() => setHover(null)}
              onClick={() => onSelect?.(s.label)} style={{ cursor: onSelect ? 'pointer' : 'default', outline: 'none' }} />
          ))}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none text-center px-3">
          {h ? (
            <>
              <div className="font-mono text-xs text-text-primary">{(h.share * 100).toFixed(1)}%</div>
              <div className="text-[10px] text-text-secondary leading-tight line-clamp-2">{h.label}</div>
              <div className="text-[10px] text-text-tertiary font-mono">{fmt(h.value)}</div>
            </>
          ) : (
            <>
              {centerValue && <div className="font-mono text-xs text-text-primary">{centerValue}</div>}
              {centerLabel && <div className="text-[10px] text-text-tertiary leading-tight">{centerLabel}</div>}
            </>
          )}
        </div>
      </div>
      <div className="min-w-0 flex-1">
        {title && <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">{title}</div>}
        <ul className="space-y-0.5">
          {slices.map((s, i) => (
            <li key={s.label} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
              className={`flex items-center gap-1.5 text-2xs ${hover === i ? 'text-text-primary' : 'text-text-secondary'}`}>
              <span className="inline-block w-2 h-2 rounded-sm shrink-0" style={{ background: s.color }} />
              <span className="truncate" title={s.sub ? `${s.label} — ${s.sub}` : s.label}>{s.label}</span>
              <span className="ml-auto font-mono tabular-nums text-text-primary">{(s.share * 100).toFixed(1)}%</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
