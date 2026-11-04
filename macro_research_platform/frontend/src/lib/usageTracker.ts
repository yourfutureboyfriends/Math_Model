/**
 * Screen usage (api/usage.py): which dashboard panels and Markets functions are actually read, so screens can be
 * retired or folded into workflows on evidence. A panel counts as viewed once it has stayed at least 40% on screen
 * for 3 seconds; a Markets function counts when opened. Once per screen per page load, with the seconds in view.
 * Nothing about what was on the screen is sent. Batched every minute and when the tab is hidden.
 */
import { FUNCTIONS } from '@/components/markets/functions';
import { getHubMode } from '@/lib/hubMode';

type Ev = { screen: string; seconds: number; views: number };
const DWELL_MS = 3000;
const pending = new Map<string, Ev>();
const counted = new Set<string>();
let known: { screen: string; label: string; area: string }[] = [];
const knownSent = new Set<string>();

function add(screen: string, seconds: number, view: boolean) {
  const e = pending.get(screen) ?? { screen, seconds: 0, views: 0 };
  e.seconds += Math.round(seconds);
  if (view && !counted.has(screen)) { counted.add(screen); e.views += 1; }
  if (e.views || e.seconds) pending.set(screen, e);
}

function flush() {
  const events = [...pending.values()].filter((e) => e.views || e.seconds >= 1);
  const fresh = known.filter((k) => !knownSent.has(k.screen));
  if (!events.length && !fresh.length) return;
  pending.clear();
  fresh.forEach((k) => knownSent.add(k.screen));
  fetch('/api/v1/usage', { method: 'POST', headers: { 'Content-Type': 'application/json' }, keepalive: true,
    body: JSON.stringify({ events, known: fresh }) }).catch(() => { /* usage is best-effort */ });
}

function registerPanels() {
  const area = getHubMode();
  const label = (el: HTMLElement) =>
    (el.querySelector('[data-panel-head] h2, [data-panel-head] h3, [data-panel-header], h2, h3')?.textContent ?? el.id).trim().slice(0, 80);
  const seen = new Set(known.map((k) => k.screen));
  document.querySelectorAll<HTMLElement>('.terminal-section[id]').forEach((el) => {
    const s = `dash:${el.id}`;
    if (!seen.has(s)) known.push({ screen: s, label: label(el), area });
  });
}

export function startUsageTracking(): () => void {
  if (typeof window === 'undefined' || typeof IntersectionObserver === 'undefined') return () => {};
  known = FUNCTIONS.map((f) => ({ screen: `mkt:${f.code}`, label: f.name ?? f.code, area: 'markets' }));
  // panels: dwell timers
  const since = new Map<string, number>();
  const timers = new Map<string, number>();
  const io = new IntersectionObserver((entries) => {
    const now = Date.now();
    for (const en of entries) {
      const s = `dash:${(en.target as HTMLElement).id}`;
      if (en.isIntersecting && en.intersectionRatio >= 0.4) {
        if (!since.has(s)) {
          since.set(s, now);
          timers.set(s, window.setTimeout(() => add(s, 0, true), DWELL_MS));
        }
      } else if (since.has(s)) {
        const ms = now - since.get(s)!;
        clearTimeout(timers.get(s));
        since.delete(s);
        if (ms >= DWELL_MS) add(s, ms / 1000, false);
      }
    }
  }, { threshold: [0, 0.4] });
  const observed = new WeakSet<Element>();
  const scan = () => {
    document.querySelectorAll<HTMLElement>('.terminal-section[id]').forEach((el) => { if (!observed.has(el)) { observed.add(el); io.observe(el); } });
    registerPanels();
  };
  let pendingScan = 0;
  const mo = new MutationObserver(() => { if (!pendingScan) pendingScan = window.setTimeout(() => { pendingScan = 0; scan(); }, 1000); });
  mo.observe(document.body, { childList: true, subtree: true });
  scan();
  // Markets functions: one view per function opened, time until the next route
  let cur: { s: string; t: number } | null = null;
  const route = () => {
    const now = Date.now();
    if (cur) add(cur.s, (now - cur.t) / 1000, false);
    const m = window.location.hash.match(/^#mkt\/([a-z0-9]+)/i);
    cur = m ? { s: `mkt:${m[1].toUpperCase()}`, t: now } : null;
    if (cur) { counted.delete(cur.s); add(cur.s, 0, true); }
  };
  route();
  window.addEventListener('hashchange', route);
  const hide = () => {
    if (document.visibilityState !== 'hidden') return;
    const now = Date.now();
    since.forEach((t, s) => { if (now - t >= DWELL_MS) add(s, (now - t) / 1000, false); since.set(s, now); });
    if (cur) { add(cur.s, (now - cur.t) / 1000, false); cur.t = now; }
    flush();
  };
  document.addEventListener('visibilitychange', hide);
  const iv = window.setInterval(flush, 60_000);
  return () => {
    io.disconnect(); mo.disconnect(); clearInterval(iv); clearTimeout(pendingScan); timers.forEach((t) => clearTimeout(t));
    window.removeEventListener('hashchange', route); document.removeEventListener('visibilitychange', hide); flush();
  };
}
