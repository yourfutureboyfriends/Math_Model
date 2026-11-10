// Section G Panel 2 — Yield Curve Explorer + Phase 2 Store Integration
// Interactive yield curve (Apache ECharts)

import { useMemo, useState } from 'react';
import { Card } from '@/components/ui/Card';
import { cn } from '@/lib/utils';
import { useMacroStore } from '@/store/macroStore';
import { useApiData } from '@/hooks/useApiData';
import { fmtRate, fmtProbability } from '@/utils/format';
import { EChart, alpha, axisStyle, color, useChartTheme } from '@/components/charts/EChart';

interface YieldPoint {
  tenor: number;
  yield: number;
}

interface YieldCurveData {
  country: string;
  points: YieldPoint[];
  spread2s10s?: number;
  spread3m10y?: number;
  spread5s30s?: number;
  spreadShort10y?: number | null;
  shortRate?: string | null;
  realYield10y?: number;
  shape: string;
  recessionProb?: number;
  history?: Record<string, { date: string; points: YieldPoint[] }> | null;
}

interface FixedIncomeData {
  yieldCurves: Record<string, YieldCurveData>;
  creditSpreads: Array<{
    name: string;
    spreadBps: number;
    signal: string;
  }>;
  realYieldSignal: string;
}

const COUNTRIES = [
  { code: 'US', name: 'United States' },
  { code: 'UK', name: 'United Kingdom' },
  { code: 'DE', name: 'Germany' },
  { code: 'JP', name: 'Japan' },
  { code: 'CA', name: 'Canada' },
  { code: 'AU', name: 'Australia' },
];

const bp = (v: number | null | undefined) => (v == null ? '--' : `${v > 0 ? '+' : ''}${Math.round(v)}bp`);

const TENOR_LABEL: [number, string][] = [[0.0027, 'ON'], [0.0833, '1M'], [0.25, '3M'], [0.5, '6M'], [1, '1Y'], [2, '2Y'],
  [3, '3Y'], [5, '5Y'], [7, '7Y'], [10, '10Y'], [20, '20Y'], [30, '30Y']];
const tenorLabel = (t: number) => TENOR_LABEL.find(([v]) => Math.abs(v - t) < 0.01)?.[1] ?? `${t}Y`;
const KEY_TENORS = new Set([0.25, 2, 10, 30]);

/** Yield curve on Apache ECharts: tenors evenly spaced (as on a terminal curve page), today's curve with labelled
 *  key tenors, 1M and 1Y ago dashed behind it, and a tooltip with each tenor's change in basis points. */
const PAST_STYLE: Record<string, { color: string; dash: number[]; width: number }> = {
  '1M ago': { color: '#9aa4b2', dash: [5, 4], width: 1.5 },
  '1Y ago': { color: '#5b6270', dash: [2, 3], width: 1.25 },
};

function CurveChart({ points, history }: { points: YieldPoint[]; history?: Record<string, { date: string; points: YieldPoint[] }> | null }) {
  const t = useChartTheme();
  const option = useMemo(() => {
    const past = Object.entries(history ?? {});
    const tenors = points.map((p) => p.tenor);
    const at = (ps: YieldPoint[]) => tenors.map((tn) => ps.find((q) => Math.abs(q.tenor - tn) < 1e-6)?.yield ?? null);
    const today = color('rgb(var(--c-bloomberg))', t.accent);
    const ax = axisStyle(t);
    return {
      legend: { top: 0, right: 90, data: ['Today', ...past.map(([l]) => l)] },
      grid: { left: 8, right: 16, top: 34, bottom: 6, containLabel: true },
      tooltip: { trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: t.mutedText, type: 'dashed' } },
        formatter: (ps: any[]) => {
          const i = ps[0]?.dataIndex ?? 0, now = points[i].yield;
          const rows = past.map(([l, h]) => { const q = at(h.points)[i]; if (q == null) return '';
            const d = Math.round((now - q) * 100); return `<div>vs ${l}: <b style="color:${d >= 0 ? t.red : t.green}">${d >= 0 ? '+' : ''}${d}bp</b> <span style="opacity:.6">(${q.toFixed(2)}%)</span></div>`; }).join('');
          return `<b>${tenorLabel(points[i].tenor)}</b> ${now.toFixed(2)}%${rows}`;
        } },
      xAxis: { type: 'category', data: tenors.map(tenorLabel), boundaryGap: false, ...ax, splitLine: { show: false }, axisLabel: { ...ax.axisLabel, fontFamily: t.mono } },
      yAxis: { type: 'value', scale: true, ...ax, axisLabel: { ...ax.axisLabel, fontFamily: t.mono, formatter: (v: number) => `${v.toFixed(2)}%` } },
      series: [
        ...past.map(([l, h]) => ({ name: l, type: 'line', data: at(h.points), showSymbol: false, connectNulls: true, z: 1,
          lineStyle: { color: PAST_STYLE[l]?.color ?? t.mutedText, width: PAST_STYLE[l]?.width ?? 1.25, type: PAST_STYLE[l]?.dash ?? [4, 3] },
          itemStyle: { color: PAST_STYLE[l]?.color ?? t.mutedText } })),
        { name: 'Today', type: 'line', data: points.map((p) => p.yield), z: 3, symbol: 'circle', symbolSize: 7,
          lineStyle: { color: today, width: 2.5 }, itemStyle: { color: today, borderColor: t.surface1, borderWidth: 2 },
          areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: alpha(today, 0.18) }, { offset: 1, color: alpha(today, 0) }] }, origin: 'start' },
          label: { show: true, position: 'top', fontSize: 10, fontFamily: t.mono, color: t.text,
            formatter: (p: any) => (KEY_TENORS.has(points[p.dataIndex].tenor) || points.length <= 3 ? p.value.toFixed(2) : '') } },
      ],
    };
  }, [points, history, t]);
  return <EChart option={option} height={230} ariaLabel="Yield curve: today against 1 month and 1 year ago" />;
}

