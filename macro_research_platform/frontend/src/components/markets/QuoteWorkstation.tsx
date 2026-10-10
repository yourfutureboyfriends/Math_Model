// Futubull-style quote workstation (DES): watchlist on the left (↑/↓ steps through it), a dense
// quote panel, chart and tabs in the middle, and top of book, intraday tape, buy/sell volume,
// volume-by-price and the order ticket on the right — everything follows the selected stock.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { toTerminal } from './bbg';
import { Chart } from './TickerView';
import { AnalystGauge, EarningsCard, NewsList, OrderTicket, SimilarStocks } from './InstrumentOverview';
import { Flash, fmtBig, fmtPct, fmtPrice, Loading, symType, useJSON } from './shared';

const enc = encodeURIComponent;

function Box({ title, right, children, className }: { title: string; right?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn('bg-surface-1 border border-border min-w-0', className)}>
      <header className="panel-bar flex items-center justify-between px-2 h-6 text-[11px] uppercase tracking-wide">
        <span className="text-bloomberg font-semibold">{title}</span>{right}
      </header>
      <div className="p-2">{children}</div>
    </section>
  );
}

// Yahoo states market caps of lines quoted in minor units (pence, cents, agorot) in the major unit
const MAJOR: Record<string, string> = { GBp: 'GBP', GBX: 'GBP', ZAc: 'ZAR', ILA: 'ILS' };

const upDown = (v: number | null | undefined) => (v == null ? 'text-text-tertiary' : v > 0 ? 'text-green' : v < 0 ? 'text-red' : 'text-text-secondary');

// ── Left: watchlist ─────────────────────────────────────────────────────────
export function WatchColumn({ current, onOpen }: { current?: string; onOpen: (s: string) => void }) {
  const [lists, setLists] = useState<any[]>([]);
  const [idx, setIdx] = useState(() => { try { return Number(localStorage.getItem('mkt_ws_list') ?? 0) || 0; } catch { return 0; } });
  const [quotes, setQuotes] = useState<Record<string, any>>({});
  const load = useCallback(() => fetch('/api/v1/mkt/watchlists').then((r) => r.json()).then((j) => setLists(j.watchlists ?? [])).catch(() => {}), []);
  useEffect(() => { load(); const t = setInterval(load, 120_000); return () => clearInterval(t); }, [load]);
  useEffect(() => { try { localStorage.setItem('mkt_ws_list', String(idx)); } catch { /* storage unavailable */ } }, [idx]);
  const list = lists[Math.min(idx, Math.max(0, lists.length - 1))];
  const syms: string[] = list?.symbols ?? [];
  useEffect(() => {
    if (!syms.length) return;
    let live = true;
    const get = () => fetch(`/api/v1/mkt/quotes?symbols=${enc(syms.join(','))}`).then((r) => r.json())
      .then((j) => live && setQuotes(Object.fromEntries((j.quotes ?? []).map((q: any) => [q.symbol, q])))).catch(() => {});
    get();
    const t = setInterval(() => document.visibilityState === 'visible' && get(), 30_000);
    return () => { live = false; clearInterval(t); };
  }, [list?.id, syms.join(',')]);
  // ↑ / ↓ step through the list, as in Futubull (ignored while typing)
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)) return;
      if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown' || !syms.length || e.altKey || e.metaKey || e.ctrlKey) return;
      e.preventDefault();
      const i = current ? syms.indexOf(current) : -1;
      const n = e.key === 'ArrowDown' ? (i + 1) % syms.length : (i <= 0 ? syms.length - 1 : i - 1);
      onOpen(syms[n]);
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [syms.join(','), current, onOpen]);
  return (
    <aside className="hidden xl:flex flex-col bg-surface-1 border border-border sticky top-[calc(var(--topbar-height)+8px)] h-[calc(100vh-var(--topbar-height)-56px)] min-h-[420px]">
      <div className="panel-bar flex items-center gap-1 px-1.5 h-7">
        <select value={Math.min(idx, Math.max(0, lists.length - 1))} onChange={(e) => setIdx(Number(e.target.value))} aria-label="Watchlist"
          className="flex-1 min-w-0 bg-transparent text-[11px] uppercase tracking-wide text-bloomberg font-semibold outline-none">
          {lists.map((l, i) => <option key={l.id} value={i} className="bg-surface-1 text-text-primary normal-case">{l.name} ({l.symbols.length})</option>)}
        </select>
        <button onClick={() => { window.location.hash = '#mkt/w'; }} className="text-[10px] text-text-tertiary hover:text-bloomberg">EDIT</button>
      </div>
      <div className="grid grid-cols-[1fr_auto_auto] gap-x-2 px-2 py-1 text-[10px] text-text-tertiary border-b border-border-subtle"><span>Name / code</span><span className="text-right">Last</span><span className="text-right w-14">Chg%</span></div>
      <ul className="flex-1 overflow-y-auto text-[12px]">
        {syms.map((s) => { const q = quotes[s]; const on = s === current; return (
          <li key={s}><button onClick={() => onOpen(s)} className={cn('w-full grid grid-cols-[1fr_auto_auto] gap-x-2 items-center px-2 py-1 text-left border-l-2 hover:bg-surface-3',
            on ? 'border-bloomberg bg-surface-3' : 'border-transparent')}>
            <span className="min-w-0"><span className="block truncate text-text-primary">{q?.name ?? s}</span><span className="block text-[10px] text-text-tertiary font-mono truncate">{toTerminal(s)}</span></span>
            <span className={cn('font-mono tabular-nums text-right', upDown(q?.change_1d))}><Flash value={q?.price}>{q ? fmtPrice(q.price, symType(s)) : '…'}</Flash></span>
            <span className={cn('font-mono tabular-nums text-right w-14 px-1 text-[11px]', q?.change_1d == null ? 'text-text-tertiary' : q.change_1d >= 0 ? 'bg-green/15 text-green' : 'bg-red/15 text-red')}>
              {q?.change_1d == null ? '—' : `${q.change_1d >= 0 ? '+' : ''}${(q.change_1d * 100).toFixed(2)}%`}</span>
          </button></li>); })}
        {!syms.length && <li className="p-3 text-xs text-text-tertiary">{lists.length ? 'Empty — add with “+ Watch”.' : 'Loading…'}</li>}
      </ul>
      <div className="px-2 py-1 text-[10px] text-text-tertiary border-t border-border-subtle">↑ ↓ to switch stocks</div>
    </aside>
  );
}

