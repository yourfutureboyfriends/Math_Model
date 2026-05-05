// Phase 8 — International Macro Section (Redesigned)
// Global macro regime comparison with terminal aesthetic

import { Globe, AlertTriangle, ArrowRightLeft, Activity } from 'lucide-react';
import type { InternationalMacroData } from '@/types';

interface InternationalMacroSectionProps {
  data?: InternationalMacroData;
}

export function InternationalMacroSection({ data }: InternationalMacroSectionProps) {
  if (!data) return null;

  const regions = [
    { key: 'US', label: 'US', flag: '🇺🇸' },
    { key: 'EU', label: 'EU', flag: '🇪🇺' },
    { key: 'UK', label: 'UK', flag: '🇬🇧' },
    { key: 'Japan', label: 'JP', flag: '🇯🇵' },
  ] as const;

  const getRegimeTag = (regime: string) => {
    if (regime.includes('On') || regime.includes('Expansion')) return 'signal-tag bullish';
    if (regime.includes('Off') || regime.includes('Contraction')) return 'signal-tag bearish';
    return 'signal-tag neutral';
  };

  const getLiquidityTag = (score: number) => {
    if (score > 50) return 'signal-tag bullish';
    if (score < 30) return 'signal-tag bearish';
    return 'signal-tag warning';
  };

  return (
    <div id="international" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">27</span>
          <h2 className="section-title">International Macro</h2>
        </div>
      </div>

      <div className="space-y-3">
        {/* Global Liquidity Summary */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Globe className="w-3 h-3 text-text-secondary" />
              <div>
                <div className="text-2xs text-text-tertiary uppercase tracking-wider">
                  Global Liquidity
                </div>
                <div className="text-xl font-mono font-bold text-text-primary">
                  {data.globalLiquidityComposite?.toFixed(1) ?? 'N/A'}
                </div>
              </div>
            </div>
            <span className={getLiquidityTag(data.globalLiquidityComposite ?? 50)}>
              {(data.globalLiquidityComposite ?? 50) > 50
                ? 'Accommodative'
                : (data.globalLiquidityComposite ?? 50) < 30
                  ? 'Tight'
                  : 'Neutral'}
            </span>
          </div>

          {/* Liquidity Gauge */}
          <div className="mt-2">
            <div className="h-1 bg-surface-4 relative">
              <div
                className="absolute top-0 bottom-0 bg-accent"
                style={{ width: `${data.globalLiquidityComposite ?? 50}%` }}
              />
            </div>
            <div className="flex justify-between text-2xs text-text-tertiary mt-1">
              <span>Tight</span>
              <span>Neutral</span>
              <span>Accommodative</span>
            </div>
          </div>
        </div>

        {/* Regional Comparison Grid */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
          {regions.map(({ key, label, flag }) => {
            const region = data.regions?.[key];
            if (!region) return null;
            return (
              <div key={key} className="p-2 bg-surface-1 border border-border">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-sm">{flag}</span>
                  <span className="text-xs font-medium text-text-primary">{label}</span>
                </div>

                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-2xs text-text-tertiary">Regime</span>
                    <span className={getRegimeTag(region.regime || '')}>
                      {(region.regime || 'Unknown').slice(0, 8)}
                    </span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-2xs text-text-tertiary">Growth</span>
                    <span className={`font-mono text-xs ${(region.growth || 0) > 0 ? 'text-green' : 'text-red'}`}>
                      {(region.growth || 0) > 0 ? '+' : ''}{(region.growth || 0).toFixed(1)}%
                    </span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-2xs text-text-tertiary">Inflation</span>
                    <span className="font-mono text-xs text-text-primary">
                      {(region.inflation || 0).toFixed(1)}%
                    </span>
                  </div>

                  {region.confidence && (
                    <div className="flex items-center justify-between">
                      <span className="text-2xs text-text-tertiary">Conf</span>
                      <div className="w-10 h-1 bg-surface-4">
                        <div
                          className="h-full bg-accent"
                          style={{ width: `${region.confidence * 100}%` }}
                        />
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Regime Divergences */}
        {data.regimeDivergences?.length > 0 && (
          <div className="p-3 border border-amber bg-amber-dim">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-3 h-3 text-amber" />
              <span className="text-xs font-medium text-amber">
                Regime Divergences
              </span>
            </div>
            <div className="space-y-1">
              {data.regimeDivergences.map((div, idx) => (
                <div key={idx} className="flex items-center gap-2 p-1.5 bg-surface-1">
                  <span className="text-xs text-text-secondary">{div.pair}</span>
                  <div className="flex items-center gap-2 text-2xs">
                    <span className="signal-tag neutral">{div.us}</span>
                    <ArrowRightLeft className="w-3 h-3 text-text-tertiary" />
                    <span className="signal-tag neutral">{div.other}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* FX Implications */}
        {data.fxImplications?.length > 0 && (
          <div className="border border-border bg-surface-1">
            <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2 flex items-center gap-2">
              <Activity className="w-3 h-3 text-text-tertiary" />
              <span className="text-2xs text-text-tertiary uppercase tracking-wider">FX Implications</span>
            </div>
            <div className="p-2 grid grid-cols-1 md:grid-cols-2 gap-2">
              {data.fxImplications.map((fx, idx) => (
                <div key={idx} className="p-2 bg-surface-2 border border-border-subtle">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono font-medium text-text-primary">
                      {fx.pair}
                    </span>
                    <span className={`signal-tag ${fx.bias === 'bullish' ? 'bullish' : fx.bias === 'bearish' ? 'bearish' : 'neutral'} text-2xs`}>
                      {fx.bias}
                    </span>
                  </div>
                  <p className="text-2xs text-text-secondary">{fx.reason}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Last Updated */}
        <div className="text-2xs text-text-tertiary text-right">
          Last: {new Date(data.lastUpdated).toLocaleDateString()}
        </div>
      </div>
    </div>
  );
}
