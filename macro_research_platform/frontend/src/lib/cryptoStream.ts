// Live crypto ticks streamed straight from Coinbase's free public WebSocket (no key, no server hop): every trade moves
// the price on the ticker tape, the top bar and a crypto security's header. One socket for the whole app, opened only
// while something listens, closed while the tab is hidden, reconnecting with back-off. Coins Coinbase does not list
// (BNB) simply never tick and keep the polled price.
import { useSyncExternalStore } from 'react';

export type CryptoTick = { price: number; time: string };

const WS_URL = 'wss://ws-feed.exchange.coinbase.com';
const NOTIFY_MS = 400;                            // at most ~2.5 repaints a second per coin, however busy the tape
const latest = new Map<string, CryptoTick>();     // 'BTC' → last trade
const listeners = new Map<string, Set<() => void>>();
const dirty = new Set<string>();
let ws: WebSocket | null = null;
let retry = 0;
let reconnect: ReturnType<typeof setTimeout> | null = null;
let flush: ReturnType<typeof setTimeout> | null = null;

/** 'BTC-USD' → 'BTC'; null for anything that is not a USD crypto pair. */
export function coinOf(symbol: string | null | undefined): string | null {
  const s = (symbol ?? '').toUpperCase();
  return s.endsWith('-USD') && s.length > 4 && !s.includes('=') ? s.slice(0, -4) : null;
}

function wanted(): string[] { return [...listeners.keys()].filter((c) => listeners.get(c)!.size); }

function send(coins: string[], type: 'subscribe' | 'unsubscribe') {
  if (ws?.readyState !== WebSocket.OPEN) return;
  // One message per product: Coinbase rejects a whole subscribe when any product in it is unknown.
  for (const c of coins) ws.send(JSON.stringify({ type, product_ids: [`${c}-USD`], channels: ['ticker'] }));
}

function scheduleFlush() {
  if (flush) return;
  flush = setTimeout(() => {
    flush = null;
    const coins = [...dirty]; dirty.clear();
    for (const c of coins) listeners.get(c)?.forEach((l) => l());
  }, NOTIFY_MS);
}

function open() {
  if (ws || typeof WebSocket === 'undefined' || !wanted().length) return;
  if (typeof document !== 'undefined' && document.hidden) return;
  try { ws = new WebSocket(WS_URL); } catch { ws = null; return; }
  ws.onopen = () => { retry = 0; send(wanted(), 'subscribe'); };
  ws.onmessage = (e) => {
    try {
      const m = JSON.parse(e.data);
      if (m.type !== 'ticker' || !m.price || !m.product_id) return;
      const coin = String(m.product_id).replace(/-USD$/, '');
      const price = Number(m.price);
      if (!Number.isFinite(price) || latest.get(coin)?.price === price) return;
      latest.set(coin, { price, time: m.time ?? new Date().toISOString() });
      dirty.add(coin); scheduleFlush();
    } catch { /* ignore a malformed frame */ }
  };
  ws.onclose = () => {
    ws = null;
    if (!wanted().length || (typeof document !== 'undefined' && document.hidden)) return;
    const wait = Math.min(30_000, 1000 * 2 ** retry++);
    reconnect = setTimeout(() => { reconnect = null; open(); }, wait);
  };
  ws.onerror = () => { try { ws?.close(); } catch { /* closing anyway */ } };
}

function close() {
  if (reconnect) { clearTimeout(reconnect); reconnect = null; }
  const s = ws; ws = null;
  if (s) { s.onclose = null; try { s.close(); } catch { /* already closed */ } }
}

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => (document.hidden ? close() : open()));
}

/** Listen to one coin's trades; returns the unsubscribe. */
export function subscribeCoin(coin: string, l: () => void): () => void {
  const c = coin.toUpperCase();
  let set = listeners.get(c);
  if (!set) listeners.set(c, (set = new Set()));
  const first = set.size === 0;
  set.add(l);
  if (!ws) open(); else if (first) send([c], 'subscribe');
  return () => {
    set!.delete(l);
    if (!set!.size) { send([c], 'unsubscribe'); if (!wanted().length) close(); }
  };
}

export function lastTick(coin: string): CryptoTick | null { return latest.get(coin.toUpperCase()) ?? null; }

const noop = () => () => {};
/** The latest streamed trade for a USD crypto symbol ('ETH-USD'), or null (not crypto / no trade yet). */
export function useCryptoTick(symbol: string | null | undefined): CryptoTick | null {
  const coin = coinOf(symbol);
  return useSyncExternalStore(coin ? (l) => subscribeCoin(coin, l) : noop, () => (coin ? latest.get(coin) ?? null : null), () => null);
}

/** A quote with the streamed price laid over it; the change stays against the quote's own previous close. */
export function useLiveQuote<T extends { symbol?: string; price?: number | null; previous_close?: number | null } | null>(d: T): T {
  const t = useCryptoTick(d?.symbol);
  if (!d || !t || !d.price || Math.abs(t.price / d.price - 1) > 0.25) return d;   // guard: a different coin's ticker
  const prev = d.previous_close;
  return { ...d, price: t.price, delay_minutes: 0, quote_time: t.time, streaming: true,
    ...(prev ? { change: t.price - prev, change_pct: t.price / prev - 1 } : {}) };
}