// ── Centre: dense quote panel ───────────────────────────────────────────────
function quoteCells(q: any) {
  const ext = q.market_state === 'PRE' || q.market_state === 'PREPRE' ? { label: 'Pre-market', p: q.pre_market_price, c: q.pre_market_change_pct }
    : (q.market_state === 'POST' || q.market_state === 'POSTPOST' || q.market_state === 'CLOSED') && q.post_market_price ? { label: 'After hours', p: q.post_market_price, c: q.post_market_change_pct } : null;
  // vs previous close: tinted only when both are known
  const tone = (v: number | null | undefined) => (v == null || q.previous_close == null ? undefined : v > q.previous_close ? 'text-green' : v < q.previous_close ? 'text-red' : undefined);
  // money figures carry the listing's currency when it isn't the dollar (Toyota: "34.47T JPY")
  const ccy = q.currency && q.currency !== 'USD' && !['FX', 'Index'].includes(q.type) ? q.currency : null;
  const cells: [string, string, string?][] = [
    ['High', fmtPrice(q.day_high, q.type), tone(q.day_high)], ['Open', fmtPrice(q.open, q.type), tone(q.open)],
    ['Volume', fmtBig(q.volume)], ['Mkt cap', fmtBig(q.market_cap, ccy && (MAJOR[ccy] ?? ccy))], ['P/E TTM', q.trailing_pe != null ? q.trailing_pe.toFixed(2) : '—'], ['52W high', fmtPrice(q.week52_high, q.type)],
    ['Low', fmtPrice(q.day_low, q.type), tone(q.day_low)], ['Prev close', fmtPrice(q.previous_close, q.type)],
    ['Turnover', fmtBig(q.turnover, ccy)], ['Float', fmtBig(q.float_shares)], ['P/E fwd', q.forward_pe != null ? q.forward_pe.toFixed(2) : '—'], ['52W low', fmtPrice(q.week52_low, q.type)],
    ['Amplitude', q.amplitude != null ? `${(q.amplitude * 100).toFixed(2)}%` : '—'], ['Avg price', '—'],
    ['Turnover %', q.turnover_ratio != null ? `${(q.turnover_ratio * 100).toFixed(2)}%` : '—'], ['Vol ratio', q.volume_ratio != null ? q.volume_ratio.toFixed(2) : '—'],
    ['Div yield', q.dividend_yield != null ? `${(q.dividend_yield * 100).toFixed(2)}%` : '—'], ['EPS TTM', q.eps_ttm != null ? q.eps_ttm.toFixed(2) : '—'],
  ];
  return { ext, cells };
}

