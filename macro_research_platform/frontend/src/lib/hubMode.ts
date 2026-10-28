/**
 * Hub mode: the app is five separate areas, switched from the top bar —
 *   'macro'   : the macro model, regimes, signals, forecasts and the cycle   (dashboard panels)
 *   'trading' : ideas, pre-trade checks, positions, risk and governance       (dashboard panels)
 *   'quant'   : Quant Lab, Strategy Lab, backtests, model validation, data    (dashboard panels)
 *   'markets' : any instrument's workstation, movers, screener                (MarketsPage)
 *   'pe'      : private equity — LBO deal evaluation                          (PrivateEquityPage)
 * Remembered per browser; `?mode=…` or a `#mkt/...` link selects one. The old single 'research' mode (macro +
 * trading + quant together) is read as 'macro'.
 */
import { useEffect, useState } from 'react';

export type HubMode = 'macro' | 'trading' | 'quant' | 'markets' | 'pe';
export type DashboardMode = 'macro' | 'trading' | 'quant';
const MODES: HubMode[] = ['macro', 'trading', 'quant', 'markets', 'pe'];
const KEY = 'hub_mode';
const EVT = 'hub-mode';

export const HUB_MODES: { id: HubMode; label: string; title: string }[] = [
  { id: 'macro', label: 'Macro', title: 'The macro model, regimes, signals, forecasts and the cycle' },
  { id: 'trading', label: 'Trading', title: 'Ideas, pre-trade checks, positions, risk and governance' },
  { id: 'quant', label: 'Quant', title: 'Quant Lab, Strategy Lab, backtests, model validation and the data' },
  { id: 'markets', label: 'Markets', title: 'Any stock, ETF, index, FX, future or crypto — workstation, movers, screener' },
  { id: 'pe', label: 'PE', title: 'Private equity — LBO deal evaluation' },
];

/** The three areas built from dashboard panels (they share the Research dashboard page). */
export const isDashboardMode = (m: HubMode): m is DashboardMode => m === 'macro' || m === 'trading' || m === 'quant';

function parse(v: string | null): HubMode | null {
  if (v === 'research') return 'macro';
  return MODES.includes(v as HubMode) ? (v as HubMode) : null;
}

export function getHubMode(): HubMode {
  try {
    const q = parse(new URLSearchParams(window.location.search).get('mode'));
    if (q) return q;
    if (window.location.hash.startsWith('#mkt')) return 'markets';
    return parse(localStorage.getItem(KEY)) ?? 'macro';
  } catch { return 'macro'; }
}

export function setHubMode(m: HubMode) {
  try { localStorage.setItem(KEY, m); } catch { /* storage unavailable */ }
  if (m !== 'markets' && window.location.hash.startsWith('#mkt')) history.replaceState(null, '', window.location.pathname + window.location.search);
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
