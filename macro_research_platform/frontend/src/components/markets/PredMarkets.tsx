// PRED: prediction markets — every open event on Kalshi and Polymarket, searchable, with price
// history, the live order book, today's movers, the same question on both venues, and the macro
// questions (the next Fed decision vs fed funds futures). Read-only market data.
import { Fragment, useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { ErrorBox, Loading, Panel, useJSON } from './shared';
import { useFollow } from './follow';

const P = (v: number | null | undefined) => (v == null ? '—' : `${(v * 100).toFixed(v < 0.01 || v > 0.99 ? 1 : 0)}%`);
const PT = (v: number | null | undefined) => (v == null || Math.abs(v) < 0.005 ? '' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(0)}pt`);
const tone = (v: number | null | undefined) => (v == null ? 'text-text-tertiary' : v >= 0 ? 'text-green' : 'text-red');
const big = (v: number | null | undefined) => (v == null ? '—' : v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(0)}k` : Math.round(v).toString());
const VENUE: Record<string, string> = { Kalshi: 'text-[rgb(16_185_129)] border-[rgb(16_185_129)]/40', Polymarket: 'text-[rgb(59_130_246)] border-[rgb(59_130_246)]/40' };
const vol = (venue: string, v: number) => (venue === 'Polymarket' ? `$${big(v)}` : `${big(v)} ct`);

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button onClick={onClick} className={cn('px-2 py-0.5 border rounded-sm', on ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary hover:text-text-primary')}>{children}</button>;
}
const Venue = ({ v }: { v: string }) => <span className={cn('text-[9px] uppercase tracking-wide border px-1 rounded-sm', VENUE[v])}>{v}</span>;

type Open = { venue: string; id: string } | null;

export function PredView() {
  const [tab, setTab] = useState<'browse' | 'movers' | 'cross' | 'arb' | 'macro' | 'follow'>('browse');
  const [open, setOpen] = useState<Open>(() => {
    try {
      const h = JSON.parse(sessionStorage.getItem('pred_open') || 'null');
      sessionStorage.removeItem('pred_open');
      return h ? { venue: h.venue, id: h.id } : null;
    } catch { return null; }
  });
  const fol = useFollow('pred');
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1 text-[11px]">
        {([['browse', 'All markets'], ['movers', 'Movers'], ['cross', 'Kalshi vs Polymarket'], ['arb', 'Arbitrage'], ['macro', 'Macro & Fed'], ['follow', `Following (${fol.list.length})`]] as const).map(([k, l]) =>
          <Chip key={k} on={tab === k} onClick={() => setTab(k)}>{l}</Chip>)}
        <span className="ml-auto text-text-tertiary">Read-only: odds, volume and order books — no trading.</span>
      </div>
      <div className={cn('grid gap-3', open ? 'grid-cols-1 2xl:grid-cols-[minmax(0,1fr)_560px]' : 'grid-cols-1')}>
        <div className="min-w-0">
          {tab === 'browse' && <Browse onOpen={setOpen} />}
          {tab === 'movers' && <Movers onOpen={setOpen} />}
          {tab === 'cross' && <Cross onOpen={setOpen} />}
          {tab === 'arb' && <Arb />}
          {tab === 'macro' && <Macro onOpen={setOpen} />}
          {tab === 'follow' && <Following onOpen={setOpen} />}
        </div>
        {open && <EventDetail key={`${open.venue}:${open.id}`} venue={open.venue} id={open.id} onClose={() => setOpen(null)} />}
      </div>
    </div>
  );
}

