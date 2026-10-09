// Macro Trader — paper book that follows the macro model's asset-class allocation
// (api/macro_trader.py). Live book + the model's walk-forward backtest.
import { useCallback, useEffect, useState } from 'react';
import { Globe2, Loader2, Play, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { KpiStrip } from '@/components/ui/KpiStrip';
import { Donut } from '@/components/ui/Donut';
import { useAuth } from '@/context/AuthContext';
import { CATEGORICAL } from '@/lib/chartPalette';
import { api, ErrorNote, Field, inputCls, num, pct, Pills, spct, tone, usd } from '@/components/sections/model/quant/shared';

const NAMES: Record<string, string> = { SPY: 'US equity', EFA: 'Developed ex-US', EEM: 'EM equity', TLT: 'Long Treasuries',
  IEF: 'Intermediate Treasuries', TIP: 'TIPS', LQD: 'IG credit', HYG: 'HY credit', GLD: 'Gold', DBC: 'Commodities' };

export function MacroTrader() {
  const [view, setView] = useState<'live' | 'backtest'>('live');
  return (
    <div className="space-y-2">
      <div className="text-2xs text-text-secondary">
        Follows the <b>macro model</b>: growth &amp; inflation factors → regime odds → expected returns → a volatility-targeted mix of 10 asset-class ETFs.
        Rebalances monthly, on a regime change, or when a position drifts; orders fill at the next open. Paper only — separate from the Quant Trader.
      </div>
      <Pills label="Macro trader view" value={view} onChange={setView} options={[['live', 'Live book'], ['backtest', 'Model backtest']] as const} />
      {view === 'live' ? <Live /> : <Backtest />}
    </div>
  );
}

function Live() {
  const { user } = useAuth();
  const isPM = ['admin', 'pm'].includes(user?.role ?? '');
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const load = useCallback(() => { api('/api/v1/macro-trader').then(setD).catch((e) => setErr(e.message)); }, []);
  useEffect(load, [load]);

  const act = async (what: string, fn: () => Promise<any>) => {
    setBusy(what); setErr(null);
    try { await fn(); load(); } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  };
  if (!d) return err ? <ErrorNote msg={err} /> : <div className="flex items-center gap-2 text-2xs text-text-tertiary p-3"><Loader2 className="w-3 h-3 animate-spin" />Loading the macro book…</div>;
  const s = d.settings;
  const pending = d.orders.filter((o: any) => o.status === 'pending');
  const started = !!d.started || d.positions.some((p: any) => p.shares);
  const perf = d.performance;
  return (
    <div className="space-y-3">
      <ErrorNote msg={err} />
      <div className="flex flex-wrap items-center gap-2 text-2xs">
        <span className="px-2 py-0.5 border border-amber/50 text-amber">PAPER — SIMULATED</span>
        <span className={cn('px-2 py-0.5 border', s.enabled ? 'border-green/50 text-green' : 'border-border text-text-tertiary')}>{s.enabled ? 'Auto-trading on' : 'Paused'}</span>
        <span className="text-text-tertiary">Following the {s.portfolio} portfolio · model regime <b className="text-text-primary">{d.model?.regime ?? '—'}</b> · runs after each US close (22:35 UTC)</span>
        <div className="ml-auto flex gap-1">
          {isPM && <button onClick={() => act('run', () => api('/api/v1/macro-trader/run', { method: 'POST' }))} disabled={!!busy}
            className="inline-flex items-center gap-1 px-2.5 py-1 border border-bloomberg text-bloomberg hover:bg-bloomberg hover:text-bg disabled:opacity-50">
            {busy === 'run' ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}Run now</button>}
          <button onClick={load} aria-label="Refresh" className="px-2 py-1 border border-border hover:border-bloomberg"><RefreshCw className="w-3 h-3" /></button>
        </div>
      </div>
      {!started && pending.length === 0 && (
        <div className="p-3 border border-dashed border-border text-2xs text-text-secondary">
          The macro book has not traded yet. {isPM ? 'Press “Run now” to place the first allocation — it fills at the next market open.' : 'A PM can start it with “Run now”; otherwise it starts after the next US close.'}
        </div>
      )}
      <KpiStrip items={[
        { label: 'NAV', value: usd(d.nav), sub: `capital ${usd(d.capital)}`, accent: true },
        { label: 'Return', value: spct(d.return, 2), tone: tone(d.return), sub: d.started ? `since ${d.started}` : 'not started' },
        { label: 'Cash', value: usd(d.cash), sub: pct(d.nav ? d.cash / d.nav : null, 0) },
        { label: 'Sharpe (live)', value: num(perf?.sharpe), sub: perf ? `${perf.years} yrs` : 'needs history' },
        { label: 'Max drawdown', value: pct(perf?.max_drawdown), tone: 'down' },
        { label: 'Last rebalance', value: d.last_rebalance ?? '—', sub: `${pending.length} orders pending` },
      ]} />
      {d.nav_history.length > 1 && (
        <div className="p-3 bg-surface-1 border border-border">
          <LineChart rows={d.nav_history} x="date" height={200} fmt={(v) => usd(v)} baseline={d.capital}
            lines={[{ key: 'nav', label: 'Macro book NAV', color: CATEGORICAL[0] }]} />
        </div>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_260px] gap-2">
        <div className="p-3 bg-surface-1 border border-border overflow-x-auto">
          <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Positions vs the model's target</div>
          <table className="w-full text-2xs font-mono">
            <thead><tr className="text-text-tertiary"><th className="text-left font-normal">ETF</th><th className="text-left font-normal">Asset class</th>
              <th className="text-right font-normal">Shares</th><th className="text-right font-normal">Value</th><th className="text-right font-normal">Weight</th>
              <th className="text-right font-normal">Target</th><th className="text-right font-normal">Drift</th></tr></thead>
            <tbody>{d.positions.map((p: any) => {
              const drift = (p.weight ?? 0) - (p.target ?? 0);
              return (
                <tr key={p.symbol} className="border-t border-border-subtle">
                  <td className="text-text-primary">{p.symbol}</td><td className="text-text-secondary font-sans">{NAMES[p.symbol] ?? ''}</td>
                  <td className="text-right">{num(p.shares, 0)}</td><td className="text-right">{usd(p.value)}</td>
                  <td className="text-right">{pct(p.weight)}</td><td className="text-right">{pct(p.target)}</td>
                  <td className={cn('text-right', Math.abs(drift) > s.drift_threshold ? 'text-amber' : 'text-text-tertiary')}>{spct(drift)}</td>
                </tr>);
            })}</tbody>
          </table>
        </div>
        <div className="p-3 bg-surface-1 border border-border">
          <Donut title="Target allocation" fmt={(v) => pct(v, 0)} centerLabel="invested"
            centerValue={pct(Object.values(d.positions).reduce((a: number, p: any) => a + (p.target ?? 0), 0) as number, 0)}
            data={d.positions.filter((p: any) => p.target > 0).map((p: any) => ({ label: NAMES[p.symbol] ?? p.symbol, value: p.target }))} />
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
        <div className="p-3 bg-surface-1 border border-border">
          <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Orders</div>
          <div className="max-h-56 overflow-y-auto">
            {d.orders.length === 0 ? <div className="text-2xs text-text-tertiary">None yet.</div> : (
              <table className="w-full text-2xs font-mono"><tbody>{d.orders.map((o: any) => (
                <tr key={o.id} className="border-t border-border-subtle" title={o.reason}>
                  <td className={o.shares > 0 ? 'text-green' : 'text-red'}>{o.shares > 0 ? 'BUY' : 'SELL'}</td>
                  <td>{o.symbol}</td><td className="text-right">{num(Math.abs(o.shares), 0)}</td>
                  <td className="text-text-tertiary">{o.status === 'filled' ? `@ ${num(o.fill_price)} on ${o.fill_date}` : o.status === 'pending' ? `next open (placed ${o.placed_on})` : o.status}</td>
                </tr>))}</tbody></table>
            )}
          </div>
        </div>
        <div className="p-3 bg-surface-1 border border-border">
          <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Activity</div>
          <div className="max-h-56 overflow-y-auto space-y-1">
            {d.log.map((l: any) => <div key={l.id} className="text-2xs"><span className="font-mono text-text-tertiary">{String(l.ts).slice(0, 16).replace('T', ' ')}</span> <span className="text-text-secondary">{l.message}</span></div>)}
          </div>
        </div>
      </div>
      {isPM && <Settings s={s} onSaved={load} />}
    </div>
  );
}

function Settings({ s, onSaved }: { s: any; onSaved: () => void }) {
  const [f, setF] = useState({ portfolio: s.portfolio, drift_threshold: s.drift_threshold, cost_bps: s.cost_bps, enabled: s.enabled });
  const [err, setErr] = useState<string | null>(null);
  const save = async () => {
    setErr(null);
    try { await api('/api/v1/macro-trader/settings', { method: 'PUT', json: f }); onSaved(); } catch (e: any) { setErr(e.message); }
  };
  return (
    <div className="p-3 bg-surface-1 border border-border">
      <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-2">Settings</div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 items-end">
        <Field label="Follow" hint="Tactical tilts with the regime; strategic is the long-run risk-balanced mix.">
          <select className={inputCls} value={f.portfolio} onChange={(e) => setF({ ...f, portfolio: e.target.value })}>
            <option value="tactical">Tactical (regime-driven)</option><option value="strategic">Strategic (long-run)</option>
          </select>
        </Field>
        <Field label="Drift trigger %"><input type="number" min={1} max={50} className={inputCls} value={Math.round(f.drift_threshold * 100)} onChange={(e) => setF({ ...f, drift_threshold: Number(e.target.value) / 100 })} /></Field>
        <Field label="Cost per trade (bp)"><input type="number" min={0} max={100} className={inputCls} value={f.cost_bps} onChange={(e) => setF({ ...f, cost_bps: Number(e.target.value) })} /></Field>
        <label className="flex items-center gap-2 text-2xs text-text-secondary"><input type="checkbox" checked={f.enabled} onChange={(e) => setF({ ...f, enabled: e.target.checked })} />Auto-trade after each close</label>
      </div>
      <button onClick={save} className="mt-2 px-3 py-1 text-2xs border border-border hover:border-bloomberg">Save settings</button>
      <ErrorNote msg={err} />
    </div>
  );
}

function Backtest() {
  const [m, setM] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api('/api/v1/model').then(setM).catch((e) => setErr(e.message)); }, []);
  if (err) return <ErrorNote msg={err} />;
  if (!m) return <div className="flex items-center gap-2 text-2xs text-text-tertiary p-3"><Loader2 className="w-3 h-3 animate-spin" />Loading the macro model backtest…</div>;
  const bt = m.backtest;
  if (!bt?.available) return <div className="text-2xs text-text-tertiary p-3">The macro model backtest is not available yet.</div>;
  const st = bt.stats;
  const tvs = bt.tactical_vs_strategic;
  const fs = bt.forecast_skill;
  return (
    <div className="space-y-3">
      <div className="text-2xs text-text-secondary"><Globe2 className="w-3 h-3 inline mr-1" />Walk-forward, monthly, {bt.start} → {bt.end}; every month uses only data available then. Returns are {bt.returns_are}, net of {m.params.cost_bps} bp costs.</div>
      <div className="p-3 bg-surface-1 border border-border">
        <LineChart rows={bt.equity_curve} x="month" height={240} log baseline={1} fmt={(v) => `${v.toFixed(2)}×`}
          lines={[{ key: 'model', label: 'Tactical (traded)', color: CATEGORICAL[0] }, { key: 'strategic', label: 'Strategic', color: CATEGORICAL[1] },
            { key: 'sixty_forty', label: '60/40', color: '#6b7280' }, { key: 'risk_parity', label: 'Risk parity', color: CATEGORICAL[2] }]} />
      </div>
      <table className="w-full text-2xs font-mono">
        <thead><tr className="text-text-tertiary"><th className="text-left font-normal">Portfolio</th><th className="text-right font-normal">Return</th><th className="text-right font-normal">Vol</th>
          <th className="text-right font-normal">Sharpe</th><th className="text-right font-normal">Max DD</th><th className="text-right font-normal">Hit rate</th></tr></thead>
        <tbody>{Object.entries(st).map(([k, v]: [string, any]) => (
          <tr key={k} className={cn('border-t border-border-subtle', k.startsWith('Tactical') && 'text-text-primary')}>
            <td className="font-sans">{k}</td><td className="text-right">{spct(v.cagr)}</td><td className="text-right">{pct(v.vol)}</td>
            <td className="text-right">{num(v.sharpe)}</td><td className="text-right">{pct(v.max_drawdown, 0)}</td><td className="text-right">{pct(v.hit_rate, 0)}</td>
          </tr>))}</tbody>
      </table>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-2xs">
        <div className="p-3 bg-surface-1 border border-border">
          <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Does the tactical tilt add value?</div>
          <p className="text-text-secondary">Tactical beat strategic by {spct(tvs.annualised_diff)} a year (t = {num(tvs.t_stat, 2)}, information ratio {num(tvs.information_ratio)}).
            {tvs.significant_5pct ? ' Statistically significant.' : ' Not statistically significant — treat the regime tilt as a modest edge.'}</p>
        </div>
        <div className="p-3 bg-surface-1 border border-border">
          <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Forecast skill</div>
          <p className="text-text-secondary">Growth direction right {pct(fs.growth_direction.accuracy, 0)} of months (Brier skill {num(fs.growth_direction.skill)}), inflation {pct(fs.inflation_direction.accuracy, 0)} (skill {num(fs.inflation_direction.skill)}); top regime right {pct(fs.top_regime_hit_rate, 0)} over {fs.months_scored} months.</p>
        </div>
      </div>
    </div>
  );
}
