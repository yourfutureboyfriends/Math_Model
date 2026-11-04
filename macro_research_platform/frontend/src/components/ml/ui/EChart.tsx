/**
 * Apache ECharts in React: themed from the app's CSS tokens (light/dark, re-themed on toggle), resized with its
 * container, optionally linked to other charts in a `group` (shared crosshair and zoom via echarts.connect), and
 * with a toolbox (save image, data view, zoom reset) on every chart.
 */
import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { BarChart, HeatmapChart, LineChart, ScatterChart } from 'echarts/charts';
import {
  DataZoomComponent, GridComponent, LegendComponent, MarkAreaComponent, MarkLineComponent, ToolboxComponent,
  TooltipComponent, VisualMapComponent, BrushComponent, AxisPointerComponent, TitleComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { EChartsCoreOption } from 'echarts/core';

echarts.use([LineChart, BarChart, ScatterChart, HeatmapChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent,
  ToolboxComponent, MarkAreaComponent, MarkLineComponent, VisualMapComponent, BrushComponent, AxisPointerComponent, TitleComponent, CanvasRenderer]);

/** ECharts parses only legacy colour syntax: turn `rgb(r g b / a)` into `rgba(r,g,b,a)`. */
const legacy = (c: string) => c.replace(/rgba?\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*(?:\/\s*([\d.]+%?))?\s*\)/g,
  (_m, r, g, b, a) => (a ? `rgba(${r},${g},${b},${a.endsWith('%') ? parseFloat(a) / 100 : a})` : `rgb(${r},${g},${b})`));
const css = (name: string, fallback: string) => {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return legacy(v || fallback);
};
const rgb = (name: string, fallback: string) => { const v = css(name, ''); return v ? `rgb(${v.split(' ').join(',')})` : fallback; };

/** Colours and text styles from the app's tokens, so charts follow the theme. */
export function chartTheme() {
  const text = css('--text-secondary', '#9aa0a6'), muted = css('--text-tertiary', '#6b7280'), border = css('--border-subtle', '#2a2f37');
  return {
    series: [css('--viz-1', '#3987e5'), css('--viz-2', '#d95926'), css('--viz-3', '#199e70'), css('--viz-4', '#c98500')],
    muted: css('--viz-muted', 'rgba(190,190,190,.28)'), outcome: css('--viz-outcome', 'rgba(200,200,200,.1)'),
    text, textStrong: css('--text-primary', '#e5e7eb'), mutedText: muted, border, surface: css('--surface-2', '#15181d'),
    red: rgb('--c-red', '#ef4444'), green: rgb('--c-green', '#22c55e'), amber: rgb('--c-amber', '#f59e0b'),
    font: css('--font-data', 'ui-monospace, SFMono-Regular, Menlo, monospace'),
  };
}

export function baseOption(t = chartTheme()): EChartsCoreOption {
  return {
    backgroundColor: 'transparent',
    textStyle: { color: t.text, fontFamily: 'Inter, system-ui, sans-serif', fontSize: 11 },
    grid: { left: 48, right: 16, top: 36, bottom: 34, containLabel: false },
    tooltip: { backgroundColor: t.surface, borderColor: t.border, textStyle: { color: t.textStrong, fontSize: 11 }, confine: true },
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

export function EChart({ option, height = 300, group, onReady, ariaLabel }: {
  option: EChartsCoreOption; height?: number; group?: string; onReady?: (c: echarts.ECharts) => void; ariaLabel?: string;
}) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const latest = useRef(option);
  latest.current = option;
  useEffect(() => {
    if (!el.current) return;
    const c = echarts.init(el.current, undefined, { renderer: 'canvas' });
    chart.current = c;
    if (group) { c.group = group; echarts.connect(group); }
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(el.current);
    // re-theme when the app's theme attribute changes
    const mo = new MutationObserver(() => c.setOption(withBase(latest.current), { notMerge: true }));
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    onReady?.(c);
    return () => { ro.disconnect(); mo.disconnect(); c.dispose(); chart.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [group]);
  useEffect(() => { chart.current?.setOption(withBase(option), { notMerge: true }); }, [option]);
  return <div ref={el} style={{ height, width: '100%' }} role="img" aria-label={ariaLabel} />;
}
