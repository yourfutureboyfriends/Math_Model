// Phase 8 — Factor Decomposition Section (Redesigned)
// Two Sigma lens factor exposure with terminal aesthetic

import { Target, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { FactorDecompositionData } from '@/types';

interface FactorDecompositionSectionProps {
  data?: FactorDecompositionData;
}

export function FactorDecompositionSection({ data }: FactorDecompositionSectionProps) {
  if (!data) return null;

  const getAlignmentTag = (label: string) => {
    switch (label) {
      case 'Strong':
      case 'Good':
        return 'signal-tag bullish';
      case 'Moderate':
        return 'signal-tag warning';
      default:
        return 'signal-tag bearish';
    }
  };

  const FactorBar = ({ factor, exposure }: { factor: string; exposure: any }) => {
    // Normalize beta to -2 to +2 range for display
    const normalizedBeta = Math.max(-2, Math.min(2, exposure.beta));
    const normalizedOptimal = Math.max(-2, Math.min(2, exposure.optimal));

    // Calculate positions (0% = -2, 50% = 0, 100% = +2)
    const betaPosition = ((normalizedBeta + 2) / 4) * 100;
    const optimalPosition = ((normalizedOptimal + 2) * 100) / 4;

    return (
      <div className="mb-3">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-text-primary capitalize">{factor}</span>
            <span className={getAlignmentTag(exposure.alignment >= 70 ? 'Strong' : exposure.alignment >= 50 ? 'Moderate' : 'Poor')}>
              {exposure.alignment}%
            </span>
          </div>
          <div className="text-2xs text-text-secondary">
            <span className="font-mono">{exposure.beta > 0 ? '+' : ''}{exposure.beta.toFixed(2)}</span>
            <span className="text-text-tertiary mx-1">|</span>
            <span className="text-text-tertiary">Opt: </span>
            <span className="font-mono">{exposure.optimal > 0 ? '+' : ''}{exposure.optimal.toFixed(2)}</span>
          </div>
        </div>

        {/* Factor bar */}
        <div className="relative h-2 bg-surface-4">
          {/* Gradient background - using CSS classes instead of inline gradient */}
          <div className="absolute inset-0 bg-gradient-to-r from-red via-text-tertiary to-green" />

          {/* Optimal marker */}
          <div
            className="absolute top-0 bottom-0 w-px bg-text-tertiary z-10"
            style={{ left: `${optimalPosition}%` }}
          />

          {/* Current position marker */}
          <div
            className="absolute top-1/2 w-2 h-2 bg-bloomberg border border-surface-2 z-20"
            style={{
              left: `${betaPosition}%`,
              transform: `translate(-50%, -50%)`
            }}
          />
        </div>

        <div className="flex items-center justify-between mt-1 text-2xs text-text-tertiary">
          <span>-2</span>
          <span className="text-text-secondary">{exposure.signal}</span>
          <span>+2</span>
        </div>
      </div>
    );
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
        {/* Header with overall alignment */}
        <div className="flex items-center justify-between p-3 bg-surface-1 border border-border">
          <div className="flex items-center gap-2">
            <Target className="w-3 h-3 text-text-secondary" />
            <div>
              <div className="text-2xs text-text-tertiary uppercase tracking-wider">Overall Alignment</div>
              <div className="text-lg font-mono font-bold text-text-primary">{data.overallAlignment}%</div>
            </div>
          </div>
          <div className="text-right">
            <span className={getAlignmentTag(data.alignmentLabel)}>
              {data.alignmentLabel.toUpperCase()}
            </span>
            <div className="text-2xs text-text-tertiary mt-1">{data.portfolioType}</div>
          </div>
        </div>

        {/* Factor exposure bars */}
        <div className="p-3 bg-surface-1 border border-border">
          {data.factorExposures?.equity && (
            <FactorBar factor="equity" exposure={data.factorExposures.equity} />
          )}
          {data.factorExposures?.rates && (
            <FactorBar factor="rates" exposure={data.factorExposures.rates} />
          )}
          {data.factorExposures?.inflation && (
            <FactorBar factor="inflation" exposure={data.factorExposures.inflation} />
          )}
          {data.factorExposures?.credit && (
            <FactorBar factor="credit" exposure={data.factorExposures.credit} />
          )}
        </div>

        {/* Dominant factor */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="flex items-center gap-2 mb-2">
            {data.dominantFactorBeta > 0 ? (
              <TrendingUp className="w-3 h-3 text-green" />
            ) : data.dominantFactorBeta < 0 ? (
              <TrendingDown className="w-3 h-3 text-red" />
            ) : (
              <Minus className="w-3 h-3 text-text-tertiary" />
            )}
            <span className="text-xs font-medium text-text-primary">
              Dominant: {data.dominantFactor}
            </span>
            <span className="text-2xs text-text-tertiary font-mono">β {data.dominantFactorBeta > 0 ? '+' : ''}{data.dominantFactorBeta.toFixed(2)}</span>
          </div>
          <p className="text-xs text-text-secondary">{data.interpretation}</p>
        </div>

        {/* Rebalance suggestions */}
        {data.rebalanceSuggestions && data.rebalanceSuggestions.length > 0 && (
          <div className="p-3 border border-amber bg-amber-dim">
            <div className="text-2xs text-amber uppercase tracking-wider mb-2">Rebalance Suggestions</div>
            <ul className="space-y-1">
              {data.rebalanceSuggestions.map((suggestion, idx) => (
                <li key={idx} className="text-xs text-text-secondary flex items-start gap-2">
                  <span className="text-amber">›</span>
                  {suggestion}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Asset betas table */}
        {data.assetBetas && data.assetBetas.length > 0 && (
          <div className="border border-border bg-surface-1 overflow-hidden">
            <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2">
              <span className="text-2xs text-text-tertiary uppercase tracking-wider">Asset Betas</span>
            </div>
            <table className="w-full">
              <thead>
                <tr className="border-b border-border-subtle">
                  <th className="text-left py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Asset</th>
                  <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Eq</th>
                  <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Rate</th>
                  <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Inf</th>
                  <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Cred</th>
                  <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">R²</th>
                </tr>
              </thead>
              <tbody>
                {data.assetBetas.slice(0, 5).map((asset) => (
                  <tr key={asset.ticker} className="border-b border-border-subtle last:border-0">
                    <td className="py-2 px-2 text-sm text-text-primary">{asset.ticker}</td>
                    <td className="py-2 px-2 text-center font-mono text-2xs">
                      <span className={asset.equity && asset.equity > 0 ? 'text-green' : asset.equity && asset.equity < 0 ? 'text-red' : 'text-text-tertiary'}>
                        {asset.equity ? (asset.equity > 0 ? '+' : '') + asset.equity.toFixed(2) : '—'}
                      </span>
                    </td>
                    <td className="py-2 px-2 text-center font-mono text-2xs">
                      <span className={asset.rates && asset.rates > 0 ? 'text-green' : asset.rates && asset.rates < 0 ? 'text-red' : 'text-text-tertiary'}>
                        {asset.rates ? (asset.rates > 0 ? '+' : '') + asset.rates.toFixed(2) : '—'}
                      </span>
                    </td>
                    <td className="py-2 px-2 text-center font-mono text-2xs">
                      <span className={asset.inflation && asset.inflation > 0 ? 'text-green' : asset.inflation && asset.inflation < 0 ? 'text-red' : 'text-text-tertiary'}>
                        {asset.inflation ? (asset.inflation > 0 ? '+' : '') + asset.inflation.toFixed(2) : '—'}
                      </span>
                    </td>
                    <td className="py-2 px-2 text-center font-mono text-2xs">
                      <span className={asset.credit && asset.credit > 0 ? 'text-green' : asset.credit && asset.credit < 0 ? 'text-red' : 'text-text-tertiary'}>
                        {asset.credit ? (asset.credit > 0 ? '+' : '') + asset.credit.toFixed(2) : '—'}
                      </span>
                    </td>
                    <td className="py-2 px-2 text-center font-mono text-2xs text-text-secondary">{asset.r2.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
