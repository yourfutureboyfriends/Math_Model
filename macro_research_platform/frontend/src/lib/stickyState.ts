// useState that remembers its value in this browser, so a screen reopens with the index, period or view you last chose.
// Storage can be unavailable (private window, blocked site data): it then behaves like plain useState.
import { useCallback, useState } from 'react';

const PREFIX = 'view.';

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(PREFIX + key);
    if (raw == null) return fallback;
    const v = JSON.parse(raw);
    return typeof v === typeof fallback || fallback == null ? v : fallback;   // ignore a stored value of the wrong type
  } catch {
    return fallback;
  }
}

export function useStickyState<T>(key: string, initial: T): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(() => read(key, initial));
  const set = useCallback((v: T) => {
    setValue(v);
    try { localStorage.setItem(PREFIX + key, JSON.stringify(v)); } catch { /* not persisted; still works this session */ }
  }, [key]);
  return [value, set];
}
