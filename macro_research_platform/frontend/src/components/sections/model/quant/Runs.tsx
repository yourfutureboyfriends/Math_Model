/**
 * Stored Code Lab runs: every run is saved (newest 50 per user, /api/v1/quant/code/runs). Reopen one, or tick two to
 * four and compare them side by side — growth on a common window, the headline statistics, validation and what
 * differs between them (engine, code, costs, parameters).
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { GitCompare, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { CATEGORICAL } from '@/lib/chartPalette';
import { useConfirm } from '@/components/ui/ConfirmDialog';
import { CodeResults } from './CodeLab';
import { api, ErrorNote, num, pct, spct, usd } from './shared';

export function Runs({ onOpenCode }: { onOpenCode: (code: string, name: string) => void }) {
  const [rows, setRows] = useState<any[] | null>(null);
  const [sel, setSel] = useState<number[]>([]);
  const [open, setOpen] = useState<any>(null);
  const [cmp, setCmp] = useState<any[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [dialog, ask] = useConfirm();
  const load = useCallback(() => { api('/api/v1/quant/code/runs').then((j) => setRows(j.runs)).catch((e) => setErr(e.message)); }, []);
  useEffect(load, [load]);

  const toggle = (id: number) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : s.length >= 4 ? s : [...s, id]));
  const view = async (id: number) => { setCmp(null); setErr(null); try { setOpen(await api(`/api/v1/quant/code/runs/${id}`)); } catch (e: any) { setErr(e.message); } };
  const compare = async () => {
    setOpen(null); setErr(null);
    try { setCmp(await Promise.all(sel.map((id) => api(`/api/v1/quant/code/runs/${id}`)))); } catch (e: any) { setErr(e.message); }
  };
  const del = async (r: any) => {
    if (!(await ask({ title: `Delete run “${r.label}”?`, body: 'The stored result is removed (the trial registry still counts it).', confirmLabel: 'Delete', danger: true }))) return;
    try { await api(`/api/v1/quant/code/runs/${r.id}`, { method: 'DELETE' }); setSel((s) => s.filter((x) => x !== r.id)); load(); } catch (e: any) { setErr(e.message); }
  };

  return (
    <div className="space-y-3">
      {dialog}
      <ErrorNote msg={err} />
      <div className="flex items-center gap-2 text-2xs">
        <span className="text-text-tertiary">Every run is stored (newest 50). Tick 2–4 to compare.</span>
        <button disabled={sel.length < 2} onClick={compare} className="ml-auto inline-flex items-center gap-1 px-3 py-1 border border-bloomberg text-bloomberg disabled:opacity-40">
          <GitCompare className="w-3 h-3" />Compare {sel.length || ''}</button>
      </div>
      {!rows ? <div className="text-2xs text-text-tertiary">Loading…</div> : rows.length === 0 ? <div className="text-2xs text-text-tertiary">No stored runs yet — run a strategy in Code & test.</div> : (
        <div className="overflow-x-auto">
          <table className="w-full text-[11px] font-mono">
            <thead className="text-text-tertiary"><tr>{['', 'Run', 'When', 'Period', 'CAGR', 'Sharpe', 'Max DD', 'Costs /yr', 'Look-ahead', 'PBO', 'Capacity', ''].map((h, i) => <th key={i} className="text-left font-normal px-1.5 py-1">{h}</th>)}</tr></thead>
            <tbody>{rows.map((r) => {
              const s = r.summary ?? {};
              return (
                <tr key={r.id} className={cn('border-t border-border-subtle', sel.includes(r.id) && 'bg-bloomberg/5')}>
                  <td className="px-1.5"><input type="checkbox" checked={sel.includes(r.id)} onChange={() => toggle(r.id)} aria-label={`Select ${r.label}`} /></td>
                  <td className="px-1.5 font-sans"><button className="hover:underline text-text-primary" onClick={() => view(r.id)}>#{r.id} {r.label}</button></td>
                  <td className="px-1.5 text-text-tertiary">{String(r.ts).slice(0, 16).replace('T', ' ')}</td>
                  <td className="px-1.5 text-text-tertiary">{s.period?.[0]?.slice(0, 4)}–{s.period?.[1]?.slice(0, 4)}</td>
                  <td className="px-1.5">{spct(s.cagr)}</td><td className="px-1.5">{num(s.sharpe)}</td><td className="px-1.5">{pct(s.max_drawdown, 0)}</td>
                  <td className="px-1.5">{pct(s.trading_costs, 2)}</td>
                  <td className={cn('px-1.5', s.causality === false ? 'text-red' : s.causality ? 'text-green' : 'text-text-tertiary')}>{s.causality === false ? 'FAILED' : s.causality ? 'passed' : '—'}</td>
                  <td className={cn('px-1.5', s.pbo >= 0.5 && 'text-red')}>{s.pbo == null ? '—' : pct(s.pbo, 0)}</td>
                  <td className="px-1.5">{s.capacity ? usd(s.capacity) : '—'}</td>
                  <td className="px-1.5"><button onClick={() => del(r)} className="text-text-tertiary hover:text-red" aria-label={`Delete ${r.label}`}><Trash2 className="w-3 h-3" /></button></td>
                </tr>);
            })}</tbody>
          </table>
        </div>)}
      {cmp && <Compare runs={cmp} />}
      {open && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-2xs">
            <span className="text-xs font-semibold text-text-primary">#{open.id} {open.label}</span>
            <span className="text-text-tertiary">{String(open.ts).slice(0, 16).replace('T', ' ')}</span>
            {open.code && <button onClick={() => onOpenCode(open.code, open.label)} className="ml-auto px-2 py-0.5 border border-border hover:border-bloomberg">Open its code in the editor</button>}
          </div>
          <CodeResults r={open.result} a={open.analysis} />
        </div>)}
    </div>
  );
}

function Compare({ runs }: { runs: any[] }) {
  // growth of 1 on the common window (from the latest start)
  const rows = useMemo(() => {
    const start = runs.map((r) => r.result.dates[0]).sort().slice(-1)[0];
    const maps = runs.map((r) => new Map<string, number>(r.result.dates.map((d: string, i: number) => [d, r.result.returns[i]])));
    const dates = Array.from(new Set(runs.flatMap((r) => r.result.dates.filter((d: string) => d >= start)))).sort();
    const g = runs.map(() => 1);
    const step = Math.max(1, Math.ceil(dates.length / 900));
    const out: any[] = [];
    dates.forEach((d, i) => {
      maps.forEach((m, k) => { g[k] *= 1 + (m.get(d) ?? 0); });
      if (i % step === 0 || i === dates.length - 1) out.push({ date: d, ...Object.fromEntries(g.map((v, k) => [`r${k}`, +v.toFixed(4)])) });
    });
    return out;
  }, [runs]);
  const stat = (f: (r: any) => any) => runs.map(f);
  const metricRows: [string, (r: any) => string][] = [
    ['CAGR (net)', (r) => spct(r.result.metrics?.cagr)], ['Sharpe', (r) => num(r.result.metrics?.sharpe)], ['Volatility', (r) => pct(r.result.metrics?.vol)],
    ['Max drawdown', (r) => pct(r.result.metrics?.max_drawdown)], ['Trading costs /yr', (r) => pct(r.result.costs?.total_trading, 2)],
    ['Turnover /yr', (r) => num(r.result.costs?.turnover, 1)], ['Equal-weight baseline CAGR', (r) => spct(r.result.baseline_equal_weight?.cagr)],
    ['Look-ahead check', (r) => { const p = r.result.validation?.causality?.passed; return p === false ? 'FAILED' : p ? 'passed' : '—'; }],
    ['PBO', (r) => (r.result.validation?.pbo?.pbo == null ? '—' : pct(r.result.validation.pbo.pbo, 0))],
    ['CPCV Sharpe (mean / min)', (r) => { const c = r.result.validation?.cpcv; return c ? `${num(c.sharpe_mean)} / ${num(c.sharpe_min)}` : '—'; }],
    ['Capacity', (r) => (r.result.capacity?.capacity ? usd(r.result.capacity.capacity) : '—')],
    ['Ex-ante volatility', (r) => pct(r.result.risk?.vol)], ['Account', (r) => r.result.account_currency ?? 'USD'],
    ['Record', (r) => r.result.provenance?.record_type ?? '—'], ['Engine', (r) => r.result.provenance?.engine_version ?? '—'],
    ['Code hash', (r) => r.result.provenance?.code_hash ?? '—'], ['Parameters', (r) => JSON.stringify(r.result.optimisation?.params ?? r.result.provenance?.params ?? {})],
  ];
  // cost settings that differ between the runs
  const costKeys = Array.from(new Set(runs.flatMap((r) => Object.keys(r.result.provenance?.costs ?? {}))));
  const diffCosts = costKeys.filter((k) => new Set(stat((r) => JSON.stringify(r.result.provenance?.costs?.[k]))).size > 1);
  return (
    <div className="p-3 bg-surface-1 border border-border space-y-3 text-[11px]">
      <div className="text-xs font-semibold text-text-primary">Comparison</div>
      <div>
        <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Growth of 1 on the common window — net of costs</div>
        <LineChart rows={rows} x="date" height={240} log baseline={1} fmt={(v) => `${v.toFixed(2)}×`}
          lines={runs.map((r, k) => ({ key: `r${k}`, label: `#${r.id} ${r.label}`, color: CATEGORICAL[k] }))} />
      </div>
      <table className="w-full font-mono">
        <thead className="text-text-tertiary"><tr><th className="text-left font-normal px-1.5" />{runs.map((r, k) => <th key={r.id} className="text-right font-normal px-1.5" style={{ color: CATEGORICAL[k] }}>#{r.id} {r.label}</th>)}</tr></thead>
        <tbody>
          {metricRows.map(([l, f]) => {
            const vals = stat(f);
            const differs = new Set(vals).size > 1;
            return (<tr key={l} className="border-t border-border-subtle"><td className="font-sans px-1.5 text-text-secondary">{l}</td>
              {vals.map((v, k) => <td key={k} className={cn('text-right px-1.5 break-all', differs && ['Engine', 'Code hash', 'Parameters', 'Account'].includes(l) && 'text-amber')}>{v}</td>)}</tr>);
          })}
          {diffCosts.map((k) => (
            <tr key={k} className="border-t border-border-subtle"><td className="font-sans px-1.5 text-amber">cost: {k}</td>
              {runs.map((r) => <td key={r.id} className="text-right px-1.5 text-amber">{String(r.result.provenance?.costs?.[k] ?? '—')}</td>)}</tr>))}
        </tbody>
      </table>
      <div className="text-text-tertiary">Amber rows differ between runs. Compare like with like: runs on different engines, data windows or account currencies are not directly comparable.</div>
    </div>
  );
}
