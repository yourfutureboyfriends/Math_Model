/**
 * Broker link (Interactive Brokers) for the current fund — read-only: connection status, set-up steps, the broker's
 * positions and cash, reconciliation against the platform book, and a one-time import of the broker's positions.
 * No order routing. Backend: /api/v1/broker/ibkr* (api/brokerage/ibkr.py).
 */
import { useCallback, useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useConfirm } from '@/components/ui/ConfirmDialog';

async function call(url: string, method = 'GET', body?: any) {
  const r = await fetch(url, { method, headers: body ? { 'Content-Type': 'application/json' } : undefined, body: body ? JSON.stringify(body) : undefined });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : `HTTP ${r.status}`);
  return j;
}
const btn = 'px-2 py-1 border border-border hover:border-bloomberg text-2xs disabled:opacity-40';
const num = (v: any, d = 2) => (v == null || v === '' ? '—' : Number(v).toLocaleString(undefined, { maximumFractionDigits: d }));

export function BrokerLink() {
  const [st, setSt] = useState<any>(null);
  const [snap, setSnap] = useState<any>(null);
  const [rec, setRec] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [dialog, ask] = useConfirm();
  const load = useCallback(() => { call('/api/v1/broker/ibkr').then(setSt).catch((e) => setErr(e.message)); }, []);
  useEffect(load, [load]);
  const run = async (k: string, fn: () => Promise<any>) => { setBusy(k); setErr(null); try { await fn(); } catch (e: any) { setErr(e.message); } finally { setBusy(null); } };
  if (!st) return <div className="text-2xs text-text-tertiary">{err ?? 'Loading…'}</div>;
  const ready = st.flex_configured || st.gateway?.authenticated;
  return (
    <div className="space-y-3 text-xs">
      {dialog}
      <div className="grid md:grid-cols-3 gap-2">
        <div className="border border-border bg-surface-2 p-2">
          <div className="text-2xs text-text-tertiary uppercase mb-1">Account</div>
          <div className="font-mono">{st.account_id ?? <span className="text-amber">not pinned</span>}</div>
          <div className="text-[10px] text-text-tertiary">Only this account's data is accepted for this fund.</div>
        </div>
        <div className="border border-border bg-surface-2 p-2">
          <div className="text-2xs text-text-tertiary uppercase mb-1">Flex statements (daily, read-only)</div>
          <div className={st.flex_configured ? 'text-green' : 'text-amber'}>{st.flex_configured ? 'configured' : 'not configured'}</div>
        </div>
        <div className="border border-border bg-surface-2 p-2">
          <div className="text-2xs text-text-tertiary uppercase mb-1">Client Portal Gateway (live)</div>
          <div className={st.gateway?.authenticated ? 'text-green' : st.gateway?.reachable ? 'text-amber' : 'text-text-tertiary'}>
            {st.gateway?.authenticated ? 'signed in' : st.gateway?.reachable ? 'running — sign in to it' : 'not running'}</div>
          <div className="text-[10px] text-text-tertiary font-mono">{st.gateway_url}</div>
        </div>
      </div>
      {!ready && (
        <div className="border border-border bg-surface-2 p-2 text-[11px] text-text-secondary space-y-1">
          <div className="text-2xs text-text-tertiary uppercase">Set-up (the account holder does this — credentials never go through the app)</div>
          <div><b>Statements (recommended first):</b> in IBKR Account Management → Performance &amp; Reports → Flex Queries, create an Activity Flex Query with
            Open Positions, Trades and Cash Report, XML format; then Reports → Settings → Flex Web Service → generate a token. Put them in the server's <span className="font-mono">.env</span>:</div>
          <pre className="bg-surface-1 border border-border p-2 font-mono text-[10px] whitespace-pre-wrap">{st.env_keys.map((k: string) => `${k}=…`).join('\n')}</pre>
          <div><b>Live (optional):</b> run IBKR's Client Portal Gateway on this machine and sign in to it at {st.gateway_url} in your browser.</div>
          <div className="text-text-tertiary">Education / paper accounts: check that Flex Queries and the Web API are enabled for the account type in Account Management. Then restart the backend.</div>
        </div>)}
      {err && <div className="text-amber text-2xs">{err}</div>}
      <div className="flex flex-wrap gap-1">
        <button className={btn} disabled={!ready || !!busy} onClick={() => run('snap', async () => setSnap(await call('/api/v1/broker/ibkr/snapshot')))}>
          {busy === 'snap' ? <Loader2 className="w-3 h-3 animate-spin inline" /> : 'Fetch broker positions'}</button>
        <button className={btn} disabled={!ready || !!busy} onClick={() => run('rec', async () => setRec(await call('/api/v1/broker/ibkr/reconcile', 'POST')))}>
          {busy === 'rec' ? <Loader2 className="w-3 h-3 animate-spin inline" /> : 'Reconcile book with IBKR'}</button>
        <button className={btn} disabled={!ready || !!busy} onClick={() => run('imp', async () => {
          if (!(await ask({ title: 'Replace the book with IBKR positions?', danger: true, confirmLabel: 'Import',
            body: "Positions in the 'IBKR' book are replaced by the broker's (quantity and average cost). Audit-logged. Use once to onboard, or to re-base after a break you have investigated." }))) return;
          const r = await call('/api/v1/broker/ibkr/import', 'POST', { book: 'IBKR', confirm: true });
          setErr(`Imported ${r.imported} position(s) from ${r.source} (account ${r.account_id}).${r.notes?.length ? ' ' + r.notes.join('; ') : ''}`);
        })}>Import positions into the book</button>
        <span className="text-[10px] text-text-tertiary self-center">Read-only link: no orders are sent to IBKR.</span>
      </div>
      {rec && (
        <div className={cn('border p-2', rec.ok ? 'border-green/40' : 'border-red/40')}>
          <div className={rec.ok ? 'text-green' : 'text-red'}>{rec.ok ? `Reconciled: ${rec.matched} position(s) match IBKR` : `${rec.breaks.length} break(s) — an incident was opened`}</div>
          {rec.breaks.length > 0 && <table className="w-full mt-1"><tbody>{rec.breaks.map((b: any) => (
            <tr key={b.ticker} className="border-b border-border-subtle"><td className="py-0.5 font-mono">{b.ticker}</td><td>{b.status.replace('_', ' ')}</td>
              <td className="text-right font-mono">platform {num(b.platform, 4)}</td><td className="text-right font-mono">IBKR {num(b.broker, 4)}</td></tr>))}</tbody></table>}
        </div>)}
      {snap && (
        <div className="border border-border p-2">
          <div className="text-2xs text-text-tertiary uppercase mb-1">IBKR {snap.source} · account {snap.account_id}</div>
          <table className="w-full"><thead><tr className="text-2xs text-text-tertiary border-b border-border-subtle"><th className="text-left font-normal py-1">Symbol</th><th className="text-left font-normal">Exchange</th>
            <th className="text-right font-normal">Quantity</th><th className="text-right font-normal">Mark</th><th className="text-right font-normal">Avg cost</th><th className="text-right font-normal">Value</th></tr></thead>
            <tbody>{snap.positions.map((p: any, i: number) => (
              <tr key={i} className="border-b border-border-subtle"><td className="py-0.5 font-mono">{p.symbol}</td><td>{p.exchange} · {p.currency}</td>
                <td className="text-right font-mono">{num(p.quantity, 4)}</td><td className="text-right font-mono">{num(p.mark_price, 4)}</td>
                <td className="text-right font-mono">{num(p.cost_price, 4)}</td><td className="text-right font-mono">{num(p.market_value)}</td></tr>))}</tbody></table>
          {snap.cash?.length > 0 && <div className="text-[11px] text-text-secondary mt-1">Cash: {snap.cash.map((c: any) => `${c.currency} ${num(c.ending_cash)}`).join(' · ')}</div>}
        </div>)}
    </div>
  );
}
