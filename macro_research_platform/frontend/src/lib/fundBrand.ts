// The current fund's brand: its palette becomes the app's accent (and tints the dark canvas), and its logo shapes are
// drawn as CSS masks in the theme's colours — so the identity is part of the interface, not an image pasted on it.
import { useEffect, useState } from 'react';
import { currentFund } from '@/lib/fund';

export type Brand = { short_name?: string; tagline?: string; accent_dark?: string; accent_light?: string; bg_dark?: string;
  surface_dark?: string; secondary?: string; band?: string;
  mark_fill?: 'gradient' | 'text'; word_height?: number };
export type FundInfo = { id: string; name: string; base_currency?: string; benchmark?: string; logo?: boolean;
  logo_masks?: boolean; logo_version?: number; brand?: Brand | null };

const CACHE_KEY = 'macro.funds.cache';           // last fund list (brand, logo flags) so the look applies at first paint

export function cachedFunds(): FundInfo[] {
  try { return JSON.parse(localStorage.getItem(CACHE_KEY) || '[]'); } catch { return []; }
}

let fundsP: Promise<FundInfo[]> | null = null;
export function loadFunds(force = false): Promise<FundInfo[]> {
  if (!fundsP || force) {
    fundsP = fetch('/api/v1/funds').then((r) => (r.ok ? r.json() : null)).then((j) => {
      const fs: FundInfo[] = j?.funds ?? cachedFunds();
      if (j?.funds) { try { localStorage.setItem(CACHE_KEY, JSON.stringify(fs)); } catch { /* storage unavailable */ } }
      return fs;
    }).catch(() => cachedFunds());
  }
  return fundsP;
}

/** At startup, before the first render: the remembered brand of the selected fund (no flash of the default look). */
export function initBrand() {
  applyBrand(cachedFunds().find((f) => f.id === currentFund())?.brand);
}

const ch = (s: string) => s.split(' ').map(Number);
const mix = (a: string, b: string, t: number) => { const x = ch(a), y = ch(b); return x.map((v, i) => Math.round(v + (y[i] - v) * t)).join(' '); };

/** Apply the current fund's brand to <html> (CSS variables + data-brand); remove it for an unbranded fund. */
export function applyBrand(b: Brand | null | undefined) {
  const root = document.documentElement;
  if (!b?.accent_dark) { delete root.dataset.brand; return; }
  const bg = b.bg_dark ?? '6 9 12';
  const s1 = b.surface_dark ?? mix(bg, '255 255 255', 0.03);
  const v: Record<string, string> = {
    '--brand-accent-dark': b.accent_dark, '--brand-accent-light': b.accent_light ?? b.accent_dark,
    '--brand-bg-dark': bg, '--brand-surface-dark': s1, '--brand-surface2-dark': mix(s1, b.accent_dark, 0.035),
    '--brand-surface3-dark': mix(s1, b.accent_dark, 0.07), '--brand-border-dark': mix(s1, b.accent_dark, 0.16),
    '--brand-border-subtle-dark': mix(s1, b.accent_dark, 0.09), '--brand-secondary': b.secondary ?? b.accent_dark,
    '--brand-band': b.band ?? bg,
  };
  for (const [k, x] of Object.entries(v)) root.style.setProperty(k, x);
  root.dataset.brand = currentFund();
}

/** Call once when signed in. */
export function useApplyFundBrand() {
  useEffect(() => {
    loadFunds().then((fs) => applyBrand(fs.find((f) => f.id === currentFund())?.brand));
  }, []);
}

export function useCurrentFund(): FundInfo | null {
  const [f, setF] = useState<FundInfo | null>(() => cachedFunds().find((x) => x.id === currentFund()) ?? null);
  useEffect(() => { loadFunds().then((fs) => setF(fs.find((x) => x.id === currentFund()) ?? null)); }, []);
  return f;
}
