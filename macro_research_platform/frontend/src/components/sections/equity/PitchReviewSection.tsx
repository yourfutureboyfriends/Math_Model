/**
 * Pitch Review — analysts' investment pitches for the Portfolio Management Committee: thesis, horizon, bear / base /
 * bull fair values with probabilities, entry range, target weight, catalysts and kill criteria; versioned (a revision
 * never overwrites); submit → PMC decision by a PM who is not the author (four-eyes); valuation against the live price
 * and kill-criteria status. Backend: /api/v1/pitches (api/pitches.py).
 */
import { useCallback, useEffect, useState } from 'react';
import { Loader2, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';

const inputCls = 'w-full bg-surface-1 border border-border px-2 py-1 text-xs font-mono text-text-primary focus:border-bloomberg outline-none';
const num = (v?: number | null, d = 2) => (v == null || !Number.isFinite(v) ? '—' : v.toLocaleString(undefined, { maximumFractionDigits: d }));
const spct = (v?: number | null) => (v == null || !Number.isFinite(v) ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`);
const STATUS_TONE: Record<string, string> = { draft: 'text-text-tertiary', submitted: 'text-amber', approved: 'text-green', rejected: 'text-red', closed: 'text-text-tertiary' };

type Kill = { type: string; level?: string; threshold?: string; metric?: string; date?: string; description?: string };
const EMPTY = {
  symbol: '', title: '', thesis: '', horizon_years: '3', valuation_method: '',
  bear: '', bear_p: '0.25', base: '', base_p: '0.5', bull: '', bull_p: '0.25',
  entry_low: '', entry_high: '', target_weight: '', catalyst: '', catalyst_date: '', catalyst_conf: 'scheduled',
};

async function call(url: string, method = 'GET', body?: any) {
  const r = await fetch(url, { method, headers: body ? { 'Content-Type': 'application/json' } : undefined, body: body ? JSON.stringify(body) : undefined });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : `HTTP ${r.status}`);
  return j;
}

export function PitchReviewSection() {
  const [list, setList] = useState<any>(null);
  const [sel, setSel] = useState<any>(null);
  const [form, setForm] = useState<any>(null);          // null = closed; {…, _revise: id} = revising
  const [kills, setKills] = useState<Kill[]>([{ type: 'price_below', level: '', description: '' }]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notes, setNotes] = useState('');

  const load = useCallback(async () => {
    try { setList(await call('/api/v1/pitches')); setErr(null); } catch (e: any) { setErr(e.message); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const open = async (id: number) => { setBusy(true); try { setSel(await call(`/api/v1/pitches/${id}`)); } catch (e: any) { setErr(e.message); } finally { setBusy(false); } };

  const toBody = () => {
    const f = form;
    const body: any = {
      thesis: f.thesis, horizon_years: Number(f.horizon_years), valuation_method: f.valuation_method,
      scenarios: { bear: { value: Number(f.bear), probability: Number(f.bear_p) }, base: { value: Number(f.base), probability: Number(f.base_p) },
                   bull: { value: Number(f.bull), probability: Number(f.bull_p) } },
      kill_criteria: kills.filter((k) => k.type).map((k) => ({ type: k.type, description: k.description,
        ...(k.level ? { level: Number(k.level) } : {}), ...(k.threshold ? { threshold: Number(k.threshold) } : {}),
        ...(k.metric ? { metric: k.metric } : {}), ...(k.date ? { date: k.date } : {}) })),
    };
    if (f.entry_low && f.entry_high) body.entry_range = { low: Number(f.entry_low), high: Number(f.entry_high) };
    if (f.target_weight) body.target_weight = Number(f.target_weight) / 100;
    if (f.catalyst) body.catalysts = [{ event: f.catalyst, expected_date: f.catalyst_date || null, date_confidence: f.catalyst_date ? f.catalyst_conf : 'undated' }];
    return body;
  };
  const save = async () => {
    setBusy(true); setErr(null);
    try {
      const p = form._revise
        ? await call(`/api/v1/pitches/${form._revise}/versions`, 'POST', { body: toBody(), note: form.note || '' })
        : await call('/api/v1/pitches', 'POST', { symbol: form.symbol, title: form.title || form.symbol, body: toBody() });
      setForm(null); await load(); await open(p.id);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const act = async (path: string, body?: any) => {
    setBusy(true); setErr(null);
    try { const p = await call(`/api/v1/pitches/${sel.id}/${path}`, 'POST', body); await load(); await open(p.id); setNotes(''); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const revise = () => {
    const c = sel.current;
    setForm({ ...EMPTY, _revise: sel.id, symbol: sel.symbol, title: sel.title, thesis: c.thesis, horizon_years: String(c.horizon_years), valuation_method: c.valuation_method ?? '',
      bear: String(c.scenarios.bear.value), bear_p: String(c.scenarios.bear.probability), base: String(c.scenarios.base.value), base_p: String(c.scenarios.base.probability),
      bull: String(c.scenarios.bull.value), bull_p: String(c.scenarios.bull.probability),
      entry_low: c.entry_range ? String(c.entry_range.low) : '', entry_high: c.entry_range ? String(c.entry_range.high) : '',
      target_weight: c.target_weight ? String(c.target_weight * 100) : '' });
    setKills((c.kill_criteria ?? []).map((k: any) => ({ ...k, level: k.level != null ? String(k.level) : '', threshold: k.threshold != null ? String(k.threshold) : '' })));
  };
  const F = (k: string, label: string, w = 'w-24', ph = '') => (
    <label className="text-2xs text-text-tertiary">{label}<br /><input className={cn(inputCls, w)} value={form[k]} placeholder={ph} onChange={(e) => setForm({ ...form, [k]: e.target.value })} /></label>);

  return (
    <section id="pitch-review" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">◆</span>
          <h2 className="section-title">Pitch Review</h2>
          <span className="text-2xs text-text-tertiary ml-2">analyst pitches for the PMC · versioned · four-eyes decisions · kill criteria</span>
        </div>
        <button onClick={() => { setForm({ ...EMPTY }); setKills([{ type: 'price_below', level: '', description: '' }]); }} className="inline-flex items-center gap-1 px-2 py-0.5 text-2xs border border-border hover:border-bloomberg"><Plus className="w-3 h-3" />New pitch</button>
      </div>
      {err && <div className="text-xs text-red mb-2">{err}</div>}

      {form && (
        <div className="border border-border bg-surface-1 p-3 mb-3 space-y-2">
          <div className="text-xs font-semibold text-text-primary">{form._revise ? `Revise pitch #${form._revise} (adds a version; an approved pitch goes back to the PMC)` : 'New pitch'}</div>
          <div className="flex flex-wrap gap-2">
            {!form._revise && F('symbol', 'Security', 'w-24', 'AZN.L')}
            {F('title', 'Title', 'w-56')}{F('horizon_years', 'Horizon (years, 1–5)', 'w-20')}{F('valuation_method', 'Valuation method', 'w-56', 'DCF, EV/EBITDA…')}
          </div>
          <label className="text-2xs text-text-tertiary block">Thesis<textarea className={cn(inputCls, 'h-20 font-sans')} value={form.thesis} onChange={(e) => setForm({ ...form, thesis: e.target.value })} /></label>
          <div className="text-2xs text-text-tertiary">Fair values per share in the listing's quote currency (pence for London). Probabilities add up to 1.</div>
          <div className="flex flex-wrap gap-2">
            {F('bear', 'Bear value')}{F('bear_p', 'p', 'w-14')}{F('base', 'Base value')}{F('base_p', 'p', 'w-14')}{F('bull', 'Bull value')}{F('bull_p', 'p', 'w-14')}
            {F('entry_low', 'Entry low')}{F('entry_high', 'Entry high')}{F('target_weight', 'Target weight %', 'w-20')}
          </div>
          <div className="flex flex-wrap gap-2">
            {F('catalyst', 'Catalyst', 'w-56', 'Q3 results')}{F('catalyst_date', 'Expected date', 'w-28', 'YYYY-MM-DD')}
            <label className="text-2xs text-text-tertiary">Date is<br /><select className={inputCls} value={form.catalyst_conf} onChange={(e) => setForm({ ...form, catalyst_conf: e.target.value })}><option value="scheduled">scheduled</option><option value="estimated">estimated</option></select></label>
          </div>
          <div className="text-2xs text-text-tertiary">Kill criteria (at least one)</div>
          {kills.map((k, i) => (
            <div key={i} className="flex flex-wrap gap-2 items-end">
              <select className={cn(inputCls, 'w-44')} value={k.type} onChange={(e) => setKills(kills.map((x, j) => (j === i ? { ...x, type: e.target.value } : x)))}>
                {(list?.kill_types ?? ['price_below']).map((t: string) => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
              </select>
              {['price_below', 'price_above'].includes(k.type) && <input className={cn(inputCls, 'w-24')} placeholder="level" value={k.level ?? ''} onChange={(e) => setKills(kills.map((x, j) => (j === i ? { ...x, level: e.target.value } : x)))} />}
              {['drawdown_from_entry', 'underperform_benchmark', 'metric_below', 'metric_above'].includes(k.type) && <input className={cn(inputCls, 'w-24')} placeholder="threshold (0.2)" value={k.threshold ?? ''} onChange={(e) => setKills(kills.map((x, j) => (j === i ? { ...x, threshold: e.target.value } : x)))} />}
              {['metric_below', 'metric_above'].includes(k.type) && (
                <select className={cn(inputCls, 'w-36')} value={k.metric ?? ''} onChange={(e) => setKills(kills.map((x, j) => (j === i ? { ...x, metric: e.target.value } : x)))}>
                  <option value="">metric…</option>{(list?.metrics ?? []).map((m: string) => <option key={m}>{m}</option>)}
                </select>)}
              {k.type === 'date_passed' && <input className={cn(inputCls, 'w-28')} placeholder="YYYY-MM-DD" value={k.date ?? ''} onChange={(e) => setKills(kills.map((x, j) => (j === i ? { ...x, date: e.target.value } : x)))} />}
              <input className={cn(inputCls, 'w-64 font-sans')} placeholder="why it ends the thesis" value={k.description ?? ''} onChange={(e) => setKills(kills.map((x, j) => (j === i ? { ...x, description: e.target.value } : x)))} />
              <button className="text-2xs text-text-tertiary hover:text-red" onClick={() => setKills(kills.filter((_, j) => j !== i))}>remove</button>
            </div>))}
          <button className="text-2xs text-bloomberg" onClick={() => setKills([...kills, { type: 'manual', description: '' }])}>+ kill criterion</button>
          {form._revise && <div className="flex gap-2">{F('note', 'What changed', 'w-96')}</div>}
          <div className="flex gap-2">
            <button onClick={save} disabled={busy} className="px-3 py-1 text-2xs bg-bloomberg text-bg disabled:opacity-50">{busy ? 'Saving…' : form._revise ? 'Save version' : 'Create draft'}</button>
            <button onClick={() => setForm(null)} className="px-3 py-1 text-2xs border border-border">Cancel</button>
          </div>
        </div>)}

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] gap-2">
        <div className="border border-border bg-surface-1">
          {!list ? <div className="p-3 text-2xs text-text-tertiary"><Loader2 className="w-3 h-3 animate-spin inline" /> Loading…</div>
            : !list.pitches.length ? <div className="p-3 text-2xs text-text-tertiary">No pitches yet — analysts add them with New pitch.</div> : (
              <table className="w-full text-2xs">
                <thead><tr className="text-text-tertiary border-b border-border"><th className="text-left p-1.5">Security</th><th className="text-left p-1.5">Status</th><th className="text-right p-1.5">Value (p-wtd)</th><th className="text-left p-1.5">Analyst</th><th className="text-left p-1.5">Updated</th></tr></thead>
                <tbody>
                  {list.pitches.map((p: any) => (
                    <tr key={p.id} onClick={() => open(p.id)} className={cn('cursor-pointer border-b border-border-subtle hover:bg-surface-3', sel?.id === p.id && 'bg-surface-3')}>
                      <td className="p-1.5 font-mono text-text-primary">{p.symbol}<span className="text-text-tertiary font-sans"> {p.title !== p.symbol ? p.title : ''}</span></td>
                      <td className={cn('p-1.5 uppercase', STATUS_TONE[p.status])}>{p.status} v{p.current_version}</td>
                      <td className="p-1.5 text-right font-mono">{num(p.expected_value)}</td>
                      <td className="p-1.5">{p.analyst}</td>
                      <td className="p-1.5 text-text-tertiary">{String(p.updated_at).slice(0, 10)}</td>
                    </tr>))}
                </tbody>
              </table>)}
        </div>

        {sel && (
          <div className="border border-border bg-surface-1 p-3 space-y-2 text-xs">
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="font-mono font-semibold text-text-primary">{sel.symbol}</span><span className="text-text-secondary">{sel.title}</span>
              <span className={cn('uppercase text-2xs', STATUS_TONE[sel.status])}>{sel.status} · v{sel.current_version}</span>
              <span className="text-2xs text-text-tertiary ml-auto">by {sel.analyst}{sel.decided_by ? ` · PMC ${sel.status} by ${sel.decided_by} ${String(sel.decided_at).slice(0, 10)}` : ''}</span>
            </div>
            <div className="text-text-secondary whitespace-pre-wrap">{sel.current?.thesis}</div>
            {sel.valuation && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-2xs">
                <div>Price <b className="font-mono">{num(sel.quote?.price)} {sel.quote?.currency}</b></div>
                <div>Bear / base / bull <b className="font-mono">{num(sel.valuation.bear)} / {num(sel.valuation.base)} / {num(sel.valuation.bull)}</b></div>
                <div>Expected return <b className="font-mono">{spct(sel.valuation.expected_return)}</b> ({spct(sel.valuation.annualised_expected_return)} a yr, {sel.current?.horizon_years}y)</div>
                <div>Reward / risk <b className="font-mono">{num(sel.valuation.reward_to_risk)}</b>{sel.valuation.in_entry_range != null && <> · {sel.valuation.in_entry_range ? 'in entry range' : 'outside entry range'}</>}</div>
              </div>)}
            <div className="text-2xs">
              <div className="text-text-tertiary uppercase tracking-wider mb-0.5">Kill criteria</div>
              {(sel.kill_criteria_status ?? []).map((k: any, i: number) => (
                <div key={i} className={cn(k.status === 'triggered' ? 'text-red' : k.status === 'ok' ? 'text-green' : 'text-text-tertiary')}>
                  {k.status === 'triggered' ? '✗ TRIGGERED' : k.status === 'ok' ? '✓ ok' : k.status === 'manual' ? '· manual check' : '· not evaluable'} — {k.description || k.type.replace(/_/g, ' ')}
                  {k.level != null ? ` (level ${num(k.level)})` : ''}{k.threshold != null ? ` (threshold ${k.threshold})` : ''}{k.observed != null ? ` · now ${typeof k.observed === 'number' ? num(k.observed, 3) : k.observed}` : ''}
                </div>))}
            </div>
            {sel.current?.catalysts?.length > 0 && (
              <div className="text-2xs"><span className="text-text-tertiary uppercase tracking-wider">Catalysts </span>
                {sel.current.catalysts.map((c: any, i: number) => <span key={i} className="mr-3">{c.event} {c.expected_date ? `${c.expected_date} (${c.date_confidence})` : '(undated)'}</span>)}</div>)}
            <div className="text-2xs text-text-tertiary">Versions: {sel.versions.map((v: any) => `v${v.version} ${String(v.created_at).slice(0, 10)} ${v.author}${v.note ? ` — ${v.note}` : ''}`).join(' · ')}</div>
            {sel.decision_notes && <div className="text-2xs">PMC notes: {sel.decision_notes}</div>}
            <div className="flex flex-wrap gap-2 items-center pt-1 border-t border-border-subtle">
              {['draft', 'rejected'].includes(sel.status) && <button disabled={busy} onClick={() => act('submit')} className="px-2 py-0.5 text-2xs border border-amber text-amber">Submit to PMC</button>}
              {sel.status !== 'closed' && <button disabled={busy} onClick={revise} className="px-2 py-0.5 text-2xs border border-border">Revise</button>}
              {sel.status === 'submitted' && <>
                <input className={cn(inputCls, 'w-64 font-sans')} placeholder="PMC decision notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
                <button disabled={busy} onClick={() => act('decision', { decision: 'approve', notes })} className="px-2 py-0.5 text-2xs border border-green text-green">Record approval</button>
                <button disabled={busy} onClick={() => act('decision', { decision: 'reject', notes })} className="px-2 py-0.5 text-2xs border border-red text-red">Record rejection</button>
              </>}
              {sel.status === 'approved' && <button disabled={busy} onClick={() => act('close')} className="px-2 py-0.5 text-2xs border border-border">Close (position exited)</button>}
              <span className="text-2xs text-text-tertiary">Decisions are recorded by a PM who is not the author; every step is in the audit log.</span>
            </div>
          </div>)}
      </div>
    </section>
  );
}
