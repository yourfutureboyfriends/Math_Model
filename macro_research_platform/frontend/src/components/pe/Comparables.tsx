// Comparables: where a deal's entry and exit multiples sit against listed peers (trading comps), the fund's own
// precedent transactions and the industry — and the precedent book itself (add / remove, every multiple sourced).
// Reads /api/v1/pe/{benchmark,precedents}.
import { useCallback, useEffect, useState } from 'react';
import { Loader2, Plus, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, NumField, api, xx } from './peShared';

type Stats = { low: number; q1: number; median: number; q3: number; high: number; n: number } | null;

/** One distribution as a range bar: whiskers low–high, the interquartile box, the median, and the deal's marks. */
function RangeBar({ label, st, marks, lo, hi }: { label: string; st: Stats; marks: { v?: number | null; label: string; tone: string }[]; lo: number; hi: number }) {
  const x = (v: number) => `${Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100))}%`;
  return (
    <div className="grid grid-cols-[150px_1fr] items-center gap-3 text-[11px]">
      <div><div className="text-text-secondary">{label}</div>
        <div className="text-[10px] text-text-tertiary">{st ? `median ${xx(st.median, 1)} · IQR ${xx(st.q1, 1)}–${xx(st.q3, 1)} · n ${st.n}` : 'no data'}</div></div>
      <div className="relative h-7">
        <div className="absolute inset-x-0 top-1/2 h-px bg-border" />
        {st && <>
          <div className="absolute top-1/2 h-px bg-text-tertiary" style={{ left: x(st.low), width: `calc(${x(st.high)} - ${x(st.low)})` }} />
          <div className="absolute top-1 bottom-1 rounded bg-bloomberg/15 ring-1 ring-bloomberg/40" style={{ left: x(st.q1), width: `calc(${x(st.q3)} - ${x(st.q1)})` }} />
          <div className="absolute top-0.5 bottom-0.5 w-0.5 bg-bloomberg" style={{ left: x(st.median) }} title={`median ${xx(st.median, 1)}`} />
        </>}
        {marks.filter((m) => m.v != null).map((m) => (
          <div key={m.label} className="absolute -top-0.5 flex flex-col items-center -translate-x-1/2" style={{ left: x(m.v!) }} title={`${m.label} ${xx(m.v, 1)}`}>
            <span className={cn('w-2.5 h-2.5 rotate-45 rounded-[2px] ring-2 ring-surface-1', m.tone)} />
          </div>))}
      </div>
    </div>
  );
}

