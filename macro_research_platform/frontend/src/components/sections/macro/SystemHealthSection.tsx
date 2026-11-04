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
  const [monitor, setMonitor] = useState<any>(null);       // free-data source monitor (api/source_monitor.py)
  const [checking, setChecking] = useState(false);
  const checkNow = async () => {
    setChecking(true);
    try { const r = await fetch('/api/v1/system/sources/check', { method: 'POST' }); if (r.ok) setMonitor(await r.json()); } finally { setChecking(false); }
  };

  const load = useCallback(async () => {
    setBusy(true);
    const get = async (u: string) => {
      const r = await fetch(u);
      if (!r.ok) throw new Error(`${u}: HTTP ${r.status}`);
      return r.json();
    };
    const [h, s, f, m] = await Promise.allSettled([get('/api/health'), get('/api/v1/health/sources'), get('/api/v1/freshness'), get('/api/v1/system/sources')]);
    if (h.status === 'fulfilled') setHealth(h.value);
    if (s.status === 'fulfilled') setSources(s.value);
    if (f.status === 'fulfilled') setFresh(f.value);
    if (m.status === 'fulfilled') setMonitor(m.value);
    const failed = [h, s, f, m].filter((x) => x.status === 'rejected') as PromiseRejectedResult[];
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
              <span className="text-text-secondary capitalize">{name.replace(/_/g, ' ')}</span>
              <span className="font-mono">
                <span className={tone(p.status)}>{p.status}</span>
                <span className="text-text-tertiary"> · {p.latency_ms == null ? '—' : `${p.latency_ms} ms`}</span>
              </span>
            </div>
          ))}
          {(sources?.sources as any)?.quote_freshness?.instruments && (
            <div className="mt-1 pl-2 space-y-0.5">
              {Object.entries((sources!.sources as any).quote_freshness.instruments as Record<string, any>).map(([sym, q]) => (
                <div key={sym} className="flex justify-between text-2xs text-text-tertiary" title={q.detail ?? `last 5-minute bar ${q.last_bar}`}>
                  <span className="font-mono">{sym}</span>
                  <span><span className={q.status === 'fresh' ? 'text-green' : q.status === 'stale' ? 'text-amber' : 'text-red'}>{q.status}</span>
                    {q.age_min != null && ` · ${q.age_min}m old · market ${q.open_now ? 'open' : 'closed'}`}</span>
                </div>
              ))}
            </div>
          )}
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

        <div className="border border-border bg-surface-1 p-3 lg:col-span-3">
          <div className="flex items-center justify-between mb-2">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider">Free data sources — parsed and dated every {monitor?.interval_hours ?? 6} h</div>
            <button onClick={checkNow} disabled={checking} className="text-2xs px-2 py-0.5 border border-border hover:border-bloomberg disabled:opacity-40">{checking ? 'Checking…' : 'Check now'}</button>
          </div>
          {!monitor?.sources?.length ? <div className="text-2xs text-text-tertiary">First check runs 5 minutes after start.</div> : (
            <>
              <div className="text-xs text-text-secondary mb-1">
                {(['ok', 'stale', 'degraded', 'failing'] as const).map((k) => (
                  <span key={k} className={`mr-3 font-mono ${k === 'ok' ? 'text-green' : k === 'failing' ? 'text-red' : 'text-amber'}`}>{monitor.summary?.[k] ?? 0} {k}</span>))}
                <span className="text-2xs text-text-tertiary">checked {String(monitor.checked_at ?? '').replace('T', ' ').slice(0, 16)}</span>
              </div>
              <div className="workspace-table-scroll" tabIndex={0} role="group" aria-label="Scrollable data table"><table className="w-full text-2xs">
                <tbody>
                  {monitor.sources.map((r: any) => (
                    <tr key={r.name} className="border-b border-border-subtle last:border-0" title={`Feeds: ${r.feeds}${r.error ? `\n${r.error}` : ''}`}>
                      <td className="py-0.5 pr-2 text-text-secondary">{r.name}</td>
                      <td className={`py-0.5 pr-2 font-mono uppercase ${r.status === 'ok' ? 'text-green' : r.status === 'failing' ? 'text-red' : 'text-amber'}`}>{r.status}</td>
                      <td className="py-0.5 pr-2 font-mono text-text-tertiary">{r.latest ?? '—'}{r.age_days != null && r.age_days >= 0 ? ` (${r.age_days}d)` : ''}</td>
                      <td className="py-0.5 text-text-tertiary truncate max-w-[22rem]">{r.status === 'ok' ? '' : `${r.error ?? ''} · since ${String(r.since ?? '').slice(0, 16).replace('T', ' ')}`}</td>
                    </tr>))}
                </tbody>
              </table></div>
            </>)}
        </div>
      </div>
      <OpsIncidents />
      <ScreenUsage />
    </section>
  );
}

