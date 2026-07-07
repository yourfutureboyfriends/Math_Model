// Section G Panel 4 — Fixed Income Dashboard + Phase 2 Store Integration
// Comprehensive rates and credit spreads using format library

import { Card } from '@/components/ui/Card';
import { SourceTag } from '@/components/ui/SourceTag';
import { Table } from '@/components/ui/Table';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';
import { useMacroStore } from '@/store/macroStore';
import { useApiData } from '@/hooks/useApiData';
import { fmtRate, fmtBps, fmtChange } from '@/utils/format';

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
  const { data, loading } = useApiData<FixedIncomeData>('/api/rates');

  // Use macro store for rates
  const prices = useMacroStore((state) => state.prices);
  const storeLoading = useMacroStore((state) => state.meta.dataStatus === 'loading');

  if (loading || storeLoading) {
    return <div className="h-64 bg-surface-1 border border-border animate-pulse" />;
  }

  // Build rates table with store data where available
  const buildRatesTable = (): RatesTableItem[] => {
    const table = data?.ratesTable || [];

    // Replace 10Y and 2Y with store data if available
    return table.map(item => {
      if (item.instrument === '10Y Treasury' && prices.TENYR) {
        return { ...item, yield: prices.TENYR };
      }
      if (item.instrument === '2Y Treasury' && prices.TWYR) {
        return { ...item, yield: prices.TWYR };
      }
      if (item.instrument === 'Fed Funds' && prices.FED) {
        return { ...item, yield: prices.FED };
      }
      return item;
    });
  };

  const ratesColumns = [
    { header: 'Instrument', accessor: (r: RatesTableItem) => r.instrument, align: 'left' as const },
    {
      header: 'Yield/Spread',
      accessor: (r: RatesTableItem) => (
        <span className="font-mono">{fmtRate(r.yield)}</span>
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
        <span className="font-mono">{fmtBps(c.spreadBps)}</span>
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
          {c.change1w ? fmtChange(c.change1w / 10000) : '--'}
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
    <Card
      title="FIXED INCOME DASHBOARD"
      headerRight={<SourceTag source="FRED · Yahoo" timestamp={(data as any)?.lastUpdated} staleAfterSeconds={900} />}
    >
      <div className="grid grid-cols-2 gap-4">
        {/* Rates Table */}
        <div>
          <div className="text-2xs text-text-tertiary uppercase mb-2">Rates & Spreads</div>
          <Table
            data={buildRatesTable()}
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
                <div className="font-mono">{data?.breakevenInflation?.tenYear != null ? fmtRate(data.breakevenInflation.tenYear) : '--'}</div>
              </div>
              <div className="text-right">
                <div className="text-2xs text-text-tertiary">5Y5Y Forward</div>
                <div className="font-mono">{data?.breakevenInflation?.fiveYearFiveYear != null ? fmtRate(data.breakevenInflation.fiveYearFiveYear) : '--'}</div>
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
