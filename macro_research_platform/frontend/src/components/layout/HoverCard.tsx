// Security hover cards: rest the pointer on a ticker anywhere — the tape, the quote board, a table cell — and a card
// shows its quote (price, day change, day and 52-week ranges, volume vs average, market cap), a 1-year sparkline,
// the fund's position in it, and actions: Chart, News, Description and a one-line price alert.
//
// What counts as a ticker: any element with data-symbol="…" (set by the tape, the board and some tables), or a
// short monospace leaf cell inside a panel whose text looks like a symbol (AAPL, ^N225, EURUSD=X, BTC-USD, 7203.T):
// 2–12 characters, not a chart period (1M, 3Y), not a plain word longer than five letters (REFLATION) and not a
// common table word, region or currency code. The card only opens when the quote service recognises the
// symbol, so a false candidate costs one cached lookup and shows nothing. Esc or moving away closes it.
import { useCallback, useEffect, useRef, useState } from 'react';
import { BarChart3, Bell, FileText, Newspaper } from 'lucide-react';
import { openChart } from '@/components/ui/ChartModal';
import { goMarkets } from '@/lib/marketsRoute';
import { pushPopup } from '@/lib/popups';
import { cn } from '@/lib/utils';

const DWELL_MS = 450, CLOSE_MS = 220, TTL_MS = 60_000;
const TICKER = /^(?=.*[A-Z])[A-Z0-9^][A-Z0-9.\-=^]{0,11}$/;
const STOP = new Set(('BUY SELL LONG SHORT HOLD OK NA N/A HIGH LOW MED MEDIUM WARN BLOCK PASS FAIL CASH ETF UTC LIVE AUTO ' +
  'YES NO ON OFF NEW OPEN CLOSED PRE POST ALL TOTAL NAV PNL VAR CVAR ES PM QUANT RISK ADMIN GO MOVE NEWS ECO MIN MAX ' +
  'AVG YTD MTD QTD YOY MOM DES CN GP HP TAPE ALERTS LINK POLL DATA DLYD WORLD REGIME UP DOWN FLAT STALE DONE IDEA ' +
  'US EA ROW EU UK EM DM APAC EMEA AMER G7 G10 ' +
  'DE JP CA AU GB FR IT ES CN IN BR MX KR CH SE NL HK SG TW ZA SA ' +             // country codes (DE is also Deere)
  'GC CL NQ TY HY IG FX ' +                                                   // futures roots and labels (CL is also Colgate)
  'USD EUR GBP JPY CHF CNY HKD AUD CAD NZD SEK NOK DKK INR KRW BRL MXN ZAR SGD TWD').split(' '));

type Quote = Record<string, any>;
const quoteCache = new Map<string, { at: number; q: Quote | null }>();
const sparkCache = new Map<string, { at: number; s: number[] }>();
let positionsCache: { at: number; rows: any[] } | null = null;

async function getQuote(sym: string): Promise<Quote | null> {
  const hit = quoteCache.get(sym);
  if (hit && Date.now() - hit.at < TTL_MS) return hit.q;
  let q: Quote | null = null;
  try {
    const r = await fetch(`/api/v1/mkt/quote/${encodeURIComponent(sym)}`);
    q = r.ok ? await r.json() : null;
    if (q && q.price == null) q = null;
  } catch { q = null; }
  quoteCache.set(sym, { at: Date.now(), q });
  return q;
}

async function getSpark(sym: string): Promise<number[]> {
  const hit = sparkCache.get(sym);
  if (hit && Date.now() - hit.at < 10 * TTL_MS) return hit.s;
  try {
    const j = await (await fetch(`/api/v1/mkt/hp/${encodeURIComponent(sym)}?period=1y&interval=1wk`)).json();
    const s = (j.rows ?? []).map((r: any) => r.close).filter((v: any) => typeof v === 'number');
    sparkCache.set(sym, { at: Date.now(), s });
    return s;
  } catch { return []; }
}

async function getPosition(sym: string): Promise<any[]> {
  if (!positionsCache || Date.now() - positionsCache.at > TTL_MS) {
    try {
      const j = await (await fetch('/api/v1/portfolio/positions')).json();
      positionsCache = { at: Date.now(), rows: j.positions ?? [] };
    } catch { positionsCache = { at: Date.now(), rows: [] }; }
  }
  return positionsCache.rows.filter((p) => String(p.symbol).toUpperCase() === sym);
}