// ── Browse ──────────────────────────────────────────────────────────────────
function Browse({ onOpen }: { onOpen: (o: Open) => void }) {
  const [q, setQ] = useState('');
  const [dq, setDq] = useState('');
  const [venue, setVenue] = useState('');
  const [cat, setCat] = useState('');
  const [sort, setSort] = useState('volume');
  const [n, setN] = useState(60);
  const [active, setActive] = useState(true);
  useEffect(() => { const t = setTimeout(() => setDq(q), 300); return () => clearTimeout(t); }, [q]);
  useEffect(() => setN(60), [dq, venue, cat, sort, active]);
  const url = `/api/v1/mkt/pred/browse?q=${encodeURIComponent(dq)}&venue=${venue}&category=${encodeURIComponent(cat)}&sort=${sort}&limit=${n}&active=${active}&sports=${cat === 'Sports'}`;
  const { data: d, error, loading } = useJSON<any>(url, 300_000);
  return (
    <div className="space-y-2">
      {d && <div className="grid grid-cols-2 md:grid-cols-4 gap-1.5">
        {Object.entries<any>(d.venues).flatMap(([v, s]) => [
          [`${v} — open events`, `${s.events.toLocaleString()}`, `${s.markets.toLocaleString()} outcomes`],
          [`${v} — 24h volume`, vol(v, s.volume_24h), v === 'Polymarket' ? 'USDC' : 'contracts ($1 each)']]).map(([k, val, sub]) => (
          <div key={k} className="border border-border bg-surface-1 px-2.5 py-1.5"><div className="text-[10px] uppercase tracking-wide text-text-tertiary">{k}</div>
            <div className="font-mono text-text-primary">{val}</div><div className="text-[10px] text-text-tertiary">{sub}</div></div>))}
      </div>}
      <div className="flex flex-wrap items-center gap-1 text-[11px]">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search every market — Fed, CPI, recession, oil, Taiwan, election…"
          className="w-80 bg-surface-1 border border-border px-2 py-0.5 text-text-primary" />
        {[['', 'Both venues'], ['Kalshi', 'Kalshi'], ['Polymarket', 'Polymarket']].map(([k, l]) => <Chip key={l} on={venue === k} onClick={() => setVenue(k)}>{l}</Chip>)}
        <Chip on={active} onClick={() => setActive(!active)}>Actively traded only</Chip>
        <select value={sort} onChange={(e) => setSort(e.target.value)} className="ml-auto bg-surface-1 border border-border px-1 py-0.5 text-text-primary">
          <option value="volume">Most traded (24h)</option><option value="total">Most traded (all time)</option><option value="liquidity">Most liquid</option>
          <option value="moving">Biggest move today</option><option value="ending">Resolving soonest</option>
        </select>
      </div>
      {d && <div className="flex flex-wrap gap-1 text-[11px]"><Chip on={cat === ''} onClick={() => setCat('')}>All</Chip>
        {d.categories.map(([c, k]: [string, number]) => <Chip key={c} on={cat === c} onClick={() => setCat(c)}>{c} <span className="text-text-tertiary">{k}</span></Chip>)}</div>}
      {error && !d ? <ErrorBox msg={error} /> : !d ? <Loading label="Loading every open market on Kalshi and Polymarket (first load ~15 s)…" /> : (
        <>
          <div className="text-[10px] text-text-tertiary">{d.total.toLocaleString()} events{loading ? ' · updating…' : ''}</div>
          <div className="grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-2">
            {d.events.map((e: any) => <EventCard key={`${e.venue}${e.id}`} e={e} onOpen={onOpen} />)}
          </div>
          {d.total > d.events.length && <button onClick={() => setN(n + 60)} className="w-full border border-border py-1 text-[11px] text-text-secondary hover:text-text-primary">Show more ({(d.total - d.events.length).toLocaleString()} left)</button>}
          <div className="text-[10px] text-text-tertiary">Kalshi prices use the bid/ask midpoint when the quote is within 6¢, otherwise the last trade. Faded “thin” outcomes have a spread over 10¢ or under 100 traded today — treat their odds as indicative. {d.note} Source: {d.source}. As of {d.as_of?.replace('T', ' ')} UTC.</div>
        </>)}
    </div>
  );
}

function EventCard({ e, onOpen }: { e: any; onOpen: (o: Open) => void }) {
  return (
    <button onClick={() => onOpen({ venue: e.venue, id: e.id })} className="text-left border border-border bg-surface-1 rounded-md p-2.5 hover:bg-surface-2 transition-colors">
      <div className="flex justify-between gap-2 items-start"><span className="text-xs font-semibold text-text-primary">{e.title}</span><Venue v={e.venue} /></div>
      <div className="text-[10px] text-text-tertiary mb-1">{e.category} · 24h {vol(e.venue, e.volume_24h)}{e.end ? ` · closes ${e.end}` : ''}{e.n_markets > 4 ? ` · ${e.n_markets} outcomes` : ''}</div>
      {e.markets.map((m: any) => <OutcomeRow key={m.id} m={m} />)}
    </button>
  );
}

function OutcomeRow({ m }: { m: any }) {
  const multi = !m.binary && m.outcomes?.length > 2;
  return (
    <div className={cn('flex items-center gap-2 text-[11px] py-0.5', m.thin && 'opacity-60')}
      title={m.thin ? 'Thin market: wide spread or little trading — the price may be stale' : m.spread != null ? `Spread ${(m.spread * 100).toFixed(1)}¢` : undefined}>
      <span className="flex-1 min-w-0 truncate text-text-secondary">{m.label}{m.thin && <span className="ml-1 text-[9px] text-amber">thin</span>}</span>
      {multi ? <span className="font-mono text-text-primary">{m.outcomes.map((o: any) => `${o.name} ${P(o.price)}`).join(' · ')}</span> : <>
        <span className="w-20 h-1.5 bg-surface-3 rounded-full overflow-hidden"><span className="block h-full bg-bloomberg" style={{ width: `${m.yes * 100}%` }} /></span>
        <span className="w-11 text-right font-mono text-text-primary">{P(m.yes)}</span>
        <span className={cn('w-10 text-right font-mono', tone(m.chg_1d))}>{PT(m.chg_1d)}</span></>}
    </div>
  );
}

