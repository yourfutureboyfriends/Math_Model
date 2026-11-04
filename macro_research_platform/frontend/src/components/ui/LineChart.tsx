// Multi-series line chart on Apache ECharts: legend (click to hide a series), end labels that never overlap,
// axis crosshair tooltip, drag-to-zoom (double-click resets), log scale, dashed baseline and labelled reference
// levels, toolbox to save a PNG or read the data. Date-indexed charts add period presets, interval resampling
// and typed date ranges above the plot.

import { useEffect, useMemo, useRef, useState } from 'react';
import { EChart, alpha, axisStyle, color, inkOn, useChartTheme, type ECharts } from '@/components/charts/EChart';

export interface ChartLine { key: string; label: string; color: string }

interface Props {
  rows: Record<string, any>[];
  x: string;                         // row key holding the x label ("YYYY-MM" dates get calendar ticks)
  lines: ChartLine[];
  height?: number;
  fmt?: (v: number) => string;       // value format (tooltip, end labels)
  axisFmt?: (v: number) => string;  // y-axis tick format (defaults to fmt)
  log?: boolean;                     // log y scale (values must be > 0)
  baseline?: number;                 // dashed reference line (e.g. 0, or 1 for growth of $1)
  refs?: { value: number; label: string; color?: string }[];   // labelled horizontal levels
}

const NO_REFS: { value: number; label: string; color?: string }[] = [];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** Compact axis label for a date-like x value: "2019" on long monthly spans, "Mar 24" otherwise. */
function dateLabel(v: string, longSpan: boolean): string {
  if (/^\d{4}-\d{2}(-\d{2})?$/.test(v)) {
    const m = Number(v.slice(5, 7)) - 1;
    return longSpan ? v.slice(0, 4) : `${MONTHS[m]} ${v.slice(2, 4)}`;
  }
  return v;
}

// ── Period / interval controls ───────────────────────────────────────────────
// Charts whose x values are dates get period presets and (for daily data) daily / weekly /
// monthly resampling. Growth-of-1 series (baseline 1) are re-based to 1 at the start of the
// chosen period so the lines stay comparable; other series are shown as is.
const RANGES: { key: string; label: string; days: number }[] = [
  { key: '1m', label: '1M', days: 31 }, { key: '3m', label: '3M', days: 92 }, { key: '6m', label: '6M', days: 183 },
  { key: 'ytd', label: 'YTD', days: -1 }, { key: '1y', label: '1Y', days: 366 }, { key: '2y', label: '2Y', days: 731 }, { key: '3y', label: '3Y', days: 1096 },
  { key: '5y', label: '5Y', days: 1827 }, { key: '10y', label: '10Y', days: 3653 }, { key: 'all', label: 'All', days: 0 },
];
const isDaily = (v: unknown) => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v);
const isMonthly = (v: unknown) => typeof v === 'string' && /^\d{4}-\d{2}$/.test(v);

