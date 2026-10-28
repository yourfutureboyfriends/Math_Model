// Shared pieces of the PE area: number formats, small inputs, the API helpers, and the PE tab / "open this deal"
// signals the sidebar and the pipeline use to drive the workbench.
import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';

export type PeTab = 'workbench' | 'pipeline' | 'waterfall' | 'performance';
export const PE_TABS: { id: PeTab; label: string; desc: string }[] = [
  { id: 'workbench', label: 'LBO workbench', desc: 'Model a buyout: financing, cases, returns, credit' },
  { id: 'pipeline', label: 'Deal pipeline', desc: 'Saved deals by stage, with their activity' },
  { id: 'waterfall', label: 'Carry waterfall', desc: 'LP / GP split: hurdle, catch-up, carry' },
  { id: 'performance', label: 'Fund performance', desc: 'IRR, TVPI, DPI and public-market equivalents' },
];
const TAB_KEY = 'pe_tab';
const TAB_EVT = 'pe-tab';
const OPEN_EVT = 'pe-open-deal';

export function getPeTab(): PeTab {
  try { const t = localStorage.getItem(TAB_KEY); if (PE_TABS.some((x) => x.id === t)) return t as PeTab; } catch { /* storage unavailable */ }
  return 'workbench';
}
export function setPeTab(t: PeTab) {
  try { localStorage.setItem(TAB_KEY, t); } catch { /* storage unavailable */ }
  window.dispatchEvent(new CustomEvent(TAB_EVT, { detail: t }));
}
export function usePeTab(): PeTab {
  const [t, setT] = useState<PeTab>(getPeTab);
  useEffect(() => {
    const h = (e: Event) => setT((e as CustomEvent).detail as PeTab);
    window.addEventListener(TAB_EVT, h);
    return () => window.removeEventListener(TAB_EVT, h);
  }, []);
  return t;
}
/** Open a saved deal in the workbench (the pipeline's "Open"). */
export function openDeal(id: number) { setPeTab('workbench'); setTimeout(() => window.dispatchEvent(new CustomEvent(OPEN_EVT, { detail: id })), 0); }
export function onOpenDeal(fn: (id: number) => void) {
  const h = (e: Event) => fn(Number((e as CustomEvent).detail));
  window.addEventListener(OPEN_EVT, h);
  return () => window.removeEventListener(OPEN_EVT, h);
}