/** Where the price sits inside a range (day, 52 weeks): a thin track with a marker. */
function RangeBar({ label, lo, hi, v, type }: { label: string; lo?: number | null; hi?: number | null; v?: number | null; type?: string }) {
  if (lo == null || hi == null || v == null || !(hi > lo)) return null;
  const pct = Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100));
  return (
    <div className="text-[10px] min-w-[150px]" title={`${label}: ${fmtPrice(lo, type)} – ${fmtPrice(hi, type)} · ${pct.toFixed(0)}% of the range`}>
      <div className="flex justify-between text-text-tertiary"><span>{label}</span><span>{pct.toFixed(0)}%</span></div>
      <div className="relative h-1.5 bg-surface-3 mt-0.5">
        <div className="absolute inset-y-0 left-0 bg-bloomberg/30" style={{ width: `${pct}%` }} />
        <div className="absolute -top-0.5 w-0.5 h-2.5 bg-bloomberg" style={{ left: `calc(${pct}% - 1px)` }} />
      </div>
      <div className="flex justify-between font-mono text-text-tertiary mt-0.5"><span>{fmtPrice(lo, type)}</span><span>{fmtPrice(hi, type)}</span></div>
    </div>
  );
}

function QuoteHeaderDense({ q, vwap }: { q: any; vwap?: number | null }) {
  const { ext, cells } = quoteCells(q);
  const filled = cells.map((c) => (c[0] === 'Avg price' ? [c[0], vwap != null ? fmtPrice(vwap, q.type) : '—'] as [string, string] : c));
  return (
    <div className="bg-surface-1 border border-border p-2 flex flex-wrap gap-x-6 gap-y-2">
      <div className="min-w-[200px]">
        <div className="flex items-baseline gap-2">
          <Flash value={q.price} className={cn('text-3xl font-semibold font-mono tabular-nums', upDown(q.change))}>{fmtPrice(q.price, q.type)}</Flash>
          <span className={cn('text-sm font-mono', upDown(q.change))}>{q.change != null ? `${q.change >= 0 ? '+' : ''}${fmtPrice(q.change, q.type)}` : ''}</span>
          <span className={cn('text-sm font-mono', upDown(q.change))}>{q.change_pct != null ? `${q.change_pct >= 0 ? '+' : ''}${(q.change_pct * 100).toFixed(2)}%` : ''}</span>
        </div>
        <div className="text-[11px] text-text-tertiary mt-0.5">{q.currency} · {q.exchange}{q.delay_minutes ? ` · delayed ${q.delay_minutes}m` : ''}</div>
        {ext?.p != null && <div className="text-[11px] mt-0.5"><span className="text-text-tertiary">{ext.label} </span>
          <span className={cn('font-mono', upDown(ext.c))}>{fmtPrice(ext.p, q.type)} {ext.c != null ? `${ext.c >= 0 ? '+' : ''}${(ext.c * 100).toFixed(2)}%` : ''}</span></div>}
        <div className="flex gap-4 mt-1.5">
          <RangeBar label="Day range" lo={q.day_low} hi={q.day_high} v={q.price} type={q.type} />
          <RangeBar label="52-week range" lo={q.week52_low} hi={q.week52_high} v={q.price} type={q.type} />
        </div>
      </div>
      <dl className="flex-1 grid grid-cols-3 sm:grid-cols-6 gap-x-4 gap-y-1 text-[11px] min-w-[300px]">
        {filled.map(([k, v, tone]) => (
          <div key={k} className="flex justify-between gap-2"><dt className="text-text-tertiary whitespace-nowrap">{k}</dt><dd className={cn('font-mono tabular-nums text-right', tone ?? 'text-text-primary')}>{v}</dd></div>))}
      </dl>
    </div>
  );
}

