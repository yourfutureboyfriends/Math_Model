/**
 * Sparkline on Apache ECharts (SVG renderer: light enough for a chart in every table row). Starts only when it
 * scrolls into view, so long tables stay fast. Up = green, down = red, a near-flat series (pegs) is drawn grey and
 * not stretched; hover shows the value (and its label when given) in a tooltip that escapes the table cell.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { EChart, alpha, color, useChartTheme } from './EChart';

export function MiniChart({ values, width, height = 20, labels, fmt, colour, area = true, dot = true, ariaLabel, fill = false }: {
  values?: (number | null)[]; width?: number | string; height?: number; labels?: string[]; fmt?: (v: number) => string;
  colour?: string; area?: boolean; dot?: boolean; ariaLabel?: string; fill?: boolean;
}) {
  const t = useChartTheme();
  const box = useRef<HTMLSpanElement>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = box.current; if (!el || seen) return;
    if (typeof IntersectionObserver === 'undefined') { setSeen(true); return; }
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) { setSeen(true); io.disconnect(); } }, { rootMargin: '200px' });
    io.observe(el);
    return () => io.disconnect();
  }, [seen]);
  const v = (values ?? []).filter((x): x is number => typeof x === 'number' && Number.isFinite(x));
  const option = useMemo(() => {
    if (v.length < 2) return null;
    const lo = Math.min(...v), hi = Math.max(...v);
    const flat = hi === lo || (hi - lo) / Math.max(Math.abs((hi + lo) / 2), 1e-12) < 0.002;     // pegs: don't stretch noise
    const up = v[v.length - 1] >= v[0];
    const c = colour ? color(colour) : flat ? t.mutedText : up ? t.green : t.red;
    const f = fmt ?? ((x: number) => x.toLocaleString(undefined, { maximumFractionDigits: Math.abs(x) >= 100 ? 0 : 2 }));
    return {
      animation: false, legend: { show: false }, toolbox: { show: false },
      grid: { left: 1, right: dot ? 3 : 1, top: 2, bottom: 2 },
      tooltip: { trigger: 'axis', appendTo: 'body', confine: false, axisPointer: { type: 'line', lineStyle: { color: t.mutedText, type: 'dashed' } },
        padding: [3, 6], textStyle: { fontSize: 10, color: t.textStrong }, extraCssText: 'box-shadow:0 4px 12px rgba(0,0,0,.25);border-radius:4px;',
        formatter: (ps: any[]) => `${labels?.[ps[0].dataIndex] ? `<span style="opacity:.6">${labels[ps[0].dataIndex]}</span> ` : ''}<b>${f(ps[0].value)}</b>` },
      xAxis: { type: 'category', show: false, boundaryGap: false, data: v.map((_, i) => i) },
      yAxis: { type: 'value', show: false, min: flat ? lo - 1 : lo, max: flat ? hi + 1 : hi },
      series: [{ type: 'line', data: v, showSymbol: false, symbol: 'circle', symbolSize: 4, lineStyle: { width: 1.3, color: c }, itemStyle: { color: c },
        ...(area && !flat ? { areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: alpha(c, 0.22) }, { offset: 1, color: alpha(c, 0) }] }, origin: 'start' } } : {}),
        ...(dot && !flat ? { markPoint: { symbol: 'circle', symbolSize: 4, silent: true, label: { show: false }, itemStyle: { color: c }, data: [{ coord: [v.length - 1, v[v.length - 1]] }] } } : {}) }],
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(v), labels, colour, area, dot, t]);
  const w = fill ? '100%' : width ?? 72;
  return (
    <span ref={box} className="inline-block align-middle" style={{ width: w, height }} aria-label={ariaLabel} role={ariaLabel ? 'img' : undefined} aria-hidden={ariaLabel ? undefined : true}>
      {seen && option && <EChart option={option} height={height} renderer="svg" />}
    </span>
  );
}
