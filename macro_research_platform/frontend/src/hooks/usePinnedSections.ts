/**
 * usePinnedSections — per-user pinned dashboard panels.
 *
 * Lets a PM pin their most-watched panels for one-click access. Persisted in
 * localStorage per user so it survives reloads. Capped at 8 pins.
 */
import { useState, useEffect, useCallback } from 'react';

const MAX_PINS = 8;
const storageKey = (userKey: string) => `macroos.pinnedSections.${userKey}`;

export function usePinnedSections(userKey: string = 'default') {
  const [pinned, setPinned] = useState<string[]>(() => {
    try {
      const raw = localStorage.getItem(storageKey(userKey));
      const arr = raw ? JSON.parse(raw) : [];
      return Array.isArray(arr) ? arr.filter((x) => typeof x === 'string') : [];
    } catch {
      return [];
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(storageKey(userKey), JSON.stringify(pinned));
    } catch {
      /* storage unavailable — pins simply won't persist */
    }
  }, [pinned, userKey]);

  const toggle = useCallback((id: string) => {
    setPinned((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id].slice(0, MAX_PINS)
    );
  }, []);

  const isPinned = useCallback((id: string) => pinned.includes(id), [pinned]);

  return { pinned, toggle, isPinned, maxPins: MAX_PINS };
}
