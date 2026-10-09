// Brokerage-style instrument overview (DES): chart + order ticket, key statistics with a
// 52-week range bar, analyst consensus gauge, earnings card, similar stocks, news, about.
import { useState } from 'react';
import { CheckCircle2, ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Chart } from './TickerView';
import { Chg, fmtBig, fmtPct, fmtPrice, Loading, useJSON } from './shared';

const enc = encodeURIComponent;

function Card({ title, right, children, className }: { title: string; right?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn('bg-surface-1 border border-border rounded-md', className)}>
      <header className="flex items-center justify-between px-4 pt-3 pb-2">
        <h3 className="text-xs font-semibold text-text-primary">{title}</h3>{right}
      </header>
      <div className="px-4 pb-4">{children}</div>
    </section>
  );
}

function RangeBar({ low, high, value, label }: { low?: number | null; high?: number | null; value?: number | null; label: string }) {
  if (low == null || high == null || value == null || high <= low) return null;
  const p = Math.max(0, Math.min(100, ((value - low) / (high - low)) * 100));
  return (
    <div className="col-span-2">
      <div className="flex justify-between text-[10px] text-text-tertiary mb-1"><span>{label}</span><span>{p.toFixed(0)}% of range</span></div>
      <div className="relative h-1.5 rounded-full bg-surface-3">
        <div className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-red/60 via-amber/60 to-green/60" style={{ width: '100%' }} />
        <div className="absolute -top-1 w-0.5 h-3.5 bg-text-primary" style={{ left: `${p}%` }} />
      </div>
      <div className="flex justify-between text-[11px] font-mono text-text-secondary mt-1"><span>{fmtPrice(low)}</span><span>{fmtPrice(high)}</span></div>
    </div>
  );
}

function KeyStats({ q, p }: { q: any; p: any }) {
  const v = p?.valuation ?? {};
  const rows: [string, string][] = [
    ['Open', fmtPrice(q.open, q.type)], ['Previous close', fmtPrice(q.previous_close, q.type)],
    ['Day high', fmtPrice(q.day_high, q.type)], ['Day low', fmtPrice(q.day_low, q.type)],
    ['Volume', fmtBig(q.volume)], ['Avg volume', fmtBig(q.avg_volume)],
    ['Market cap', fmtBig(q.market_cap)], ['P/E (TTM)', v.trailing_pe != null ? v.trailing_pe.toFixed(1) : '—'],
    ['Forward P/E', v.forward_pe != null ? v.forward_pe.toFixed(1) : '—'], ['Dividend yield', v.dividend_yield != null ? fmtPct(v.dividend_yield, 2).replace('+', '') : '—'],
    ['Beta', v.beta != null ? v.beta.toFixed(2) : '—'], ['Price / book', v.price_to_book != null ? v.price_to_book.toFixed(2) : '—'],
  ];
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-2">
      <RangeBar low={q.day_low} high={q.day_high} value={q.price} label="Day range" />
      <RangeBar low={q.week52_low} high={q.week52_high} value={q.price} label="52-week range" />
      {rows.map(([k, val]) => (
        <div key={k} className="flex justify-between gap-2 text-xs border-b border-border-subtle pb-1">
          <span className="text-text-tertiary">{k}</span><span className="font-mono text-text-primary">{val}</span></div>))}
    </div>
  );
}

