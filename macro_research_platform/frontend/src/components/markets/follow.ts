// Following: ships and aircraft you want to keep an eye on, with your own notes. Kept per browser
// (localStorage) and shared live between the trackers through a window event.
import { useEffect, useState } from 'react';

export type Followed = { kind: 'ship' | 'plane'; id: string; label: string; note: string; added: string; reason?: string };
const KEY = 'mkt_follow_v1';
const EVT = 'mkt-follow';

function read(): Followed[] {
  try { const v = JSON.parse(localStorage.getItem(KEY) || '[]'); return Array.isArray(v) ? v : []; } catch { return []; }
}
function write(list: Followed[]) {
  try { localStorage.setItem(KEY, JSON.stringify(list)); } catch { /* storage unavailable */ }
  window.dispatchEvent(new CustomEvent(EVT));
}

export function useFollow(kind: 'ship' | 'plane') {
  const [all, setAll] = useState<Followed[]>(read);
  useEffect(() => {
    const h = () => setAll(read());
    window.addEventListener(EVT, h); window.addEventListener('storage', h);
    return () => { window.removeEventListener(EVT, h); window.removeEventListener('storage', h); };
  }, []);
  const list = all.filter((f) => f.kind === kind);
  const ids = new Set(list.map((f) => f.id));
  return {
    list,
    ids,
    isFollowed: (id: string) => ids.has(id),
    toggle: (id: string, label: string, reason?: string) => {
      const cur = read();
      write(cur.some((f) => f.kind === kind && f.id === id) ? cur.filter((f) => !(f.kind === kind && f.id === id))
        : [...cur, { kind, id, label, note: '', added: new Date().toISOString().slice(0, 16), reason }]);
    },
    setNote: (id: string, note: string) => write(read().map((f) => (f.kind === kind && f.id === id ? { ...f, note } : f))),
    remove: (id: string) => write(read().filter((f) => !(f.kind === kind && f.id === id))),
  };
}
