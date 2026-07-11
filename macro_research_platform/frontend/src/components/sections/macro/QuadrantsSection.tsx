/**
 * QuadrantsSection — Bridgewater Four Quadrants (Phase 1).
 *
 * Classifies the environment on two independent axes — growth surprise × inflation surprise —
 * into Reflation / Goldilocks / Stagflation / Deflation, shows the favored/unfavored asset
 * playbook, and cross-validates against the app's 6-regime label. Reads /api/v1/quadrants.
 */
import { useCallback, useEffect, useState } from 'react';
import { Grid2x2, RefreshCw, CheckCircle2, AlertTriangle } from 'lucide-react';
import { DataLineagePopover } from '@/components/ui/DataLineagePopover';

const CELLS = ['Reflation', 'Goldilocks', 'Stagflation', 'Deflation'];

export function QuadrantsSection() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [reason, setReason] = useState<string | null>(null);

  const load = useCallback(async (attempt = 0) => {
    setLoading(true); setReason(null);
    const timeout = new Promise<null>((r) => setTimeout(() => r(null), 8000));
    try {
      const res = await Promise.race([fetch('/api/v1/quadrants').then((r) => r.json()), timeout]);
      if (!res) { if (attempt < 1) { setTimeout(() => load(attempt + 1), 1500); return; } setReason('Timed out.'); setData(null); }
      else if (res.available === false) { setReason(res.reason || 'Unavailable.'); setData(null); }
      else setData(res);
    } catch (e: any) { setReason(e?.message || 'Failed.'); setData(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const current = data?.quadrant;
  const xv = data?.cross_validation as string | undefined;
  const agrees = data?.agreement === true;

  return (
    <div id="quadrants" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><Grid2x2 className="w-3 h-3" /></span>
          <h2 className="section-title">Four Quadrants (Bridgewater)</h2>
          {data && <DataLineagePopover lineage={{ source: data.source, fetched_at: data.as_of, formula: 'Growth surprise (z) × Inflation surprise (z) vs trailing trend → quadrant + playbook', notes: data.citation }} />}
        </div>
        <button onClick={() => load()} title="Refresh" aria-label="Refresh" className="p-1 text-text-tertiary hover:text-bloomberg">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading && !data && <div className="p-3 text-2xs text-text-tertiary">Classifying environment…</div>}
      {!loading && reason && <div className="p-3 text-xs text-amber border border-amber/30 bg-amber-dim">Unavailable — {reason}</div>}

      {data && current && (
        <div className="space-y-3">
          {/* 2×2 grid, current cell highlighted */}
          <div className="grid grid-cols-2 gap-1">
            {CELLS.map((c) => {
              const active = c === current;
              return (
                <div key={c} className={`p-2 border text-center ${active ? 'border-bloomberg bg-bloomberg/10' : 'border-border-subtle bg-surface-1'}`}>
                  <div className={`text-xs font-bold ${active ? 'text-bloomberg' : 'text-text-tertiary'}`}>{c}</div>
                </div>
              );
            })}
          </div>

          {/* Surprise axes */}
          <div className="flex gap-2 text-2xs">
            <div className="flex-1 p-2 border border-border bg-surface-1">
              <div className="text-text-tertiary uppercase tracking-wider">Growth surprise</div>
              <div className={`font-mono font-bold text-sm ${data.growth_surprise >= 0 ? 'text-green' : 'text-red'}`}>{data.growth_surprise >= 0 ? '+' : ''}{data.growth_surprise?.toFixed(2)}σ</div>
            </div>
            <div className="flex-1 p-2 border border-border bg-surface-1">
              <div className="text-text-tertiary uppercase tracking-wider">Inflation surprise</div>
              <div className={`font-mono font-bold text-sm ${data.inflation_surprise >= 0 ? 'text-amber' : 'text-green'}`}>{data.inflation_surprise >= 0 ? '+' : ''}{data.inflation_surprise?.toFixed(2)}σ</div>
            </div>
          </div>

          {/* Playbook */}
          {data.playbook && (
            <div className="text-2xs space-y-1">
              <div><span className="text-green uppercase tracking-wider">Favored:</span> <span className="text-text-secondary">{(data.playbook.favored || []).join(' · ')}</span></div>
              <div><span className="text-red uppercase tracking-wider">Unfavored:</span> <span className="text-text-secondary">{(data.playbook.unfavored || []).join(' · ')}</span></div>
              {data.playbook.note && <div className="text-text-tertiary pt-1">{data.playbook.note}</div>}
            </div>
          )}

          {/* Cross-validation vs 6-regime */}
          {xv && (
            <div className={`flex items-start gap-2 text-2xs p-2 border ${agrees ? 'border-green/30 bg-green/5' : 'border-amber/40 bg-amber-dim'}`}>
              {agrees ? <CheckCircle2 className="w-3.5 h-3.5 text-green shrink-0" /> : <AlertTriangle className="w-3.5 h-3.5 text-amber shrink-0" />}
              <span className="text-text-secondary">Cross-validation vs 6-regime ({data.regime_6}): {xv}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
