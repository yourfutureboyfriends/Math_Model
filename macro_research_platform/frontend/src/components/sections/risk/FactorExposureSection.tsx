/**
 * FactorExposureSection — Phase 2 factor risk model.
 *
 * Shows the portfolio's OLS factor loadings (betas to equity/size/value/growth/
 * momentum/rates/credit/commodity/USD/vol) with a toggle between raw exposure and each
 * factor's contribution to portfolio volatility, plus a per-position breakdown. Reads
 * /api/v1/risk/factor-exposure, which is computed against the ingested positions.
 */
import { useCallback, useEffect, useState } from 'react';
import { Activity, RefreshCw } from 'lucide-react';

interface FactorRow {
  factor: string; label: string; proxy: string;
  exposure: number; factor_vol_annual: number; contribution_to_vol: number;
}
interface PositionRow {
  symbol: string; book: string; net_weight: number; r_squared: number;
  loadings: Record<string, number>; estimated: boolean;
}
interface Resp {
  available: boolean; reason?: string; book?: string;
  factors: FactorRow[]; positions?: PositionRow[]; observations?: number; computed_at?: string;
}

export function FactorExposureSection() {
  const [data, setData] = useState<Resp | null>(null);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<'exposure' | 'vol'>('exposure');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch('/api/v1/risk/factor-exposure');
      setData(r.ok ? await r.json() : { available: false, reason: `HTTP ${r.status}`, factors: [] });
    } catch (e: any) {
      setData({ available: false, reason: e?.message || 'failed', factors: [] });
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const factors = data?.factors ?? [];
  const maxAbs = Math.max(0.01, ...factors.map((f) => (mode === 'exposure' ? Math.abs(f.exposure) : f.contribution_to_vol)));

  return (
    <div id="factor-exposure" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><Activity className="w-3 h-3" /></span>
          <h2 className="section-title">Factor Exposure</h2>
          {data?.available && <span className="section-meta">{data.observations} obs · {data.book}</span>}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex border border-border-subtle text-2xs">
            <button onClick={() => setMode('exposure')}
              className={`px-2 py-0.5 ${mode === 'exposure' ? 'bg-bloomberg text-bg' : 'text-text-secondary hover:text-text-primary'}`}>Exposure</button>
            <button onClick={() => setMode('vol')}
              className={`px-2 py-0.5 ${mode === 'vol' ? 'bg-bloomberg text-bg' : 'text-text-secondary hover:text-text-primary'}`}>Vol Contribution</button>
          </div>
          <button onClick={load} title="Refresh" aria-label="Refresh" className="p-1 text-text-tertiary hover:text-bloomberg">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {loading && !data && (
        <div className="p-6 text-center text-sm text-text-secondary">Estimating factor loadings…</div>
      )}

      {data && !data.available && (
        <div className="p-6 bg-surface-1 border border-border text-center text-sm text-text-secondary">
          {data.reason || 'Factor exposure unavailable.'}
        </div>
      )}

      {data?.available && (
        <div className="space-y-3">
          {/* Factor bars */}
          <div className="p-3 bg-surface-1 border border-border space-y-2">
            {factors.map((f) => {
              const val = mode === 'exposure' ? f.exposure : f.contribution_to_vol;
              const w = (Math.abs(val) / maxAbs) * 50; // % of half-width
              const pos = val >= 0;
              return (
                <div key={f.factor} className="flex items-center gap-2 text-xs">
                  <span className="w-28 shrink-0 text-text-secondary">{f.label}</span>
                  <div className="flex-1 relative h-3 bg-surface-3">
                    <div className="absolute top-0 bottom-0 left-1/2 w-px bg-text-tertiary/30" />
                    <div
                      className={`absolute top-0 bottom-0 ${pos ? 'bg-green' : 'bg-red'}`}
                      style={{ left: pos ? '50%' : `${50 - w}%`, width: `${w}%` }}
                    />
                  </div>
                  <span className={`w-16 text-right font-mono ${mode === 'exposure' ? (pos ? 'text-green' : 'text-red') : 'text-text-primary'}`}>
                    {mode === 'exposure' ? `${pos ? '+' : ''}${val.toFixed(2)}` : `${(val * 100).toFixed(0)}%`}
                  </span>
                </div>
              );
            })}
            <div className="text-2xs text-text-tertiary pt-1 border-t border-border-subtle">
              {mode === 'exposure'
                ? 'Portfolio beta to each factor (net-weighted OLS loadings, 1y daily returns).'
                : 'Share of portfolio variance attributable to each factor (independent-factor approximation).'}
            </div>
          </div>

          {/* Per-position breakdown */}
          {data.positions && data.positions.length > 0 && (
            <div className="border border-border bg-surface-1 overflow-x-auto">
              <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2 text-2xs text-text-tertiary uppercase tracking-wider">
                Per-Position Loadings
              </div>
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border-subtle text-2xs text-text-tertiary uppercase">
                    <th className="text-left py-2 px-3 font-medium">Symbol</th>
                    <th className="text-right py-2 px-3 font-medium">Net W</th>
                    <th className="text-right py-2 px-3 font-medium">R²</th>
                    <th className="text-right py-2 px-3 font-medium">Equity β</th>
                    <th className="text-right py-2 px-3 font-medium">Rates β</th>
                    <th className="text-right py-2 px-3 font-medium">Credit β</th>
                  </tr>
                </thead>
                <tbody>
                  {data.positions.map((p) => (
                    <tr key={p.symbol} className="border-b border-border-subtle last:border-0">
                      <td className="py-2 px-3 text-sm text-text-primary">{p.symbol}
                        {!p.estimated && <span className="ml-1 text-2xs text-amber">no fit</span>}</td>
                      <td className={`py-2 px-3 text-right font-mono text-xs ${p.net_weight >= 0 ? 'text-green' : 'text-red'}`}>{(p.net_weight * 100).toFixed(1)}%</td>
                      <td className="py-2 px-3 text-right font-mono text-xs text-text-secondary">{p.r_squared.toFixed(2)}</td>
                      <td className="py-2 px-3 text-right font-mono text-xs text-text-primary">{p.loadings.equity?.toFixed(2) ?? '—'}</td>
                      <td className="py-2 px-3 text-right font-mono text-xs text-text-primary">{p.loadings.rates?.toFixed(2) ?? '—'}</td>
                      <td className="py-2 px-3 text-right font-mono text-xs text-text-primary">{p.loadings.credit?.toFixed(2) ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
