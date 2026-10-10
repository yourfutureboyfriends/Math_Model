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
        if (!r.ok) throw Object.assign(new Error(apiError(j, r.status)), { transient: r.status >= 500 });
        return j;
      }).then((j) => { if (live) { setData(j); setDataUrl(url); setError(null); } if (live && first) setLoading(false); })
        .catch((e) => {
          if (!live || !first) return;                       // a failed refresh keeps the last data
          // network blips and 5xx (e.g. the API restarting) are retried with backoff before surfacing
          if ((e.transient || e instanceof TypeError) && attempt < 3) { retry = setTimeout(() => load(true, attempt + 1), [1500, 4000, 9000][attempt]); return; }
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
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${hi === lo ? h / 2 : h - ((v - lo) / (hi - lo)) * h}`).join(' ');
  const up = values[values.length - 1] >= values[0];
  return (
    <svg width={w} height={h} aria-hidden="true" className="inline-block align-middle">
      <polyline points={pts} fill="none" stroke={up ? 'rgb(var(--c-green))' : 'rgb(var(--c-red))'} strokeWidth={1.25} />
    </svg>
  );
}

export function Panel({ title, right, children, className }: { title?: string; right?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('bg-surface-1 border border-border', className)}>
      {(title || right) && (
        <div className="panel-hdr flex items-center justify-between px-3 py-1.5 border-b border-border-subtle">
          <span className="text-[10px] uppercase tracking-wider text-text-tertiary">{title}</span>
          {right}
        </div>
      )}
      <div className="p-3">{children}</div>
    </div>
  );
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return <div className="text-2xs text-text-tertiary p-3 animate-pulse">{label}</div>;
}

export function ErrorBox({ msg }: { msg: string | null }) {
  return msg ? <div className="px-3 py-2 border border-red/40 bg-red/5 text-xs text-red" role="alert">{msg}</div> : null;
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
