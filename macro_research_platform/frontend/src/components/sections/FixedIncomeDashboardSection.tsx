// Section G Panel 4 — Fixed Income Dashboard
// Comprehensive rates and credit spreads table

import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/Card';
import { Table } from '@/components/ui/Table';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';

interface RatesTableItem {
  instrument: string;
  yield: number;
  signal: string;
}

interface CreditSpread {
  name: string;
  spreadBps: number;
  change1d?: number;
  change1w?: number;
  signal: string;
}

interface FixedIncomeData {
  ratesTable: RatesTableItem[];
  creditSpreads: CreditSpread[];
  breakevenInflation: {
    tenYear?: number;
    fiveYearFiveYear?: number;
  };
  realYieldSignal: string;
}

export function FixedIncomeDashboardSection() {
  const [data, setData] = useState<FixedIncomeData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/rates')
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

  const ratesColumns = [
    { header: 'Instrument', accessor: (r: RatesTableItem) => r.instrument, align: 'left' as const },
    {
      header: 'Yield/Spread',
      accessor: (r: RatesTableItem) => (
        <span className="font-mono">{r.yield?.toFixed(2) || '--'}%</span>
      ),
      align: 'right' as const,
    },
    {
      header: 'Signal',
      accessor: (r: RatesTableItem) => {
        const variant = r.signal === 'INVERTED' ? 'danger' :
                         r.signal === 'NORMAL' ? 'success' :
                         r.signal === 'FLAT' ? 'warning' :
                         r.signal === 'RESTRICTIVE' ? 'warning' :
                         r.signal === 'USD PREMIUM' ? 'info' :
                         'neutral';
        return <Badge variant={variant}>{r.signal}</Badge>;
      },
      align: 'center' as const,
    },
  ];

  const creditColumns = [
    { header: 'Spread', accessor: (c: CreditSpread) => c.name, align: 'left' as const },
    {
      header: 'BPS',
      accessor: (c: CreditSpread) => (
        <span className="font-mono">{c.spreadBps || '--'}</span>
      ),
      align: 'right' as const,
    },
    {
      header: '1W Chg',
      accessor: (c: CreditSpread) => (
        <span className={cn(
          'font-mono text-2xs',
          c.change1w && c.change1w > 0 ? 'text-red' :
          c.change1w && c.change1w < 0 ? 'text-green' : 'text-text-secondary'
        )}>
          {c.change1w ? `${c.change1w > 0 ? '+' : ''}${c.change1w.toFixed(0)}` : '--'}
        </span>
      ),
      align: 'right' as const,
    },
    {
      header: 'Signal',
      accessor: (c: CreditSpread) => {
        const variant = c.signal === 'COMPRESSION' ? 'success' :
                         c.signal === 'STRESS' ? 'danger' :
                         c.signal === 'DETERIORATING' ? 'warning' :
                         'neutral';
        return <Badge variant={variant}>{c.signal}</Badge>;
      },
      align: 'center' as const,
    },
  ];

  return (
    <Card title="FIXED INCOME DASHBOARD">
      <div className="grid grid-cols-2 gap-4">
        {/* Rates Table */}
        <div>
          <div className="text-2xs text-text-tertiary uppercase mb-2">Rates & Spreads</div>
          <Table
            data={data?.ratesTable}
            columns={ratesColumns}
            keyExtractor={(r) => r.instrument}
          />
        </div>

        {/* Credit Spreads */}
        <div>
          <div className="text-2xs text-text-tertiary uppercase mb-2">Credit Spreads</div>
          <Table
            data={data?.creditSpreads}
            columns={creditColumns}
            keyExtractor={(c) => c.name}
          />

          {/* Breakeven Inflation */}
          <div className="mt-4 p-3 border border-border-subtle bg-surface-2">
            <div className="text-2xs text-text-tertiary uppercase mb-2">Inflation Expectations</div>
            <div className="flex justify-between text-sm">
              <div>
                <div className="text-2xs text-text-tertiary">10Y Breakeven</div>
                <div className="font-mono">{data?.breakevenInflation?.tenYear?.toFixed(2) || '--'}%</div>
              </div>
              <div className="text-right">
                <div className="text-2xs text-text-tertiary">5Y5Y Forward</div>
                <div className="font-mono">{data?.breakevenInflation?.fiveYearFiveYear?.toFixed(2) || '--'}%</div>
              </div>
            </div>
            <div className="mt-2 text-2xs">
              <span className="text-text-tertiary">Real Yield Signal: </span>
              <span className={cn(
                data?.realYieldSignal === 'RESTRICTIVE' && 'text-red',
                data?.realYieldSignal === 'ACCOMMODATIVE' && 'text-green',
                data?.realYieldSignal === 'NEUTRAL' && 'text-text-secondary'
              )}>
                {data?.realYieldSignal}
              </span>
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}
