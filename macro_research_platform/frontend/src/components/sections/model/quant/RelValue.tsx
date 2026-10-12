/**
 * Relative value & market making — the two businesses quant trading firms are best known for.
 * Pairs: Engle–Granger cointegration scan of a universe, then a no-look-ahead z-score backtest
 * of any pair (/api/v1/quant/pairs/*). Market making: Avellaneda–Stoikov quoting simulated on
 * free intraday bars against symmetric quoting (/api/v1/quant/mm).
 */
import { useState } from 'react';
import { Loader2, Play, Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { KpiStrip } from '@/components/ui/KpiStrip';
import { CATEGORICAL } from '@/lib/chartPalette';
import { api, ErrorNote, Field, inputCls, num, pct, Pills, spct, tone, usd } from './shared';
type Meta = { universes: { id: string; label: string }[] };

type Sub = 'pairs' | 'mm';

export function RelValue({ meta }: { meta: Meta }) {
  const [sub, setSub] = useState<Sub>('pairs');
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <Pills label="Relative value" value={sub} onChange={setSub} options={[['pairs', 'Pairs trading'], ['mm', 'Market making']] as const} />
        <span className="text-2xs text-text-tertiary">
          {sub === 'pairs'
            ? 'Cointegrated pairs — the classic stat-arb trade of quant market-neutral desks (Gatev, Goetzmann & Rouwenhorst 2006).'
            : 'Avellaneda–Stoikov (2008) inventory-aware quoting — the core model of electronic market makers.'}
        </span>
      </div>
      {sub === 'pairs' ? <Pairs meta={meta} /> : <MarketMaking />}
    </div>
  );
}

