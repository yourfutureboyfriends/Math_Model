/**
 * Focus mode: show only the panels the signed-in role works from (My Desk, the Macro Model,
 * the Daily Brief and the role's focus panels). Remembered per browser.
 */
import { useEffect, useState } from 'react';

const KEY = 'macro_focus_mode';
const EVT = 'macro-focus-mode';

export function getFocusMode(): boolean {
  try { return localStorage.getItem(KEY) === '1'; } catch { return false; }
}

export function setFocusMode(on: boolean) {
  try { localStorage.setItem(KEY, on ? '1' : '0'); } catch { /* storage unavailable */ }
  window.dispatchEvent(new CustomEvent(EVT, { detail: on }));
}

export function useFocusMode(): boolean {
  const [on, setOn] = useState(getFocusMode);
  useEffect(() => {
    const h = (e: Event) => setOn(Boolean((e as CustomEvent).detail));
    window.addEventListener(EVT, h);
    return () => window.removeEventListener(EVT, h);
  }, []);
  return on;
}

/** Hide every top-level terminal section that doesn't contain one of the allowed anchors. */
export function applyFocus(container: HTMLElement | null, allowed: Set<string> | null) {
  if (!container) return;
  container.querySelectorAll<HTMLElement>(':scope > .terminal-section').forEach((sec) => {
    if (!allowed) { sec.hidden = false; return; }
    const ids = [sec.id, ...Array.from(sec.querySelectorAll<HTMLElement>('[id]')).map((e) => e.id)].filter(Boolean);
    sec.hidden = !ids.some((id) => allowed.has(id));
  });
}