export function LineChart(props: Props & { controls?: boolean; defaultRange?: string }) {
  const { rows, x, controls = true, lines, baseline } = props;
  const first = rows[0]?.[x], last = rows[rows.length - 1]?.[x];
  const daily = isDaily(first) && isDaily(last);
  const monthly = isMonthly(first) && isMonthly(last);
  const enabled = controls && rows.length > 8 && (daily || monthly);
  // a long history can start zoomed in (e.g. 5Y) so one extreme episode doesn't flatten the rest
  // an unknown preset (e.g. '1Y' instead of '1y') falls back to the full history rather than crashing
  const [range, setRange] = useState(() => { const k = (props.defaultRange ?? 'all').toLowerCase(); return RANGES.some((q) => q.key === k) ? k : 'all'; });
  const [freq, setFreq] = useState<'D' | 'W' | 'M'>('D');
  // custom window: typed dates or a drag-to-zoom selection (overrides the preset)
  const [custom, setCustom] = useState<{ from: string; to: string } | null>(null);
  const spanDays = useMemo(() => {
    if (!enabled) return 0;
    const a = new Date(`${String(first).slice(0, 10)}${monthly ? '-01' : ''}T00:00:00`).getTime();
    const b = new Date(`${String(last).slice(0, 10)}${monthly ? '-28' : ''}T00:00:00`).getTime();
    return (b - a) / 864e5;
  }, [enabled, first, last, monthly]);
  const presets = RANGES.filter((q) => q.days <= 0 || q.days < spanDays * 1.15);     // only periods the history covers

  const view = useMemo(() => {
    if (!enabled) return rows;
    let out: Record<string, any>[];
    if (custom) {
      out = rows.filter((row) => String(row[x]) >= custom.from && String(row[x]) <= custom.to);
    } else {
      const end = new Date(`${String(last).slice(0, 7)}${monthly ? '-28' : String(last).slice(7)}T00:00:00`);
      const r = RANGES.find((q) => q.key === range) ?? RANGES[RANGES.length - 1];
      let cutoff: string | null = null;
      if (r.days > 0) cutoff = new Date(end.getTime() - r.days * 864e5).toISOString().slice(0, monthly ? 7 : 10);
      if (r.days === -1) cutoff = `${end.getFullYear()}-01${monthly ? '' : '-01'}`;
      out = cutoff ? rows.filter((row) => String(row[x]) >= cutoff!) : rows;
    }
    if (daily && freq !== 'D') {
      const keyOf = (d: string) => {
        if (freq === 'M') return d.slice(0, 7);
        const t = new Date(`${d}T00:00:00`);
        const monday = new Date(t.getTime() - ((t.getDay() + 6) % 7) * 864e5);
        return monday.toISOString().slice(0, 10);
      };
      const lastOf = new Map<string, Record<string, any>>();
      out.forEach((row) => lastOf.set(keyOf(String(row[x])), row));         // period's last observation
      out = Array.from(lastOf.values());
    }
    if (baseline === 1 && out.length && out !== rows) {                       // re-base growth-of-1 lines
      const base = out[0];
      out = out.map((row) => {
        const o: Record<string, any> = { ...row };
        lines.forEach((l) => { const b = Number(base[l.key]); const v = Number(row[l.key]); if (b > 0 && Number.isFinite(v)) o[l.key] = v / b; });
        return o;
      });
    }
    return out;
  }, [enabled, rows, x, range, freq, daily, monthly, last, baseline, lines, custom]);

  if (!enabled) return <LineChartCore {...props} />;
  const btn = (on: boolean) => `px-2 py-0.5 text-[10px] font-medium rounded-[5px] transition-colors ${on ? 'bg-surface-1 text-text-primary shadow-sm ring-1 ring-border' : 'text-text-tertiary hover:text-text-primary'}`;
  const dateType = monthly ? 'month' : 'date';
  const lo = String(first).slice(0, monthly ? 7 : 10), hi = String(last).slice(0, monthly ? 7 : 10);
  return (
    <div>
      <div className="flex flex-wrap items-center gap-1.5 mb-1">
        <div className="flex gap-0.5 p-0.5 rounded-md bg-surface-2/70" role="group" aria-label="Period">
          {presets.map((q) => (
            <button key={q.key} onClick={() => { setRange(q.key); setCustom(null); }} aria-pressed={!custom && range === q.key} className={btn(!custom && range === q.key)}>{q.label}</button>
          ))}
        </div>
        {daily && (
          <div className="flex gap-0.5 p-0.5 rounded-md bg-surface-2/70" role="group" aria-label="Interval">
            {([['D', 'Daily'], ['W', 'Weekly'], ['M', 'Monthly']] as const).map(([k, l]) => (
              <button key={k} onClick={() => setFreq(k)} aria-pressed={freq === k} className={btn(freq === k)}>{l}</button>
            ))}
          </div>
        )}
        <div className="flex items-center gap-1 text-[10px] text-text-tertiary" role="group" aria-label="Custom range">
          <input type={dateType} min={lo} max={hi} value={custom?.from ?? ''} aria-label="From"
            onChange={(e) => e.target.value && setCustom({ from: e.target.value, to: custom?.to ?? hi })}
            className="bg-transparent border border-border px-1 py-0.5 font-mono text-text-secondary w-[7.6rem]" />
          <span>–</span>
          <input type={dateType} min={lo} max={hi} value={custom?.to ?? ''} aria-label="To"
            onChange={(e) => e.target.value && setCustom({ from: custom?.from ?? lo, to: e.target.value })}
            className="bg-transparent border border-border px-1 py-0.5 font-mono text-text-secondary w-[7.6rem]" />
          {custom && <button onClick={() => setCustom(null)} className="px-1.5 py-0.5 border border-border text-text-secondary hover:text-text-primary">Reset</button>}
        </div>
        <span className="text-[10px] text-text-tertiary">{custom ? `${custom.from} → ${custom.to}` : 'drag on the chart to zoom'}</span>
        {baseline === 1 && (custom || range !== 'all') && <span className="text-[10px] text-text-tertiary">· re-based to 1 at the start</span>}
      </div>
      {view.length > 1 ? <LineChartCore {...props} rows={view}
          onZoom={(a, b) => setCustom({ from: a.slice(0, monthly ? 7 : 10), to: b.slice(0, monthly ? 7 : 10) })} onReset={() => setCustom(null)} />
        : <div className="text-2xs text-text-tertiary p-3">No data in this period.</div>}
    </div>
  );
}

