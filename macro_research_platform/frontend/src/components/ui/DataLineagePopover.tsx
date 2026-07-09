/**
 * DataLineagePopover — Phase 1A ground-truth traceability.
 *
 * A small "i" icon next to a metric. On click it reveals a popover with the number's full
 * lineage: source feed, last fetch time (+ relative age & staleness), the calculation
 * formula if the value is derived, and the raw upstream value when it differs from what is
 * displayed. Makes traceability visible so a number is trusted, not just shown.
 *
 * Reusable everywhere — accepts a lineage object; no per-call styling.
 */
import { useEffect, useRef, useState } from 'react';
import { Info } from 'lucide-react';

export interface Lineage {
  value?: number | string | null;
  source: string;
  fetched_at?: string | null;
  staleness_threshold_seconds?: number;
  status?: 'live' | 'stale' | 'error';
  formula?: string;          // present when the value is derived
  raw_value?: number | string | null; // upstream value if different from displayed
  notes?: string;
}

function relAge(sec: number): string {
  if (sec < 60) return `${Math.round(sec)}s ago`;
  if (sec < 3600) return `${Math.round(sec / 60)}m ago`;
  return `${Math.round(sec / 3600)}h ago`;
}

export function DataLineagePopover({ lineage }: { lineage: Lineage }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onEsc);
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onEsc); };
  }, [open]);

  const ms = lineage.fetched_at ? new Date(lineage.fetched_at).getTime() : NaN;
  const valid = !isNaN(ms);
  const ageSec = valid ? Math.max(0, (Date.now() - ms) / 1000) : null;
  const threshold = lineage.staleness_threshold_seconds ?? 900;
  const status = lineage.status ?? (!valid ? 'error' : ageSec! > threshold ? 'stale' : 'live');
  const dot = status === 'live' ? 'bg-green' : status === 'stale' ? 'bg-amber' : 'bg-red';
  const statusText = status === 'live' ? 'text-green' : status === 'stale' ? 'text-amber' : 'text-red';

  return (
    <span ref={ref} className="relative inline-flex">
      <button
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
        title="Data lineage"
        className={`inline-flex items-center justify-center w-3.5 h-3.5 text-text-tertiary hover:text-bloomberg ${open ? 'text-bloomberg' : ''}`}
      >
        <Info className="w-3 h-3" />
      </button>

      {open && (
        <div className="absolute right-0 top-5 z-50 w-64 p-2.5 bg-surface-2 border border-border-strong text-2xs font-mono shadow-none"
          onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center gap-1.5 mb-2 pb-1.5 border-b border-border-subtle">
            <span className={`inline-block w-1.5 h-1.5 rounded-full ${dot}`} />
            <span className={`uppercase tracking-wider font-bold ${statusText}`}>{status}</span>
            <span className="ml-auto text-text-tertiary uppercase tracking-wider">Lineage</span>
          </div>
          <dl className="space-y-1">
            <Row label="Source" value={lineage.source} />
            {lineage.value !== undefined && lineage.value !== null && (
              <Row label="Displayed" value={String(lineage.value)} strong />
            )}
            {lineage.raw_value !== undefined && lineage.raw_value !== null && String(lineage.raw_value) !== String(lineage.value) && (
              <Row label="Raw upstream" value={String(lineage.raw_value)} />
            )}
            <Row label="Fetched" value={valid ? `${new Date(ms).toLocaleString()} · ${relAge(ageSec!)}` : 'no timestamp'} />
            {lineage.formula && <Row label="Formula" value={lineage.formula} wrap />}
            {lineage.notes && <Row label="Notes" value={lineage.notes} wrap />}
          </dl>
        </div>
      )}
    </span>
  );
}

function Row({ label, value, strong, wrap }: { label: string; value: string; strong?: boolean; wrap?: boolean }) {
  return (
    <div className="flex gap-2">
      <dt className="text-text-tertiary uppercase tracking-wider shrink-0 w-16">{label}</dt>
      <dd className={`${strong ? 'text-text-primary font-bold' : 'text-text-secondary'} ${wrap ? 'break-words' : 'truncate'} flex-1`}>{value}</dd>
    </div>
  );
}
