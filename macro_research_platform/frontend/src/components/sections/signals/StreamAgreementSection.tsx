/**
 * StreamAgreementSection — Bridgewater 3-stream signal agreement (Phase 3).
 *
 * Reduces live signals to three INDEPENDENT evidence streams — macro drivers, intermarket
 * action, capital flows — each risk-on/off/neutral, and shows the agreement score + the
 * position-sizing multiplier conviction implies. Reads /api/v1/stream-agreement.
 */
import { useCallback, useEffect, useState } from 'react';
import { Layers, RefreshCw, ArrowUp, ArrowDown, Minus } from 'lucide-react';
import { DataLineagePopover } from '@/components/ui/DataLineagePopover';

const STREAM_LABEL: Record<string, string> = {
  macro: 'Macro Drivers', intermarket: 'Intermarket Action', flows: 'Capital Flows',
};
const CONV_TONE: Record<string, string> = {
  high: 'text-green', moderate: 'text-bloomberg', conflicted: 'text-amber', low: 'text-text-tertiary',
};

function Dir({ d }: { d: number }) {
  if (d > 0) return <span className="flex items-center gap-1 text-green"><ArrowUp className="w-3 h-3" />risk-on</span>;
  if (d < 0) return <span className="flex items-center gap-1 text-red"><ArrowDown className="w-3 h-3" />risk-off</span>;
  return <span className="flex items-center gap-1 text-text-tertiary"><Minus className="w-3 h-3" />neutral</span>;
}

export function StreamAgreementSection() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [reason, setReason] = useState<string | null>(null);

  const load = useCallback(async (attempt = 0) => {
    setLoading(true); setReason(null);
    const timeout = new Promise<null>((r) => setTimeout(() => r(null), 8000));
    try {
      const res = await Promise.race([fetch('/api/v1/stream-agreement').then((r) => r.json()), timeout]);
      if (!res) { if (attempt < 1) { setTimeout(() => load(attempt + 1), 1500); return; } setReason('Timed out.'); setData(null); }
      else if (res.available === false) { setReason(res.reason || 'Unavailable.'); setData(null); }
      else setData(res);
    } catch (e: any) { setReason(e?.message || 'Failed.'); setData(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const streams = data?.streams || {};
  const score = data ? Math.round((data.agreement_score || 0) * 100) : 0;

  return (
    <div id="stream-agreement" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><Layers className="w-3 h-3" /></span>
          <h2 className="section-title">Signal Stream Agreement</h2>
          {data && <DataLineagePopover lineage={{ source: data.source, fetched_at: data.as_of, formula: 'Macro / intermarket / flows each reduced to risk-on/off/neutral; conviction scales with independent agreement', notes: data.citation }} />}
        </div>
        <button onClick={() => load()} title="Refresh" aria-label="Refresh" className="p-1 text-text-tertiary hover:text-bloomberg">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading && !data && <div className="p-3 text-2xs text-text-tertiary">Reconciling evidence streams…</div>}
      {!loading && reason && <div className="p-3 text-xs text-amber border border-amber/30 bg-amber-dim">Unavailable — {reason}</div>}

      {data && (
        <div className="space-y-3">
          {/* Headline */}
          <div className="p-3 border border-border bg-surface-1">
            <div className="flex items-baseline justify-between">
              <span className="text-sm text-text-primary">Consensus: <span className="font-bold text-bloomberg">{data.consensus_direction}</span></span>
              <span className={`text-2xs uppercase font-bold ${CONV_TONE[data.conviction] || 'text-text-secondary'}`}>{data.conviction} conviction</span>
            </div>
            <div className="text-2xs text-text-secondary mt-1">
              {data.agreeing_streams}/3 streams agree · size <span className="font-mono font-bold text-text-primary">×{data.sizing_multiplier}</span> within VaR budget
            </div>
            <div className="mt-2 h-1.5 bg-surface-3">
              <div className="h-1.5 bg-bloomberg" style={{ width: `${score}%` }} />
            </div>
          </div>

          {/* Per-stream */}
          <div className="space-y-1">
            {['macro', 'intermarket', 'flows'].map((k) => (
              <div key={k} className="flex items-center justify-between px-2 py-1.5 border border-border-subtle bg-surface-1 text-xs">
                <span className="text-text-secondary">{STREAM_LABEL[k]}</span>
                <span className="font-mono text-2xs"><Dir d={streams[k] ?? 0} /></span>
              </div>
            ))}
          </div>
          <div className="text-2xs text-text-tertiary">{data.note}</div>
        </div>
      )}
    </div>
  );
}