export function Comparables({ inputs, industry, onUse }: { inputs: Record<string, any>; industry?: { ev_ebitda?: number; industry?: string } | null;
  onUse: (patch: Record<string, any>) => void }) {
  const [b, setB] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const entry = Number(inputs.entry_multiple) || null;
  const exit = Number(inputs.exit_multiple ?? inputs.entry_multiple) || null;
  const key = `${inputs.symbol ?? ''}|${entry}|${exit}|${industry?.ev_ebitda ?? ''}|${industry?.industry ?? ''}`;
  useEffect(() => {
    const q = new URLSearchParams();
    if (entry) q.set('entry', String(entry));
    if (exit) q.set('exit', String(exit));
    if (inputs.symbol) q.set('symbol', inputs.symbol);
    else if (industry?.industry) q.set('sector', industry.industry);
    if (industry?.ev_ebitda) q.set('industry', String(industry.ev_ebitda));
    setBusy(true);
    const t = setTimeout(() => api(`/api/v1/pe/benchmark?${q}`).then((j) => { setB(j); setErr(null); }).catch((e) => setErr(e.message)).finally(() => setBusy(false)), 400);
    return () => clearTimeout(t);
  }, [key]);                                        // eslint-disable-line react-hooks/exhaustive-deps

  const ts: Stats = b?.trading?.stats ?? null, ps: Stats = b?.precedent_stats ?? null;
  const vals = [ts?.low, ts?.high, ps?.low, ps?.high, entry, exit, industry?.ev_ebitda].filter((v): v is number => v != null && isFinite(v));
  const lo = Math.max(0, Math.floor(Math.min(...vals, 6) - 1)), hi = Math.ceil(Math.max(...vals, 12) + 1);
  const marks = [{ v: entry, label: 'Entry', tone: 'bg-amber' }, { v: exit, label: 'Exit', tone: 'bg-green' }];
  return (
    <Card title="Comparables" right={<span className="text-[10.5px] text-text-tertiary inline-flex items-center gap-3">
      {busy && <Loader2 className="w-3 h-3 animate-spin" />}<span><span className="inline-block w-2 h-2 rotate-45 bg-amber mr-1" />entry</span>
      <span><span className="inline-block w-2 h-2 rotate-45 bg-green mr-1" />exit</span><span>EV / EBITDA</span></span>}>
      {err && <div className="text-xs text-amber mb-2">{err}</div>}
      {b && <div className="space-y-2.5">
        {!ts && !ps && !industry?.ev_ebitda && (
          <div className="text-[11.5px] text-text-secondary">No comparables yet — load a listed company (its peers’ multiples load automatically) or record deals under <b>Precedents</b>.</div>)}
        {ts && <RangeBar label="Trading comps" st={ts} marks={marks} lo={lo} hi={hi} />}
        {ps && <RangeBar label={`Precedents${b.sector ? ` · ${b.sector}` : ''}`} st={ps} marks={marks} lo={lo} hi={hi} />}
        {industry?.ev_ebitda && <RangeBar label="Industry (Damodaran)" st={{ low: industry.ev_ebitda, q1: industry.ev_ebitda, median: industry.ev_ebitda, q3: industry.ev_ebitda, high: industry.ev_ebitda, n: 1 }} marks={marks} lo={lo} hi={hi} />}
        {(ts || ps || industry?.ev_ebitda) && <div className="flex justify-between text-[10px] text-text-tertiary pl-[162px]"><span>{lo}×</span><span>{hi}×</span></div>}
        <ul className="text-[11px] text-text-secondary space-y-0.5">{b.notes.map((n: string) => <li key={n}>· {n}</li>)}</ul>
        <div className="flex flex-wrap gap-1.5">
          {ts && <button onClick={() => onUse({ exit_multiple: Math.round(ts.median * 100) / 100 })} className="px-2 py-1 rounded-md border border-border text-[11px]">Exit at trading median {xx(ts.median, 1)}</button>}
          {ps && <button onClick={() => onUse({ exit_multiple: Math.round(ps.median * 100) / 100 })} className="px-2 py-1 rounded-md border border-border text-[11px]">Exit at precedent median {xx(ps.median, 1)}</button>}
          {ps && <button onClick={() => onUse({ entry_multiple: Math.round(ps.median * 100) / 100 })} className="px-2 py-1 rounded-md border border-border text-[11px]">Entry at precedent median {xx(ps.median, 1)}</button>}
        </div>
        {b.trading?.peers?.length > 0 && (
          <details className="text-[11px]"><summary className="cursor-pointer text-text-tertiary">{b.trading.peers.length} listed peers · {b.trading.source}</summary>
            <table className="w-full mt-1 tabular-nums"><tbody>{b.trading.peers.map((p: any) => (
              <tr key={p.symbol} className={cn('border-t border-border-subtle', !p.usable && 'opacity-50')}>
                <td className="py-0.5 pr-2">{p.name} <span className="text-text-tertiary">{p.symbol}</span></td><td className="text-text-tertiary">{p.region}</td>
                <td className="text-right">{p.usable ? xx(p.ev_ebitda, 1) : 'n/m'}</td></tr>))}</tbody></table></details>)}
      </div>}
    </Card>
  );
}

const EMPTY = { date: '', target: '', acquirer: '', sector: '', region: '', currency: 'USD', ev: null as number | null, ebitda: null as number | null, deal_type: 'Buyout', source: '', notes: '' };

