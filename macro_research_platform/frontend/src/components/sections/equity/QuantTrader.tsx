// Three separate paper traders: Macro (asset-class model book + macro algos), Fundamental (stocks chosen on company
// fundamentals) and Technical (stocks on price/volume + the stock entry-model book). api/quant/trader.py keeps them apart.
import { memo, useCallback, useEffect, useState } from 'react';
import { useConfirm } from '@/components/ui/ConfirmDialog';
import { Loader2, RefreshCw, Square } from 'lucide-react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { KpiStrip } from '@/components/ui/KpiStrip';
import { Donut } from '@/components/ui/Donut';
import { useAuth } from '@/context/AuthContext';
import { CATEGORICAL } from '@/lib/chartPalette';
import { api, ErrorNote, money, num, pct, Pills, spct, tone, usd } from '@/components/sections/model/quant/shared';
import { DeepAnalysis } from '@/components/sections/model/quant/DeepReport';

const STATUS: Record<string, string> = {
  'on track': 'border-green/50 text-green', 'too early': 'border-border text-text-tertiary',
  'below range': 'border-red/50 text-red', 'above range': 'border-amber/50 text-amber',
};

/** Macro Quant Trader — asset-class books only: the macro model's allocation (incl. Bridgewater All Weather)
 *  and systematic macro algos (trend, momentum, GTAA, risk parity across ETFs). No single stocks. */
export function MacroQuantTrader({ modelBook }: { modelBook: React.ReactNode }) {
  const [view, setView] = useState<'model' | 'algos'>('model');
  return (
    <div className="space-y-2">
      <div className="text-2xs text-text-secondary">
        <b>Macro quant trading</b> — asset classes only (equity indices, bonds, credit, commodities, gold, sectors, countries).
        The <b>model book</b> follows the macro model or Bridgewater’s All Weather; <b>macro algos</b> are systematic strategies on ETF universes deployed from the
        <a href="#quant-lab" className="underline text-bloomberg"> Quant Lab</a>. Kept completely separate from the Fundamental and Technical Quant Traders. Paper only.
      </div>
      <Pills label="Macro trader view" value={view} onChange={setView} options={[['model', 'Model book'], ['algos', 'Macro algos']] as const} />
      {view === 'model' && modelBook}
      {view === 'algos' && <Algos book="macro" />}
    </div>
  );
}

/** Fundamental Quant Trader — single stocks chosen on company fundamentals (value, quality, profitability). */
export function FundamentalQuantTrader() {
  return (
    <div className="space-y-2">
      <div className="text-2xs text-text-secondary">
        <b>Fundamental quant trading</b> — individual companies chosen on what the accounts say: value (earnings, book, cash-flow yields), quality and
        profitability, built from point-in-time SEC filings in the <a href="#quant-lab" className="underline text-bloomberg">Quant Lab</a>.
        Separate from the Macro and Technical Quant Traders. Paper only.
      </div>
      <Algos book="fundamental" />
    </div>
  );
}

/** Technical Quant Trader — single stocks traded on price and volume only: momentum, reversal, breakouts, low volatility,
 *  and the stock entry-model book (price set-ups with stops and targets). */
export function TechnicalQuantTrader({ stockLive, stockBacktest }: { stockLive: React.ReactNode; stockBacktest: React.ReactNode }) {
  const [view, setView] = useState<'algos' | 'stock' | 'stock_bt'>('algos');
  return (
    <div className="space-y-2">
      <div className="text-2xs text-text-secondary">
        <b>Technical quant trading</b> — individual stocks traded on price and volume alone: momentum and 52-week highs, short-term reversal, pullbacks,
        low volatility, and the stock entry book (price set-ups with stops and targets, gated by the market’s trend). Algos come from the
        <a href="#quant-lab" className="underline text-bloomberg"> Quant Lab</a>. Separate from the Macro and Fundamental Quant Traders. Paper only.
      </div>
      <Pills label="Technical trader view" value={view} onChange={setView}
        options={[['algos', 'Technical algos'], ['stock', 'Stock entry book'], ['stock_bt', 'Stock book backtest']] as const} />
      {view === 'algos' && <Algos book="technical" />}
      {view === 'stock' && stockLive}
      {view === 'stock_bt' && stockBacktest}
    </div>
  );
}

