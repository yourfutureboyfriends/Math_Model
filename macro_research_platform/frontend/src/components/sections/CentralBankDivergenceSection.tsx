// Section G Panel 3 — Central Bank Divergence Matrix + Phase 2 Format Library
// G10 central bank policy rates using format library

import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/Card';
import { Table } from '@/components/ui/Table';
import { cn } from '@/lib/utils';
import { useMacroStore } from '@/store/macroStore';
import { fmtRate, fmtBps } from '@/utils/format';

interface CentralBank {
  code: string;
  name: string;
  currentRate: number;
  realRate: number;
  stance: string;
  nextMeeting: string;
}

interface DivergencePair {
  pair: string;
  spreadBps: number;
  direction: string;
  isExtreme: boolean;
}

interface CountryMacroData {
  countries: Array<{
    code: string;
    name: string;
    policyRate: number;
    realRate: number;
  }>;
  centralBanks: CentralBank[];
  divergence: {
    divergenceMatrix: DivergencePair[];
    mostDivergent: DivergencePair | null;
  };
}

export function CentralBankDivergenceSection() {
  const [data, setData] = useState<CountryMacroData | null>(null);
  const [loading, setLoading] = useState(true);

  // Use macro store for regime context
  const regime = useMacroStore((state) => state.regime);

  useEffect(() => {
    fetch('/api/global/countries')
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

  const cbColumns = [
    { header: 'CB', accessor: (cb: CentralBank) => cb.code, align: 'left' as const },
    {
      header: 'Rate',
      accessor: (cb: CentralBank) => (
        <span className="font-mono">{cb.currentRate != null ? fmtRate(cb.currentRate / 100) : '--'}</span>
      ),
      align: 'right' as const,
    },
    {
      header: 'Real Rate',
      accessor: (cb: CentralBank) => (
        <span className={cn(
          'font-mono',
          cb.realRate > 0 ? 'text-green' : 'text-red'
        )}>
          {cb.realRate != null ? fmtRate(cb.realRate / 100) : '--'}
        </span>
      ),
      align: 'right' as const,
    },
    {
      header: 'Stance',
      accessor: (cb: CentralBank) => (
        <span className={cn(
          'text-2xs uppercase',
          cb.stance === 'Hawkish' && 'text-green',
          cb.stance === 'Dovish' && 'text-red',
          cb.stance === 'Neutral' && 'text-text-secondary'
        )}>
          {cb.stance}
        </span>
      ),
      align: 'center' as const,
    },
    {
      header: 'Next Meeting',
      accessor: (cb: CentralBank) => (
        <span className="font-mono text-2xs">{cb.nextMeeting || 'TBA'}</span>
      ),
      align: 'center' as const,
    },
  ];

  return (
    <Card title={`CENTRAL BANK DIVERGENCE | Regime: ${regime.current ? regime.current.toUpperCase() : '—'}`}>
      <div className="grid grid-cols-5 gap-4">
        {/* CB Table */}
        <div className="col-span-3">
          <Table
            data={data?.centralBanks}
            columns={cbColumns}
            keyExtractor={(cb) => cb.code}
          />
        </div>

        {/* Divergence Matrix */}
        <div className="col-span-2 space-y-3">
          <div className="text-2xs text-text-tertiary uppercase">FED Divergence</div>

          {data?.divergence?.divergenceMatrix?.map((pair) => (
            <div
              key={pair.pair}
              className={cn(
                'flex items-center justify-between p-2 border',
                pair.isExtreme ? 'border-amber bg-amber-dim/20' : 'border-border-subtle bg-surface-2'
              )}
            >
              <div className="text-xs">{pair.pair.replace('FED vs ', '')}</div>
              <div className="text-right">
                <div className={cn(
                  'font-mono font-bold',
                  pair.isExtreme && 'text-amber'
                )}>
                  {fmtBps(pair.spreadBps)}
                </div>
                <div className="text-2xs text-text-tertiary">{pair.direction}</div>
              </div>
            </div>
          ))}

          {data?.divergence?.mostDivergent && (
            <div className="mt-4 p-2 border border-amber bg-amber-dim/10">
              <div className="text-2xs text-amber uppercase">Most Divergent</div>
              <div className="text-sm font-mono">{data.divergence.mostDivergent.pair.replace('FED vs ', '')}</div>
              <div className="text-xs">{fmtBps(data.divergence.mostDivergent.spreadBps)} spread</div>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
