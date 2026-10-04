/**
 * FundCockpitSection — hedge-fund layer: NAV & track record, risk limits with pre-trade
 * compliance, and the regime rebalance engine.
 *
 * Reads /api/v1/fund/overview, /api/v1/risk/limits, /api/v1/risk/pretrade,
 * /api/v1/portfolio/rebalance (+ /stage) and /api/v1/fund/snapshot. Writes carry the
 * logged-in user (X-User) so the audit trail records who acted.
 */
import { useCallback, useEffect, useState } from 'react';
import { Briefcase, RefreshCw } from 'lucide-react';
import { actorHeaders } from '@/lib/actor';
import { useAuth } from '@/context/AuthContext';
import { fmtPct, fmtPrice, fmtSignal } from '@/utils/format';

type Tab = 'nav' | 'limits' | 'rebalance' | 'orders' | 'scorecard';

const usd = (v: number | null | undefined) =>
  v == null ? '—' : `${v < 0 ? '-' : ''}$${fmtPrice(Math.abs(v), 0)}`;
const pct = (v: number | null | undefined, d = 1) => fmtPct(v ?? null, d);
const pctSigned = (v: number | null | undefined, d = 2) => fmtPct(v ?? null, d, true);

const STATUS_STYLE: Record<string, string> = {
  OK: 'text-green border-green/40', WARN: 'text-amber border-amber/40', BREACH: 'text-red border-red/40',
  PASS: 'text-green border-green/40', BLOCK: 'text-red border-red/40',
};

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="p-2 bg-surface-1 border border-border">
      <div className="text-2xs text-text-tertiary uppercase tracking-wider">{label}</div>
      <div className={`text-sm font-mono font-bold ${tone ?? 'text-text-primary'}`}>{value}</div>
    </div>
  );
}

function NavTab({ ov }: { ov: any }) {
  const tr = ov?.track_record;
  const pf = ov?.proforma;
  const exp = ov?.exposures ?? {};
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
        <Stat label="NAV" value={usd(ov?.nav)} />
        <Stat label="Unrealized P&L" value={usd(ov?.unrealized_pnl)}
              tone={(ov?.unrealized_pnl ?? 0) >= 0 ? 'text-green' : 'text-red'} />
        <Stat label="Gross" value={pct(exp.gross)} />
        <Stat label="Net" value={pct(exp.net)} />
        <Stat label="VaR 95% 1d" value={usd(ov?.var95_1d_usd)} />
        <Stat label="Vol target" value={pct(ov?.fund?.vol_target, 0)} />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
        <Stat label="Cash" value={usd(ov?.cash)} />
        <Stat label="Realized P&L" value={usd(ov?.realized_pnl)}
              tone={(ov?.realized_pnl ?? 0) >= 0 ? 'text-green' : 'text-red'} />
        <Stat label="Commissions" value={usd(ov?.commissions)} />
        <Stat label="Equity beta $" value={usd(ov?.factor_exposure_usd?.equity)} />
        <Stat label="Rates beta $" value={usd(ov?.factor_exposure_usd?.rates)} />
        <Stat label="USD beta $" value={usd(ov?.factor_exposure_usd?.usd)} />
      </div>

      <div className="p-3 bg-surface-1 border border-border">
        <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">
          Track record — {tr?.basis}
        </div>
        {tr?.available ? (
          <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
            <Stat label="Total return" value={pctSigned(tr.total_return)} />
            <Stat label="Ann. vol" value={pct(tr.annualized_vol)} />
            <Stat label="Sharpe" value={tr.sharpe == null ? '—' : fmtSignal(tr.sharpe)} />
            <Stat label="Max DD" value={pctSigned(tr.max_drawdown)} tone="text-red" />
            <Stat label="Hit rate" value={pct(tr.hit_rate, 0)} />
            <Stat label="Days" value={String(tr.observations)} />
          </div>
        ) : (
          <div className="text-xs text-text-secondary">
            Recording started {ov?.fund?.inception_date ?? 'today'} — {tr?.observations ?? 0} daily
            snapshot{tr?.observations === 1 ? '' : 's'} so far (taken automatically after each US close).
            Statistics appear once there are at least two.
          </div>
        )}
      </div>

      {pf?.stats?.available && (
        <div className="p-3 bg-surface-1 border border-amber/30">
          <div className="text-2xs text-amber uppercase tracking-wider mb-2">Pro-forma (hypothetical)</div>
          <div className="text-2xs text-text-tertiary mb-2">{pf.basis}</div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            <Stat label="Ann. return" value={pctSigned(pf.stats.annualized_return)} />
            <Stat label="Ann. vol" value={pct(pf.stats.annualized_vol, 2)} />
            <Stat label="Sharpe" value={pf.stats.sharpe == null ? '—' : fmtSignal(pf.stats.sharpe)} />
            <Stat label="Max DD" value={pctSigned(pf.stats.max_drawdown)} tone="text-red" />
            <Stat label="Days" value={String(pf.stats.observations)} />
          </div>
        </div>
      )}
    </div>
  );
}

