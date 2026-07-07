/**
 * DataHealthIndicator — data-trust layer
 *
 * Global header widget showing how many upstream data feeds (FRED, market data,
 * database) are live vs degraded vs down, backed by the active /api/v1/health/sources
 * probe. Hover for per-source status, latency and last-checked time so a PM can see
 * exactly which feed is degraded before trusting a number.
 */
import React, { useEffect, useRef, useState } from 'react';

type SourceStatus = 'live' | 'degraded' | 'down';

interface SourceHealth {
  status: SourceStatus;
  latency_ms: number | null;
  detail: string;
  last_checked: string;
}

interface SourcesHealth {
  overall: 'healthy' | 'degraded' | 'down';
  live: number;
  degraded: number;
  down: number;
  total: number;
  sources: Record<string, SourceHealth>;
  checked_at: string;
}

const POLL_MS = 30_000;

const SOURCE_LABELS: Record<string, string> = {
  fred: 'FRED (macro)',
  market_data: 'Market Data',
  database: 'Database',
};

const dotColor = (s: SourceStatus | 'loading') =>
  s === 'live' ? 'bg-green' : s === 'degraded' ? 'bg-amber' : s === 'down' ? 'bg-red' : 'bg-text-tertiary';

const textColor = (s: string) =>
  s === 'live' || s === 'healthy' ? 'text-green'
    : s === 'degraded' ? 'text-amber'
    : s === 'down' ? 'text-red' : 'text-text-tertiary';

function relTime(iso: string): string {
  const t = new Date(iso).getTime();
  if (isNaN(t)) return '—';
  const secs = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.round(secs / 60);
  return `${mins}m ago`;
}

export function DataHealthIndicator(): React.ReactElement {
  const [data, setData] = useState<SourcesHealth | null>(null);
  const [errored, setErrored] = useState(false);
  const [open, setOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const r = await fetch('/api/v1/health/sources');
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const j = await r.json();
        if (!cancelled) { setData(j); setErrored(false); }
      } catch {
        if (!cancelled) setErrored(true);
      }
    };
    load();
    timer.current = setInterval(load, POLL_MS);
    return () => { cancelled = true; if (timer.current) clearInterval(timer.current); };
  }, []);

  const overall: SourceStatus | 'loading' = errored
    ? 'down'
    : !data ? 'loading'
    : data.overall === 'healthy' ? 'live' : data.overall === 'down' ? 'down' : 'degraded';

  const label = !data && !errored ? '…' : errored ? '?/?' : `${data!.live}/${data!.total}`;

  return (
    <div
      className="relative inline-flex items-center"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        className="flex items-center gap-1.5 px-2 h-full border border-border bg-surface-1 hover:border-bloomberg-border transition-colors shrink-0"
        title="Upstream data-feed health"
      >
        <span className={`inline-block w-2 h-2 rounded-full ${dotColor(overall)} ${overall === 'degraded' || overall === 'down' ? 'animate-pulse' : ''}`} />
        <span className="text-2xs text-text-tertiary uppercase tracking-wider">Feeds</span>
        <span className={`text-xs font-mono font-bold ${textColor(errored ? 'down' : data?.overall ?? 'loading')}`}>{label}</span>
      </button>

      {open && (data || errored) && (
        <div className="absolute top-full right-0 mt-2 z-50 min-w-[280px] p-3 bg-surface-1 border border-border-subtle shadow-lg rounded text-xs">
          <div className="flex items-center justify-between border-b border-border-subtle pb-1 mb-2">
            <span className="font-medium text-text-primary">Data Feed Health</span>
            {data && (
              <span className={`font-mono ${textColor(data.overall)}`}>{data.overall.toUpperCase()}</span>
            )}
          </div>

          {errored && !data && (
            <div className="text-red">Health probe unreachable — backend may be down.</div>
          )}

          {data && (
            <div className="space-y-1.5">
              {Object.entries(data.sources).map(([key, s]) => (
                <div key={key} className="flex items-center gap-2">
                  <span className={`inline-block w-2 h-2 rounded-full ${dotColor(s.status)} shrink-0`} />
                  <span className="text-text-primary w-28 shrink-0">{SOURCE_LABELS[key] ?? key}</span>
                  <span className={`font-mono ${textColor(s.status)} w-16 shrink-0`}>{s.status.toUpperCase()}</span>
                  <span className="font-mono text-text-tertiary w-14 text-right shrink-0">
                    {s.latency_ms != null ? `${s.latency_ms}ms` : '—'}
                  </span>
                </div>
              ))}
              <div className="pt-1.5 mt-1 border-t border-border-subtle grid grid-cols-1 gap-0.5 text-text-tertiary">
                {Object.entries(data.sources).map(([key, s]) => (
                  <div key={key} className="truncate">
                    <span className="text-text-secondary">{SOURCE_LABELS[key] ?? key}:</span> {s.detail}
                  </div>
                ))}
              </div>
              <div className="pt-1 text-2xs text-text-tertiary text-right">
                Probed {relTime(data.checked_at)} · auto-refresh 30s
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
