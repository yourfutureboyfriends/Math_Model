// Quant Trader — paper book of the systematic algos deployed from the Quant Lab
// (api/quant/trader.py), plus the stock entry-model book (its own rules and backtest).
import { useCallback, useEffect, useState } from 'react';
import { Loader2, RefreshCw, Square } from 'lucide-react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { KpiStrip } from '@/components/ui/KpiStrip';
import { Donut } from '@/components/ui/Donut';
import { useAuth } from '@/context/AuthContext';
import { CATEGORICAL } from '@/lib/chartPalette';
import { api, ErrorNote, num, pct, Pills, spct, tone, usd } from '@/components/sections/model/quant/shared';

const STATUS: Record<string, string> = {
  'on track': 'border-green/50 text-green', 'too early': 'border-border text-text-tertiary',
  'below range': 'border-red/50 text-red', 'above range': 'border-amber/50 text-amber',
};

export function QuantTrader({ stockLive, stockBacktest }: { stockLive: React.ReactNode; stockBacktest: React.ReactNode }) {
  const [view, setView] = useState<'algos' | 'stock' | 'stock_bt'>('algos');
  return (
    <div className="space-y-2">
      <div className="text-2xs text-text-secondary">
        Runs <b>systematic quant algos</b> — strategies you build or pick in the <a href="#quant-lab" className="underline text-bloomberg">Quant Lab</a> and deploy here — plus the stock entry-model book.
        Paper only; separate from the Macro Trader.
      </div>
      <Pills label="Quant trader view" value={view} onChange={setView}
        options={[['algos', 'Deployed algos'], ['stock', 'Stock entry book'], ['stock_bt', 'Stock book backtest']] as const} />
      {view === 'algos' && <Algos />}
      {view === 'stock' && stockLive}
      {view === 'stock_bt' && stockBacktest}
    </div>
  );
}