export function YieldCurveSection() {
  const { data, loading } = useApiData<FixedIncomeData>('/api/rates');
  const [selectedCountry, setSelectedCountry] = useState('US');

  // Use macro store for loading state and regime context
  const storeLoading = useMacroStore((state) => state.meta.dataStatus === 'loading');
  const regime = useMacroStore((state) => state.regime);

  const curve = data?.yieldCurves?.[selectedCountry];

  if (loading || storeLoading) {
    return <div className="h-64 bg-surface-1 border border-border animate-pulse" />;
  }

  return (
    <Card title={`YIELD CURVE EXPLORER | Regime: ${regime.current ? regime.current.toUpperCase() : '—'}`}>
      <div className="space-y-4">
        {/* Country Tabs */}
        <div className="flex gap-1 overflow-x-auto">
          {COUNTRIES.map(c => (
            <button
              key={c.code}
              onClick={() => setSelectedCountry(c.code)}
              className={cn(
                'px-3 py-1 text-xs font-mono border transition-colors',
                selectedCountry === c.code
                  ? 'bg-bloomberg text-bg border-bloomberg'
                  : 'bg-surface-2 text-text-secondary border-border-subtle hover:bg-surface-3'
              )}
            >
              {c.code}
            </button>
          ))}
        </div>

        {/* Yield Curve Chart */}
        <div className="border border-border-subtle bg-surface-2 p-3">
          {curve && curve.points.length >= 2
            ? <CurveChart points={curve.points} history={curve.history} />
            : <div className="h-40 flex items-center justify-center text-2xs text-text-tertiary">No curve data for {selectedCountry}</div>}
          {curve && <div className="mt-1 text-[10px] text-text-tertiary">{(curve as any).source}</div>}
        </div>

        {/* Key Metrics - FIXED (BUG 2): Use != null check instead of truthy to allow 0 values */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          <div className="p-2 border border-border-subtle bg-surface-2">
            <div className="text-2xs text-text-tertiary uppercase">2s10s Spread</div>
            <div className={cn(
              'font-mono font-bold',
              curve?.spread2s10s != null && curve.spread2s10s < 0 ? 'text-red' : 'text-text-primary'
            )}>
              {bp(curve?.spread2s10s)}
            </div>
            <div className="text-2xs text-text-tertiary capitalize">{curve?.shape ?? '—'}</div>
          </div>

          <div className="p-2 border border-border-subtle bg-surface-2">
            {/* Without a fresh 3M point (e.g. UK) the short end is an overnight rate (SONIA),
                labelled as such rather than shown as a 3M spread. */}
            <div className="text-2xs text-text-tertiary uppercase">
              {curve?.spread3m10y == null && curve?.spreadShort10y != null
                ? `${curve.shortRate ?? 'ON'}-10Y Spread` : '3m10y Spread'}
            </div>
            <div className="font-mono font-bold text-text-primary">
              {curve?.spread3m10y != null ? bp(curve.spread3m10y) : bp(curve?.spreadShort10y)}
            </div>
            <div className="text-2xs text-text-tertiary">
              {curve?.spread3m10y == null && curve?.spreadShort10y != null ? 'Overnight vs 10Y' : 'Recession Predictor'}
            </div>
          </div>

          <div className="p-2 border border-border-subtle bg-surface-2">
            <div className="text-2xs text-text-tertiary uppercase">Real Yield 10Y (TIPS)</div>
            <div className="font-mono font-bold text-text-primary">
              {curve?.realYield10y != null ? fmtRate(curve.realYield10y) : '--'}
            </div>
            <div className="text-2xs text-text-tertiary">{data?.realYieldSignal}</div>
          </div>

          <div className="p-2 border border-border-subtle bg-surface-2">
            <div className="text-2xs text-text-tertiary uppercase">Recession Prob</div>
            <div className={cn(
              'font-mono font-bold',
              curve?.recessionProb != null && curve.recessionProb > 0.3 ? 'text-red' : 'text-text-primary'
            )}>
              {curve?.recessionProb != null ? fmtProbability(curve.recessionProb) : '--'}
            </div>
            <div className="text-2xs text-text-tertiary">Estrella-Mishkin</div>
          </div>
        </div>
      </div>
    </Card>
  );
}
