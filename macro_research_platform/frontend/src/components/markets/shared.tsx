// Shared bits for the Markets mode: data hook, number formats that respect the instrument
// (FX/crypto precision, currency), change colouring, compact market caps.
import { useEffect, useMemo, useRef, useState } from 'react';
import { cn } from '@/lib/utils';

/** A readable message from a FastAPI error body (string detail, or a list of validation errors). */
export function apiError(j: any, status: number): string {
  const d = j?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d.length) {
    return d.map((e: any) => {
      const field = Array.isArray(e?.loc) ? String(e.loc[e.loc.length - 1]).replace(/_/g, ' ') : 'input';
      return `${field}: ${String(e?.msg ?? 'invalid').replace(/^Input should be /, 'must be ')}`;
    }).join('; ');
  }
  return `Request failed (HTTP ${status}).`;
}

// Messages the API returned with 404 — "this doesn't apply / isn't published for this instrument",
// not a failure — so ErrorBox can show them as a neutral note instead of a red error.
const NOT_APPLICABLE = new Set<string>();

export function useJSON<T = any>(url: string | null, refreshMs = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [dataUrl, setDataUrl] = useState<string | null>(null);   // the url `data` was fetched for
  useEffect(() => {
    if (!url) { setData(null); setDataUrl(null); return; }
    let live = true;
    let retry: ReturnType<typeof setTimeout> | null = null;
    const load = (first: boolean, attempt = 0) => {
      if (first && attempt === 0) { setLoading(true); setError(null); }
      fetch(url).then(async (r) => {
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw Object.assign(new Error(apiError(j, r.status)), { transient: r.status >= 500, status: r.status });
        return j;
      }).then((j) => { if (live) { setData(j); setDataUrl(url); setError(null); } if (live && first) setLoading(false); })
        .catch((e) => {
          if (!live || !first) return;                       // a failed refresh keeps the last data
          // network blips and 5xx (e.g. the API restarting) are retried with backoff before surfacing
          if ((e.transient || e instanceof TypeError) && attempt < 3) { retry = setTimeout(() => load(true, attempt + 1), [1500, 4000, 9000][attempt]); return; }
          if (e.status === 404) NOT_APPLICABLE.add(e.message);
          setError(e.message); setData(null); setLoading(false);
        });
    };
    load(true);
    const t = refreshMs > 0 ? setInterval(() => { if (document.visibilityState === 'visible') load(false); }, refreshMs) : null;
    return () => { live = false; if (t) clearInterval(t); if (retry) clearTimeout(retry); };
  }, [url, refreshMs]);
  // `current` is false while `data` still belongs to a previous url (e.g. the last symbol)
  return { data, error, loading, current: data != null && dataUrl === url };
}

export function decimalsFor(price: number | null | undefined, type?: string): number {
  if (price == null) return 2;
  const a = Math.abs(price);
  if (type === 'FX') return a >= 20 ? 3 : 5;
  if (a >= 1000) return 2;
  if (a >= 1) return 2;
  if (a >= 0.01) return 4;
  return 8;
}

export const fmtPrice = (v: number | null | undefined, type?: string) =>
  v == null || !Number.isFinite(v) ? '—' : v.toLocaleString(undefined, { minimumFractionDigits: decimalsFor(v, type), maximumFractionDigits: decimalsFor(v, type) });

