/**
 * RiskParityCompareSection — risk-parity method comparison + honest backtest (Phase 2).
 *
 * Traditional RP (inverse-vol), Return-overlay RP, HRP, CVaR-RP vs a 60/40 benchmark on the
 * SAME real asset returns — Sharpe / Sortino / max drawdown, with each method flagged on whether
 * it actually beats 60/40. Plus bootstrapped risk-contribution fragility bands. Honest ~1yr
 * caveat surfaced. Reads /api/v1/risk-parity-compare.
 */
import { useCallback, useEffect, useState } from 'react';
import { Scale, RefreshCw } from 'lucide-react';
import { DataLineagePopover } from '@/components/ui/DataLineagePopover';

export function RiskParityCompareSection() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [reason, setReason] = useState<string | null>(null);

  const load = useCallback(async (attempt = 0) => {
    setLoading(true); setReason(null);
    const timeout = new Promise<null>((r) => setTimeout(() => r(null), 8000));
    try {
      const res = await Promise.race([fetch('/api/v1/risk-parity-compare').then((r) => r.json()), timeout]);
      if (!res) { if (attempt < 1) { setTimeout(() => load(attempt + 1), 1500); return; } setReason('Timed out.'); setData(null); }
      else if (res.available === false) { setReason(res.reason || 'Unavailable.'); setData(null); }
      else setData(res);
    } catch (e: any) { setReason(e?.message || 'Failed.'); setData(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const rows = data?.results || [];
  const bands = data?.risk_contribution_uncertainty;

  return (
    <div id="risk-parity-compare" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><Scale className="w-3 h-3" /></span>
          <h2 className="section-title">Risk Parity Comparison</h2>
          {data && <DataLineagePopover lineage={{ source: `${(data.universe || []).join(', ')} · ${data.observations} obs`, fetched_at: data.as_of, formula: 'Static full-sample weights per scheme, backtested on the same real returns', notes: (data.citations || []).join('; ') }} />}
        </div>
        <button onClick={() => load()} title="Refresh" aria-label="Refresh" className="p-1 text-text-tertiary hover:text-bloomberg">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading && !data && <div className="p-3 text-2xs text-text-tertiary">Backtesting allocation schemes…</div>}
      {!loading && reason && <div className="p-3 text-xs text-amber border border-amber/30 bg-amber-dim">Unavailable — {reason}</div>}

      {data && rows.length > 0 && (
        <div className="space-y-3">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-2xs text-text-tertiary uppercase tracking-wider">
                  <th className="text-left font-normal pb-1">Method</th>
                  <th className="text-right font-normal pb-1">Sharpe</th>
                  <th className="text-right font-normal pb-1">Sortino</th>
                  <th className="text-right font-normal pb-1">Max DD</th>
                  <th className="text-right font-normal pb-1">vs 60/40</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r: any) => {
                  const bench = r.beats_6040_sharpe === null;
                  return (
                    <tr key={r.method} className={`border-t border-border-subtle ${bench ? 'text-bloomberg' : 'text-text-primary'}`}>
                      <td className="py-1 pr-2">{r.method}</td>
                      <td className="py-1 text-right font-mono tabular-nums">{r.sharpe}</td>
                      <td className="py-1 text-right font-mono tabular-nums">{r.sortino}</td>
                      <td className="py-1 text-right font-mono tabular-nums text-red">{r.max_drawdown_pct}%</td>
                      <td className="py-1 text-right font-mono">
                        {bench ? <span className="text-text-tertiary">—</span>
                          : r.beats_6040_sharpe ? <span className="text-green">beats</span>
                          : <span className="text-amber">no</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Risk-contribution fragility bands (Phase 2C) */}
          {bands?.available && (
            <div className="text-2xs space-y-1">
              <div className="text-text-tertiary uppercase tracking-wider">Inverse-vol risk contribution (90% bootstrap band) · target {(bands.target_risk_share * 100).toFixed(0)}% each</div>
              {bands.per_asset.map((a: any) => (
                <div key={a.asset} className="flex items-center gap-2">
                  <span className="w-28 truncate text-text-secondary">{a.asset}</span>
                  <div className="flex-1 h-2 bg-surface-3 relative">
                    <div className="absolute h-2 bg-blue/40" style={{ left: `${a.p5 * 100}%`, width: `${Math.max(1, (a.p95 - a.p5) * 100)}%` }} />
                    <div className="absolute h-2 w-0.5 bg-bloomberg" style={{ left: `${a.mean_risk_share * 100}%` }} />
                  </div>
                  <span className="w-10 text-right font-mono text-text-primary tabular-nums">{(a.mean_risk_share * 100).toFixed(0)}%</span>
                </div>
              ))}
              <div className="text-text-tertiary pt-0.5">{bands.note}</div>
            </div>
          )}

          <div className="text-2xs text-amber border border-amber/30 bg-amber-dim p-2">{data.note}</div>
        </div>
      )}
    </div>
  );
}
