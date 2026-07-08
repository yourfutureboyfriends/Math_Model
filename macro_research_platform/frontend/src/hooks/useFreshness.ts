/**
 * useFreshness — shared per-field data-freshness state.
 *
 * Fetches /api/v1/freshness once (module-shared, refreshed every 5 min) so any number
 * of StaleBadge components can flag an individual stale metric without each issuing its
 * own request.
 */
import { useEffect, useState } from 'react';

export interface FieldFreshness {
  metric: string;
  name: string;
  series_id: string;
  last_observation_date: string | null;
  age_days: number | null;
  max_lag_days: number;
  status: 'FRESH' | 'STALE' | 'CRITICAL' | 'UNKNOWN';
}

interface FreshnessResponse {
  available: boolean;
  series: FieldFreshness[];
}

const REFRESH_MS = 300_000;
let cache: FreshnessResponse | null = null;
let lastFetch = 0;
let inflight: Promise<FreshnessResponse | null> | null = null;
const listeners = new Set<(d: FreshnessResponse | null) => void>();

async function load(force = false): Promise<FreshnessResponse | null> {
  const now = Date.now();
  if (!force && cache && now - lastFetch < REFRESH_MS) return cache;
  if (inflight) return inflight;
  inflight = fetch('/api/v1/freshness')
    .then((r) => (r.ok ? r.json() : null))
    .then((j: FreshnessResponse | null) => {
      cache = j;
      lastFetch = Date.now();
      inflight = null;
      listeners.forEach((fn) => fn(cache));
      return cache;
    })
    .catch(() => {
      inflight = null;
      return cache;
    });
  return inflight;
}

export function useFreshness(): FreshnessResponse | null {
  const [data, setData] = useState<FreshnessResponse | null>(cache);
  useEffect(() => {
    listeners.add(setData);
    load();
    const t = setInterval(() => load(true), REFRESH_MS);
    return () => { listeners.delete(setData); clearInterval(t); };
  }, []);
  return data;
}

export function freshnessFor(data: FreshnessResponse | null, metric: string): FieldFreshness | undefined {
  return data?.series?.find((s) => s.metric === metric);
}