// ── Pairs ────────────────────────────────────────────────────────────────────
function Pairs({ meta }: { meta: Meta }) {
  const [preset, setPreset] = useState('us_megacaps');
  const [custom, setCustom] = useState('');
  const [years, setYears] = useState(2);
  const [scan, setScan] = useState<any>(null);
  const [p, setP] = useState({ a: 'EWA', b: 'EWC', lookback: 252, entry: 2, exit: 0.5, stop: 4, max_hold: 60, bps: 3 });
  const [bt, setBt] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const runScan = async () => {
    setBusy('scan'); setErr(null);
    const q = preset === 'custom' ? `symbols=${encodeURIComponent(custom)}` : `preset=${preset}`;
    try { setScan(await api(`/api/v1/quant/pairs/scan?${q}&years=${years}`)); } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  };
  const runBt = async (over: Partial<typeof p> = {}) => {
    const q = { ...p, ...over };
    setP(q); setBusy('bt'); setErr(null);
    const qs = new URLSearchParams(Object.entries(q).map(([k, v]) => [k, String(v)])).toString();
    try { setBt(await api(`/api/v1/quant/pairs/backtest?${qs}`)); } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  };
  const set = (k: keyof typeof p) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setP({ ...p, [k]: k === 'a' || k === 'b' ? e.target.value.toUpperCase() : Number(e.target.value) });

  return (
    <div className="space-y-3">
      <ErrorNote msg={err} />
      <div className="p-3 bg-surface-1 border border-border">
        <div className="text-xs font-semibold text-text-primary mb-2">1 · Find candidate pairs</div>
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Universe" className="w-56">
            <select className={inputCls} value={preset} onChange={(e) => setPreset(e.target.value)}>
              {meta.universes.map((u) => <option key={u.id} value={u.id}>{u.label}</option>)}
              <option value="custom">Custom tickers…</option>
            </select>
          </Field>
          {preset === 'custom' && (
            <Field label="Tickers (comma-separated)" className="w-72">
              <input className={inputCls} value={custom} onChange={(e) => setCustom(e.target.value.toUpperCase())} placeholder="KO, PEP, XOM, CVX, GLD, SLV" />
            </Field>
          )}
          <Field label="Formation window (years)" className="w-40">
            <input type="number" min={0.5} max={10} step={0.5} className={inputCls} value={years} onChange={(e) => setYears(Number(e.target.value))} />
          </Field>
          <button onClick={runScan} disabled={!!busy} className="inline-flex items-center gap-1 px-3 py-1 text-2xs bg-bloomberg text-bg disabled:opacity-50">
            {busy === 'scan' ? <Loader2 className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}Scan
          </button>
        </div>
        {scan && (
          <div className="mt-3 space-y-2">
            <div className={cn('text-2xs px-2 py-1 border', scan.passed_5pct > 2 * scan.expected_by_chance ? 'border-border text-text-secondary' : 'border-amber/50 text-amber')}>
              {scan.note} Window {scan.window.start} → {scan.window.end}. Bonferroni cut for {scan.pairs_tested} tests: p &lt; {scan.bonferroni_p.toPrecision(2)}.
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-2xs font-mono">
                <thead className="text-text-tertiary">
                  <tr className="border-b border-border">
                    {['Pair', 'Return corr', 'Hedge ratio', 'ADF', 'p-value', 'Half-life (d)', 'z now', ''].map((h) => <th key={h} className="text-left font-normal px-1.5 py-1">{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {scan.pairs.map((r: any) => (
                    <tr key={r.a + r.b} className="border-b border-border/50 hover:bg-surface-2">
                      <td className="px-1.5 py-1 text-text-primary">{r.a} / {r.b}</td>
                      <td className="px-1.5">{num(r.corr)}</td>
                      <td className="px-1.5">{num(r.hedge_ratio, 3)}</td>
                      <td className="px-1.5">{num(r.adf)}</td>
                      <td className={cn('px-1.5', r.significant_after_bonferroni ? 'text-green' : r.p_value < 0.05 ? 'text-text-primary' : 'text-text-tertiary')}>
                        {r.p_value.toFixed(4)}{r.significant_after_bonferroni && ' ✓'}
                      </td>
                      <td className="px-1.5">{r.half_life_days ?? '—'}</td>
                      <td className={cn('px-1.5', Math.abs(r.z_now ?? 0) >= 2 ? 'text-amber' : '')}>{num(r.z_now)}</td>
                      <td className="px-1.5">
                        <button className="underline text-bloomberg" onClick={() => runBt({ a: r.a, b: r.b })}>Backtest</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="text-[10px] text-text-tertiary">✓ = significant after Bonferroni correction for the number of pairs tested. Half-life: days for the spread to close half its gap.</div>
          </div>
        )}
      </div>

      <div className="p-3 bg-surface-1 border border-border">
        <div className="text-xs font-semibold text-text-primary mb-2">2 · Backtest a pair (rolling estimates, no look-ahead)</div>
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2 items-end">
          <Field label="Long leg A"><input className={inputCls} value={p.a} onChange={set('a')} /></Field>
          <Field label="Hedge leg B"><input className={inputCls} value={p.b} onChange={set('b')} /></Field>
          <Field label="Lookback (days)" hint="Window for the hedge ratio and spread mean/volatility"><input type="number" className={inputCls} value={p.lookback} onChange={set('lookback')} /></Field>
          <Field label="Entry |z|"><input type="number" step={0.25} className={inputCls} value={p.entry} onChange={set('entry')} /></Field>
          <Field label="Exit |z|"><input type="number" step={0.25} className={inputCls} value={p.exit} onChange={set('exit')} /></Field>
          <Field label="Stop |z|" hint="Close if the spread keeps diverging — the pair may have broken"><input type="number" step={0.5} className={inputCls} value={p.stop} onChange={set('stop')} /></Field>
          <Field label="Max hold (days)"><input type="number" className={inputCls} value={p.max_hold} onChange={set('max_hold')} /></Field>
          <Field label="Cost (bp/side)"><input type="number" step={0.5} className={inputCls} value={p.bps} onChange={set('bps')} /></Field>
        </div>
        <button onClick={() => runBt()} disabled={!!busy} className="mt-2 inline-flex items-center gap-1 px-3 py-1 text-2xs bg-bloomberg text-bg disabled:opacity-50">
          {busy === 'bt' ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}Run backtest
        </button>
        {bt && <PairResult r={bt} />}
      </div>
    </div>
  );
}

function PairResult({ r }: { r: any }) {
  const m = r.metrics;
  return (
    <div className="mt-3 space-y-2">
      <KpiStrip compact cols={8} items={[
        { label: 'CAGR', value: spct(m.cagr), tone: tone(m.cagr) },
        { label: 'Sharpe (net)', value: num(m.sharpe), sub: `gross ${num(m.sharpe_gross)}`, tone: tone(m.sharpe) },
        { label: 'Volatility', value: pct(m.vol) },
        { label: 'Max drawdown', value: pct(m.max_drawdown), tone: 'down' },
        { label: 'Trades', value: String(m.trades), sub: `${m.stop_losses} stop-outs` },
        { label: 'Win rate', value: pct(m.win_rate, 0) },
        { label: 'Avg hold', value: m.avg_days == null ? '—' : `${m.avg_days}d` },
        { label: 'Now', value: r.position_now, sub: `z ${num(r.z_now)} · β ${num(r.hedge_ratio_now, 3)}`, accent: r.position_now !== 'flat' },
      ]} />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
        <div>
          <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Growth of $1 — {r.a} / {r.b}, {r.period.start} → {r.period.end}</div>
          <LineChart rows={r.curve} x="date" height={200} baseline={1} fmt={(v) => v.toFixed(3)}
            lines={[{ key: 'equity', label: 'Pair strategy (net)', color: CATEGORICAL[0] }]} />
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Spread z-score (rolling)</div>
          <LineChart rows={r.curve} x="date" height={200} baseline={0} fmt={(v) => v.toFixed(2)}
            refs={[{ value: r.params.entry, label: `+${r.params.entry}` }, { value: -r.params.entry, label: `−${r.params.entry}` }]}
            lines={[{ key: 'z', label: 'z-score', color: CATEGORICAL[1] }]} />
        </div>
      </div>
      {r.trades.length > 0 && (
        <details className="text-2xs">
          <summary className="cursor-pointer text-text-secondary">Last {r.trades.length} trades</summary>
          <table className="w-full font-mono mt-1">
            <thead className="text-text-tertiary"><tr>{['Side', 'Entry', 'z', 'Exit', 'z', 'Days', 'Why', 'Return'].map((h, i) => <th key={i} className="text-left font-normal px-1.5">{h}</th>)}</tr></thead>
            <tbody>
              {r.trades.map((t: any, i: number) => (
                <tr key={i} className="border-b border-border/40">
                  <td className="px-1.5">{t.side}</td><td className="px-1.5">{t.entry_date}</td><td className="px-1.5">{num(t.entry_z)}</td>
                  <td className="px-1.5">{t.exit_date}</td><td className="px-1.5">{num(t.exit_z)}</td><td className="px-1.5">{t.days}</td>
                  <td className={cn('px-1.5', t.reason === 'stop-loss' && 'text-red')}>{t.reason}</td>
                  <td className={cn('px-1.5', (t.return ?? 0) >= 0 ? 'text-green' : 'text-red')}>{spct(t.return, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
      <ul className="text-[10px] text-text-tertiary list-disc pl-4">{r.notes.map((n: string) => <li key={n}>{n}</li>)}</ul>
    </div>
  );
}

// ── Market making ────────────────────────────────────────────────────────────
function MarketMaking() {
  const [p, setP] = useState({ symbol: 'SPY', interval: '1m', half_spread_bps: 1, aversion: 1, max_inventory: 10, lot: 100, rebate_per_share: 0 });
  const [r, setR] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const run = async () => {
    setBusy(true); setErr(null);
    const qs = new URLSearchParams(Object.entries(p).map(([k, v]) => [k, String(v)])).toString();
    try { setR(await api(`/api/v1/quant/mm?${qs}`)); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const set = (k: keyof typeof p) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setP({ ...p, [k]: k === 'symbol' ? e.target.value.toUpperCase() : k === 'interval' ? e.target.value : Number(e.target.value) });

  return (
    <div className="space-y-3">
      <ErrorNote msg={err} />
      <div className="p-3 bg-surface-1 border border-border">
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2 items-end">
          <Field label="Symbol"><input className={inputCls} value={p.symbol} onChange={set('symbol')} /></Field>
          <Field label="Bars" hint="Free history: 1m ≈ 7 days, 2m ≈ 30 days, 5m ≈ 60 days">
            <select className={inputCls} value={p.interval} onChange={set('interval')}>
              <option value="1m">1-minute (7d)</option><option value="2m">2-minute (30d)</option><option value="5m">5-minute (60d)</option>
            </select>
          </Field>
          <Field label="Base half-spread (bp)" hint="Distance of each quote from the reservation price before the volatility term"><input type="number" step={0.25} className={inputCls} value={p.half_spread_bps} onChange={set('half_spread_bps')} /></Field>
          <Field label="Inventory aversion ×" hint="0 = quote symmetrically around the mid; 1 = lean quotes by 2× the half-spread at the inventory limit"><input type="number" step={0.25} min={0} className={inputCls} value={p.aversion} onChange={set('aversion')} /></Field>
          <Field label="Inventory limit (lots)"><input type="number" className={inputCls} value={p.max_inventory} onChange={set('max_inventory')} /></Field>
          <Field label="Lot (shares)"><input type="number" className={inputCls} value={p.lot} onChange={set('lot')} /></Field>
          <Field label="Maker rebate ($/sh)" hint="Exchange rebate for resting liquidity, e.g. 0.002; negative = fee"><input type="number" step={0.0005} className={inputCls} value={p.rebate_per_share} onChange={set('rebate_per_share')} /></Field>
        </div>
        <button onClick={run} disabled={busy} className="mt-2 inline-flex items-center gap-1 px-3 py-1 text-2xs bg-bloomberg text-bg disabled:opacity-50">
          {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}Simulate
        </button>
        <div className="mt-2 text-[10px] text-text-tertiary leading-relaxed">
          Reservation price r = mid − q·γ·σ²·τ leans both quotes against inventory q — hardest when more of the day (τ) is left to carry the risk — and the spread widens with volatility σ.
          The comparison run quotes the same spread symmetrically around the mid.
        </div>
      </div>
      {r && <MMResult r={r} />}
    </div>
  );
}

function MMResult({ r }: { r: any }) {
  const a = r.runs.avellaneda_stoikov, s = r.runs.symmetric;
  const rows: [string, (x: any) => string][] = [
    ['Total P&L', (x) => usd(x.total_pnl)],
    ['  Spread captured', (x) => usd(x.spread_capture)],
    ['  Inventory P&L', (x) => usd(x.inventory_pnl)],
    ['  Rebates', (x) => usd(x.rebates)],
    ['  Close-out cost', (x) => usd(-x.flatten_cost)],
    ['Fills (round trips)', (x) => `${x.fills} (${x.round_trips})`],
    ['Avg edge per fill', (x) => `${num(x.avg_edge_bps)} bp`],
    [`Markout after 5 bars`, (x) => `${num(x.markout_bps)} bp`],
    ['Avg |inventory|', (x) => `${num(x.avg_abs_inventory)} lots`],
    ['Max |inventory|', (x) => `${x.max_abs_inventory} lots`],
    ['Winning days', (x) => `${x.win_days} / ${x.days}`],
    ['Worst day', (x) => usd(x.worst_day)],
  ];
  return (
    <div className="space-y-2">
      <div className="text-2xs text-text-secondary">
        {r.symbol} · {r.bars.toLocaleString()} {r.interval} bars · {r.period.start} → {r.period.end} ({r.period.days} sessions) ·
        realised vol {pct(r.market.realized_vol_ann)} · quote lean {num(r.market.skew_per_lot_open_bps, 2)} bp per lot at the open
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-2">
        <table className="text-2xs font-mono bg-surface-1 border border-border w-full">
          <thead className="text-text-tertiary"><tr className="border-b border-border"><th className="text-left font-normal px-2 py-1" /><th className="text-right font-normal px-2">Avellaneda–Stoikov</th><th className="text-right font-normal px-2">Symmetric</th></tr></thead>
          <tbody>
            {rows.map(([l, f]) => (
              <tr key={l} className="border-b border-border/40">
                <td className="px-2 py-0.5 text-text-secondary whitespace-pre">{l}</td>
                <td className="px-2 text-right">{f(a)}</td>
                <td className="px-2 text-right">{f(s)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="lg:col-span-2 space-y-2">
          <div>
            <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Cumulative P&amp;L ($)</div>
            <LineChart rows={r.path} x="t" height={170} baseline={0} fmt={(v) => usd(v)}
              lines={[{ key: 'eq_as', label: 'Avellaneda–Stoikov', color: CATEGORICAL[0] }, { key: 'eq_sym', label: 'Symmetric', color: CATEGORICAL[1] }]} />
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Inventory (lots)</div>
            <LineChart rows={r.path} x="t" height={130} baseline={0} fmt={(v) => v.toFixed(0)}
              lines={[{ key: 'inv_as', label: 'Avellaneda–Stoikov', color: CATEGORICAL[0] }, { key: 'inv_sym', label: 'Symmetric', color: CATEGORICAL[1] }]} />
          </div>
        </div>
      </div>
      <ul className="text-[10px] text-text-tertiary list-disc pl-4">{r.caveats.map((c: string) => <li key={c}>{c}</li>)}</ul>
    </div>
  );
}