/** The ticker an element stands for, or null. */
export function symbolOf(el: Element | null): string | null {
  if (!el) return null;
  const tagged = el.closest('[data-symbol]');
  if (tagged) return (tagged.getAttribute('data-symbol') || '').toUpperCase() || null;
  const leaf = el as HTMLElement;
  if (leaf.childElementCount > 0 || !leaf.closest('.terminal-section, .mkt-root')) return null;
  if (!leaf.closest('td, .font-mono') && !leaf.classList.contains('font-mono')) return null;
  const t = (leaf.textContent || '').trim();
  if (t.length < 2 || t.length > 12 || !TICKER.test(t) || STOP.has(t)) return null;
  if (/^\d+[DWMQY]$/.test(t)) return null;                 // chart periods: 1M, 3Y …
  if (/^[\d.,]+[KMBT]$/.test(t)) return null;              // abbreviated numbers: 19.6K, 2.3B
  if (/^[A-Z]+$/.test(t) && t.length > 5) return null;     // plain words (REFLATION, BULLISH); real tickers are ≤ 5 letters
  return t;
}

const fmt = (v: number | null | undefined, d = 2) =>
  v == null || !Number.isFinite(v) ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const big = (v?: number | null) => (v == null ? '—' : v >= 1e12 ? `${(v / 1e12).toFixed(2)}T` : v >= 1e9 ? `${(v / 1e9).toFixed(1)}B` : v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : fmt(v, 0));
const decimals = (p?: number) => (p == null ? 2 : Math.abs(p) >= 1000 ? 0 : Math.abs(p) >= 1 ? 2 : 4);

function Spark({ s }: { s: number[] }) {
  if (s.length < 2) return <div className="h-10" />;
  const w = 268, h = 40, lo = Math.min(...s), hi = Math.max(...s), span = hi - lo || 1;
  const pts = s.map((v, i) => `${((i / (s.length - 1)) * w).toFixed(1)},${(h - ((v - lo) / span) * (h - 4) - 2).toFixed(1)}`).join(' ');
  const up = s[s.length - 1] >= s[0];
  const col = up ? 'rgb(var(--c-green))' : 'rgb(var(--c-red))';
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-label="One-year price">
      <polygon points={`0,${h} ${pts} ${w},${h}`} fill={col} opacity={0.08} />
      <polyline points={pts} fill="none" stroke={col} strokeWidth={1.4} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function Range({ lo, hi, v, label }: { lo?: number; hi?: number; v?: number; label: string }) {
  if (lo == null || hi == null || v == null || hi <= lo) return null;
  const x = Math.min(100, Math.max(0, ((v - lo) / (hi - lo)) * 100));
  const d = decimals(v);
  return (
    <div className="text-[10px]">
      <div className="flex justify-between text-text-tertiary"><span>{label}</span><span className="font-mono">{fmt(lo, d)} – {fmt(hi, d)}</span></div>
      <div className="relative h-1 mt-0.5 bg-surface-3 rounded-full">
        <span className="absolute top-1/2 w-2 h-2 -mt-1 -ml-1 rounded-full bg-bloomberg" style={{ left: `${x}%` }} />
      </div>
    </div>
  );
}

function AlertForm({ sym, price, onDone }: { sym: string; price?: number; onDone: () => void }) {
  const [kind, setKind] = useState<'above' | 'below'>('above');
  const [value, setValue] = useState(() => (price ? String(+(price * 1.05).toPrecision(5)) : ''));
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (price) setValue(String(+(price * (kind === 'above' ? 1.05 : 0.95)).toPrecision(5))); }, [kind, price]);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    try {
      const r = await fetch('/api/v1/mkt/alerts', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: sym, kind, value: Number(value) }) });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : `HTTP ${r.status}`);
      pushPopup({ id: `alert-set:${sym}:${kind}:${value}:${Date.now()}`, kind: 'alert', title: `Alert set: ${sym} ${kind} ${value}`,
        body: 'Checked every five minutes; it pops up here when it triggers.', tone: 'neutral' });
      onDone();
    } catch (e2: any) { setErr(e2?.message || 'Could not set the alert'); }
  };
  return (
    <form onSubmit={submit} className="mt-2 pt-2 border-t border-border-subtle">
      <div className="flex items-center gap-1">
        <select value={kind} onChange={(e) => setKind(e.target.value as 'above' | 'below')} aria-label="Condition"
          className="bg-bg border border-border text-[11px] px-1 py-0.5 text-text-primary">
          <option value="above">Rises above</option><option value="below">Falls below</option>
        </select>
        <input value={value} onChange={(e) => setValue(e.target.value)} inputMode="decimal" aria-label="Price level"
          className="w-20 bg-bg border border-border text-[11px] font-mono px-1 py-0.5 text-text-primary" />
        <button type="submit" className="ml-auto px-2 py-0.5 text-[11px] bg-bloomberg text-bg">Set alert</button>
      </div>
      {err && <div className="mt-1 text-[10px] text-red">{err}</div>}
    </form>
  );
}

