// Deal pipeline: the fund's saved LBO cases by stage — headline returns from their last run, stage moves, notes and
// the activity log; "Open" loads a deal back into the workbench. Reads /api/v1/pe/deals.
import { useCallback, useEffect, useState } from 'react';
import { Loader2, MessageSquarePlus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { amt, api, irrTone, openDeal, pct, unitFor, xx } from './peShared';

export function Pipeline() {
  const [deals, setDeals] = useState<any[] | null>(null);
  const [stages, setStages] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<any>(null);
  const [text, setText] = useState('');

  const load = useCallback(() => api('/api/v1/pe/deals').then((j) => { setDeals(j.deals); setStages(j.stages); }).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);
  const show = async (id: number) => { try { setOpen(await api(`/api/v1/pe/deals/${id}`)); } catch (e: any) { setErr(e.message); } };
  const move = async (id: number, stage: string) => {
    try { const d = await api(`/api/v1/pe/deals/${id}/stage`, { stage }); if (open?.id === id) setOpen(d); load(); } catch (e: any) { setErr(e.message); }
  };
  const addNote = async () => {
    if (!open || !text.trim()) return;
    try { setOpen(await api(`/api/v1/pe/deals/${open.id}/notes`, { text })); setText(''); load(); } catch (e: any) { setErr(e.message); }
  };

  if (err) return <div className="text-xs text-red">{err}</div>;
  if (!deals) return <div className="p-6 text-xs text-text-tertiary"><Loader2 className="w-4 h-4 animate-spin inline mr-2" />Loading the pipeline…</div>;
  const active = stages.filter((s) => s !== 'Passed');
  return (
    <div className="space-y-3">
      {/* Funnel: count per stage */}
      <div className="flex flex-wrap gap-2">
        {stages.map((s) => { const k = deals.filter((d) => d.stage === s).length; return (
          <div key={s} className={cn('px-3 py-2 rounded-xl border border-border bg-surface-1 min-w-[110px]', !k && 'opacity-60')}>
            <div className="text-[10px] uppercase tracking-[0.06em] text-text-tertiary">{s}</div>
            <div className="text-lg font-semibold tabular-nums">{k}</div>
          </div>); })}
      </div>
      {deals.length === 0 ? (
        <div className="p-6 rounded-xl border border-dashed border-border text-xs text-text-tertiary">No deals yet — build a case in the LBO workbench and press <b>Save to pipeline</b>. Deals are kept in this fund’s own database.</div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-[1fr_380px] gap-3 items-start">
          <div className="rounded-xl border border-border bg-surface-1 overflow-x-auto">
            <table className="w-full text-[11.5px] tabular-nums">
              <thead><tr className="text-left text-text-tertiary"><th className="px-3 py-2 font-normal">Deal</th><th className="font-normal">Stage</th>
                <th className="font-normal text-right">EV</th><th className="font-normal text-right">Entry</th><th className="font-normal text-right">Leverage</th>
                <th className="font-normal text-right">IRR</th><th className="font-normal text-right">MOIC</th><th className="font-normal text-right">Max at hurdle</th><th className="font-normal text-right pr-3">Updated</th></tr></thead>
              <tbody>{[...active, 'Passed'].flatMap((s) => deals.filter((d) => d.stage === s)).map((d) => { const sm = d.summary ?? {}; const u = unitFor(sm.ev ? sm.ev / (sm.entry_multiple || 1) : null); return (
                <tr key={d.id} onClick={() => show(d.id)} className={cn('border-t border-border-subtle cursor-pointer', open?.id === d.id && 'bg-bloomberg/5', d.stage === 'Passed' && 'opacity-60')}>
                  <td className="px-3 py-1.5"><div className="font-medium text-text-primary">{d.name}</div><div className="text-[10.5px] text-text-tertiary">{d.symbol ?? 'private'} · {d.owner}</div></td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <select value={d.stage} onChange={(e) => move(d.id, e.target.value)} className="rounded-md border border-border bg-bg/40 px-1.5 py-0.5 text-[11px]">
                      {stages.map((s) => <option key={s}>{s}</option>)}</select></td>
                  <td className="text-right">{sm.ev ? `${amt(sm.ev, sm.currency, u)}${u === 1e6 ? 'm' : ''}` : '—'}</td>
                  <td className="text-right">{xx(sm.entry_multiple, 1)}</td><td className="text-right">{xx(sm.leverage, 1)}</td>
                  <td className={cn('text-right font-semibold', irrTone(sm.irr, sm.hurdle ?? 0.2))}>{pct(sm.irr)}</td>
                  <td className="text-right">{xx(sm.moic)}</td><td className="text-right">{xx(sm.max_entry_multiple, 1)}</td>
                  <td className="text-right pr-3 text-text-tertiary">{(d.updated_at ?? '').slice(0, 10)}</td>
                </tr>); })}</tbody>
            </table>
          </div>
          {open && (
            <div className="p-3.5 rounded-xl border border-border bg-surface-1 space-y-2.5">
              <div className="flex items-start gap-2">
                <div className="min-w-0"><div className="text-[13px] font-semibold text-text-primary truncate">{open.name}</div>
                  <div className="text-[10.5px] text-text-tertiary">{open.stage} · created {(open.created_at ?? '').slice(0, 10)} by {open.owner}</div></div>
                <button onClick={() => openDeal(open.id)} className="ml-auto px-2.5 py-1 rounded-lg bg-bloomberg text-white text-[11px] font-medium">Open in workbench</button>
              </div>
              {open.summary?.warnings?.length > 0 && <div className="text-[11px] text-amber">{open.summary.warnings.join(' ')}</div>}
              <div className="flex gap-2">
                <input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addNote()} placeholder="Add a note (IC feedback, diligence finding…)"
                  className="flex-1 rounded-md border border-border bg-bg/40 px-2 py-1.5 text-xs outline-none focus:border-bloomberg/60" />
                <button onClick={addNote} className="px-2 rounded-md border border-border" title="Add note"><MessageSquarePlus className="w-3.5 h-3.5" /></button>
              </div>
              <ol className="space-y-1.5 max-h-80 overflow-y-auto">
                {open.log.map((l: any, i: number) => (
                  <li key={i} className="text-[11px] border-l-2 border-border pl-2">
                    <div className="text-text-tertiary">{(l.at ?? '').replace('T', ' ').slice(0, 16)} · {l.author} · {l.kind}</div>
                    <div className="text-text-secondary">{l.text}</div></li>))}
              </ol>
            </div>)}
        </div>)}
    </div>
  );
}