export const fmtPct = (v: number | null | undefined, d = 2) =>
  v == null || !Number.isFinite(v) ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`;

export function fmtBig(v: number | null | undefined, ccy?: string | null): string {
  if (v == null || !Number.isFinite(v)) return '—';
  const a = Math.abs(v);
  const s = a >= 1e12 ? `${(v / 1e12).toFixed(2)}T` : a >= 1e9 ? `${(v / 1e9).toFixed(2)}B` : a >= 1e6 ? `${(v / 1e6).toFixed(1)}M`
    : a >= 1e3 ? `${(v / 1e3).toFixed(1)}K` : v.toFixed(0);
  return ccy ? `${s} ${ccy}` : s;
}

export function Chg({ v, d = 2, className }: { v: number | null | undefined; d?: number; className?: string }) {
  return <span className={cn('font-mono tabular-nums', v == null ? 'text-text-tertiary' : v > 0 ? 'text-green' : v < 0 ? 'text-red' : 'text-text-secondary', className)}>{fmtPct(v, d)}</span>;
}

export function Spark({ values, w = 72, h = 20 }: { values?: number[]; w?: number; h?: number }) {
  if (!values || values.length < 2) return <span className="inline-block" style={{ width: w }} />;
  const lo = Math.min(...values), hi = Math.max(...values);
  // a range under 0.2% of the level (stablecoins, pegs) is noise: don't stretch it to full height
  const flat = hi === lo || (hi - lo) / Math.max(Math.abs((hi + lo) / 2), 1e-12) < 0.002;
  const pad = 1.5, ih = h - 2 * pad;                    // keep the stroke and end dot inside the box
  const xy = values.map((v, i) => [(i / (values.length - 1)) * (w - 3), flat ? h / 2 : pad + ih - ((v - lo) / (hi - lo)) * ih]);
  const pts = xy.map(([a, b]) => `${a.toFixed(1)},${b.toFixed(1)}`).join(' ');
  const up = values[values.length - 1] >= values[0];
  if (flat) return <svg width={w} height={h} aria-hidden="true" className="inline-block align-middle"><polyline points={pts} fill="none" stroke="rgb(var(--c-text-tertiary))" strokeWidth={1.25} /></svg>;
  const col = up ? 'rgb(var(--c-green))' : 'rgb(var(--c-red))';
  const [lx, ly] = xy[xy.length - 1];
  return (
    <svg width={w} height={h} aria-hidden="true" className="inline-block align-middle overflow-visible">
      <polygon points={`0,${h} ${pts} ${lx.toFixed(1)},${h}`} fill={col} fillOpacity={0.12} />
      <polyline points={pts} fill="none" stroke={col} strokeWidth={1.3} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={lx} cy={ly} r={1.8} fill={col} />
    </svg>
  );
}

export function Panel({ title, right, children, className }: { title?: string; right?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('mkt-panel bg-surface-1 border border-border', className)}>
      {(title || right) && (
        <div className="panel-hdr flex items-center justify-between gap-2 px-3 py-1.5 border-b border-border-subtle">
          <span className="text-[10px] uppercase tracking-wider text-text-tertiary">{title}</span>
          {right}
        </div>
      )}
      <div className="p-3">{children}</div>
    </div>
  );
}

/** Loading placeholder: a shimmering skeleton with the label, so a screen never looks blank. */
export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="p-3 space-y-2" role="status" aria-live="polite">
      <div className="flex items-center gap-2 text-2xs text-text-tertiary">
        <span className="inline-block w-3 h-3 rounded-full border-2 border-bloomberg/30 border-t-bloomberg animate-spin" />{label}
      </div>
      <div className="mkt-skeleton h-2.5 w-3/4" /><div className="mkt-skeleton h-2.5 w-1/2" /><div className="mkt-skeleton h-2.5 w-2/3" />
    </div>
  );
}

export function ErrorBox({ msg }: { msg: string | null }) {
  if (msg && NOT_APPLICABLE.has(msg)) {
    return (
      <div className="flex items-start gap-2 px-3 py-2 rounded-md border border-border bg-surface-1 text-xs text-text-secondary" role="status">
        <svg viewBox="0 0 16 16" className="w-3.5 h-3.5 mt-0.5 shrink-0 text-text-tertiary" fill="currentColor" aria-hidden="true"><path d="M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13Zm-.75 3h1.5V6h-1.5V4.5Zm0 3h1.5v4h-1.5v-4Z" /></svg>
        <span>{msg}</span>
      </div>);
  }
  return msg ? (
    <div className="flex items-start gap-2 px-3 py-2 rounded-md border border-red/35 bg-red/[0.06] text-xs text-red" role="alert">
      <svg viewBox="0 0 16 16" className="w-3.5 h-3.5 mt-0.5 shrink-0" fill="currentColor" aria-hidden="true"><path d="M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13Zm-.75 3.5h1.5v4.5h-1.5V5Zm0 5.5h1.5V12h-1.5v-1.5Z" /></svg>
      <span>{msg}</span>
    </div>) : null;
}

export const TYPE_COLOR: Record<string, string> = {
  Stock: 'text-blue', ETF: 'text-green', Fund: 'text-green', Index: 'text-amber', FX: 'text-purple',
  Crypto: 'text-bloomberg', Future: 'text-purple', Option: 'text-red',
};

/** A value that flashes green/red for a moment when it ticks up/down (terminal monitors). */
export function Flash({ value, children, className }: { value: number | null | undefined; children: React.ReactNode; className?: string }) {
  const prev = useRef<number | null | undefined>(value);
  const [cls, setCls] = useState('');
  const [n, setN] = useState(0);
  useEffect(() => {
    if (value != null && prev.current != null && value !== prev.current) {
      setCls(value > prev.current ? 'flash-up' : 'flash-down');
      setN((k) => k + 1);                       // restart the animation on every tick
    }
    prev.current = value;
  }, [value]);
  return <span key={n} className={cn(cls, className)}>{children}</span>;
}

/** Click-to-sort for any table: `useSort(rows)` returns the sorted rows and a header factory.
 *  First click sorts descending for numbers (biggest first) and ascending for text; again flips. */
export function useSort<T extends Record<string, any>>(rows: T[] | undefined, initial?: { key: string; dir: 1 | -1 }) {
  const [s, setS] = useState<{ key: string; dir: 1 | -1 } | null>(initial ?? null);
  const sorted = useMemo(() => {
    const r = [...(rows ?? [])];
    if (!s) return r;
    const val = (x: T) => {
      const v = s.key.split('.').reduce((o: any, k) => (o == null ? o : o[k]), x);
      return typeof v === 'string' ? v.toLowerCase() : v;
    };
    return r.sort((a, b) => {
      const va = val(a), vb = val(b);
      if (va == null && vb == null) return 0;
      if (va == null) return 1;                              // blanks always last
      if (vb == null) return -1;
      return (va < vb ? -1 : va > vb ? 1 : 0) * s.dir;
    });
  }, [rows, s]);
  const th = (key: string, label: React.ReactNode, className = '', numeric = true) => (
    <th className={cn('font-normal cursor-pointer select-none hover:text-text-primary whitespace-nowrap', className)} aria-sort={s?.key === key ? (s.dir > 0 ? 'ascending' : 'descending') : undefined}
      onClick={() => setS((p) => (p?.key === key ? { key, dir: (p.dir * -1) as 1 | -1 } : { key, dir: numeric ? -1 : 1 }))} title="Sort">
      {label}{s?.key === key ? <span className="text-bloomberg ml-0.5">{s.dir > 0 ? '▲' : '▼'}</span> : null}</th>
  );
  return { rows: sorted, th, sort: s };
}

/** Instrument type from a Yahoo symbol, for lists that only carry symbols (FX needs 4–5 decimals). */
export const symType = (s?: string | null) => (s && s.endsWith('=X') ? 'FX' : undefined);