/** Open data incidents, the last after-close accuracy audit and recent feed events (api/ops_monitor.py). */
function OpsIncidents() {
  const [m, setM] = useState<any>(null);
  useEffect(() => {
    const load = () => fetch('/api/v1/ops/monitor').then((r) => r.json()).then(setM).catch(() => {});
    load();
    const t = setInterval(load, 5 * 60_000);
    return () => clearInterval(t);
  }, []);
  if (!m) return null;
  const a = m.last_audit;
  const sev = (s: string) => (s === 'critical' ? 'text-red' : s === 'warning' ? 'text-amber' : 'text-green');
  return (
    <div className="mt-3 grid grid-cols-1 lg:grid-cols-2 gap-3">
      <div className="border border-border bg-surface-1 p-3">
        <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Data incidents</div>
        {m.open_incidents.length === 0
          ? <p className="text-xs text-green">No open incidents — every feed is in its normal state.</p>
          : m.open_incidents.map((e: any) => (
            <div key={e.source + e.time} className="text-xs py-0.5"><span className={`font-mono uppercase ${sev(e.severity)}`}>{e.to}</span>{' '}
              <span className="text-text-primary">{e.source}</span> <span className="text-text-tertiary">since {e.time.slice(0, 16).replace('T', ' ')} UTC</span></div>))}
        <div className="text-2xs text-text-tertiary uppercase tracking-wider mt-3 mb-1">Recent events</div>
        {m.events.length === 0 ? <p className="text-2xs text-text-tertiary">None recorded yet.</p> : (
          <ul className="space-y-0.5 max-h-40 overflow-y-auto">{m.events.slice(0, 20).map((e: any, i: number) => (
            <li key={i} className="text-2xs"><span className="font-mono text-text-tertiary">{e.time.slice(5, 16).replace('T', ' ')}</span>{' '}
              <span className={sev(e.severity)}>{e.kind === 'feed' ? `${e.source}: ${e.from} → ${e.to}` : `audit: ${e.detail}`}</span></li>))}</ul>)}
      </div>
      <div className="border border-border bg-surface-1 p-3">
        <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Accuracy audit (after each US close)</div>
        {!a ? <p className="text-xs text-text-tertiary">Not run yet — it runs at 22:30 UTC on weekdays.</p> : (<>
          <p className={`text-xs ${sev(a.severity)}`}>{a.detail}</p>
          <p className="text-2xs text-text-tertiary">{a.time.slice(0, 16).replace('T', ' ')} UTC · {a.seconds ?? '—'}s · {a.report ?? ''}</p>
          {(a.failures ?? []).length > 0 && <ul className="mt-1 space-y-0.5">{a.failures.map((f: any, i: number) => (
            <li key={i} className="text-2xs text-red">{f.check}: <span className="text-text-secondary">{f.detail}</span></li>))}</ul>}
        </>)}
        <p className="text-2xs text-text-tertiary mt-2">{m.note}</p>
      </div>
    </div>
  );
}

/** Which screens are actually read (lib/usageTracker.ts → api/usage.py): evidence for consolidating the platform. */
function ScreenUsage() {
  const [days, setDays] = useState(90);
  const [u, setU] = useState<any>(null);
  const [showNever, setShowNever] = useState(false);
  useEffect(() => { fetch(`/api/v1/usage/summary?days=${days}`).then((r) => (r.ok ? r.json() : null)).then(setU).catch(() => {}); }, [days]);
  if (!u) return null;
  const top = u.screens.slice(0, 15);
  const max = Math.max(1, ...top.map((r: any) => r.views));
  const byArea: Record<string, any[]> = {};
  for (const n of u.never_viewed) (byArea[n.area || 'other'] ??= []).push(n);
  return (
    <div className="mt-3 border border-border bg-surface-1 p-3">
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <span className="text-2xs text-text-tertiary uppercase tracking-wider">Screen usage</span>
        <span className="text-2xs text-text-tertiary">{u.tracking_since ? `tracking since ${u.tracking_since}` : 'no views recorded yet'}</span>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="ml-auto bg-surface-2 border border-border text-2xs px-1 py-0.5" aria-label="Period">
          {[30, 90, 365].map((d) => <option key={d} value={d}>last {d} days</option>)}</select>
      </div>
      <p className="text-xs text-text-secondary mb-2">
        {u.viewed_screens} of {u.known_screens} screens viewed
        {u.concentration.of > 0 && <> · <span className="text-text-primary">{u.concentration.screens_for_80pct_of_views}</span> screens account for 80% of views</>}
        {u.never_viewed.length > 0 && <> · <button className="text-amber underline-offset-2 hover:underline" onClick={() => setShowNever(!showNever)}>{u.never_viewed.length} never viewed</button></>}
      </p>
      {top.length > 0 && <div className="space-y-0.5">{top.map((r: any) => (
        <div key={r.screen} className="flex items-center gap-2 text-2xs">
          <span className="w-44 truncate text-text-primary" title={r.screen}>{r.label}</span>
          <span className="w-14 text-text-tertiary">{r.area}</span>
          <div className="flex-1 h-1.5 bg-surface-3 rounded-sm overflow-hidden"><div className="h-full bg-bloomberg rounded-sm" style={{ width: `${(100 * r.views) / max}%` }} /></div>
          <span className="w-28 text-right font-mono text-text-secondary">{r.views} · {r.users} user{r.users === 1 ? '' : 's'} · {Math.round(r.seconds / 60)}m</span>
        </div>))}</div>}
      {showNever && <div className="mt-2 grid md:grid-cols-3 gap-2">{Object.entries(byArea).map(([a, list]) => (
        <div key={a}><div className="text-[10px] uppercase text-text-tertiary mb-0.5">{a} ({list.length})</div>
          <div className="text-2xs text-text-secondary leading-relaxed">{list.map((n: any) => n.label).join(' · ')}</div></div>))}</div>}
      <p className="text-2xs text-text-tertiary mt-2">{u.note}</p>
    </div>
  );
}