function Algos({ book }: { book: 'macro' | 'fundamental' | 'technical' }) {
  const { user } = useAuth();
  const canManage = ['admin', 'pm', 'quant'].includes(user?.role ?? '');
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialog, ask] = useConfirm();
  const load = useCallback((refresh = false, quiet = false) => {
    if (!quiet) setBusy(true);
    setErr(null);
    api(`/api/v1/quant/trader?book=${book}${refresh ? '&refresh=true' : ''}`).then(setD).catch((e) => setErr(e.message)).finally(() => setBusy(false));
  }, [book]);
  useEffect(() => load(), [load]);
  // the server answers at once from its latest results and refreshes stale algos in the background: poll quietly
  useEffect(() => {
    if (!d?.refreshing) return;
    const t = setTimeout(() => load(false, true), 15_000);
    return () => clearTimeout(t);
  }, [d, load]);
  const [showAll, setShowAll] = useState(false);
  const stop = async (dep: any) => {
    if (!(await ask({ title: `Stop “${dep.name}”?`, body: 'Its paper record ends today.', confirmLabel: 'Stop', danger: true }))) return;
    try { await api(`/api/v1/quant/trader/deployments/${dep.id}`, { method: 'DELETE' }); load(true); } catch (e: any) { setErr(e.message); }
  };
  if (!d) return err ? <ErrorNote msg={err} /> : <div className="flex items-center gap-2 text-2xs text-text-tertiary p-3"><Loader2 className="w-3 h-3 animate-spin" />Updating deployed algos…</div>;
  const pending = (d.pending ?? []) as any[];
  if (!d.deployments.length && pending.length) return (
    <div className="flex items-center gap-2 p-3 text-2xs text-text-secondary border border-border">
      <Loader2 className="w-3 h-3 animate-spin" />Preparing {pending.map((x) => `“${x.name}”`).join(', ')} for the first time — a large universe can take a few minutes; this page updates by itself.
    </div>
  );
  if (!d.deployments.length) return (
    <div className="p-4 border border-dashed border-border text-2xs text-text-secondary">
      No {book} algos deployed yet. Open the <a href="#quant-lab" className="underline text-bloomberg">Quant Lab</a>, run a {({ macro: 'cross-asset / ETF', fundamental: 'value or quality (company-fundamentals)', technical: 'stock momentum, reversal or low-volatility' } as const)[book]} strategy from the library or your own code, then press <b>Deploy</b> — it is routed to this trader automatically.
      {d.errors?.length > 0 && <ErrorNote msg={d.errors.map((e: any) => `${e.name}: ${e.error}`).join(' · ')} />}
    </div>
  );
  return (
    <div className="space-y-3">
      {dialog}
      <ErrorNote msg={err} />
      <div className="flex items-center gap-2 text-2xs">
        <span className="px-2 py-0.5 border border-amber/50 text-amber">PAPER — SIMULATED</span>
        <span className="text-text-tertiary">Each algo trades at the next open after its signal, with its costs. Live = days after deployment only.</span>
        {d.refreshing && <span className="inline-flex items-center gap-1 text-text-tertiary"><Loader2 className="w-3 h-3 animate-spin" />{pending.length ? `preparing ${pending.length} new algo${pending.length > 1 ? 's' : ''}…` : 'updating with today’s data…'}</span>}
        <button onClick={() => load(true)} disabled={busy} aria-label="Refresh" className="ml-auto px-2 py-1 border border-border hover:border-bloomberg disabled:opacity-50">
          {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}</button>
      </div>
      <KpiStrip items={[
        { label: 'Book NAV (USD)', value: usd(d.nav), sub: `capital ${usd(d.capital)}${d.deployments?.some((x: any) => x.currency && x.currency !== 'USD') ? ' · other-currency accounts converted at as-of FX' : ''}`, accent: true },
        { label: 'Return', value: spct(d.return, 2), tone: tone(d.return) },
        { label: 'Algos running', value: String(d.deployments.length) },
        { label: 'Gross exposure', value: d.gross_exposure == null ? '—' : `${num(d.gross_exposure)}×` },
        { label: 'Positions', value: String(d.positions_total ?? d.exposure.length) },
        { label: 'Updated', value: String(d.as_of).slice(11, 16) + ' UTC' },
      ]} />
      {d.curve.length > 1 && (
        <div className="p-3 bg-surface-1 border border-border">
          <LineChart rows={d.curve} x="date" height={200} baseline={d.capital} fmt={(v) => usd(v)} lines={[{ key: 'nav', label: `${({ macro: 'Macro', fundamental: 'Fundamental', technical: 'Technical' } as const)[book]} algos NAV`, color: CATEGORICAL[0] }]} />
        </div>
      )}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-2">
        {d.deployments.map((x: any) => <AlgoCard key={x.id} x={x} canManage={canManage} onStop={stop} />)}
      </div>
      {d.exposure.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-2">
          <div className="p-3 bg-surface-1 border border-border">
            <Donut title="Book exposure by sector (longs)" fmt={(v) => usd(v)}
              data={(d.by_sector ?? []).filter((e: any) => e.usd > 0).map((e: any) => ({ label: e.sector, value: e.usd }))} />
          </div>
          <div className="p-3 bg-surface-1 border border-border overflow-x-auto">
            <div className="flex items-baseline gap-2 mb-1">
              <div className="text-[10px] uppercase tracking-wide text-text-tertiary">Largest combined positions</div>
              <div className="text-[10px] text-text-tertiary">{d.positions_total ?? d.exposure.length} in total</div>
            </div>
            <table className="w-full text-2xs font-mono"><tbody>
              {(showAll ? d.exposure : d.exposure.slice(0, 15)).map((e: any) => (
                <tr key={e.symbol} className="border-t border-border-subtle"><td>{e.symbol}</td>
                  <td className="font-sans text-text-tertiary truncate max-w-[10rem]">{e.sector}</td>
                  <td className={cn('text-right', e.usd < 0 && 'text-red')}>{usd(e.usd)}</td><td className="text-right text-text-tertiary">{pct(e.weight)}</td></tr>))}
              {(() => {
                const hidden = showAll ? [] : d.exposure.slice(15);
                const n = hidden.length + (d.exposure_other?.count ?? 0);
                const v = hidden.reduce((a: number, e: any) => a + e.usd, 0) + (d.exposure_other?.usd ?? 0);
                return n > 0 ? (
                  <tr className="border-t border-border-subtle text-text-tertiary"><td colSpan={2} className="font-sans">Other {n} position{n === 1 ? '' : 's'}</td>
                    <td className="text-right">{usd(v)}</td><td className="text-right">{d.nav ? pct(v / d.nav) : '—'}</td></tr>) : null;
              })()}
            </tbody></table>
            {d.exposure.length > 15 && (
              <button onClick={() => setShowAll(!showAll)} className="mt-1 text-[10px] underline text-text-tertiary">
                {showAll ? 'show fewer' : `show top ${d.exposure.length}`}</button>)}
          </div>
        </div>
      )}
      {d.errors?.length > 0 && <ErrorNote msg={d.errors.map((e: any) => `${e.name}: ${e.error}`).join(' · ')} />}
    </div>
  );
}