// ── Right: top of book, tape, flow, profile ─────────────────────────────────
function BookBox({ q }: { q: any }) {
  const bid = q.bid, ask = q.ask, bs = q.bid_size ?? 0, as_ = q.ask_size ?? 0;
  const spread = bid && ask ? ask - bid : null;
  const pctBid = bs + as_ > 0 ? (bs / (bs + as_)) * 100 : 50;
  return (
    <Box title="Bid / ask" right={<span className="text-[10px] text-text-tertiary normal-case tracking-normal" title="Free data has the best bid and offer only (no depth). Sizes as the exchange reports them (US: round lots).">top of book</span>}>
      {!bid && !ask ? <p className="text-[11px] text-text-tertiary">No live bid/ask outside trading hours for this market.</p> : (
        <div className="space-y-1.5 text-[12px] font-mono tabular-nums">
          <div className="grid grid-cols-[auto_1fr_auto] gap-x-2"><span className="text-text-tertiary font-sans text-[11px]">Ask</span><span className="text-red text-right">{fmtPrice(ask, q.type)}</span><span className="text-text-secondary w-16 text-right">{as_ ? fmtBig(as_) : '—'}</span></div>
          <div className="grid grid-cols-[auto_1fr_auto] gap-x-2"><span className="text-text-tertiary font-sans text-[11px]">Bid</span><span className="text-green text-right">{fmtPrice(bid, q.type)}</span><span className="text-text-secondary w-16 text-right">{bs ? fmtBig(bs) : '—'}</span></div>
          <div className="flex h-1.5 overflow-hidden"><div className="bg-green" style={{ width: `${pctBid}%` }} /><div className="bg-red flex-1" /></div>
          <div className="flex justify-between text-[10px] text-text-tertiary font-sans"><span>Bid {pctBid.toFixed(0)}%</span>
            <span>Spread {spread != null ? `${fmtPrice(spread, q.type)} (${((spread / ((bid + ask) / 2)) * 1e4).toFixed(1)} bp)` : '—'}</span></div>
        </div>)}
    </Box>
  );
}

