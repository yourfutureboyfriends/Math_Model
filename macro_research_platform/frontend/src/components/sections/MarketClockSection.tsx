// Section G Panel 1 — Market Clock + Global Equity Monitor
// Real-time market status and global indices grid

import { useState, useEffect } from 'react';
import { Badge } from '@/components/ui/Badge';
import { MetricCard } from '@/components/ui/MetricCard';
import { cn } from '@/lib/utils';

interface MarketIndex {
  ticker: string;
  name: string;
  region: string;
  price: number;
  change1d: number;
  change1m: number;
  week52Percentile: number;
  momentumSignal: string;
}

interface MarketClock {
  exchange: string;
  status: 'OPEN' | 'CLOSED' | 'PRE_MARKET' | 'POST_MARKET' | 'WEEKEND';
  localTime: string;
  timeToOpenMinutes?: number;
  timeToCloseMinutes?: number;
  nextSession: string;
}

interface GlobalMarketsData {
  indices: MarketIndex[];
  dmAverage1m: number;
  emAverage1m: number;
  dmEmSpread: number;
  globalRiskOnScore: number;
  marketClock: MarketClock[];
  vixComplex: {
    fearComposite?: number;
    fearStatus: string;
  };
}

export function MarketClockSection() {
  const [data, setData] = useState<GlobalMarketsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/global/markets')
      .then(r => r.json())
      .then(d => {
        setData(d);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="h-32 bg-surface-1 border border-border animate-pulse" />
    );
  }

  const dmIndices = data?.indices.filter(i => i.region !== 'EM') || [];
  const emIndices = data?.indices.filter(i => i.region === 'EM') || [];

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'OPEN': return 'bg-green';
      case 'PRE_MARKET':
      case 'POST_MARKET': return 'bg-amber';
      default: return 'bg-red';
    }
  };

  return (
    <div className="space-y-4">
      {/* Market Clock Row */}
      <div className="flex items-center gap-4 overflow-x-auto pb-2">
        {data?.marketClock.map(clock => (
          <div
            key={clock.exchange}
            className={cn(
              'flex items-center gap-2 px-3 py-1.5 border min-w-fit',
              clock.status === 'OPEN' ? 'border-green/30 bg-green-dim' : 'border-border-subtle bg-surface-2'
            )}
          >
            <div className={cn('w-2 h-2 rounded-full', getStatusColor(clock.status))} />
            <span className="text-2xs text-text-tertiary uppercase">{clock.exchange}</span>
            <span className={cn(
              'text-xs font-mono',
              clock.status === 'OPEN' ? 'text-green' : 'text-text-secondary'
            )}>
              {clock.status === 'OPEN' && clock.timeToCloseMinutes
                ? `${Math.floor(clock.timeToCloseMinutes / 60)}h${clock.timeToCloseMinutes % 60}m left`
                : clock.status === 'CLOSED' && clock.timeToOpenMinutes
                ? `opens in ${Math.floor(clock.timeToOpenMinutes / 60)}h`
                : clock.status}
            </span>
          </div>
        ))}
      </div>

      {/* Fear Composite */}
      {data?.vixComplex?.fearComposite && (
        <div className="flex items-center gap-4 text-xs">
          <span className="text-text-tertiary">FEAR COMPOSITE:</span>
          <span className={cn(
            'font-mono font-bold',
            data.vixComplex.fearComposite > 70 ? 'text-red' :
            data.vixComplex.fearComposite < 30 ? 'text-green' : 'text-text-primary'
          )}>
            {data.vixComplex.fearComposite.toFixed(1)}
          </span>
          <Badge variant={data.vixComplex.fearStatus === 'SYSTEMIC FEAR' ? 'danger' : 'neutral'}>
            {data.vixComplex.fearStatus}
          </Badge>
        </div>
      )}

      {/* Aggregate Metrics */}
      <div className="grid grid-cols-4 gap-3">
        <MetricCard
          label="DM Avg 1M"
          value={data?.dmAverage1m ? `${data.dmAverage1m > 0 ? '+' : ''}${data.dmAverage1m.toFixed(2)}%` : '--'}
          direction={data?.dmAverage1m && data.dmAverage1m > 0 ? 'up' : 'down'}
        />
        <MetricCard
          label="EM Avg 1M"
          value={data?.emAverage1m ? `${data.emAverage1m > 0 ? '+' : ''}${data.emAverage1m.toFixed(2)}%` : '--'}
          direction={data?.emAverage1m && data.emAverage1m > 0 ? 'up' : 'down'}
        />
        <MetricCard
          label="DM-EM Spread"
          value={data?.dmEmSpread ? `${data.dmEmSpread > 0 ? '+' : ''}${data.dmEmSpread.toFixed(2)}%` : '--'}
          direction={data?.dmEmSpread && data.dmEmSpread > 0 ? 'up' : 'down'}
        />
        <MetricCard
          label="Risk-On Score"
          value={data?.globalRiskOnScore ? `${data.globalRiskOnScore.toFixed(0)}%` : '--'}
          direction={data?.globalRiskOnScore && data.globalRiskOnScore > 50 ? 'up' : 'down'}
        />
      </div>

      {/* DM Indices Grid */}
      <div>
        <div className="text-2xs text-text-tertiary uppercase mb-2">Developed Markets</div>
        <div className="grid grid-cols-7 gap-1 text-xs">
          {dmIndices.slice(0, 14).map(idx => (
            <div
              key={idx.ticker}
              className={cn(
                'p-2 border border-border-subtle',
                idx.momentumSignal === 'UPTREND' && 'bg-green-dim/30',
                idx.momentumSignal === 'DOWNTREND' && 'bg-red-dim/30'
              )}
            >
              <div className="text-2xs text-text-tertiary truncate">{idx.name}</div>
              <div className="font-mono">{idx.price?.toFixed(0) || '--'}</div>
              <div className={cn(
                'text-2xs font-mono',
                idx.change1d > 0 ? 'text-green' : idx.change1d < 0 ? 'text-red' : 'text-text-secondary'
              )}>
                {idx.change1d > 0 ? '+' : ''}{idx.change1d?.toFixed(2) || '--'}%
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* EM Indices Grid */}
      <div>
        <div className="text-2xs text-text-tertiary uppercase mb-2">Emerging Markets</div>
        <div className="grid grid-cols-7 gap-1 text-xs">
          {emIndices.map(idx => (
            <div
              key={idx.ticker}
              className={cn(
                'p-2 border border-border-subtle',
                idx.momentumSignal === 'UPTREND' && 'bg-green-dim/30',
                idx.momentumSignal === 'DOWNTREND' && 'bg-red-dim/30'
              )}
            >
              <div className="text-2xs text-text-tertiary truncate">{idx.name}</div>
              <div className="font-mono">{idx.price?.toFixed(0) || '--'}</div>
              <div className={cn(
                'text-2xs font-mono',
                idx.change1d > 0 ? 'text-green' : idx.change1d < 0 ? 'text-red' : 'text-text-secondary'
              )}>
                {idx.change1d > 0 ? '+' : ''}{idx.change1d?.toFixed(2) || '--'}%
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
