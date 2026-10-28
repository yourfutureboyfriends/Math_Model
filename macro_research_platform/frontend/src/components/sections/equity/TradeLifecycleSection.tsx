/**
 * Trade Lifecycle — the Head of Trading's after-the-fact view: pitch → pre-trade assessment → order (four-eyes)
 * → fill, with transaction-cost analysis of each fill against its own pre-trade estimate; stock splits on held
 * positions (applied automatically when unambiguous, otherwise listed for review); and the NAV record by currency.
 * Backend: GET /api/v1/trading/lifecycle, /api/v1/corporate-actions (+ /apply), /api/v1/fund/nav-series.
 */
import { Fragment, useCallback, useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { apiCall } from '@/lib/http';
import { num } from '@/lib/format';

const bp = (v?: number | null) => (v == null || !Number.isFinite(v) ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(1)}`);
const costTone = (v?: number | null) => (v == null ? 'text-text-tertiary' : v > 0 ? 'text-red' : v < 0 ? 'text-green' : 'text-text-secondary');

const call = apiCall;

type Tab = 'lifecycle' | 'corp' | 'nav';

function Lifecycle() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  useEffect(() => { call('/api/v1/trading/lifecycle').then(setD).catch((e) => setErr(e.message)); }, []);
  if (err) return <div className="p-3 text-xs text-amber">{err}</div>;
  if (!d) return <div className="p-3 text-xs text-text-tertiary flex items-center gap-2"><Loader2 className="w-3 h-3 animate-spin" />Loading…</div>;
  const s = d.summary;
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 md:grid-cols-6 gap-2 text-xs">
        {[['Orders', s.orders], ['Executed', s.executed], ['With assessment', s.with_assessment], ['With pitch', s.with_pitch],
          ['Avg estimate (bp)', bp(s.avg_estimated_bps)], ['Avg shortfall (bp)', bp(s.avg_shortfall_bps)]].map(([k, v]) => (
          <div key={k as string} className="p-2 bg-surface-2 border border-border-subtle">
            <div className="text-2xs text-text-tertiary uppercase">{k}</div><div className="font-mono">{v}</div>
          </div>))}
      </div>
      {d.orders.length === 0 ? (
        <div className="text-xs text-text-tertiary p-2">No orders in this fund yet. Run a pre-trade assessment, then raise the order: it is linked to the assessment automatically (same name and side, within three days).</div>
      ) : (
        <table className="w-full text-xs">
          <thead><tr className="text-2xs text-text-tertiary uppercase border-b border-border-subtle">
            <th className="text-left font-normal py-1">Order</th><th className="text-left font-normal">Pitch</th>
            <th className="text-left font-normal">Assessment</th><th className="text-left font-normal">State</th>
            <th className="text-right font-normal">Fill</th><th className="text-right font-normal">Est. (bp)</th>
            <th className="text-right font-normal">Shortfall (bp)</th></tr></thead>
          <tbody>
            {d.orders.map((o: any) => (
              <Fragment key={o.order_id}>
                <tr className="border-b border-border-subtle cursor-pointer hover:bg-surface-2" onClick={() => setOpen(open === o.order_id ? null : o.order_id)}>
                  <td className="py-1 font-mono">#{o.order_id} {o.side} {num(o.quantity, 0)} {o.symbol}</td>
                  <td className="text-text-secondary">{o.pitch ? (o.pitch.missing ? `#${o.pitch.id} (missing)` : `#${o.pitch.id} ${o.pitch.status}`) : '—'}</td>
                  <td className="text-text-secondary">{o.assessment ? `#${o.assessment.id} ${o.assessment.verdict ?? ''}` : '—'}</td>
                  <td className="text-text-secondary">{o.state}{o.approved_by ? ` · ${o.approved_by}` : ''}</td>
                  <td className="text-right font-mono">{o.fill ? num(o.fill.price, 4) : '—'}</td>
                  <td className="text-right font-mono">{o.assessment ? bp(o.assessment.total_bps) : '—'}</td>
                  <td className={cn('text-right font-mono', costTone(o.tca?.actual?.implementation_shortfall_bps))}>{bp(o.tca?.actual?.implementation_shortfall_bps)}</td>
                </tr>
                {open === o.order_id && (
                  <tr className="border-b border-border-subtle bg-surface-2">
                    <td colSpan={7} className="p-2 text-2xs space-y-1">
                      {o.tca ? (
                        <table className="w-full max-w-xl">
                          <thead><tr className="text-text-tertiary"><th className="text-left font-normal">bp of notional (+ = cost)</th><th className="text-right font-normal">Estimate</th><th className="text-right font-normal">Actual</th><th className="text-right font-normal">Actual − est.</th></tr></thead>
                          <tbody className="font-mono">
                            <tr><td className="font-sans text-text-secondary">Decision → execution reference (market move)</td><td className="text-right">—</td><td className="text-right">{bp(o.tca.actual.delay_bps)}</td><td className="text-right">—</td></tr>
                            <tr><td className="font-sans text-text-secondary">Spread + impact</td><td className="text-right">{bp(o.tca.estimate?.execution_bps)}</td><td className="text-right">{bp(o.tca.actual.execution_bps)}</td><td className="text-right">{bp(o.tca.actual_minus_estimate_bps?.execution)}</td></tr>
                            <tr><td className="font-sans text-text-secondary">Commission + taxes</td><td className="text-right">{bp(o.tca.estimate?.explicit_bps)}</td><td className="text-right">{bp(o.tca.actual.explicit_bps)}</td><td className="text-right">{bp(o.tca.actual_minus_estimate_bps?.explicit)}</td></tr>
                            <tr className="font-medium"><td className="font-sans">Implementation shortfall</td><td className="text-right">{bp(o.tca.estimate?.total_bps)}</td><td className="text-right">{bp(o.tca.actual.implementation_shortfall_bps)}</td><td className="text-right">—</td></tr>
                          </tbody>
                        </table>
                      ) : <div className="text-text-tertiary">Not executed yet.</div>}
                      <div className="text-text-tertiary">
                        Decision price {num(o.tca?.decision_price ?? o.assessment?.decision_price, 4)} {o.assessment?.price_currency ?? ''}
                        {o.assessment ? ` (${o.assessment.market_state ?? ''}, ${String(o.assessment.ts).slice(0, 16).replace('T', ' ')} UTC, by ${o.assessment.user}; link: ${o.assessment.link ?? '—'})` : ''}
                        {o.fill ? ` · fill ${o.fill.source} ${String(o.fill.ts).slice(0, 16).replace('T', ' ')}` : ''}
                      </div>
                      {o.tca?.note && <div className="text-amber">{o.tca.note}</div>}
                      {o.tca?.note_fx && <div className="text-text-tertiary">{o.tca.note_fx}</div>}
                      {o.history?.length > 0 && (
                        <div className="text-text-tertiary">Trail: {o.history.map((h: any) => `${h.state ?? ''} (${h.by ?? ''})`).join(' → ')}</div>)}
                    </td>
                  </tr>)}
              </Fragment>))}
          </tbody>
        </table>)}
      <div className="text-[10px] text-text-tertiary">{d.method}</div>
    </div>
  );
}