// ── One event: outcomes, history, order book, rules ─────────────────────────
function EventDetail({ venue, id, onClose }: { venue: string; id: string; onClose: () => void }) {
  const { data: e, error } = useJSON<any>(`/api/v1/mkt/pred/event/${venue}/${encodeURIComponent(id)}`, 300_000);
  const [sel, setSel] = useState<string | null>(null);
  const [span, setSpan] = useState('1m');
  const fol = useFollow('pred');
  const key = `${venue}:${id}`;
  const m = e?.markets?.find((x: any) => x.id === sel) ?? e?.markets?.[0];
  const hist = useJSON<any>(m ? `/api/v1/mkt/pred/history/${venue}/${encodeURIComponent(m.id)}?series=${m.series ?? ''}&span=${span}` : null, 300_000);
  const book = useJSON<any>(m ? `/api/v1/mkt/pred/book/${venue}/${encodeURIComponent(m.id)}` : null, 30_000);
  return (
    <Panel title={e ? e.title : 'Loading…'} className="self-start 2xl:sticky 2xl:top-2" right={<div className="flex gap-1 text-[11px]">
      {e && <button onClick={() => fol.toggle(key, e.title, `${venue} · ${e.category}`)} className={cn('px-2 border', fol.isFollowed(key) ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>{fol.isFollowed(key) ? '★ Following' : '☆ Follow'}</button>}
      <button onClick={onClose} className="px-2 border border-border text-text-secondary">✕</button></div>}>
      {error && !e ? <ErrorBox msg={error} /> : !e ? <Loading /> : (
        <div className="space-y-3 text-[11px]">
          <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-text-tertiary"><Venue v={venue} /><span>{e.category}</span>
            <span>24h {vol(venue, e.volume_24h)}</span><span>total {vol(venue, e.volume)}</span>
            {e.open_interest ? <span>open interest {vol(venue, e.open_interest)}</span> : null}{e.end && <span>closes {e.end}</span>}</div>
          <div className="max-h-56 overflow-auto border border-border-subtle">
            <table className="w-full font-mono"><thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary">
              <th className="text-left font-normal px-1">Outcome</th><th className="text-right font-normal">Yes</th><th className="text-right font-normal">Bid</th><th className="text-right font-normal">Ask</th><th className="text-right font-normal">Spread</th><th className="text-right font-normal">24h</th><th className="text-right font-normal px-1">Vol 24h</th></tr></thead>
              <tbody>{e.markets.map((x: any) => (
                <tr key={x.id} onClick={() => setSel(x.id)} className={cn('border-t border-border-subtle cursor-pointer hover:bg-surface-2', x.id === m?.id && 'bg-bloomberg/10')}>
                  <td className="px-1 py-0.5 font-sans text-text-primary truncate max-w-[220px]" title={x.question}>{x.binary ? x.label : x.outcomes.map((o: any) => o.name).join(' / ')}</td>
                  <td className="text-right">{x.binary ? P(x.yes) : x.outcomes.map((o: any) => P(o.price)).join(' / ')}</td>
                  <td className="text-right text-text-secondary">{P(x.bid)}</td><td className="text-right text-text-secondary">{P(x.ask)}</td>
                  <td className={cn('text-right', x.thin ? 'text-amber' : 'text-text-tertiary')}>{x.spread != null ? `${(x.spread * 100).toFixed(1)}¢` : '—'}</td>
                  <td className={cn('text-right', tone(x.chg_1d))}>{PT(x.chg_1d)}</td><td className="text-right px-1">{big(x.volume_24h)}</td></tr>))}</tbody></table>
          </div>
          {m && <>
            <div className="flex items-center gap-1"><span className="font-semibold text-text-primary truncate flex-1">{m.question || m.label}</span>
              {['1d', '1w', '1m', 'max'].map((s) => <Chip key={s} on={span === s} onClick={() => setSpan(s)}>{s.toUpperCase()}</Chip>)}</div>
            {hist.error && !hist.data ? <ErrorBox msg={hist.error} /> : !hist.data ? <Loading label="Loading price history…" /> :
              <LineChart rows={hist.data.rows} x="date" height={200} controls={false} fmt={(v) => `${v.toFixed(1)}%`} refs={[{ value: 50, label: '50%' }]}
                lines={[{ key: 'p', label: `${m.binary ? m.label || 'Yes' : m.outcomes?.[0]?.name} — probability`, color: 'rgb(var(--c-bloomberg))' }]} />}
            <Book b={book.data} err={book.error} />
          </>}
          {(m?.rules || e.description) && <details><summary className="cursor-pointer text-text-secondary">Resolution rules</summary>
            <p className="mt-1 text-text-tertiary whitespace-pre-wrap">{m?.rules || e.description}</p></details>}
        </div>)}
    </Panel>
  );
}

function Book({ b, err }: { b: any; err: string | null }) {
  if (err && !b) return <ErrorBox msg={err} />;
  if (!b) return <Loading label="Loading order book…" />;
  const rows = Math.min(10, Math.max(b.bids.length, b.asks.length));
  const max = Math.max(1, ...b.bids.slice(0, 10).map((x: any) => x.size), ...b.asks.slice(0, 10).map((x: any) => x.size));
  if (!rows) return <div className="text-text-tertiary">The order book is empty.</div>;
  const spread = b.best_bid != null && b.best_ask != null ? b.best_ask - b.best_bid : null;
  return (
    <div>
      <div className="flex justify-between text-text-tertiary mb-0.5"><span>Order book (Yes) — size in {b.unit}</span><span>spread {spread != null ? `${(spread * 100).toFixed(1)}¢` : '—'}</span></div>
      <div className="grid grid-cols-2 gap-1 font-mono">
        {[['Bids', b.bids, 'bg-green/20', 'text-green'], ['Asks', b.asks, 'bg-red/20', 'text-red']].map(([name, side, bg, fg]: any) => (
          <div key={name}><div className="text-text-tertiary">{name}</div>
            {side.slice(0, 10).map((x: any, i: number) => (
              <div key={i} className="relative flex justify-between px-1">
                <span className={cn('absolute inset-y-0 left-0', bg)} style={{ width: `${(x.size / max) * 100}%` }} />
                <span className={cn('relative', fg)}>{(x.price * 100).toFixed(1)}¢</span><span className="relative">{big(x.size)}</span></div>))}</div>))}
      </div>
    </div>
  );
}

// ── Movers ──────────────────────────────────────────────────────────────────
function Movers({ onOpen }: { onOpen: (o: Open) => void }) {
  const [sports, setSports] = useState(false);
  const { data: d, error } = useJSON<any>(`/api/v1/mkt/pred/movers?sports=${sports}`, 300_000);
  if (error && !d) return <ErrorBox msg={error} />;
  if (!d) return <Loading label="Finding today's biggest moves…" />;
  return (
    <Panel title="Biggest 24-hour moves" right={<label className="text-[11px] text-text-secondary"><input type="checkbox" checked={sports} onChange={(e) => setSports(e.target.checked)} /> include live sports</label>}>
      <table className="w-full text-[11px] font-mono">
        <thead><tr className="text-text-tertiary"><th className="text-left font-normal">Event</th><th className="text-left font-normal">Outcome</th><th className="text-right font-normal">Now</th><th className="text-right font-normal">24h</th><th className="text-right font-normal">Vol 24h</th><th className="text-right font-normal">Closes</th></tr></thead>
        <tbody>{d.rows.map((r: any, i: number) => (
          <tr key={i} onClick={() => onOpen({ venue: r.venue, id: r.event_id })} className="border-t border-border-subtle cursor-pointer hover:bg-surface-2">
            <td className="py-0.5 font-sans text-text-primary max-w-[340px] truncate"><Venue v={r.venue} /> {r.event}</td>
            <td className="font-sans text-text-secondary max-w-[200px] truncate">{r.label}</td><td className="text-right">{P(r.yes)}</td>
            <td className={cn('text-right', tone(r.chg_1d))}>{PT(r.chg_1d)}</td><td className="text-right">{vol(r.venue, r.volume_24h)}</td><td className="text-right text-text-tertiary">{r.end}</td></tr>))}</tbody>
      </table>
      <div className="text-[10px] text-text-tertiary mt-1">{d.note}</div>
    </Panel>
  );
}

// ── Same question on both venues ────────────────────────────────────────────
function Cross({ onOpen }: { onOpen: (o: Open) => void }) {
  const { data: d, error } = useJSON<any>('/api/v1/mkt/pred/cross', 300_000);
  if (error && !d) return <ErrorBox msg={error} />;
  if (!d) return <Loading label="Matching events across Kalshi and Polymarket…" />;
  return (
    <div className="space-y-2">
      <div className="text-[10px] text-text-tertiary">{d.note}</div>
      {!d.pairs.length && <div className="text-text-tertiary text-[11px]">No overlapping questions right now.</div>}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-2">{d.pairs.map((p: any, i: number) => (
        <div key={i} className="border border-border bg-surface-1 rounded-md p-2.5 text-[11px]">
          <div className="grid grid-cols-2 gap-2 mb-1">
            <button onClick={() => onOpen({ venue: 'Polymarket', id: p.poly.id })} className="text-left hover:underline"><Venue v="Polymarket" /> <span className="text-text-primary">{p.poly.title}</span></button>
            <button onClick={() => onOpen({ venue: 'Kalshi', id: p.kalshi.id })} className="text-left hover:underline"><Venue v="Kalshi" /> <span className="text-text-primary">{p.kalshi.title}</span></button>
          </div>
          <table className="w-full font-mono"><thead><tr className="text-text-tertiary"><th className="text-left font-normal">Outcome</th><th className="text-right font-normal">Poly</th><th className="text-right font-normal">Kalshi</th><th className="text-right font-normal">Gap</th></tr></thead>
            <tbody>{p.outcomes.map((o: any, j: number) => (
              <tr key={j} className="border-t border-border-subtle"><td className="font-sans text-text-secondary truncate max-w-[220px]">{o.label}</td>
                <td className="text-right">{P(o.poly)}</td><td className="text-right">{P(o.kalshi)}</td>
                <td className={cn('text-right', Math.abs(o.gap) >= 0.05 ? 'text-amber font-semibold' : 'text-text-tertiary')}>{PT(o.gap) || '0'}</td></tr>))}</tbody></table>
        </div>))}</div>
    </div>
  );
}

