/**
 * Workspaces: which dashboard panels are shown. 'all', 'focus' (the signed-in role's panels:
 * My Desk, the Macro Model, the Daily Brief and the role's focus panels), or one navigation
 * group (OVERVIEW, SIGNALS, RISK, ...). Remembered per browser.
 *
 * Collapsed panels: a per-browser set of panel ids whose content is folded to the header.
 */
import { useEffect, useState } from 'react';
import { areaOf, areaPanels, navigationFor, type AreaId } from '@/lib/navigation';
import { getHubMode, isDashboardMode, setHubMode } from '@/lib/hubMode';

const KEY = 'macro_workspace';                 // per area: macro_workspace:<area> (the bare key is the old, shared one)
const LEGACY_FOCUS_KEY = 'macro_focus_mode';
const EVT = 'macro-workspace';

export type Workspace = string;   // 'all' | 'focus' | one of the current area's group titles

/** The current dashboard area (Macro when the app is on Markets / PE). */
export function currentArea(): AreaId {
  const m = getHubMode();
  return isDashboardMode(m) ? m : 'macro';
}

const title = (t: string) => t.charAt(0) + t.slice(1).toLowerCase();

/** The workspace tabs of an area: My focus, its groups, All panels. */
export function workspacesFor(area: AreaId = currentArea()): { id: Workspace; label: string }[] {
  return [{ id: 'focus', label: 'My focus' },
    ...navigationFor(area).map((s) => ({ id: s.title, label: title(s.title) })),
    { id: 'all', label: 'All panels' }];
}

export function getWorkspace(area: AreaId = currentArea()): Workspace {
  try {
    const w = localStorage.getItem(`${KEY}:${area}`) ?? (area === 'macro' ? localStorage.getItem(KEY) : null);
    if (w && workspacesFor(area).some((x) => x.id === w)) return w;
    return localStorage.getItem(LEGACY_FOCUS_KEY) === '1' ? 'focus' : 'all';
  } catch { return 'all'; }
}

export function setWorkspace(w: Workspace, area: AreaId = currentArea()) {
  try { localStorage.setItem(`${KEY}:${area}`, w); } catch { /* storage unavailable */ }
  window.dispatchEvent(new CustomEvent(EVT, { detail: w }));
}

/** The current area's workspace; follows area switches too. */
export function useWorkspace(): Workspace {
  const [w, setW] = useState(() => getWorkspace());
  useEffect(() => {
    const h = () => setW(getWorkspace());
    window.addEventListener(EVT, h);
    window.addEventListener('hub-mode', h);
    return () => { window.removeEventListener(EVT, h); window.removeEventListener('hub-mode', h); };
  }, []);
  return w;
}

let deskPanelsCache: string[] = [];
/** The signed-in role's focus panels (set by the dashboard once the desk loads). */
export function setDeskPanels(ids: string[]) { deskPanelsCache = ids; }

/** Panel ids a workspace shows in an area. */
export function workspacePanels(w: Workspace, deskPanels: string[] = deskPanelsCache, area: AreaId = currentArea()): Set<string> {
  const mine = areaPanels(area);
  if (w === 'focus') return new Set(['my-desk', ...['macro-model', 'morning-brief', ...deskPanels].filter((id) => mine.has(id))]);
  const group = navigationFor(area).find((s) => s.title === w);
  if (w === 'all' || !group) return mine;
  const ids = group.items.map((i) => i.id);
  return new Set(group === navigationFor(area)[0] ? ['my-desk', ...ids] : ids);
}

/** Make sure a panel is visible before scrolling to it: switch to its area and group if hidden. True if anything
 *  changed (the caller waits for the re-render before scrolling). */
export function revealPanel(id: string): boolean {
  const area = areaOf(id);
  if (area && area !== currentArea()) { setHubMode(area); setWorkspace('all', area); return true; }
  const cur = workspacePanels(getWorkspace());
  if (cur.has(id)) return false;
  setWorkspace(navigationFor(currentArea()).find((s) => s.items.some((i) => i.id === id))?.title ?? 'all');
  return true;
}

// Back-compat: the original two-state focus toggle.
export const getFocusMode = () => getWorkspace() === 'focus';
export const setFocusMode = (on: boolean) => setWorkspace(on ? 'focus' : 'all');
export const useFocusMode = () => useWorkspace() === 'focus';

/** Hide every top-level terminal section that doesn't contain one of the allowed anchors. */
export function applyFocus(container: HTMLElement | null, allowed: Set<string> | null, showUnassigned = false) {
  if (!container) return;
  container.querySelectorAll<HTMLElement>(':scope > .terminal-section').forEach((sec) => {
    if (!allowed) { sec.hidden = false; return; }
    // Ids of the section, of its content, and of content not mounted yet (a WhenNear placeholder lists them).
    const ids = [sec.id, ...Array.from(sec.querySelectorAll<HTMLElement>('[id]')).map((e) => e.id),
      ...Array.from(sec.querySelectorAll<HTMLElement>('[data-near-ids]')).flatMap((e) => (e.dataset.nearIds ?? '').split(' '))].filter(Boolean);
    // A section that belongs to no area (no navigation anchor) stays visible under Macro → All panels.
    if (showUnassigned && !ids.some((id) => id === 'my-desk' || areaOf(id))) { sec.hidden = false; return; }
    sec.hidden = !ids.some((id) => allowed.has(id));
  });
}

// ── Collapsed panels ─────────────────────────────────────────────────────────
const COLLAPSE_KEY = 'macro_collapsed_panels';

export function getCollapsed(): Set<string> {
  try { return new Set(JSON.parse(localStorage.getItem(COLLAPSE_KEY) ?? '[]')); } catch { return new Set(); }
}

export function saveCollapsed(ids: Set<string>) {
  try { localStorage.setItem(COLLAPSE_KEY, JSON.stringify([...ids])); } catch { /* storage unavailable */ }
}

/** Stable id of a top-level panel (wrapper id, else its first anchored descendant). */
export function panelId(sec: HTMLElement): string | null {
  return sec.id !== '' ? sec.id : (sec.querySelector<HTMLElement>('[id]')?.id ?? null);
}