function TapeBoxes({ symbol, q }: { symbol: string; q: any }) {
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/tape/${enc(symbol)}`, 60_000);
  const maxV = useMemo(() => Math.max(1, ...(data?.profile ?? []).map((b: any) => b.volume)), [data]);
  if (loading && !data) return <Box title="Intraday"><Loading /></Box>;
  if (error && !data) return <Box title="Intraday"><p className="text-[11px] text-text-tertiary">{error}</p></Box>;
  if (!data) return null;
  const tot = data.up_volume + data.down_volume;
  const buyPct = tot > 0 ? (data.up_volume / tot) * 100 : 50;
  const vsVwap = data.vwap && q.price ? q.price / data.vwap - 1 : null;
  return (
    <>
      <Box title="Buying vs selling" right={<span className="text-[10px] text-text-tertiary normal-case tracking-normal" title={data.method}>tick-rule estimate</span>}>
        <div className="space-y-1.5 text-[11px]">
          <div className="flex h-2 overflow-hidden"><div className="bg-green" style={{ width: `${buyPct}%` }} /><div className="bg-red flex-1" /></div>
          <div className="flex justify-between font-mono tabular-nums"><span className="text-green">Buy {fmtBig(data.up_volume)} ({buyPct.toFixed(0)}%)</span><span className="text-red">Sell {fmtBig(data.down_volume)}</span></div>
          <div className="flex justify-between"><span className="text-text-tertiary">VWAP</span><span className="font-mono text-text-primary">{fmtPrice(data.vwap, q.type)} <span className={upDown(vsVwap)}>{vsVwap != null ? fmtPct(vsVwap, 2) : ''}</span></span></div>
        </div>
      </Box>
      <Box title="Volume by price" right={<span className="text-[10px] text-text-tertiary normal-case tracking-normal">{data.date}</span>}>
        <div className="space-y-px">
          {[...data.profile].reverse().map((b: any, i: number) => {
            const here = q.price >= b.price_low && q.price < b.price_high;
            const atVwap = data.vwap >= b.price_low && data.vwap < b.price_high;
            return (
              <div key={i} className="grid grid-cols-[52px_1fr] items-center gap-1 text-[10px] font-mono">
                <span className={cn('text-right tabular-nums', here ? 'text-bloomberg font-semibold' : 'text-text-tertiary')}>{fmtPrice((b.price_low + b.price_high) / 2, q.type)}</span>
                <div className="h-2 bg-surface-3 relative"><div className={cn('h-full', here ? 'bg-bloomberg' : atVwap ? 'bg-blue/70' : 'bg-text-tertiary/50')} style={{ width: `${(b.volume / maxV) * 100}%` }} /></div>
              </div>);
          })}
          <div className="text-[10px] text-text-tertiary pt-1"><span className="text-bloomberg">■</span> price now · <span className="text-blue">■</span> VWAP</div>
        </div>
      </Box>
      <Box title="Tape" right={<span className="text-[10px] text-text-tertiary normal-case tracking-normal">1-minute prints</span>}>
        <div className="max-h-64 overflow-y-auto">
          <table className="w-full text-[11px] font-mono tabular-nums">
            <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-left font-normal">Time</th><th className="text-right font-normal">Price</th><th className="text-right font-normal">Volume</th></tr></thead>
            <tbody>{data.prints.map((p: any, i: number) => (
              <tr key={i}><td className="text-text-tertiary">{p.time}</td><td className={cn('text-right', p.side > 0 ? 'text-green' : p.side < 0 ? 'text-red' : 'text-text-secondary')}>{fmtPrice(p.price, q.type)}</td>
                <td className="text-right text-text-secondary">{fmtBig(p.volume)}</td></tr>))}</tbody>
          </table>
        </div>
      </Box>
    </>
  );
}

// ── The workstation ─────────────────────────────────────────────────────────
type Tab = 'overview' | 'news' | 'peers';

export function QuoteWorkstation({ q, onOpen, onGo }: { q: any; onOpen: (s: string) => void; onGo: (fn: string, s?: string) => void }) {
  const [tab, setTab] = useState<Tab>('overview');
  const p = useJSON<any>(`/api/v1/mkt/profile/${enc(q.symbol)}`);
  const tape = useJSON<any>(`/api/v1/mkt/tape/${enc(q.symbol)}`, 60_000);
  const isEquity = q.type === 'Stock';
  const tabs: [Tab, string][] = [['overview', 'Overview'], ['news', 'News'], ...(isEquity ? [['peers', 'Peers'] as [Tab, string]] : [])];
  return (
    <div className="grid grid-cols-1 2xl:grid-cols-[minmax(0,1fr)_300px] gap-2">
      <div className="space-y-2 min-w-0">
        <QuoteHeaderDense q={q} vwap={tape.data?.vwap} />
        <div className="border border-border"><Chart symbol={q.symbol} height={430} /></div>
        <div className="bg-surface-1 border border-border">
          <nav className="flex items-center gap-1 border-b border-border px-1" aria-label="Quote tabs">
            {tabs.map(([k, l]) => (
              <button key={k} onClick={() => setTab(k)} className={cn('px-3 py-1.5 text-xs -mb-px border-b-2', tab === k ? 'border-bloomberg text-text-primary font-semibold' : 'border-transparent text-text-secondary hover:text-text-primary')}>{l}</button>))}
            <span className="ml-auto flex gap-1 text-[10px] pr-1">
              {(isEquity ? ['FA', 'ERN', 'ANR', 'OMON', 'DCF', 'HDS'] : ['GP', 'HP', 'OMON']).map((fn) => (
                <button key={fn} onClick={() => onGo(fn, q.symbol)} className="px-1.5 py-0.5 border border-border text-text-secondary hover:text-bloomberg hover:border-bloomberg font-mono">{fn}</button>))}
            </span>
          </nav>
          <div className="p-3">
            {tab === 'overview' && (
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                {isEquity && <div><div className="text-[11px] uppercase tracking-wide text-text-tertiary mb-2">Analyst consensus</div><AnalystGauge symbol={q.symbol} price={q.price} /></div>}
                {isEquity && <div><div className="text-[11px] uppercase tracking-wide text-text-tertiary mb-2">Earnings</div><EarningsCard symbol={q.symbol} /></div>}
                <div className={isEquity ? '' : 'lg:col-span-3'}><div className="text-[11px] uppercase tracking-wide text-text-tertiary mb-2">About</div>
                  {p.data?.description ? <p className="text-xs text-text-secondary leading-relaxed line-clamp-[8]">{p.data.description}</p> : <p className="text-xs text-text-tertiary">{p.loading ? 'Loading…' : 'No description.'}</p>}
                  {p.data && <div className="mt-2 text-[11px] text-text-tertiary">{[p.data.sector, p.data.industry, p.data.country, p.data.employees ? `${p.data.employees.toLocaleString()} staff` : null].filter(Boolean).join(' · ')}</div>}
                </div>
              </div>)}
            {tab === 'news' && <NewsList symbol={q.symbol} />}
            {tab === 'peers' && <SimilarStocks symbol={q.symbol} onOpen={onOpen} />}
          </div>
        </div>
      </div>
      <div className="space-y-2">
        <BookBox q={q} />
        <TapeBoxes symbol={q.symbol} q={q} />
        <Box title="Trade (paper)"><OrderTicket q={q} /></Box>
      </div>
    </div>
  );
}
