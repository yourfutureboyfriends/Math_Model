/**
 * Parameter optimisation on real LEAN (QuantConnect's optimizer): every combination of the algorithm's get_parameter
 * values runs in-sample (up to the hold-out date); the best by the chosen objective then runs on the hold-out, which no
 * combination saw — the gap between the two is how much of the "best" was luck. Engine: api/quant/leanrun.optimize.
 */
import { useEffect, useMemo, useState } from 'react';
import { Loader2, SlidersHorizontal } from 'lucide-react';
import { cn } from '@/lib/utils';
import { api, ErrorNote, Field, inputCls, num, spct, tone } from './shared';

type Param = { name: string; default: string | null };

/** Suggested values around a numeric default: half, default, one and a half times. */
function suggest(def: string | null): string {
  const x = Number(def);
  if (def == null || !Number.isFinite(x)) return def ?? '';
  const isInt = Number.isInteger(x);
  const vals = [x * 0.5, x, x * 1.5].map((v) => (isInt ? Math.max(1, Math.round(v)) : +v.toFixed(4)));
  return [...new Set(vals)].join(', ');
}

function parseValues(s: string): (number | string)[] {
  return s.split(',').map((t) => t.trim()).filter(Boolean).map((t) => (Number.isFinite(Number(t)) ? Number(t) : t));
}