function OrderTicket({ q }: { q: any }) {
  const [side, setSide] = useState<'buy' | 'sell'>('buy');
  const [mode, setMode] = useState<'shares' | 'amount'>('shares');
  const [qty, setQty] = useState('');
  const [limit, setLimit] = useState('');
  const [type, setType] = useState<'market' | 'limit'>('market');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const px = type === 'limit' && Number(limit) > 0 ? Number(limit) : q.price;
  const shares = mode === 'shares' ? Number(qty) : px ? Number(qty) / px : 0;
  const cost = shares && px ? shares * px : null;
  const submit = async () => {
    if (!shares || shares <= 0 || !px) { setMsg({ ok: false, text: 'Enter a quantity.' }); return; }
    setBusy(true); setMsg(null);
    try {
      const r = await fetch('/api/v1/portfolio/positions', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: q.symbol, quantity: (side === 'buy' ? 1 : -1) * +shares.toFixed(6), avg_cost: px,
          asset_class: q.type === 'Stock' ? 'Equity' : q.type, book: 'Discretionary' }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(typeof j?.detail === 'string' ? j.detail : `HTTP ${r.status}`);
      setMsg({ ok: true, text: `Paper ${side} of ${+shares.toFixed(4)} ${q.symbol} at ${fmtPrice(px, q.type)} recorded in My Portfolio.` });
      setQty('');
    } catch (e: any) { setMsg({ ok: false, text: e.message }); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 rounded-md overflow-hidden border border-border">
        {(['buy', 'sell'] as const).map((s) => (
          <button key={s} onClick={() => setSide(s)} className={cn('py-2 text-sm font-semibold capitalize transition-colors',
            side === s ? (s === 'buy' ? 'bg-green text-white' : 'bg-red text-white') : 'text-text-secondary hover:bg-surface-3')}>{s}</button>))}
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <label className="text-text-tertiary">Order type
          <select value={type} onChange={(e) => setType(e.target.value as any)} className="mt-1 w-full bg-surface-2 border border-border rounded px-2 py-1.5 text-text-primary">
            <option value="market">Market</option><option value="limit">Limit</option></select></label>
        <label className="text-text-tertiary">Buy in
          <select value={mode} onChange={(e) => setMode(e.target.value as any)} className="mt-1 w-full bg-surface-2 border border-border rounded px-2 py-1.5 text-text-primary">
            <option value="shares">Units</option><option value="amount">{q.currency ?? 'Amount'}</option></select></label>
      </div>
      {type === 'limit' && <label className="block text-xs text-text-tertiary">Limit price
        <input type="number" min="0" step="any" value={limit} onChange={(e) => setLimit(e.target.value)} placeholder={fmtPrice(q.price, q.type)}
          className="mt-1 w-full bg-surface-2 border border-border rounded px-2 py-1.5 font-mono text-text-primary" /></label>}
      <label className="block text-xs text-text-tertiary">{mode === 'shares' ? 'Quantity' : `Amount (${q.currency})`}
        <input type="number" min="0" step="any" value={qty} onChange={(e) => setQty(e.target.value)} placeholder="0"
          className="mt-1 w-full bg-surface-2 border border-border rounded px-2 py-2 text-base font-mono text-text-primary" /></label>
      <div className="text-xs space-y-1 border-t border-border-subtle pt-2">
        <div className="flex justify-between"><span className="text-text-tertiary">{type === 'market' ? 'Market price' : 'Limit price'}</span><span className="font-mono">{fmtPrice(px, q.type)}</span></div>
        {mode === 'amount' && <div className="flex justify-between"><span className="text-text-tertiary">Units</span><span className="font-mono">{shares ? +shares.toFixed(4) : '—'}</span></div>}
        <div className="flex justify-between font-semibold"><span className="text-text-secondary">Estimated {side === 'buy' ? 'cost' : 'proceeds'}</span>
          <span className="font-mono">{cost != null ? `${fmtPrice(cost)} ${q.currency ?? ''}` : '—'}</span></div>
      </div>
      <button onClick={submit} disabled={busy} className={cn('w-full py-2.5 rounded-md text-sm font-semibold text-white disabled:opacity-50', side === 'buy' ? 'bg-green hover:bg-green/90' : 'bg-red hover:bg-red/90')}>
        {busy ? 'Recording…' : `Review & ${side} (paper)`}</button>
      {msg && <div className={cn('text-xs flex gap-1.5', msg.ok ? 'text-green' : 'text-red')}>{msg.ok && <CheckCircle2 className="w-3.5 h-3.5 shrink-0 mt-0.5" />}{msg.text}</div>}
      <p className="text-[10px] text-text-tertiary leading-relaxed">Paper trading: records the position in Portfolios → My Portfolio at the shown price. No real order is sent. Prices may be delayed.</p>
    </div>
  );
}

function AnalystGauge({ symbol, price }: { symbol: string; price?: number | null }) {
  const { data, loading } = useJSON<any>(`/api/v1/mkt/anr/${enc(symbol)}`);
  if (loading && !data) return <Loading />;
  const s = data?.summary?.[0];
  const rm = data?.recommendation_mean;                 // Yahoo: 1 = strong buy … 5 = strong sell
  if (!s && rm == null) return <p className="text-xs text-text-tertiary">No analyst coverage.</p>;
  const counts = s ? [s.strongSell ?? 0, s.sell ?? 0, s.hold ?? 0, s.buy ?? 0, s.strongBuy ?? 0] : [0, 0, 0, 0, 0];
  const n = s ? counts.reduce((a, b) => a + b, 0) || 1 : data.analysts ?? 0;
  const score = s ? (counts[0] * 1 + counts[1] * 2 + counts[2] * 3 + counts[3] * 4 + counts[4] * 5) / (n || 1) : 6 - rm;   // 1 = strong sell … 5 = strong buy
  const label = score >= 4.5 ? 'Strong buy' : score >= 3.5 ? 'Buy' : score >= 2.5 ? 'Hold' : score >= 1.5 ? 'Sell' : 'Strong sell';
  const ang = Math.PI * (1 - (score - 1) / 4);
  const t = data.targets ?? {};
  return (
    <div className="flex items-center gap-4">
      <svg viewBox="0 0 120 70" className="w-36 shrink-0" role="img" aria-label={`Analyst consensus ${label}`}>
        {[['rgb(var(--c-red))', 0, 0.2], ['rgb(var(--c-red) / 0.5)', 0.2, 0.4], ['var(--text-tertiary)', 0.4, 0.6], ['rgb(var(--c-green) / 0.55)', 0.6, 0.8], ['rgb(var(--c-green))', 0.8, 1]].map(([c, a, b]) => {
          const a1 = Math.PI * (1 - (a as number)), a2 = Math.PI * (1 - (b as number));
          return <path key={c as string} d={`M ${60 + 50 * Math.cos(a1)} ${62 - 50 * Math.sin(a1)} A 50 50 0 0 1 ${60 + 50 * Math.cos(a2)} ${62 - 50 * Math.sin(a2)}`} stroke={c as string} strokeWidth="9" fill="none" />;
        })}
        <line x1="60" y1="62" x2={60 + 40 * Math.cos(ang)} y2={62 - 40 * Math.sin(ang)} stroke="var(--text-primary)" strokeWidth="2.5" strokeLinecap="round" />
        <circle cx="60" cy="62" r="4" fill="var(--text-primary)" />
      </svg>
      <div className="min-w-0 text-xs space-y-1">
        <div className="text-base font-semibold text-text-primary">{label}</div>
        <div className="text-text-tertiary">{s ? `${n} analysts · ${counts[4] + counts[3]} buy · ${counts[2]} hold · ${counts[1] + counts[0]} sell` : `${n || '—'} analysts · mean rating ${rm?.toFixed(2)} (1 = strong buy)`}</div>
        {t.mean != null && <div>Target <span className="font-mono text-text-primary">{fmtPrice(t.mean)}</span>
          {price ? <> (<Chg v={t.mean / price - 1} d={1} />)</> : null}<div className="text-text-tertiary">range {fmtPrice(t.low)} – {fmtPrice(t.high)}</div></div>}
      </div>
    </div>
  );
}

function EarningsCard({ symbol }: { symbol: string }) {
  const { data, loading } = useJSON<any>(`/api/v1/mkt/ern/${enc(symbol)}`);
  if (loading && !data) return <Loading />;
  if (!data) return <p className="text-xs text-text-tertiary">No earnings data.</p>;
  const up = data.upcoming?.[0], last = data.history?.[0];
  const days = up ? Math.round((new Date(up.date).getTime() - Date.now()) / 86400000) : null;
  return (
    <div className="grid grid-cols-2 gap-3 text-xs">
      <div><div className="text-text-tertiary">Next report</div><div className="text-sm font-semibold text-text-primary">{up ? new Date(up.date).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—'}</div>
        {days != null && <div className="text-text-tertiary">{days >= 0 ? `in ${days} days` : 'recently'}{up?.eps_estimate != null ? ` · est. EPS ${up.eps_estimate.toFixed(2)}` : ''}</div>}</div>
      <div><div className="text-text-tertiary">Last quarter</div>{last ? <><div className="text-sm font-semibold font-mono">{last.eps_reported?.toFixed(2)} <span className="text-text-tertiary text-xs font-sans">vs {last.eps_estimate?.toFixed(2)}</span></div>
        <div className={cn(last.surprise_pct > 0 ? 'text-green' : 'text-red')}>{last.surprise_pct > 0 ? 'Beat' : 'Missed'} by {Math.abs(last.surprise_pct).toFixed(1)}%</div></> : '—'}</div>
      {data.beat_rate != null && <div className="col-span-2 text-text-tertiary">Beat estimates in <span className="text-text-primary">{Math.round(data.beat_rate * 100)}%</span> of the last {data.history.length} reports.</div>}
    </div>
  );
}

function SimilarStocks({ symbol, onOpen }: { symbol: string; onOpen: (s: string) => void }) {
  const { data, loading } = useJSON<any>(`/api/v1/mkt/rv/${enc(symbol)}`);
  const peers = (data?.rows ?? []).filter((r: any) => !r.subject).slice(0, 8);
  const quotes = useJSON<any>(peers.length ? `/api/v1/mkt/quotes?symbols=${enc(peers.map((p: any) => p.symbol).join(','))}` : null);
  const qm: Record<string, any> = Object.fromEntries((quotes.data?.quotes ?? []).map((x: any) => [x.symbol, x]));
  if (loading && !data) return <Loading label="Finding similar companies…" />;
  if (!peers.length) return <p className="text-xs text-text-tertiary">No peers found.</p>;
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
      {peers.map((p: any) => (
        <button key={p.symbol} onClick={() => onOpen(p.symbol)} className="text-left p-2.5 rounded-md border border-border hover:border-bloomberg/60 hover:bg-surface-2 transition-colors">
          <div className="font-mono text-xs font-semibold text-text-primary">{p.symbol}</div>
          <div className="text-[10px] text-text-tertiary truncate">{p.name}</div>
          <div className="mt-1 flex items-baseline justify-between gap-1"><span className="font-mono text-xs">{fmtPrice(qm[p.symbol]?.price)}</span><Chg v={qm[p.symbol]?.change_1d} d={1} className="text-[11px]" /></div>
        </button>))}
    </div>
  );
}

function NewsList({ symbol }: { symbol: string }) {
  const { data, loading } = useJSON<any>(`/api/v1/mkt/news/${enc(symbol)}`, 900_000);
  if (loading && !data) return <Loading />;
  const items = data?.news ?? [];
  if (!items.length) return <p className="text-xs text-text-tertiary">No recent headlines.</p>;
  return (
    <ul className="divide-y divide-border-subtle">{items.slice(0, 6).map((n: any, i: number) => (
      <li key={i} className="py-2"><a href={n.url} target="_blank" rel="noreferrer noopener" className="group block">
        <div className="text-xs text-text-primary group-hover:text-bloomberg leading-snug">{n.title} <ExternalLink className="inline w-3 h-3 text-text-tertiary" /></div>
        <div className="text-[10px] text-text-tertiary mt-0.5">{n.publisher}{n.time ? ` · ${new Date(n.time).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}` : ''}</div>
      </a></li>))}</ul>
  );
}

export function InstrumentOverview({ q, onOpen, onGo }: { q: any; onOpen: (s: string) => void; onGo: (fn: string, s?: string) => void }) {
  const p = useJSON<any>(`/api/v1/mkt/profile/${enc(q.symbol)}`);
  const isEquity = q.type === 'Stock';
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 2xl:grid-cols-[minmax(0,1fr)_340px] gap-3">
        <div className="bg-surface-1 border border-border rounded-md overflow-hidden"><Chart symbol={q.symbol} height={420} /></div>
        <div className="space-y-3">
          <Card title="Trade (paper)"><OrderTicket q={q} /></Card>
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
        <Card title="Key statistics"><KeyStats q={q} p={p.data} /></Card>
        {isEquity && <Card title="Analyst consensus" right={<button onClick={() => onGo('ANR', q.symbol)} className="text-[10px] text-bloomberg hover:underline">Details</button>}>
          <AnalystGauge symbol={q.symbol} price={q.price} /></Card>}
        {isEquity && <Card title="Earnings" right={<button onClick={() => onGo('ERN', q.symbol)} className="text-[10px] text-bloomberg hover:underline">Details</button>}>
          <EarningsCard symbol={q.symbol} /></Card>}
        {!isEquity && p.data && <Card title="Facts"><dl className="grid grid-cols-2 gap-2 text-xs">
          {[['Category', p.data.category], ['Fund family', p.data.fund_family], ['Expense ratio', p.data.expense_ratio != null ? `${(p.data.expense_ratio > 0.2 ? p.data.expense_ratio : p.data.expense_ratio * 100).toFixed(2)}%` : null],
            ['Assets', p.data.total_assets != null ? fmtBig(p.data.total_assets) : null], ['Underlying', p.data.underlying], ['Exchange', q.exchange], ['Currency', q.currency]]
            .filter(([, v]) => v).map(([k, v]) => <div key={k as string}><dt className="text-text-tertiary">{k}</dt><dd className="text-text-primary">{v as string}</dd></div>)}</dl></Card>}
      </div>
      {isEquity && <Card title="Similar companies" right={<button onClick={() => onGo('RV', q.symbol)} className="text-[10px] text-bloomberg hover:underline">Compare all</button>}>
        <SimilarStocks symbol={q.symbol} onOpen={onOpen} /></Card>}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Card title="Latest news" right={<button onClick={() => onGo('CN', q.symbol)} className="text-[10px] text-bloomberg hover:underline">All news & filings</button>}><NewsList symbol={q.symbol} /></Card>
        <Card title="About">{p.data?.description ? <p className="text-xs text-text-secondary leading-relaxed line-clamp-[10]">{p.data.description}</p> : <p className="text-xs text-text-tertiary">No description.</p>}
          {p.data && <dl className="grid grid-cols-2 gap-2 mt-3 text-xs">
            {[['Sector', p.data.sector], ['Industry', p.data.industry], ['Country', p.data.country], ['Employees', p.data.employees?.toLocaleString()]]
              .filter(([, v]) => v).map(([k, v]) => <div key={k as string}><dt className="text-text-tertiary">{k}</dt><dd className="text-text-primary">{v as string}</dd></div>)}</dl>}</Card>
      </div>
    </div>
  );
}