function CorporateActions() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const load = useCallback(() => { call('/api/v1/corporate-actions').then(setD).catch((e) => setErr(e.message)); }, []);
  useEffect(load, [load]);
  const apply = async (p: any) => {
    setBusy(`${p.book}${p.symbol}${p.ex_date}`); setErr(null);
    try { await call('/api/v1/corporate-actions/apply', 'POST', { book: p.book, symbol: p.symbol, ex_date: p.ex_date, ratio: p.ratio }); load(); }
    catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  };
  if (!d) return <div className="p-3 text-xs text-text-tertiary">{err ?? 'Loading…'}</div>;
  return (
    <div className="space-y-3 text-xs">
      {err && <div className="text-amber">{err}</div>}
      <div>
        <div className="text-2xs text-text-tertiary uppercase mb-1">Pending</div>
        {d.pending.length === 0 ? <div className="text-text-tertiary">None — every split on a held position is applied.</div> : (
          <table className="w-full"><tbody>
            {d.pending.map((p: any) => (
              <tr key={`${p.book}${p.symbol}${p.ex_date}`} className="border-b border-border-subtle">
                <td className="py-1 font-mono">{p.symbol}</td><td>{p.book}</td><td className="font-mono">{p.ex_date}</td>
                <td className="font-mono">{p.ratio >= 1 ? `${p.ratio}:1 split` : `1:${num(1 / p.ratio, 2)} consolidation`}</td>
                <td className="text-text-secondary">{num(p.quantity, 4)} → {num(p.quantity * p.ratio, 4)} shares</td>
                <td className="text-amber">{p.reason ?? 'applied by the daily job'}</td>
                <td>{p.needs_review && (
                  <button disabled={!!busy} onClick={() => apply(p)} className="px-2 py-0.5 border border-border hover:border-bloomberg text-2xs">
                    {busy === `${p.book}${p.symbol}${p.ex_date}` ? 'Applying…' : 'Apply'}</button>)}</td>
              </tr>))}
          </tbody></table>)}
      </div>
      <div>
        <div className="text-2xs text-text-tertiary uppercase mb-1">Applied</div>
        {d.applied.length === 0 ? <div className="text-text-tertiary">None yet.</div> : (
          <table className="w-full"><tbody>
            {d.applied.map((a: any) => (
              <tr key={a.id} className="border-b border-border-subtle">
                <td className="py-1 font-mono">{a.symbol}</td><td>{a.book}</td><td className="font-mono">{a.ex_date}</td>
                <td className="font-mono">{num(a.ratio, 4)}:1</td>
                <td className="text-text-secondary">{num(a.quantity_before, 4)} → {num(a.quantity_after, 4)} sh · cost {num(a.avg_cost_before, 4)} → {num(a.avg_cost_after, 4)}</td>
                <td className="text-text-tertiary">{a.how} · {a.applied_by} · {String(a.applied_at).slice(0, 10)}</td>
              </tr>))}
          </tbody></table>)}
      </div>
      <div className="text-[10px] text-text-tertiary">Split history from Yahoo. On the ex-date shares × ratio and average cost ÷ ratio (value unchanged). Applied automatically each morning when the position predates the ex-date and nothing was traded in the name since; otherwise listed here for review. Blotter rows are never rewritten.</div>
    </div>
  );
}

