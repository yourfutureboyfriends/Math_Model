// Your tools: W (watchlists), ALRT (alerts), JRNL (trading journal) + the alert toast.
import { useCallback, useEffect, useState } from 'react';
import { Bell, Plus, Trash2, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Chg, ErrorBox, fmtPct, fmtPrice, Loading, Panel, Spark } from './shared';

async function call(url: string, method = 'GET', body?: unknown) {
  const r = await fetch(url, { method, headers: body ? { 'Content-Type': 'application/json' } : undefined, body: body ? JSON.stringify(body) : undefined });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j?.detail === 'string' ? j.detail : `HTTP ${r.status}`);
  return j;
}
const inp = 'bg-surface-1 border border-border px-2 py-1 text-xs text-text-primary';

// ── W ────────────────────────────────────────────────────────────────────────
export function WatchlistsView({ onOpen }: { onOpen: (s: string) => void }) {
  const [lists, setLists] = useState<any[] | null>(null);
  const [active, setActive] = useState<number | null>(null);
  const [quotes, setQuotes] = useState<Record<string, any>>({});
  const [add, setAdd] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => call('/api/v1/mkt/watchlists').then((j) => { setLists(j.watchlists); setActive((a) => a ?? j.watchlists[0]?.id ?? null); }).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);
  const list = lists?.find((l) => l.id === active);
  useEffect(() => {
    if (!list?.symbols.length) { setQuotes({}); return; }
    let live = true;
    const get = () => call(`/api/v1/mkt/quotes?symbols=${encodeURIComponent(list.symbols.join(','))}`)
      .then((j) => live && setQuotes(Object.fromEntries(j.quotes.map((q: any) => [q.symbol, q])))).catch(() => {});
    get();
    const t = setInterval(() => document.visibilityState === 'visible' && get(), 60_000);
    return () => { live = false; clearInterval(t); };
  }, [list?.id, list?.symbols.join(',')]);
  const save = async (symbols: string[], name?: string) => {
    if (!list) return;
    try { const u = await call(`/api/v1/mkt/watchlists/${list.id}`, 'PUT', { symbols, name }); setLists((ls) => ls!.map((l) => (l.id === u.id ? u : l))); setErr(null); }
    catch (e: any) { setErr(e.message); }
  };
  const create = async () => {
    const name = window.prompt('Name for the new watchlist?', 'New list');
    if (!name) return;
    try { const w = await call('/api/v1/mkt/watchlists', 'POST', { name, symbols: [] }); setLists((ls) => [...(ls ?? []), w]); setActive(w.id); } catch (e: any) { setErr(e.message); }
  };
  const remove = async () => {
    if (!list || !window.confirm(`Delete the watchlist “${list.name}”?`)) return;
    try { await call(`/api/v1/mkt/watchlists/${list.id}`, 'DELETE'); setActive(null); load(); } catch (e: any) { setErr(e.message); }
  };
  if (!lists) return err ? <ErrorBox msg={err} /> : <Loading label="Loading watchlists…" />;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1">
        {lists.map((l) => (
          <button key={l.id} onClick={() => setActive(l.id)} className={cn('px-3 py-1 text-2xs border', l.id === active ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary hover:text-text-primary')}>
            {l.name} <span className="text-text-tertiary">{l.symbols.length}</span></button>))}
        <button onClick={create} className="px-2 py-1 text-2xs border border-dashed border-border text-text-tertiary hover:text-text-primary inline-flex items-center gap-1"><Plus className="w-3 h-3" />New list</button>
      </div>
      <ErrorBox msg={err} />
      {list && (
        <Panel title={list.name} right={<div className="flex items-center gap-2">
          <button onClick={() => { const n = window.prompt('Rename watchlist', list.name); if (n) save(list.symbols, n); }} className="text-2xs text-text-tertiary hover:text-text-primary">Rename</button>
          <button onClick={remove} className="text-2xs text-text-tertiary hover:text-red">Delete</button></div>}>
          <form onSubmit={(e) => { e.preventDefault(); const s = add.trim().toUpperCase(); if (s && !list.symbols.includes(s)) save([...list.symbols, s]); setAdd(''); }} className="flex gap-2 mb-3">
            <input value={add} onChange={(e) => setAdd(e.target.value)} placeholder="Add a ticker — e.g. NVDA, 7203.T, EURUSD=X, GC=F, BTC-USD" className={cn(inp, 'flex-1 font-mono')} />
            <button className="px-3 py-1 text-xs bg-bloomberg text-text-inverse">Add</button>
          </form>
          {list.symbols.length === 0 ? <div className="text-2xs text-text-tertiary">Empty — add tickers above, or use “+ Watch” on any instrument page.</div> : (
            <table className="w-full text-xs"><thead><tr className="text-2xs text-text-tertiary"><th className="text-left font-normal">Symbol</th><th className="text-right font-normal">Last</th>
              <th className="text-right font-normal">Day</th><th className="text-right font-normal">1 month</th><th className="text-right font-normal hidden sm:table-cell">Trend</th><th /></tr></thead>
              <tbody>{list.symbols.map((s: string) => { const q = quotes[s]; return (
                <tr key={s} className="border-t border-border-subtle hover:bg-surface-3">
                  <td className="py-1.5 font-mono text-text-primary cursor-pointer" onClick={() => onOpen(s)}>{s}</td>
                  <td className="text-right font-mono">{q ? fmtPrice(q.price) : '…'}</td>
                  <td className="text-right"><Chg v={q?.change_1d} /></td><td className="text-right"><Chg v={q?.change_1m} d={1} /></td>
                  <td className="text-right hidden sm:table-cell"><Spark values={q?.spark} /></td>
                  <td className="text-right"><button onClick={() => save(list.symbols.filter((x: string) => x !== s))} aria-label={`Remove ${s}`} className="p-1 text-text-tertiary hover:text-red"><X className="w-3 h-3" /></button></td>
                </tr>); })}</tbody></table>
          )}
          <div className="text-[10px] text-text-tertiary mt-2">Prices refresh every minute while this tab is open (daily bars; exchange delays apply).</div>
        </Panel>
      )}
    </div>
  );
}

