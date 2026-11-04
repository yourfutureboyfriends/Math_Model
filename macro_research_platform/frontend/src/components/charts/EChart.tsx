/**
 * Apache ECharts in React — the platform's one chart engine. Themed from the app's CSS tokens (re-themed when the
 * light/dark theme changes), resized with its container, optionally linked to other charts in a `group` (shared
 * crosshair and zoom via echarts.connect), with a toolbox (zoom, data view, save PNG) on charts that have room.
 * Colours may be passed as the app's CSS expressions (`rgb(var(--c-blue))`, `var(--text-tertiary)`); `color()`
 * resolves them, since ECharts draws on a canvas and cannot read CSS variables.
 */
import { useEffect, useRef, useState } from 'react';
import * as echarts from 'echarts/core';
import { BarChart, CandlestickChart, CustomChart, EffectScatterChart, GaugeChart, GraphChart, HeatmapChart, LineChart, LinesChart, PieChart, ScatterChart, TreemapChart } from 'echarts/charts';
import {
  AxisPointerComponent, BrushComponent, DataZoomComponent, GraphicComponent, GridComponent, LegendComponent, MarkAreaComponent,
  MarkLineComponent, MarkPointComponent, TitleComponent, ToolboxComponent, TooltipComponent, VisualMapComponent,
} from 'echarts/components';
import { LabelLayout } from 'echarts/features';
import { CanvasRenderer, SVGRenderer } from 'echarts/renderers';
import type { EChartsCoreOption } from 'echarts/core';

echarts.use([LineChart, BarChart, ScatterChart, HeatmapChart, CandlestickChart, PieChart, GaugeChart, CustomChart, TreemapChart, GraphChart, LinesChart, EffectScatterChart, GridComponent, TooltipComponent,
  LegendComponent, DataZoomComponent, ToolboxComponent, MarkAreaComponent, MarkLineComponent, MarkPointComponent,
  VisualMapComponent, BrushComponent, AxisPointerComponent, TitleComponent, GraphicComponent, LabelLayout, CanvasRenderer, SVGRenderer]);

export type ECharts = echarts.ECharts;

/** ECharts parses only legacy colour syntax: turn `rgb(r g b / a)` into `rgba(r,g,b,a)`. */
const legacy = (c: string) => c.replace(/rgba?\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*(?:\/\s*([\d.]+%?))?\s*\)/g,
  (_m, r, g, b, a) => (a ? `rgba(${r},${g},${b},${a.endsWith('%') ? parseFloat(a) / 100 : a})` : `rgb(${r},${g},${b})`));
const css = (name: string, fallback: string) => {
  const v = typeof document === 'undefined' ? '' : getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return legacy(v || fallback);
};
const rgb = (name: string, fallback: string) => { const v = css(name, ''); return v ? `rgb(${v.split(/[\s,]+/).join(',')})` : fallback; };

/** Any CSS colour expression the app uses, resolved to a colour ECharts can draw (cached per theme). */
let probe: HTMLSpanElement | null = null;
const resolved = new Map<string, string>();
export function color(c: string | undefined, fallback = '#3987e5'): string {
  if (!c) return fallback;
  if (!c.includes('var(') && !/\s\/\s/.test(c) && !/rgba?\(\s*\d+\s+\d+/.test(c)) return c;
  const hit = resolved.get(c);
  if (hit) return hit;
  if (typeof document === 'undefined') return fallback;
  if (!probe) { probe = document.createElement('span'); probe.style.display = 'none'; document.body.appendChild(probe); }
  probe.style.color = '';
  probe.style.color = c;
  const out = legacy(getComputedStyle(probe).color || '') || fallback;
  resolved.set(c, out);
  return out;
}

/** A drawable colour at the given opacity (hex, rgb() or rgba() in; rgba() out). */
export function alpha(c: string, a: number): string {
  const h = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(c);
  if (h) { const x = h[1].length === 3 ? h[1].split('').map((d) => d + d).join('') : h[1];
    return `rgba(${parseInt(x.slice(0, 2), 16)},${parseInt(x.slice(2, 4), 16)},${parseInt(x.slice(4, 6), 16)},${a})`; }
  const m = /^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)/i.exec(c);
  return m ? `rgba(${m[1]},${m[2]},${m[3]},${a})` : c;
}

