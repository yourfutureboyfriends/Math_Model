// One shared, polled feed of the world-markets overview (/api/v1/mkt/overview) for the screen chrome — the topbar
// quote strip and the ticker tape both read it, so the server is asked once a minute however many widgets show it.
// Polling pauses while the tab is hidden and stops when nothing is subscribed.
import { useSyncExternalStore } from 'react';

export type PulseRow = {
  symbol: string; name: string; price: number | null; date?: string;
  change_1d?: number | null; change_1d_bp?: number | null; is_yield?: boolean; spark?: number[];
};
export type PulseState = { rows: Record<string, PulseRow>; asOf: string | null; status: 'loading' | 'ok' | 'error' };

const POLL_MS = 60_000;
let state: PulseState = { rows: {}, asOf: null, status: 'loading' };
const listeners = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | null = null;

async function load(): Promise<void> {
  if (typeof document !== 'undefined' && document.hidden && state.status === 'ok') return;
  try {
    const r = await fetch('/api/v1/mkt/overview');
    if (!r.ok) throw new Error(String(r.status));
    const j = await r.json();
    const rows: Record<string, PulseRow> = {};
    for (const g of j.groups ?? []) for (const row of g.rows ?? []) rows[row.symbol] = row;
    state = { rows, asOf: j.as_of ?? null, status: 'ok' };
  } catch {
    state = { ...state, status: 'error' };            // keep the last good quotes on screen
  }
  listeners.forEach((l) => l());
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  if (!timer) { load(); timer = setInterval(load, POLL_MS); }
  return () => {
    listeners.delete(l);
    if (!listeners.size && timer) { clearInterval(timer); timer = null; }
  };
}

/** The latest world-markets snapshot; re-renders when a poll lands. */
export function useMarketPulse(): PulseState {
  return useSyncExternalStore(subscribe, () => state, () => state);
}

// ── Display helpers shared by the strip and the tape ──────────────────────────────────────────────

/** Terminal-style short codes (Bloomberg-like tickers) for the overview's Yahoo symbols. */
export const SHORT: Record<string, string> = {
  '^GSPC': 'SPX', '^NDX': 'NDX', '^DJI': 'INDU', '^RUT': 'RTY', '^GSPTSE': 'SPTSX', '^BVSP': 'IBOV', '^STOXX50E': 'SX5E',
  '^FTSE': 'UKX', '^GDAXI': 'DAX', '^FCHI': 'CAC', '^N225': 'NKY', '^HSI': 'HSI', '000001.SS': 'SHCOMP', '^KS11': 'KOSPI',
  '^TWII': 'TWSE', '^BSESN': 'SENSEX', '^AXJO': 'AS51', '^IRX': 'UST3M', '^FVX': 'UST5Y', '^TNX': 'UST10Y', '^TYX': 'UST30Y',
  '^VIX': 'VIX', '^MOVE': 'MOVE', 'DX-Y.NYB': 'DXY', 'EURUSD=X': 'EURUSD', 'GBPUSD=X': 'GBPUSD', 'JPY=X': 'USDJPY',
  'CHF=X': 'USDCHF', 'AUDUSD=X': 'AUDUSD', 'CAD=X': 'USDCAD', 'CNY=X': 'USDCNY', 'INR=X': 'USDINR', 'MXN=X': 'USDMXN',
  'BRL=X': 'USDBRL', 'CL=F': 'WTI', 'BZ=F': 'BRENT', 'NG=F': 'NATGAS', 'GC=F': 'GOLD', 'SI=F': 'SILVER', 'HG=F': 'COPPER',
  'PL=F': 'PLAT', 'ZC=F': 'CORN', 'ZW=F': 'WHEAT', 'ZS=F': 'SOYB', 'KC=F': 'COFFEE', 'CT=F': 'COTTON', 'BTC-USD': 'BTC',
  'ETH-USD': 'ETH', 'SOL-USD': 'SOL', 'XRP-USD': 'XRP', 'BNB-USD': 'BNB', 'DOGE-USD': 'DOGE',
};

/** Tape sections in the order the trading day travels round the world: Asia-Pacific opens first, then Europe,
 *  then the Americas — followed by the cross-border markets (rates, FX, commodities, crypto). */
export const TAPE_SECTIONS: { tag: string; symbols: string[] }[] = [
  { tag: 'ASIA-PAC', symbols: ['^N225', '^HSI', '000001.SS', '^KS11', '^TWII', '^BSESN', '^AXJO'] },
  { tag: 'EMEA', symbols: ['^STOXX50E', '^FTSE', '^GDAXI', '^FCHI'] },
  { tag: 'AMERICAS', symbols: ['^GSPC', '^NDX', '^DJI', '^RUT', '^GSPTSE', '^BVSP'] },
  { tag: 'RATES·VOL', symbols: ['^IRX', '^FVX', '^TNX', '^TYX', '^VIX', '^MOVE'] },
  { tag: 'FX', symbols: ['DX-Y.NYB', 'EURUSD=X', 'GBPUSD=X', 'JPY=X', 'CHF=X', 'AUDUSD=X', 'CAD=X', 'CNY=X', 'INR=X', 'MXN=X', 'BRL=X'] },
  { tag: 'CMDTY', symbols: ['BZ=F', 'CL=F', 'NG=F', 'GC=F', 'SI=F', 'HG=F', 'PL=F', 'ZC=F', 'ZW=F', 'ZS=F', 'KC=F', 'CT=F'] },
  { tag: 'CRYPTO', symbols: ['BTC-USD', 'ETH-USD', 'SOL-USD', 'XRP-USD', 'BNB-USD', 'DOGE-USD'] },
];

/** The topbar's at-a-glance board: one benchmark per major region, then the global macro gauges. */
export const STRIP_SYMBOLS = ['^GSPC', '^STOXX50E', '^FTSE', '^N225', '^HSI', '000001.SS', '^TNX', '^VIX', 'DX-Y.NYB',
  'EURUSD=X', 'JPY=X', 'GC=F', 'BZ=F', 'BTC-USD'];

export function fmtPulsePrice(r: PulseRow): string {
  if (r.price == null) return '—';
  const p = r.price;
  if (r.is_yield) return `${p.toFixed(3)}%`;
  const a = Math.abs(p);
  const d = a >= 1000 ? 0 : a >= 100 ? 2 : a >= 1 ? (r.symbol.endsWith('=X') ? 4 : 2) : 4;
  return p.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
}

/** Day change as text (bp for yields, % otherwise) and its direction (−1, 0, +1). */
export function fmtPulseChange(r: PulseRow): { text: string; dir: number } {
  if (r.is_yield && r.change_1d_bp != null) {
    const v = r.change_1d_bp;
    return { text: `${v >= 0 ? '+' : ''}${v.toFixed(1)}bp`, dir: Math.sign(Math.round(v * 10)) };
  }
  if (r.change_1d == null) return { text: '', dir: 0 };
  const v = r.change_1d * 100;
  return { text: `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`, dir: Math.sign(Math.round(v * 100)) };
}