export function useAddToWatchlist() {
  return useCallback(async (symbol: string) => {
    const j = await call('/api/v1/mkt/watchlists');
    const lists = j.watchlists as any[];
    const target = lists.length === 1 ? lists[0] : lists.find((l) => l.name === window.prompt(`Add ${symbol} to which list?\n${lists.map((l) => l.name).join(', ')}`, lists[0]?.name));
    if (!target) return null;
    if (target.symbols.includes(symbol)) return target.name;
    await call(`/api/v1/mkt/watchlists/${target.id}`, 'PUT', { symbols: [...target.symbols, symbol] });
    return target.name;
  }, []);
}

// ── ALRT ─────────────────────────────────────────────────────────────────────
export function AlertsView({ seed }: { seed?: string }) {
  const [data, setData] = useState<any>(null);
  const [form, setForm] = useState({ symbol: seed ?? '', kind: 'above', value: '', note: '' });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => call('/api/v1/mkt/alerts').then(setData).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);
  const create = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      await call('/api/v1/mkt/alerts', 'POST', { ...form, symbol: form.symbol.toUpperCase(), value: Number(form.value) });
      setForm({ ...form, value: '', note: '' }); load();
      if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission().catch(() => {});
    } catch (e2: any) { setErr(e2.message); } finally { setBusy(false); }
  };
  const del = async (id: number) => { await call(`/api/v1/mkt/alerts/${id}`, 'DELETE').catch(() => {}); load(); };
  const check = async () => { setBusy(true); try { await call('/api/v1/mkt/alerts/check', 'POST'); load(); } catch (e: any) { setErr(e.message); } finally { setBusy(false); } };
  return (
    <div className="space-y-3">
      <Panel title="New alert">
        <form onSubmit={create} className="grid grid-cols-2 md:grid-cols-6 gap-2 items-end">
          <label className="text-[10px] uppercase text-text-tertiary">Symbol<input required value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })} className={cn(inp, 'w-full font-mono')} placeholder="AAPL" /></label>
          <label className="text-[10px] uppercase text-text-tertiary col-span-2">Condition
            <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })} className={cn(inp, 'w-full')}>
              {Object.entries(data?.kinds ?? { above: 'Price rises above', below: 'Price falls below', change_up: "Day's gain exceeds %", change_down: "Day's loss exceeds %" })
                .map(([k, l]) => <option key={k} value={k}>{l as string}</option>)}</select></label>
          <label className="text-[10px] uppercase text-text-tertiary">{form.kind.startsWith('change') ? 'Percent' : 'Price'}<input required type="number" step="any" min="0" value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} className={cn(inp, 'w-full font-mono')} /></label>
          <label className="text-[10px] uppercase text-text-tertiary">Note<input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} className={cn(inp, 'w-full')} placeholder="optional" /></label>
          <button disabled={busy} className="px-3 py-1.5 text-xs bg-bloomberg text-text-inverse inline-flex items-center justify-center gap-1 disabled:opacity-50"><Bell className="w-3 h-3" />Create</button>
        </form>
        <div className="text-[10px] text-text-tertiary mt-2">Checked every 5 minutes. A triggered alert pops up in the terminal (and as a browser notification if you allow it) and stays in the list below.</div>
      </Panel>
      <ErrorBox msg={err} />
      <Panel title="Your alerts" right={<button onClick={check} disabled={busy} className="text-2xs text-text-tertiary hover:text-text-primary disabled:opacity-40">Check now</button>}>
        {!data ? <Loading /> : data.alerts.length === 0 ? <div className="text-2xs text-text-tertiary">No alerts yet.</div> : (
          <table className="w-full text-xs"><tbody>{data.alerts.map((a: any) => (
            <tr key={a.id} className="border-t border-border-subtle">
              <td className="py-1.5 font-mono text-text-primary">{a.symbol}</td>
              <td className="text-text-secondary">{a.label} <span className="font-mono text-text-primary">{a.kind.startsWith('change') ? `${a.value}%` : fmtPrice(a.value)}</span>{a.note && <span className="text-text-tertiary"> · {a.note}</span>}</td>
              <td className="text-2xs">{a.active ? <span className="text-green">● watching</span> : <span className="text-amber">triggered {String(a.triggered_at).slice(0, 16).replace('T', ' ')} at {fmtPrice(a.triggered_price)}</span>}</td>
              <td className="text-right"><button onClick={() => del(a.id)} aria-label="Delete alert" className="p-1 text-text-tertiary hover:text-red"><Trash2 className="w-3 h-3" /></button></td>
            </tr>))}</tbody></table>)}
      </Panel>
    </div>
  );
}

