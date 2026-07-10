/**
 * SystemAuditSection — Phase 8 audit & compliance.
 *
 * Two panels: an append-only decision log (every override/approval with user, timestamp
 * and required rationale) and a point-in-time "time machine" (browse periodic snapshots
 * of regime / ensemble / portfolio risk to answer "what did the system say at time T").
 * Reads /api/v1/audit/{decisions,snapshots}.
 */
import { useCallback, useEffect, useState } from 'react';
import { ScrollText, History, RefreshCw, Plus } from 'lucide-react';
import { actorHeaders, currentActor } from '../../../lib/actor';

const t = (iso?: string) => (iso ? new Date(iso).toLocaleString() : '—');

export function SystemAuditSection() {
  const [decisions, setDecisions] = useState<any[]>([]);
  const [snapshots, setSnapshots] = useState<any[]>([]);
  const [dq, setDq] = useState<any>(null);
  const [selected, setSelected] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState('');
  const [rationale, setRationale] = useState('');
  const [saving, setSaving] = useState(false);
  const [logErr, setLogErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [dr, sr, qr] = await Promise.all([
        fetch('/api/v1/audit/decisions').then((r) => r.json()).catch(() => null),
        fetch('/api/v1/audit/snapshots').then((r) => r.json()).catch(() => null),
        fetch('/api/v1/data-quality').then((r) => r.json()).catch(() => null),
      ]);
      setDecisions(dr?.decisions || []);
      setSnapshots(sr?.snapshots || []);
      setDq(qr);
    } finally { setLoading(false); }
  }, []);
  const dqTone = (s: string) => (s === 'PASS' ? 'text-green' : s === 'WARN' ? 'text-amber' : s === 'FAIL' ? 'text-red' : 'text-text-tertiary');
  useEffect(() => { load(); }, [load]);

  const openSnapshot = async (id: number) => {
    const r = await fetch(`/api/v1/audit/snapshots/${id}`);
    if (r.ok) setSelected(await r.json());
  };

  const logDecision = async () => {
    if (!action.trim() || !rationale.trim()) { setLogErr('Action and rationale are required.'); return; }
    setSaving(true); setLogErr(null);
    try {
      const r = await fetch('/api/v1/audit/decisions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...actorHeaders() },
        body: JSON.stringify({ action: action.trim(), rationale: rationale.trim() }),
      });
      if (!r.ok) { setLogErr((await r.json().catch(() => ({})))?.detail || 'Failed to log decision.'); return; }
      setAction(''); setRationale('');
      await load();
    } finally { setSaving(false); }
  };

  return (
    <div id="system-audit" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><ScrollText className="w-3 h-3" /></span>
          <h2 className="section-title">Audit &amp; Compliance</h2>
        </div>
        <button onClick={load} title="Refresh" aria-label="Refresh" className="p-1 text-text-tertiary hover:text-bloomberg">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Data-quality checks */}
      {dq?.available && (
        <div className="mb-3 p-2 bg-surface-1 border border-border flex items-center gap-3 flex-wrap">
          <span className="text-2xs text-text-tertiary uppercase tracking-wider">Data Quality</span>
          <span className={`text-xs font-mono font-bold ${dqTone(dq.overall)}`}>{dq.overall}</span>
          <span className="text-2xs text-text-tertiary">{dq.counts?.PASS}/{dq.series?.length} series clean</span>
          <div className="flex flex-wrap gap-1">
            {dq.series?.map((s: any) => (
              <span key={s.series} title={`${s.series}: ${s.status}${s.jump_count ? ` · ${s.jump_count} bad ticks` : ''}`}
                className={`inline-block w-2 h-2 rounded-full ${s.status === 'PASS' ? 'bg-green' : s.status === 'WARN' ? 'bg-amber' : s.status === 'FAIL' ? 'bg-red' : 'bg-text-tertiary'}`} />
            ))}
          </div>
          <span className="text-2xs text-text-tertiary ml-auto">Bad-tick / outlier scan on {dq.series?.length} price feeds</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {/* Decision log */}
        <div className="border border-border bg-surface-1 overflow-hidden">
          <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2 text-2xs text-text-tertiary uppercase tracking-wider flex items-center gap-1">
            <ScrollText className="w-3 h-3" /> Decision Log
            <span className="ml-auto normal-case tracking-normal text-text-tertiary">acting as <span className="text-bloomberg font-mono">{currentActor()}</span></span>
          </div>
          {/* Manual decision entry — attributed to the logged-in user via X-User */}
          <div className="px-3 py-2 border-b border-border-subtle bg-surface-2/40 space-y-1.5">
            <input value={action} onChange={(e) => setAction(e.target.value)} placeholder="Action (e.g. Override recession model)"
              className="w-full bg-surface-1 border border-border px-2 py-1 text-xs text-text-primary placeholder:text-text-tertiary focus:border-bloomberg outline-none" />
            <input value={rationale} onChange={(e) => setRationale(e.target.value)} placeholder="Rationale (required)"
              className="w-full bg-surface-1 border border-border px-2 py-1 text-xs text-text-primary placeholder:text-text-tertiary focus:border-bloomberg outline-none" />
            <div className="flex items-center gap-2">
              <button onClick={logDecision} disabled={saving}
                className="flex items-center gap-1 px-2 py-1 text-2xs bg-bloomberg-muted text-bloomberg hover:bg-bloomberg hover:text-black disabled:opacity-50">
                <Plus className="w-3 h-3" /> {saving ? 'Logging…' : 'Log decision'}
              </button>
              {logErr && <span className="text-2xs text-red">{logErr}</span>}
            </div>
          </div>
          <div className="max-h-72 overflow-y-auto">
            {decisions.length === 0 && <div className="p-3 text-2xs text-text-tertiary">No decisions logged yet.</div>}
            {decisions.map((d) => (
              <div key={d.id} className="px-3 py-2 border-b border-border-subtle last:border-0 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-text-primary">{d.action}</span>
                  <span className="text-2xs text-text-tertiary">{t(d.ts)}</span>
                </div>
                <div className="text-2xs text-text-secondary">
                  <span className="text-bloomberg">{d.user}</span>
                  {d.target && <span> · {d.target}</span>}
                  <span> — {d.rationale}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Time machine */}
        <div className="border border-border bg-surface-1 overflow-hidden">
          <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2 text-2xs text-text-tertiary uppercase tracking-wider flex items-center gap-1">
            <History className="w-3 h-3" /> Time Machine ({snapshots.length} snapshots)
          </div>
          <div className="flex" style={{ maxHeight: '18rem' }}>
            <div className="w-40 border-r border-border-subtle overflow-y-auto shrink-0">
              {snapshots.length === 0 && <div className="p-3 text-2xs text-text-tertiary">Capturing…</div>}
              {snapshots.map((s) => (
                <button key={s.id} onClick={() => openSnapshot(s.id)}
                  className={`w-full text-left px-2 py-1.5 border-b border-border-subtle text-2xs font-mono hover:bg-surface-3 ${selected?.id === s.id ? 'bg-bloomberg-muted text-bloomberg' : 'text-text-secondary'}`}>
                  {t(s.ts)}
                </button>
              ))}
            </div>
            <div className="flex-1 p-3 overflow-y-auto text-xs">
              {!selected && <div className="text-2xs text-text-tertiary">Select a snapshot to see the system state at that moment.</div>}
              {selected && (
                <div className="space-y-1.5 font-mono">
                  <div className="text-2xs text-text-tertiary">{t(selected.ts)}</div>
                  {selected.state?.regime && (
                    <div><span className="text-text-tertiary">regime:</span> <span className="text-text-primary">{selected.state.regime.current}</span> <span className="text-text-secondary">({selected.state.regime.confidence != null ? (selected.state.regime.confidence * 100).toFixed(0) + '%' : '—'})</span></div>
                  )}
                  {selected.state?.ensemble && (
                    <div><span className="text-text-tertiary">ensemble:</span> <span className="text-text-primary">{selected.state.ensemble.score}</span> <span className="text-text-secondary">agree {selected.state.ensemble.agreement != null ? (selected.state.ensemble.agreement * 100).toFixed(0) + '%' : '—'} · {selected.state.ensemble.mode}</span></div>
                  )}
                  {selected.state?.key_metrics && (
                    <div><span className="text-text-tertiary">recession:</span> <span className="text-text-primary">{selected.state.key_metrics.recession ?? '—'}%</span></div>
                  )}
                  {selected.state?.portfolio && (
                    <div className="pt-1 border-t border-border-subtle">
                      <div className="text-2xs text-text-tertiary uppercase">Portfolio</div>
                      <div><span className="text-text-tertiary">gross:</span> ${Math.round(selected.state.portfolio.gross_exposure).toLocaleString()} · <span className="text-text-tertiary">net:</span> ${Math.round(selected.state.portfolio.net_exposure).toLocaleString()}</div>
                      <div><span className="text-text-tertiary">P&L:</span> <span className={selected.state.portfolio.total_unrealized_pnl >= 0 ? 'text-green' : 'text-red'}>${Math.round(selected.state.portfolio.total_unrealized_pnl).toLocaleString()}</span> · {selected.state.portfolio.position_count} positions</div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
