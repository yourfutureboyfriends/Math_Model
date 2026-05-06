// Section G Panel 2 — Yield Curve Explorer + Phase 2 Store Integration
// Interactive yield curve visualization using format library

import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/Card';
import { cn } from '@/lib/utils';
import { useMacroStore } from '@/store/macroStore';
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

export function YieldCurveSection() {
  const [data, setData] = useState<FixedIncomeData | null>(null);
  const [selectedCountry, setSelectedCountry] = useState('US');
  const [loading, setLoading] = useState(true);

  // Use macro store for loading state and regime context
  const storeLoading = useMacroStore((state) => state.meta.dataStatus === 'loading');
  const regime = useMacroStore((state) => state.regime);

  useEffect(() => {
    fetch('/api/rates')
      .then(r => r.json())
      .then(d => {
        setData(d);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const curve = data?.yieldCurves?.[selectedCountry];

  // SVG chart dimensions
  const width = 600;
  const height = 200;
  const padding = { top: 20, right: 40, bottom: 40, left: 50 };

  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  // Scale functions
  const maxYield = Math.max(...(curve?.points.map(p => p.yield) || [5]), 5);
  const minYield = Math.min(...(curve?.points.map(p => p.yield) || [0]), 0);
  const yieldRange = maxYield - minYield || 1;

  const xScale = (tenor: number) => (tenor / 30) * chartWidth;
  const yScale = (yield_: number) => chartHeight - ((yield_ - minYield) / yieldRange) * chartHeight;

  // Generate SVG path
  const pathData = curve?.points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${xScale(p.tenor)} ${yScale(p.yield)}`)
    .join(' ');

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
        <div className="border border-border-subtle bg-surface-2 p-4">
          <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`}>
            <g transform={`translate(${padding.left}, ${padding.top})`}>
              {/* Grid lines */}
              {[0, 1, 2, 3, 4, 5].map(tick => (
                <g key={tick}>
                  <line
                    x1={0}
                    y1={yScale(minYield + (yieldRange * tick) / 5)}
                    x2={chartWidth}
                    y2={yScale(minYield + (yieldRange * tick) / 5)}
                    stroke="var(--border-subtle)"
                    strokeWidth={0.5}
                    strokeDasharray="2,2"
                  />
                  <text
                    x={-10}
                    y={yScale(minYield + (yieldRange * tick) / 5)}
                    fill="var(--text-tertiary)"
                    fontSize="10"
                    textAnchor="end"
                    dominantBaseline="middle"
                  >
                    {fmtRate(minYield + (yieldRange * tick) / 5)}
                  </text>
                </g>
              ))}

              {/* X-axis labels */}
              {['1Y', '5Y', '10Y', '20Y', '30Y'].map((label, i) => {
                const tenor = [1, 5, 10, 20, 30][i];
                return (
                  <text
                    key={label}
                    x={xScale(tenor)}
                    y={chartHeight + 20}
                    fill="var(--text-tertiary)"
                    fontSize="10"
                    textAnchor="middle"
                  >
                    {label}
                  </text>
                );
              })}

              {/* Yield curve */}
              {pathData && (
                <path
                  d={pathData}
                  stroke="var(--bloomberg)"
                  strokeWidth={2}
                  fill="none"
                  vectorEffect="non-scaling-stroke"
                />
              )}

              {/* Data points */}
              {curve?.points.map((p, i) => (
                <circle
                  key={i}
                  cx={xScale(p.tenor)}
                  cy={yScale(p.yield)}
                  r={3}
                  fill="var(--bloomberg)"
                />
              ))}
            </g>
          </svg>
        </div>

        {/* Key Metrics - FIXED (BUG 2): Use != null check instead of truthy to allow 0 values */}
        <div className="grid grid-cols-4 gap-3 text-xs">
          <div className="p-2 border border-border-subtle bg-surface-2">
            <div className="text-2xs text-text-tertiary uppercase">2s10s Spread</div>
            <div className={cn(
              'font-mono font-bold',
              curve?.spread2s10s != null && curve.spread2s10s < 0 ? 'text-red' : 'text-text-primary'
            )}>
              {curve?.spread2s10s != null ? fmtRate(curve.spread2s10s / 100) : '--'}
            </div>
            <div className="text-2xs text-text-tertiary">{curve?.shape}</div>
          </div>

          <div className="p-2 border border-border-subtle bg-surface-2">
            <div className="text-2xs text-text-tertiary uppercase">3m10y Spread</div>
            <div className="font-mono font-bold text-text-primary">
              {curve?.spread3m10y != null ? fmtRate(curve.spread3m10y / 100) : '--'}
            </div>
            <div className="text-2xs text-text-tertiary">Recession Predictor</div>
          </div>

          <div className="p-2 border border-border-subtle bg-surface-2">
            <div className="text-2xs text-text-tertiary uppercase">Real Yield 10Y</div>
            <div className="font-mono font-bold text-text-primary">
              {curve?.realYield10y != null ? fmtRate(curve.realYield10y / 100) : '--'}
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