/** One deployed algo: headline numbers, range check, its five largest holdings (expandable), deep analysis on demand. */
const AlgoCard = memo(function AlgoCard({ x, canManage, onStop }: { x: any; canManage: boolean; onStop: (x: any) => void }) {
  const [more, setMore] = useState(false);
  const band = x.expected_range ?? {};
  const shown = more ? x.positions : x.positions.slice(0, 5);
  const hiddenCount = (x.positions_count ?? x.positions.length) - shown.length;
  return (
    <div className="p-3 bg-surface-1 border border-border space-y-1.5">
      <div className="flex items-start gap-2">
        <div className="min-w-0">
          <div className="text-xs font-semibold text-text-primary truncate" title={x.name}>{x.name}</div>
          <div className="text-[10px] text-text-tertiary">live since {x.deployed_at} · {x.live_days} sessions{x.rebalance ? ` · ${x.rebalance}` : ''} · by {x.owner}</div>
        </div>
        <span className={cn('ml-auto shrink-0 px-2 py-0.5 border text-[10px] uppercase', STATUS[x.status] ?? STATUS['too early'])}>{x.status}</span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-2xs">
        <div><div className="text-text-tertiary text-[10px]">NAV{x.currency && x.currency !== 'USD' ? ` (${x.currency})` : ''}</div>
          <div className="font-mono">{money(x.nav, x.currency || 'USD')}</div>
          {x.currency && x.currency !== 'USD' && <div className="text-[10px] text-text-tertiary font-mono">≈ {usd(x.nav_usd)}</div>}</div>
        <div><div className="text-text-tertiary text-[10px]">Live return</div><div className={cn('font-mono', x.live_return > 0 ? 'text-green' : x.live_return < 0 ? 'text-red' : '')}>{spct(x.live_return, 2)}</div></div>
        <div><div className="text-text-tertiary text-[10px]">Backtest</div><div className="font-mono">{spct(x.backtest?.cagr)} · SR {num(x.backtest?.sharpe)}</div></div>
      </div>
      {x.record && x.live_days > 0 && (
        <div className="text-[10px] text-text-tertiary" title="Each final session is recorded once and never recomputed; the latest stays provisional until the next close">
          Record: {x.record.frozen_days} session{x.record.frozen_days === 1 ? '' : 's'} locked{x.record.provisional ? ` · ${x.record.provisional} provisional` : ''}
          {x.record.revised_days > 0 && <span className="text-amber"> · {x.record.revised_days} would read differently on today’s data (the record keeps what was recorded)</span>}
        </div>)}
      {band.p5 != null && (
        <div className="text-[10px] text-text-tertiary">
          Expected range for {x.live_days} sessions: {spct(band.p5)} to {spct(band.p95)}.
          {x.status === 'below range' && <span className="text-red"> Worse than 95% of backtest paths — review it.</span>}
        </div>
      )}
      {x.positions.length > 0 && (
        <div className="flex flex-wrap items-center gap-1 text-[10px] font-mono">
          {shown.map((p: any) => (
            <span key={p.symbol} className={cn('px-1.5 py-0.5 border border-border', p.weight < 0 && 'text-red')}>{p.symbol} {spct(p.weight, 1)}</span>))}
          {hiddenCount > 0 && (
            <button onClick={() => setMore(!more)} className="px-1.5 py-0.5 text-text-tertiary underline">
              {more ? 'fewer' : `+${hiddenCount} more`}</button>)}
          {more && x.positions_other && <span className="text-text-tertiary">and {x.positions_other.count} smaller ({spct(x.positions_other.weight, 1)})</span>}
        </div>
      )}
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0"><DeepAnalysis request={['/api/v1/quant/deep', { deployment_id: x.id }]} title="Deep analysis" /></div>
        {canManage && <button onClick={() => onStop(x)} className="shrink-0 inline-flex items-center gap-1 px-2 py-2 text-[10px] border border-border text-text-secondary hover:border-red hover:text-red"><Square className="w-2.5 h-2.5" />Stop</button>}
      </div>
    </div>
  );
});