// ── Cross-venue arbitrage ───────────────────────────────────────────────────
const C = (v: number | null | undefined) => (v == null ? '—' : `${(v * 100).toFixed(1)}¢`);
const usd0 = (v: number | null | undefined) => (v == null ? '—' : `$${Math.round(v).toLocaleString()}`);
const DIR: Record<string, string> = { poly_yes_kalshi_no: 'YES Polymarket + NO Kalshi', kalshi_yes_poly_no: 'YES Kalshi + NO Polymarket' };

function Arb() {
  const [kFee, setKFee] = useState(0.07);
  const [pFee, setPFee] = useState(0);
  const [onlyPos, setOnlyPos] = useState(true);
  const [sel, setSel] = useState<number | null>(null);
  const { data: d, error } = useJSON<any>(`/api/v1/mkt/pred/arb?kalshi_fee=${kFee}&poly_fee=${pFee}`, 120_000);
  const rows = (d?.rows ?? []).filter((r: any) => !onlyPos || r.edge > 0);
  return (
    <div className="space-y-2">
      <Panel title="Polymarket ↔ Kalshi arbitrage" right={
        <div className="flex items-center gap-3 text-[11px] text-text-secondary">
          <label>Kalshi fee rate <input type="number" step={0.005} min={0} max={0.2} value={kFee} onChange={(e) => setKFee(Number(e.target.value))} className="w-16 bg-surface-1 border border-border px-1 font-mono" /></label>
          <label>Polymarket fee <input type="number" step={0.001} min={0} max={0.1} value={pFee} onChange={(e) => setPFee(Number(e.target.value))} className="w-16 bg-surface-1 border border-border px-1 font-mono" /></label>
          <label><input type="checkbox" checked={onlyPos} onChange={(e) => setOnlyPos(e.target.checked)} /> positive edge only</label>
        </div>}>
        <div className="text-[10px] text-text-tertiary mb-2 leading-relaxed">
          Buy YES on one venue and NO on the other: one of them pays $1. If both cost less than $1 after fees, the difference is locked in —
          <b className="text-text-secondary"> provided both venues resolve the question the same way</b>. Kalshi's taker fee is ⌈rate × contracts × P × (1−P)⌉; most Polymarket markets charge none.
        </div>
        {error && !d && <ErrorBox msg={error} />}
        {!d && !error && <Loading label="Matching questions across both venues and reading their order books…" />}
        {d && (
          <>
            <div className="text-[11px] text-text-secondary mb-1">{d.matched_questions} questions matched · {d.arbs} with size available at a positive edge after fees · as of {d.as_of}</div>
            <div className="overflow-x-auto">
              <table className="w-full text-[11px] font-mono">
                <thead><tr className="text-text-tertiary">
                  {['Question', 'Trade', 'YES', 'NO', 'Edge/ct', 'Size', 'Profit', 'Ann.', 'vs UST', 'Closes', ''].map((h) => <th key={h} className={cn('font-normal px-1.5 whitespace-nowrap', h === 'Question' || h === 'Trade' ? 'text-left' : 'text-right')}>{h}</th>)}
                </tr></thead>
                <tbody>{rows.map((r: any, i: number) => {
                  const x = r.executable;
                  const beats = r.annualized != null && r.treasury_yield != null ? r.annualized > r.treasury_yield : null;
                  return (<Fragment key={i}>
                    <tr onClick={() => setSel(sel === i ? null : i)} className={cn('border-t border-border-subtle cursor-pointer hover:bg-surface-2', sel === i && 'bg-surface-2')}>
                      <td className="py-0.5 pr-1.5 font-sans text-text-primary max-w-[320px] truncate" title={r.poly_question}>{r.poly_question}</td>
                      <td className="px-1.5 font-sans text-text-secondary whitespace-nowrap">{DIR[r.dir]}</td>
                      <td className="px-1.5 whitespace-nowrap text-right">{C(r.yes_price)}</td><td className="px-1.5 whitespace-nowrap text-right">{C(r.no_price)}</td>
                      <td className={cn('px-1.5 whitespace-nowrap text-right', r.edge > 0 ? 'text-green' : 'text-text-tertiary')}>{C(x?.edge_per_contract ?? r.edge)}</td>
                      <td className="px-1.5 whitespace-nowrap text-right">{x?.contracts ? big(x.contracts) : '—'}</td>
                      <td className={cn('px-1.5 whitespace-nowrap text-right', (x?.profit ?? 0) > 0 && 'text-green')}>{x?.contracts ? usd0(x.profit) : '—'}</td>
                      <td className="px-1.5 whitespace-nowrap text-right">{r.annualized == null ? '—' : `${(r.annualized * 100).toFixed(1)}%`}</td>
                      <td className={cn('px-1.5 whitespace-nowrap text-right', beats == null ? 'text-text-tertiary' : beats ? 'text-green' : 'text-amber')}>{r.treasury_yield == null ? '—' : `${(r.treasury_yield * 100).toFixed(1)}%`}</td>
                      <td className="px-1.5 whitespace-nowrap text-right text-text-tertiary">{r.end}</td>
                      <td className="px-1.5 whitespace-nowrap text-right">{r.flags.length ? <span className="text-amber" title={r.flags.join('\n')}>⚠ {r.flags.length}</span> : ''}</td>
                    </tr>
                    {sel === i && <tr><td colSpan={11} className="font-sans"><ArbDetail r={r} /></td></tr>}
                  </Fragment>);
                })}</tbody>
              </table>
            </div>
            {!rows.length && <div className="text-[11px] text-text-tertiary py-2">No positive-edge pairs right now — the venues are in line after fees.</div>}
            <div className="text-[10px] text-text-tertiary mt-2">{d.note}</div>
          </>
        )}
      </Panel>
      <ArbCheck kFee={kFee} pFee={pFee} />
    </div>
  );
}

