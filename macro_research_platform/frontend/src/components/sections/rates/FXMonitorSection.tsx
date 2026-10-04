// Section G Panel 5 — FX Monitor + Phase 1E Store Integration
// G10 FX dashboard using macroStore for live prices

import { useState } from 'react';
import { Card } from '@/components/ui/Card';
import { SourceTag } from '@/components/ui/SourceTag';
import { CsvButton } from '@/components/ui/CsvButton';
import { Table } from '@/components/ui/Table';
import { cn } from '@/lib/utils';
import { useMacroStore } from '@/store/macroStore';
import { useApiData } from '@/hooks/useApiData';
import { fmtFx, fmtChange, fmtVol } from '@/utils/format';

// Unknown values stay null and render as "--" (never 0, which reads as "unchanged").
interface FXPair {
  pair: string;
  spot: number | null;
  change1d: number | null;
  change1w: number | null;
  change1m: number | null;
  vol1m: number | null;
  trendSignal: string;
  asOf?: string | null;
}

interface FXData {
  g10: FXPair[];
  em: FXPair[];
  dxy?: {
    spot: number;
    change1d: number | null;
    as_of?: string;
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

  // Broad live FX board (20 pairs, region-grouped) — real spots + daily change.
  const { data: fxApi } = useApiData<any>('/api/fx-rates');

  const toPair = (p: any): FXPair => ({
    pair: p.pair, spot: p.spot ?? null, change1d: p.change1d ?? null, change1w: p.change1w ?? null,
    change1m: p.change1m ?? null, vol1m: p.vol1m ?? null, trendSignal: p.trend ?? '--', asOf: p.as_of,
  });

  // Build FX data from store prices (fallback when the fx-rates endpoint isn't loaded yet)
  const buildFXFromStore = (): FXData => {
    const g10: FXPair[] = [
      { pair: 'EUR/USD', spot: prices.EURUSD, change1d: changes.EURUSD != null ? changes.EURUSD * 100 : null, change1w: null, change1m: null, vol1m: null, trendSignal: '--' },
      { pair: 'GBP/USD', spot: prices.GBPUSD, change1d: changes.GBPUSD != null ? changes.GBPUSD * 100 : null, change1w: null, change1m: null, vol1m: null, trendSignal: '--' },
      { pair: 'USD/JPY', spot: prices.USDJPY, change1d: changes.USDJPY != null ? changes.USDJPY * 100 : null, change1w: null, change1m: null, vol1m: null, trendSignal: '--' },
    ].filter(f => f.spot != null && f.spot > 0);

    return {
      g10,
      em: propData?.em ?? [],
      dxy: prices.DXY ? { spot: prices.DXY, change1d: changes.DXY != null ? changes.DXY * 100 : null } : undefined,
    };
  };

  // Prefer the live fx-rates board; fall back to store prices while it loads.
  const data: FXData = fxApi?.available
    ? {
        g10: (fxApi.g10 ?? []).filter((p: any) => p.available).map(toPair),
        em: [...(fxApi.asia ?? []), ...(fxApi.emea_latam ?? [])].filter((p: any) => p.available).map(toPair),
        dxy: fxApi.dxy ?? undefined,
      }
    : buildFXFromStore();
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
          (f.change1d ?? 0) > 0 ? 'text-green' : (f.change1d ?? 0) < 0 ? 'text-red' : 'text-text-secondary'
        )}>
          {f.change1d != null ? fmtChange(f.change1d / 100) : '--'}
        </span>
      ),
      align: 'right' as const,
    },
    {
      header: '1M',
      accessor: (f: FXPair) => (
        <span className={cn(
          'font-mono',
          (f.change1m ?? 0) > 0 ? 'text-green' : (f.change1m ?? 0) < 0 ? 'text-red' : 'text-text-secondary'
        )}>
          {f.change1m != null ? fmtChange(f.change1m / 100) : '--'}
        </span>
      ),
      align: 'right' as const,
    },
    {
      header: 'Vol(1M)',
      accessor: (f: FXPair) => (
        <span className="font-mono text-text-secondary">{f.vol1m != null ? `${fmtVol(f.vol1m)}%` : '--'}</span>
      ),
      align: 'right' as const,
    },
    {
      header: 'Trend 1M',
      accessor: (f: FXPair) => (
        <span className={cn(
          'text-2xs uppercase',
          f.trendSignal === 'UP' && 'text-green',
          f.trendSignal === 'DOWN' && 'text-red',
          f.trendSignal === 'FLAT' && 'text-text-secondary'
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
      headerRight={
        <div className="flex items-center gap-2">
          <CsvButton
            filename="fx-monitor"
            getData={() => ({
              columns: ['Pair', 'Spot', '1D %', '1W %', '1M %', 'Vol 1M %', 'As of'],
              rows: data.g10.map((f) => [f.pair, f.spot, f.change1d, f.change1w, f.change1m, f.vol1m, f.asOf ?? '']),
            })}
          />
          <SourceTag source="Yahoo (NY-session dated)" timestamp={asOf} staleAfterSeconds={900} />
        </div>
      }
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
                (data.dxy.change1d ?? 0) > 0 ? 'text-green' : (data.dxy.change1d ?? 0) < 0 ? 'text-red' : 'text-text-secondary'
              )}>
                {data.dxy.change1d != null ? fmtChange(data.dxy.change1d / 100) : '--'}
              </span>
              {data.dxy.as_of && <span className="text-2xs text-text-tertiary">{data.dxy.as_of}</span>}
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
                {fx.asOf && <div className="text-2xs text-text-tertiary">close {fx.asOf}</div>}
                <div className="flex items-center justify-between text-xs mt-1">
                  <span className={cn(
                    (fx.change1d ?? 0) > 0 ? 'text-green' : (fx.change1d ?? 0) < 0 ? 'text-red' : 'text-text-secondary'
                  )}>
                    {fx.change1d != null ? fmtChange(fx.change1d / 100) : '--'}
                  </span>
                  <span className={cn(
                    'text-2xs',
                    fx.trendSignal === 'UP' && 'text-green',
                    fx.trendSignal === 'DOWN' && 'text-red'
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

        {/* EM FX Summary (Asia + EMEA/LatAm) */}
        <div>
          <div className="text-2xs text-text-tertiary uppercase mb-2">EM FX · Asia · LatAm</div>
          <div className="grid grid-cols-4 gap-2">
            {(data.em ?? []).slice(0, 8).map(fx => (
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
