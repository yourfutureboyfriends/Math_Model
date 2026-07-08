/**
 * StaleBadge — per-field staleness flag.
 *
 * Renders nothing when a metric's underlying series is fresh, and a distinct
 * amber (STALE) / red (CRITICAL) badge with the data age when it is not — so a PM
 * can see that an individual number is running on stale inputs, not just a whole panel.
 */
import React from 'react';
import { useFreshness, freshnessFor } from '@/hooks/useFreshness';

interface StaleBadgeProps {
  /** metric key matching /api/v1/freshness (e.g. "inflation", "growth"). */
  metric: string;
  className?: string;
}

export function StaleBadge({ metric, className = '' }: StaleBadgeProps): React.ReactElement | null {
  const data = useFreshness();
  const f = freshnessFor(data, metric);
  if (!f || f.status === 'FRESH' || f.status === 'UNKNOWN') return null;

  const critical = f.status === 'CRITICAL';
  const tone = critical
    ? 'text-red border-red/50 bg-red-dim'
    : 'text-amber border-amber/50 bg-amber-dim';
  const age = f.age_days != null ? `${f.age_days}d` : '';
  const title = `${f.name}: last release ${f.last_observation_date ?? 'unknown'} · ${age} old (max ${f.max_lag_days}d)`;

  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 text-2xs font-mono px-1 py-0.5 rounded-sm border border-dashed ${tone} ${className}`}
    >
      <span className={`inline-block w-1.5 h-1.5 rounded-full ${critical ? 'bg-red' : 'bg-amber'}`} />
      {f.status}{age ? ` ${age}` : ''}
    </span>
  );
}