type Card = { sym: string; rect: DOMRect };

export function HoverCards() {
  const [card, setCard] = useState<Card | null>(null);
  const [q, setQ] = useState<Quote | null>(null);
  const [spark, setSpark] = useState<number[]>([]);
  const [pos, setPos] = useState<any[]>([]);
  const [alertOpen, setAlertOpen] = useState(false);
  const dwell = useRef<ReturnType<typeof setTimeout>>();
  const closer = useRef<ReturnType<typeof setTimeout>>();
  const current = useRef<string | null>(null);
  const pending = useRef<string | null>(null);     // the ticker under the pointer right now

  const close = useCallback(() => { setCard(null); setQ(null); setAlertOpen(false); current.current = null; }, []);

  useEffect(() => {
    const over = (e: MouseEvent) => {
      const target = e.target as Element;
      if (target.closest?.('.hover-card')) { clearTimeout(closer.current); return; }
      const sym = symbolOf(target);
      pending.current = sym;
      clearTimeout(dwell.current);
      if (!sym) { if (current.current) { clearTimeout(closer.current); closer.current = setTimeout(close, CLOSE_MS); } return; }
      if (sym === current.current) { clearTimeout(closer.current); return; }
      const anchor = (target.closest('[data-symbol]') ?? target) as Element;
      dwell.current = setTimeout(async () => {
        const quote = await getQuote(sym);
        if (!quote || pending.current !== sym) return;   // unknown to the quote service, or the pointer moved on
        current.current = sym;
        setCard({ sym, rect: anchor.getBoundingClientRect() });
        setQ(quote); setSpark([]); setPos([]); setAlertOpen(false);
        getSpark(sym).then((s) => current.current === sym && setSpark(s));
        getPosition(sym).then((p) => current.current === sym && setPos(p));
      }, DWELL_MS);
    };
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') close(); };
    const scroll = () => { if (current.current) close(); };
    document.addEventListener('mouseover', over);
    window.addEventListener('keydown', key);
    window.addEventListener('scroll', scroll, { passive: true, capture: true });
    return () => {
      document.removeEventListener('mouseover', over);
      window.removeEventListener('keydown', key);
      window.removeEventListener('scroll', scroll, { capture: true });
      clearTimeout(dwell.current); clearTimeout(closer.current);
    };
  }, [close]);

  if (!card || !q) return null;
  const W = 300;
  const below = card.rect.bottom + 8 + 300 < window.innerHeight;
  const left = Math.min(Math.max(8, card.rect.left), window.innerWidth - W - 8);
  const style: React.CSSProperties = below ? { top: card.rect.bottom + 6, left, width: W } : { bottom: window.innerHeight - card.rect.top + 6, left, width: W };
  const d = decimals(q.price);
  const chg = q.change_pct;
  const sym = card.sym;
  const isSecurity = q.type === 'EQUITY' || q.type === 'ETF';
  return (
    <div className="hover-card" style={style} role="dialog" aria-label={`${sym} quote`}
      onMouseEnter={() => clearTimeout(closer.current)} onMouseLeave={() => { closer.current = setTimeout(close, CLOSE_MS); }}>
      <div className="flex items-baseline gap-2">
        <span className="font-mono font-bold text-text-primary text-sm">{q.symbol ?? sym}</span>
        <span className="text-[10px] text-text-tertiary truncate">{[q.exchange, q.currency, q.type].filter(Boolean).join(' · ')}</span>
        <span className={cn('ml-auto text-[9px] font-mono px-1 border', q.delay_minutes ? 'border-border text-text-tertiary' : 'border-green/50 text-green')}>
          {q.delay_minutes ? `${q.delay_minutes}m DELAY` : q.market_state === 'REGULAR' ? 'LIVE' : (q.market_state || 'LAST')}</span>
      </div>
      <div className="text-[11px] text-text-secondary truncate">{q.name}</div>
      <div className="flex items-baseline gap-2 mt-1">
        <span className="font-mono text-xl font-semibold text-text-primary">{fmt(q.price, d)}</span>
        <span className={cn('font-mono text-xs', chg > 0 ? 'text-green' : chg < 0 ? 'text-red' : 'text-text-tertiary')}>
          {chg > 0 ? '▲' : chg < 0 ? '▼' : ''} {q.change != null ? `${q.change > 0 ? '+' : ''}${fmt(q.change, d)}` : ''} ({chg != null ? `${chg > 0 ? '+' : ''}${(chg * 100).toFixed(2)}%` : '—'})
        </span>
      </div>
      <Spark s={spark} />
      <div className="space-y-1.5 mt-1">
        <Range lo={q.day_low} hi={q.day_high} v={q.price} label="Day range" />
        <Range lo={q.week52_low} hi={q.week52_high} v={q.price} label="52-week range" />
      </div>
      <div className="grid grid-cols-2 gap-x-3 mt-1.5 text-[10px] text-text-tertiary">
        {q.market_cap != null && <span>Mkt cap <span className="font-mono text-text-secondary">{big(q.market_cap)}</span></span>}
        {q.volume != null && <span>Volume <span className="font-mono text-text-secondary">{big(q.volume)}</span>
          {q.volume_ratio != null && <span className={q.volume_ratio > 1.5 ? 'text-amber' : ''}> ({q.volume_ratio.toFixed(1)}× avg)</span>}</span>}
        {q.trailing_pe != null && <span>P/E <span className="font-mono text-text-secondary">{fmt(q.trailing_pe, 1)}</span></span>}
        {q.dividend_yield != null && <span>Yield <span className="font-mono text-text-secondary">{(q.dividend_yield * 100).toFixed(2)}%</span></span>}
      </div>
      {pos.length > 0 && (
        <div className="mt-1.5 p-1.5 border border-bloomberg/40 bg-bloomberg/5 text-[10px]">
          <span className="text-bloomberg font-semibold">IN THE BOOK </span>
          {pos.map((p, i) => (
            <span key={i} className="font-mono text-text-secondary">{i ? ' · ' : ''}{p.quantity} @ {fmt(p.avg_cost, d)}{p.book ? ` (${p.book})` : ''}
              {p.unrealized_pnl != null && <span className={p.unrealized_pnl >= 0 ? 'text-green' : 'text-red'}> {p.unrealized_pnl >= 0 ? '+' : ''}{fmt(p.unrealized_pnl, 0)}</span>}</span>
          ))}
        </div>
      )}
      <div className="flex gap-1 mt-2">
        <button type="button" className="hover-card-btn" onClick={() => { openChart(sym, q.name); close(); }}><BarChart3 className="w-3 h-3" />Chart</button>
        {isSecurity && <button type="button" className="hover-card-btn" onClick={() => { goMarkets('CN', sym); close(); }}><Newspaper className="w-3 h-3" />News</button>}
        <button type="button" className="hover-card-btn" onClick={() => { goMarkets('DES', sym); close(); }}><FileText className="w-3 h-3" />Describe</button>
        <button type="button" className={cn('hover-card-btn ml-auto', alertOpen && 'border-bloomberg text-bloomberg')} onClick={() => setAlertOpen((v) => !v)}><Bell className="w-3 h-3" />Alert</button>
      </div>
      {alertOpen && <AlertForm sym={sym} price={q.price} onDone={() => setAlertOpen(false)} />}
      <div className="mt-1.5 text-[9px] text-text-tertiary truncate">{q.source}</div>
    </div>
  );
}