export async function api<T = any>(url: string, body?: unknown, method = body === undefined ? 'GET' : 'POST'): Promise<T> {
  const r = await fetch(url, { method, headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : `HTTP ${r.status}`);
  return j as T;
}

/** POST and save the response as a file (the Excel model). */
export async function download(url: string, body: unknown, filename: string) {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const blob = await r.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

// ── Formats ──────────────────────────────────────────────────────────────────────────────────────────────────────
export const pct = (v?: number | null, d = 1) => (v == null || !isFinite(v) ? '—' : `${(v * 100).toFixed(d)}%`);
export const spct = (v?: number | null, d = 1) => (v == null || !isFinite(v) ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(d)}%`);
export const xx = (v?: number | null, d = 2) => (v == null || !isFinite(v) ? '—' : `${v.toFixed(d)}×`);
/** Amounts: millions when large (the deal's currency). */
export function amt(v?: number | null, ccy?: string | null, unit = 1e6): string {
  if (v == null || !isFinite(v)) return '—';
  const x = v / unit;
  const s = Math.abs(x) >= 100 ? x.toLocaleString('en-US', { maximumFractionDigits: 0 }) : x.toLocaleString('en-US', { maximumFractionDigits: 1 });
  return `${x < 0 ? '(' : ''}${s.replace('-', '')}${x < 0 ? ')' : ''}${ccy ? '' : ''}`;
}
/** A unit that suits the deal size: millions for real companies, units for small illustrative ones. */
export const unitFor = (ebitda?: number | null) => (ebitda && Math.abs(ebitda) >= 1e5 ? 1e6 : 1);
export const irrTone = (v?: number | null, hurdle = 0.2) =>
  v == null ? 'text-text-tertiary' : v >= hurdle ? 'text-green' : v >= hurdle * 0.6 ? 'text-amber' : 'text-red';

// ── Inputs ───────────────────────────────────────────────────────────────────────────────────────────────────────
/** A number field shown in display units (percent → ×100, millions → ÷1e6); calls onChange with the model value. */
export function NumField({ label, value, onChange, kind = 'num', step, hint, className }: {
  label: string; value: number | null | undefined; onChange: (v: number | null) => void;
  kind?: 'num' | 'pct' | 'x' | 'm' | 'int'; step?: number; hint?: string; className?: string;
}) {
  const scale = kind === 'pct' ? 100 : kind === 'm' ? 1e-6 : 1;
  const shown = value == null ? '' : String(+(value * scale).toFixed(kind === 'pct' ? 3 : kind === 'm' ? 2 : 3));
  const [text, setText] = useState(shown);
  useEffect(() => setText(shown), [shown]);
  const suffix = kind === 'pct' ? '%' : kind === 'x' ? '×' : kind === 'm' ? 'm' : '';
  return (
    <label className={cn('block', className)} title={hint}>
      <span className="block text-[10.5px] text-text-tertiary mb-0.5 truncate">{label}</span>
      <span className="flex items-center rounded-md border border-border bg-bg/40 focus-within:border-bloomberg/60">
        <input value={text} inputMode="decimal" step={step}
          onChange={(e) => setText(e.target.value)}
          onBlur={() => { const n = text.trim() === '' ? null : Number(text); if (n === null || isFinite(n)) onChange(n === null ? null : n / scale); else setText(shown); }}
          onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
          className="w-full min-w-0 bg-transparent px-2 py-1 text-xs tabular-nums text-text-primary outline-none" />
        {suffix && <span className="pr-2 text-[10.5px] text-text-tertiary">{suffix}</span>}
      </span>
    </label>
  );
}

export function Kpi({ label, value, sub, tone }: { label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: string }) {
  return (
    <div className="p-3 rounded-xl border border-border bg-surface-1">
      <div className="text-[10px] uppercase tracking-[0.06em] text-text-tertiary">{label}</div>
      <div className={cn('text-lg font-semibold tabular-nums mt-0.5', tone ?? 'text-text-primary')}>{value}</div>
      {sub && <div className="text-[10.5px] text-text-tertiary mt-0.5">{sub}</div>}
    </div>
  );
}

export function Card({ title, right, children, className }: { title: string; right?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('p-3.5 rounded-xl border border-border bg-surface-1', className)}>
      <div className="flex items-center gap-2 mb-2.5">
        <span className="text-[12px] font-semibold text-text-primary">{title}</span>
        <span className="ml-auto">{right}</span>
      </div>
      {children}
    </div>
  );
}

/** A heat-mapped IRR grid (green above the hurdle, red below). */
export function IrrGrid({ g, hurdle, colFmt, rowFmt }: { g: { rows: number[]; cols: number[]; irr: (number | null)[][]; row_label: string; col_label: string };
  hurdle: number; colFmt: (v: number) => string; rowFmt: (v: number) => string }) {
  const tone = (v: number | null) => {
    if (v == null) return { background: 'transparent' };
    const d = Math.max(-1, Math.min(1, (v - hurdle) / 0.15));
    return { background: d >= 0 ? `rgb(var(--c-green) / ${0.08 + 0.32 * d})` : `rgb(var(--c-red) / ${0.08 + 0.32 * -d})` };
  };
  return (
    <div className="overflow-x-auto">
      <div className="text-[10.5px] text-text-tertiary mb-1">{g.row_label} ↓ · {g.col_label} →</div>
      <table className="text-[11px] tabular-nums border-separate border-spacing-[2px]">
        <thead><tr><th />{g.cols.map((c) => <th key={c} className="px-2 py-1 font-medium text-text-tertiary">{colFmt(c)}</th>)}</tr></thead>
        <tbody>{g.rows.map((r, i) => (
          <tr key={r}><td className="pr-2 text-text-tertiary font-medium">{rowFmt(r)}</td>
            {g.irr[i].map((v, j) => <td key={j} className="px-2.5 py-1 rounded-md text-center text-text-primary" style={tone(v)}>{pct(v)}</td>)}</tr>))}
        </tbody>
      </table>
    </div>
  );
}