function LimitsTab({ limits, onChanged }: { limits: any; onChanged: () => void }) {
  const [symbol, setSymbol] = useState('');
  const [qty, setQty] = useState('');
  const [check, setCheck] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  const runCheck = async () => {
    const q = Number(qty);
    if (!symbol.trim() || !q) return;
    setBusy(true);
    try {
      const r = await fetch('/api/v1/risk/pretrade', {
        method: 'POST', headers: actorHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ symbol: symbol.trim().toUpperCase(), quantity: q }),
      });
      setCheck(await r.json());
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-xs">
        <span className="text-text-tertiary">Overall:</span>
        <span className={`px-2 py-0.5 border font-mono font-bold ${STATUS_STYLE[limits?.overall] ?? ''}`}>
          {limits?.overall ?? '—'}
        </span>
        <button onClick={onChanged} className="ml-auto text-2xs text-text-tertiary hover:text-bloomberg">refresh</button>
      </div>
      <div className="bg-surface-1 border border-border">
        {(limits?.limits ?? []).map((l: any) => {
          const util = Math.min(1.2, l.utilization ?? 0);
          const isPct = l.unit !== 'days';
          const fmt = (v: number | null) => v == null ? '—' : isPct ? pct(v) : `${fmtSignal(v).replace('+', '')}d`;
          return (
            <div key={l.metric} className="flex items-center gap-3 px-3 py-1.5 text-xs border-b border-border-subtle last:border-0">
              <span className="w-44 shrink-0 text-text-secondary">{l.label}</span>
              <div className="flex-1 relative h-2 bg-surface-3">
                <div className="absolute top-0 bottom-0 bg-amber/40" style={{ left: `${(l.soft / l.hard) * 100 / 1.2}%`, width: '1px' }} />
                <div className={`h-full ${l.status === 'BREACH' ? 'bg-red' : l.status === 'WARN' ? 'bg-amber' : 'bg-green'}`}
                     style={{ width: `${(util / 1.2) * 100}%` }} />
              </div>
              <span className="w-20 text-right font-mono">{l.available ? fmt(l.value) : 'n/a'}</span>
              <span className="w-28 text-right font-mono text-text-tertiary">{fmt(l.soft)} / {fmt(l.hard)}</span>
              <span className={`w-16 text-center border text-2xs font-mono ${STATUS_STYLE[l.status]}`}>{l.status}</span>
            </div>
          );
        })}
      </div>

      <div className="p-3 bg-surface-1 border border-border">
        <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Pre-trade compliance check</div>
        <div className="flex flex-wrap items-end gap-2">
          <input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="Ticker"
                 className="w-28 bg-surface-2 border border-border px-2 py-1 text-xs font-mono" />
          <input value={qty} onChange={(e) => setQty(e.target.value)} placeholder="Qty (− to sell)"
                 className="w-32 bg-surface-2 border border-border px-2 py-1 text-xs font-mono" />
          <button onClick={runCheck} disabled={busy}
                  className="px-3 py-1 text-xs border border-bloomberg text-bloomberg hover:bg-bloomberg/10 disabled:opacity-50">
            {busy ? 'Checking…' : 'Check'}
          </button>
          {check?.decision && (
            <span className={`px-2 py-1 border font-mono font-bold text-xs ${STATUS_STYLE[check.decision]}`}>
              {check.decision}
            </span>
          )}
          {check?.trade && (
            <span className="text-2xs text-text-tertiary font-mono">
              {usd(check.trade.notional)} · {pct(check.trade.pct_nav)} of NAV
            </span>
          )}
          {check?.detail && <span className="text-2xs text-red">{String(check.detail)}</span>}
        </div>
        {check?.reasons?.length > 0 && (
          <ul className="mt-2 text-2xs text-text-secondary space-y-0.5">
            {check.reasons.map((r: string) => <li key={r}>• {r}</li>)}
          </ul>
        )}
      </div>
    </div>
  );
}

