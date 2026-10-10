/**
 * The Markets region (Bloomberg-style GLOBAL / AMERICAS / EUROPE / MIDDLE EAST & AFRICA /
 * ASIA-PACIFIC). Screens default to it: the home monitor, movers, screener, heatmap, news,
 * economic and earnings calendars. Remembered per browser.
 */
import { useEffect, useState } from 'react';

export type Region = 'global' | 'americas' | 'europe' | 'mea' | 'apac';
export const REGIONS: { id: Region; label: string; short: string }[] = [
  { id: 'global', label: 'Global', short: 'GLOBAL' }, { id: 'americas', label: 'Americas', short: 'AMERICAS' },
  { id: 'europe', label: 'Europe', short: 'EUROPE' }, { id: 'mea', label: 'Middle East & Africa', short: 'MID EAST & AFRICA' },
  { id: 'apac', label: 'Asia-Pacific', short: 'ASIA-PACIFIC' },
];
// Lead screener market per region and the currencies whose releases the calendar shows
export const REGION_MARKETS: Record<Region, string[]> = {
  global: ['us', 'jp', 'gb', 'cn', 'de', 'in'], americas: ['us', 'ca', 'br', 'mx'], europe: ['gb', 'de', 'fr', 'ch', 'nl', 'it', 'es', 'se'],
  mea: ['sa', 'za'], apac: ['jp', 'cn', 'hk', 'in', 'kr', 'tw', 'au', 'sg'],
};
export const REGION_CCYS: Record<Region, string[]> = {
  global: [], americas: ['USD', 'CAD'], europe: ['EUR', 'GBP', 'CHF'], mea: [], apac: ['JPY', 'CNY', 'AUD', 'NZD'],
};
export const REGION_HEATMAP: Record<Region, string> = { global: 'US', americas: 'US', europe: 'GB', mea: 'SA', apac: 'JP' };

const KEY = 'mkt_region';
const EVT = 'mkt-region';

export function getRegion(): Region {
  try { const v = localStorage.getItem(KEY) as Region | null; return REGIONS.some((r) => r.id === v) ? (v as Region) : 'global'; } catch { return 'global'; }
}
export function setRegion(r: Region) {
  try { localStorage.setItem(KEY, r); } catch { /* storage unavailable */ }
  window.dispatchEvent(new CustomEvent(EVT, { detail: r }));
}
export function useRegion(): Region {
  const [r, setR] = useState<Region>(getRegion);
  useEffect(() => {
    const h = (e: Event) => setR((e as CustomEvent).detail as Region);
    window.addEventListener(EVT, h);
    return () => window.removeEventListener(EVT, h);
  }, []);
  return r;
}
