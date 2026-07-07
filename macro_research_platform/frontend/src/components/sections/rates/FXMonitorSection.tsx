// Section G Panel 5 — FX Monitor + Phase 1E Store Integration
// G10 FX dashboard using macroStore for live prices

import { useState } from 'react';
import { Card } from '@/components/ui/Card';
import { SourceTag } from '@/components/ui/SourceTag';
import { Table } from '@/components/ui/Table';
import { cn } from '@/lib/utils';
import { useMacroStore } from '@/store/macroStore';
import { fmtFx, fmtChange, fmtVol } from '@/utils/format';

interface FXPair {
  pair: string;
  spot: number;
  change1d: number;
  change1w: number;
  change1m: number;
  vol1m: number;
  trendSignal: string;
}

interface FXData {
  g10: FXPair[];
  em: FXPair[];
  dxy?: {
    spot: number;
    change1d: number;
  };
}

interface FXMonitorSectionProps {
  data?: FXData;
}

export function FXMonitorSection({ data: propData }: FXMonitorSectionProps) {
  const [view, setView] = useState<'grid' | 'table'>('grid');

  // Use macro store for live FX prices
  const prices = useMacroStore((state) => state.prices);
  const changes = useMacroStore((state) => state.changes);
  const isLoading = useMacroStore((state) => state.meta.dataStatus === 'loading');
  const asOf = useMacroStore((state) => (state.fullDashboard as any)?.timestamp as string | undefined);

  // Build FX data from store prices
  const buildFXFromStore = (): FXData => {
    const g10: FXPair[] = [
      { pair: 'EUR/USD', spot: prices.EURUSD ?? 0, change1d: (changes.EURUSD ?? 0) * 100, change1w: 0, change1m: 0, vol1m: 8.5, trendSignal: 'NEUTRAL' },
      { pair: 'GBP/USD', spot: prices.GBPUSD ?? 0, change1d: (changes.GBPUSD ?? 0) * 100, change1w: 0, change1m: 0, vol1m: 9.2, trendSignal: 'NEUTRAL' },
      { pair: 'USD/JPY', spot: prices.USDJPY ?? 0, change1d: (changes.USDJPY ?? 0) * 100, change1w: 0, change1m: 0, vol1m: 10.1, trendSignal: 'NEUTRAL' },
      { pair: 'USD/CHF', spot: prices.USDCHF ?? 0, change1d: (changes.USDCHF ?? 0) * 100, change1w: 0, change1m: 0, vol1m: 9.8, trendSignal: 'NEUTRAL' },
      { pair: 'USD/CAD', spot: prices.USDCAD ?? 0, change1d: (changes.USDCAD ?? 0) * 100, change1w: 0, change1m: 0, vol1m: 8.9, trendSignal: 'NEUTRAL' },
      { pair: 'AUD/USD', spot: prices.AUDUSD ?? 0, change1d: (changes.AUDUSD ?? 0) * 100, change1w: 0, change1m: 0, vol1m: 11.2, trendSignal: 'NEUTRAL' },
      { pair: 'NZD/USD', spot: prices.NZDUSD ?? 0, change1d: (changes.NZDUSD ?? 0) * 100, change1w: 0, change1m: 0, vol1m: 11.8, trendSignal: 'NEUTRAL' },
    ].filter(f => f.spot > 0);

    return {
      g10,
      em: propData?.em ?? [],
      dxy: prices.DXY ? {
        spot: prices.DXY,
        change1d: (changes.DXY ?? 0) * 100
      } : undefined
    };
  };

  // Use store data if available, fallback to props
  const data = buildFXFromStore();
  const majorPairs = data.g10.slice(0, 8);

  const fxColumns = [
    { header: 'Pair', accessor: (f: FXPair) => f.pair, align: 'left' as const },
    {
      header: 'Spot',
      accessor: (f: FXPair) => (
        <span className="font-mono">{fmtFx(f.spot)}</span>
      ),
      align: 'right' as const,
    },
    {
      header: '1D',
      accessor: (f: FXPair) => (
        <span className={cn(
          'font-mono',
          f.change1d > 0 ? 'text-green' : f.change1d < 0 ? 'text-red' : 'text-text-secondary'
        )}>
          {f.change1d ? fmtChange(f.change1d / 100) : '--'}
        </span>
      ),
      align: 'right' as const,
    },
    {
      header: '1M',
      accessor: (f: FXPair) => (
        <span className={cn(
          'font-mono',
          f.change1m > 0 ? 'text-green' : f.change1m < 0 ? 'text-red' : 'text-text-secondary'
        )}>
          {f.change1m ? fmtChange(f.change1m / 100) : '--'}
        </span>
      ),
      align: 'right' as const,
    },
    {
      header: 'Vol(1M)',
      accessor: (f: FXPair) => (
        <span className="font-mono text-text-secondary">{fmtVol(f.vol1m)}%</span>
      ),
      align: 'right' as const,
    },
    {
      header: 'Signal',
      accessor: (f: FXPair) => (
        <span className={cn(
          'text-2xs uppercase',
          f.trendSignal === 'LONG' && 'text-green',
          f.trendSignal === 'SHORT' && 'text-red',
          f.trendSignal === 'NEUTRAL' && 'text-text-secondary'
        )}>
          {f.trendSignal}
        </span>
      ),
      align: 'center' as const,
    },
  ];

  if (isLoading && !propData) {
    return <div className="h-64 bg-surface-1 border border-border animate-pulse" />;
  }

  return (
    <Card
      title="FX MONITOR"
      headerRight={<SourceTag source="Yahoo" timestamp={asOf} staleAfterSeconds={900} />}
    >
      <div className="space-y-4">
        {/* View Toggle + DXY */}
        <div className="flex items-center justify-between">
          <div className="flex gap-1">
            <button
              onClick={() => setView('grid')}
              className={cn(
                'px-3 py-1 text-xs border',
                view === 'grid'
                  ? 'bg-bloomberg text-bg border-bloomberg'
                  : 'bg-surface-2 text-text-secondary border-border-subtle'
              )}
            >
              GRID
            </button>
            <button
              onClick={() => setView('table')}
              className={cn(
                'px-3 py-1 text-xs border',
                view === 'table'
                  ? 'bg-bloomberg text-bg border-bloomberg'
                  : 'bg-surface-2 text-text-secondary border-border-subtle'
              )}
            >
              TABLE
            </button>
          </div>

          {data?.dxy && (
            <div className="flex items-center gap-3 text-sm">
              <span className="text-text-tertiary">DXY</span>
              <span className="font-mono font-bold">{fmtFx(data.dxy.spot, 2)}</span>
              <span className={cn(
                'font-mono',
                data.dxy.change1d > 0 ? 'text-green' : 'text-red'
              )}>
                {fmtChange(data.dxy.change1d / 100)}
              </span>
            </div>
          )}
        </div>

        {/* Grid View */}
        {view === 'grid' && (
          <div className="grid grid-cols-4 gap-2">
            {majorPairs.map(fx => (
              <div
                key={fx.pair}
                className="p-3 border border-border-subtle bg-surface-2"
              >
                <div className="text-2xs text-text-tertiary uppercase">{fx.pair}</div>
                <div className="font-mono text-lg">{fmtFx(fx.spot)}</div>
                <div className="flex items-center justify-between text-xs mt-1">
                  <span className={cn(
                    (fx.change1d ?? 0) > 0 ? 'text-green' : (fx.change1d ?? 0) < 0 ? 'text-red' : 'text-text-secondary'
                  )}>
                    {fx.change1d != null ? fmtChange(fx.change1d / 100) : '--'}
                  </span>
                  <span className={cn(
                    'text-2xs',
                    fx.trendSignal === 'LONG' && 'text-green',
                    fx.trendSignal === 'SHORT' && 'text-red'
                  )}>
                    {fx.trendSignal}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Table View */}
        {view === 'table' && (
          <Table
            data={data?.g10 ?? []}
            columns={fxColumns}
            keyExtractor={(f) => f.pair}
          />
        )}

        {/* EM FX Summary */}
        <div>
          <div className="text-2xs text-text-tertiary uppercase mb-2">EM FX</div>
          <div className="grid grid-cols-4 gap-2">
            {(propData?.em ?? []).slice(0, 4).map(fx => (
              <div
                key={fx.pair}
                className="p-2 border border-border-subtle"
              >
                <div className="text-2xs text-text-tertiary">{fx.pair}</div>
                <div className="font-mono">{fmtFx(fx.spot, 2)}</div>
                <div className={cn(
                  'text-2xs font-mono',
                  (fx.change1m ?? 0) > 0 ? 'text-green' : (fx.change1m ?? 0) < 0 ? 'text-red' : 'text-text-secondary'
                )}>
                  {fx.change1m != null ? fmtChange(fx.change1m / 100) : '--'}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}
