/**
 * Colour theme: 'auto' (light 07:00–19:00 local time, dark otherwise — re-checked every
 * minute so it flips at the boundary), or a fixed 'light' / 'dark'. Remembered per browser.
 * Applies `data-theme` on <html>; colours come from CSS channel variables (index.css).
 */
import { useEffect, useState } from 'react';

export type ThemeSetting = 'auto' | 'light' | 'dark';
export type Theme = 'light' | 'dark';
const KEY = 'ui_theme';
const EVT = 'ui-theme';
export const DAY_START = 7;    // 07:00 local
export const DAY_END = 19;     // 19:00 local

export function getThemeSetting(): ThemeSetting {
  try {
    const v = localStorage.getItem(KEY);
    return v === 'light' || v === 'dark' || v === 'auto' ? v : 'auto';
  } catch { return 'auto'; }
}

export function themeFor(setting: ThemeSetting, now: Date = new Date()): Theme {
  if (setting !== 'auto') return setting;
  const h = now.getHours();
  return h >= DAY_START && h < DAY_END ? 'light' : 'dark';
}

export function applyTheme(t: Theme) {
  const root = document.documentElement;
  if (root.dataset.theme !== t) root.dataset.theme = t;
}

let timer: ReturnType<typeof setInterval> | null = null;

/** Call once at startup (before first render, to avoid a flash). */
export function initTheme() {
  applyTheme(themeFor(getThemeSetting()));
  if (timer) clearInterval(timer);
  timer = setInterval(() => applyTheme(themeFor(getThemeSetting())), 60_000);
}

export function setThemeSetting(s: ThemeSetting) {
  try { localStorage.setItem(KEY, s); } catch { /* storage unavailable */ }
  applyTheme(themeFor(s));
  window.dispatchEvent(new CustomEvent(EVT, { detail: s }));
}

export function useTheme(): { setting: ThemeSetting; theme: Theme } {
  const [setting, setS] = useState<ThemeSetting>(getThemeSetting);
  const [theme, setT] = useState<Theme>(() => themeFor(getThemeSetting()));
  useEffect(() => {
    const h = (e: Event) => { const s = (e as CustomEvent).detail as ThemeSetting; setS(s); setT(themeFor(s)); };
    const tick = setInterval(() => setT(themeFor(getThemeSetting())), 60_000);
    window.addEventListener(EVT, h);
    return () => { window.removeEventListener(EVT, h); clearInterval(tick); };
  }, []);
  return { setting, theme };
}

// ── Markets skin: 'classic' (black terminal) or 'modern' (follows the theme) ──
export type MarketsSkin = 'classic' | 'modern';
const SKIN_KEY = 'mkt_skin_v2';          // v2: the classic terminal look is the default again
const SKIN_EVT = 'mkt-skin';
export function getMarketsSkin(): MarketsSkin {
  try { return localStorage.getItem(SKIN_KEY) === 'modern' ? 'modern' : 'classic'; } catch { return 'classic'; }
}
export function setMarketsSkin(s: MarketsSkin) {
  try { localStorage.setItem(SKIN_KEY, s); } catch { /* storage unavailable */ }
  window.dispatchEvent(new CustomEvent(SKIN_EVT, { detail: s }));
}
export function useMarketsSkin(): MarketsSkin {
  const [s, setS] = useState<MarketsSkin>(getMarketsSkin);
  useEffect(() => {
    const h = (e: Event) => setS((e as CustomEvent).detail as MarketsSkin);
    window.addEventListener(SKIN_EVT, h);
    return () => window.removeEventListener(SKIN_EVT, h);
  }, []);
  return s;
}
/** Applies the terminal skin to <html> while `on` (the Markets mode with the classic skin). */
export function applySkin(on: boolean) {
  const root = document.documentElement;
  if (on) root.dataset.skin = 'terminal'; else delete root.dataset.skin;
}

// ── Up/down colours: 'green' (US/Europe: green = up) or 'red' (HK/China/Japan/Korea: red = up) ──
export type UpDown = 'green' | 'red';
const UD_KEY = 'mkt_updown';
const UD_EVT = 'mkt-updown';
export function getUpDown(): UpDown {
  try { return localStorage.getItem(UD_KEY) === 'red' ? 'red' : 'green'; } catch { return 'green'; }
}
export function applyUpDown(u: UpDown = getUpDown()) {
  const root = document.documentElement;
  if (u === 'red') root.dataset.updown = 'red'; else delete root.dataset.updown;
}
export function setUpDown(u: UpDown) {
  try { localStorage.setItem(UD_KEY, u); } catch { /* storage unavailable */ }
  applyUpDown(u);
  window.dispatchEvent(new CustomEvent(UD_EVT, { detail: u }));
}
export function useUpDown(): UpDown {
  const [u, setU] = useState<UpDown>(getUpDown);
  useEffect(() => {
    const h = (e: Event) => setU((e as CustomEvent).detail as UpDown);
    window.addEventListener(UD_EVT, h);
    return () => window.removeEventListener(UD_EVT, h);
  }, []);
  return u;
}