function ArbDetail({ r }: { r: any }) {
  const x = r.executable;
  return (
    <div className="mt-2 border border-border bg-surface-1 p-2 text-[11px] space-y-2">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
        <div><Venue v="Polymarket" /> <span className="text-text-primary">{r.poly_question}</span>
          <div className="text-text-tertiary">Event: {r.poly_event} · YES {P(r.poly_yes)}</div>
          {r.poly_slug && <a className="text-bloomberg underline" href={`https://polymarket.com/event/${r.poly_slug}`} target="_blank" rel="noreferrer">Open on Polymarket ↗</a>}
          <div className="mt-1 text-[10px] text-text-secondary whitespace-pre-wrap max-h-32 overflow-auto">{r.poly_rules || 'No rules text.'}</div></div>
        <div><Venue v="Kalshi" /> <span className="text-text-primary">{r.kalshi_question}</span>
          <div className="text-text-tertiary">Ticker {r.kalshi_ticker} · YES {P(r.kalshi_yes)}</div>
          {r.kalshi_series && <a className="text-bloomberg underline" href={`https://kalshi.com/markets/${String(r.kalshi_series).toLowerCase()}`} target="_blank" rel="noreferrer">Open on Kalshi ↗</a>}
          <div className="mt-1 text-[10px] text-text-secondary whitespace-pre-wrap max-h-32 overflow-auto">{r.kalshi_rules || 'No rules text.'}</div></div>
      </div>
      <div className="font-mono">
        {DIR[r.dir]}: {C(r.yes_price)} + {C(r.no_price)} at the touch, cost incl. fees {C(r.cost)} → edge {C(r.edge)} per $1 contract.
        {x?.contracts ? ` Walking both books: ${big(x.contracts)} contracts for ${usd0(x.outlay)} (fees ${usd0(x.fees)}) → ${usd0(x.profit)} locked if both resolve alike.` : x?.error ? ` Order books unavailable: ${x.error}` : ' No size at a positive edge once the books are walked.'}
        {' '}Match: {r.match_how === 'fed' ? 'Fed decision (meeting + bps)' : `wording ${(r.match * 100).toFixed(0)}%`}.
      </div>
      {r.flags.length > 0 && <ul className="list-disc pl-4 text-amber">{r.flags.map((f: string) => <li key={f}>{f}</li>)}</ul>}
    </div>
  );
}