/** Polls for triggered alerts while signed in; shows a toast + a browser notification. */
export function AlertToasts({ onOpen }: { onOpen: (s: string) => void }) {
  const [items, setItems] = useState<any[]>([]);
  useEffect(() => {
    let seen = new Set<number>();
    const poll = () => call('/api/v1/mkt/alerts/triggered').then((j) => {
      const fresh = (j.alerts as any[]).filter((a) => !seen.has(a.id));
      fresh.forEach((a) => {
        seen.add(a.id);
        if ('Notification' in window && Notification.permission === 'granted') {
          try { new Notification(`${a.symbol}: ${a.label} ${a.kind.startsWith('change') ? `${a.value}%` : a.value}`, { body: `Triggered at ${a.triggered_price ?? '—'}` }); } catch { /* blocked */ }
        }
      });
      if (j.alerts.length) setItems(j.alerts);
    }).catch(() => {});
    poll();
    const t = setInterval(poll, 60_000);
    return () => { clearInterval(t); seen = new Set(); };
  }, []);
  if (!items.length) return null;
  const dismiss = () => { call('/api/v1/mkt/alerts/seen', 'POST').catch(() => {}); setItems([]); };
  return (
    <div className="fixed bottom-4 right-4 z-50 w-80 bg-surface-1 border border-amber/60 shadow-xl" role="status">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border-subtle"><span className="text-2xs font-semibold text-amber inline-flex items-center gap-1"><Bell className="w-3 h-3" />{items.length} alert{items.length > 1 ? 's' : ''} triggered</span>
        <button onClick={dismiss} aria-label="Dismiss" className="text-text-tertiary hover:text-text-primary"><X className="w-3.5 h-3.5" /></button></div>
      <ul className="max-h-48 overflow-y-auto">{items.map((a) => (
        <li key={a.id}><button onClick={() => onOpen(a.symbol)} className="w-full text-left px-3 py-1.5 text-2xs hover:bg-surface-3">
          <span className="font-mono text-text-primary">{a.symbol}</span> <span className="text-text-secondary">{a.label} {a.kind.startsWith('change') ? `${a.value}%` : fmtPrice(a.value)}</span>
          <span className="text-text-tertiary"> · at {fmtPrice(a.triggered_price)}</span></button></li>))}</ul>
    </div>
  );
}

