// Phase 8 — Correlation Regime Adjustment Section (Redesigned)
// Correlation regime monitor with terminal aesthetic

import { GitBranch, AlertTriangle, Link2, Unlink } from 'lucide-react';
import type { CorrelationRegimeData } from '@/types';

interface CorrelationRegimeSectionProps {
  data?: CorrelationRegimeData;
}

export function CorrelationRegimeSection({ data }: CorrelationRegimeSectionProps) {
  if (!data) {
    return (
      <div id="correlation" className="terminal-section">
        <div className="section-header mb-3">
          <div className="section-header-left">
            <span className="section-tag">26</span>
            <h2 className="section-title">Correlation Regime</h2>
          </div>
        </div>
        <div className="p-4 text-text-secondary text-sm">Loading...</div>
      </div>
    );
  }

  // Safe destructuring with defaults
  const currentRegime = data?.currentRegime ?? 'STANDARD';
  const switchTriggered = data?.switchTriggered ?? false;
  const equityBondCorrelation = data?.equityBondCorrelation ?? 0;
  const fallbackStrategy = data?.fallbackStrategy ?? 'STANDARD';
  const correlations = data?.correlations ?? [];
  const normalWeights = data?.riskParityAdjustment?.normalWeights ?? {};
  const adjustedWeights = data?.riskParityAdjustment?.adjustedWeights ?? {};
  const riskParityRationale = data?.riskParityAdjustment?.rationale ?? '';

  const getCorrelationIcon = (correlation: number) => {
    if (Math.abs(correlation) > 0.3) return <Link2 className="w-3 h-3 text-red" />;
    return <Unlink className="w-3 h-3 text-green" />;
  };

  const getCorrelationColor = (correlation: number) => {
    if (correlation > 0.3) return 'text-red';
    if (correlation > 0) return 'text-amber';
    if (correlation > -0.3) return 'text-green';
    return 'text-blue';
  };

  const getRegimeTag = (regime: string) => {
    return regime === 'positive' ? 'signal-tag bearish' : 'signal-tag bullish';
  };

  return (
    <div id="correlation" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">26</span>
          <h2 className="section-title">Correlation Regime</h2>
          <span className={`section-meta ${switchTriggered ? 'text-red' : 'text-green'}`}>
            {(currentRegime ?? '').replace(/_/g, ' ').toUpperCase()}
          </span>
        </div>
      </div>

      <div className="space-y-3">
        {/* Current Regime Header */}
        <div className={`p-3 border ${switchTriggered ? 'bg-red-dim border-red' : 'bg-green-dim border-green'}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <GitBranch className={`w-4 h-4 ${switchTriggered ? 'text-red' : 'text-green'}`} />
              <div>
                <div className="text-2xs text-text-tertiary uppercase tracking-wider">Current Regime</div>
                <div className={`text-xl font-mono font-bold ${switchTriggered ? 'text-red' : 'text-green'}`}>
                  {(currentRegime ?? '').replace(/_/g, ' ').toUpperCase()}
                </div>
              </div>
            </div>
            <div className="text-right">
              <div className="text-2xs text-text-tertiary">Equity-Bond ρ</div>
              <div className={`text-base font-mono ${getCorrelationColor(equityBondCorrelation)}`}>
                {equityBondCorrelation.toFixed(3)}
              </div>
            </div>
          </div>

          {switchTriggered && (
            <div className="mt-2 p-2 border border-red bg-red/10 flex items-center gap-2">
              <AlertTriangle className="w-3 h-3 text-red" />
              <span className="text-xs text-red">Switch: {(fallbackStrategy ?? '').replace(/_/g, ' ')}</span>
            </div>
          )}
        </div>

        {/* Rolling Correlations */}
        <div className="border border-border bg-surface-1">
          <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2">
            <span className="text-2xs text-text-tertiary uppercase tracking-wider">60-Day Rolling Correlations</span>
          </div>
          <div className="p-2 space-y-2">
            {correlations.map((corr) => (
              <div key={corr?.assetPair ?? 'unknown'} className="p-2 border border-border-subtle bg-surface-2">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-medium text-text-primary">{corr?.assetPair ?? 'Unknown'}</span>
                  {getCorrelationIcon(corr?.correlation60d ?? 0)}
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-base font-mono font-bold ${getCorrelationColor(corr?.correlation60d ?? 0)}`}>
                    {(corr?.correlation60d ?? 0) > 0 ? '+' : ''}{(corr?.correlation60d ?? 0).toFixed(3)}
                  </span>
                  <span className={getRegimeTag(corr?.regime ?? 'neutral')}>
                    {corr?.regime ?? 'neutral'}
                  </span>
                </div>
                <p className="text-2xs text-text-secondary mt-1">{corr?.interpretation ?? ''}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Risk Parity Adjustment */}
        <div className="p-3 border border-border bg-surface-1">
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Risk Parity Adjustment</div>

          <div className="grid grid-cols-2 gap-3 mb-2">
            <div>
              <div className="text-2xs text-text-tertiary mb-1">Standard</div>
              <div className="space-y-1">
                {Object.entries(normalWeights).map(([asset, weight]) => (
                  <div key={asset} className="flex items-center justify-between text-xs">
                    <span className="text-text-secondary capitalize">{asset}</span>
                    <span className="font-mono text-text-primary">{((weight ?? 0) * 100).toFixed(0)}%</span>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <div className="text-2xs text-text-tertiary mb-1">{switchTriggered ? 'Adjusted' : 'Current'}</div>
              <div className="space-y-1">
                {Object.entries(adjustedWeights).map(([asset, weight]) => (
                  <div key={asset} className="flex items-center justify-between text-xs">
                    <span className="text-text-secondary capitalize">{asset}</span>
                    <span className={`font-mono ${switchTriggered && weight !== normalWeights[asset] ? 'text-amber' : 'text-text-primary'}`}>
                      {((weight ?? 0) * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <p className="text-xs text-text-secondary border-t border-border-subtle pt-2">
            {riskParityRationale}
          </p>
        </div>
      </div>
    </div>
  );
}
