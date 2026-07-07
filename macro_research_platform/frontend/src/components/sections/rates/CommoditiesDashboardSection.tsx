// Section G Panel 6 — Commodities Dashboard + Phase 2 Store Integration
// Energy, metals, and agriculture with macro signals using format library
// REFACTORED: Now uses useApiData hook instead of direct fetch()

import { memo } from 'react';
import { Card } from '@/components/ui/Card';
import { SourceTag } from '@/components/ui/SourceTag';
import { Badge } from '@/components/ui/Badge';
import { LoadingState } from '@/components/ui/LoadingState';
import { ErrorState } from '@/components/ui/ErrorState';
import { cn } from '@/lib/utils';
import { useMacroStore } from '@/store/macroStore';
import { fmtPrice, fmtChange, fmtProbability } from '@/utils/format';
import { useApiData } from '@/hooks/useApiData';

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

export const CommoditiesDashboardSection = memo(function CommoditiesDashboardSection() {
  // REFACTORED: Use useApiData hook instead of direct fetch()
  const { data, loading: apiLoading, error: apiError } = useApiData<CommoditiesResponse>('/api/commodities');

  // Use macro store for GLD/WTI prices
  const prices = useMacroStore((state) => state.prices);
  const changes = useMacroStore((state) => state.changes);
  const storeLoading = useMacroStore((state) => state.meta.dataStatus === 'loading');
  const storeError = useMacroStore((state) => state.meta.dataStatus === 'error');

  const loading = apiLoading || storeLoading;
  const error = apiError?.message || (storeError ? 'Store data unavailable' : null);

  if (loading) {
    return (
      <Card title="COMMODITIES DASHBOARD">
        <LoadingState message="Loading commodities data..." className="h-64" />
      </Card>
    );
  }

  if (error) {
    return (
      <Card title="COMMODITIES DASHBOARD">
        <div className="h-64">
          <ErrorState
            message={error}
            retry={() => window.location.reload()}
          />
        </div>
      </Card>
    );
  }

  // Use store prices for gold if available
  const goldPrice = prices.GLD;
  const goldChange = changes.GLD;

  const renderCommodityRow = (commodities: Commodity[]) => (
    <div className="grid grid-cols-4 gap-2">
      {commodities.slice(0, 4).map(c => (
        <div
          key={c.symbol}
          className="p-2 border border-border-subtle bg-surface-2"
        >
          <div className="text-2xs text-text-tertiary truncate">{c.name}</div>
          <div className="font-mono">{fmtPrice(c.spot, 2)}</div>
          <div className="flex items-center justify-between text-2xs">
            <span className={cn(
              (c.change1d ?? 0) > 0 ? 'text-green' : (c.change1d ?? 0) < 0 ? 'text-red' : 'text-text-secondary'
            )}>
              {c.change1d != null ? fmtChange(c.change1d / 100) : '--'}
            </span>
            <span className="text-text-tertiary">
              52W: {c.week52Percentile != null ? fmtProbability(c.week52Percentile / 100) : '--'}
            </span>
          </div>
        </div>
      ))}
    </div>
  );

  return (
    <Card
      title="COMMODITIES DASHBOARD"
      headerRight={<SourceTag source="Yahoo" timestamp={(data as any)?.lastUpdated} staleAfterSeconds={600} />}
    >
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

          {/* Gold from store */}
          {goldPrice && (
            <div className="p-3 border border-border-subtle bg-surface-2">
              <div className="text-2xs text-text-tertiary">Gold (GLD)</div>
              <div className="font-mono text-lg">{fmtPrice(goldPrice)}</div>
              <span className={cn(
                'text-xs',
                (goldChange ?? 0) > 0 ? 'text-green' : (goldChange ?? 0) < 0 ? 'text-red' : 'text-text-secondary'
              )}>
                {goldChange != null ? fmtChange(goldChange) : '--'}
              </span>
            </div>
          )}

          {data?.macroSignals?.copperGoldRatio && (
            <div className="p-3 border border-border-subtle bg-surface-2">
              <div className="text-2xs text-text-tertiary">Copper/Gold Ratio</div>
              <div className="font-mono text-lg">{fmtPrice(data.macroSignals.copperGoldRatio.value, 4)}</div>
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
                {fmtChange(data.macroSignals.commodityInflationIndex.score / 100)}
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
});