/** The fund's precedent-transaction book. */
export function Precedents() {
  const [rows, setRows] = useState<any[] | null>(null);
  const [f, setF] = useState({ ...EMPTY });
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState('');
  const load = useCallback(() => api('/api/v1/pe/precedents').then((j) => setRows(j.precedents)).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);
  const add = async () => {
    try { await api('/api/v1/pe/precedents', f); setF({ ...EMPTY, sector: f.sector, currency: f.currency }); setErr(null); load(); }
    catch (e: any) { setErr(e.message); }
  };
  const del = async (id: number) => { try { await api(`/api/v1/pe/precedents/${id}`, undefined, 'DELETE'); load(); } catch (e: any) { setErr(e.message); } };
  const shown = (rows ?? []).filter((r) => !filter || `${r.target} ${r.acquirer ?? ''} ${r.sector ?? ''}`.toLowerCase().includes(filter.toLowerCase()));
  const text = (k: keyof typeof EMPTY, label: string, w = '') => (
    <label className={cn('block', w)}><span className="block text-[10.5px] text-text-tertiary mb-0.5">{label}</span>
      <input value={(f[k] as string) ?? ''} onChange={(e) => setF({ ...f, [k]: e.target.value })} type={k === 'date' ? 'date' : 'text'}
        className="w-full rounded-md border border-border bg-bg/40 px-2 py-1 text-xs outline-none focus:border-bloomberg/60" /></label>);
  return (
    <div className="grid grid-cols-1 xl:grid-cols-[360px_1fr] gap-3 items-start">
      <Card title="Record a transaction">
        <div className="grid grid-cols-2 gap-2">
          {text('date', 'Announced')}{text('target', 'Target')}{text('acquirer', 'Acquirer / sponsor')}{text('sector', 'Sector (as in Damodaran / Yahoo)')}
          {text('region', 'Region')}{text('currency', 'Currency')}
          <NumField label="Enterprise value" value={f.ev} onChange={(v) => setF({ ...f, ev: v })} />
          <NumField label="LTM EBITDA" value={f.ebitda} onChange={(v) => setF({ ...f, ebitda: v })} />
          {text('deal_type', 'Type (buyout, strategic…)')}
          <div className="col-span-2">{text('source', 'Source — filing, press release or report (required)')}</div>
          <div className="col-span-2">{text('notes', 'Notes')}</div>
        </div>
        {f.ev && f.ebitda ? <div className="text-[11px] text-text-secondary mt-2">EV / EBITDA {xx(f.ev / f.ebitda, 1)}</div> : null}
        <button onClick={add} className="mt-2 w-full py-1.5 rounded-lg bg-bloomberg text-white text-xs font-medium inline-flex items-center justify-center gap-1.5"><Plus className="w-3.5 h-3.5" />Add to the book</button>
        {err && <div className="text-xs text-red mt-2">{err}</div>}
        <p className="text-[10.5px] text-text-tertiary mt-2">Deal multiples aren’t published free, so this is the fund’s own book: record the deals you track, each with its source. The workbench’s Comparables card compares a deal against the ones in its sector.</p>
      </Card>
      <div className="rounded-xl border border-border bg-surface-1 overflow-x-auto">
        <div className="flex items-center gap-2 p-2.5">
          <span className="text-[12px] font-semibold">Precedent transactions</span><span className="text-[11px] text-text-tertiary">{rows?.length ?? 0} in this fund’s book</span>
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter by target, acquirer or sector"
            className="ml-auto w-60 rounded-md border border-border bg-bg/40 px-2 py-1 text-xs outline-none" />
        </div>
        {!rows ? <div className="p-4 text-xs text-text-tertiary">Loading…</div> : shown.length === 0 ? <div className="p-4 text-xs text-text-tertiary">No transactions recorded yet.</div> : (
          <table className="w-full text-[11.5px] tabular-nums">
            <thead><tr className="text-left text-text-tertiary"><th className="px-2.5 font-normal">Date</th><th className="font-normal">Target</th><th className="font-normal">Acquirer</th>
              <th className="font-normal">Sector</th><th className="font-normal text-right">EV</th><th className="font-normal text-right">EBITDA</th><th className="font-normal text-right">EV/EBITDA</th><th className="font-normal">Source</th><th /></tr></thead>
            <tbody>{shown.map((r) => (
              <tr key={r.id} className="border-t border-border-subtle">
                <td className="px-2.5 py-1">{r.date}</td><td className="font-medium">{r.target}</td><td className="text-text-secondary">{r.acquirer ?? '—'}</td>
                <td className="text-text-secondary">{r.sector ?? '—'}</td><td className="text-right">{r.ev.toLocaleString()} {r.currency ?? ''}</td>
                <td className="text-right">{r.ebitda.toLocaleString()}</td><td className="text-right font-semibold">{xx(r.ev_ebitda, 1)}</td>
                <td className="text-text-tertiary max-w-[16rem] truncate" title={r.source}>{r.source}</td>
                <td className="pr-2"><button onClick={() => del(r.id)} title="Remove" className="text-text-tertiary hover:text-red"><Trash2 className="w-3.5 h-3.5" /></button></td>
              </tr>))}</tbody>
          </table>)}
      </div>
    </div>
  );
}