function LineChartCore({ rows, x, lines, height = 180, fmt = (v) => v.toFixed(2), axisFmt, log = false, baseline, refs = NO_REFS, onZoom, onReset }:
  Props & { onZoom?: (from: string, to: string) => void; onReset?: () => void }) {
  const t = useChartTheme();
  const chart = useRef<ECharts | null>(null);
  const cb = useRef({ onZoom, onReset, rows, x });
  cb.current = { onZoom, onReset, rows, x };
  const zoomable = !!onZoom;
  const option = useMemo(() => {
    const cats = rows.map((r) => String(r[x]));
    const first = cats[0] ?? '', last = cats[cats.length - 1] ?? '';
    const years = (Number(last.slice(0, 4)) - Number(first.slice(0, 4))) || 0;
    const longSpan = /^\d{4}-\d{2}/.test(first) && years > 3;
    const lastRow = rows[rows.length - 1] ?? {};
    const endLen = Math.max(0, ...lines.map((l) => (typeof lastRow[l.key] === 'number' ? fmt(lastRow[l.key]).length : 0)));
    const finite = rows.flatMap((r) => lines.map((l) => r[l.key])).filter((v): v is number => typeof v === 'number' && Number.isFinite(v) && (!log || v > 0));
    const extra = [...(baseline !== undefined ? [baseline] : []), ...refs.map((r) => r.value)].filter((v) => !log || v > 0);
    const lo = Math.min(...finite, ...extra), hi = Math.max(...finite, ...extra);
    const val = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) && (!log || v > 0) ? v : null);
    const marks = [
      ...(baseline !== undefined ? [{ yAxis: baseline, lineStyle: { color: t.mutedText, type: 'dashed' as const }, label: { show: false } }] : []),
      ...refs.map((r) => ({ yAxis: r.value, lineStyle: { color: color(r.color, t.mutedText), type: [4, 3] as any },
        label: { show: true, position: 'insideStartTop' as const, formatter: `${r.label} ${fmt(r.value)}`, color: color(r.color, t.mutedText), fontSize: 10, fontFamily: t.mono } })),
    ];
    const series = lines.map((l, k) => {
      const c = color(l.color);
      return {
        name: l.label, type: 'line', data: rows.map((r) => val(r[l.key])), showSymbol: false, symbol: 'circle', symbolSize: 8, connectNulls: false,
        lineStyle: { width: 2, color: c }, itemStyle: { color: c, borderColor: t.surface1, borderWidth: 2 }, emphasis: { focus: 'series' as const },
        endLabel: { show: true, formatter: (p: any) => (p.value == null ? '' : fmt(p.value)), color: inkOn(c), backgroundColor: c, padding: [2, 4], borderRadius: 3, fontSize: 10, fontFamily: t.mono, distance: 6 },
        labelLayout: { moveOverlap: 'shiftY' as const },
        ...(k === 0 && lines.length <= 2 ? { areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: alpha(c, 0.22) }, { offset: 1, color: alpha(c, 0) }] }, origin: 'start' as const } } : {}),
        ...(k === 0 && marks.length ? { markLine: { symbol: 'none', silent: true, data: marks } } : {}),
      };
    });
    const ax = axisStyle(t);
    return {
      legend: { type: 'scroll', top: 0, left: 0, right: 90, data: lines.map((l) => l.label), itemHeight: 8, itemWidth: 8, icon: 'circle' },
      grid: { left: 8, right: endLen * 6.4 + 22, top: 32, bottom: 6, containLabel: true },
      tooltip: { trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: t.mutedText, type: 'dashed' } }, order: 'valueDesc',
        valueFormatter: (v: number) => (v == null ? '—' : fmt(v)) },
      xAxis: { type: 'category', data: cats, boundaryGap: false, ...ax, splitLine: { show: false },
        axisLabel: { ...ax.axisLabel, fontFamily: t.mono, hideOverlap: true, formatter: (v: string) => dateLabel(v, longSpan) } },
      yAxis: { type: log ? 'log' : 'value', scale: !log, ...(log && Number.isFinite(lo) ? { min: lo / 1.08, max: hi * 1.08, logBase: hi / lo > 50 ? 10 : 2 } : {}), ...ax, axisLabel: { ...ax.axisLabel, fontFamily: t.mono, formatter: (v: number) => (axisFmt ?? fmt)(v) } },
      dataZoom: zoomable ? [{ type: 'inside', xAxisIndex: 0, zoomOnMouseWheel: 'shift', moveOnMouseWheel: false, filterMode: 'none' }] : [],
      toolbox: { top: 0, feature: { ...(zoomable ? { dataZoom: { yAxisIndex: 'none', title: { zoom: 'Drag to zoom', back: 'Back' } } } : {}),
        dataView: { readOnly: true, title: 'Data', lang: ['Data', 'Close', 'Refresh'], backgroundColor: t.surface, textColor: t.textStrong, textareaColor: t.surface },
        saveAsImage: { title: 'Save PNG', backgroundColor: t.surface, pixelRatio: 2 } } },
      series,
    };
  }, [rows, x, lines, fmt, axisFmt, log, baseline, refs, zoomable, t]);
  // drag on the plot selects a window: keep the zoom-select cursor on after every redraw
  useEffect(() => {
    const c = chart.current;
    if (c && zoomable) c.dispatchAction({ type: 'takeGlobalCursor', key: 'dataZoomSelect', dataZoomSelectActive: true });
  }, [option, zoomable]);
  const onReady = (c: ECharts) => {
    chart.current = c;
    c.on('datazoom', (e: any) => {
      const { onZoom: z, rows: rs, x: xk } = cb.current;
      const b0 = e?.batch?.[0] ?? e ?? {};
      const last = rs.length - 1;
      // the drag-select reports values; the inside zoom reports percentages
      const a = Math.max(0, Math.round(b0.startValue ?? ((b0.start ?? 0) / 100) * last));
      const b = Math.min(last, Math.round(b0.endValue ?? ((b0.end ?? 100) / 100) * last));
      if (z && b - a >= 2 && (a > 0 || b < last)) z(String(rs[a][xk]), String(rs[b][xk]));
    });
    c.getZr().on('dblclick', () => cb.current.onReset?.());
    if (onZoom) c.dispatchAction({ type: 'takeGlobalCursor', key: 'dataZoomSelect', dataZoomSelectActive: true });
  };
  if (rows.length < 2) return <div className="text-2xs text-text-tertiary p-3" style={{ height }}>Not enough data to chart.</div>;
  return <EChart option={option} height={height + 30} onReady={onReady} ariaLabel={`Line chart: ${lines.map((l) => l.label).join(', ')}`} />;
}
