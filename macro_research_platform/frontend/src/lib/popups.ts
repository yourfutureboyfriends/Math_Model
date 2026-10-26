// Live pop-up notifications (breaking headlines, big market moves, economic releases, regime changes): a tiny store
// shared by the toast stack (components/layout/LivePopups) and the status-bar button that opens the history and
// the settings. Settings are remembered per browser; "seen" keys per session, so a reload doesn't replay them.
import { useSyncExternalStore } from 'react';

export type PopupKind = 'news' | 'move' | 'eco' | 'regime';
export type Popup = {
  id: string; kind: PopupKind; title: string; body?: string; tone?: 'up' | 'down' | 'neutral';
  at: number; href?: string; action?: { label: string; run: () => void };
};
export const KIND_LABEL: Record<PopupKind, string> = { news: 'Headlines', move: 'Market moves', eco: 'Economic releases', regime: 'Regime changes' };

type State = { toasts: Popup[]; history: Popup[]; unread: number; enabled: boolean; kinds: Record<PopupKind, boolean>; panel: boolean };
const SETTINGS = 'ui_popups_v1';
const MAX_TOASTS = 4;
const MAX_HISTORY = 40;

function loadSettings(): Pick<State, 'enabled' | 'kinds'> {
  const def = { enabled: true, kinds: { news: true, move: true, eco: true, regime: true } };
  try {
    const s = JSON.parse(localStorage.getItem(SETTINGS) || 'null');
    return s ? { enabled: s.enabled !== false, kinds: { ...def.kinds, ...(s.kinds || {}) } } : def;
  } catch { return def; }
}

let state: State = { toasts: [], history: [], unread: 0, panel: false, ...loadSettings() };
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());
const set = (patch: Partial<State>) => { state = { ...state, ...patch }; emit(); };
const save = () => { try { localStorage.setItem(SETTINGS, JSON.stringify({ enabled: state.enabled, kinds: state.kinds })); } catch { /* storage unavailable */ } };

/** The current state, outside React (tests, non-component code). */
export const popupState = (): State => state;

export function usePopups(): State {
  return useSyncExternalStore((l) => { listeners.add(l); return () => listeners.delete(l); }, () => state, () => state);
}

/** Show a pop-up (kept in the history even when pop-ups are muted or the kind is switched off). */
export function pushPopup(p: Omit<Popup, 'at'>): void {
  if (state.history.some((h) => h.id === p.id)) return;
  const item: Popup = { ...p, at: Date.now() };
  const show = state.enabled && state.kinds[p.kind];
  set({
    history: [item, ...state.history].slice(0, MAX_HISTORY),
    unread: state.panel ? state.unread : state.unread + 1,
    toasts: show ? [item, ...state.toasts].slice(0, MAX_TOASTS) : state.toasts,
  });
}

export const dismissPopup = (id: string) => set({ toasts: state.toasts.filter((t) => t.id !== id) });
export const setPopupsEnabled = (on: boolean) => { set({ enabled: on, toasts: on ? state.toasts : [] }); save(); };
export const setKindEnabled = (k: PopupKind, on: boolean) => { set({ kinds: { ...state.kinds, [k]: on } }); save(); };
export const togglePanel = (open?: boolean) => set({ panel: open ?? !state.panel, unread: 0 });

/** Session-scoped "already notified" keys, so a reload or a re-poll doesn't repeat a pop-up. */
const SEEN = 'popup_seen_v1';
let seen: Set<string> = (() => { try { return new Set(JSON.parse(sessionStorage.getItem(SEEN) || '[]')); } catch { return new Set(); } })();
export function seenBefore(key: string): boolean {
  if (seen.has(key)) return true;
  seen.add(key);
  if (seen.size > 600) seen = new Set([...seen].slice(-400));
  try { sessionStorage.setItem(SEEN, JSON.stringify([...seen])); } catch { /* storage unavailable */ }
  return false;
}
