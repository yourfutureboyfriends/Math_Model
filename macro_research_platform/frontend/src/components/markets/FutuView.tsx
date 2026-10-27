// FUTU: real-time order book, tick-by-tick trades with the exchange's direction, capital flow by order size and the
// Hong Kong broker queue — from the user's own FutuOpenD gateway. Read-only: nothing here can place an order.
import { cn } from '@/lib/utils';
import { ErrorBox, fmtBig, Loading, Panel, useJSON } from './shared';

const enc = encodeURIComponent;
const pc = (x: number | null | undefined, d = 1) => (x == null ? '—' : `${(x * 100).toFixed(d)}%`);
const px = (x: number | null | undefined) => (x == null ? '—' : x.toLocaleString(undefined, { maximumFractionDigits: 3 }));

export function FutuView({ symbol }: { symbol: string }) {
  const st = useJSON<any>('/api/v1/mkt/futu/status', 30_000);
  const on = !!st.data?.connected && st.data?.logged_in !== false;
  const book = useJSON<any>(on ? `/api/v1/mkt/futu/book/${enc(symbol)}` : null, 3_000);
  const ticks = useJSON<any>(on ? `/api/v1/mkt/futu/ticks/${enc(symbol)}` : null, 5_000);
  const flow = useJSON<any>(on ? `/api/v1/mkt/futu/flow/${enc(symbol)}` : null, 30_000);
  const hk = symbol.toUpperCase().endsWith('.HK');
  const brokers = useJSON<any>(on && hk ? `/api/v1/mkt/futu/brokers/${enc(symbol)}` : null, 5_000);

  if (st.loading && !st.data) return <Loading label="Checking FutuOpenD…" />;
  if (!on) return (
    <Panel title="Futu — not connected">
      <div className="text-xs text-text-secondary space-y-1">
        <div>{st.data?.reason ?? 'FutuOpenD is not logged in.'}</div>
        <div className="text-text-tertiary">Open FutuOpenD on this computer and log in with your Futu account (the password stays in OpenD). This
          screen then shows the live order book, tick-by-tick trades, capital flow and — for Hong Kong stocks — the broker queue. Read-only.</div>
      </div>
    </Panel>);

  const b = book.data, t = ticks.data, f = flow.data;
  const maxVol = b ? Math.max(1, ...b.bids.map((x: any) => x.volume), ...b.asks.map((x: any) => x.volume)) : 1;
  return (
    <div className="space-y-3">
      <div className="text-[10px] text-text-tertiary">Futu OpenAPI via your FutuOpenD · entitlements: {Object.entries(st.data?.entitlements ?? {}).filter(([k]) => k.endsWith('qot_right')).map(([k, v]) => `${k.replace('_qot_right', '').toUpperCase()} ${v}`).join(' · ') || '—'}</div>
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
        <Panel title="Order book (live)">
          {book.error ? <ErrorBox msg={book.error} /> : !b ? <Loading /> : (
            <table className="w-full text-[11px] font-mono tabular-nums">
              <thead><tr className="text-text-tertiary"><th className="text-left font-normal">Bid vol</th><th className="text-right font-normal">Bid</th><th className="text-left font-normal pl-2">Ask</th><th className="text-right font-normal">Ask vol</th></tr></thead>
              <tbody>{Array.from({ length: Math.max(b.bids.length, b.asks.length) }).map((_, i) => {
                const bd = b.bids[i], ak = b.asks[i];
                return (
                  <tr key={i} className="border-t border-border-subtle">
                    <td className="relative">{bd && <span className="absolute inset-y-0 right-0 bg-green/15" style={{ width: `${(bd.volume / maxVol) * 100}%` }} />}<span className="relative">{bd ? fmtBig(bd.volume) : ''}</span></td>
                    <td className="text-right text-green">{bd ? px(bd.price) : ''}</td>
                    <td className="pl-2 text-red">{ak ? px(ak.price) : ''}</td>
                    <td className="relative text-right">{ak && <span className="absolute inset-y-0 left-0 bg-red/15" style={{ width: `${(ak.volume / maxVol) * 100}%` }} />}<span className="relative">{ak ? fmtBig(ak.volume) : ''}</span></td>
                  </tr>);
              })}</tbody>
            </table>)}
        </Panel>
        <Panel title={`Trades — ${t?.buy_share != null ? `${pc(t.buy_share, 0)} buyer-initiated` : 'tick by tick'}`}>
          {ticks.error ? <ErrorBox msg={ticks.error} /> : !t ? <Loading /> : (
            <div className="max-h-72 overflow-y-auto"><table className="w-full text-[11px] font-mono tabular-nums"><tbody>
              {t.ticks.slice(0, 120).map((x: any, i: number) => (
                <tr key={i} className="border-t border-border-subtle"><td className="text-text-tertiary">{String(x.time).slice(11, 19)}</td>
                  <td className={cn('text-right', x.side > 0 ? 'text-green' : x.side < 0 ? 'text-red' : '')}>{px(x.price)}</td>
                  <td className="text-right">{fmtBig(x.volume)}</td></tr>))}
            </tbody></table></div>)}
        </Panel>
        <Panel title="Capital flow today, by order size">
          {flow.error ? <ErrorBox msg={flow.error} /> : !f ? <Loading /> : (
            <div className="space-y-1 text-[11px]">
              {Object.entries(f.by_order_size ?? {}).map(([k, v]: [string, any]) => (
                <div key={k} className="flex items-center gap-2"><span className="w-12 text-text-tertiary capitalize">{k}</span>
                  <span className="font-mono text-green w-20 text-right">+{fmtBig(v.in)}</span><span className="font-mono text-red w-20 text-right">−{fmtBig(v.out)}</span>
                  <span className={cn('font-mono w-20 text-right', v.net >= 0 ? 'text-green' : 'text-red')}>{v.net >= 0 ? '+' : '−'}{fmtBig(Math.abs(v.net))}</span></div>))}
              <div className="text-[10px] text-text-tertiary pt-1">{f.note}</div>
            </div>)}
        </Panel>
      </div>
      {hk && (
        <Panel title="Broker queue (HKEX)">
          {brokers.error ? <ErrorBox msg={brokers.error} /> : !brokers.data ? <Loading /> : (
            <div className="grid grid-cols-2 gap-3 text-[11px]">
              {(['bid', 'ask'] as const).map((side) => (
                <div key={side}><div className={cn('mb-1 uppercase text-[10px]', side === 'bid' ? 'text-green' : 'text-red')}>{side}</div>
                  <div className="flex flex-wrap gap-1">{brokers.data[side].slice(0, 40).map((x: any, i: number) => (
                    <span key={i} className="px-1.5 py-0.5 border border-border-subtle" title={`level ${x.level}`}>{x.broker || x.broker_id}</span>))}</div></div>))}
            </div>)}
        </Panel>)}
      <div className="text-[10px] text-text-tertiary">Read-only: this screen cannot place, change or cancel orders. Data and entitlements come from your Futu account.</div>
    </div>
  );
}
