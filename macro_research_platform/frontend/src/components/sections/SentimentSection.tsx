// Phase 8 — Sentiment & Risk Appetite Section (Redesigned)
// Unified panel with options intelligence integration

import { cn } from '@/lib/utils';
import type { SentimentRiskData, OptionsIntelligenceData } from '@/types';

interface SentimentSectionProps {
  data?: SentimentRiskData;
  optionsData?: OptionsIntelligenceData;
}

export function SentimentSection({ data, optionsData }: SentimentSectionProps) {
  if (!data) return null;

  const getRiskColor = (value: number) => {
    if (value > 75) return 'text-green';
    if (value > 50) return 'text-blue';
    if (value < 25) return 'text-red';
    if (value < 40) return 'text-amber';
    return 'text-text-secondary';
  };

  const getPercentileBar = (percentile: number) => {
    const width = Math.max(0, Math.min(100, percentile));
    let color = 'bg-green';
    if (percentile > 75) color = 'bg-green';
    else if (percentile > 50) color = 'bg-blue';
    else if (percentile > 25) color = 'bg-amber';
    else color = 'bg-red';

    return (
      <div className="w-full h-1 bg-surface-4">
        <div className={`h-full ${color}`} style={{ width: `${width}%` }} />
      </div>
    );
  };

  return (
    <div id="sentiment" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">14</span>
          <h2 className="section-title">Sentiment & Risk Appetite</h2>
        </div>
      </div>

      <div className="space-y-3">
        {/* Main Header */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-0.5">Risk Appetite Index</div>
              <div className={`text-xl font-mono font-bold ${getRiskColor(data.compositeRiskAppetite)}`}>
                {data.compositeRiskAppetite.toFixed(1)}
              </div>
            </div>
            <span className={data.regime === 'Risk-On' ? 'signal-tag bullish' : data.regime === 'Risk-Off' ? 'signal-tag bearish' : 'signal-tag neutral'}>
              {data.regime.toUpperCase()}
            </span>
          </div>
        </div>

        {/* Options Intelligence */}
        {optionsData && (
          <div className="border border-border bg-surface-1">
            <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2">
              <span className="text-2xs text-text-tertiary uppercase tracking-wider">Options Intelligence</span>
            </div>
            <div className="p-2">
              {/* Options Fear Composite */}
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-text-secondary">Fear Composite</span>
                <span className="font-mono text-sm text-text-primary">
                  {optionsData.optionsFearComposite.toFixed(1)}
                </span>
              </div>
              <div className="h-1 bg-surface-4 mb-3">
                <div
                  className="h-full bg-accent"
                  style={{ width: `${optionsData.optionsFearComposite}%` }}
                />
              </div>

              {/* Component Breakdown */}
              <div className="grid grid-cols-2 gap-2 text-2xs">
                {optionsData.components.vix && (
                  <div className="flex justify-between">
                    <span className="text-text-tertiary">VIX</span>
                    <span className="font-mono text-text-primary">{optionsData.components.vix.value}</span>
                  </div>
                )}
                {optionsData.components.vvix && (
                  <div className="flex justify-between">
                    <span className="text-text-tertiary">VVIX</span>
                    <span className="font-mono text-text-primary">{optionsData.components.vvix.value}</span>
                  </div>
                )}
                {optionsData.components.skew && (
                  <div className="flex justify-between">
                    <span className="text-text-tertiary">SKEW</span>
                    <span className="font-mono text-text-primary">{optionsData.components.skew.value}</span>
                  </div>
                )}
                {optionsData.components.putCallRatio && (
                  <div className="flex justify-between">
                    <span className="text-text-tertiary">P/C</span>
                    <span className="font-mono text-text-primary">{optionsData.components.putCallRatio.value}</span>
                  </div>
                )}
              </div>

              {/* Contrarian Signal */}
              {optionsData.contrarian.signal !== 'NEUTRAL' && (
                <div className={`mt-2 p-2 border ${optionsData.contrarian.signal === 'BULLISH' ? 'bg-green-dim border-green' : 'bg-amber-dim border-amber'}`}>
                  <span className={`text-xs font-medium ${optionsData.contrarian.signal === 'BULLISH' ? 'text-green' : 'text-amber'}`}>
                    Contrarian: {optionsData.contrarian.signal}
                  </span>
                  <p className="text-2xs text-text-secondary mt-0.5">{optionsData.contrarian.note}</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Sentiment Gauges */}
        <div className="border border-border bg-surface-1">
          <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2">
            <span className="text-2xs text-text-tertiary uppercase tracking-wider">Sentiment Gauges</span>
          </div>
          <div className="p-2 space-y-2">
            {data.gauges.map((gauge) => (
              <div key={gauge.name}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-text-secondary">{gauge.name}</span>
                  <span className="text-2xs text-text-tertiary">{gauge.percentile.toFixed(0)}th %ile</span>
                </div>
                {getPercentileBar(gauge.percentile)}
                <div className="flex items-center justify-between mt-1">
                  <span className="text-sm font-mono text-text-primary">{gauge.formatted}</span>
                  <span className="text-2xs text-text-tertiary">{gauge.signal}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Cross-Asset Momentum */}
        <div className="p-2 border border-border bg-surface-1">
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Cross-Asset Momentum</div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-text-secondary">Avg (3M)</span>
            <span className={cn('font-mono text-sm', data.crossAssetMomentum.averageMomentum >= 0 ? 'text-green' : 'text-red')}>
              {data.crossAssetMomentum.averageMomentum >= 0 ? '+' : ''}{data.crossAssetMomentum.averageMomentum.toFixed(1)}%
            </span>
          </div>
          <div className="grid grid-cols-3 gap-1">
            {data.crossAssetMomentum.assets.slice(0, 6).map((asset) => (
              <div key={asset.asset} className="text-2xs p-1 bg-surface-2 flex justify-between">
                <span className="text-text-tertiary">{asset.asset}</span>
                <span className={cn('font-mono', asset.momentum3m >= 0 ? 'text-green' : 'text-red')}>
                  {asset.momentum3m >= 0 ? '+' : ''}{asset.momentum3m.toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
