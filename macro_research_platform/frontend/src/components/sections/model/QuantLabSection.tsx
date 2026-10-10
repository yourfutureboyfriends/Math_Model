/**
 * Quant Lab — build, backtest, stress-test and deploy your own systematic (quant) algos.
 * Write a signal formula or start from a research-backed template; every backtest reports
 * whether the result is likely real (Deflated Sharpe counting every variant you tried,
 * out-of-sample decay, bootstrap ranges, cost/delay stress). Sweeps report the probability
 * of backtest overfitting; Combine blends algos by equal risk; Deploy sends an algo to the
 * Quant Trader's paper book (Portfolios → Quant Trader).
 * Reads /api/v1/quant/* (api/routers/quant.py).
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { BookOpen, Copy, FlaskConical, Layers, Library, Loader2, Play, Rocket, Save, SlidersHorizontal, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { Donut } from '@/components/ui/Donut';
import { CorrelationHeatmap } from '@/components/ui/CorrelationHeatmap';
import { HeatGrid } from '@/components/ui/HeatGrid';
import { KpiStrip } from '@/components/ui/KpiStrip';
import { CATEGORICAL } from '@/lib/chartPalette';
import { useAuth } from '@/context/AuthContext';
import { StrategyBuilder, type Meta } from './quant/StrategyBuilder';
import { QuantReport } from './quant/QuantReport';
import { api, BLANK_SPEC, ErrorNote, Field, inputCls, num, pct, spct, tone, withDefaults, type Spec } from './quant/shared';

const TABS = [
  ['build', 'Build & test', FlaskConical], ['templates', 'Templates', Library], ['mine', 'My strategies', Save],
  ['sweep', 'Parameter sweep', SlidersHorizontal], ['combine', 'Combine', Layers], ['research', 'Research', BookOpen],
] as const;
type Tab = (typeof TABS)[number][0];

function loadDraft(): { spec: Spec; id: number | null } {
  try {
    const d = JSON.parse(localStorage.getItem('quantlab.draft') || 'null');
    if (d?.spec) return { spec: withDefaults(d.spec), id: d.id ?? null };
  } catch { /* storage unavailable */ }
  return { spec: BLANK_SPEC, id: null };
}

