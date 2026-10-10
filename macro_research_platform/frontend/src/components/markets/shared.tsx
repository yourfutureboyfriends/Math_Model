// Shared bits for the Markets mode: data hook, number formats that respect the instrument
// (FX/crypto precision, currency), change colouring, compact market caps.
import { useEffect, useRef, useState } from 'react';
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
    const load = (first: boolean) => {
      if (first) { setLoading(true); setError(null); }
      fetch(url).then(async (r) => {
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(apiError(j, r.status));
        return j;
      }).then((j) => { if (live) { setData(j); setDataUrl(url); setError(null); } })
        .catch((e) => { if (live && first) { setError(e.message); setData(null); } })   // a failed refresh keeps the last data
        .finally(() => { if (live && first) setLoading(false); });
    };
    load(true);
    const t = refreshMs > 0 ? setInterval(() => { if (document.visibilityState === 'visible') load(false); }, refreshMs) : null;
    return () => { live = false; if (t) clearInterval(t); };
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
      <polyline points={pts} fill="none" stroke={up ? '#199e70' : '#e66767'} strokeWidth={1.25} />
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
