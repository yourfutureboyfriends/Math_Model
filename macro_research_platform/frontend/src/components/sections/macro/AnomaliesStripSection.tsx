/**
 * AnomaliesStripSection — Phase 3 system-wide anomaly strip, pinned to the top of Overview.
 *
 * Lists every tracked metric currently outside 2σ of its own history, ranked by |z-score|,
 * so extremes surface without being asked for. Reads /api/v1/anomalies. When nothing is
 * flagged it collapses to a single "all within normal range" line (still shows the top few
 * z-scores for context). 3-state resolution, bounded load (Phase 9).
 */
import { useCallback, useEffect, useState } from 'react';
import { Activity, RefreshCw } from 'lucide-react';
import { AnomalyBadge } from '@/components/ui/AnomalyBadge';

export function AnomaliesStripSection() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [reason, setReason] = useState<string | null>(null);

  const load = useCallback(async (attempt = 0) => {
    setLoading(true); setReason(null);
    const timeout = new Promise<null>((r) => setTimeout(() => r(null), 8000));
    try {
      const res = await Promise.race([fetch('/api/v1/anomalies').then((r) => r.json()), timeout]);
      if (!res) { if (attempt < 1) { setTimeout(() => load(attempt + 1), 1500); return; } setReason('Timed out.'); setData(null); }
      else if (!res.available) { setReason(res.reason || 'Unavailable.'); setData(null); }
      else setData(res);
    } catch (e: any) { setReason(e?.message || 'Failed.'); setData(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const metrics = data?.metrics ?? [];
  const flagged = metrics.filter((m: any) => m.is_anomalous);
  const fmt = (m: any) => (m.unit === '$' ? `$${m.current.toLocaleString()}` : m.current.toLocaleString());

  return (
    <div id="anomalies" className="terminal-section">
      <div className="section-header mb-2">
        <div className="section-header-left">
          <span className="section-tag"><Activity className="w-3 h-3" /></span>
          <h2 className="section-title">Anomalies</h2>
          {data && (
            <span className={`ml-2 text-2xs font-mono px-1.5 py-0.5 border ${flagged.length ? 'text-amber border-amber/40 bg-amber-dim' : 'text-green border-green/30'}`}>
              {flagged.length ? `${flagged.length} outside 2σ` : 'all within range'}
            </span>
          )}
        </div>
        <button onClick={() => load()} title="Refresh" className="p-1 text-text-tertiary hover:text-bloomberg">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading && !data && <div className="p-2 text-2xs text-text-tertiary">Scanning metrics…</div>}
      {!loading && reason && <div className="p-2 text-2xs text-amber">Unavailable — {reason}</div>}

      {data && (
        <div className="flex flex-wrap gap-2">
          {(flagged.length ? flagged : metrics.slice(0, 4)).map((m: any) => (
            <div key={m.ticker}
              className={`flex items-center gap-2 px-2 py-1.5 border text-xs ${m.is_anomalous ? 'border-amber/40 bg-amber-dim' : 'border-border bg-surface-1'}`}>
              <span className="font-mono text-text-secondary uppercase text-2xs tracking-wider">{m.metric}</span>
              <span className="font-mono font-bold text-text-primary tabular-nums">{fmt(m)}</span>
              <AnomalyBadge zScore={m.z_score} isAnomalous={m.is_anomalous} />
              <span className="text-2xs text-text-tertiary">μ {m.historical_mean.toLocaleString()}</span>
            </div>
          ))}
          {!flagged.length && (
            <span className="self-center text-2xs text-text-tertiary">
              No metric outside 2σ — showing highest deviations. Source: {data.source}, {data.window}d.
            </span>
          )}
        </div>
      )}
    </div>
  );
}