function NavRecord() {
  const [d, setD] = useState<any>(null);
  useEffect(() => { call('/api/v1/fund/nav-series').then(setD).catch(() => setD({ series: [] })); }, []);
  if (!d) return <div className="p-3 text-xs text-text-tertiary">Loading…</div>;
  return (
    <div className="text-xs space-y-2">
      {d.series.length === 0 ? <div className="text-text-tertiary">No NAV snapshots yet (the first is taken after today's close).</div> : (
        <table className="w-full"><thead><tr className="text-2xs text-text-tertiary uppercase border-b border-border-subtle">
          <th className="text-left font-normal py-1">Currency</th><th className="text-left font-normal">From</th><th className="text-left font-normal">To</th>
          <th className="text-right font-normal">Snapshots</th><th className="text-right font-normal">Status</th></tr></thead>
          <tbody>{d.series.map((r: any) => (
            <tr key={r.start} className="border-b border-border-subtle"><td className="py-1 font-mono">{r.currency}</td><td className="font-mono">{r.start}</td>
              <td className="font-mono">{r.end}</td><td className="text-right font-mono">{r.snapshots}</td>
              <td className="text-right">{r.current ? 'current series' : 'earlier series (kept, not converted)'}</td></tr>))}
          </tbody></table>)}
      <div className="text-[10px] text-text-tertiary">Each snapshot records its currency. Paper / simulated NAV is not a fund track record. Changing the fund's base currency starts a new series; the earlier one is kept as recorded and never relabelled.</div>
    </div>
  );
}

export function TradeLifecycleSection() {
  const [tab, setTab] = useState<Tab>('lifecycle');
  return (
    <div className="border border-border bg-surface-1">
      <div className="px-3 py-2 border-b border-border flex items-center gap-3 flex-wrap">
        <span className="text-xs font-medium text-text-primary uppercase tracking-wider">Trade Lifecycle</span>
        {([['lifecycle', 'Lifecycle & TCA'], ['corp', 'Corporate actions'], ['nav', 'NAV record']] as [Tab, string][]).map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)} className={cn('text-2xs px-2 py-0.5 border', tab === k ? 'border-bloomberg text-bloomberg' : 'border-border text-text-tertiary hover:text-text-primary')}>{l}</button>))}
      </div>
      <div className="p-3">
        {tab === 'lifecycle' && <Lifecycle />}
        {tab === 'corp' && <CorporateActions />}
        {tab === 'nav' && <NavRecord />}
      </div>
    </div>
  );
}