export function LeanOptimizer({ code, disabled }: { code: string; disabled?: boolean }) {
  const [params, setParams] = useState<Param[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [split, setSplit] = useState('');
  const [objective, setObjective] = useState('sharpe');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [res, setRes] = useState<any>(null);
  const [jobId, setJobId] = useState<string | null>(null);

  // the parameters the algorithm reads (re-read when the code changes, debounced)
  useEffect(() => {
    if (!/get_?parameter/i.test(code)) { setParams([]); return; }
    const t = setTimeout(() => {
      api('/api/v1/quant/lean/parameters', { json: { code } }).then((j) => {
        setParams(j.parameters ?? []);
        setValues((prev) => Object.fromEntries((j.parameters ?? []).map((p: Param) => [p.name, prev[p.name] ?? suggest(p.default)])));
      }).catch(() => setParams([]));
    }, 600);
    return () => clearTimeout(t);
  }, [code]);

  const combos = useMemo(() => params.reduce((n, p) => n * Math.max(1, parseValues(values[p.name] ?? '').length), 1), [params, values]);

  if (!params.length) return null;

  const run = async () => {
    setBusy(true); setErr(null); setRes(null);
    try {
      const grid = Object.fromEntries(params.map((p) => [p.name, parseValues(values[p.name] ?? '')]).filter(([, v]) => (v as any[]).length));
      const job = await api('/api/v1/quant/lean/optimize', { json: { code, grid, split: split || null, objective } });
      setJobId(job.id);
      let j = job;
      while (j.state === 'queued' || j.state === 'running') {
        setStatus(`${j.message} (${Math.round(j.elapsed_s ?? 0)} s)`);
        await new Promise((r) => setTimeout(r, 2000));
        j = await api(`/api/v1/quant/code/jobs/${job.id}`);
      }
      if (j.state !== 'done') throw new Error(j.state === 'cancelled' ? 'Cancelled.' : (j.error || 'The optimisation failed.'));
      setRes(j.result);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); setStatus(null); setJobId(null); }
  };
  const cancel = () => { if (jobId) api(`/api/v1/quant/code/jobs/${jobId}`, { method: 'DELETE' }).catch(() => {}); };

  const best = res?.best?.parameters;
  const same = (a: any, b: any) => a && b && Object.keys(a).every((k) => String(a[k]) === String(b[k]));
  const rows = [...(res?.rows ?? [])].sort((a: any, b: any) => (b.metrics?.[objective] ?? -1e9) - (a.metrics?.[objective] ?? -1e9));

  return (
    <div className="border border-border bg-surface-1 p-3 space-y-2">
      <div className="flex items-center gap-2 text-xs font-semibold text-text-primary">
        <SlidersHorizontal className="w-3.5 h-3.5 text-bloomberg" />Optimise parameters on real LEAN
        <span className="font-normal text-text-tertiary">· every combination in-sample, the best on a hold-out it never saw</span>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        {params.map((p) => (
          <Field key={p.name} label={`${p.name}${p.default != null ? ` (default ${p.default})` : ''}`} className="w-48" hint="comma-separated values">
            <input className={inputCls} value={values[p.name] ?? ''} onChange={(e) => setValues({ ...values, [p.name]: e.target.value })} />
          </Field>))}
        <Field label="Hold-out from" className="w-36" hint="in-sample before, tested after">
          <input type="date" className={inputCls} value={split} onChange={(e) => setSplit(e.target.value)} />
        </Field>
        <Field label="Objective" className="w-28">
          <select className={inputCls} value={objective} onChange={(e) => setObjective(e.target.value)}>
            {['sharpe', 'cagr', 'calmar', 'sortino'].map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        </Field>
        <button onClick={run} disabled={busy || disabled || combos < 1 || combos > 60}
          className="inline-flex items-center gap-1 px-3 py-1 text-2xs border border-bloomberg text-bloomberg disabled:opacity-40"
          title={combos > 60 ? 'At most 60 combinations' : undefined}>
          {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <SlidersHorizontal className="w-3 h-3" />}Optimise ({combos} run{combos === 1 ? '' : 's'}{split ? ' + hold-out' : ''})
        </button>
        {busy && jobId && <button onClick={cancel} className="px-2 py-1 text-2xs border border-border hover:border-red hover:text-red">Cancel</button>}
      </div>
      {!split && <div className="text-[10px] text-amber">Without a hold-out date the best combination is judged only on the data it was picked on.</div>}
      {status && <div className="flex items-center gap-2 text-2xs text-text-secondary"><Loader2 className="w-3 h-3 animate-spin" />{status}</div>}
      <ErrorNote msg={err} />
      {res && (
        <div className="space-y-2">
          {res.holdout && (
            <div className={cn('text-xs p-2 border', (res.decay ?? 0) >= 0.5 ? 'border-green/40' : 'border-amber/40')}>
              <b>Best in-sample:</b> {Object.entries(best ?? {}).map(([k, v]) => `${k}=${v}`).join(', ')} — {objective} {num(res.best.metrics?.[objective])} in-sample
              {' · '}<b>hold-out</b> ({split} →): {objective} {num(res.holdout.metrics?.[objective])}, CAGR {spct(res.holdout.metrics?.cagr)}, max drawdown {spct(res.holdout.metrics?.max_drawdown)}
              {res.decay != null && <> · kept <b>{Math.round(res.decay * 100)}%</b> of its in-sample {objective}</>}
            </div>)}
          <div className="text-[10px] text-text-tertiary">{res.note}</div>
          <div className="overflow-x-auto">
            <table className="w-full text-2xs font-mono">
              <thead><tr className="text-text-tertiary border-b border-border">
                {params.map((p) => <th key={p.name} className="text-left py-1 pr-2">{p.name}</th>)}
                {['cagr', 'sharpe', 'sortino', 'calmar', 'max_drawdown'].map((k) => <th key={k} className={cn('text-right py-1 px-2', k === objective && 'text-bloomberg')}>{k.replace('_', ' ')}</th>)}
                <th className="text-right py-1 px-2">orders</th><th className="text-left py-1 px-2">period</th>
              </tr></thead>
              <tbody>
                {rows.map((r: any, i: number) => (
                  <tr key={i} className={cn('border-b border-border-subtle', same(r.parameters, best) && 'bg-bloomberg/10')}>
                    {params.map((p) => <td key={p.name} className="py-1 pr-2">{String(r.parameters?.[p.name] ?? '')}</td>)}
                    {r.error ? <td colSpan={7} className="text-red py-1 px-2">{r.error}</td> : <>
                      {['cagr', 'sharpe', 'sortino', 'calmar', 'max_drawdown'].map((k) => (
                        <td key={k} className={cn('text-right py-1 px-2', tone(r.metrics?.[k]) === 'up' ? 'text-green' : tone(r.metrics?.[k]) === 'down' ? 'text-red' : '')}>
                          {k === 'cagr' || k === 'max_drawdown' ? spct(r.metrics?.[k]) : num(r.metrics?.[k])}</td>))}
                      <td className="text-right py-1 px-2">{r.orders ?? '—'}</td>
                      <td className="py-1 px-2 text-text-tertiary">{r.period ? `${r.period[0]} → ${r.period[1]}` : ''}</td></>}
                  </tr>))}
              </tbody>
            </table>
          </div>
        </div>)}
    </div>
  );
}
