/**
 * Live performance of deployed algos: today's provisional intraday P&L (5-minute prices, refreshed every minute) and
 * the record since deployment with today's live point. Reads /api/v1/quant/trader (locked daily record) and
 * /api/v1/quant/trader/live (intraday marking).
 */
import { useEffect, useMemo, useState } from 'react';
import { Loader2, Radio } from 'lucide-react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { CATEGORICAL } from '@/lib/chartPalette';
import { api, Pills, spct } from '@/components/sections/model/quant/shared';

type Book = 'macro' | 'fundamental' | 'technical';

export function LivePerformance({ book, deployments }: { book: Book; deployments: any[] }) {
  const [scope, setScope] = useState<'book' | 'all'>('book');
  const [view, setView] = useState<'today' | 'since'>('today');
  const [live, setLive] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [allBooks, setAllBooks] = useState<any[] | null>(null);

  useEffect(() => {
    let stop = false;
    let t: ReturnType<typeof setTimeout>;
    setLive(null);
    // the server answers at once from its last pricing; while the first pricing runs it says pending — ask again soon
    const load = () => api(`/api/v1/quant/trader/live?book=${scope === 'all' ? 'all' : book}`)
      .then((j) => {
        if (stop) return;
        if (!j.pending) setLive(j);
        setErr(null);
        t = setTimeout(load, j.pending ? 5_000 : 60_000);
      })
      .catch((e) => { if (!stop) { setErr(e.message || 'live prices unavailable'); t = setTimeout(load, 60_000); } });
    load();
    return () => { stop = true; clearTimeout(t); };
  }, [book, scope]);

  // since-deployment curves for every book when "all" is chosen (each trader page only has its own)
  useEffect(() => {
    if (scope !== 'all' || view !== 'since') return;
    Promise.all((['macro', 'fundamental', 'technical'] as const).map((b) => api(`/api/v1/quant/trader?book=${b}`).catch(() => null)))
      .then((xs) => setAllBooks(xs.flatMap((x) => x?.deployments ?? [])));
  }, [scope, view]);

  const algos = (live?.algos ?? []) as any[];
  const deps = scope === 'all' ? (allBooks ?? deployments) : deployments;
  const lines = algos.map((a, i) => ({ key: `a${a.id}`, label: a.name, color: CATEGORICAL[(i + 1) % CATEGORICAL.length] }));

  const todayRows = useMemo(() => {
    const m = new Map<string, any>();
    const put = (t: string, k: string, r: number) => { const row = m.get(t) ?? { t, label: new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }; row[k] = r; m.set(t, row); };
    (live?.book_path ?? []).forEach((p: any) => put(p.t, 'book', p.r));
    algos.forEach((a) => a.path.forEach((p: any) => put(p.t, `a${a.id}`, p.r)));
    return Array.from(m.values()).sort((x, y) => (x.t < y.t ? -1 : 1));
  }, [live]);   // eslint-disable-line react-hooks/exhaustive-deps

  const sinceRows = useMemo(() => {
    const m = new Map<string, any>();
    const byId = new Map(algos.map((a) => [a.id, a]));
    deps.forEach((d: any) => {
      const start = String(d.deployed_at ?? '').slice(0, 10);   // every curve starts at 0 on its deployment day
      if (start) { const row = m.get(start) ?? { t: start, label: start }; row[`a${d.id}`] ??= 0; m.set(start, row); }
      (d.curve ?? []).forEach((c: any) => { const row = m.get(c.date) ?? { t: c.date, label: c.date }; row[`a${d.id}`] = c.nav / d.capital - 1; m.set(c.date, row); });
      const a = byId.get(d.id);
      if (a) {                                              // today's provisional point on top of the locked record
        const t = 'today (live)';
        const row = m.get(t) ?? { t: '9999', label: t };
        row[`a${d.id}`] = (1 + (d.live_return ?? 0)) * (1 + a.today) - 1;
        m.set(t, row);
      }
    });
    return Array.from(m.values()).sort((x, y) => (x.t < y.t ? -1 : 1));
  }, [deps, live]);   // eslint-disable-line react-hooks/exhaustive-deps

  const bookToday = live?.book_path?.length ? live.book_path[live.book_path.length - 1].r : null;
  return (
    <div className="p-3 bg-surface-1 border border-border space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1 text-xs font-semibold text-text-primary"><Radio className="w-3 h-3 text-green" />Live performance</span>
        {bookToday != null && <span className={cn('font-mono text-2xs', bookToday > 0 ? 'text-green' : bookToday < 0 ? 'text-red' : 'text-text-secondary')}>today {spct(bookToday, 2)}</span>}
        <span className="text-[10px] text-text-tertiary">{live ? `updated ${new Date(live.as_of).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · every minute` : ''}</span>
        <span className="ml-auto flex gap-2">
          <Pills label="Live scope" value={scope} onChange={setScope} options={[['book', 'This trader'], ['all', 'All live algos']] as const} />
          <Pills label="Live view" value={view} onChange={setView} options={[['today', 'Today'], ['since', 'Since deployment']] as const} />
        </span>
      </div>
      {err && <div className="text-2xs text-amber">{live ? `Showing the last pricing — ${err}` : err}</div>}
      {!live && !err ? <div className="flex items-center gap-2 text-2xs text-text-tertiary"><Loader2 className="w-3 h-3 animate-spin" />Pricing the holdings…</div>
        : algos.length === 0 ? <div className="text-2xs text-text-tertiary">No deployed algos to mark yet.</div> : (
        <>
          <LineChart rows={view === 'today' ? todayRows : sinceRows} x="label" height={220} baseline={0} fmt={(v) => spct(v, 2)}
            lines={[...(view === 'today' ? [{ key: 'book', label: scope === 'all' ? 'All algos' : 'Book', color: CATEGORICAL[0] }] : []), ...lines]} />
          <div className="flex flex-wrap gap-1.5 text-[10px] font-mono">
            {algos.map((a, i) => (
              <span key={a.id} className="px-1.5 py-0.5 border border-border" title={`${a.names_priced} holdings priced, ${Math.round(a.coverage * 100)}% of the weight`}>
                <span className="inline-block w-2 h-2 mr-1 rounded-sm" style={{ background: CATEGORICAL[(i + 1) % CATEGORICAL.length] }} />
                {a.name}: <span className={a.today > 0 ? 'text-green' : a.today < 0 ? 'text-red' : ''}>{spct(a.today, 2)}</span>
                {a.first_live_session ? ' (first session, from the open)' : ''}
              </span>))}
          </div>
          <div className="text-[10px] text-text-tertiary">{live.note}</div>
        </>)}
    </div>
  );
}