/** A translucent colour flattened onto a background, as an opaque rgb() — for fills that sit on other fills. */
export function over(c: string, bg: string): string {
  const m = /rgba?\(([\d.]+),([\d.]+),([\d.]+)(?:,([\d.]+))?/.exec(alpha(c, 1) === c ? c : c.replace(/\s/g, ''));
  const b = /rgba?\(([\d.]+),([\d.]+),([\d.]+)/.exec(alpha(bg, 1));
  if (!m || !b) return c;
  const a = m[4] == null ? 1 : Number(m[4]);
  const mix = (i: number) => Math.round(Number(m[i]) * a + Number(b[i]) * (1 - a));
  return `rgb(${mix(1)},${mix(2)},${mix(3)})`;
}

/** Dark or light text, whichever reads on the given background colour. */
export function inkOn(bg: string): string {
  const x = alpha(bg, 1), m = /rgba\(([\d.]+),([\d.]+),([\d.]+)/.exec(x);
  if (!m) return '#fff';
  const [r, g, b] = [m[1], m[2], m[3]].map((v) => { const c = Number(v) / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.45 ? '#111418' : '#ffffff';
}

/** Colours and text styles from the app's tokens, so charts follow the theme. */
export function chartTheme() {
  const text = css('--text-secondary', '#9aa0a6'), muted = css('--text-tertiary', '#6b7280'), border = css('--border-subtle', '#2a2f37');
  return {
    series: [css('--viz-1', '#3987e5'), css('--viz-2', '#d95926'), css('--viz-3', '#199e70'), css('--viz-4', '#c98500')],
    muted: css('--viz-muted', 'rgba(190,190,190,.28)'), outcome: css('--viz-outcome', 'rgba(200,200,200,.1)'),
    text, textStrong: css('--text-primary', '#e5e7eb'), mutedText: muted, border, borderStrong: css('--border', '#2f3640'),
    surface: css('--surface-2', '#15181d'), surface1: css('--surface-1', '#0f1216'),
    red: rgb('--c-red', '#ef4444'), green: rgb('--c-green', '#22c55e'), amber: rgb('--c-amber', '#f59e0b'), accent: rgb('--c-bloomberg', '#f59e0b'),
    mono: css('--font-data', "'Geist Mono', 'JetBrains Mono', Menlo, monospace"), sans: css('--font-ui', "'Geist', Inter, system-ui, sans-serif"),
  };
}
export type ChartTheme = ReturnType<typeof chartTheme>;

/** Re-render on a light/dark switch so options built from the theme pick up the new colours. */
export function useChartTheme(): ChartTheme {
  const [, bump] = useState(0);
  useEffect(() => {
    const mo = new MutationObserver(() => { resolved.clear(); bump((n) => n + 1); });
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'class'] });
    return () => mo.disconnect();
  }, []);
  return chartTheme();
}

export function baseOption(t = chartTheme()): EChartsCoreOption {
  return {
    backgroundColor: 'transparent',
    animationDuration: 300,
    textStyle: { color: t.text, fontFamily: t.sans, fontSize: 11 },
    grid: { left: 48, right: 16, top: 36, bottom: 34, containLabel: false },
    tooltip: { backgroundColor: t.surface, borderColor: t.border, textStyle: { color: t.textStrong, fontSize: 11 }, confine: true,
      extraCssText: 'box-shadow:0 8px 24px rgba(0,0,0,.25);border-radius:8px;' },
    legend: { top: 4, left: 0, textStyle: { color: t.text, fontSize: 11 }, itemWidth: 14, itemHeight: 3, icon: 'roundRect', inactiveColor: t.mutedText },
    toolbox: { right: 0, top: 0, itemSize: 12, iconStyle: { borderColor: t.mutedText }, emphasis: { iconStyle: { borderColor: t.textStrong } },
      feature: { dataZoom: { yAxisIndex: 'none', title: { zoom: 'Zoom', back: 'Reset zoom' } }, restore: { title: 'Restore' },
        dataView: { readOnly: true, title: 'Data', lang: ['Data', 'Close', 'Refresh'], backgroundColor: t.surface, textColor: t.textStrong, textareaColor: t.surface },
        saveAsImage: { title: 'Save PNG', backgroundColor: t.surface, pixelRatio: 2 } } },
  };
}

export const axisStyle = (t = chartTheme()) => ({
  axisLine: { lineStyle: { color: t.border } }, axisTick: { show: false },
  axisLabel: { color: t.mutedText, fontSize: 10 }, splitLine: { lineStyle: { color: t.border, type: 'dashed' as const } },
  nameTextStyle: { color: t.mutedText, fontSize: 10 },
});

/** The chart's option over the base: legend, tooltip and toolbox merge one level deep so a chart keeps the theme. */
function withBase(option: EChartsCoreOption): EChartsCoreOption {
  const base = baseOption() as Record<string, any>, o = option as Record<string, any>;
  const out: Record<string, any> = { ...base, ...o };
  for (const k of ['legend', 'tooltip', 'toolbox']) if (o[k] && !Array.isArray(o[k])) out[k] = { ...base[k], ...o[k] };
  if (o.yAxis?.type === 'category') out.grid = { ...o.grid, left: 8, containLabel: true };   // size the label column to the labels
  if ((o.grid?.top ?? 36) < 28) out.toolbox = { ...out.toolbox, show: false };   // compact chart: no room above the plot
  return out;
}

// Canvas where the browser has one, SVG otherwise, so a chart never throws; test DOMs get the labelled container only.
const isTestDom = () => typeof navigator !== 'undefined' && /jsdom/i.test(navigator.userAgent);
let drawable: boolean | null = null;
const canDraw = () => {
  if (drawable == null) {
    try { drawable = !isTestDom() && !!document.createElement('canvas').getContext('2d'); } catch { drawable = false; }
  }
  return drawable;
};

export function EChart({ option, height = 300, group, onReady, ariaLabel, className, merge = false }: {
  option: EChartsCoreOption; height?: number; group?: string; onReady?: (c: echarts.ECharts) => void; ariaLabel?: string; className?: string;
  /** Update in place instead of redrawing (keeps running effects such as moving particles continuous between frames). */
  merge?: boolean;
}) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const latest = useRef(option);
  latest.current = option;
  const sig = useRef('');
  useEffect(() => {
    if (!el.current) return;
    if (isTestDom()) return;                      // jsdom: keep the labelled container, skip drawing
    let c: echarts.ECharts;
    try { c = echarts.init(el.current, undefined, { renderer: canDraw() ? 'canvas' : 'svg' }); } catch { return; }
    chart.current = c;
    if (group) { c.group = group; echarts.connect(group); }
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => { try { c.resize(); } catch { /* chart mid-update */ } }) : null;
    ro?.observe(el.current);
    // re-theme when the app's theme changes
    const mo = new MutationObserver(() => c.setOption(withBase(latest.current), { notMerge: true }));
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'class'] });
    try { c.setOption(withBase(latest.current), { notMerge: true }); sig.current = JSON.stringify(latest.current); } catch { /* bad option: leave blank */ }
    onReady?.(c);
    return () => { ro?.disconnect(); mo.disconnect(); c.dispose(); chart.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [group]);
  // Parents often rebuild an identical option (inline formatters); redraw only when its content changed, so a
  // re-render never resets the user's zoom or replays the animation. Functions are left out of the comparison.
  useEffect(() => {
    let next = '';
    try { next = JSON.stringify(option); } catch { next = String(Math.random()); }
    if (next === sig.current) return;
    sig.current = next;
    try { chart.current?.setOption(withBase(option), merge ? { notMerge: false, lazyUpdate: true } : { notMerge: true }); } catch { /* keep last frame */ }
  }, [option, merge]);
  return <div ref={el} className={className} style={{ height, width: '100%' }} role="img" aria-label={ariaLabel} />;
}
