// Section G Panel 2 — Yield Curve Explorer + Phase 2 Store Integration
// Interactive yield curve visualization using format library

import { useEffect, useRef, useState } from 'react';
import { Card } from '@/components/ui/Card';
import { cn } from '@/lib/utils';
import { useMacroStore } from '@/store/macroStore';
import { useApiData } from '@/hooks/useApiData';
import { fmtRate, fmtProbability } from '@/utils/format';

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

/** Yield curve in real pixels: sqrt maturity axis (short end readable), y-axis fitted to the
 *  data in 25/50bp steps, labels at key tenors, hover readout for any point. */
function CurveChart({ points }: { points: YieldPoint[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(0);
  const [hover, setHover] = useState<number | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.round(e.contentRect.width)));
    ro.observe(el);
    setW(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  const H = 200, L = 46, R = 16, T = 18, B = 24;
  const ys = points.map((p) => p.yield);
  const span = Math.max(...ys) - Math.min(...ys);
  const step = span > 2 ? 0.5 : span > 0.8 ? 0.25 : 0.1;
  const lo = Math.floor((Math.min(...ys) - step * 0.3) / step) * step;
  const hi = Math.ceil((Math.max(...ys) + step * 0.3) / step) * step;
  const ticks: number[] = [];
  for (let v = lo; v <= hi + 1e-9; v += step) ticks.push(Math.round(v * 100) / 100);
  const tMax = Math.max(...points.map((p) => p.tenor));
  const sx = (t: number) => L + (Math.sqrt(t) / Math.sqrt(tMax)) * (W - L - R);
  const sy = (v: number) => T + (1 - (v - lo) / (hi - lo || 1)) * (H - T - B);
  // x labels: every tenor present, skipping any closer than 26px to the previous one
  const xl: YieldPoint[] = [];
  points.forEach((p) => { if (!xl.length || sx(p.tenor) - sx(xl[xl.length - 1].tenor) >= 26) xl.push(p); });
  const hp = hover !== null ? points[hover] : null;

  return (
    <div ref={ref} className="relative w-full" style={{ height: H }}>
      {W > 0 && (
        <svg width={W} height={H} className="block select-none" onMouseLeave={() => setHover(null)}
          onMouseMove={(e) => {
            const px = e.clientX - e.currentTarget.getBoundingClientRect().left;
            let best = 0;
            points.forEach((p, i) => { if (Math.abs(sx(p.tenor) - px) < Math.abs(sx(points[best].tenor) - px)) best = i; });
            setHover(best);
          }}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={L} x2={W - R} y1={sy(t)} y2={sy(t)} stroke="var(--border-subtle)" />
              <text x={L - 6} y={sy(t) + 3.5} fontSize={10} textAnchor="end" fill="var(--text-tertiary)" className="font-mono">{t.toFixed(step < 0.25 ? 1 : 2)}%</text>
            </g>
          ))}
          <line x1={L} x2={W - R} y1={H - B} y2={H - B} stroke="var(--border)" />
          {xl.map((p) => (
            <text key={p.tenor} x={sx(p.tenor)} y={H - 7} fontSize={10} textAnchor="middle" fill="var(--text-tertiary)" className="font-mono">{tenorLabel(p.tenor)}</text>
          ))}
          <path d={points.map((p, i) => `${i ? 'L' : 'M'}${sx(p.tenor).toFixed(1)},${sy(p.yield).toFixed(1)}`).join('')}
            fill="none" stroke="var(--bloomberg)" strokeWidth={2} strokeLinejoin="round" />
          {points.map((p, i) => (
            <g key={p.tenor}>
              <circle cx={sx(p.tenor)} cy={sy(p.yield)} r={hover === i ? 4.5 : 3} fill="var(--bloomberg)" stroke="var(--surface-2)" strokeWidth={1.5} />
              {(KEY_TENORS.has(p.tenor) || points.length <= 3) && hover !== i && (
                <text x={sx(p.tenor)} y={sy(p.yield) - 8} fontSize={10} textAnchor="middle" fill="var(--text-secondary)" className="font-mono">{p.yield.toFixed(2)}</text>
              )}
            </g>
          ))}
          {hp && <line x1={sx(hp.tenor)} x2={sx(hp.tenor)} y1={T} y2={H - B} stroke="var(--text-tertiary)" strokeDasharray="2 2" pointerEvents="none" />}
        </svg>
      )}
      {hp && W > 0 && (
        <div className="pointer-events-none absolute top-0 px-2 py-1 bg-surface-3/95 border border-border text-2xs font-mono shadow-lg"
          style={sx(hp.tenor) > W * 0.6 ? { right: W - sx(hp.tenor) + 8 } : { left: sx(hp.tenor) + 8 }}>
          <span className="text-text-tertiary">{tenorLabel(hp.tenor)}</span> <span className="text-text-primary">{hp.yield.toFixed(2)}%</span>
        </div>
      )}
    </div>
  );
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
            ? <CurveChart points={curve.points} />
            : <div className="h-40 flex items-center justify-center text-2xs text-text-tertiary">No curve data for {selectedCountry}</div>}
          {curve && <div className="mt-1 text-[10px] text-text-tertiary">{(curve as any).source}</div>}
        </div>

        {/* Key Metrics - FIXED (BUG 2): Use != null check instead of truthy to allow 0 values */}
        <div className="grid grid-cols-4 gap-3 text-xs">
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
