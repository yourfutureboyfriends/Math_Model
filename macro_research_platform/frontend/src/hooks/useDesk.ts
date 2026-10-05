/**
 * useDesk — the signed-in user's role desk (/api/v1/desk), shared by the My Desk panel
 * and the sidebar's "YOUR DESK" links. One request per minute however many consumers.
 */
import { useEffect, useState } from 'react';

export interface DeskItem {
  priority: 'high' | 'medium' | 'info';
  kind: string;
  title: string;
  detail: string;
  target: string | null;
}

export interface DeskLimit {
  metric: string; label: string; unit: string; value: number | null;
  soft: number; hard: number; utilization: number | null; status: string;
}

export interface DeskPrint {
  metric: string; name: string; series_id: string; latest_value: number | null; unit?: string;
  last_observation_date: string | null; frequency: string; status: string; state: string;
  next_expected_release: string | null; category: string;
}

export interface Desk {
  user: { username: string; role: string };
  focus: { title: string; panels: string[] };
  queue: DeskItem[];
  fund: {
    available: boolean; fund_name?: string; base_currency?: string; nav?: number;
    unrealized_pnl?: number | null; realized_pnl?: number; last_day_pnl?: number | null;
    exposures?: { gross?: number; net?: number; long?: number; short?: number };
    var95_1d_usd?: number | null; positions?: number;
    limits?: { overall: string; breaches: DeskLimit[]; warnings: DeskLimit[]; top_utilization: DeskLimit[] };
    track_record?: { available: boolean; observations?: number; total_return?: number | null;
      annualized_vol?: number | null; sharpe?: number | null; max_drawdown?: number | null };
  };
  macro: {
    available: boolean; regime?: string; regime_confidence?: number | null; regime_months?: number | null;
    recession_probability?: number | null; sahm?: number | null; ensemble_score?: number | null;
    model_regime?: string | null; model_regime_probability?: number | null;
    conviction?: string | null; risk_budget?: number | null;
  };
  data: {
    available: boolean; score_pct?: number | null; unknown?: number;
    categories?: Record<string, { total: number; fresh: number }>; prints?: DeskPrint[];
  };
  orders: { available: boolean; by_state: Record<string, number> };
  as_of: string;
}

const REFRESH_MS = 60_000;
let cache: Desk | null = null;
let lastFetch = 0;
let inflight: Promise<void> | null = null;
const listeners = new Set<(d: Desk | null) => void>();

function load(force = false) {
  // Slightly under the interval so each consumer's timer still refreshes, but only once.
  if (!force && cache && Date.now() - lastFetch < REFRESH_MS - 2_000) return;
  if (inflight) return;
  inflight = fetch('/api/v1/desk')
    .then((r) => (r.ok ? r.json() : null))
    .then((j: Desk | null) => {
      if (j) { cache = j; lastFetch = Date.now(); }
      listeners.forEach((fn) => fn(cache));
    })
    .catch(() => { /* keep last good desk */ })
    .finally(() => { inflight = null; });
}

export function refreshDesk() { load(true); }

/** `username` keys the shared cache so a new sign-in never sees the previous user's desk. */
export function useDesk(username?: string): Desk | null {
  const fits = (d: Desk | null) => (d && (!username || d.user.username === username) ? d : null);
  const [data, setData] = useState<Desk | null>(fits(cache));
  useEffect(() => {
    if (cache && username && cache.user.username !== username) { cache = null; lastFetch = 0; }
    const onData = (d: Desk | null) => setData(fits(d));
    listeners.add(onData);
    load();
    const t = setInterval(() => load(), REFRESH_MS);
    return () => { listeners.delete(onData); clearInterval(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [username]);
  return data;
}
