// Range (forest) plot on Apache ECharts — point estimates with their uncertainty interval on one shared axis,
// so outcomes and their spread compare at a glance (scenarios, forecasts, model estimates). Zero line marked;
// the estimate and interval are printed beside each row and the tooltip gives the note.

import { useMemo } from 'react';
import { EChart, axisStyle, useChartTheme } from '@/components/charts/EChart';

export interface RangeDatum { label: string; value: number; lo: number; hi: number; note?: string }

export function RangePlot({ data, fmt = (v) => v.toFixed(2), title }:
  { data: RangeDatum[]; fmt?: (v: number) => string; title?: string; labelWidth?: string }) {
  const t = useChartTheme();
  const option = useMemo(() => {
    const ax = axisStyle(t);
    const tone = (v: number) => (v >= 0 ? t.green : t.red);
    const rows = [...data].reverse();                    // first item on top
    return {
      legend: { show: false }, toolbox: { show: false },
      grid: { left: 8, right: 8, top: 6, bottom: 4, containLabel: true },
      tooltip: { trigger: 'item', formatter: (q: any) => { const d = rows[q.dataIndex];
        return `<b>${d.label}</b><br/>${fmt(d.value)} <span style="opacity:.6">[${fmt(d.lo)}, ${fmt(d.hi)}]</span>${d.note ? `<br/><span style="opacity:.7">${d.note}</span>` : ''}`; } },
      xAxis: { type: 'value', min: (v: any) => Math.min(0, v.min), max: (v: any) => Math.max(0, v.max), ...ax, axisLabel: { ...ax.axisLabel, fontFamily: t.mono, formatter: (v: number) => fmt(v) } },
      yAxis: [{ type: 'category', data: rows.map((d) => d.label), ...ax, axisLine: { show: false }, splitLine: { show: false }, axisLabel: { ...ax.axisLabel, color: t.text, fontSize: 11 } },
        { type: 'category', data: rows.map((d) => `${fmt(d.value)}  [${fmt(d.lo)}, ${fmt(d.hi)}]`), position: 'right', ...ax, axisLine: { show: false }, splitLine: { show: false },
          axisLabel: { ...ax.axisLabel, fontFamily: t.mono, color: t.text } }],
      series: [
        { type: 'custom', silent: true, z: 1,                                          // interval whiskers with end caps
          renderItem: (_: any, api: any) => {
            const y = api.coord([0, api.value(0)])[1], a = api.coord([api.value(1), 0])[0], b = api.coord([api.value(2), 0])[0];
            const c = tone(api.value(3)), cap = 5;
            const style = { stroke: c, lineWidth: 1.5, opacity: 0.85 };
            return { type: 'group', children: [
              { type: 'line', shape: { x1: a, y1: y, x2: b, y2: y }, style },
              { type: 'line', shape: { x1: a, y1: y - cap, x2: a, y2: y + cap }, style },
              { type: 'line', shape: { x1: b, y1: y - cap, x2: b, y2: y + cap }, style }] };
          },
          encode: { x: [1, 2], y: 0 },
          data: rows.map((d, i) => [i, d.lo, d.hi, d.value]) },
        { type: 'scatter', z: 3, symbolSize: 10, data: rows.map((d) => ({ value: [d.value, d.label], itemStyle: { color: tone(d.value), borderColor: t.surface1, borderWidth: 2 } })),
          markLine: { symbol: 'none', silent: true, data: [{ xAxis: 0 }], lineStyle: { color: t.borderStrong, type: 'solid' }, label: { show: false } } },
      ],
    };
  }, [data, fmt, t]);
  if (!data.length) return null;
  return (
    <div>
      {title && <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">{title}</div>}
      <EChart option={option} height={Math.max(90, data.length * 30 + 30)} ariaLabel={title ?? 'Estimates with 95% intervals'} />
    </div>
  );
}