function ArbCheck({ kFee, pFee }: { kFee: number; pFee: number }) {
  const [poly, setPoly] = useState('');
  const [kal, setKal] = useState('');
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true); setErr(null); setRes(null);
    try {
      const r = await fetch(`/api/v1/mkt/pred/arb/check?poly=${encodeURIComponent(poly)}&kalshi=${encodeURIComponent(kal)}&kalshi_fee=${kFee}&poly_fee=${pFee}`);
      const j = await r.json();
      if (!r.ok) throw new Error(j?.detail || `HTTP ${r.status}`);
      setRes(j);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <Panel title="Check a pair yourself">
      <div className="flex flex-wrap items-end gap-2 text-[11px]">
        <label className="flex-1 min-w-[260px]"><span className="block text-text-tertiary">Polymarket question URL / slug</span>
          <input value={poly} onChange={(e) => setPoly(e.target.value)} placeholder="https://polymarket.com/event/…/will-…" className="w-full bg-surface-1 border border-border px-2 py-1 font-mono" /></label>
        <label className="w-64"><span className="block text-text-tertiary">Kalshi market ticker</span>
          <input value={kal} onChange={(e) => setKal(e.target.value.toUpperCase())} placeholder="KXFEDDECISION-26OCT-H0" className="w-full bg-surface-1 border border-border px-2 py-1 font-mono" /></label>
        <button onClick={run} disabled={busy || !poly || !kal} className="px-3 py-1 bg-bloomberg text-bg disabled:opacity-50">{busy ? 'Checking…' : 'Check'}</button>
      </div>
      {err && <div className="mt-2"><ErrorBox msg={err} /></div>}
      {res && (
        <div className="mt-2 text-[11px] space-y-1">
          <div><Venue v="Polymarket" /> {res.poly.question} — bid {C(res.poly.bid)} / ask {C(res.poly.ask)} · closes {res.poly.end}</div>
          <div><Venue v="Kalshi" /> {res.kalshi.question} — bid {C(res.kalshi.bid)} / ask {C(res.kalshi.ask)} · closes {res.kalshi.end}</div>
          <table className="w-full font-mono"><tbody>{res.directions.map((d: any) => (
            <tr key={d.dir} className="border-t border-border-subtle">
              <td className="font-sans text-text-secondary">{DIR[d.dir]}</td><td className="text-right">{C(d.yes_price)} + {C(d.no_price)}</td>
              <td className={cn('text-right', d.edge > 0 ? 'text-green' : 'text-text-tertiary')}>edge {C(d.edge)}</td>
              <td className="text-right">{d.executable?.contracts ? `${big(d.executable.contracts)} ct → ${usd0(d.executable.profit)}` : 'no size'}</td></tr>))}</tbody></table>
          <div className="text-[10px] text-text-tertiary">Read both rules texts before trading — same words can settle on different sources or times.</div>
        </div>
      )}
    </Panel>
  );
}

