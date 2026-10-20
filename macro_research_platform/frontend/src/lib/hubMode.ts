/**
 * Hub mode: the app has two modes —
 *   'research' : Research & Trading (macro research, signals, risk, Quant Lab, the traders)
 *   'markets'  : Markets (universal search, any instrument's workstation, movers, screener)
 * Remembered per browser; `?mode=markets` or a `#mkt/...` link selects Markets.
 */
import { useEffect, useState } from 'react';

export type HubMode = 'research' | 'markets';
const KEY = 'hub_mode';
const EVT = 'hub-mode';

export function getHubMode(): HubMode {
  try {
    const q = new URLSearchParams(window.location.search).get('mode');
    if (q === 'markets' || q === 'research') return q;
    if (window.location.hash.startsWith('#mkt')) return 'markets';
    return localStorage.getItem(KEY) === 'markets' ? 'markets' : 'research';
  } catch { return 'research'; }
}

export function setHubMode(m: HubMode) {
  try { localStorage.setItem(KEY, m); } catch { /* storage unavailable */ }
  if (m === 'research' && window.location.hash.startsWith('#mkt')) history.replaceState(null, '', window.location.pathname + window.location.search);
  window.dispatchEvent(new CustomEvent(EVT, { detail: m }));
  window.scrollTo({ top: 0 });
}

export function useHubMode(): HubMode {
  const [m, setM] = useState<HubMode>(getHubMode);
  useEffect(() => {
    const h = (e: Event) => setM((e as CustomEvent).detail as HubMode);
    // A #mkt/... link (or Back into one) opens the Markets mode.
    const onHash = () => { if (window.location.hash.startsWith('#mkt')) setHubMode('markets'); };
    window.addEventListener(EVT, h);
    window.addEventListener('hashchange', onHash);
    return () => { window.removeEventListener(EVT, h); window.removeEventListener('hashchange', onHash); };
  }, []);
  return m;
}

/** Open an instrument in the Markets workstation from anywhere in the app. */
export function openInMarkets(symbol: string) {
  window.location.hash = `#mkt/ticker/${encodeURIComponent(symbol)}`;
  setHubMode('markets');
}