export function QuantLabSection() {
  const { user } = useAuth();
  const canSave = ['admin', 'pm', 'quant', 'analyst'].includes(user?.role ?? '');
  const canDeploy = ['admin', 'pm', 'quant'].includes(user?.role ?? '');
  const [tab, setTab] = useState<Tab>('build');
  const [meta, setMeta] = useState<Meta | null>(null);
  const [draft] = useState(loadDraft);
  const [spec, setSpec] = useState<Spec>(draft.spec);
  const [strategyId, setStrategyId] = useState<number | null>(draft.id);
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [mine, setMine] = useState<any[]>([]);
  const [capital, setCapital] = useState(1_000_000);

  useEffect(() => { api('/api/v1/quant/meta').then(setMeta).catch((e) => setErr(e.message)); }, []);
  useEffect(() => { try { localStorage.setItem('quantlab.draft', JSON.stringify({ spec, id: strategyId })); } catch { /* storage unavailable */ } }, [spec, strategyId]);
  const loadMine = useCallback(() => { api('/api/v1/quant/strategies').then((j) => setMine(j.strategies)).catch(() => {}); }, []);
  useEffect(loadMine, [loadMine]);

  const run = useCallback(async (s: Spec = spec, id: number | null = strategyId) => {
    setBusy('run'); setErr(null); setNote(null);
    try {
      setResult(await api('/api/v1/quant/backtest', { json: { spec: s, strategy_id: id } }));
    } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  }, [spec, strategyId]);

  const open = (s: Partial<Spec>, id: number | null = null, autorun = false) => {
    const full = withDefaults(s);
    setSpec(full); setStrategyId(id); setResult(null); setTab('build');
    if (autorun) void run(full, id);
  };

  const save = async (asNew: boolean) => {
    setBusy('save'); setErr(null);
    try {
      const j = asNew || strategyId == null
        ? await api('/api/v1/quant/strategies', { json: { spec } })
        : await api(`/api/v1/quant/strategies/${strategyId}`, { method: 'PUT', json: { spec } });
      setStrategyId(j.id); setNote(`Saved “${j.name}”.`); loadMine();
    } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  };

  const deploy = async () => {
    if (!window.confirm(`Deploy “${spec.name}” to the Quant Trader paper book with $${capital.toLocaleString()}? It trades from the next session; no real orders.`)) return;
    setBusy('deploy'); setErr(null);
    try {
      const d = await api('/api/v1/quant/trader/deploy', { json: { spec, strategy_id: strategyId, capital } });
      setNote(`Deployed “${d.name}” — live from the session after ${d.deployed_at}. See Portfolios → Quant Trader.`);
    } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  };

  return (
    <div className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><FlaskConical className="w-3 h-3" /></span>
          <h2 className="section-title">Quant Lab</h2>
          <span className="text-2xs text-text-tertiary">build · backtest · stress-test · deploy your own quant algos</span>
        </div>
      </div>
      <div className="flex flex-wrap border border-border mb-3 w-fit" role="tablist" aria-label="Quant Lab">
        {TABS.map(([k, l, Icon]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
            className={cn('inline-flex items-center gap-1 px-3 py-1 text-2xs', tab === k ? 'bg-bloomberg text-bg' : 'text-text-secondary hover:text-text-primary')}>
            <Icon className="w-3 h-3" />{l}
          </button>
        ))}
      </div>
      <ErrorNote msg={err} />
      {note && <div className="mb-2 px-3 py-2 border border-green/40 bg-green/5 text-xs text-green">{note}</div>}
      {!meta ? (
        <div className="flex items-center gap-2 text-2xs text-text-tertiary p-3"><Loader2 className="w-3 h-3 animate-spin" />Loading the lab…</div>
      ) : (
        <>
          {tab === 'build' && (
            <div className="grid grid-cols-1 xl:grid-cols-[minmax(320px,420px)_1fr] gap-3">
              <div className="space-y-3">
                <StrategyBuilder spec={spec} setSpec={setSpec} meta={meta} />
                <div className="flex flex-wrap gap-2">
                  <button onClick={() => run()} disabled={!!busy}
                    className="inline-flex items-center gap-1 px-3 py-1.5 text-xs bg-bloomberg text-bg disabled:opacity-50">
                    {busy === 'run' ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}Run backtest
                  </button>
                  {canSave && <button onClick={() => save(false)} disabled={!!busy} className="inline-flex items-center gap-1 px-3 py-1.5 text-xs border border-border hover:border-bloomberg disabled:opacity-50">
                    <Save className="w-3 h-3" />{strategyId ? 'Save' : 'Save as mine'}</button>}
                  {canSave && strategyId && <button onClick={() => save(true)} disabled={!!busy} className="inline-flex items-center gap-1 px-3 py-1.5 text-xs border border-border hover:border-bloomberg disabled:opacity-50">
                    <Copy className="w-3 h-3" />Save copy</button>}
                  <button onClick={() => { setSpec(BLANK_SPEC); setStrategyId(null); setResult(null); }} className="px-3 py-1.5 text-xs text-text-secondary hover:text-text-primary">New</button>
                </div>
                {canDeploy && (
                  <div className="flex flex-wrap items-end gap-2 p-2 border border-border">
                    <Field label="Paper capital ($)"><input type="number" min={1000} step={10000} className={cn(inputCls, 'w-32')} value={capital} onChange={(e) => setCapital(Number(e.target.value))} /></Field>
                    <button onClick={deploy} disabled={!!busy} className="inline-flex items-center gap-1 px-3 py-1.5 text-xs border border-bloomberg text-bloomberg hover:bg-bloomberg hover:text-bg disabled:opacity-50">
                      {busy === 'deploy' ? <Loader2 className="w-3 h-3 animate-spin" /> : <Rocket className="w-3 h-3" />}Deploy to Quant Trader
                    </button>
                    <span className="text-[10px] text-text-tertiary w-full">Paper-trades this exact spec from the next session — its live record is compared with the backtest.</span>
                  </div>
                )}
                {strategyId && <div className="text-[10px] text-text-tertiary">Editing saved strategy #{strategyId}. Each distinct variant you run is counted in its Deflated Sharpe.</div>}
              </div>
              <div className="min-w-0">
                {busy === 'run' && !result && <div className="flex items-center gap-2 text-2xs text-text-tertiary p-6"><Loader2 className="w-3 h-3 animate-spin" />Downloading prices and running… the first run of a new universe can take ~30 s.</div>}
                {result ? <div className={cn(busy === 'run' && 'opacity-50')}><QuantReport r={result} /></div> : busy !== 'run' && (
                  <div className="p-4 border border-dashed border-border text-2xs text-text-secondary space-y-1.5">
                    <div className="text-text-primary text-xs">How it works</div>
                    <p>1. Pick a universe and write a <b>signal</b>: a formula scored for every asset each day (higher = more attractive), e.g. <code className="font-mono">mom(252, 21)</code> for 12-1 month momentum.</p>
                    <p>2. Choose how to <b>select</b> (top N, threshold, long/short by sign…) and <b>weight</b> holdings, how often to rebalance, and the cost per trade.</p>
                    <p>3. <b>Run backtest</b>. Trades happen at the next open after each signal, so there is no look-ahead. The report tells you whether the result is likely real or luck.</p>
                    <p>Not sure where to start? Open a <button className="underline text-bloomberg" onClick={() => setTab('templates')}>template</button>.</p>
                  </div>
                )}
              </div>
            </div>
          )}
          {tab === 'templates' && <Templates meta={meta} onOpen={(s, auto) => open(s, null, auto)} />}
          {tab === 'mine' && <Mine rows={mine} me={user?.username} isAdmin={user?.role === 'admin'} onOpen={(s, id) => open(s.spec, id)} onChanged={loadMine} />}
          {tab === 'sweep' && <Sweep spec={spec} strategyId={strategyId} />}
          {tab === 'combine' && <Combine meta={meta} mine={mine} />}
          {tab === 'research' && <Research meta={meta} />}
        </>
      )}
    </div>
  );
}

// ── Templates ────────────────────────────────────────────────────────────────
function Templates({ meta, onOpen }: { meta: Meta; onOpen: (s: Partial<Spec>, autorun: boolean) => void }) {
  const fams = Array.from(new Set(meta.templates.map((t) => t.family)));
  return (
    <div className="space-y-3">
      <p className="text-2xs text-text-secondary">Research-backed starting points. Open one in the builder to change it and make it your own — your edits are counted as new variants, so the significance tests stay honest.</p>
      {fams.map((f) => (
        <div key={f}>
          <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">{f}</div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
            {meta.templates.filter((t) => t.family === f).map((t) => (
              <div key={t.id} className="p-3 bg-surface-1 border border-border flex flex-col gap-1.5">
                <div className="text-xs font-semibold text-text-primary">{t.name}</div>
                <div className="text-2xs text-text-secondary">{t.description}</div>
                <code className="block text-[11px] font-mono text-bloomberg/90 break-all">{t.spec.signal}{t.spec.filter ? `  ·  filter: ${t.spec.filter}` : ''}</code>
                <div className="text-[10px] text-text-tertiary leading-relaxed"><b className="text-text-secondary">Evidence:</b> {t.evidence}</div>
                <div className="text-[10px] text-text-tertiary italic">{t.citation}</div>
                <div className="flex gap-2 mt-auto pt-1">
                  <button onClick={() => onOpen({ ...t.spec, name: t.name, description: t.description }, true)} className="inline-flex items-center gap-1 px-2.5 py-1 text-2xs bg-bloomberg text-bg"><Play className="w-3 h-3" />Backtest</button>
                  <button onClick={() => onOpen({ ...t.spec, name: `${t.name} (my version)`, description: t.description }, false)} className="px-2.5 py-1 text-2xs border border-border hover:border-bloomberg">Customise</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── My strategies ────────────────────────────────────────────────────────────
function Mine({ rows, me, isAdmin, onOpen, onChanged }: { rows: any[]; me?: string; isAdmin: boolean; onOpen: (s: any, id: number) => void; onChanged: () => void }) {
  const del = async (s: any) => {
    if (!window.confirm(`Delete “${s.name}”? This cannot be undone.`)) return;
    await api(`/api/v1/quant/strategies/${s.id}`, { method: 'DELETE' }).catch(() => {});
    onChanged();
  };
  if (!rows.length) return <div className="p-4 text-2xs text-text-tertiary border border-dashed border-border">No saved strategies yet — build one and press “Save as mine”.</div>;
  return (
    <table className="w-full text-2xs">
      <thead><tr className="text-text-tertiary text-left"><th className="font-normal py-1">Name</th><th className="font-normal">Signal</th><th className="font-normal">Universe</th><th className="font-normal">Owner</th><th className="font-normal">Updated</th><th /></tr></thead>
      <tbody>{rows.map((s) => (
        <tr key={s.id} className="border-t border-border-subtle">
          <td className="py-1.5 text-text-primary">{s.name}</td>
          <td className="font-mono text-text-secondary max-w-[22rem] truncate" title={s.spec.signal}>{s.spec.signal}</td>
          <td className="text-text-secondary">{s.spec.universe.preset ?? `${(s.spec.universe.symbols ?? []).length} tickers`}</td>
          <td className="text-text-secondary">{s.owner}</td>
          <td className="text-text-tertiary">{String(s.updated_at).slice(0, 10)}</td>
          <td className="text-right whitespace-nowrap">
            <button onClick={() => onOpen(s, s.id)} className="px-2 py-0.5 border border-border hover:border-bloomberg">Open</button>
            {(s.owner === me || isAdmin) && <button onClick={() => del(s)} aria-label={`Delete ${s.name}`} className="ml-1 px-1.5 py-0.5 text-text-tertiary hover:text-red"><Trash2 className="w-3 h-3" /></button>}
          </td>
        </tr>))}</tbody>
    </table>
  );
}

// ── Parameter sweep ──────────────────────────────────────────────────────────
function Sweep({ spec, strategyId }: { spec: Spec; strategyId: number | null }) {
  const [p1, setP1] = useState({ name: 'n', values: '126, 189, 252' });
  const [p2, setP2] = useState({ name: '', values: '' });
  const [signal, setSignal] = useState(spec.signal.match(/\{\w+\}/) ? spec.signal : spec.signal.replace(/mom\((\d+)/, 'mom({n}'));
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const parse = (s: string) => s.split(/[\s,]+/).map(Number).filter((x) => Number.isFinite(x));
  const go = async () => {
    setBusy(true); setErr(null);
    const params: Record<string, number[]> = { [p1.name]: parse(p1.values) };
    if (p2.name.trim()) params[p2.name.trim()] = parse(p2.values);
    const selection = 'k' in params ? { ...spec.selection, n: '{k}' } : spec.selection;
    try { setRes(await api('/api/v1/quant/sweep', { json: { spec: { ...spec, signal, selection }, params, strategy_id: strategyId } })); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const grid = useMemo(() => {
    if (!res || res.keys.length !== 2) return null;
    const [a, b] = res.keys;
    const av = Array.from(new Set(res.rows.map((r: any) => r.params[a]))) as number[];
    const bv = Array.from(new Set(res.rows.map((r: any) => r.params[b]))) as number[];
    return { cols: bv.map(String), rows: av.map((x) => ({ label: `${a} = ${x}`, values: bv.map((y) => res.rows.find((r: any) => r.params[a] === x && r.params[b] === y)?.sharpe ?? null) })), b };
  }, [res]);
  const pbo = res?.pbo?.pbo;
  return (
    <div className="space-y-3">
      <p className="text-2xs text-text-secondary">Test how sensitive the current builder strategy is to its settings. Put <code className="font-mono">{'{name}'}</code> placeholders in the formula (or a numeric setting) and list values to try. A robust idea works across many settings; if only one setting works, it is probably overfit.</p>
      <Field label="Signal formula with placeholders"><input className={inputCls} value={signal} onChange={(e) => setSignal(e.target.value)} /></Field>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <Field label="Parameter 1"><input className={inputCls} value={p1.name} onChange={(e) => setP1({ ...p1, name: e.target.value })} /></Field>
        <Field label="Values"><input className={inputCls} value={p1.values} onChange={(e) => setP1({ ...p1, values: e.target.value })} /></Field>
        <Field label="Parameter 2 (optional)"><input className={inputCls} value={p2.name} placeholder="e.g. k" onChange={(e) => setP2({ ...p2, name: e.target.value })} /></Field>
        <Field label="Values"><input className={inputCls} value={p2.values} placeholder="e.g. 2, 3, 4" onChange={(e) => setP2({ ...p2, values: e.target.value })} /></Field>
      </div>
      <div className="text-[10px] text-text-tertiary">Up to 36 combinations. Name a parameter <code className="font-mono">k</code> to sweep the number of holdings (Top N / long-short).</div>
      <button onClick={go} disabled={busy} className="inline-flex items-center gap-1 px-3 py-1.5 text-xs bg-bloomberg text-bg disabled:opacity-50">
        {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <SlidersHorizontal className="w-3 h-3" />}Run sweep</button>
      <ErrorNote msg={err} />
      {res && (
        <div className="space-y-3">
          <div className={cn('p-3 border bg-surface-1 text-2xs', pbo == null ? 'border-border' : pbo > 0.5 ? 'border-amber/50' : 'border-green/50')}>
            <div className="text-xs font-semibold text-text-primary mb-1">Probability of backtest overfitting: {pct(pbo, 0)}</div>
            <div className="text-text-secondary">{res.interpretation}</div>
            <div className="text-text-tertiary mt-1">Best variant’s Deflated Sharpe after {res.deflated_sharpe_best.trials} trials: {pct(res.deflated_sharpe_best.dsr, 0)} · Sharpe range {num(res.sharpe_spread.min)}–{num(res.sharpe_spread.max)} (median {num(res.sharpe_spread.median)}) · {res.window.start} → {res.window.end}</div>
          </div>
          {grid && <div className="p-3 bg-surface-1 border border-border"><HeatGrid title={`Sharpe by ${res.keys[0]} (rows) and ${grid.b} (columns)`} columns={grid.cols} rows={grid.rows} fmt={(v) => v.toFixed(2)} labelWidth="6rem" /></div>}
          <table className="w-full text-2xs font-mono">
            <thead><tr className="text-text-tertiary text-left"><th className="font-normal">Parameters</th><th className="font-normal text-right">Sharpe</th><th className="font-normal text-right">Return</th><th className="font-normal text-right">Max DD</th><th className="font-normal text-right">Turnover</th></tr></thead>
            <tbody>{[...res.rows].sort((a: any, b: any) => (b.sharpe ?? -9) - (a.sharpe ?? -9)).map((r: any) => (
              <tr key={JSON.stringify(r.params)} className="border-t border-border-subtle">
                <td>{Object.entries(r.params).map(([k, v]) => `${k}=${v}`).join(', ')}</td>
                <td className="text-right">{num(r.sharpe)}</td><td className="text-right">{spct(r.cagr)}</td>
                <td className="text-right">{pct(r.max_drawdown, 0)}</td><td className="text-right">{num(r.turnover, 1)}×</td>
              </tr>))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Combine ──────────────────────────────────────────────────────────────────
function Combine({ meta, mine }: { meta: Meta; mine: any[] }) {
  const options = useMemo(() => [
    ...meta.templates.map((t) => ({ key: `t:${t.id}`, label: t.name, member: { template: t.id } })),
    ...mine.map((s) => ({ key: `s:${s.id}`, label: `★ ${s.name}`, member: { strategy_id: s.id } })),
  ], [meta, mine]);
  const [picked, setPicked] = useState<string[]>(['t:house_multi_trend', 't:sector_rotation', 't:low_vol_stocks', 't:faber_gtaa5']);
  const [method, setMethod] = useState('erc');
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const go = async () => {
    setBusy(true); setErr(null);
    try { setRes(await api('/api/v1/quant/combine', { json: { members: options.filter((o) => picked.includes(o.key)).map((o) => o.member), method } })); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const lines = res ? [{ key: 'combined', label: 'Combined', color: CATEGORICAL[0] },
    ...res.names.map((n: string, i: number) => ({ key: n, label: n.length > 26 ? `${n.slice(0, 25).trim()}…` : n, color: CATEGORICAL[(i + 1) % CATEGORICAL.length] }))] : [];
  return (
    <div className="space-y-3">
      <p className="text-2xs text-text-secondary">Run several algos as one book. Strategies with low correlation smooth each other's losing streaks — this is how multi-strategy funds are built. Pick 2–8.</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-1 max-h-56 overflow-y-auto border border-border p-2">
        {options.map((o) => (
          <label key={o.key} className="flex items-center gap-1.5 text-2xs text-text-secondary">
            <input type="checkbox" checked={picked.includes(o.key)}
              onChange={(e) => setPicked((p) => e.target.checked ? [...p, o.key].slice(0, 8) : p.filter((x) => x !== o.key))} />
            <span className="truncate" title={o.label}>{o.label}</span>
          </label>
        ))}
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Weighting">
          <select className={inputCls} value={method} onChange={(e) => setMethod(e.target.value)}>
            <option value="erc">Equal risk contribution (walk-forward)</option>
            <option value="inverse_vol">Inverse volatility</option>
            <option value="equal">Equal capital</option>
          </select>
        </Field>
        <button onClick={go} disabled={busy || picked.length < 2} className="inline-flex items-center gap-1 px-3 py-1.5 text-xs bg-bloomberg text-bg disabled:opacity-50">
          {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Layers className="w-3 h-3" />}Combine {picked.length}</button>
      </div>
      <ErrorNote msg={err} />
      {res && (
        <div className="space-y-3">
          <KpiStrip items={[
            { label: 'Combined return', value: spct(res.metrics.cagr), tone: tone(res.metrics.cagr), accent: true },
            { label: 'Sharpe', value: num(res.metrics.sharpe), sub: `best single ${num(Math.max(...Object.values(res.members).map((m: any) => m.sharpe ?? -9)))}` },
            { label: 'Volatility', value: pct(res.metrics.vol) },
            { label: 'Max drawdown', value: pct(res.metrics.max_drawdown), tone: 'down' },
            { label: 't-stat', value: num(res.metrics.t_stat, 1) },
            { label: 'Sharpe 90% range', value: res.bootstrap?.sharpe_p05 != null ? `${num(res.bootstrap.sharpe_p05)}–${num(res.bootstrap.sharpe_p95)}` : '—' },
          ]} />
          <div className="p-3 bg-surface-1 border border-border">
            <LineChart rows={res.curve} x="date" lines={lines} height={260} log baseline={1} fmt={(v) => `${v.toFixed(2)}×`} />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
            <div className="p-3 bg-surface-1 border border-border">
              <Donut title="Latest weights" data={Object.entries(res.weights).map(([label, value]) => ({ label, value: Number(value) }))} fmt={(v) => pct(v, 0)} />
              <table className="w-full text-2xs font-mono mt-2">
                <thead><tr className="text-text-tertiary"><th className="text-left font-normal">Algo</th><th className="text-right font-normal">Sharpe</th><th className="text-right font-normal">Return</th><th className="text-right font-normal">Max DD</th></tr></thead>
                <tbody>{res.names.map((n: string) => (
                  <tr key={n} className="border-t border-border-subtle"><td className="truncate max-w-[14rem]" title={n}>{n}</td>
                    <td className="text-right">{num(res.members[n].sharpe)}</td><td className="text-right">{spct(res.members[n].cagr)}</td><td className="text-right">{pct(res.members[n].max_drawdown, 0)}</td></tr>))}</tbody>
              </table>
            </div>
            <div className="p-3 bg-surface-1 border border-border min-w-0">
              <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Correlation of daily returns</div>
              <CorrelationHeatmap labels={res.names.map((n: string) => n.slice(0, 10))}
                matrix={res.names.map((a: string) => res.names.map((b: string) => res.correlation[a][b]))} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Research ─────────────────────────────────────────────────────────────────
function Research({ meta }: { meta: Meta }) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
        {meta.research.map((n) => (
          <div key={n.title} className="p-3 bg-surface-1 border border-border">
            <div className="text-xs font-semibold text-text-primary mb-1">{n.title}</div>
            <div className="text-2xs text-text-secondary leading-relaxed">{n.text}</div>
          </div>
        ))}
      </div>
      <div className="p-3 bg-surface-1 border border-border">
        <div className="text-xs font-semibold text-text-primary mb-1">The tests in every report</div>
        <ul className="text-2xs text-text-secondary space-y-1 list-disc pl-4">
          <li><b>Deflated Sharpe Ratio</b> (Bailey &amp; López de Prado 2014): probability the Sharpe is real after accounting for every variant you tried — the lab counts them for you.</li>
          <li><b>t &gt; 3 hurdle</b> (Harvey, Liu &amp; Zhu 2016): the bar for a new strategy once data mining is accounted for.</li>
          <li><b>Probability of Backtest Overfitting</b> (Bailey, Borwein, López de Prado &amp; Zhu 2017): in a sweep, how often the in-sample winner lands in the bottom half out of sample.</li>
          <li><b>Out-of-sample decay</b>: the last 30% of history is held out; McLean &amp; Pontiff (2016) find published anomalies lose ~58% after publication.</li>
          <li><b>Block bootstrap</b> (Politis &amp; Romano 1994): resampling 1-month blocks gives a realistic range for Sharpe and return.</li>
          <li><b>Costs, delay, vol targeting</b>: doubled/tripled costs, trading a day late, and with/without the volatility target (Cederburg et al. 2020).</li>
        </ul>
      </div>
    </div>
  );
}
