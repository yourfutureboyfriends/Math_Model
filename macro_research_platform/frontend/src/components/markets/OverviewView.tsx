// World markets at a glance: equity indices, rates & volatility, currencies, commodities,
// crypto — last price, 1-day / 1-month / YTD change and a 3-month sparkline. Click any row
// to open its workstation.
import { Chg, ErrorBox, fmtPrice, Loading, Panel, Spark, useJSON } from './shared';

export function OverviewView({ onOpen }: { onOpen: (s: string) => void }) {
  const { data, error, loading } = useJSON<any>('/api/v1/mkt/overview', 120_000);
  if (loading && !data) return <Loading label="Loading world markets…" />;
  if (error && !data) return <ErrorBox msg={error} />;
  if (!data) return null;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        {data.groups.map((g: any) => (
          <Panel key={g.group} title={g.group}>
            <table className="w-full text-2xs">
              <thead><tr className="text-text-tertiary">
                <th className="text-left font-normal pb-1">Instrument</th><th className="text-right font-normal">{g.is_yield ? 'Level' : 'Last'}</th>
                <th className="text-right font-normal">1D</th><th className="text-right font-normal hidden sm:table-cell">1M</th>
                <th className="text-right font-normal">YTD</th><th className="text-right font-normal hidden md:table-cell">3M</th></tr></thead>
              <tbody>
                {g.rows.map((r: any) => (
                  <tr key={r.symbol} onClick={() => onOpen(r.symbol)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-3"
                    title={`${r.symbol}${r.date ? ` · ${r.date}` : ''} — open workstation`}>
                    <td className="py-1"><span className="text-text-primary">{r.name}</span> <span className="font-mono text-text-tertiary">{r.symbol}</span></td>
                    <td className="text-right font-mono text-text-primary">{r.price == null ? '—' : g.is_yield ? r.price.toFixed(2) : fmtPrice(r.price, g.group === 'Currencies' ? 'FX' : undefined)}</td>
                    {r.is_yield ? <>
                      <td className="text-right"><Bp v={r.change_1d_bp} /></td>
                      <td className="text-right hidden sm:table-cell"><Bp v={r.change_1m_bp} /></td>
                      <td className="text-right"><Bp v={r.change_ytd_bp} /></td>
                    </> : <>
                      <td className="text-right"><Chg v={r.change_1d} /></td>
                      <td className="text-right hidden sm:table-cell"><Chg v={r.change_1m} d={1} /></td>
                      <td className="text-right"><Chg v={r.change_ytd} d={1} /></td>
                    </>}
                    <td className="text-right hidden md:table-cell"><Spark values={r.spark} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        ))}
      </div>
      <div className="text-[10px] text-text-tertiary">{data.source} · daily closes, exchange delays apply · refreshed every 2 minutes. Yields in percent; their changes in basis points.</div>
    </div>
  );
}

function Bp({ v }: { v: number | null | undefined }) {
  // Rising yields = falling bond prices; colour by the yield move itself (neutral palette would hide it).
  return <span className={v == null ? 'text-text-tertiary font-mono' : v > 0 ? 'text-red font-mono' : v < 0 ? 'text-green font-mono' : 'text-text-secondary font-mono'}>
    {v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(0)}bp`}</span>;
}
