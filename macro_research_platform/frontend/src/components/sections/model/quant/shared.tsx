// Shared helpers for the Quant Lab and the two paper traders: API calls, number formats,
// small presentational pieces.
import { cn } from '@/lib/utils';

export async function api(url: string, init?: RequestInit & { json?: unknown }) {
  const { json, ...rest } = init ?? {};
  const r = await fetch(url, json !== undefined
    ? { ...rest, method: rest.method ?? 'POST', headers: { 'Content-Type': 'application/json', ...(rest.headers ?? {}) }, body: JSON.stringify(json) }
    : rest);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j?.detail === 'string' ? j.detail : j?.detail?.message || `HTTP ${r.status}`);
  return j;
}

export const usd = (v: number | null | undefined, d = 0) =>
  v == null ? '—' : `${v < 0 ? '-' : ''}$${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d })}`;
export const pct = (v: number | null | undefined, d = 1) => (v == null || !Number.isFinite(v) ? '—' : `${(v * 100).toFixed(d)}%`);
export const spct = (v: number | null | undefined, d = 1) => (v == null || !Number.isFinite(v) ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`);
export const num = (v: number | null | undefined, d = 2) => (v == null || !Number.isFinite(v) ? '—' : v.toFixed(d));
export const tone = (v: number | null | undefined) => (v == null ? null : v > 0 ? 'up' : v < 0 ? 'down' : null) as 'up' | 'down' | null;

export interface Spec {
  name: string; description?: string;
  universe: { preset?: string; symbols?: string[] };
  signal: string; filter?: string | null;
  selection: { mode: string; n?: number | string; pct?: number; min_score?: number | null; long_only?: boolean };
  weighting: string;
  risk?: { vol_target?: number | null; max_weight?: number; max_gross?: number; vol_lookback?: number };
  rebalance: string; execution?: string;
  costs?: { bps?: number; borrow_bps?: number };
  fallback?: string | null; benchmark?: string; start?: string; end?: string | null;
}

export const BLANK_SPEC: Spec = {
  name: 'My algo', universe: { preset: 'cross_asset' }, signal: 'mom(252, 21)', filter: '',
  selection: { mode: 'top_n', n: 3, pct: 0.2, min_score: null, long_only: true }, weighting: 'equal',
  risk: { vol_target: null, max_weight: 1, max_gross: 1, vol_lookback: 63 }, rebalance: 'monthly', execution: 'next_open',
  costs: { bps: 5, borrow_bps: 50 }, fallback: '', benchmark: 'SPY', start: '2005-01-01',
};

export function withDefaults(s: Partial<Spec>): Spec {
  return {
    ...BLANK_SPEC, ...s,
    universe: s.universe ?? BLANK_SPEC.universe,
    selection: { ...BLANK_SPEC.selection, ...(s.selection ?? {}) },
    risk: { ...BLANK_SPEC.risk, ...(s.risk ?? {}) },
    costs: { ...BLANK_SPEC.costs, ...(s.costs ?? {}) },
    filter: s.filter ?? '', fallback: s.fallback ?? '',
  };
}

export const GRADE: Record<string, { cls: string; label: string }> = {
  promising: { cls: 'border-green/50 text-green', label: 'Promising' },
  mixed: { cls: 'border-amber/50 text-amber', label: 'Mixed' },
  weak: { cls: 'border-red/50 text-red', label: 'Weak' },
};

export function Field({ label, hint, children, className }: { label: string; hint?: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={cn('block text-2xs', className)}>
      <span className="block text-[10px] uppercase tracking-wide text-text-tertiary mb-0.5" title={hint}>{label}{hint && <span className="ml-1 cursor-help">ⓘ</span>}</span>
      {children}
    </label>
  );
}

export const inputCls = 'w-full bg-surface-1 border border-border px-2 py-1 text-xs font-mono text-text-primary focus:border-bloomberg outline-none';

export function Pills<T extends string>({ value, options, onChange, label }: {
  value: T; options: readonly (readonly [T, string])[]; onChange: (v: T) => void; label: string;
}) {
  return (
    <div className="flex flex-wrap border border-border w-fit" role="tablist" aria-label={label}>
      {options.map(([k, l]) => (
        <button key={k} type="button" role="tab" aria-selected={value === k} onClick={() => onChange(k)}
          className={cn('px-2.5 py-0.5 text-2xs', value === k ? 'bg-bloomberg text-bg' : 'text-text-secondary hover:text-text-primary')}>
          {l}
        </button>
      ))}
    </div>
  );
}

export function ErrorNote({ msg }: { msg: string | null }) {
  if (!msg) return null;
  return <div className="px-3 py-2 border border-red/40 bg-red/5 text-xs text-red" role="alert">{msg}</div>;
}