// ── JRNL ─────────────────────────────────────────────────────────────────────
const blank = { date: new Date().toISOString().slice(0, 10), symbol: '', side: 'long', quantity: '', entry: '', exit: '', thesis: '', outcome: '', tags: '' };

export function JournalView({ seed, onOpen }: { seed?: string; onOpen: (s: string) => void }) {
  const [data, setData] = useState<any>(null);
  const [form, setForm] = useState<any>({ ...blank, symbol: seed ?? '' });
  const [editing, setEditing] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => call('/api/v1/mkt/journal').then(setData).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    const body = { ...form, tags: String(form.tags || '').split(',').map((t: string) => t.trim()).filter(Boolean),
      quantity: form.quantity === '' ? null : Number(form.quantity), entry: form.entry === '' ? null : Number(form.entry), exit: form.exit === '' ? null : Number(form.exit) };
    try {
      if (editing) await call(`/api/v1/mkt/journal/${editing}`, 'PUT', body); else await call('/api/v1/mkt/journal', 'POST', body);
      setForm({ ...blank }); setEditing(null); load();
    } catch (e2: any) { setErr(e2.message); }
  };
  const edit = (r: any) => { setEditing(r.id); setForm({ ...r, quantity: r.quantity ?? '', entry: r.entry ?? '', exit: r.exit ?? '', tags: (r.tags ?? []).join(', '), thesis: r.thesis ?? '', outcome: r.outcome ?? '' }); window.scrollTo({ top: 0, behavior: 'smooth' }); };
  const del = async (id: number) => { if (window.confirm('Delete this journal entry?')) { await call(`/api/v1/mkt/journal/${id}`, 'DELETE').catch(() => {}); load(); } };
  const st = data?.stats;
  return (
    <div className="space-y-3">
      {st && <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        {[['Entries', st.entries], ['Open', st.open], ['Win rate', st.win_rate != null ? fmtPct(st.win_rate, 0).replace('+', '') : '—'],
          ['Average result', st.avg_return != null ? fmtPct(st.avg_return, 1) : '—'], ['Avg win / loss', st.avg_win != null ? `${fmtPct(st.avg_win, 1)} / ${st.avg_loss != null ? fmtPct(st.avg_loss, 1) : '—'}` : '—']]
          .map(([k, v]) => <div key={k as string} className="px-3 py-2 bg-surface-1 border border-border"><div className="text-[10px] uppercase text-text-tertiary">{k}</div><div className="font-mono text-sm">{v as any}</div></div>)}
      </div>}
      <Panel title={editing ? 'Edit entry' : 'New entry'}>
        <form onSubmit={submit} className="space-y-2">
          <div className="grid grid-cols-2 md:grid-cols-7 gap-2">
            <input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} className={inp} aria-label="Date" />
            <input value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })} placeholder="Symbol" className={cn(inp, 'font-mono')} aria-label="Symbol" />
            <select value={form.side} onChange={(e) => setForm({ ...form, side: e.target.value })} className={inp} aria-label="Side"><option value="long">Long</option><option value="short">Short</option><option value="idea">Idea only</option></select>
            <input type="number" step="any" min="0" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} placeholder="Quantity" className={cn(inp, 'font-mono')} aria-label="Quantity" />
            <input type="number" step="any" min="0" value={form.entry} onChange={(e) => setForm({ ...form, entry: e.target.value })} placeholder="Entry price" className={cn(inp, 'font-mono')} aria-label="Entry price" />
            <input type="number" step="any" min="0" value={form.exit} onChange={(e) => setForm({ ...form, exit: e.target.value })} placeholder="Exit price (closes it)" className={cn(inp, 'font-mono')} aria-label="Exit price" />
            <input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} placeholder="Tags, e.g. momentum, earnings" className={inp} aria-label="Tags" />
          </div>
          <textarea value={form.thesis} onChange={(e) => setForm({ ...form, thesis: e.target.value })} rows={2} placeholder="Thesis — why this trade? What would prove you wrong?" className={cn(inp, 'w-full')} aria-label="Thesis" />
          <textarea value={form.outcome} onChange={(e) => setForm({ ...form, outcome: e.target.value })} rows={2} placeholder="Outcome & lessons (after closing)" className={cn(inp, 'w-full')} aria-label="Outcome" />
          <div className="flex gap-2"><button className="px-3 py-1.5 text-xs bg-bloomberg text-text-inverse">{editing ? 'Save changes' : 'Add to journal'}</button>
            {editing && <button type="button" onClick={() => { setEditing(null); setForm({ ...blank }); }} className="px-3 py-1.5 text-xs border border-border">Cancel</button>}</div>
        </form>
      </Panel>
      <ErrorBox msg={err} />
      {!data ? <Loading /> : data.entries.length === 0 ? <Panel><div className="text-2xs text-text-tertiary">No entries yet. Writing down why you take a trade — and reviewing it later — is one of the most reliable ways to improve.</div></Panel> : (
        <div className="space-y-2">{data.entries.map((r: any) => (
          <div key={r.id} className="p-3 bg-surface-1 border border-border">
            <div className="flex flex-wrap items-center gap-2 text-2xs">
              <span className="font-mono text-text-tertiary">{r.date}</span>
              {r.symbol && <button onClick={() => onOpen(r.symbol)} className="font-mono text-text-primary hover:text-bloomberg">{r.symbol}</button>}
              <span className={cn('px-1.5 border uppercase text-[10px]', r.side === 'long' ? 'border-green/50 text-green' : r.side === 'short' ? 'border-red/50 text-red' : 'border-border text-text-tertiary')}>{r.side}</span>
              {r.entry != null && <span className="text-text-secondary font-mono">{r.quantity ? `${r.quantity} @ ` : '@ '}{fmtPrice(r.entry)}{r.exit != null && <> → {fmtPrice(r.exit)}</>}</span>}
              {r.return_pct != null && <Chg v={r.return_pct} d={1} />}
              {r.pnl != null && <span className={cn('font-mono', r.pnl >= 0 ? 'text-green' : 'text-red')}>{r.pnl >= 0 ? '+' : ''}{r.pnl.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>}
              <span className={cn('text-[10px]', r.status === 'open' ? 'text-amber' : 'text-text-tertiary')}>{r.status}</span>
              {r.tags.map((t: string) => <span key={t} className="px-1.5 bg-surface-3 text-text-secondary text-[10px]">{t}</span>)}
              <span className="ml-auto flex gap-2"><button onClick={() => edit(r)} className="text-text-tertiary hover:text-text-primary">Edit</button><button onClick={() => del(r.id)} className="text-text-tertiary hover:text-red">Delete</button></span>
            </div>
            {r.thesis && <p className="mt-1.5 text-xs text-text-primary whitespace-pre-line">{r.thesis}</p>}
            {r.outcome && <p className="mt-1 text-xs text-text-secondary whitespace-pre-line"><span className="text-text-tertiary">Outcome: </span>{r.outcome}</p>}
          </div>))}</div>
      )}
    </div>
  );
}
