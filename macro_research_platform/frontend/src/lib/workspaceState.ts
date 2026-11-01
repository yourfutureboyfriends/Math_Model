import { HUB_MODES, type HubMode } from './hubMode';
export type SavedView = { id: string; mode: HubMode; label: string; workspace?: string; hash?: string; pe?: 'workbench'|'pipeline'|'precedents'|'waterfall'|'performance' };
/** Browser storage is optional, untrusted input. Ignore old/corrupt records instead of crashing the shell. */
export function savedViews(value: unknown): SavedView[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  return value.filter((v): v is SavedView => {
    if (!v || typeof v !== 'object' || typeof v.id !== 'string' || typeof v.label !== 'string' ||
        !HUB_MODES.some(m => m.id === v.mode) || v.id.length > 500 || v.label.length > 500) return false;
    if (v.mode === 'markets' && (typeof v.hash !== 'string' || !v.hash.startsWith('#mkt/'))) return false;
    if (v.mode === 'pe' && !['workbench','pipeline','precedents','waterfall','performance'].includes(v.pe)) return false;
    if (v.workspace != null && typeof v.workspace !== 'string') return false;
    if (seen.has(v.id)) return false;
    seen.add(v.id); return true;
  }).slice(0, 20);
}
export function preference(value: unknown): boolean { return value === true; }
