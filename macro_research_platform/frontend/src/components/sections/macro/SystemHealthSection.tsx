// System Health — service status, data-source probes, model availability and data freshness,
// from /api/health, /api/v1/health/sources and /api/v1/freshness.

import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';

interface SourceProbe { status: string; latency_ms: number | null; detail?: string; last_checked?: string }
interface Health {
  status?: string;
  analyticalIntegrity?: string;
  integrityErrors?: string[];
  models?: Record<string, boolean>;
  fred_circuit_breaker?: { open: boolean; retry_in_s: number; trips: number };
}
interface Sources { overall: string; sources: Record<string, SourceProbe>; checked_at?: string }
interface FreshRow { name: string; series_id: string; status: string; state?: string; last_observation_date?: string; next_expected_release?: string; periods_behind?: number }
interface Freshness { available?: boolean; series?: FreshRow[] }

const TONE: Record<string, string> = {
  live: 'text-green', ok: 'text-green', healthy: 'text-green', fresh: 'text-green',
  degraded: 'text-amber', stale: 'text-amber', warning: 'text-amber',
  down: 'text-red', error: 'text-red', critical: 'text-red', overdue: 'text-red',
};
const tone = (s?: string) => TONE[(s || '').toLowerCase()] ?? 'text-text-secondary';
const LABEL: Record<string, string> = {
  recession: 'Recession probit', lei: 'Leading indicators', credit_impulse: 'Credit impulse',
  risk_parity: 'Risk parity', fin_conditions: 'Financial conditions', classifier: 'Regime classifier',
};

export function SystemHealthSection() {
  const [health, setHealth] = useState<Health | null>(null);
  const [sources, setSources] = useState<Sources | null>(null);
  const [fresh, setFresh] = useState<Freshness | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    const get = async (u: string) => {
      const r = await fetch(u);
      if (!r.ok) throw new Error(`${u}: HTTP ${r.status}`);
      return r.json();
    };
    const [h, s, f] = await Promise.allSettled([get('/api/health'), get('/api/v1/health/sources'), get('/api/v1/freshness')]);
    if (h.status === 'fulfilled') setHealth(h.value);
    if (s.status === 'fulfilled') setSources(s.value);
    if (f.status === 'fulfilled') setFresh(f.value);
    const failed = [h, s, f].filter((x) => x.status === 'rejected') as PromiseRejectedResult[];
    setError(failed.length ? failed.map((x) => x.reason?.message).join('; ') : null);
    setBusy(false);
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, [load]);

  const series = fresh?.series ?? [];
  const notFresh = series.filter((r) => (r.status || '').toUpperCase() !== 'FRESH');
  const breaker = health?.fred_circuit_breaker;

  return (
    <section className="terminal-section">
      <div className="section-header mb-3">
        <span className="section-tag">HEALTH</span>
        <h2 className="section-title">System Health</h2>
        {sources && <span className={`ml-2 text-2xs uppercase font-mono ${tone(sources.overall)}`}>{sources.overall}</span>}
        <button onClick={load} disabled={busy} className="ml-auto p-1 text-text-tertiary hover:text-bloomberg disabled:opacity-50" aria-label="Refresh" title="Refresh">
          <RefreshCw className={`w-3.5 h-3.5 ${busy ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {error && <div className="mb-2 text-2xs text-amber">Partially unavailable: {error}</div>}
      {!health && !sources && !error && <div className="h-24 animate-pulse bg-surface-2" />}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-2">
        <div className="border border-border bg-surface-1 p-3">
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Data sources</div>
          {sources && Object.entries(sources.sources).map(([name, p]) => (
            <div key={name} className="flex items-baseline justify-between text-xs py-0.5" title={p.detail}>
              <span className="text-text-secondary capitalize">{name.replace('_', ' ')}</span>
              <span className="font-mono">
                <span className={tone(p.status)}>{p.status}</span>
                <span className="text-text-tertiary"> · {p.latency_ms == null ? '—' : `${p.latency_ms} ms`}</span>
              </span>
            </div>
          ))}
          {breaker && (
            <div className="mt-1 pt-1 border-t border-border-subtle text-2xs text-text-tertiary">
              FRED circuit breaker: <span className={breaker.open ? 'text-red' : 'text-green'}>{breaker.open ? `open, retry in ${Math.round(breaker.retry_in_s)}s` : 'closed'}</span>
              {breaker.trips > 0 && ` · ${breaker.trips} trips`}
            </div>
          )}
          {sources && Object.values(sources.sources).some((p) => p.status !== 'live') && (
            <div className="mt-1 text-2xs text-text-tertiary">
              {Object.entries(sources.sources).filter(([, p]) => p.status !== 'live').map(([n, p]) => `${n}: ${p.detail ?? p.status}`).join(' · ').slice(0, 220)}
            </div>
          )}
        </div>

        <div className="border border-border bg-surface-1 p-3">
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Models</div>
          {health?.models && Object.entries(health.models).map(([k, ok]) => (
            <div key={k} className="flex justify-between text-xs py-0.5">
              <span className="text-text-secondary">{LABEL[k] ?? k}</span>
              <span className={`font-mono ${ok ? 'text-green' : 'text-red'}`}>{ok ? 'loaded' : 'unavailable'}</span>
            </div>
          ))}
          {health && (
            <div className="mt-1 pt-1 border-t border-border-subtle text-2xs text-text-tertiary">
              Analytical integrity: <span className={tone(health.analyticalIntegrity)}>{health.analyticalIntegrity ?? '—'}</span>
              {health.integrityErrors?.length ? ` · ${health.integrityErrors.join('; ')}` : ''}
            </div>
          )}
        </div>

        <div className="border border-border bg-surface-1 p-3">
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Data freshness</div>
          {fresh && (
            <>
              <div className="text-xs text-text-secondary mb-1">
                <span className="font-mono text-text-primary">{series.length - notFresh.length}/{series.length}</span> series current with their release calendar
              </div>
              {notFresh.length === 0 ? (
                <div className="text-2xs text-green">All inputs up to date.</div>
              ) : notFresh.slice(0, 6).map((r) => (
                <div key={r.series_id} className="flex justify-between text-2xs py-0.5">
                  <span className="text-text-secondary">{r.name}</span>
                  <span className={`font-mono ${tone(r.status)}`}>{r.status}{r.last_observation_date ? ` · ${r.last_observation_date}` : ''}</span>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
