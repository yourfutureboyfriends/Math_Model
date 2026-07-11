// Phase 8 — Factor Rotation Section (Redesigned)
// AQR Factor Rotation Engine with terminal aesthetic

import { cn } from '@/lib/utils';
import { ArrowUpRight, ArrowDownRight } from 'lucide-react';
import type { FactorRotationData } from '@/types';
import { useMacroStore } from '@/store/macroStore';

interface FactorRotationSectionProps {
  data?: FactorRotationData;
}

export function FactorRotationSection({ data }: FactorRotationSectionProps) {
  const _fullDash = useMacroStore((s) => s.fullDashboard);
  if (!data) data = (_fullDash as any)?.["factorRotation"] as any;

  if (!data) return null;

  const getSignalTag = (signal: string) => {
    switch (signal) {
      case 'OVERWEIGHT':
      case 'SLIGHT OVERWEIGHT':
        return 'signal-tag overweight';
      case 'UNDERWEIGHT':
      case 'SLIGHT UNDERWEIGHT':
        return 'signal-tag underweight';
      default:
        return 'signal-tag neutral';
    }
  };

  const getScoreBarColor = (score: number) => {
    if (score >= 0.5) return 'bg-green';
    if (score >= 0) return 'bg-bloomberg';
    if (score >= -0.5) return 'bg-amber';
    return 'bg-red';
  };

  return (
    <div id="factor-rotation" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">◆</span>
          <h2 className="section-title">Factor Rotation</h2>
          <span className="section-meta">{data.currentRegime}</span>
        </div>
      </div>

      <div className="space-y-3">
        {/* Factor Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {(data.factors ?? []).map((factor) => (
            <div
              key={factor.ticker}
              className="border border-border bg-surface-1 p-3"
            >
              <div className="flex items-center justify-between mb-2">
                <div>
                  <div className="text-base font-mono font-bold text-text-primary">{factor.ticker}</div>
                  <div className="text-2xs text-text-tertiary">{factor.name}</div>
                </div>
                <span className={getSignalTag(factor.signal)}>
                  {factor.signal.replace('SLIGHT ', 'SL ')}
                </span>
              </div>

              {/* Score bar */}
              <div className="mb-2">
                <div className="h-1 bg-surface-4 relative">
                  <div
                    className={cn('h-full absolute', getScoreBarColor(factor.compositeScore))}
                    style={{
                      width: `${Math.min(50, Math.abs(factor.compositeScore) / 1.8 * 50)}%`,
                      left: factor.compositeScore >= 0 ? '50%' : `${50 - Math.abs(factor.compositeScore) / 1.8 * 50}%`,
                    }}
                  />
                  <div className="absolute top-0 bottom-0 left-1/2 w-px bg-text-tertiary/30" />
                </div>
              </div>

              {/* Metrics */}
              <div className="grid grid-cols-2 gap-2 text-2xs mb-2">
                <div>
                  <span className="text-text-tertiary">3M:</span>
                  <span className={cn('font-mono ml-1', factor.momentum3m >= 0 ? 'text-green' : 'text-red')}>
                    {factor.momentum3m >= 0 ? '+' : ''}{factor.momentum3m.toFixed(1)}%
                  </span>
                </div>
                <div>
                  <span className="text-text-tertiary">vs SPY:</span>
                  <span className={cn('font-mono ml-1', factor.relativeStrength >= 0 ? 'text-green' : 'text-red')}>
                    {factor.relativeStrength >= 0 ? '+' : ''}{factor.relativeStrength.toFixed(1)}%
                  </span>
                </div>
              </div>

              {/* Rationale */}
              <p className="text-2xs text-text-secondary">{factor.rationale}</p>
            </div>
          ))}
        </div>

        {/* Top Picks and Avoid */}
        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 border border-border bg-surface-1">
            <div className="flex items-center gap-2 mb-2">
              <ArrowUpRight className="w-3 h-3 text-green" />
              <span className="text-xs font-medium text-text-primary">Top Picks</span>
            </div>
            <div className="flex flex-wrap gap-1">
              {(data.topPicks ?? []).map((ticker) => (
                <span key={ticker} className="signal-tag bullish text-2xs">
                  {ticker}
                </span>
              ))}
            </div>
          </div>
          <div className="p-3 border border-border bg-surface-1">
            <div className="flex items-center gap-2 mb-2">
              <ArrowDownRight className="w-3 h-3 text-red" />
              <span className="text-xs font-medium text-text-primary">Avoid</span>
            </div>
            <div className="flex flex-wrap gap-1">
              {(data.avoid ?? []).map((ticker) => (
                <span key={ticker} className="signal-tag bearish text-2xs">
                  {ticker}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Regime Summary */}
        <div className="p-3 border border-amber bg-amber-dim">
          <div className="flex items-start gap-2">
            <span className="text-xs font-medium text-amber">Note:</span>
            <p className="text-xs text-text-secondary">{data.regimeFactorSummary}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