// ── Macro & Fed ─────────────────────────────────────────────────────────────
function Macro({ onOpen }: { onOpen: (o: Open) => void }) {
  const { data: d, error } = useJSON<any>('/api/v1/mkt/pred/macro', 300_000);
  if (error && !d) return <ErrorBox msg={error} />;
  if (!d) return <Loading label="Loading Fed and macro markets…" />;
  const f = d.fed;
  const lab = (bp: number) => (bp === 0 ? 'Hold' : bp > 0 ? `Hike ${bp}bp${bp >= 50 ? '+' : ''}` : `Cut ${-bp}bp${bp <= -50 ? '+' : ''}`);
  return (
    <div className="space-y-3">
      <Panel title={`Next Fed decision — ${f.futures?.meeting ?? f.polymarket_event ?? ''}: crowds vs the rates market`}>
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_260px] gap-3 text-[11px]">
          <table className="w-full font-mono"><thead><tr className="text-text-tertiary"><th className="text-left font-normal">Outcome</th>
            <th className="text-right font-normal">Polymarket</th><th className="text-right font-normal">Kalshi</th><th className="text-right font-normal">Fed funds futures</th><th className="text-right font-normal">Max gap</th></tr></thead>
            <tbody>{f.rows.map((r: any) => {
              const v = [r.polymarket, r.kalshi, r.futures ?? (f.futures ? 0 : null)].filter((x) => x != null) as number[];
              const gap = v.length > 1 ? Math.max(...v) - Math.min(...v) : null;
              return (
                <tr key={r.move_bp} className="border-t border-border-subtle"><td className="font-sans text-text-primary py-0.5">{lab(r.move_bp)}</td>
                  {[r.polymarket, r.kalshi, r.futures ?? (f.futures ? 0 : null)].map((x, i) => (
                    <td key={i} className="text-right"><span className="inline-block w-14 h-1.5 bg-surface-3 mr-1 align-middle"><span className="block h-full bg-bloomberg" style={{ width: `${(x ?? 0) * 100}%` }} /></span>{P(x)}</td>))}
                  <td className={cn('text-right', (gap ?? 0) >= 0.05 ? 'text-amber font-semibold' : 'text-text-tertiary')}>{gap != null ? `${(gap * 100).toFixed(0)}pt` : '—'}</td></tr>);
            })}</tbody></table>
          <div className="space-y-1 text-text-secondary">
            {f.futures && <div>Target range <span className="font-mono text-text-primary">{f.futures.target_lower?.toFixed(2)}–{f.futures.target_upper?.toFixed(2)}%</span>; futures imply <span className="font-mono text-text-primary">{f.futures.change_bp >= 0 ? '+' : ''}{f.futures.change_bp?.toFixed(1)}bp</span>.</div>}
            {f.kalshi_thresholds?.length ? <div>{f.kalshi_note}: {f.kalshi_thresholds.map((t: any) => <span key={t.above} className="font-mono text-text-primary"> above {t.above.toFixed(2)}% {P(t.p)};</span>)}</div> : null}
            <div className="text-text-tertiary">{d.note}</div>
          </div>
        </div>
      </Panel>
      {Object.entries<any[]>(d.groups).map(([g, evs]) => (
        <Panel key={g} title={`${g} — ${evs.length} most-traded`}>
          <div className="grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-2">
            {evs.slice(0, 12).map((e: any) => <EventCard key={`${e.venue}${e.id}`} e={{ ...e, n_markets: e.markets.length, markets: e.markets.slice(0, 4) }} onOpen={onOpen} />)}</div>
        </Panel>))}
    </div>
  );
}

// ── Following ───────────────────────────────────────────────────────────────
function Following({ onOpen }: { onOpen: (o: Open) => void }) {
  const fol = useFollow('pred');
  if (!fol.list.length) return <div className="text-[11px] text-text-tertiary">Open any market and press ☆ Follow to keep it here, with your own notes.</div>;
  return (
    <div className="space-y-1">{fol.list.map((f) => {
      const [venue, ...rest] = f.id.split(':');
      return (
        <div key={f.id} className="border border-border bg-surface-1 rounded-md px-3 py-2 flex gap-2 items-start text-[11px]">
          <button onClick={() => onOpen({ venue, id: rest.join(':') })} className="text-left flex-1 min-w-0"><Venue v={venue} /> <span className="text-text-primary font-semibold">{f.label}</span>
            <div className="text-text-tertiary">{f.reason} · added {f.added.replace('T', ' ')}</div></button>
          <input value={f.note} onChange={(e) => fol.setNote(f.id, e.target.value)} placeholder="Note…" className="w-64 bg-surface-2 border border-border px-2 py-0.5 text-text-primary" />
          <button onClick={() => fol.remove(f.id)} className="text-text-tertiary hover:text-red">✕</button>
        </div>);
    })}</div>
  );
}

