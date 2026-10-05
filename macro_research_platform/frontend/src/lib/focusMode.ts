/**
 * Workspaces: which dashboard panels are shown. 'all', 'focus' (the signed-in role's panels:
 * My Desk, the Macro Model, the Daily Brief and the role's focus panels), or one navigation
 * group (OVERVIEW, SIGNALS, RISK, ...). Remembered per browser.
 *
 * Collapsed panels: a per-browser set of panel ids whose content is folded to the header.
 */
import { useEffect, useState } from 'react';
import { groupOf, navigation } from '@/lib/navigation';

const KEY = 'macro_workspace';
const LEGACY_FOCUS_KEY = 'macro_focus_mode';
const EVT = 'macro-workspace';

export type Workspace = string;   // 'all' | 'focus' | navigation group title

export const WORKSPACES: { id: Workspace; label: string }[] = [
  { id: 'focus', label: 'My focus' },
  ...navigation.map((s) => ({ id: s.title, label: s.title.charAt(0) + s.title.slice(1).toLowerCase() })),
  { id: 'all', label: 'All panels' },
];

export function getWorkspace(): Workspace {
  try {
    const w = localStorage.getItem(KEY);
    if (w && WORKSPACES.some((x) => x.id === w)) return w;
    return localStorage.getItem(LEGACY_FOCUS_KEY) === '1' ? 'focus' : 'all';
  } catch { return 'all'; }
}

export function setWorkspace(w: Workspace) {
  try { localStorage.setItem(KEY, w); } catch { /* storage unavailable */ }
  window.dispatchEvent(new CustomEvent(EVT, { detail: w }));
}

export function useWorkspace(): Workspace {
  const [w, setW] = useState(getWorkspace);
  useEffect(() => {
    const h = (e: Event) => setW(String((e as CustomEvent).detail));
    window.addEventListener(EVT, h);
    return () => window.removeEventListener(EVT, h);
  }, []);
  return w;
}

let deskPanelsCache: string[] = [];
/** The signed-in role's focus panels (set by the dashboard once the desk loads). */
export function setDeskPanels(ids: string[]) { deskPanelsCache = ids; }

/** Panel ids a workspace shows (null = everything). */
export function workspacePanels(w: Workspace, deskPanels: string[] = deskPanelsCache): Set<string> | null {
  if (w === 'all') return null;
  if (w === 'focus') return new Set(['my-desk', 'macro-model', 'morning-brief', ...deskPanels]);
  const group = navigation.find((s) => s.title === w);
  if (!group) return null;
  const ids = group.items.map((i) => i.id);
  return new Set(w === navigation[0].title ? ['my-desk', ...ids] : ids);
}

/** Make sure a panel is visible before scrolling to it: switch to its group if hidden. */
export function revealPanel(id: string): boolean {
  const cur = workspacePanels(getWorkspace());
  if (!cur || cur.has(id)) return false;
  setWorkspace(groupOf(id) ?? 'all');
  return true;
}

// Back-compat: the original two-state focus toggle.
export const getFocusMode = () => getWorkspace() === 'focus';
export const setFocusMode = (on: boolean) => setWorkspace(on ? 'focus' : 'all');
export const useFocusMode = () => useWorkspace() === 'focus';

/** Hide every top-level terminal section that doesn't contain one of the allowed anchors. */
export function applyFocus(container: HTMLElement | null, allowed: Set<string> | null) {
  if (!container) return;
  container.querySelectorAll<HTMLElement>(':scope > .terminal-section').forEach((sec) => {
    if (!allowed) { sec.hidden = false; return; }
    const ids = [sec.id, ...Array.from(sec.querySelectorAll<HTMLElement>('[id]')).map((e) => e.id)].filter(Boolean);
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