/** The macro and credit backdrop for the deal (Macro area + credit markets), with a link back to the macro model. */
export function MacroBackdrop({ currency }: { currency?: string }) {
  const [m, setM] = useState<any>(null);
  useEffect(() => { api(`/api/v1/pe/macro?currency=${encodeURIComponent(currency || 'USD')}`).then(setM).catch(() => setM(null)); }, [currency]);
  if (!m) return null;
  const cr = m.credit ?? {}, rg = m.b_spread_range;
  const tone = m.credit_conditions === 'tight' ? 'text-green' : m.credit_conditions === 'wide' ? 'text-amber' : 'text-text-primary';
  const pc = (v?: number | null, d = 1) => (v == null ? '—' : `${(v * 100).toFixed(d)}%`);
  const cell = (label: string, value: React.ReactNode, sub?: React.ReactNode) => (
    <div className="p-2.5 rounded-lg bg-text-primary/[0.03]"><div className="text-[10px] uppercase tracking-[0.06em] text-text-tertiary">{label}</div>
      <div className="text-[13px] font-semibold mt-0.5">{value}</div>{sub && <div className="text-[10.5px] text-text-tertiary mt-0.5">{sub}</div>}</div>);
  return (
    <Card title="Macro & credit backdrop" right={<button onClick={() => import('@/lib/commands').then((c) => c.openPanel('macro-model'))} className="text-[11px] text-bloomberg hover:underline">Open the macro model →</button>}>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
        {cell('Regime', <>{m.signal_regime ? m.signal_regime.charAt(0).toUpperCase() + m.signal_regime.slice(1) : '—'}</>,
          m.model_regime ? `macro model (US): ${m.model_regime} ${pc(m.model_probability, 0)}` : undefined)}
        {cell('Recession, next 12m', pc(m.recession_12m), m.recession_level ? `${m.recession_level} · model contraction odds ${pc(m.p_contraction)}` : undefined)}
        {cell('Financing today', `${cr.base_rate_name ?? 'Base'} ${pc(cr.base_rate, 2)}`, cr.loan_spread != null ? `loans + ${pc(cr.loan_spread, 2)} · B bonds + ${pc(cr.b_spread, 2)}` : `B bonds + ${pc(cr.b_spread, 2)}`)}
        {cell('Credit spreads', <span className={tone}>{m.credit_conditions ? m.credit_conditions.charAt(0).toUpperCase() + m.credit_conditions.slice(1) : '—'}</span>,
          rg ? `single-B ${pc(rg.now, 2)} · ${pc(m.b_spread_percentile, 0)} pctile since ${String(rg.from).slice(0, 7)}` : undefined)}
      </div>
      <p className="text-[10.5px] text-text-tertiary mt-2">Spread history is what FRED serves for the ICE BofA indices (from {rg ? String(rg.from).slice(0, 7) : 'late 2023'}) — a recent window, not a full credit cycle.
        A deal underwritten on today’s financing should hold up if spreads and the exit multiple revert: compare the downside case and the leverage × growth grid.</p>
    </Card>
  );
}
