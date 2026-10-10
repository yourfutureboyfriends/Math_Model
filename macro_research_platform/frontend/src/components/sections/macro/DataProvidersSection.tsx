/**
 * DataProvidersSection — Universal Data Layer health (Phase 5C / 6).
 *
 * Shows every configured data provider, its priority, the asset classes it serves, whether
 * it's currently healthy, and its served / error / fallback counters — so degraded reliance
 * on a backup source (or an inactive keyed provider) is visible at a glance. Reads
 * /api/v1/providers. 3-state bounded load.
 */
import { useCallback, useEffect, useState } from 'react';
import { Network, RefreshCw } from 'lucide-react';

export function DataProvidersSection() {
  const [providers, setProviders] = useState<any[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [reason, setReason] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setReason(null);
    try {
      const res = await fetch('/api/v1/providers').then((r) => r.json());
      setProviders(res?.providers ?? []);
    } catch (e: any) { setReason(e?.message || 'Failed.'); setProviders(null); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const dot = (healthy: boolean) => (healthy ? 'bg-green' : 'bg-text-tertiary');

  return (
    <div id="data-providers" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><Network className="w-3 h-3" /></span>
          <h2 className="section-title">Data Providers</h2>
          {providers && (
            <span className="ml-2 text-2xs font-mono text-text-tertiary">
              {providers.filter((p) => p.healthy).length}/{providers.length} active
            </span>
          )}
        </div>
        <button onClick={load} title="Refresh" aria-label="Refresh" className="p-1 text-text-tertiary hover:text-bloomberg">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading && !providers && <div className="p-3 text-2xs text-text-tertiary">Probing providers…</div>}
      {!loading && reason && <div className="p-3 text-xs text-amber border border-amber/30 bg-amber-dim">Unavailable — {reason}</div>}

      {providers && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-2xs text-text-tertiary uppercase tracking-wider border-b border-border-subtle">
                <th className="text-left py-1.5">Provider</th>
                <th className="text-left">Priority</th>
                <th className="text-left">Asset classes</th>
                <th className="text-right">Served</th>
                <th className="text-right">Errors</th>
                <th className="text-right">Fallbacks</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {providers.map((p) => (
                <tr key={p.name} className="border-b border-border-subtle last:border-0">
                  <td className="py-1.5">
                    <span className="inline-flex items-center gap-1.5">
                      <span className={`inline-block w-1.5 h-1.5 rounded-full ${dot(p.healthy)}`} />
                      <span className="text-text-primary">{p.name}</span>
                      {!p.healthy && <span className="text-2xs text-text-tertiary">(inactive)</span>}
                    </span>
                  </td>
                  <td className="text-text-secondary">{p.priority}</td>
                  <td className="text-2xs text-text-tertiary">{(p.asset_classes || []).join(', ')}</td>
                  <td className="text-right text-text-secondary tabular-nums">{p.served}</td>
                  <td className={`text-right tabular-nums ${p.errors ? 'text-amber' : 'text-text-tertiary'}`}>{p.errors}</td>
                  <td className={`text-right tabular-nums ${p.fallbacks_triggered ? 'text-amber' : 'text-text-tertiary'}`}>{p.fallbacks_triggered}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-2 text-2xs text-text-tertiary">
            Requests route to the highest-priority healthy provider and fall back automatically on failure; the serving provider is recorded in each quote's lineage.
          </div>
        </div>
      )}
    </div>
  );
}
