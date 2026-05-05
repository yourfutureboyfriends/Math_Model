// Phase 8 — Liquidity Conditions Section (Redesigned)
// Liquidity conditions with terminal aesthetic

import { Droplets, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { LiquidityConditionsData } from '@/types';

interface LiquiditySectionProps {
  data?: LiquidityConditionsData;
}

export function LiquiditySection({ data }: LiquiditySectionProps) {
  if (!data) return null;

  const getTrendIcon = (trend: string) => {
    switch (trend.toLowerCase()) {
      case 'easing':
        return <TrendingUp className="w-3 h-3 text-green" />;
      case 'tightening':
        return <TrendingDown className="w-3 h-3 text-red" />;
      default:
        return <Minus className="w-3 h-3 text-text-tertiary" />;
    }
  };

  const getStatusTag = (regime: string) => {
    switch (regime.toLowerCase()) {
      case 'easy':
        return 'signal-tag bullish';
      case 'tight':
        return 'signal-tag bearish';
      default:
        return 'signal-tag neutral';
    }
  };

  return (
    <div id="liquidity" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">29</span>
          <h2 className="section-title">Liquidity Conditions</h2>
          <span className="section-meta">{data.regime.toUpperCase()}</span>
        </div>
      </div>

      <div className="space-y-3">
        {/* Composite Score */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Droplets className="w-3 h-3 text-text-secondary" />
              <div>
                <div className="text-2xs text-text-tertiary">Composite Score</div>
                <div className={`text-xl font-mono font-bold ${data.compositeScore > 0 ? 'text-green' : data.compositeScore < 0 ? 'text-red' : 'text-text-secondary'}`}>
                  {data.compositeScore >= 0 ? '+' : ''}{data.compositeScore.toFixed(2)}σ
                </div>
              </div>
            </div>
            <span className={getStatusTag(data.regime)}>
              {data.regime}
            </span>
          </div>
        </div>

        {/* Indicators Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {data.indicators.map((indicator) => (
            <div key={indicator.name} className="p-2 bg-surface-1 border border-border">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-text-primary">{indicator.name}</span>
                {getTrendIcon(indicator.trend)}
              </div>
              <div className="flex items-baseline gap-2 mb-1">
                <span className="text-base font-mono font-bold text-text-primary">{indicator.formatted}</span>
                <span className={`text-2xs font-mono ${indicator.zScore > 0 ? 'text-green' : indicator.zScore < 0 ? 'text-red' : 'text-text-tertiary'}`}>
                  ({indicator.zScore >= 0 ? '+' : ''}{indicator.zScore.toFixed(2)}σ)
                </span>
              </div>
              <p className="text-2xs text-text-secondary">{indicator.interpretation}</p>
            </div>
          ))}
        </div>

        {/* Policy Stance */}
        <div className="grid grid-cols-2 gap-2">
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary mb-1">Fed Policy</div>
            <div className={`text-sm font-medium ${data.fedPolicyStance === 'Restrictive' ? 'text-red' : data.fedPolicyStance === 'Accommodative' ? 'text-green' : 'text-text-primary'}`}>
              {data.fedPolicyStance}
            </div>
          </div>
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary mb-1">Credit</div>
            <div className={`text-sm font-medium ${data.creditAvailability === 'Tight' ? 'text-red' : data.creditAvailability === 'Easy' ? 'text-green' : 'text-text-primary'}`}>
              {data.creditAvailability}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
