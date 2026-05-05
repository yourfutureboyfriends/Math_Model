// Section G Panel 6 — Commodities Dashboard
// Energy, metals, and agriculture with macro signals

import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';

interface Commodity {
  symbol: string;
  name: string;
  spot: number;
  change1d: number;
  change1m: number;
  change3m: number;
  week52Percentile: number;
}

interface CommodityData {
  energy: Commodity[];
  metals: Commodity[];
  agriculture: Commodity[];
}

interface MacroSignals {
  copperGoldRatio?: {
    value: number;
    signal: string;
    description?: string;
  };
  oilTrend?: {
    direction: string;
    interpretation: string;
  };
  commodityInflationIndex?: {
    score: number;
    signal: string;
  };
}

interface CommoditiesResponse {
  commodities: CommodityData;
  macroSignals: MacroSignals;
}

export function CommoditiesDashboardSection() {
  const [data, setData] = useState<CommoditiesResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/commodities')
      .then(r => r.json())
      .then(d => {
        setData(d);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="h-64 bg-surface-1 border border-border animate-pulse" />;
  }

  // FIXED (BUG 4): Use != null checks instead of truthy
  const renderCommodityRow = (commodities: Commodity[]) => (
    <div className="grid grid-cols-4 gap-2">
      {commodities.slice(0, 4).map(c => (
        <div
          key={c.symbol}
          className="p-2 border border-border-subtle bg-surface-2"
        >
          <div className="text-2xs text-text-tertiary truncate">{c.name}</div>
          <div className="font-mono">{c.spot != null ? c.spot.toFixed(2) : '--'}</div>
          <div className="flex items-center justify-between text-2xs">
            <span className={cn(
              (c.change1d ?? 0) > 0 ? 'text-green' : (c.change1d ?? 0) < 0 ? 'text-red' : 'text-text-secondary'
            )}>
              {c.change1d != null ? `${c.change1d >= 0 ? '+' : ''}${c.change1d.toFixed(1)}%` : '--'}
            </span>
            <span className="text-text-tertiary">
              52W: {c.week52Percentile != null ? c.week52Percentile.toFixed(0) : '--'}%
            </span>
          </div>
        </div>
      ))}
    </div>
  );

  return (
    <Card title="COMMODITIES DASHBOARD">
      <div className="grid grid-cols-3 gap-4">
        {/* Commodities */}
        <div className="col-span-2 space-y-4">
          {/* Energy */}
          <div>
            <div className="text-2xs text-text-tertiary uppercase mb-2">Energy</div>
            {renderCommodityRow(data?.commodities?.energy || [])}
          </div>

          {/* Metals */}
          <div>
            <div className="text-2xs text-text-tertiary uppercase mb-2">Metals</div>
            {renderCommodityRow(data?.commodities?.metals || [])}
          </div>

          {/* Agriculture */}
          <div>
            <div className="text-2xs text-text-tertiary uppercase mb-2">Agriculture</div>
            {renderCommodityRow(data?.commodities?.agriculture || [])}
          </div>
        </div>

        {/* Macro Signals */}
        <div className="space-y-3">
          <div className="text-2xs text-text-tertiary uppercase">Macro Signals</div>

          {data?.macroSignals?.copperGoldRatio && (
            <div className="p-3 border border-border-subtle bg-surface-2">
              <div className="text-2xs text-text-tertiary">Copper/Gold Ratio</div>
              <div className="font-mono text-lg">{data.macroSignals.copperGoldRatio.value.toFixed(4)}</div>
              <Badge
                variant={data.macroSignals.copperGoldRatio.signal === 'RISK-ON' ? 'success' : 'neutral'}
              >
                {data.macroSignals.copperGoldRatio.signal}
              </Badge>
              {data.macroSignals.copperGoldRatio.description && (
                <div className="text-2xs text-text-tertiary mt-1">
                  {data.macroSignals.copperGoldRatio.description}
                </div>
              )}
            </div>
          )}

          {data?.macroSignals?.oilTrend && (
            <div className="p-3 border border-border-subtle bg-surface-2">
              <div className="text-2xs text-text-tertiary">Oil Trend</div>
              <div className={cn(
                'font-mono',
                data.macroSignals.oilTrend.direction === 'RISING' ? 'text-red' : 'text-text-primary'
              )}>
                {data.macroSignals.oilTrend.direction}
              </div>
              <div className="text-2xs text-text-tertiary">
                {data.macroSignals.oilTrend.interpretation}
              </div>
            </div>
          )}

          {data?.macroSignals?.commodityInflationIndex && (
            <div className="p-3 border border-border-subtle bg-surface-2">
              <div className="text-2xs text-text-tertiary">Inflation Index</div>
              <div className={cn(
                'font-mono text-lg',
                data.macroSignals.commodityInflationIndex.score > 2 ? 'text-red' :
                data.macroSignals.commodityInflationIndex.score < -2 ? 'text-green' : 'text-text-primary'
              )}>
                {data.macroSignals.commodityInflationIndex.score.toFixed(1)}%
              </div>
              <Badge
                variant={data.macroSignals.commodityInflationIndex.signal === 'RISING' ? 'warning' : 'neutral'}
              >
                {data.macroSignals.commodityInflationIndex.signal}
              </Badge>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