function Algos() {
  const { user } = useAuth();
  const canManage = ['admin', 'pm', 'quant'].includes(user?.role ?? '');
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback((refresh = false) => {
    setBusy(true); setErr(null);
    api(`/api/v1/quant/trader${refresh ? '?refresh=true' : ''}`).then(setD).catch((e) => setErr(e.message)).finally(() => setBusy(false));
  }, []);
  useEffect(() => load(), [load]);
  const stop = async (dep: any) => {
    if (!window.confirm(`Stop “${dep.name}”? Its paper record ends today.`)) return;
    try { await api(`/api/v1/quant/trader/deployments/${dep.id}`, { method: 'DELETE' }); load(true); } catch (e: any) { setErr(e.message); }
  };
  if (!d) return err ? <ErrorNote msg={err} /> : <div className="flex items-center gap-2 text-2xs text-text-tertiary p-3"><Loader2 className="w-3 h-3 animate-spin" />Updating deployed algos…</div>;
  if (!d.deployments.length) return (
    <div className="p-4 border border-dashed border-border text-2xs text-text-secondary">
      No algos deployed yet. Open the <a href="#quant-lab" className="underline text-bloomberg">Quant Lab</a>, backtest a template or your own formula, then press <b>Deploy to Quant Trader</b>.
      {d.errors?.length > 0 && <ErrorNote msg={d.errors.map((e: any) => `${e.name}: ${e.error}`).join(' · ')} />}
    </div>
  );
  return (
    <div className="space-y-3">
      <ErrorNote msg={err} />
      <div className="flex items-center gap-2 text-2xs">
        <span className="px-2 py-0.5 border border-amber/50 text-amber">PAPER — SIMULATED</span>
        <span className="text-text-tertiary">Each algo trades at the next open after its signal, with its costs. Live = days after deployment only.</span>
        <button onClick={() => load(true)} disabled={busy} aria-label="Refresh" className="ml-auto px-2 py-1 border border-border hover:border-bloomberg disabled:opacity-50">
          {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}</button>
      </div>
      <KpiStrip items={[
        { label: 'Book NAV', value: usd(d.nav), sub: `capital ${usd(d.capital)}`, accent: true },
        { label: 'Return', value: spct(d.return, 2), tone: tone(d.return) },
        { label: 'Algos running', value: String(d.deployments.length) },
        { label: 'Gross exposure', value: d.gross_exposure == null ? '—' : `${num(d.gross_exposure)}×` },
        { label: 'Positions', value: String(d.exposure.length) },
        { label: 'Updated', value: String(d.as_of).slice(11, 16) + ' UTC' },
      ]} />
      {d.curve.length > 1 && (
        <div className="p-3 bg-surface-1 border border-border">
          <LineChart rows={d.curve} x="date" height={200} baseline={d.capital} fmt={(v) => usd(v)} lines={[{ key: 'nav', label: 'Quant book NAV', color: CATEGORICAL[0] }]} />
        </div>
      )}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-2">
        {d.deployments.map((x: any) => {
          const band = x.expected_range ?? {};
          return (
            <div key={x.id} className="p-3 bg-surface-1 border border-border space-y-1.5">
              <div className="flex items-start gap-2">
                <div className="min-w-0">
                  <div className="text-xs font-semibold text-text-primary truncate" title={x.name}>{x.name}</div>
                  <div className="text-[10px] text-text-tertiary">live since {x.deployed_at} · {x.live_days} sessions · {x.rebalance} · by {x.owner}</div>
                </div>
                <span className={cn('ml-auto shrink-0 px-2 py-0.5 border text-[10px] uppercase', STATUS[x.status] ?? STATUS['too early'])}>{x.status}</span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-2xs">
                <div><div className="text-text-tertiary text-[10px]">NAV</div><div className="font-mono">{usd(x.nav)}</div></div>
                <div><div className="text-text-tertiary text-[10px]">Live return</div><div className={cn('font-mono', x.live_return > 0 ? 'text-green' : x.live_return < 0 ? 'text-red' : '')}>{spct(x.live_return, 2)}</div></div>
                <div><div className="text-text-tertiary text-[10px]">Backtest</div><div className="font-mono">{spct(x.backtest?.cagr)} · SR {num(x.backtest?.sharpe)}</div></div>
              </div>
              {band.p5 != null && (
                <div className="text-[10px] text-text-tertiary">
                  Backtest-implied range for {x.live_days} sessions: {spct(band.p5)} to {spct(band.p95)} (median {spct(band.p50)}).
                  {x.status === 'below range' && <span className="text-red"> Worse than 95% of backtest paths — review it.</span>}
                </div>
              )}
              {x.positions.length > 0 && (
                <div className="text-[10px] font-mono text-text-secondary break-words">
                  {x.positions.slice(0, 10).map((p: any) => `${p.symbol} ${spct(p.weight, 0)}`).join(' · ')}{x.positions.length > 10 ? ` · +${x.positions.length - 10} more` : ''}
                </div>
              )}
              {canManage && <button onClick={() => stop(x)} className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] border border-border text-text-secondary hover:border-red hover:text-red"><Square className="w-2.5 h-2.5" />Stop</button>}
            </div>
          );
        })}
      </div>
      {d.exposure.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-2">
          <div className="p-3 bg-surface-1 border border-border">
            <Donut title="Book exposure (longs)" fmt={(v) => usd(v)} data={d.exposure.filter((e: any) => e.usd > 0).map((e: any) => ({ label: e.symbol, value: e.usd }))} />
          </div>
          <div className="p-3 bg-surface-1 border border-border overflow-x-auto">
            <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Combined target positions</div>
            <table className="w-full text-2xs font-mono"><tbody>{d.exposure.map((e: any) => (
              <tr key={e.symbol} className="border-t border-border-subtle"><td>{e.symbol}</td>
                <td className={cn('text-right', e.usd < 0 && 'text-red')}>{usd(e.usd)}</td><td className="text-right text-text-tertiary">{pct(e.weight)}</td></tr>))}</tbody></table>
          </div>
        </div>
      )}
      {d.errors?.length > 0 && <ErrorNote msg={d.errors.map((e: any) => `${e.name}: ${e.error}`).join(' · ')} />}
    </div>
  );
}
