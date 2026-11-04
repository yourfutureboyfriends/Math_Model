/**
 * Semicircular gauge (Apache ECharts) for a single reading on a banded scale — risk regime, analyst consensus.
 * Bands are [upTo, colour] in scale units; the needle and value are drawn by the library, colours come from the
 * app's tokens.
 */
import { useMemo } from 'react';
import { EChart, color, useChartTheme } from './EChart';

export function Gauge({ value, min, max, bands, minLabel, maxLabel, height = 130, ariaLabel }: {
  value: number; min: number; max: number; bands: [number, string][]; minLabel?: string; maxLabel?: string; height?: number; ariaLabel: string;
}) {
  const t = useChartTheme();
  const option = useMemo(() => ({
    legend: { show: false }, toolbox: { show: false }, tooltip: { show: false },
    series: [{
      type: 'gauge', startAngle: 180, endAngle: 0, min, max, radius: '150%', center: ['50%', '88%'], splitNumber: 4,
      axisLine: { lineStyle: { width: 12, color: bands.map(([upTo, c]) => [(upTo - min) / (max - min), color(c)]) } },
      pointer: { icon: 'path://M2.9,0.7L2.9,0.7c1.4,0,2.6,1.2,2.6,2.6v115c0,1.4-1.2,2.6-2.6,2.6l0,0c-1.4,0-2.6-1.2-2.6-2.6V3.3C0.3,1.9,1.4,0.7,2.9,0.7z',
        length: '62%', width: 5, offsetCenter: [0, '-6%'], itemStyle: { color: t.textStrong } },
      anchor: { show: true, size: 10, itemStyle: { color: t.textStrong, borderColor: t.surface1, borderWidth: 2 } },
      axisTick: { show: false }, splitLine: { show: false },
      axisLabel: { show: false },
      detail: { show: false }, title: { show: false },
      data: [{ value: Math.max(min, Math.min(max, value)) }],
      animationDuration: 600,
    }],
  }), [value, min, max, bands, t]);
  return (
    <div>
      <EChart option={option} height={height} ariaLabel={ariaLabel} />
      {(minLabel || maxLabel) && <div className="flex justify-between px-1 text-[10px] text-text-tertiary"><span>{minLabel}</span><span>{maxLabel}</span></div>}
    </div>
  );
}
