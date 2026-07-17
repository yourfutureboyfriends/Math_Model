// Section G Panel 7 — Positioning & Flows + Phase 2 Format Library
// CFTC COT data, fund flows, and short interest using format library

import { Card } from '@/components/ui/Card';
import { Table } from '@/components/ui/Table';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';
import { useMacroStore } from '@/store/macroStore';
import { useApiData } from '@/hooks/useApiData';
import { fmtChange, fmtPrice } from '@/utils/format';

interface COTPosition {
  contract: string;
  name: string;
  category: string;
  percentOI: number;
  isExtreme: boolean;
  signal: string;
}

interface FlowIndicator {
  name: string;
  value: number;
  change?: number;
  signal: string;
}

interface ShortInterest {
  ticker: string;
  shortPercent?: number;
  daysToCover?: number;
  signal: string;
}

interface PositioningData {
  cot: {
    positions: COTPosition[];
    extremeCount: number;
    crowdingAlert: boolean;
  };
  fundFlows: FlowIndicator[];
  shortInterest: ShortInterest[];
  positioningAlert: {
    active: boolean;
    message?: string;
  };
}

export function PositioningSection() {
  const { data, loading } = useApiData<PositioningData>('/api/positioning');

  // Use macro store for regime context
  const regime = useMacroStore((state) => state.regime);

  if (loading) {
    return <div className="h-64 bg-surface-1 border border-border animate-pulse" />;
  }

  const cotColumns = [
    { header: 'Instrument', accessor: (p: COTPosition) => p.name, align: 'left' as const },
    {
      header: 'Net %',
      accessor: (p: COTPosition) => (
        <span className={cn(
          'font-mono',
          p.percentOI > 0 ? 'text-green' : 'text-red'
        )}>
          {p.percentOI != null ? fmtChange(p.percentOI / 100) : '--'}
        </span>
      ),
      align: 'right' as const,
    },
    {
      header: 'Extreme?',
      accessor: (p: COTPosition) => (
        p.isExtreme ? <span className="text-amber">⚠</span> : '—'
      ),
      align: 'center' as const,
    },
    {
      header: 'Signal',
      accessor: (p: COTPosition) => (
        <span className={cn(
          'text-2xs',
          p.signal.includes('LONG') && 'text-amber',
          p.signal.includes('SHORT') && 'text-red'
        )}>
          {p.signal}
        </span>
      ),
      align: 'center' as const,
    },
  ];

  return (
    <Card title={`POSITIONING & FLOWS | Regime: ${regime.current ? regime.current.toUpperCase() : '—'}`}>
      <div className="grid grid-cols-2 gap-4">
        {/* COT Table */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <div className="text-2xs text-text-tertiary uppercase">CFTC COT Positions</div>
            {data?.positioningAlert?.active && (
              <Badge variant="warning">ALERT</Badge>
            )}
          </div>

          <Table
            data={data?.cot?.positions?.slice(0, 6)}
            columns={cotColumns}
            keyExtractor={(p) => p.contract}
          />

          {data?.positioningAlert?.message && (
            <div className="mt-2 p-2 border border-amber bg-amber-dim/10 text-2xs text-amber">
              {data.positioningAlert.message}
            </div>
          )}
        </div>

        {/* Flows & Short Interest */}
        <div className="space-y-4">
          {/* Fund Flows */}
          <div>
            <div className="text-2xs text-text-tertiary uppercase mb-2">Fund Flows</div>
            <div className="space-y-2">
              {data?.fundFlows?.map(flow => (
                <div
                  key={flow.name}
                  className="flex items-center justify-between p-2 border border-border-subtle bg-surface-2"
                >
                  <span className="text-xs">{flow.name}</span>
                  <div className="text-right">
                    <div className="font-mono text-sm">${flow.value != null ? fmtPrice(flow.value, 2) : '--'}T</div>
                    <div className={cn(
                      'text-2xs',
                      flow.signal === 'RISK-ON' ? 'text-green' : 'text-red'
                    )}>
                      {flow.signal}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Short Interest */}
          <div>
            <div className="text-2xs text-text-tertiary uppercase mb-2">Short Interest</div>
            <div className="grid grid-cols-2 gap-2">
              {data?.shortInterest?.slice(0, 4).map(si => (
                <div
                  key={si.ticker}
                  className="p-2 border border-border-subtle"
                >
                  <div className="text-2xs text-text-tertiary">{si.ticker}</div>
                  <div className="font-mono">{si.shortPercent != null ? fmtChange(si.shortPercent / 100) : '--'}</div>
                  {si.signal !== 'NORMAL' && (
                    <div className="text-2xs text-amber">{si.signal}</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}
