// Section G Panel 5 — FX Monitor
// G10 FX dashboard with grid and table views

import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/Card';
import { Table } from '@/components/ui/Table';
import { cn } from '@/lib/utils';

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

export function FXMonitorSection() {
  const [data, setData] = useState<FXData | null>(null);
  const [view, setView] = useState<'grid' | 'table'>('grid');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/fx')
      .then(r => r.json())
      .then(d => {
        setData(d.fx);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="h-64 bg-surface-1 border border-border animate-pulse" />;
  }

  const majorPairs = data?.g10.slice(0, 8) || [];

  const fxColumns = [
    { header: 'Pair', accessor: (f: FXPair) => f.pair, align: 'left' as const },
    {
      header: 'Spot',
      accessor: (f: FXPair) => (
        <span className="font-mono">{f.spot?.toFixed(4) || '--'}</span>
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
          {f.change1d ? `${f.change1d > 0 ? '+' : ''}${f.change1d.toFixed(2)}%` : '--'}
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
          {f.change1m ? `${f.change1m > 0 ? '+' : ''}${f.change1m.toFixed(2)}%` : '--'}
        </span>
      ),
      align: 'right' as const,
    },
    {
      header: 'Vol(1M)',
      accessor: (f: FXPair) => (
        <span className="font-mono text-text-secondary">{f.vol1m?.toFixed(1) || '--'}%</span>
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

  return (
    <Card title="FX MONITOR">
      <div className="space-y-4">
        {/* View Toggle + DXY */}
        <div className="flex items-center justify-between">
          <div className="flex gap-1">
            <button
              onClick={() => setView('grid')}
              className={cn(
                'px-3 py-1 text-xs border',
                view === 'grid'
                  ? 'bg-accent text-bg border-accent'
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
                  ? 'bg-accent text-bg border-accent'
                  : 'bg-surface-2 text-text-secondary border-border-subtle'
              )}
            >
              TABLE
            </button>
          </div>

          {data?.dxy && (
            <div className="flex items-center gap-3 text-sm">
              <span className="text-text-tertiary">DXY</span>
              <span className="font-mono font-bold">{data.dxy.spot.toFixed(2)}</span>
              <span className={cn(
                'font-mono',
                data.dxy.change1d > 0 ? 'text-green' : 'text-red'
              )}>
                {data.dxy.change1d > 0 ? '+' : ''}{data.dxy.change1d.toFixed(2)}%
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
                <div className="font-mono text-lg">{fx.spot?.toFixed(4) || '--'}</div>
                <div className="flex items-center justify-between text-xs mt-1">
                  <span className={cn(
                    fx.change1d > 0 ? 'text-green' : 'text-red'
                  )}>
                    {fx.change1d ? `${fx.change1d > 0 ? '+' : ''}${fx.change1d.toFixed(2)}%` : '--'}
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
            data={data?.g10}
            columns={fxColumns}
            keyExtractor={(f) => f.pair}
          />
        )}

        {/* EM FX Summary */}
        <div>
          <div className="text-2xs text-text-tertiary uppercase mb-2">EM FX</div>
          <div className="grid grid-cols-4 gap-2">
            {data?.em?.slice(0, 4).map(fx => (
              <div
                key={fx.pair}
                className="p-2 border border-border-subtle"
              >
                <div className="text-2xs text-text-tertiary">{fx.pair}</div>
                <div className="font-mono">{fx.spot?.toFixed(2) || '--'}</div>
                <div className={cn(
                  'text-2xs font-mono',
                  fx.change1m > 0 ? 'text-green' : 'text-red'
                )}>
                  {fx.change1m ? `${fx.change1m > 0 ? '+' : ''}${fx.change1m.toFixed(1)}%` : '--'}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}
