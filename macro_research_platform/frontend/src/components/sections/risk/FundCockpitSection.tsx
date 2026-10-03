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
import { fmtPct, fmtPrice, fmtSignal } from '@/utils/format';

type Tab = 'nav' | 'limits' | 'rebalance';

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

      <div className="flex gap-1 mb-3">
        {([['nav', 'NAV & Track Record'], ['limits', 'Risk Limits & Pre-trade'], ['rebalance', 'Rebalance']] as const).map(([k, label]) => (
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
      ) : (
        <RebalanceTab />
      )}
    </div>
  );
}
