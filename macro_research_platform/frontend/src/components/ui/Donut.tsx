// Donut chart for part-to-whole (allocations, sector / country mix, exit mix), drawn with Apache ECharts.
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
import { EChart, color, useChartTheme, type ECharts } from '@/components/charts/EChart';

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


export function Donut({ data, title, centerValue, centerLabel, size = 132, maxSlices = 6,
                        fmt = (v) => v.toLocaleString(undefined, { maximumFractionDigits: 0 }), colorFor, onSelect }: Props) {
  const [hover, setHover] = useState<number | null>(null);

  const slices = useMemo(() => {
    const clean = data.filter((d) => Number.isFinite(d.value) && d.value > 0).sort((a, b) => b.value - a.value);
    const keep = clean.length > maxSlices ? clean.slice(0, maxSlices - 1) : clean;
    const rest = clean.slice(keep.length);
    const all = rest.length ? [...keep, { label: `Other (${rest.length})`, value: rest.reduce((s, d) => s + d.value, 0), other: true }] : keep;
    const total = all.reduce((s, d) => s + d.value, 0);
    return all.map((d: any, i) => ({ ...d, share: total > 0 ? d.value / total : 0,
      color: color(d.other ? OTHER_GRAY : (colorFor ? colorFor(d.label, i) : CATEGORICAL[i % CATEGORICAL.length])) }));
  }, [data, maxSlices, colorFor]);
  const t = useChartTheme();
  const option = useMemo(() => ({
    animationDuration: 400, legend: { show: false }, toolbox: { show: false }, tooltip: { show: false },
    series: [{ type: 'pie', radius: ['66%', '96%'], center: ['50%', '50%'], avoidLabelOverlap: false, label: { show: false }, labelLine: { show: false },
      itemStyle: { borderColor: t.surface1, borderWidth: slices.length > 1 ? 2 : 0, borderRadius: 2 },
      emphasis: { scale: true, scaleSize: 3, itemStyle: { borderColor: t.surface1 } }, blur: { itemStyle: { opacity: 0.45 } },
      data: slices.map((s) => ({ name: s.label, value: s.value, itemStyle: { color: s.color } })) }],
  }), [slices, t]);
  const cb = useMemo(() => ({ onSelect }), [onSelect]);

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
  const h = hover != null ? slices[hover] : null;
  const onReady = (c: ECharts) => {
    c.on('mouseover', (e: any) => setHover(e.dataIndex));
    c.on('mouseout', () => setHover(null));
    c.on('click', (e: any) => cb.onSelect?.(e.name));
  };

  return (
    <div className="flex items-center gap-3 min-w-0">
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <EChart option={option} height={size} onReady={onReady}
          ariaLabel={`${title ?? 'Composition'}: ${slices.map((s) => `${s.label} ${(s.share * 100).toFixed(0)}%`).join(', ')}`} />
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
            <li key={s.label} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onClick={() => onSelect?.(s.label)}
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
