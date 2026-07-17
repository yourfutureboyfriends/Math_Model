/**
 * FactorValidationSection — factor out-of-sample validation (Phase 4, AQR discipline).
 *
 * For each factor: in-sample vs out-of-sample R², with factors whose explanatory power does not
 * survive out-of-sample explicitly flagged UNSTABLE (overfitting), plus each factor's own max
 * drawdown so tail risk is visible. Reads /api/v1/factor-validation.
 */
import { useCallback, useEffect, useState } from 'react';
import { FlaskConical, RefreshCw, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { DataLineagePopover } from '@/components/ui/DataLineagePopover';

export function FactorValidationSection() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [reason, setReason] = useState<string | null>(null);

  const load = useCallback(async (attempt = 0) => {
    setLoading(true); setReason(null);
    const timeout = new Promise<null>((r) => setTimeout(() => r(null), 8000));
    try {
      const res = await Promise.race([fetch('/api/v1/factor-validation').then((r) => r.json()), timeout]);
      if (!res) { if (attempt < 1) { setTimeout(() => load(attempt + 1), 1500); return; } setReason('Timed out.'); setData(null); }
      else if (res.available === false) { setReason(res.reason || 'Unavailable.'); setData(null); }
      else setData(res);
    } catch (e: any) { setReason(e?.message || 'Failed.'); setData(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const factors = (data?.factors || []).filter((f: any) => f.available);

  return (
    <div id="factor-validation" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><FlaskConical className="w-3 h-3" /></span>
          <h2 className="section-title">Factor OOS Validation (AQR)</h2>
          {data && <DataLineagePopover lineage={{ source: data.benchmark, fetched_at: data.as_of, formula: data.method, notes: data.citation }} />}
        </div>
        <button onClick={() => load()} title="Refresh" aria-label="Refresh" className="p-1 text-text-tertiary hover:text-bloomberg">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading && !data && <div className="p-3 text-2xs text-text-tertiary">Splitting in/out-of-sample…</div>}
      {!loading && reason && <div className="p-3 text-xs text-amber border border-amber/30 bg-amber-dim">Unavailable — {reason}</div>}

      {data && factors.length > 0 && (
        <div className="space-y-2">
          {/* column header */}
          <div className="flex items-center gap-2 text-2xs text-text-tertiary uppercase tracking-wider px-2">
            <span className="flex-1">Factor</span>
            <span className="w-14 text-right">R² IS</span>
            <span className="w-14 text-right">R² OOS</span>
            <span className="w-14 text-right">Max DD</span>
          </div>
          {factors.map((f: any) => (
            <div key={f.factor} className={`flex items-center gap-2 px-2 py-1.5 border text-xs ${f.unstable ? 'border-amber/40 bg-amber-dim' : 'border-border-subtle bg-surface-1'}`}>
              <span className="flex-1 flex items-center gap-1.5 text-text-secondary">
                {f.unstable ? <AlertTriangle className="w-3 h-3 text-amber" /> : <CheckCircle2 className="w-3 h-3 text-green" />}
                {f.factor}
              </span>
              <span className="w-14 text-right font-mono text-text-primary tabular-nums">{f.in_sample_r2?.toFixed(2)}</span>
              <span className={`w-14 text-right font-mono tabular-nums ${f.unstable ? 'text-amber' : 'text-text-primary'}`}>{f.out_of_sample_r2?.toFixed(2)}</span>
              <span className="w-14 text-right font-mono text-red tabular-nums">{f.factor_max_drawdown_pct}%</span>
            </div>
          ))}
          <div className={`text-2xs p-2 border ${data.n_unstable ? 'text-amber border-amber/30 bg-amber-dim' : 'text-text-tertiary border-border-subtle'}`}>{data.note}</div>
        </div>
      )}
    </div>
  );
}
