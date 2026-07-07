// Phase 8 — Factor Decomposition Section
// Renders the backend factor decomposition ({asset, rSquared, factors:[{factor,
// exposure, contribution, tStat, significance}]}) as a real exposure table.

import { Target, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { FactorDecompositionData } from '@/types';
import { useMacroStore } from '@/store/macroStore';

interface FactorDecompositionSectionProps {
  data?: FactorDecompositionData;
}

export function FactorDecompositionSection({ data: dataProp }: FactorDecompositionSectionProps) {
  const _fullDash = useMacroStore((s) => s.fullDashboard);
  let data: any = dataProp;
  if (!data) data = (_fullDash as any)?.factorDecomposition as any;
  if (!data) return null;

  const factors: any[] = Array.isArray(data.factors) ? data.factors : [];
  const rSquared: number | undefined = typeof data.rSquared === 'number' ? data.rSquared : undefined;
  const asset: string = data.asset ?? 'Portfolio';

  // Dominant factor = largest absolute contribution.
  const dominant = factors.slice().sort(
    (a, b) => Math.abs(b.contribution ?? 0) - Math.abs(a.contribution ?? 0)
  )[0];

  const num = (v: any, d = 2) => (typeof v === 'number' && isFinite(v) ? v.toFixed(d) : '—');

  const sigTag = (sig: string) => {
    const s = String(sig).toLowerCase();
    if (s.includes('highly')) return 'signal-tag bullish';
    if (s.includes('significant')) return 'signal-tag warning';
    return 'signal-tag neutral';
  };

  return (
    <div id="factor-decomposition" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">27</span>
          <h2 className="section-title">Factor Decomposition</h2>
        </div>
      </div>

      <div className="space-y-3">
        {/* Header: asset + model fit */}
        <div className="flex items-center justify-between p-3 bg-surface-1 border border-border">
          <div className="flex items-center gap-2">
            <Target className="w-3 h-3 text-text-secondary" />
            <div>
              <div className="text-2xs text-text-tertiary uppercase tracking-wider">Asset</div>
              <div className="text-lg font-mono font-bold text-text-primary">{asset}</div>
            </div>
          </div>
          {rSquared != null && (
            <div className="text-right">
              <div className="text-2xs text-text-tertiary uppercase tracking-wider">Model Fit (R²)</div>
              <div className="text-lg font-mono font-bold text-text-primary">{(rSquared * 100).toFixed(0)}%</div>
            </div>
          )}
        </div>

        {/* Dominant factor */}
        {dominant && (
          <div className="p-3 bg-surface-1 border border-border">
            <div className="flex items-center gap-2">
              {(dominant.exposure ?? 0) > 0 ? (
                <TrendingUp className="w-3 h-3 text-green" />
              ) : (dominant.exposure ?? 0) < 0 ? (
                <TrendingDown className="w-3 h-3 text-red" />
              ) : (
                <Minus className="w-3 h-3 text-text-tertiary" />
              )}
              <span className="text-xs font-medium text-text-primary">Dominant: {dominant.factor}</span>
              <span className="text-2xs text-text-tertiary font-mono">
                β {(dominant.exposure ?? 0) > 0 ? '+' : ''}{num(dominant.exposure)}
              </span>
            </div>
          </div>
        )}

        {/* Factor exposure table */}
        {factors.length > 0 && (
          <div className="border border-border bg-surface-1 overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border bg-surface-2">
                  <th className="text-left py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Factor</th>
                  <th className="text-right py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Exposure (β)</th>
                  <th className="text-right py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Contribution</th>
                  <th className="text-right py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">t-Stat</th>
                  <th className="text-center py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Significance</th>
                </tr>
              </thead>
              <tbody>
                {factors.map((f, idx) => (
                  <tr key={f.factor ?? idx} className="border-b border-border-subtle last:border-0 hover:bg-surface-3 transition-colors">
                    <td className="py-2 px-3 text-sm text-text-primary">{f.factor}</td>
                    <td className={`py-2 px-3 text-right font-mono text-sm ${(f.exposure ?? 0) > 0 ? 'text-green' : (f.exposure ?? 0) < 0 ? 'text-red' : 'text-text-tertiary'}`}>
                      {(f.exposure ?? 0) > 0 ? '+' : ''}{num(f.exposure)}
                    </td>
                    <td className="py-2 px-3 text-right font-mono text-sm text-text-primary">
                      {typeof f.contribution === 'number' ? `${f.contribution.toFixed(0)}%` : '—'}
                    </td>
                    <td className="py-2 px-3 text-right font-mono text-sm text-text-secondary">{num(f.tStat, 1)}</td>
                    <td className="py-2 px-3 text-center">
                      {f.significance && <span className={sigTag(f.significance)}>{f.significance}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {data.interpretation && (
          <div className="p-3 bg-surface-1 border border-border">
            <p className="text-xs text-text-secondary">{data.interpretation}</p>
          </div>
        )}
      </div>
    </div>
  );
}