function RebalanceTab() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [staged, setStaged] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setStaged(null);
    try { setData(await fetch('/api/v1/portfolio/rebalance?book=Macro').then((r) => r.json())); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const stage = async () => {
    if (!data?.orders?.length) return;
    const r = await fetch('/api/v1/portfolio/rebalance/stage', {
      method: 'POST', headers: actorHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ book: data.book, regime: data.regime, orders: data.orders }),
    });
    const j = await r.json();
    setStaged(r.ok ? `${j.staged} orders sent to Trade Workflow for approval` : `Failed: ${j.detail ?? r.status}`);
  };

  if (loading && !data) return <div className="p-4 text-xs text-text-secondary">Building target portfolio…</div>;
  if (data && data.available === false) return <div className="p-4 text-xs text-text-secondary">{data.reason}</div>;
  if (!data) return null;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
        <Stat label="Regime" value={String(data.regime ?? '—')} />
        <Stat label="Sleeve NAV" value={usd(data.sleeve_nav)} />
        <Stat label="Leverage" value={`${fmtSignal(data.leverage).replace('+', '')}x${data.gross_capped ? ' (cap)' : ''}`}
              tone={data.gross_capped ? 'text-amber' : undefined} />
        <Stat label="Expected vol" value={pct(data.expected_vol)} />
        <Stat label="Turnover" value={pct(data.turnover_pct_nav)} />
        <Stat label="Est. cost" value={usd(data.est_total_cost)} />
      </div>
      <div className="text-2xs text-text-tertiary">{data.method}</div>

      <div className="grid md:grid-cols-2 gap-3">
        <div className="bg-surface-1 border border-border">
          <div className="px-3 py-1.5 text-2xs text-text-tertiary uppercase tracking-wider border-b border-border">Target portfolio</div>
          <table className="w-full text-xs">
            <thead><tr className="text-text-tertiary text-2xs">
              <th className="text-left px-3 py-1">Asset</th><th className="text-right px-2">Budget</th>
              <th className="text-right px-2">Risk share</th><th className="text-right px-3">Weight</th></tr></thead>
            <tbody>
              {data.weights.map((w: any) => (
                <tr key={w.symbol} className="border-t border-border-subtle">
                  <td className="px-3 py-1"><span className="font-mono text-text-primary">{w.symbol}</span>
                    <span className="text-text-tertiary"> · {w.name}</span></td>
                  <td className="text-right px-2 font-mono">{pct(w.budget)}</td>
                  <td className="text-right px-2 font-mono">{pct(w.risk_share)}</td>
                  <td className="text-right px-3 font-mono font-bold">{pct(w.weight)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="bg-surface-1 border border-border">
          <div className="px-3 py-1.5 text-2xs text-text-tertiary uppercase tracking-wider border-b border-border flex items-center">
            Orders ({data.order_count})
            <button onClick={stage} disabled={!data.order_count}
                    className="ml-auto px-2 py-0.5 border border-bloomberg text-bloomberg normal-case tracking-normal hover:bg-bloomberg/10 disabled:opacity-40">
              Stage for approval
            </button>
          </div>
          <table className="w-full text-xs">
            <thead><tr className="text-text-tertiary text-2xs">
              <th className="text-left px-3 py-1">Order</th><th className="text-right px-2">Qty</th>
              <th className="text-right px-2">Notional</th><th className="text-right px-3">Cost</th></tr></thead>
            <tbody>
              {data.orders.map((o: any) => (
                <tr key={o.symbol} className="border-t border-border-subtle">
                  <td className="px-3 py-1">
                    <span className={o.side === 'BUY' ? 'text-green' : 'text-red'}>{o.side}</span>{' '}
                    <span className="font-mono">{o.symbol}</span>
                    <span className="text-text-tertiary text-2xs"> {o.action}</span>
                  </td>
                  <td className="text-right px-2 font-mono">{o.quantity.toLocaleString()}</td>
                  <td className="text-right px-2 font-mono">{usd(o.notional)}</td>
                  <td className="text-right px-3 font-mono text-text-tertiary">{usd(o.est_cost)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {staged && <div className="px-3 py-1.5 text-2xs text-green border-t border-border">{staged}</div>}
        </div>
      </div>
    </div>
  );
}


const STATE_STYLE: Record<string, string> = {
  Proposed: 'text-amber', 'Under Review': 'text-amber', Approved: 'text-blue',
  Executed: 'text-green', Closed: 'text-text-tertiary',
};

function OrdersTab({ onBooked }: { onBooked: () => void }) {
  // UI mirrors the server's role rules (the server enforces them regardless).
  const { user } = useAuth();
  const role = user?.role ?? '';
  const canApprove = role === 'risk' || role === 'admin';
  const canExecute = role === 'pm' || role === 'admin';
  const [orders, setOrders] = useState<any[]>([]);
  const [mode, setMode] = useState<string>('simulated');
  const [blotter, setBlotter] = useState<any>(null);
  const [ticket, setTicket] = useState({ symbol: '', side: 'BUY', quantity: '', book: 'Macro', thesis: '' });
  const [msg, setMsg] = useState<{ text: string; tone: string } | null>(null);
  const [notes, setNotes] = useState<Record<number, string>>({});

  const load = useCallback(async () => {
    const [o, b] = await Promise.all([
      fetch('/api/v1/orders').then((r) => r.json()).catch(() => null),
      fetch('/api/v1/blotter?limit=50').then((r) => r.json()).catch(() => null),
    ]);
    setOrders(o?.orders ?? []); setMode(o?.execution_mode ?? 'simulated'); setBlotter(b);
  }, []);
  useEffect(() => { load(); }, [load]);

  const errText = (j: any) => {
    const d = j?.detail;
    if (!d) return 'request failed';
    if (typeof d === 'string') return d;
    return [d.message, ...(d.reasons ?? []), d.detail].filter(Boolean).join(' · ');
  };

  const post = async (url: string, body?: any) => {
    const r = await fetch(url, {
      method: 'POST', headers: actorHeaders({ 'Content-Type': 'application/json' }),
      body: body ? JSON.stringify(body) : undefined,
    });
    return { ok: r.ok, j: await r.json().catch(() => ({})) };
  };

  const submit = async () => {
    const q = Number(ticket.quantity);
    if (!ticket.symbol.trim() || !q || q <= 0) { setMsg({ text: 'Enter a ticker and a positive quantity', tone: 'text-amber' }); return; }
    const { ok, j } = await post('/api/v1/orders', { ...ticket, symbol: ticket.symbol.trim().toUpperCase(), quantity: q });
    setMsg(ok ? { text: `Order #${j.order.id} queued — pre-trade ${j.pretrade.decision}${j.pretrade.reasons?.length ? ': ' + j.pretrade.reasons.join('; ') : ''}`,
                  tone: j.pretrade.decision === 'BLOCK' ? 'text-red' : j.pretrade.decision === 'WARN' ? 'text-amber' : 'text-green' }
              : { text: errText(j), tone: 'text-red' });
    load();
  };

  const act = async (id: number, action: 'approve' | 'reject' | 'execute') => {
    const body = action === 'execute' ? undefined : { note: notes[id] || null };
    const { ok, j } = await post(`/api/v1/orders/${id}/${action}`, body);
    setMsg(ok ? { text: action === 'execute'
                    ? `Order #${id} filled: ${j.trade.side} ${j.trade.quantity} ${j.trade.symbol} @ ${fmtPrice(j.trade.price)} (${j.trade.source})`
                    : `Order #${id} ${action === 'approve' ? 'approved' : 'rejected'}`, tone: 'text-green' }
              : { text: `Order #${id}: ${errText(j)}`, tone: 'text-red' });
    load();
    if (ok && action === 'execute') onBooked();
  };

  const open = orders.filter((o) => !['Executed', 'Closed'].includes(o.state));
  const done = orders.filter((o) => ['Executed', 'Closed'].includes(o.state)).slice(0, 10);
  const input = 'bg-surface-2 border border-border px-2 py-1 text-xs font-mono';

  return (
    <div className="space-y-3">
      <div className="p-3 bg-surface-1 border border-border">
        <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2 flex items-center">
          Order ticket
          <span className="ml-auto normal-case tracking-normal">
            Execution: <span className={mode === 'simulated' ? 'text-amber' : 'text-green'}>{mode === 'simulated' ? 'SIMULATED (last close)' : 'ALPACA PAPER'}</span>
            {' · '}four-eyes: a different user must approve
          </span>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <input aria-label="Order ticker" placeholder="Ticker" value={ticket.symbol}
                 onChange={(e) => setTicket({ ...ticket, symbol: e.target.value })} className={`w-24 ${input}`} />
          <select aria-label="Order side" value={ticket.side} onChange={(e) => setTicket({ ...ticket, side: e.target.value })}
                  className={input}>
            <option>BUY</option><option>SELL</option>
          </select>
          <input aria-label="Order quantity" placeholder="Quantity" value={ticket.quantity}
                 onChange={(e) => setTicket({ ...ticket, quantity: e.target.value })} className={`w-24 ${input}`} />
          <input aria-label="Order book" placeholder="Book" value={ticket.book}
                 onChange={(e) => setTicket({ ...ticket, book: e.target.value })} className={`w-24 ${input}`} />
          <input aria-label="Order thesis" placeholder="Thesis (optional)" value={ticket.thesis}
                 onChange={(e) => setTicket({ ...ticket, thesis: e.target.value })} className={`flex-1 min-w-40 ${input}`} />
          <button onClick={submit} className="px-3 py-1 text-xs border border-bloomberg text-bloomberg hover:bg-bloomberg/10">Submit for approval</button>
        </div>
        {msg && <div className={`mt-2 text-2xs ${msg.tone}`}>{msg.text}</div>}
      </div>

      <div className="bg-surface-1 border border-border">
        <div className="px-3 py-1.5 text-2xs text-text-tertiary uppercase tracking-wider border-b border-border">Open orders ({open.length})</div>
        {open.length === 0 ? <div className="px-3 py-3 text-xs text-text-secondary">No open orders.</div> : (
          <table className="w-full text-xs">
            <tbody>
              {open.map((o) => (
                <tr key={o.id} className="border-t border-border-subtle">
                  <td className="px-3 py-1.5 font-mono text-text-tertiary">#{o.id}</td>
                  <td className="px-2"><span className={o.side === 'BUY' ? 'text-green' : 'text-red'}>{o.side}</span>{' '}
                    <span className="font-mono">{o.quantity?.toLocaleString()} {o.symbol}</span>
                    <span className="text-text-tertiary"> · {o.book}</span></td>
                  <td className={`px-2 ${STATE_STYLE[o.state] ?? ''}`}>{o.state}</td>
                  <td className="px-2 text-text-tertiary">by {o.created_by}{o.approved_by ? ` · ok ${o.approved_by}` : ''}</td>
                  <td className="px-2">
                    {o.state !== 'Approved' && canApprove && (
                      <input aria-label={`Note for order ${o.id}`} placeholder="note" value={notes[o.id] ?? ''}
                             onChange={(e) => setNotes({ ...notes, [o.id]: e.target.value })} className={`w-32 ${input}`} />
                    )}
                  </td>
                  <td className="px-3 text-right whitespace-nowrap space-x-1">
                    {o.state !== 'Approved' ? (
                      canApprove ? (
                        <>
                          <button onClick={() => act(o.id, 'approve')} disabled={o.created_by === user?.username}
                                  title={o.created_by === user?.username ? 'Four-eyes: you created this order' : undefined}
                                  className="px-2 py-0.5 border border-green/50 text-green hover:bg-green/10 disabled:opacity-40">Approve</button>
                          <button onClick={() => act(o.id, 'reject')} className="px-2 py-0.5 border border-red/50 text-red hover:bg-red/10">Reject</button>
                        </>
                      ) : <span className="text-2xs text-text-tertiary">awaiting risk approval</span>
                    ) : canExecute ? (
                      <button onClick={() => act(o.id, 'execute')} className="px-2 py-0.5 border border-bloomberg text-bloomberg hover:bg-bloomberg/10">Execute</button>
                    ) : <span className="text-2xs text-text-tertiary">awaiting execution (PM)</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="grid md:grid-cols-2 gap-3">
        <div className="bg-surface-1 border border-border">
          <div className="px-3 py-1.5 text-2xs text-text-tertiary uppercase tracking-wider border-b border-border flex">
            Blotter
            <span className="ml-auto normal-case tracking-normal">
              Cash {usd(blotter?.cash)} · Realized {usd(blotter?.realized_pnl)} · Comm. {usd(blotter?.commissions)}
            </span>
          </div>
          {!blotter?.trades?.length ? <div className="px-3 py-3 text-xs text-text-secondary">No trades booked yet.</div> : (
            <table className="w-full text-xs">
              <thead><tr className="text-text-tertiary text-2xs">
                <th className="text-left px-3 py-1">Time</th><th className="text-left px-2">Trade</th>
                <th className="text-right px-2">Price</th><th className="text-right px-2">Realized</th><th className="text-right px-3">Pos after</th></tr></thead>
              <tbody>
                {blotter.trades.map((t: any) => (
                  <tr key={t.id} className="border-t border-border-subtle">
                    <td className="px-3 py-1 text-text-tertiary font-mono">{String(t.ts).slice(5, 16).replace('T', ' ')}</td>
                    <td className="px-2"><span className={t.side === 'BUY' ? 'text-green' : 'text-red'}>{t.side}</span>{' '}
                      <span className="font-mono">{t.quantity.toLocaleString()} {t.symbol}</span>
                      <span className="text-text-tertiary"> · {t.source}</span></td>
                    <td className="text-right px-2 font-mono">{fmtPrice(t.price)}</td>
                    <td className={`text-right px-2 font-mono ${t.realized_pnl >= 0 ? 'text-green' : 'text-red'}`}>{usd(t.realized_pnl)}</td>
                    <td className="text-right px-3 font-mono">{t.position_after?.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div className="bg-surface-1 border border-border">
          <div className="px-3 py-1.5 text-2xs text-text-tertiary uppercase tracking-wider border-b border-border">Recent decisions</div>
          {done.length === 0 ? <div className="px-3 py-3 text-xs text-text-secondary">None yet.</div> : (
            <table className="w-full text-xs"><tbody>
              {done.map((o) => (
                <tr key={o.id} className="border-t border-border-subtle">
                  <td className="px-3 py-1 font-mono text-text-tertiary">#{o.id}</td>
                  <td className="px-2 font-mono">{o.side} {o.quantity?.toLocaleString()} {o.symbol}</td>
                  <td className={`px-2 ${STATE_STYLE[o.state] ?? ''}`}>{o.state === 'Closed' ? 'Rejected/Closed' : o.state}</td>
                  <td className="px-3 text-text-tertiary truncate max-w-48">{o.state_history?.[o.state_history.length - 1]?.note ?? ''}</td>
                </tr>
              ))}
            </tbody></table>
          )}
        </div>
      </div>
    </div>
  );
}

function ScorecardTab() {
  const [sc, setSc] = useState<any>(null);
  useEffect(() => { fetch('/api/v1/models/scorecard').then((r) => r.json()).then(setSc).catch(() => setSc({})); }, []);
  if (!sc) return <div className="p-4 text-xs text-text-secondary">Scoring models…</div>;
  const rt = sc.regime_transition ?? {};
  const rec = sc.recession ?? {};
  return (
    <div className="space-y-3">
      <div className="p-3 bg-surface-1 border border-border">
        <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Regime transition model — {rt.method}</div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          <Stat label="Forecasts" value={String(rt.forecasts ?? '—')} />
          <Stat label="Hit rate" value={pct(rt.hit_rate)} />
          <Stat label="Naive 'no change'" value={pct(rt.naive_persistence_hit_rate)} />
          <Stat label="Skill vs naive" value={pctSigned(rt.skill_vs_naive, 1)}
                tone={(rt.skill_vs_naive ?? 0) > 0.005 ? 'text-green' : 'text-amber'} />
          <Stat label="Brier" value={rt.brier == null ? '—' : String(rt.brier)} />
        </div>
        {rt.verdict && <div className="mt-2 text-xs text-text-secondary">Verdict: {rt.verdict}</div>}
      </div>
      <div className="p-3 bg-surface-1 border border-border">
        <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Recession model (12-month horizon) — {rec.note}</div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          <Stat label="Genuine forecasts" value={String(rec.logged_forecasts ?? '—')} />
          <Stat label="Resolved" value={String(rec.resolved ?? 0)} />
          <Stat label="Pending" value={String(rec.pending ?? 0)} />
          <Stat label="First resolves" value={rec.next_resolution ? String(rec.next_resolution).slice(0, 7) : '—'} />
          <Stat label="Brier" value={rec.brier == null ? 'n/a yet' : String(rec.brier)} />
        </div>
        {rec.excluded_non_genuine > 0 && (
          <div className="mt-2 text-2xs text-text-tertiary">
            {rec.excluded_non_genuine} logged rows excluded: back-filled or from a retired model — scoring them would score hindsight, not forecasts.
          </div>
        )}
      </div>
      {Array.isArray(sc.signals) && (
        <div className="bg-surface-1 border border-border">
          <div className="px-3 py-1.5 text-2xs text-text-tertiary uppercase tracking-wider border-b border-border">Signals (independent 21-day windows)</div>
          <table className="w-full text-xs"><tbody>
            {sc.signals.map((s: any) => (
              <tr key={s.label} className="border-t border-border-subtle">
                <td className="px-3 py-1">{s.label}</td>
                <td className="px-2 text-right font-mono">hit {pct(s.hit_rate_independent)}</td>
                <td className="px-2 text-right font-mono">n={s.independent}</td>
                <td className={`px-2 text-right font-mono ${s.p_value != null && s.p_value < 0.05 ? 'text-green' : 'text-amber'}`}>
                  p={s.p_value ?? '—'}</td>
                <td className="px-3 text-right font-mono">Sharpe {s.sharpe ?? '—'}</td>
              </tr>
            ))}
          </tbody></table>
          <div className="px-3 py-1.5 text-2xs text-text-tertiary border-t border-border">p &lt; 0.05 = statistically distinguishable from a coin flip.</div>
        </div>
      )}
    </div>
  );
}

export function FundCockpitSection() {
  const [tab, setTab] = useState<Tab>('nav');
  const [ov, setOv] = useState<any>(null);
  const [limits, setLimits] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [o, l] = await Promise.all([
        fetch('/api/v1/fund/overview').then((r) => r.json()).catch(() => null),
        fetch('/api/v1/risk/limits').then((r) => r.json()).catch(() => null),
      ]);
      setOv(o); setLimits(l);
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const snapshot = async () => {
    await fetch('/api/v1/fund/snapshot', { method: 'POST', headers: actorHeaders() });
    load();
  };

  return (
    <div id="fund-cockpit" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><Briefcase className="w-3 h-3" /></span>
          <h2 className="section-title">Fund Cockpit</h2>
          {ov?.fund && <span className="section-meta">{ov.fund.fund_name} · {ov.fund.base_currency}</span>}
          {limits?.overall && (
            <span className={`ml-2 px-1.5 border text-2xs font-mono ${STATUS_STYLE[limits.overall]}`}>
              LIMITS {limits.overall}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={snapshot} className="text-2xs px-2 py-0.5 border border-border text-text-secondary hover:text-bloomberg"
                  title="Record today's NAV now (also runs automatically after the US close)">Snapshot NAV</button>
          <button onClick={load} title="Refresh" aria-label="Refresh" className="p-1 text-text-tertiary hover:text-bloomberg">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-1 mb-3">
        {([['nav', 'NAV & Track Record'], ['limits', 'Risk Limits & Pre-trade'], ['rebalance', 'Rebalance'],
           ['orders', 'Orders & Blotter'], ['scorecard', 'Model Scorecard']] as const).map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)}
                  className={`px-3 py-1 text-xs border ${tab === k ? 'border-bloomberg text-bloomberg bg-bloomberg/10' : 'border-border text-text-secondary hover:text-text-primary'}`}>
            {label}
          </button>
        ))}
      </div>

      {loading && !ov ? (
        <div className="p-6 text-center text-sm text-text-secondary">Loading fund state…</div>
      ) : tab === 'nav' ? (
        <NavTab ov={ov} />
      ) : tab === 'limits' ? (
        <LimitsTab limits={limits} onChanged={load} />
      ) : tab === 'rebalance' ? (
        <RebalanceTab />
      ) : tab === 'orders' ? (
        <OrdersTab onBooked={load} />
      ) : (
        <ScorecardTab />
      )}
    </div>
  );
}
