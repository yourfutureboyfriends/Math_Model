/**
 * SourceTag — data-trust layer
 *
 * Small "SOURCE · age" provenance tag for a panel. Shows where a number came from
 * and how fresh it is, and renders a distinct amber/dashed treatment once the data
 * is older than its staleness threshold — so a PM can never mistake a stale feed for
 * a live one. If no valid timestamp is available it renders "no timestamp" rather
 * than pretending the data is fresh.
 */
import React from 'react';

interface SourceTagProps {
  /** Human-readable source, e.g. "Yahoo", "FRED", "Computed", "Live". */
  source?: string;
  /** ISO-8601 timestamp of when the data was produced. */
  timestamp?: string | null;
  /** Age in seconds past which the data is flagged STALE. Default 15m. */
  staleAfterSeconds?: number;
  className?: string;
}

function relAge(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  return `${Math.round(seconds / 3600)}h ago`;
}

export function SourceTag({
  source = 'Live',
  timestamp,
  staleAfterSeconds = 900,
  className = '',
}: SourceTagProps): React.ReactElement {
  const ms = timestamp ? new Date(timestamp).getTime() : NaN;
  const valid = !isNaN(ms);
  const ageSec = valid ? Math.max(0, (Date.now() - ms) / 1000) : null;
  const stale = ageSec != null && ageSec > staleAfterSeconds;

  const base = 'inline-flex items-center gap-1 text-2xs font-mono px-1.5 py-0.5 rounded-sm';
  const tone = !valid
    ? 'text-text-tertiary border border-dashed border-border'
    : stale
      ? 'text-amber border border-dashed border-amber/50 bg-amber-dim'
      : 'text-text-tertiary';

  return (
    <span className={`${base} ${tone} ${className}`} title={valid ? new Date(ms).toLocaleString() : 'No timestamp available'}>
      <span
        className={`inline-block w-1.5 h-1.5 rounded-full ${
          !valid ? 'bg-text-tertiary' : stale ? 'bg-amber' : 'bg-green'
        }`}
      />
      <span className="uppercase tracking-wider">{source}</span>
      <span className="text-text-tertiary">·</span>
      <span>{valid ? relAge(ageSec!) : 'no timestamp'}</span>
      {stale && <span className="text-amber font-bold ml-0.5">STALE</span>}
    </span>
  );
}