// ── Related odds: a compact panel for other screens ─────────────────────────
const SYMBOL_TERMS: Record<string, string[]> = {
  'CL=F': ['oil', 'crude', 'wti', 'opec'], 'BZ=F': ['oil', 'brent', 'crude', 'opec'], 'GC=F': ['gold'], 'SI=F': ['silver'], 'HG=F': ['copper'],
  'NG=F': ['natural gas'], '^GSPC': ['s&p 500', 's&p', 'recession'], '^SPX': ['s&p 500', 's&p'], 'SPY': ['s&p 500', 's&p'], '^NDX': ['nasdaq', 'nasdaq-100'],
  'QQQ': ['nasdaq', 'nasdaq-100'], '^IXIC': ['nasdaq'], '^DJI': ['dow'], '^VIX': ['vix', 'recession'], '^N225': ['nikkei', 'boj', 'yen'],
  '^TNX': ['10-year', 'treasury', 'fed', 'rate cut'], '^TYX': ['30-year', 'treasury'], 'TLT': ['treasury', 'fed', 'rate cut'],
  'DX-Y.NYB': ['dollar', 'fed'], 'EURUSD=X': ['euro', 'ecb'], 'USDJPY=X': ['yen', 'boj'], 'JPY=X': ['yen', 'boj'], 'GBPUSD=X': ['pound', 'boe', 'bank of england'],
  'USDCNY=X': ['yuan', 'china', 'tariff'], 'BTC-USD': ['bitcoin', 'btc'], 'ETH-USD': ['ethereum', 'eth'], 'SOL-USD': ['solana'], 'XRP-USD': ['xrp'], 'DOGE-USD': ['dogecoin'],
};
const STOP_NAME = /\b(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|holdings?|group|sa|ag|nv|se|asa|ab|oyj|spa|the|class [a-c]|common stock|ordinary shares|adr)\b\.?/gi;

/** Search terms for a security: its short company name and ticker, or the macro theme behind it. */
export function predTerms(symbol: string, name?: string | null, type?: string | null): string[] {
  const s = symbol.toUpperCase();
  if (SYMBOL_TERMS[s]) return SYMBOL_TERMS[s];
  if (type && type !== 'Stock') return [];
  const nm = (name ?? '').replace(STOP_NAME, ' ').replace(/[,.]/g, ' ').replace(/\s+/g, ' ').trim();
  const words = nm.split(' ');
  const short = words.slice(0, words[0]?.length <= 3 ? 2 : 1).join(' ');
  const tick = s.split('.')[0];
  return [...new Set([short, nm.length <= 25 ? nm : '', /^[A-Z]{3,5}$/.test(tick) ? tick : ''].filter((x) => x && x.length >= 3))];
}

export function RelatedOdds({ terms, title = 'Prediction markets', limit = 5, className }: { terms: string[]; title?: string; limit?: number; className?: string }) {
  const q = terms.filter(Boolean).join(',');
  const { data } = useJSON<any>(q ? `/api/v1/mkt/pred/related?q=${encodeURIComponent(q)}&limit=${limit}` : null, 600_000);
  if (!data?.events?.length) return null;          // nothing relevant: stay out of the way
  const open = (e: any) => {
    try { sessionStorage.setItem('pred_open', JSON.stringify({ venue: e.venue, id: e.id, q: e.title })); } catch { /* storage unavailable */ }
    window.location.hash = '#mkt/pred';
    window.scrollTo({ top: 0 });
  };
  return (
    <div className={cn('border border-border bg-surface-1 rounded-md', className)}>
      <div className="flex items-center justify-between px-2.5 py-1.5 border-b border-border-subtle">
        <span className="text-[10px] uppercase tracking-wider text-text-tertiary font-semibold">{title}</span>
        <span className="text-[9px] text-text-tertiary">Kalshi · Polymarket — real-money odds</span></div>
      <div className="divide-y divide-border-subtle">{data.events.map((e: any) => (
        <button key={`${e.venue}${e.id}`} onClick={() => open(e)} className="w-full text-left px-2.5 py-1.5 hover:bg-surface-2 transition-colors">
          <div className="flex items-start gap-1.5"><span className="text-[11px] text-text-primary font-medium flex-1 min-w-0">{e.title}</span><Venue v={e.venue} /></div>
          {e.markets.slice(0, 3).map((m: any) => (
            <div key={m.id} className="flex items-center gap-1.5 text-[10px]">
              <span className="flex-1 min-w-0 truncate text-text-secondary">{m.binary ? m.label : m.outcomes.map((o: any) => o.name).join(' / ')}</span>
              <span className="font-mono text-text-primary">{m.binary ? P(m.yes) : m.outcomes.map((o: any) => P(o.price)).join(' / ')}</span>
              <span className={cn('w-8 text-right font-mono', tone(m.chg_1d))}>{PT(m.chg_1d)}</span></div>))}
          <div className="text-[9px] text-text-tertiary">24h {vol(e.venue, e.volume_24h)}{e.end ? ` · closes ${e.end}` : ''}</div>
        </button>))}</div>
    </div>
  );
}
