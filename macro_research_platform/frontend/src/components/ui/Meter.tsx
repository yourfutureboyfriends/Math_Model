// Utilisation meter — a value against a limit (risk limits, exposure caps, budgets).
// Same-ramp track; status by thresholds is carried by an icon + label, never colour alone.

import { AlertTriangle, CheckCircle2, XOctagon } from 'lucide-react';

interface Props {
  label: string;
  value: number | null;
  limit: number | null;
  fmt?: (v: number) => string;
  warnAt?: number;                     // share of the limit that turns the meter amber
  sub?: string;
}

export function Meter({ label, value, limit, fmt = (v) => v.toFixed(2), warnAt = 0.8, sub }: Props) {
  const used = value != null && limit ? Math.abs(value) / Math.abs(limit) : null;
  const state = used == null ? 'none' : used >= 1 ? 'breach' : used >= warnAt ? 'warn' : 'ok';
  const color = state === 'breach' ? '#e66767' : state === 'warn' ? '#c98500' : '#199e70';
  const Icon = state === 'breach' ? XOctagon : state === 'warn' ? AlertTriangle : CheckCircle2;
  return (
    <div className="min-w-0">
      <div className="flex items-baseline gap-2 text-2xs">
        <span className="text-text-secondary truncate">{label}</span>
        <span className="ml-auto font-mono text-text-primary">{value == null ? '—' : fmt(value)}</span>
        <span className="font-mono text-text-tertiary">/ {limit == null ? '—' : fmt(limit)}</span>
      </div>
      <div className="relative h-1.5 mt-1 rounded-full bg-surface-3 overflow-hidden" role="meter"
        aria-valuenow={used == null ? undefined : Math.round(used * 100)} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
        <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${Math.min(1, used ?? 0) * 100}%`, background: color }} />
        <div className="absolute inset-y-0 w-px bg-text-tertiary/60" style={{ left: `${warnAt * 100}%` }} />
      </div>
      <div className="flex items-center gap-1 mt-0.5 text-[10px]" style={{ color: state === 'none' ? undefined : color }}>
        {state !== 'none' && <Icon className="w-3 h-3" />}
        <span>{state === 'none' ? 'no limit set' : state === 'breach' ? 'Breach' : state === 'warn' ? 'Near limit' : 'Within limit'}
          {used != null ? ` · ${(used * 100).toFixed(0)}% used` : ''}</span>
        {sub && <span className="text-text-tertiary ml-auto">{sub}</span>}
      </div>
    </div>
  );
}
